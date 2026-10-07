# hetero_k5 启动前端点健康探针（2026-08-27）

> 本探针只决定是否值得启动已预注册的 hetero 小筛，不进入能力、成本或晋升证据。
> 写定时间晚于 P1 VOID 归档、早于探针启动；runtime 锚仍为
> `codex/b1-4k-canary @ cedad82`。

## 命令与口径

- 数据：`sample_data/dev.jsonl` 三题；
- 变体：仅 `current`（C0），不提前观察 hetero 对比；
- 参数：rounds=1、workers=3、timeout=90s、retry=1、temperature=0.6；
- 输出：`tmp/hetero_k5_2026-08-27/health_dev.json`；
- 判定只读 `model_error`，不看 correct、invalid 或答案内容。

## 冻结判定

- 3/3 记录均无 `model_error`：`HEALTHY`，允许紧接着启动
  `hetero_k5_screen_preregistration_2026-08-27.md` 的 complex48 小筛；
- 任一记录出现 `model_error`、runner 熔断、进程异常或工件不完整：`UNHEALTHY`，当前窗口
  停止，不启动 hetero；
- 当前窗口最多执行一次探针，不通过后不得反复探测直到“抽到健康”。后续另一个明确时间窗
  可重新建立新的健康探针记录。
