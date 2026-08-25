# PoT/TIR 受限执行器设计规格（2026-08-22）

> 状态：已评审待实现。实现会话请使用 TDD（先失败测试后实现），按 §9 工作分解推进。
> 本文自包含：新会话无需回溯历史对话即可开工。

## 0. 背景与证据基础

- 仓库：`D:\project\challenge_cup_2026\Challenge-Cup-2026`，`main` 分支
  （e8bc30b 合并投票线 + 6958485 推送远端）。当前官方提交路径 =
  `SUBMISSION_CONFIG`（user_agent.py）：F+4096 主调用 + k=5 自适应共识投票，
  L0 算术单调用，其余实验开关全关。
- 动机：k3/k5 两轮交错 A/B（docs/experiments/adaptive_vote_*_ab_2026-08-22.md）证明错误主体是
  「一致性能力缺口」——多次采样都错，多数投票无杠杆。PoT/TIR 把算术/代数计算卸载到
  确定性执行器，直接攻击该类错误。
- 文献依据：PAL/PoT、ToRA、OpenMathInstruct-2（计算密集集上程序化求解稳定优于纯 CoT）。
- 预期收益人群：choice / fill_blank / calculation 三类数值题中的「建模对、计算错」子集。

## 1. 硬约束（不可违反）

1. 平台只暴露 `client.chat(messages, temperature, max_tokens)`；不得访问 client 私有字段。
2. 执行器必须进程内 AST 白名单解释器：禁 `exec()/eval()/import/属性访问/下标/subprocess/
   网络/文件 IO/递归`。模式照抄 `sympy_adapter.py` 的既有先例（post-hoc 软超时 +
   诚实标注 warnings）。
3. 所有新开关默认关；只有 `SUBMISSION_CONFIG` 是显式开启点，回滚 = 删一行。
4. trace 不保存程序原文与原始 stdout，仅保存状态、机器可读 reason、answer_extracted 布尔、
   duration_ms。
5. 反过拟合：prompt 与语法白名单必须是通用数学能力，禁止绑定开发集题面/题号。
6. 晋升必须走预注册门（§7），同窗口逐题交错 + McNemar（复用
   `scripts/evaluate_protocol_ab.py --interleave-items` + `scripts/analyze_paired_ab.py`）。

## 2. 三种接入模式（按风险递增分阶段）

| 模式 | 触发 | 行为 | 启用时机 |
| --- | --- | --- | --- |
| C: TIR-first（本规格主目标） | 数值题型（choice/fill_blank/calculation）且 `enable_tir_first=True` | 主调用替换为「只输出计算程序」→ 执行 → 最后一个 print 值即候选答案；失败时至多一次带错误类别的修复调用 | 实验 T1/T2 |
| A: 程序救援 | 非 TIR 路径且 `_has_clear_answer` 为 False（含截断） | 条件重试改为索要程序而非原样重发；原 Invalid 题变可解，纯增量 | T2 通过后单独评估 |
| B: 程序交叉验证 | CoT 已产出答案 | 追加验证程序重算，不一致降置信 | 远期融合阶段，本文不展开 |

与 k5 投票的关系：TIR 候选携带 `evidence=[{"source":"pot_executor", ...}]` 进入等价分组
参与共识；`_select_candidate` 已有 tool_rank 通道可承载「程序验证通过」证据。

## 3. 执行器 `pot_executor.py` 规格

新建模块，公开接口：

```python
@dataclass(frozen=True)
class PotExecutorConfig:
    max_source_chars: int = 4000
    max_ast_nodes: int = 300
    max_symbols: int = 12
    max_loop_span: int = 10000        # b-a 上界（静态检查）
    max_int_exponent: int = 64        # 整数字面量指数绝对值上界
    soft_timeout_seconds: float = 10.0

def execute_program(source: str, config=None) -> dict:
    """返回 {status: SUCCESS|UNSUPPORTED|ERROR, reason: str|None,
              answer: str|None}   # answer 已经 normalize_answer() 处理"""
```

### 3.1 语句级支持矩阵

| 构造 | v1 | 守卫 / 拒绝原因 |
| --- | --- | --- |
| `name = expr` | ✅ | 变量总数 ≤ max_symbols；禁止下标目标 |
| `print(expr)` | ✅ | 至少一次；取最后一个非空 stdout 行为答案 |
| `for i in range(a, b)` | ✅ | a/b 须为整型字面量或已知常量名；`b-a ≤ max_loop_span` |
| if / while / def / class / lambda / import / from / try / with / del / global | ❌ | `unsupported:<construct>` |

### 3.2 表达式白名单

| 类别 | 允许项 |
| --- | --- |
| 运算 | BinOp: `+ - * / // % **`；UnaryOp: UAdd/USub；Compare 仅 `== != < <= > >=` 且两操作数均数值 |
| 字面量 | int（指数位受 max_int_exponent 约束）、float、str 仅允许作为 Symbol 名实参 |
| 名称 | 用户赋值变量 + 白名单函数名 + 常量 |
| sympy 对象/常量 | `Symbol Rational Integer pi E I oo` |
| sympy 函数 | `simplify expand factor solve nsimplify sqrt Abs log exp sin cos tan diff integrate Sum N` |
| 内置 | `int float abs min max sum round range`（range 仅用于 for 头） |

### 3.3 拒绝规则（安全面）

- Attribute / Subscript / Starred / Lambda / ListComp / DictComp / comprehension /
  f-string JoinedStr / Await / Yield / Global / Nonlocal → 一律拒。
- Call 仅允许白名单名字面调用（`ast.Name` func），禁止 `getattr/setattr/eval/exec/
  compile/__import__/open/input/input` 及任何字符串拼接出的动态名。
- 幂运算：任一侧为整型字面量指数时 |exp| ≤ 64；符号指数交由 sympy 求值并受软超时兜底。

### 3.4 输出契约

stdout 最后一个非空行 → `normalize_answer()` → answer；无输出 → `no_output`；
解析期拒绝 → UNSUPPORTED + reason；运行期异常（含软超时）→ ERROR + reason
（如 `runtime_error:ZeroDivisionError`、`timeout`）。全程确定性，无随机源。

### 3.5 实现提示

解释器循环：`ast.parse(mode="exec")` → 逐语句 walk；环境用普通 dict；
sympy 对象直接参与 Python 运算（`Integer(1)+1` 天然可用）；每次 BinOp 后可选
`sympy.count_ops` 抽样计时。软超时采用 sympy_adapter 同款 post-hoc 测量并在
warnings 中注明。

## 4. Prompt 契约（POT_PROGRAM_PROMPT，零样本起步）

```text
你是数学计算引擎。只用一段 Python 程序求解本题，规则：
1. 只使用以下能力：赋值语句、print(...)、for i in range(a,b)、以及这些名称：
   Symbol Rational Integer pi E I oo simplify expand factor solve nsimplify
   sqrt Abs log exp sin cos tan diff integrate Sum N float round int abs min max sum range
2. 禁止 import、函数定义、while、if、列表字典、属性访问（不要写 x.subs(...) 这类写法）。
3. 最后一行必须是 print(<最终答案表达式>)。
4. 不要输出任何解释、思考过程、markdown 代码围栏；从第一行起就是程序本身。
```

- 若 T1 测得格式遵循率 <70%：追加 2 个极短 few-shot（格式示例，非方法提示——与已失败的
  method-card RAG 不同类，需在实验记录中区分归因）。
- 长推理模型可能仍输出 thinking：沿用现有 `_has_placeholder_answer`/标记解析卫生逻辑，
  解析不到程序按 `no_program` 记录并触发修复调用。

## 5. user_agent.py 接线

AgentConfig 新增（全部默认关）：

```python
enable_tir_first: bool = False      # 模式 C
enable_pot_rescue: bool = False     # 模式 A（T2 后评估）
pot_max_tokens: int = 1536          # 程序短于推理
pot_repair_calls: int = 1           # 失败后带错误类别的修复上限
```

接线点：
- `_generate_candidates` 数值题型分支前：`enable_tir_first` → 用 POT_PROGRAM_PROMPT
  生成程序 → execute → 成功则候选 `answer=规范化输出`、`solution=程序文本`（内存内）、
  evidence 附 pot_executor SUCCESS；失败且 repair 配额未用时发起修复调用
  （prompt 附 `上一程序失败原因：<reason>`）。
- 条件重试分支：`enable_pot_rescue` 时重试 prompt 换成 POT_PROGRAM_PROMPT。
- trace 事件：`{"step":"pot_execute","status":...,"reason":...,"answer_extracted":bool,
  "duration_ms":int}`；候选 evidence：`{"source":"pot_executor","claim_status":
  "SUPPORTED"|"REFUTED"|None}`。
- runner/gate：VARIANTS 增加 `tir_first`（在 SUBMISSION_CONFIG 等价参数之上开
  enable_tir_first，即对照臂=当前提交配置，单变量=TIR 开关）；gate 增益集合加入
  `tir_first`；budget_summary 如实反映 cap。

## 6. 测试矩阵（全部本地零 API）

1. 语法接受矩阵：§3.1–3.2 每个 ✅ 项至少一正例；每个 ❌ 构造至少一负例断言
   UNSUPPORTED+精确 reason。
2. 攻击面：`__import__("os")`、`getattr`、`eval("...")`、字符串拼接动态调用、
   `while True`、`10**10**10`、超长源码、超节点数、未知名引用。
3. 正确性样例 ≥20：solve 方程组、integrate 定积分、Sum 级数、循环累加、Rational 精确分数、
   sqrt 化简、diff+solve 极值。
4. 集成：FakeClient 返回程序 → 候选生成/evidence/trace；坏程序→修复路径→好程序；
   两次修复失败→按原路径降级。
5. 确定性：同一程序重复执行结果逐字节一致。

## 7. 实验阶梯（预注册）

| 阶段 | 设计 | 判定 | 预算 |
| --- | --- | --- | --- |
| T1 可行性 | `tir_first` 单臂跑公共集+复杂集各 1 轮（不需要对照臂） | 程序有效率 ≥70% 且 unsupported 分布明确 → 进 T2；否则迭代语法/prompt | ≈25 min |
| T2 晋升门 | 交错双臂：SUBMISSION_CONFIG vs SUBMISSION_CONFIG+tir_first，复杂冻结集 ×4 轮 | 净增 ≥8 题/192 item-rounds 且 McNemar p<0.05 → 晋升；方向正不显著 → 团队判断项（同 k5 先例） | ≈90 min |
| T3 回归 | 同设计公共集 ×2 轮 | 不得显著回退 | ≈45 min |

## 8. 回滚

所有 flag 默认关；SUBMISSION_CONFIG 未加 TIR 字段即整体回退。执行器为独立模块，
删除 import 即完全移除。

## 9. 工作分解（新会话执行顺序）

1. `pot_executor.py` + §6 全部测试（纯本地，半天）
2. AgentConfig/Prompt/trace 接线 + 集成测试 + VARIANTS/gate 注册（半天）
3. T1 冒烟 → 按 unsupported 分布迭代一轮语法/prompt → 发起 T2 并挂后台监控
   （监控流程与 k5 实验相同：WMI 分离进程 + JSON 轮询 + 每轮健康探针）
4. 分析出结论 → 报告落 docs/ → 提交

## 10. 明确不做（v1）

- while/if/函数/递归/容器类型；MCP/stdio 工具服务；LaTeX→程序自动转换；
- 多语言执行器（仅 Python 语法子集）；并行多程序投票融合（留给 B 模式阶段）。
