"""Bounded Analyze--Fork--Select/Deepen--Finish relay.

The relay is an opt-in code-acceptance path.  It deliberately owns its fixed
five-call protocol instead of inheriting any mutable submission configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any, Callable


METHOD_ID = "fork_select_deepen_finish_v1"
STAGE_TOKEN_SEQUENCE = (2048, 2048, 2048, 8192, 4096)
# fsdf_de_budget_swap_v1：D/E 预算对调（总数与调用数不变）。依据：E 截断近饱和
# （length 11-13/15）而 D 常见 stop（10/14），D 有安全捐出空间；交接-first 条目
# 增量自含且 P1 裁掉未闭合尾部，4096 的 D 仍产出可用部分交接。
STAGE_TOKEN_SEQUENCE_DE_SWAP = (2048, 2048, 2048, 4096, 8192)
L0_TOKEN_SEQUENCE = (4096,)
SOFT_DEADLINE_SECONDS = 900.0
HARD_DEADLINE_SECONDS = 1080.0

_ANALYSIS_LIMIT = 1800
_ANALYSIS_FALLBACK_LIMIT = 5000
_IDEA_LIMIT = 1600
_DEEP_CONTEXT_LIMIT = 6000
_HANDOFF_LIMIT = 5000
_FINISH_CONTEXT_LIMIT = 6500
# E 的接力上下文内先为 D handoff 预留固定份额，A 摘要与选中思路不得挤占。
_FINISH_HANDOFF_RESERVE = 2000
_FINISH_LABEL_BUDGET = 64
# 多行交接候选（fsdf_multiline_handoff_v2）：在同一个 6500 总上限内把 handoff
# 优先级提高（已完成推导/未解步骤/检查结果），相应压缩 A 摘要与思路叙述。
_FINISH_HANDOFF_RESERVE_V2 = 3000
# fsdf_finish_handoff_share_v1（迭代 4）：删除"选中思路"块（其 PLAN 字段诱发 E
# 重推导），把该份额转给 D handoff 的装配上限（3000→4600），总上限 6500 不变。
_FINISH_HANDOFF_RESERVE_V2_SHARE = 4600
# 为末尾有界标记行（INCOMPLETE/CONFLICT/DROPPED/PARTIAL）预留的字符余量。
_HANDOFF_TRAILER_HEADROOM = 200

_ANALYSIS_FIELDS = ("GOAL", "ANSWER_TYPE", "CONSTRAINTS", "STRUCTURE", "BOTTLENECK")
_IDEA_FIELDS = ("BRANCH", "METHOD", "KEY_LEMMA", "PLAN", "EXPECTED_FORM", "RISK")
_HANDOFF_FIELDS = ("SELECTED_BRANCH", "CANDIDATE_D", "DERIVED", "OPEN", "CHECKS", "RISK")
# v2 交接解析收集正文的多行字段；SELECTED_BRANCH/FINAL_D 只作边界不收集。
_HANDOFF_VALUE_FIELDS = ("CANDIDATE_D", "DERIVED", "OPEN", "CHECKS", "RISK")
# 保留优先级（高→低）：裁剪时先丢 RISK，最后保留已完成推导。
_HANDOFF_KEEP_PRIORITY = ("DERIVED", "OPEN", "CHECKS", "CANDIDATE_D", "RISK")
_HANDOFF_DISPLAY_ORDER = ("CANDIDATE_D", "DERIVED", "OPEN", "CHECKS", "RISK")
# fsdf_handoff_open_first_e_v1（迭代 5）：仅改 E 侧渲染顺序——OPEN 提到 DERIVED
# 之前，让 E 先读"剩余步骤"再读推导墙（E 自顶向下读输入且截断丢尾部）。
# 装配保留优先级不变；解析与预算不变。
_HANDOFF_DISPLAY_ORDER_OPEN_FIRST = ("CANDIDATE_D", "OPEN", "DERIVED", "CHECKS", "RISK")

ANALYZE_PROMPT = """你负责 Analyze 阶段。只拆解题目，不完成整题，不输出 FINAL。
严格输出五个字段：GOAL、ANSWER_TYPE、CONSTRAINTS、STRUCTURE、BOTTLENECK。
每个字段保持简洁，说明题目目标、答案形式、定义域/边界/唯一性、核心结构和唯一瓶颈。"""

BRANCH_B_PROMPT = """你负责 Fork 的 B 分支。只提出标准构造/正向推导方法，不展开完整证明，
不计算正式终值，不输出 FINAL。严格输出 BRANCH: B、METHOD、KEY_LEMMA、PLAN（不超过6步）、
EXPECTED_FORM、RISK 六个字段。"""

BRANCH_C_PROMPT = """你负责 Fork 的 C 分支。只提出区别于标准正向推导的替代方法，优先使用反推、
极值、不变量、分类讨论、几何变换或模运算；不展开完整证明，不计算正式终值，不输出 FINAL。
严格输出 BRANCH: C、METHOD、KEY_LEMMA、PLAN（不超过6步）、EXPECTED_FORM、RISK 六个字段。"""

DEEPEN_PROMPT = """你负责 Select/Deepen 阶段。先明确选择 B 或 C 中恰好一条，再只沿选中的方法深推。
不得把两条方法融合成第三条。必须先输出 SELECTED_BRANCH: B 或 C、SELECTION_REASON、
CANDIDATE_D。随后输出 handoff 字段：SELECTED_BRANCH、CANDIDATE_D、DERIVED、OPEN、CHECKS、RISK。
可以输出 FINAL_D，但不要把未选分支全文复制进 handoff。"""

# fsdf_handoff_first_d_v1：仅改变 D 的职责表达（交接产物优先），解析、调用数与预算不变。
# 交接的可靠性由程序承担（保存/传递/完整性标记）；提示词只承载阶段约定，不是可靠保证。
# 字段沿用现有协议（DERIVED≈RESULT、RISK≈PREMISES、OPEN≈NEXT），不新增解析边界。
DEEPEN_PROMPT_V2 = """你负责 Select/Deepen 阶段。先明确选择 B 或 C 中恰好一条，不得把两条方法融合成第三条。
随后按固定顺序输出交接字段，交接产物优先，不要等完整深推之后再总结；每个字段只出现一次：
SELECTED_BRANCH: B 或 C
SELECTION_REASON: <一句话>
CANDIDATE_D: <当前候选；无法确定写 UNKNOWN>
OPEN: <下一步具体做什么：按顺序列出剩余待解步骤>
CHECKS: <已做检查及结论；未确认的检查必须写明未确认>
RISK: <当前推导依赖的前提与可能失效之处>
DERIVED: <已完成推导，每条单独一行并以“第N步:”开头；每条自含完整公式与结论，宁短勿断；随推导持续补入新条目，被截断时前面的条目仍可用>
DERIVED 是本阶段主要产物，优先保证每条完整；可以输出 FINAL_D；不要把未选分支全文复制进 handoff。"""

# fsdf_mandatory_final_d_v1（迭代 3）：DEEPEN_PROMPT_V2 的两处编辑——CANDIDATE_D
# 之后立即强制输出 FINAL_D（置于 DERIVED 之前，D 在 4096 截断下也能存活），
# 并删除可选 FINAL_D 尾句。机制：激活休眠的 deep_final 回退（P2a 在 E 未形成
# 有效终答时采纳），结构性单调——只可能影响 E 失败的 run，不会改写已确认终答。
DEEPEN_PROMPT_MFD = """你负责 Select/Deepen 阶段。先明确选择 B 或 C 中恰好一条，不得把两条方法融合成第三条。
随后按固定顺序输出交接字段，交接产物优先，不要等完整深推之后再总结；每个字段只出现一次：
SELECTED_BRANCH: B 或 C
SELECTION_REASON: <一句话>
CANDIDATE_D: <当前候选；无法确定写 UNKNOWN>
FINAL_D: <在此立即输出你认为最可能正确的唯一最终答案，只写答案本身（数值/表达式/集合）一行，字段名后直接跟值，不加解释；确实给不出任何具体答案时才写 UNKNOWN；此后即使推导有进展也不再输出 FINAL_D>
OPEN: <下一步具体做什么：按顺序列出剩余待解步骤>
CHECKS: <已做检查及结论；未确认的检查必须写明未确认>
RISK: <当前推导依赖的前提与可能失效之处>
DERIVED: <已完成推导，每条单独一行并以“第N步:”开头；每条自含完整公式与结论，宁短勿断；随推导持续补入新条目，被截断时前面的条目仍可用>
DERIVED 是本阶段主要产物，优先保证每条完整；不要把未选分支全文复制进 handoff。"""

FINISH_PROMPT = """你负责 Finish 阶段。只沿已选分支和 D 的 handoff 收尾，不重新进行方法选择，
只修复选定链路的局部错误。第一项输出 CANDIDATE_E，末尾另起一行输出唯一 FINAL。
不要输出未选分支、多个答案或格式示例；无法确认时输出 FINAL: UNKNOWN。"""

# fsdf_finish_prompt_v2（P2b）：只改变 E 的收尾职责表达，不改答案解析、调用数或预算。
# E 先补完选定链路的局部未解步骤，再回答原题实际要求的量，输出唯一确认终答；
# 不强制先填写猜测候选，也不把“已检查”之类的自述当成确定性验证。
FINISH_PROMPT_V2 = """你负责 Finish 阶段。只沿已选分支和 D 的 handoff 收尾，不重新进行方法选择，不引入新分支。
若 handoff 的 OPEN 项仍有未解步骤，先补完这些步骤；再回到原题，确认题目实际要求的最终量（不是中间量）。
完成后末尾另起一行输出唯一 FINAL: <答案>；无法确认时输出 FINAL: UNKNOWN。
不要把未确认的候选或中间结果直接当作 FINAL；不要用“已检查”之类的自述替代实际完成最后一步；
不要输出未选分支、多个答案或格式示例。"""

# fsdf_finish_compact_v1（迭代 2）：E 紧凑输出 + 得到可确认答案立即 FINAL 并停止。
# 依据：E 在 8192 下仍 10/15 截断——任务是自延展的（长叙述重推导），紧凑化让 FINAL
# 尽早进入输出流，即使后续截断终答也已落盘。答案解析、调用数与预算不变。
FINISH_PROMPT_COMPACT_V2 = """你负责 Finish 阶段。只沿已选分支和 D 的 handoff 收尾，不重新进行方法选择，不引入新分支。
输出保持紧凑：只写关键等式、中间值与结论行，每步一行，不写长段叙述，不复述题目，不重复 handoff 中已完成的推导。
若 handoff 的 OPEN 项仍有未解步骤，先按顺序补完；再回到原题，确认题目实际要求的最终量（不是中间量）。
一旦得到可确认的答案，立即另起一行输出唯一 FINAL: <答案> 并停止输出，不再做额外检查或推导；
无法确认时输出 FINAL: UNKNOWN。不要把未确认的候选或中间结果直接当作 FINAL；
不要用“已检查”之类的自述替代实际完成最后一步；不要输出未选分支、多个答案或格式示例。"""

# fsdf_finish_compact_final_v1（配对 A/B 迭代候选）：只改 E 的职责表达，
# 针对 E 截断近饱和（13/15 length）的瓶颈——推导紧凑化 + 尽早确认 FINAL。
# 答案解析、调用数与预算不变。
# 草稿保留；该候选实际采用下方 FINISH_PROMPT_COMPACT_V2 修订文本（去掉对
# 低激活机制 FINAL_D_FOR_CHECK 的引用，强化"每步一行 + 得到答案即停止"）。
FINISH_PROMPT_COMPACT = """你负责 Finish 阶段。只沿已选分支和 D 的 handoff 收尾，不重新进行方法选择，不引入新分支。
推导保持紧凑：只写关键等式与结论行，不展开长段叙述；OPEN 项未解步骤先补完。
若 handoff 中有 FINAL_D_FOR_CHECK 候选，先核查再使用：正确则沿用并给出依据，错误则修正。
一旦得到可确认的答案，立即末尾另起一行输出唯一 FINAL: <答案>，不要继续多余推导；
无法确认时输出 FINAL: UNKNOWN。不要输出未选分支、多个答案或格式示例。"""

L0_PROMPT = """这是一个已由确定性简单算式识别器命中的 L0 题。直接计算并只输出一行 FINAL: <答案>。
不要输出推理、多个答案或占位符。"""


@dataclass
class RelayResult:
    """Small result interface returned by the relay."""

    final_response: str
    trace: list[dict[str, Any]]
    extracted_answer: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_response": self.final_response,
            "extracted_answer": self.extracted_answer,
            "trace": self.trace,
        }


@dataclass(frozen=True)
class RelayOptions:
    """Independently selectable FSDF v2 reliability increments (Issue #15 spec).

    Every flag defaults to off, which reproduces the FSDF v1 behaviour byte for
    byte; ``SUBMISSION_CONFIG`` keeps v1 until each candidate passes its own
    preregistered gate.
    """

    # P0: diagnostics only — never changes model requests or final answers.
    diagnostics_v2: bool = False
    # P1: marker-bounded multi-line handoff with dedupe/conflict and
    # field/item-granular clipping inside the existing E context cap.
    multiline_handoff_v2: bool = False
    # P2a: final-answer confirmation — explicit UNKNOWN stays UNKNOWN, conflicted
    # finals fail closed, only explicitly completed results may be adopted.
    final_confirmation_v2: bool = False
    # P2b: E finishing-responsibility prompt variant (parsing/budget unchanged).
    finish_prompt_v2: bool = False
    # fsdf_handoff_first_d_v1: D-stage "handoff product first" prompt variant
    # only; parsing, call count and budgets unchanged.
    handoff_first_d: bool = False
    # fsdf_d_result_to_e_v1: inject the protocol-valid, conflict-free FINAL_D
    # into E's input as a to-be-checked candidate; selection rules unchanged.
    d_result_to_e: bool = False
    # fsdf_de_budget_swap_v1: reallocate D/E stage budgets (8192/4096 ->
    # 4096/8192); total 18432 and the 5-call cap unchanged. Targets the
    # confirmed E-truncation bottleneck (E finish_reason=length 11-13/15).
    de_budget_swap: bool = False
    # fsdf_finish_compact_final_v1 (iteration 2): E compact-output prompt with
    # an explicit stop-after-FINAL rule so the final lands before truncation;
    # parsing, calls and budgets unchanged.
    finish_compact_final: bool = False
    # fsdf_mandatory_final_d_v1 (iteration 3): D must emit FINAL_D immediately
    # after CANDIDATE_D (survives truncation), activating the dormant
    # deep_final fallback for E-failed runs. Structurally monotone: runs where
    # E formed a final are untouched.
    mandatory_final_d: bool = False
    # fsdf_finish_handoff_share_v1 (iteration 4): E-input composition — drop
    # the selected-idea block (its PLAN invites re-derivation) and raise the
    # handoff assembly reserve 3000 -> 4600 within the same 6500 context cap.
    finish_handoff_share: bool = False
    # fsdf_handoff_open_first_e_v1 (iteration 5): E-side handoff rendering
    # order only — OPEN rendered before DERIVED so E reads the remaining steps
    # first; assembly priority, parsing and budgets unchanged.
    handoff_open_first_e: bool = False


@dataclass
class _SolveState:
    started_at: float
    logical_calls: int = 0
    stage_status: dict[str, str] = field(default_factory=dict)
    analysis_packet_a: str = ""
    idea_packet_b: str = ""
    idea_packet_c: str = ""
    selected_branch: str = ""
    deep_handoff_d: str = ""
    finish_packet_e: str = ""
    candidate_history: list[str] = field(default_factory=list)
    sanitized_errors: list[str] = field(default_factory=list)
    # P0 bounded diagnostics collected during solve; emitted only when the
    # diagnostics increment is enabled. Values come from a fixed vocabulary
    # (field names / booleans / "unavailable") and never contain model text.
    diagnostics: dict[str, Any] = field(default_factory=dict)
    # fsdf_d_result_to_e_v1: D's explicit final result, shown to E for checking
    # (never auto-promoted; selection rules unchanged).
    d_candidate_for_check: str = ""


def _clip(text: str | None, limit: int) -> str:
    """Return a deterministic head/tail crop whose total length is bounded."""
    value = text if isinstance(text, str) else ""
    limit = max(0, int(limit))
    if len(value) <= limit:
        return value
    marker = "\n...[省略]...\n"
    if limit <= len(marker):
        return value[:limit]
    available = limit - len(marker)
    head = (available + 1) // 2
    tail = available - head
    return value[:head] + marker + (value[-tail:] if tail else "")


def _marker_value(text: str | None, marker: str) -> str:
    if not isinstance(text, str):
        return ""
    match = re.search(
        rf"(?im)^\s*{re.escape(marker)}\s*[:：]\s*(.*?)\s*$",
        text,
    )
    return match.group(1).strip() if match else ""


def _canonical_packet(text: str | None, fields: tuple[str, ...], limit: int, fallback_limit: int) -> str:
    values = [_marker_value(text, field) for field in fields]
    if all(values):
        return _clip("\n".join(f"{field}: {value}" for field, value in zip(fields, values)), limit)
    return _clip(text, fallback_limit)


# ── FSDF v2 parsing helpers (flag-gated; v1 helpers above stay untouched) ──
# v1 ``_marker_value`` lets the ``\s*`` after the colon cross a newline, so an
# empty marker can absorb the next protocol line, and it can never return a
# multi-line value.  The v2 readers below fix both, and are used only by the
# flag-gated increments so the shipped v1 path stays byte-compatible.

def _marker_line_pattern(marker: str) -> str:
    """Regex for one strict single-line marker read (cannot cross newlines)."""
    return rf"(?im)^[ \t]*{re.escape(marker)}[ \t]*[:：][ \t]*(.*?)[ \t]*$"


def _marker_value_strict(text: str | None, marker: str) -> str:
    """Single-line marker read that cannot cross into the next line."""
    if not isinstance(text, str):
        return ""
    match = re.search(_marker_line_pattern(marker), text)
    return match.group(1).strip() if match else ""


def _marker_occurrences(text: str | None, markers: tuple[str, ...]) -> list[str]:
    """All strict single-line values for the given marker aliases, in order."""
    values: list[str] = []
    if not isinstance(text, str):
        return values
    for marker in markers:
        for match in re.finditer(_marker_line_pattern(marker), text):
            values.append(match.group(1).strip())
    return values


# Known protocol markers that terminate a multi-line handoff block.  Longest
# names first where prefixes overlap (FINAL_D before FINAL).
_V2_KNOWN_MARKERS = (
    "SELECTED_BRANCH", "SELECTION_REASON", "CANDIDATE_D", "FINAL_D", "DERIVED",
    "OPEN", "CHECKS", "RISK", "BRANCH", "METHOD", "KEY_LEMMA", "PLAN",
    "EXPECTED_FORM", "FINAL", "GOAL", "ANSWER_TYPE", "CONSTRAINTS",
    "STRUCTURE", "BOTTLENECK",
)
_V2_MARKER_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]*)?`?(?P<marker>"
    + "|".join(_V2_KNOWN_MARKERS)
    + r")`?[ \t]*[:：]"
)
# A continuation line shaped like "短标签: 内容" starts unlabelled free text;
# it must not be pulled into the trusted handoff package.  The char after the
# colon must be whitespace, a non-digit, or line end, so "12:30" or "x:2"
# style math fragments stay inside the block.
_UNLABELED_FIELD_LINE_RE = re.compile(r"^[ \t]*([^ \t　：:]{1,24})[：:](?:[ \t]|[^\d]|$)")
# Numbered derivation steps ("第1步" / "步骤一" / "3" / "(2)" / "Step 1") are
# content, not free-text labels.
_STEP_LABEL_RE = re.compile(
    r"^(?:第\s*[0-9一二三四五六七八九十百]+\s*步|步骤\s*[0-9一二三四五六七八九十百]+"
    r"|[0-9]{1,3}|[（(][0-9]{1,3}[)）]|[Ss]tep\s*[0-9]{1,3})$"
)
# Answer-protocol tokens inside a block signal the model switched away from
# derivation content; the block ends there.
_ANSWER_PROTOCOL_TOKEN_RE = re.compile(r"FINAL|最终答案|CANDIDATE|SELECTED_BRANCH")
# A continuation line needs at least one digit/ASCII letter/math symbol to
# count as derivation content; pure prose lines end the block.
_BLOCK_CONTENT_SIGNAL_RE = re.compile(r"[0-9A-Za-z\\=+*/^<>≤≥±×÷|{}\[\]()]")


def _handoff_block_terminates(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _ANSWER_PROTOCOL_TOKEN_RE.search(stripped):
        return True
    match = _UNLABELED_FIELD_LINE_RE.match(line)
    if match and not _STEP_LABEL_RE.fullmatch(match.group(1).strip()):
        return True
    if not _BLOCK_CONTENT_SIGNAL_RE.search(stripped):
        return True
    return False


def _handoff_block_value(raw: str) -> str:
    """Value of one handoff field: same-line remainder plus continuation lines.

    Continuation lines run until the next known marker (handled by the caller's
    slicing), an unlabelled "label:" line, an answer-protocol token, or a pure
    prose line.  Free text is never folded into the trusted handoff package.
    """
    kept: list[str] = []
    for offset, line in enumerate(raw.split("\n")):
        if offset == 0:
            # remainder after the marker colon on the marker's own line
            if line.strip():
                kept.append(line.rstrip())
            continue
        if not line.strip():
            if kept:
                kept.append("")
            continue
        if _handoff_block_terminates(line):
            break
        kept.append(line.rstrip())
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept).strip()


def _parse_handoff_blocks(text: str | None) -> dict[str, list[str]]:
    """Parse all occurrences of each multi-line handoff field."""
    if not isinstance(text, str) or not text.strip():
        return {}
    matches = list(_V2_MARKER_LINE_RE.finditer(text))
    blocks: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        field = match.group("marker")
        if field not in _HANDOFF_VALUE_FIELDS:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = _handoff_block_value(text[start:end])
        if value:
            blocks.setdefault(field, []).append(value)
    return blocks


def _is_explicit_unknown(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().strip("`\"'“”‘’").strip("。.,，；;：:！!？? ")
    return text.casefold() == "unknown"


_V2_ECHO_VALUES = frozenset({
    "final", "final d", "finald", "candidate e", "candidate d",
    "selected branch", "handoff", "answer", "result", "output",
    "最终答案", "答案", "结果", "输出", "候选", "占位符",
})
_V2_EXTRA_PLACEHOLDER_VALUES = frozenset({
    "tbd", "n/a", "todo", "xxx", "待补充", "待填写", "待完善", "略", "省略",
    "同上", "placeholder", "你的答案", "未能生成有效数学答案",
})
_METHOD_DESCRIPTION_RE = re.compile(
    r"(反证法|归纳法|构造法|枚举法|待定系数|换元法|分类讨论|判别式法|消元法"
    r"|方法[：:]|解法[：:]|by\s+(?:induction|contradiction|construction|enumeration)"
    r"|using\s+the\s+method|method\s*:)",
    re.IGNORECASE,
)


def _is_answer_echo(value: str | None) -> bool:
    """True when the value merely echoes a protocol field name."""
    if not isinstance(value, str):
        return False
    text = value.strip().strip("`\"'“”‘’").strip("。.,，；;：:！!？? ")
    folded = re.sub(r"[\s_\-]+", " ", text.casefold())
    return folded in _V2_ECHO_VALUES


def _is_method_description(value: str | None) -> bool:
    """True when the value names a method without any math content."""
    if not isinstance(value, str) or not value.strip():
        return False
    if re.search(r"[0-9=+*/^<>≤≥±×÷\\]", value):
        return False
    return bool(_METHOD_DESCRIPTION_RE.search(value))


def _is_placeholder_v2(value: str | None) -> bool:
    """v1 placeholder rules plus generalized placeholders and field echoes."""
    if _is_placeholder(value):
        return True
    if _is_answer_echo(value):
        return True
    if isinstance(value, str):
        text = value.strip().strip("`\"'“”‘’").strip("。.,，；;：:！!？? ")
        if text.casefold() in _V2_EXTRA_PLACEHOLDER_VALUES:
            return True
    return False


def _is_invalid_final_value(value: str | None) -> bool:
    """Applicable answer checks for a confirmed final answer (P2a).

    Placeholder, conflict and echo/description rules apply to every answer
    type; short-scalar restrictions are deliberately not imposed here so
    proofs, sets, ordered structures and long expressions keep their own
    boundaries.
    """
    if not isinstance(value, str) or not value.strip():
        return True
    return _is_placeholder_v2(value) or _is_method_description(value)


def _confirmed_marker_values(values: list[str]) -> tuple[bool, list[str]]:
    """Reduce repeated final-marker values to (explicit abstention, distinct)."""
    if any(_is_explicit_unknown(v) for v in values):
        return True, []
    real = [v for v in values if not _is_invalid_final_value(v)]
    return False, list(dict.fromkeys(real))


def _has_unclosed_math(value: str | None) -> bool:
    """Conservative program-side check for visibly truncated math tails.

    Heuristic only (no protocol end-marker): unbalanced curly braces or a
    trailing backslash mark a value that must not reach E as complete
    evidence.  Balanced content and stray close braces are not flagged.
    """
    if not isinstance(value, str) or not value:
        return False
    depth = 0
    for ch in value:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    if depth != 0:
        return True
    return value.rstrip().endswith("\\")


def _trim_unclosed_tail(value: str) -> str:
    """Drop trailing lines until the remaining value is closed (or empty)."""
    lines = value.split("\n")
    while lines and _has_unclosed_math("\n".join(lines)):
        lines.pop()
    return "\n".join(lines).strip()


def _is_placeholder(value: str | None) -> bool:
    if not isinstance(value, str):
        return True
    text = value.strip().strip("`\"'“”‘’")
    if not text:
        return True
    folded = text.casefold()
    if folded.strip("。.;,，；:：") in {
        "unknown",
        "<answer>",
        "<result>",
        "[answer]",
        "[result]",
        "答案",
        "answer",
        "result",
    }:
        return True
    if re.fullmatch(r"<\s*(?:answer|result|答案|答案内容|具体答案)\s*>", text, re.IGNORECASE):
        return True
    if re.fullmatch(r"\[\s*(?:answer|result|答案|答案内容|具体答案)\s*\]", text, re.IGNORECASE):
        return True
    if "格式示例" in text or "format example" in folded:
        return True
    if "..." in text or "．．．" in text or "待定" == text:
        return True
    return False


def _boxed_value(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    for match in re.finditer(r"\\boxed\s*\{", text):
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        if depth == 0:
            value = text[match.end(): index - 1].strip()
            if value and not _is_placeholder(value):
                return value
    return ""


_PURE_MATH_RE = re.compile(r"^[\s0-9A-Za-z_+*/^=(){}\[\].,<>≤≥±×÷\\|%!$\-]+$")
_MATH_STOP_WORDS = re.compile(
    r"(?:answer|result|final|candidate|unknown|therefore|because|step|proof|method|"
    r"最终答案|答案|因此|所以|证明|步骤|结论|候选|未知)",
    re.IGNORECASE,
)
_IDEA_PACKET_MARKER_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?`?(?:BRANCH|METHOD|KEY_LEMMA|PLAN|EXPECTED_FORM)`?\s*[:：]"
)


def _independent_math_line(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    candidates: list[str] = []
    for line in text.splitlines():
        value = line.strip().strip("`$")
        if not value or ":" in value or "：" in value:
            continue
        if "\\boxed" in value.casefold():
            continue
        if _MATH_STOP_WORDS.search(value) or not _PURE_MATH_RE.fullmatch(value):
            continue
        if not re.search(r"\d|[=+*/^{}()\[\]\\<>≤≥±×÷|%]", value):
            continue
        candidates.append(value)
    return candidates[0] if len(candidates) == 1 else ""


def _strip_idea_packet_text(text: str | None) -> str:
    """Ignore echoed B/C packet text before extracting D handoff fields."""
    if not isinstance(text, str):
        return ""
    marker = _IDEA_PACKET_MARKER_RE.search(text)
    return text[:marker.start()] if marker else text


def match_simple_arithmetic_expression(problem: str) -> str | None:
    """Single source of the deterministic simple-arithmetic (L0) recognizer.

    ``user_agent`` routes its baseline L0 decision through this function as
    well, so the relay path and the baseline recognizer cannot drift apart.
    """
    match = re.fullmatch(
        r"\s*(?:计算|求值|calculate|evaluate)?\s*([0-9+\-*/().\s]+)\s*[?？]?\s*",
        problem,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _error_category(exc: BaseException) -> str:
    category = getattr(exc, "category", "")
    if isinstance(category, str):
        folded = category.casefold()
        if "timeout" in folded:
            return "timeout"
        if "rate" in folded or "429" in folded:
            return "rate_limit"
        if "http" in folded or folded.isdigit() or "503" in folded:
            return "http_status"
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        try:
            return "rate_limit" if int(status_code) == 429 else "http_status"
        except (TypeError, ValueError):
            return "http_status"
    if "timeout" in type(exc).__name__.casefold():
        return "timeout"
    return "model_error"


class ForkSelectDeepenFinishRelay:
    """Deep FSDF module with one small public interface."""

    def __init__(
        self,
        client: Any,
        clock: Callable[[], float] = time.monotonic,
        options: RelayOptions | None = None,
    ) -> None:
        self.client = client
        self.clock = clock
        self.options = options or RelayOptions()

    def solve(self, problem: str, problem_type: str) -> RelayResult:
        problem_text = problem if isinstance(problem, str) else str(problem)
        state = _SolveState(started_at=self.clock())
        trace: list[dict[str, Any]] = []

        if problem_type == "calculation" and match_simple_arithmetic_expression(problem_text) is not None:
            if not self._stage_allowed(state, trace, "l0", L0_TOKEN_SEQUENCE[0]):
                return self._result(state, trace, "UNKNOWN", "unknown")
            response = self._call(
                state,
                trace,
                "l0",
                L0_PROMPT,
                problem_text,
                0.6,
                L0_TOKEN_SEQUENCE[0],
            )
            final_response, source = self._select_l0_answer(response)
            return self._result(state, trace, final_response, source)

        response_a = ""
        if self._stage_allowed(state, trace, "analyze", 2048):
            response_a = self._call(state, trace, "analyze", ANALYZE_PROMPT, problem_text, 0.2, 2048) or ""
        if response_a:
            state.analysis_packet_a = _canonical_packet(
                response_a, _ANALYSIS_FIELDS, _ANALYSIS_LIMIT, _ANALYSIS_FALLBACK_LIMIT
            )
            state.stage_status["analyze"] = "ok"
        else:
            state.stage_status["analyze"] = "failed"

        response_b = ""
        if self._stage_allowed(state, trace, "fork_b", 2048):
            response_b = self._call(
                state,
                trace,
                "fork_b",
                BRANCH_B_PROMPT,
                self._fork_user_prompt(problem_text, state.analysis_packet_a, "B"),
                0.6,
                2048,
            ) or ""
        if response_b:
            state.idea_packet_b = _canonical_packet(response_b, _IDEA_FIELDS, _IDEA_LIMIT, _IDEA_LIMIT)
            state.stage_status["fork_b"] = "ok"
            state.candidate_history.append("B")
        else:
            state.stage_status["fork_b"] = "failed"

        response_c = ""
        if self._stage_allowed(state, trace, "fork_c", 2048):
            response_c = self._call(
                state,
                trace,
                "fork_c",
                BRANCH_C_PROMPT,
                self._fork_user_prompt(problem_text, state.analysis_packet_a, "C"),
                0.6,
                2048,
            ) or ""
        if response_c:
            state.idea_packet_c = _canonical_packet(response_c, _IDEA_FIELDS, _IDEA_LIMIT, _IDEA_LIMIT)
            state.stage_status["fork_c"] = "ok"
            state.candidate_history.append("C")
        else:
            state.stage_status["fork_c"] = "failed"

        methods_equal = bool(
            state.idea_packet_b
            and state.idea_packet_c
            and (
                _marker_value(state.idea_packet_b, "METHOD").casefold()
                == _marker_value(state.idea_packet_c, "METHOD").casefold()
                or state.idea_packet_b == state.idea_packet_c
            )
        )
        if state.idea_packet_b and state.idea_packet_c:
            self._event(trace, state, "fork", "ok", 0, ideas_not_diverse=methods_equal)

        deepen_max_tokens = 4096 if self.options.de_budget_swap else 8192
        response_d = ""
        if self._stage_allowed(state, trace, "deepen", deepen_max_tokens):
            if self.options.mandatory_final_d:
                deepen_prompt = DEEPEN_PROMPT_MFD
            elif self.options.handoff_first_d:
                deepen_prompt = DEEPEN_PROMPT_V2
            else:
                deepen_prompt = DEEPEN_PROMPT
            response_d = self._call(
                state,
                trace,
                "deepen",
                deepen_prompt,
                self._deepen_user_prompt(problem_text, state),
                0.2,
                deepen_max_tokens,
            ) or ""
        if response_d:
            branch = self._selected_branch(response_d, bool(state.idea_packet_b), bool(state.idea_packet_c))
            if branch:
                state.stage_status["deepen"] = "ok"
                state.selected_branch = branch
                if self.options.multiline_handoff_v2:
                    handoff_text, handoff_meta = self._handoff_v2(response_d, state)
                    state.deep_handoff_d = handoff_text
                    if handoff_meta["clipped"]:
                        state.diagnostics["handoff_clipped"] = True
                else:
                    state.deep_handoff_d = self._handoff(response_d, state)
                state.candidate_history.append("D:" + branch)
            else:
                # D 协议失败：响应存在但没有可解析的 SELECTED_BRANCH。按 D 失败处置
                # （确定性分支回退，B 优先）。D 的 FINAL_D/CANDIDATE_D 仍保留在
                # §9 答案链，但不把不可信的 D 原文交给 E。
                state.stage_status["deepen"] = "protocol_failed"
                state.sanitized_errors.append("invalid_response")
                state.selected_branch = self._available_branch(state)
                state.deep_handoff_d = self._incomplete_handoff(state.selected_branch)
                self._mark_protocol_failure(trace, state, "deepen", state.selected_branch, deepen_max_tokens)
        else:
            state.stage_status["deepen"] = "failed"
            state.selected_branch = self._available_branch(state)
            state.deep_handoff_d = self._incomplete_handoff(state.selected_branch)

        # P0 有界诊断（单一来源：协议字段状态机，缺字段/UNKNOWN/冲突/未闭合分开统计）。
        state.diagnostics.update(self._handoff_diagnostics(response_d))

        # fsdf_d_result_to_e_v1：把协议成功且唯一有效的 FINAL_D 作为"D 给出的
        # 待核查候选"供 E 查看；不改变答案选择链，不覆盖 CANDIDATE_D。
        if self.options.d_result_to_e and state.stage_status.get("deepen") == "ok" and response_d:
            _, final_d_distinct = _confirmed_marker_values(
                _marker_occurrences(response_d, ("FINAL_D",))
            )
            if len(final_d_distinct) == 1:
                state.d_candidate_for_check = _clip(final_d_distinct[0], 500)
        state.diagnostics["d_candidate_visible_to_e"] = bool(state.d_candidate_for_check)

        finish_max_tokens = 8192 if self.options.de_budget_swap else 4096
        response_e = ""
        if self._stage_allowed(state, trace, "finish", finish_max_tokens):
            if self.options.finish_compact_final:
                finish_prompt = FINISH_PROMPT_COMPACT_V2
            elif self.options.finish_prompt_v2:
                finish_prompt = FINISH_PROMPT_V2
            else:
                finish_prompt = FINISH_PROMPT
            response_e = self._call(
                state,
                trace,
                "finish",
                finish_prompt,
                self._finish_user_prompt(problem_text, state),
                0.0,
                finish_max_tokens,
            ) or ""
        if response_e:
            state.stage_status["finish"] = "ok"
            state.finish_packet_e = _clip(response_e, _FINISH_CONTEXT_LIMIT)
        else:
            state.stage_status["finish"] = "failed"

        # P0 有界诊断：候选/终答是否存在（只记录布尔，不记录内容）。
        candidate_values = [
            value
            for value in (
                _marker_occurrences(response_e, ("CANDIDATE_E",))
                + _marker_occurrences(response_d, ("CANDIDATE_D",))
            )
            if value and not _is_placeholder(value)
        ]
        state.diagnostics["candidate_present"] = bool(candidate_values)

        if self.options.final_confirmation_v2:
            final_response, source = self._select_answer_v2(response_e, response_d, state)
        else:
            final_response, source = self._select_answer(response_e, response_d)
        # fsdf_d_result_to_e_v1 锚定观测：E 的终答是否照抄注入候选（只记布尔，不记文本）。
        if state.d_candidate_for_check:
            final_text = final_response.strip() if isinstance(final_response, str) else ""
            state.diagnostics["e_final_equals_d_candidate"] = (
                bool(final_text) and final_text == state.d_candidate_for_check
            )
        return self._result(state, trace, final_response, source)

    @staticmethod
    def _fork_user_prompt(problem: str, analysis_packet: str, branch: str) -> str:
        analysis = analysis_packet or "A 状态不可用；只依据原题提出本分支思路。"
        return f"原题：\n{problem}\n\nA 状态：\n{analysis}\n\n当前分支：{branch}"

    @staticmethod
    def _deepen_user_prompt(problem: str, state: _SolveState) -> str:
        b = state.idea_packet_b or "B 思路不可用。"
        c = state.idea_packet_c or "C 思路不可用。"
        if not state.idea_packet_b and not state.idea_packet_c:
            direct = "两条分支均不可用：使用固定 direct fallback 深推，不产生新分支。"
        else:
            direct = ""
        context = _clip(
            f"A 状态：\n{state.analysis_packet_a or '不可用'}\n\nB 思路包：\n{b}\n\nC 思路包：\n{c}\n{direct}",
            _DEEP_CONTEXT_LIMIT,
        )
        return f"原题：\n{problem}\n\n{context}"

    def _finish_user_prompt(self, problem: str, state: _SolveState) -> str:
        branch = state.selected_branch or self._available_branch(state) or "UNKNOWN"
        if branch == "B":
            selected_idea = state.idea_packet_b
        elif branch == "C":
            selected_idea = state.idea_packet_c
        else:
            selected_idea = "没有可用分支；沿 D handoff 做固定 direct fallback。"
        share_mode = self.options.multiline_handoff_v2 and self.options.finish_handoff_share
        if self.options.multiline_handoff_v2:
            # v2 handoff 已经按字段/推导项粒度适配交接预留额，直接整块传入，
            # 不再二次字符裁剪；A 摘要与思路在剩余预算内压缩。
            handoff = state.deep_handoff_d or "不可用"
        else:
            raw_handoff = state.deep_handoff_d or "不可用"
            handoff = _clip(raw_handoff, _FINISH_HANDOFF_RESERVE)
            if len(handoff) < len(raw_handoff):
                state.diagnostics["handoff_clipped"] = True
        if self.options.d_result_to_e and state.d_candidate_for_check:
            # 待核查候选作为独立标注行加入 E 输入；不覆盖 CANDIDATE_D，
            # 不改变答案选择链，只扩大 E 的可见信息。
            handoff = f"{handoff}\nFINAL_D_FOR_CHECK: {state.d_candidate_for_check}"
        budget = _FINISH_CONTEXT_LIMIT - _FINISH_LABEL_BUDGET - len(handoff)
        raw_analysis = state.analysis_packet_a or "不可用"
        if share_mode:
            # 交接份额模式：删除"选中思路"块（PLAN 叙述诱发 E 重推导），
            # 其份额已在装配端转给 handoff；A 摘要占用剩余预算。
            analysis = _clip(raw_analysis, max(0, budget))
            context = f"A 约束摘要：\n{analysis}\n\nSELECTED_BRANCH: {branch}\n\nD handoff：\n{handoff}"
            if not (state.selected_branch or self._available_branch(state)):
                context += "\n没有可用分支；沿 D handoff 做固定 direct fallback。"
        else:
            raw_selected = selected_idea or "不可用"
            selected = _clip(raw_selected, min(_IDEA_LIMIT, max(0, budget)))
            analysis = _clip(raw_analysis, max(0, budget - len(selected)))
            context = (
                f"A 约束摘要：\n{analysis}\n\nSELECTED_BRANCH: {branch}\n"
                f"选中思路：\n{selected}\n\nD handoff：\n{handoff}"
            )
        if len(context) > _FINISH_CONTEXT_LIMIT:
            state.diagnostics["finish_context_clipped"] = True
        context = _clip(context, _FINISH_CONTEXT_LIMIT)
        return f"原题：\n{problem}\n\n{context}"

    @staticmethod
    def _available_branch(state: _SolveState) -> str:
        # D 失败且两支都可用时，固定选择标准路径 B，保证降级可复现。
        if state.idea_packet_b:
            return "B"
        if state.idea_packet_c:
            return "C"
        return ""

    def _selected_branch(self, response: str, has_b: bool, has_c: bool) -> str:
        if self.options.multiline_handoff_v2:
            selected = _marker_value_strict(response, "SELECTED_BRANCH").upper()
        else:
            selected = _marker_value(response, "SELECTED_BRANCH").upper()
        if selected not in {"B", "C"}:
            return ""
        # A syntactically valid choice is still a protocol failure when that
        # branch is unavailable. Never relabel D's work as the other branch.
        if selected == "B" and not has_b:
            return ""
        if selected == "C" and not has_c:
            return ""
        return selected

    @staticmethod
    def _handoff(response: str, state: _SolveState) -> str:
        branch = state.selected_branch or "UNKNOWN"
        # Only parse the D handoff prefix.  A model may echo an idea packet
        # later in its response; idea markers are not D handoff evidence.
        safe_response = _strip_idea_packet_text(response)
        substantive = {
            field: _marker_value(safe_response, field)
            for field in _HANDOFF_FIELDS[1:]
        }
        parts = [f"SELECTED_BRANCH: {branch}"]
        parts.extend(
            f"{field}: {value}" for field, value in substantive.items() if value
        )
        if any(not value for value in substantive.values()):
            # 缺字段只标记不完整；E 不接收 D 的任意自由文本，避免未选分支泄露。
            parts.append("HANDOFF_INCOMPLETE: true")
        joined = "\n".join(parts)
        if len(joined) > _HANDOFF_LIMIT:
            state.diagnostics["handoff_clipped"] = True
        return _clip(joined, _HANDOFF_LIMIT)

    @staticmethod
    def _incomplete_handoff(branch: str) -> str:
        return _clip(
            f"SELECTED_BRANCH: {branch or 'UNKNOWN'}\nHANDOFF_INCOMPLETE: true",
            _HANDOFF_LIMIT,
        )

    @staticmethod
    def _resolve_handoff_blocks(response_d: str) -> dict[str, dict[str, Any]]:
        """Resolve every handoff field to a deduplicated value plus a state.

        States (fixed vocabulary, one per field): ``absent`` (no occurrence),
        ``unknown`` (occurred but every occurrence was a filtered placeholder,
        e.g. an honest CANDIDATE_D: UNKNOWN), ``conflict`` (>=2 distinct
        values), ``unclosed`` (single value with a program-detectably
        truncated math tail), ``content`` (single closed value).  Repeated
        identical values dedupe; placeholder occurrences carry no candidate
        semantics (so ``UNKNOWN → 42`` is an update, not a conflict).
        """
        blocks = _parse_handoff_blocks(response_d)
        resolved: dict[str, dict[str, Any]] = {}
        for field in _HANDOFF_VALUE_FIELDS:
            entries = blocks.get(field, [])
            if field == "CANDIDATE_D":
                real = [v for v in entries if not _is_placeholder_v2(v)]
            else:
                real = [v for v in entries if not _is_placeholder(v)]
            distinct = list(dict.fromkeys(real))
            if not entries:
                state, value = "absent", ""
            elif not distinct:
                state, value = "unknown", ""
            elif len(distinct) >= 2:
                state, value = "conflict", ""
            elif _has_unclosed_math(distinct[0]):
                state, value = "unclosed", distinct[0]
            else:
                state, value = "content", distinct[0]
            resolved[field] = {"state": state, "value": value}
        return resolved

    def _handoff_diagnostics(self, response_d: str) -> dict[str, Any]:
        """Bounded P0 summary: per-field states plus the rollup counts.

        "Fields present", "usable derivation" and "explicit candidate result"
        are counted separately: management fields being present does not mean
        E received real mathematical progress.  Values are field names,
        enums, booleans only — never model text.
        """
        resolved = self._resolve_handoff_blocks(_strip_idea_packet_text(response_d))
        states = {f: resolved[f]["state"] for f in _HANDOFF_VALUE_FIELDS}
        missing = [f for f in _HANDOFF_VALUE_FIELDS if states[f] == "absent"]
        _, final_d_distinct = _confirmed_marker_values(
            _marker_occurrences(response_d, ("FINAL_D",))
        )
        return {
            "handoff_missing_fields": missing,
            "handoff_unknown_fields": [
                f for f in _HANDOFF_VALUE_FIELDS if states[f] == "unknown"
            ],
            "handoff_conflict_fields": [
                f for f in _HANDOFF_VALUE_FIELDS if states[f] == "conflict"
            ],
            "handoff_unclosed_fields": [
                f for f in _HANDOFF_VALUE_FIELDS if states[f] == "unclosed"
            ],
            "handoff_field_states": states,
            "handoff_all_fields_present": not missing,
            "handoff_has_derived_content": states["DERIVED"] == "content",
            "handoff_has_candidate_result": (
                states["CANDIDATE_D"] == "content" or len(final_d_distinct) == 1
            ),
        }

    def _handoff_v2(self, response_d: str, state: _SolveState) -> tuple[str, dict[str, Any]]:
        """Marker-bounded multi-line handoff with whole-field/whole-item clipping.

        Clipping only ever drops complete fields or complete derivation items
        — including model-side truncated tails the program can detect — and
        every loss stays visible to E through the bounded trailer markers.
        """
        resolved = self._resolve_handoff_blocks(_strip_idea_packet_text(response_d))
        conflicts = [f for f in _HANDOFF_VALUE_FIELDS if resolved[f]["state"] == "conflict"]
        conflict_set = set(conflicts)
        missing = [f for f in _HANDOFF_VALUE_FIELDS if resolved[f]["state"] == "absent"]
        unclosed_trimmed: list[str] = []
        header = f"SELECTED_BRANCH: {state.selected_branch or 'UNKNOWN'}"
        reserve = (
            _FINISH_HANDOFF_RESERVE_V2_SHARE
            if self.options.finish_handoff_share
            else _FINISH_HANDOFF_RESERVE_V2
        )
        budget = reserve - len(header) - 1 - _HANDOFF_TRAILER_HEADROOM
        placed: dict[str, list[str]] = {}
        dropped: list[str] = []
        partial: list[str] = []
        used = 0

        def fits(extra: int) -> bool:
            return used + extra <= budget

        for field in _HANDOFF_KEEP_PRIORITY:
            if field in conflict_set:
                line = f"{field}_CONFLICT: true"
                if fits(len(line) + 1):
                    placed[field] = [line]
                    used += len(line) + 1
                else:
                    dropped.append(field)
                continue
            value = resolved[field]["value"]
            if resolved[field]["state"] == "unclosed":
                trimmed = _trim_unclosed_tail(value)
                if trimmed != value.strip():
                    unclosed_trimmed.append(field)
                value = trimmed
                if not value:
                    continue
            if not value:
                continue
            lines = value.split("\n")
            rendered = [f"{field}: {lines[0]}"] + lines[1:]
            whole = sum(len(line) + 1 for line in rendered)
            if fits(whole):
                placed[field] = rendered
                used += whole
                continue
            kept_lines: list[str] = []
            for line in rendered:
                cost = len(line) + 1
                if not fits(cost):
                    break
                kept_lines.append(line)
                used += cost
            if kept_lines:
                placed[field] = kept_lines
                partial.append(field)
            else:
                dropped.append(field)

        parts = [header]
        display_order = (
            _HANDOFF_DISPLAY_ORDER_OPEN_FIRST
            if self.options.handoff_open_first_e
            else _HANDOFF_DISPLAY_ORDER
        )
        for field in display_order:
            parts.extend(placed.get(field, []))
        incomplete = bool(missing or dropped or partial or unclosed_trimmed)
        if incomplete:
            parts.append("HANDOFF_INCOMPLETE: true")
        if conflicts:
            parts.append("HANDOFF_CONFLICT: " + ",".join(conflicts))
        if dropped:
            parts.append("HANDOFF_DROPPED: " + ",".join(dropped))
        if partial:
            parts.append("HANDOFF_PARTIAL: " + ",".join(partial))
        if unclosed_trimmed:
            parts.append("HANDOFF_UNCLOSED: " + ",".join(unclosed_trimmed))
        text = "\n".join(parts)
        meta = {
            "missing": missing,
            "conflicts": conflicts,
            "dropped": dropped,
            "partial": partial,
            "unclosed": unclosed_trimmed,
            "clipped": bool(dropped or partial or unclosed_trimmed),
        }
        return text, meta

    def _mark_protocol_failure(
        self,
        trace: list[dict[str, Any]],
        state: _SolveState,
        stage: str,
        selected_branch: str,
        max_tokens: int = 8192,
    ) -> None:
        for event in reversed(trace):
            if event.get("stage") == stage:
                event["status"] = "protocol_failed"
                event["error_category"] = "invalid_response"
                event["packet_present"] = False
                event["selected_branch"] = selected_branch or "UNKNOWN"
                return
        self._event(
            trace,
            state,
            stage,
            "protocol_failed",
            max_tokens,
            error_category="invalid_response",
            packet_present=False,
            selected_branch=selected_branch or "UNKNOWN",
        )

    def _call(
        self,
        state: _SolveState,
        trace: list[dict[str, Any]],
        stage: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str | None:
        if state.logical_calls >= 5:
            return None
        if self._deadline(state) == "hard":
            self._event(trace, state, stage, "skipped", max_tokens, error_category="hard_deadline")
            return None
        state.logical_calls += 1
        try:
            response = self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # the public client contract permits arbitrary exceptions
            category = _error_category(exc)
            state.sanitized_errors.append(category)
            state.stage_status[stage] = "failed"
            self._event(trace, state, stage, "failed", max_tokens, error_category=category)
            return None
        if not isinstance(response, str) or not response.strip():
            state.sanitized_errors.append("invalid_response")
            state.stage_status[stage] = "failed"
            self._event(trace, state, stage, "failed", max_tokens, error_category="invalid_response")
            return None
        state.stage_status[stage] = "ok"
        self._event(trace, state, stage, "ok", max_tokens, packet_present=True)
        return response.strip()

    def _stage_allowed(
        self, state: _SolveState, trace: list[dict[str, Any]], stage: str, max_tokens: int
    ) -> bool:
        deadline = self._deadline(state)
        if deadline:
            self._event(
                trace,
                state,
                stage,
                "skipped",
                max_tokens,
                error_category=f"{deadline}_deadline",
            )
            return False
        return True

    def _deadline(self, state: _SolveState) -> str:
        elapsed = self.clock() - state.started_at
        if elapsed >= HARD_DEADLINE_SECONDS:
            return "hard"
        if elapsed >= SOFT_DEADLINE_SECONDS:
            return "soft"
        return ""

    def _event(
        self,
        trace: list[dict[str, Any]],
        state: _SolveState,
        stage: str,
        status: str,
        max_tokens: int,
        **extra: Any,
    ) -> None:
        event: dict[str, Any] = {
            "method": METHOD_ID,
            "stage": stage,
            "status": status,
            "model_calls": state.logical_calls,
            "max_tokens": max_tokens,
            "elapsed_bucket": self._elapsed_bucket(state),
        }
        event.update({key: value for key, value in extra.items() if key in {
            "packet_present",
            "selected_branch",
            "candidate_present",
            "final_present",
            "fallback_source",
            "error_category",
            "ideas_not_diverse",
            "handoff_missing_fields",
            "handoff_unknown_fields",
            "handoff_conflict_fields",
            "handoff_unclosed_fields",
            "handoff_field_states",
            "handoff_all_fields_present",
            "handoff_has_derived_content",
            "handoff_has_candidate_result",
            "handoff_clipped",
            "finish_context_clipped",
            "d_candidate_visible_to_e",
            "e_final_equals_d_candidate",
            "token_usage",
            "finish_reason",
        }})
        trace.append(event)

    def _elapsed_bucket(self, state: _SolveState) -> str:
        elapsed = self.clock() - state.started_at
        if elapsed >= HARD_DEADLINE_SECONDS:
            return "hard"
        if elapsed >= SOFT_DEADLINE_SECONDS:
            return "soft"
        return "normal"

    @staticmethod
    def _select_l0_answer(response: str | None) -> tuple[str, str]:
        final = _marker_value(response, "FINAL") or _marker_value(response, "最终答案")
        if final and not _is_placeholder(final):
            return final, "finish_final"
        boxed = _boxed_value(response)
        if boxed:
            return boxed, "boxed"
        math_line = _independent_math_line(response)
        if math_line:
            return math_line, "math_line"
        return "UNKNOWN", "unknown"

    @staticmethod
    def _select_answer(response_e: str | None, response_d: str | None) -> tuple[str, str]:
        choices = (
            ("finish_final", _marker_value(response_e, "FINAL") or _marker_value(response_e, "最终答案")),
            ("finish_candidate", _marker_value(response_e, "CANDIDATE_E")),
            ("deep_final", _marker_value(response_d, "FINAL_D")),
            ("deep_candidate", _marker_value(response_d, "CANDIDATE_D")),
        )
        for source, value in choices:
            if value and not _is_placeholder(value):
                return value, source
        boxed = _boxed_value(response_d)
        if boxed:
            return boxed, "boxed"
        math_line = _independent_math_line(response_e)
        if math_line:
            return math_line, "math_line"
        math_line = _independent_math_line(response_d)
        if math_line:
            return math_line, "math_line"
        return "UNKNOWN", "unknown"

    def _select_answer_v2(
        self, response_e: str | None, response_d: str | None, state: _SolveState
    ) -> tuple[str, str]:
        """P2a confirmed-answer selection (fail-closed).

        - A valid, conflict-free E final wins.
        - An explicit FINAL: UNKNOWN is an abstention: the final answer stays
          UNKNOWN and no earlier candidate is revived.
        - Distinct repeated finals are a conflict: UNKNOWN, never first/last.
        - When E has no valid final, only an explicitly completed D result
          (FINAL_D) may be adopted, and only when D itself completed its
          protocol — a protocol-failed D's raw text never bypasses the
          source-validity checks.  Unconfirmed CANDIDATE values, boxed
          intermediate quantities and stray math lines are not answers.
        """
        abstained, e_distinct = _confirmed_marker_values(
            _marker_occurrences(response_e, ("FINAL", "最终答案"))
        )
        if abstained:
            return "UNKNOWN", "finish_unknown"
        if len(e_distinct) >= 2:
            return "UNKNOWN", "final_conflict"
        if len(e_distinct) == 1:
            return e_distinct[0], "finish_final"
        # E 终答缺失（无 FINAL 或终答无效）≠ 明确弃答；仅显式完成结果可回退。
        if state.stage_status.get("deepen") == "ok" and response_d:
            d_abstained, d_distinct = _confirmed_marker_values(
                _marker_occurrences(response_d, ("FINAL_D",))
            )
            if d_abstained:
                return "UNKNOWN", "unknown"
            if len(d_distinct) >= 2:
                return "UNKNOWN", "deep_final_conflict"
            if len(d_distinct) == 1:
                return d_distinct[0], "deep_final"
        return "UNKNOWN", "unknown"

    def _result(
        self,
        state: _SolveState,
        trace: list[dict[str, Any]],
        final_response: str,
        fallback_source: str,
    ) -> RelayResult:
        final = final_response.strip() if isinstance(final_response, str) else "UNKNOWN"
        # 只在终答本身无效时改写来源；显式 UNKNOWN 的原因来源（弃答/冲突）必须保留。
        if final != "UNKNOWN" and (not final or _is_placeholder(final)):
            final, fallback_source = "UNKNOWN", "unknown"
        extras: dict[str, Any] = {}
        if self.options.diagnostics_v2:
            # P0 有界诊断摘要：只含字段名/枚举/布尔/unavailable 标记，不含模型原文。
            # 公开 client 契约不暴露 token/finish_reason，无法获得时显式标记。
            extras = {
                "handoff_missing_fields": list(state.diagnostics.get("handoff_missing_fields", [])),
                "handoff_unknown_fields": list(state.diagnostics.get("handoff_unknown_fields", [])),
                "handoff_conflict_fields": list(state.diagnostics.get("handoff_conflict_fields", [])),
                "handoff_unclosed_fields": list(state.diagnostics.get("handoff_unclosed_fields", [])),
                "handoff_field_states": dict(state.diagnostics.get("handoff_field_states", {})),
                "handoff_all_fields_present": bool(state.diagnostics.get("handoff_all_fields_present", False)),
                "handoff_has_derived_content": bool(state.diagnostics.get("handoff_has_derived_content", False)),
                "handoff_has_candidate_result": bool(state.diagnostics.get("handoff_has_candidate_result", False)),
                "handoff_clipped": bool(state.diagnostics.get("handoff_clipped", False)),
                "finish_context_clipped": bool(state.diagnostics.get("finish_context_clipped", False)),
                "candidate_present": bool(state.diagnostics.get("candidate_present", False)),
                "d_candidate_visible_to_e": bool(state.diagnostics.get("d_candidate_visible_to_e", False)),
                "e_final_equals_d_candidate": bool(state.diagnostics.get("e_final_equals_d_candidate", False)),
                "token_usage": "unavailable",
                "finish_reason": "unavailable",
            }
        self._event(
            trace,
            state,
            "finalize",
            "ok" if final != "UNKNOWN" else "unknown",
            0,
            final_present=final != "UNKNOWN",
            fallback_source=fallback_source,
            selected_branch=state.selected_branch or "UNKNOWN",
            **extras,
        )
        return RelayResult(final_response=final, extracted_answer=final if final != "UNKNOWN" else "", trace=trace)


__all__ = [
    "ForkSelectDeepenFinishRelay",
    "RelayResult",
    "RelayOptions",
    "METHOD_ID",
    "STAGE_TOKEN_SEQUENCE",
    "STAGE_TOKEN_SEQUENCE_DE_SWAP",
    "L0_TOKEN_SEQUENCE",
    "SOFT_DEADLINE_SECONDS",
    "HARD_DEADLINE_SECONDS",
    "FINISH_PROMPT",
    "FINISH_PROMPT_V2",
    "FINISH_PROMPT_COMPACT_V2",
    "DEEPEN_PROMPT",
    "DEEPEN_PROMPT_V2",
    "DEEPEN_PROMPT_MFD",
    "match_simple_arithmetic_expression",
]
