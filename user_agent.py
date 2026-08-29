"""Budgeted mathematical reasoning agent with deterministic answer handling."""
from __future__ import annotations
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

# ── Task-type constants (universal, problem-text based) ────────────────────
TASK_TYPE_CHOICE = "choice"
TASK_TYPE_FILL_BLANK = "fill_blank"
TASK_TYPE_CALCULATION = "calculation"
TASK_TYPE_DERIVATION = "derivation"
TASK_TYPE_PROOF = "proof"
TASK_TYPE_EXPLANATION = "explanation"

# P1.1 采纳：三轮 12/15/12 均 > 旧基线 ~11/23；默认使用答案优先短提示。
POLICY_PROMPT = """你是严谨的数学推理智能体。解决用户给出的数学问题。不要复述题意、不要输出 Thinking Process、计划、标题、格式说明或无关说明。只输出一行“最终答案：”后接数学答案。"""
ANSWER_FIRST_POLICY_PROMPT = POLICY_PROMPT
ANSWER_ONLY_POLICY_PROMPT = """你是数学求解器。直接解题，不要输出 Thinking Process、计划、标题或格式说明。只输出一行“最终答案：”后接数学答案。"""
VERIFIER_PROMPT = """你是数学解答审核员。独立检查候选答案是否能正确解决题目。
若发现错误，指出第一个可证实的错误位置；不要复述完整解答。
最后一行必须且只能为：VERDICT: A、VERDICT: B 或 VERDICT: UNCERTAIN。
A 表示未发现可证实错误，B 表示发现可证实错误，UNCERTAIN 表示无法判断。"""
SUBSTITUTION_CHECK_PROMPT = """你是数学约束验证器。针对题目和给定候选答案，生成一个极短的 Python 检验程序。
程序运行时已经提供变量 candidate，它表示候选答案；不要给 candidate 赋值，也不要把候选答案写进程序字面量。
程序只能使用白名单数学表达式，并且必须通过 print(...) 输出一个布尔值：约束成立输出 True，否则输出 False。
只输出程序本身，可使用代码围栏但不要添加解释、导入、文件或网络操作。"""

# ── Task-aware prompts ─────────────────────────────────────────────────────
# Each prompt guides the model toward the expected output format for a specific
# question type.  All are universal (never refer to sample idx or answer).

CHOICE_PROMPT = """你是数学求解器。这是一道选择题。选出唯一正确的一项。不要输出分析、理由或无关说明。只输出一行“最终答案：X”，其中 X 是选项字母。"""

FILL_BLANK_PROMPT = """你是数学求解器。这是一道填空题。直接计算并填入结果。不要输出推导或无关说明。只输出一行“最终答案：”后接填入值。"""

CALCULATION_PROMPT = POLICY_PROMPT  # 复用已验证的 answer-first 提示词

# Experimental prompt for the numerical A/B arm.  It is opt-in so the
# promoted F+4096 default remains unchanged while the prompt effect is measured
# independently from parsing and token-budget changes.
NUMERIC_ANSWER_FIRST_PROMPT = """你是数学求解器。只解决题目本身，不输出标题或格式说明。
第一行必须且只能写：最终答案：<答案>
从第二行起可以给出必要的简短推理或校验；不要在第一行之前输出任何内容，也不要重复最终答案。"""

DERIVATION_PROMPT = """你是严谨的数学推理智能体。这是一道推导题。请直接输出面向用户的正式答案，不要输出 Thinking Process、内部计划或格式说明。严格按照以下结构输出：

最终答案：<只写最终表达式、数值或结论>

推导：
<完整的关键推导链、中间步骤和定理引用>"""

PROOF_PROMPT = """你是严谨的数学推理智能体。这是一道证明题。请直接输出面向用户的正式答案，不要输出 Thinking Process、内部计划或格式说明。严格按照以下结构输出：

最终答案：<命题成立/不成立及必要的核心结论；若题目要求求值则写求得的值>

证明：
<完整而紧凑的证明，含命题陈述、关键推理步骤和结论>"""

EXPLANATION_PROMPT = """你是严谨的数学推理智能体。这是一道解释/说明题。请直接输出面向用户的正式答案，不要输出 Thinking Process、内部计划或格式说明。严格按照以下结构输出：

最终答案：<一句能够独立判定的核心回答>

解释：
<清晰、紧凑的数学解释，含关键定义和逻辑推理>"""

# ── P2: heterogeneous reasoner prompts ──────────────────────────────────────
# DirectReasoner uses standard forward derivation (definitions → theorems → answer).
# AlternativeReasoner uses complementary strategies (contradiction, construction,
# boundary checks, numerical verification) to approach from a different angle.
# When both agree, confidence is high; conflicts are resolved by the audit step.

DIRECT_REASONER_PROMPT = """你是数学推理智能体，使用标准正向推导方法。
步骤：
1. 明确关键定义和已知条件。
2. 引用或陈述相关定理/公式。
3. 从条件出发，逐步严格推演到结论，每步给出依据。
4. 检查定义域、边界条件和遗漏情形。
最后一行必须使用"最终答案："明确写出答案。"""

ALTERNATIVE_REASONER_PROMPT = """你是数学推理智能体，使用互补策略从另一角度验证或求解。
选择至少一种方法：
- 反证法：假设结论不成立，推导矛盾。
- 构造法：构造满足条件的实例或反例。
- 边界/特例检查：验证极端值、退化情形。
- 数值/代数验证：代入数值交叉检查。
不要重复标准正向推导的全部步骤，聚焦于不同的推理路径或验证。
最后一行必须使用"最终答案："明确写出答案。"""

# ── P3: step verification and revision prompts ────────────────────────────
# InternLM models embed a verbose "Thinking Process" before every response,
# which consumes tokens and makes structured lemma extraction unreliable.
# Strategy: single-call step-by-step verification instead of lemma extraction.

STEP_VERIFY_PROMPT = """你是数学验证员。逐步检查以下解答：
对每一步输出：OK 或 ERROR:步骤:原因。
所有步骤检查完毕后，最后一行输出：
ALL_OK:COMPLETE   — 全部正确且解答完整
ALL_OK:GAPS:缺失1;缺失2   — 步骤正确但不完整
ERRORS   — 发现有步骤错误（此时前面已有 ERROR 行指出）
不要输出 Thinking Process。"""

# ponytail: merged step+full verify into single call; split again if two-call accuracy measurably better.
SOLUTION_VERIFY_PROMPT = STEP_VERIFY_PROMPT  # backward-compat alias

STEP_REVISE_PROMPT = """你是数学修正员。原解答在指定步骤有错误。请只修正受影响的推导部分，保持正确步骤不变。
输入包含：原题、原解答、错误定位和原因。
输出修正后的完整解答。最后一行必须使用"最终答案："明确写出答案。"""

# ── Verification-gated retry instructions ────────────────────────────────
# These are universal counter-evidence prompts for the single recovery slot.
GATED_TRUNCATION_INSTRUCTION = (
    "检查提示：你上一次的回答在写出完整结论前被截断。"
    "请改用最短完备推导重新作答：第一行立即写“最终答案：<答案>”，"
    "随后每一步只保留一行关键中间结果，禁止长篇展开或重复计算。"
)
GATED_UNSTRUCTURED_INSTRUCTION = (
    "检查提示：你上一次的回答缺少规定的“最终答案：”结论行。"
    "请严格按格式重新作答：先写一行“最终答案：<答案>”，再给出紧凑的解答主体。"
)
GATED_PLACEHOLDER_INSTRUCTION = (
    "检查提示：你上一次的回答只给出了占位符而不是真实答案。"
    "请直接完成计算，并写出一行“最终答案：<具体的数值、表达式或选项字母>”。"
)
GATED_CONFLICT_INSTRUCTION = (
    "检查提示：你上一次的回答包含两个互相矛盾的最终答案（“{first}”与“{second}”），两者不可能同时成立。"
    "请重新核对推导，只保留一个经过验证的最终答案，写在一行“最终答案：<答案>”。"
)
GATED_SANITY_INSTRUCTION = (
    "检查提示：你给出的答案 {answer} 不满足条件：{constraint}。"
    "请对照该约束重新核查推导，修正错误后给出一行“最终答案：<满足约束的答案>”。"
)


# Map task type → generation prompt.
TASK_PROMPTS: dict[str, str] = {
    TASK_TYPE_CHOICE: CHOICE_PROMPT,
    TASK_TYPE_FILL_BLANK: FILL_BLANK_PROMPT,
    TASK_TYPE_CALCULATION: CALCULATION_PROMPT,
    TASK_TYPE_DERIVATION: DERIVATION_PROMPT,
    TASK_TYPE_PROOF: PROOF_PROMPT,
    TASK_TYPE_EXPLANATION: EXPLANATION_PROMPT,
}

# Proof / explanation types that should never be rejected just because
# ``extract_final_answer`` found no "最终答案：" marker.
_NON_NUMERIC_TASK_TYPES: frozenset[str] = frozenset({TASK_TYPE_PROOF, TASK_TYPE_EXPLANATION, TASK_TYPE_DERIVATION})


def classify_problem_type(problem: str) -> str:
    """Return the dominant math-problem type based on problem-text signals.

    Classification is purely textual — no metadata, no sample idx, no subject.
    Order matters: more-specific patterns are checked first.
    """
    if not isinstance(problem, str) or not problem.strip():
        return TASK_TYPE_CALCULATION

    text = problem.strip()

    # ── Choice (format constraint, must precede content-type checks) ──
    if (
        re.search(r"(?:^|\n)\s*[A-D]\s*[.、．。]", text)
        or re.search(r"下列.*?(?:正确|错误|不正确).*?[是有的]", text)
        or re.search(r"选择|选项|单选|多选|[Cc]hoose\b|[Ss]elect\b", text)
    ):
        return TASK_TYPE_CHOICE

    # ── Proof ──
    if re.search(r"证明|求证|[Pp]rove\b|[Ss]how\s+that\b", text):
        return TASK_TYPE_PROOF

    # ── Explanation ──
    if re.search(r"解释|说明理由|阐述|[Ee]xplain\b|[Dd]escribe\b|为什么", text):
        return TASK_TYPE_EXPLANATION

    # ── Derivation ──
    if re.search(r"推导|导出|推演|[Dd]erive\b|[Dd]educe\b", text):
        return TASK_TYPE_DERIVATION

    # ── Fill-in-the-blank ──
    if re.search(r"_{3,}|（\s*）|填空|填入|[Ff]ill\s+in\b", text):
        return TASK_TYPE_FILL_BLANK

    # ── Default: calculation ──
    return TASK_TYPE_CALCULATION

@dataclass
class AgentConfig:
    # ── P0 stop-bleeding defaults ─────────────────────────────────────────
    # Official runs showed 1024-token truncation fanning one question into ~7
    # model calls (~98.7% finish_reason=length) with near-zero accuracy.
    # Single main call + at most one conditional retry; no per-candidate audit
    # and no verify-only P3.
    #
    # Token cap: 4096 (promoted from 3072 on 2026-08-15).  The official hidden
    # set run of the 3072 config (commit 174bbbb) scored 4.46% with a 91.7%
    # truncation rate (155/169 requests hit finish_reason=length), proving 3072
    # is still far too short on the hidden set even though it passed Gate 2 on
    # the local 112-question set (81.2% / 80.4%, length 10-18%).  Paired
    # single-variable 3072-vs-4096 A/B on the complex freeze set showed 4096
    # cuts length (35-42% -> 12-23%) and thinking leakage (33% -> 8-21%) with
    # no reproducible accuracy regression and at most +20.4% per-question token
    # cost.  The official 91.7% truncation is stronger evidence than the local
    # 5% pollution gate, so 4096 is adopted as the default.
    policy_sample_times: int = 1
    verifier_voting_times: int = 0
    max_model_calls: int = 2
    policy_temperature: float = 0.6
    policy_prompt: str = POLICY_PROMPT
    verifier_temperature: float = 0.0
    max_tokens: int = 4096
    l0_max_tokens: int = 4096
    verifier_max_tokens: int = 256
    enable_sympy_evidence: bool = False
    enable_substitution_check: bool = False
    substitution_max_tokens: int = 512
    enable_dynamic_budget: bool = False
    enable_l0_extended_tokens: bool = True
    enable_l2_routing: bool = False
    enable_local_repair: bool = False
    enable_uncertain_repair: bool = False
    max_repairs: int = 1
    l2_max_model_calls: int = 8
    # ── P0: task-aware routing ──
    enable_task_aware_prompt: bool = True
    # ── P0: time convergence (per-question wall-clock) ──
    enable_time_convergence: bool = True
    solve_converge_timeout_seconds: float = 960.0   # ~16 min → stop new candidates
    solve_hard_timeout_seconds: float = 1080.0       # ~18 min → stop all calls
    # ── P2: heterogeneous reasoners ──
    enable_heterogeneous_reasoners: bool = False
    # ── P3: step verification + targeted revision ──
    enable_step_verification: bool = False
    enable_step_revision: bool = False
    # P3 needs extra call budget beyond generation + audit.  When P3 is
    # re-enabled later, this boost reserves room for verify + revise + re-verify.
    p3_call_boost: int = 3
    # Offline method-card RAG experiment. Disabled by default; the official
    # path must remain independent of local assets until an A/B gate passes.
    enable_method_rag: bool = False
    method_rag_top_k: int = 2
    method_rag_max_context_chars: int = 4000
    enable_deterministic_solver: bool = False
    # Experimental A/B switches.  All remain opt-in; the current F+4096 path
    # is the default baseline until a freeze-set gate promotes a candidate.
    enable_numeric_answer_first_prompt: bool = False
    enable_numeric_answer_only_prompt: bool = False
    enable_strict_numeric_salvage: bool = False
    enable_conditional_token_retry: bool = False
    conditional_retry_max_tokens: int = 6144
    enable_failure_retry_backoff: bool = False
    failure_retry_backoff_seconds: float = 1.0
    enable_explicit_answer_conflict_retry: bool = False
    # B1: deterministic verification gate for the single recovery call.
    enable_verification_gated_retry: bool = False
    # B2 remains an explicit, disabled experiment; B1 does not depend on it.
    enable_truncation_recovery_prompt: bool = False
    # Adaptive consistency voting: independent full resamples of the same
    # problem; consensus is decided by conservative equivalence groups with
    # early exit once the top group reaches vote_agree_threshold clear answers.
    # Default off. When enabled (non-L0) it replaces the single conditional
    # retry slot and still respects max_model_calls and per-question time.
    enable_adaptive_voting: bool = False
    vote_k_max: int = 3
    vote_agree_threshold: int = 2


# ── Submission profile ────────────────────────────────────────────────────
# The official runner constructs ``ReasoningAgent(client=official_client)``
# without a config, which resolves here.
#
# 2026-08-27 user-approved experimental canary: C0 answer-first adaptive k5
# with one AlternativeReasoner call inside the non-L0 vote budget; remaining
# samples use DirectReasoner. This bypasses the unfinished local A/B gate.
# Rollback anchor: 242c480 (C0 runtime, official Run #4 = 9/112).
SUBMISSION_CONFIG = AgentConfig(
    policy_sample_times=1,
    policy_temperature=0.6,
    verifier_voting_times=0,
    enable_dynamic_budget=False,
    enable_l0_extended_tokens=True,
    enable_task_aware_prompt=True,
    enable_time_convergence=True,
    enable_adaptive_voting=True,
    vote_k_max=5,
    vote_agree_threshold=3,
    enable_verification_gated_retry=False,
    enable_truncation_recovery_prompt=False,
    max_model_calls=5,
    max_tokens=4096,
    l0_max_tokens=4096,
    enable_heterogeneous_reasoners=True,
    # P3 refine chain (verify -> revise -> re-verify, fail-closed) on top
    # of the hetero baseline; boarding qualification: battle-night W2+W2b
    # double clean confirm (net +1 each, cost 1.26x, zero paired losses
    # accumulated). Single new variable vs 25f99b5 behavior.
    enable_step_verification=True,
    enable_step_revision=True,
    enable_method_rag=False,
    enable_deterministic_solver=False,
    enable_numeric_answer_first_prompt=True,
    enable_numeric_answer_only_prompt=False,
    enable_strict_numeric_salvage=False,
    enable_conditional_token_retry=False,
    enable_failure_retry_backoff=False,
    enable_explicit_answer_conflict_retry=False,
    enable_l2_routing=False,
    enable_local_repair=False,
    enable_uncertain_repair=False,
    enable_sympy_evidence=False,
)


_ANSWER_MARKER_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]\s*([^\n\r]+)", re.IGNORECASE)
_ANSWER_MARKER_LINE_STRICT_RE = re.compile(
    r"^\s*(?:最终答案|final\s+answer|答案)\s*[:：]\s*(.*?)\s*$",
    re.IGNORECASE,
)
_CHOICE_LINE_RE = re.compile(r"^(?:选项\s*)?([A-Da-d])(?:[.。)）]?)\s*$")
# A standalone answer line must be pure math (no CJK prose / sentence punctuation).
_MATH_ONLY_LINE_RE = re.compile(r"^[\sA-Za-z0-9+\-*/=<>≤≥.,(){}[\]^_'\\|±×÷]+$")
# Natural-language connectives that mark a truncated / prose fragment.
_CONNECTIVE_RE = re.compile(r"(因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)")
_STRICT_THINKING_RE = re.compile(
    r"\b(?:thinking(?:\s+process)?|analysis|reasoning|draft)\b|思考过程|思维链|内部推理",
    re.IGNORECASE,
)


def extract_final_answer(response: str) -> str:
    """Return a clean, explicit answer or "" (no arbitrary last-line fallback).

    Accepts only: a closed ``\\boxed{...}``, an explicit ``最终答案：`` /
    ``Final answer:`` / ``答案：`` marker with an answer-like value, or a
    standalone short answer line (option letter / number / fraction / equation /
    set).  A truncated natural-language tail line is never treated as an answer.
    """
    if not isinstance(response, str) or not response.strip():
        return ""
    boxed = _extract_boxed_answers(response)
    if boxed:
        return boxed[-1]
    markers = _ANSWER_MARKER_RE.findall(response)
    for marker in reversed(markers):
        answer = marker.strip()
        if answer and not is_placeholder_answer(answer) and _is_answer_like(answer):
            return answer
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    for line in reversed(lines):
        choice = _CHOICE_LINE_RE.match(line)
        if choice:
            return choice.group(1).upper()
        standalone = _is_standalone_answer_line(line)
        if standalone is not None:
            return standalone
    return ""


def extract_answer_first(response: str) -> str:
    """Prefer the first standalone answer marker used by the answer-first arm."""
    if not isinstance(response, str) or not response.strip():
        return ""
    for line in response.splitlines():
        match = _ANSWER_MARKER_LINE_STRICT_RE.match(line)
        if not match:
            continue
        answer = match.group(1).strip()
        if answer and not is_placeholder_answer(answer) and _is_answer_like(answer):
            return answer
    return extract_final_answer(response)


def extract_numeric_answer(response: str) -> str:
    """Extract a conservative answer for numeric/choice/fill-blank tasks.

    This salvage arm only accepts an independent answer-marker line, a closed
    ``\\boxed{...}``, a standalone option letter, or a short pure-math line.
    It deliberately does not accept an arbitrary last line or prose sentence.
    """
    if not isinstance(response, str) or not response.strip():
        return ""
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    for line in reversed(lines):
        marker = _ANSWER_MARKER_LINE_STRICT_RE.match(line)
        if not marker:
            continue
        answer = marker.group(1).strip()
        if r"\boxed{" in answer:
            boxed_answer = _extract_standalone_boxed_answer(answer)
            if boxed_answer and _is_strict_numeric_value(boxed_answer):
                return boxed_answer
            continue
        if answer and _is_strict_numeric_value(answer):
            return answer
    for line_index in range(len(lines) - 1, -1, -1):
        line = lines[line_index]
        answer = _extract_standalone_boxed_answer(line)
        if answer and _STRICT_THINKING_RE.search("\n".join(lines[:line_index])):
            continue
        if answer and _is_strict_numeric_value(answer):
            return answer
    last_line = lines[-1] if lines else ""
    choice = _CHOICE_LINE_RE.match(last_line)
    if choice:
        return choice.group(1).upper()
    if r"\boxed{" in last_line:
        return ""
    standalone = _is_standalone_answer_line(last_line)
    if standalone is not None:
        return standalone
    return ""


def _extract_standalone_boxed_answer(line: str) -> str:
    """Extract one boxed value only when the whole line is a boxed answer."""
    text = line.strip()
    answers = _extract_boxed_answers(text)
    if len(answers) != 1 or text.count(r"\boxed{") != 1:
        return ""
    start = text.find(r"\boxed{")
    end = text.rfind("}")
    prefix = text[:start].strip().strip("$*")
    suffix = text[end + 1:].strip().strip("$*")
    if prefix or suffix:
        return ""
    return answers[0].strip()


def _is_strict_numeric_value(answer: str) -> bool:
    """Accept only a choice token or an independent pure-math answer."""
    if not answer or is_placeholder_answer(answer):
        return False
    if _CHOICE_LINE_RE.fullmatch(answer.strip()):
        return True
    return _is_standalone_answer_line(answer) is not None


# ── 13.2 实验 C/D：非数值题型答案段抽取（answer-first 协议）──────────────────
# 答案前置后，非数值题型（derivation/proof/explanation）的响应以「最终答案：<结论>」
# 开头，正文在后。这里抽取首个「真正」的答案段，跳过 thinking 复述的占位符。
_ANSWER_MARKER_POS_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]", re.IGNORECASE)
# 段边界：下一个结构标题（中英文正文标题 + 答案标记）。
_ANSWER_SEGMENT_STOP_RE = re.compile(
    r"\n\s*(?:推导|证明|解释|Derivation|Proof|Explanation|最终答案|final\s+answer|答案)\s*[:：]",
    re.IGNORECASE,
)
# 正文标题（用于 final_response 重建时定位正文起点）。
_BODY_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:推导|证明|解释|Derivation|Proof|Explanation)\s*[:：]\s*",
    re.IGNORECASE,
)
_ANSWER_ECHO_RE = re.compile(
    r"only\s+write|complete\s+chain|followed\s+by|final\s+expression|只写|简洁|独立判定|最终表达式|核心回答",
    re.IGNORECASE,
)
# thinking 元文本（假标记常出现在这类句子里）。
_THINKING_CONTEXT_RE = re.compile(
    r"system\s+prompt|asks?\s+for|format\s+instruction|following\s+structure|meta-?analysis",
    re.IGNORECASE,
)


def extract_answer_segment(response: str) -> str:
    """Return the genuine answer segment from an answer-first response, or "".

    Extracts the first "最终答案：" segment that is a real structural answer
    block, not a thinking-process echo: it skips placeholder echoes ("<…>"),
    prompt boilerplate, markers quoted inside thinking text, and markers
    sitting in meta-instruction sentences ("the system prompt asks for…").
    The segment is returned verbatim — no global numeric normalization, so
    proofs, explanations, inequalities, sets and tuples keep their semantics.
    """
    if not isinstance(response, str) or not response.strip():
        return ""
    for m in _ANSWER_MARKER_POS_RE.finditer(response):
        seg = _take_answer_segment(response, m.end())
        if not seg or _is_answer_echo(seg):
            continue
        if _is_marker_in_thinking_quote(response, m.start()):
            continue
        return seg
    return ""


def _is_marker_in_thinking_quote(text: str, pos: int) -> bool:
    """True when a marker sits inside a thinking quote / meta sentence, not a
    standalone structural line."""
    # 只看标记所在行内、标记前的内容（不跨行，避免误伤下一行的真标记）。
    line_start = text.rfind("\n", 0, pos) + 1
    ctx = text[line_start:pos]
    # Unbalanced double quote (marker inside a quoted echo).
    if ctx.count('"') % 2 == 1:
        return True
    # Unbalanced Chinese quote pair.
    if ctx.count("“") != ctx.count("”") or ctx.count("‘") != ctx.count("’"):
        return True
    # Marker right after a Markdown list bullet ("- Final Answer: …").
    if re.fullmatch(r"[-*]\s*", ctx.strip()):
        return True
    # Meta-instruction sentence on the same line.
    if _THINKING_CONTEXT_RE.search(ctx):
        return True
    return False


def _take_answer_segment(text: str, start: int) -> str:
    """Slice the segment right after a marker, up to the next structure header
    (推导/证明/解释/最终答案, 中英文) or a blank line."""
    rest = text[start:]
    stop = _ANSWER_SEGMENT_STOP_RE.search(rest)
    blank = re.search(r"\n\s*\n", rest)
    end = len(rest)
    if stop:
        end = min(end, stop.start())
    if blank:
        end = min(end, blank.start())
    return rest[:end].strip()


def _is_answer_echo(seg: str) -> bool:
    """True when a marker segment is a placeholder/prompt echo, not a real answer."""
    s = seg.strip()
    if not s:
        return True
    if re.match(r"^<[^>]*>", s):
        return True  # "<只写…>" placeholder copied verbatim
    if _ANSWER_ECHO_RE.search(s):
        return True  # prompt boilerplate echoed inside thinking
    return False


_BODY_HEADER_NAME = {
    TASK_TYPE_DERIVATION: "推导",
    TASK_TYPE_PROOF: "证明",
    TASK_TYPE_EXPLANATION: "解释",
}


def reconstruct_final_response(response: str, problem_type: str) -> str:
    """Rebuild a clean answer-first final_response, or return the original.

    Drops the thinking / prompt echo that precedes the real answer block, keeps
    the answer conclusion and the body after the structure header, and re-emits
    them as「最终答案：<结论>」+「<正文标题>：<正文>」.  Never collapses a proof
    into a bare number.  When the structure cannot be reliably identified, the
    original response is returned unchanged (no aggressive trimming).
    """
    if not isinstance(response, str) or not response.strip():
        return response or ""
    answer_pos = -1
    answer_seg = ""
    for m in _ANSWER_MARKER_POS_RE.finditer(response):
        seg = _take_answer_segment(response, m.end())
        if seg and not _is_answer_echo(seg) and not _is_marker_in_thinking_quote(response, m.start()):
            answer_pos = m.start()
            answer_seg = seg
            break
    if answer_pos < 0 or not answer_seg:
        return response  # 无真实答案块 → 不裁剪
    body_m = _BODY_HEADER_RE.search(response, answer_pos + 1)
    if not body_m:
        return response  # 无正文标题 → 不裁剪
    body = response[body_m.end():].strip()
    if not body:
        return response  # 正文为空 → 不裁剪
    header = _BODY_HEADER_NAME.get(problem_type, "证明")
    return f"最终答案：{answer_seg}\n\n{header}：\n{body}"


# ── 13.2 实验 F：行级结构语法收紧（三状态解析 PREAMBLE→ANSWER→BODY）─────────
# 实验 E 证明 Prompt 压制语已到天花板。F 从解析层收紧：答案标记/正文标题必须
# 是独立结构行（行首，允许有限 Markdown 包装），嵌在 thinking 句子、约束说明、
# 引号、列表里的「最终答案」一律不识别；占位符（<…>/[Core Answer]/[Option
# Letter]/…）一律拒绝。不做全局数值规范化，不按 thinking/analysis 词删正文句。
_ANSWER_MARKER_LINE_RE = re.compile(
    r"^(?:\*\*|\*)?\s*(?:最终答案|final\s+answer|答案)\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?$",
    re.IGNORECASE,
)
_BODY_HEADER_LINE_RE = re.compile(
    r"^(?:\*\*|\*)?\s*(?:推导|证明|解释|Derivation|Proof|Explanation)"
    r"(?:\s*(?:块|Block))?\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?$",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"^(?:<[^>]*>|\[[^\]]*\]|\.{3,}|…{1,})$")


def _is_placeholder_segment(seg: str) -> bool:
    """F：占位符答案段（尖括号/方括号占位符、纯省略号、prompt 复述词）。"""
    s = seg.strip()
    if not s:
        return True
    if _PLACEHOLDER_RE.match(s):
        return True
    if _ANSWER_ECHO_RE.search(s):
        return True
    return False


def parse_structure_f(response: str, problem_type: str) -> dict:
    """F 三状态行解析，返回 {status, answer, body}。

    status: "structured"（答案+正文齐全）/ "no_answer_block"（无独立答案标记行）
            / "no_body"（有答案但无独立正文标题行）。
    仅接受「独立结构行」：答案标记/正文标题必须是行首（允许 **…** 粗体包装）。
    不识别特定题号、学科或具体答案。
    """
    if not isinstance(response, str) or not response.strip():
        return {"status": "no_answer_block", "answer": "", "body": ""}

    lines = response.splitlines()
    answer = ""
    answer_idx = -1
    for i, line in enumerate(lines):
        m = _ANSWER_MARKER_LINE_RE.match(line)
        if m and not _is_placeholder_segment(m.group(1)):
            answer = m.group(1).strip()
            answer_idx = i
            break
    if answer_idx < 0:
        return {"status": "no_answer_block", "answer": "", "body": ""}

    for j in range(answer_idx + 1, len(lines)):
        m = _BODY_HEADER_LINE_RE.match(lines[j])
        if m:
            head_rest = m.group(1).strip()
            tail = lines[j + 1:]
            body_lines = ([head_rest] if head_rest else []) + tail
            body = "\n".join(body_lines).strip()
            if body:
                return {"status": "structured", "answer": answer, "body": body}
            return {"status": "no_body", "answer": answer, "body": ""}
    return {"status": "no_body", "answer": answer, "body": ""}


def reconstruct_final_response_f(response: str, problem_type: str) -> str:
    """F 版 final_response 重建：仅在结构可靠时裁剪 thinking 前缀。

    无独立答案块或正文标题时返回原始响应（不具备重建条件，不激进裁剪）。
    """
    parsed = parse_structure_f(response, problem_type)
    if parsed["status"] != "structured":
        return response or ""
    header = _BODY_HEADER_NAME.get(problem_type, "证明")
    return f"最终答案：{parsed['answer']}\n\n{header}：\n{parsed['body']}"


def _is_answer_like(answer: str) -> bool:
    """A marker value must look like a short mathematical result, not trailing prose."""
    s = answer.strip().strip("。；;.,\"'“”’ ")
    if not s or len(s) > 60:
        return False
    if re.search(r"[，,、;；:：=<>]\s*$", s):
        return False  # ends mid-sentence → truncated
    if re.search(r"(?:因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)$", s):
        return False  # ends with a reasoning connective → truncated
    return True


def _is_standalone_answer_line(line: str) -> str | None:
    """Return a standalone short math answer line, or None if not answer-like."""
    s = line.strip()
    if not s or len(s) > 60 or is_placeholder_answer(s):
        return None
    if re.search(r"[，。；;、？！\n]", s):
        return None  # sentence punctuation → prose, not a bare answer
    if _CONNECTIVE_RE.search(s):
        return None  # contains a reasoning connective → prose
    if not _MATH_ONLY_LINE_RE.fullmatch(s):
        return None  # contains CJK / non-math characters
    if not (re.search(r"\d", s) or re.search(r"[=<>≤≥]", s)):
        return None  # no numeric or relational content
    return s


def _has_placeholder_answer(response: str) -> bool:
    """True if an answer marker in the response resolves to a placeholder token."""
    for marker in _ANSWER_MARKER_RE.findall(response or ""):
        if is_placeholder_answer(marker):
            return True
    for boxed in _extract_boxed_answers(response or ""):
        if is_placeholder_answer(boxed):
            return True
    return False


def is_placeholder_answer(answer: str) -> bool:
    """Reject output-format placeholders and prompt echoes that are not answers."""
    compact = answer.strip().lower().strip("。；;.,\"'”’ ")
    return compact in {
        "[answer]", "<answer>", "答案", "answer",
        "明确写出答案", "写出答案", "请写出答案", "最终答案",
    }


def _truncation_signals(response: str, answer: str) -> list[str]:
    """Proxy signals for finish_reason=length truncation (client returns str only).

    These are observability-only hints; the solver's only hard decision is
    ``no clear answer → at most one recovery call``.
    """
    signals: list[str] = []
    text = (response or "").rstrip()
    if not answer:
        signals.append("no_extractable_answer")
    if re.search(r"[，,、;；:：=<>]\s*$", text):
        signals.append("ends_with_connective_punctuation")
    if re.search(r"(?:因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)$", text):
        signals.append("ends_with_connective_word")
    if "\\boxed{" in text and text.rfind("}") < text.rfind("\\boxed{"):
        signals.append("unclosed_boxed")
    if text.endswith("\\"):
        signals.append("ends_with_backslash")
    return signals

def _extract_boxed_answers(text: str) -> list[str]:
    answers, cursor = [], 0
    while True:
        start = text.find(r"\boxed{", cursor)
        if start < 0: return answers
        depth, index = 1, start + len(r"\boxed{")
        content_start = index
        while index < len(text) and depth:
            depth += (text[index] == "{") - (text[index] == "}")
            index += 1
        if depth == 0 and (answer := text[content_start:index - 1].strip()): answers.append(answer)
        cursor = index if index > start else start + 1

def _format_rational(number: Fraction) -> str:
    return str(number.numerator) if number.denominator == 1 else f"{number.numerator}/{number.denominator}"

def _parse_rational_token(token: str) -> Fraction | None:
    compact = re.sub(r"\s+", "", token or "")
    if not compact:
        return None
    compact = compact.replace("\\left", "").replace("\\right", "").replace("−", "-")
    match = re.fullmatch(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}", compact)
    if match:
        compact = f"{match.group(1)}/{match.group(2)}"
    try:
        return Fraction(Decimal(compact))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        try:
            return Fraction(compact)
        except (ValueError, ZeroDivisionError):
            return None

def _canonicalize_multi_numeric_set(answer: str) -> str | None:
    """Unordered multi-root numeric sets only; ordered tuples/vectors stay untouched.

    Universal surface forms such as ``x=1, x=-1``, ``-1 or 1``, ``{1,-1}``.
    No problem-id or subject branching.
    """
    if not isinstance(answer, str) or not answer.strip():
        return None
    text = answer.strip().rstrip("。；;.")
    # Keep ordered coordinates / inequalities / single expressions alone.
    if re.fullmatch(r"\([^()]+(?:,[^()]+)+\)", re.sub(r"\s+", "", text)):
        return None
    if re.search(r"[<>≤≥]", text):
        return None
    # Drop optional set braces after rejecting ordered tuples.
    bare = text
    if bare.startswith("{") and bare.endswith("}"):
        bare = bare[1:-1].strip()
    # Require an explicit multi-value separator before treating as a set.
    if not re.search(r",|，|、|\bor\b|或", bare, flags=re.IGNORECASE):
        return None
    pieces = [p.strip() for p in re.split(r"(?:,|，|、|\bor\b|或)", bare, flags=re.IGNORECASE) if p.strip()]
    if len(pieces) < 2:
        return None
    values: list[Fraction] = []
    for piece in pieces:
        # Strip repeated ``var =`` / ``var:`` labels common in multi-root dumps.
        piece = re.sub(r"^(?:[A-Za-z\u4e00-\u9fff]+)\s*[=:：]\s*", "", piece.strip())
        number = _parse_rational_token(piece)
        if number is None:
            return None
        values.append(number)
    # Unordered set: sort and dedupe exact rationals.
    ordered = sorted(set(values))
    return ",".join(_format_rational(v) for v in ordered)

def normalize_answer(answer: str) -> str:
    if not isinstance(answer, str): return ""
    multi = _canonicalize_multi_numeric_set(answer)
    if multi is not None:
        return multi
    compact = re.sub(r"\s+", "", answer).rstrip("。；;.,\"")
    if not compact: return ""
    # Strip display-math / markdown wrappers so LaTeX answers normalize cleanly.
    compact = compact.replace("$", "").replace("\\(", "").replace("\\)", "").replace("**", "")
    compact = compact.replace("\\left", "").replace("\\right", "")
    match = re.fullmatch(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}", compact)
    if match: compact = f"{match.group(1)}/{match.group(2)}"
    compact = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", compact).replace("−", "-").replace("×", "*")
    number = _parse_rational_token(compact)
    if number is None:
        return compact
    return _format_rational(number)

def answer_equivalence(left: str, right: str) -> str:
    """Return only proven answer identity; ambiguous expressions stay separate."""
    normalized_left, normalized_right = normalize_answer(left), normalize_answer(right)
    if not normalized_left or not normalized_right:
        return "UNKNOWN"
    if normalized_left == normalized_right:
        return "EQUIVALENT"
    numeric = r"-?\d+(?:/\d+)?"
    multi_numeric = rf"{numeric}(?:,{numeric})+"
    if re.fullmatch(numeric, normalized_left) and re.fullmatch(numeric, normalized_right):
        return "NOT_EQUIVALENT"
    if re.fullmatch(multi_numeric, normalized_left) and re.fullmatch(multi_numeric, normalized_right):
        return "NOT_EQUIVALENT"
    if re.fullmatch(r"[A-D]", normalized_left, re.IGNORECASE) and re.fullmatch(r"[A-D]", normalized_right, re.IGNORECASE):
        return "NOT_EQUIVALENT"
    return "UNKNOWN"


def has_conflicting_explicit_answers(response: str) -> bool:
    """True only for two explicit, provably different terminal answers."""
    answers = [answer.strip() for answer in _ANSWER_MARKER_RE.findall(response) if answer.strip()]
    return any(
        answer_equivalence(left, right) == "NOT_EQUIVALENT"
        for index, left in enumerate(answers)
        for right in answers[index + 1:]
    )


# ── B1: deterministic verification-gated retry checks ────────────────────


def _conflicting_answer_pair(response: str) -> tuple[str, str] | None:
    """Return the first pair of explicit, provably different answers."""
    answers = [answer.strip() for answer in _ANSWER_MARKER_RE.findall(response) if answer.strip()]
    for index, left in enumerate(answers):
        for right in answers[index + 1:]:
            if answer_equivalence(left, right) == "NOT_EQUIVALENT":
                return left, right
    return None


def _single_scalar_value(answer: str) -> Fraction | None:
    """Return an exact scalar value, or None for structured/non-scalar text."""
    if not isinstance(answer, str):
        return None
    value = re.sub(r"\s+", "", answer)
    value = re.sub(r"^[A-Za-z\u4e00-\u9fff]{1,6}\s*[＝=:：]", "", value)
    percent = value.endswith(("%", "％"))
    if percent:
        value = value[:-1]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\d+/\d+)", value) and not re.fullmatch(r"\\[df]?rac\{[\d.]+\}\{[\d.]+\}", value):
        return None
    parsed = _parse_rational_token(value)
    if parsed is None:
        return None
    return parsed / 100 if percent else parsed


_GATE_INTERROGATIVE_RE = re.compile(r"求|多少|几|是否|哪")
_GATE_PROBABILITY_RE = re.compile(r"概率|可能性")
_GATE_EXPECTATION_RE = re.compile(r"期望|均值|方差|标准差")
_GATE_COUNT_RE = re.compile(r"个数|数量|有多少|共有多少|多少个|几种|多少种|种数|条数|人数|件数|方案")
_GATE_AVERAGE_RE = re.compile(r"平均|比例|百分")


def _interrogative_sentences(problem: str) -> list[str]:
    sentences = re.split(r"[。；;！!？?\n]+", problem or "")
    return [sentence for sentence in sentences if _GATE_INTERROGATIVE_RE.search(sentence)]


def _sanity_violation(problem: str, answer: str) -> str | None:
    """Return a violated probability/count constraint when it is explicit."""
    value = _single_scalar_value(answer)
    if value is None:
        return None
    for sentence in _interrogative_sentences(problem):
        if _GATE_PROBABILITY_RE.search(sentence) and not _GATE_EXPECTATION_RE.search(sentence):
            if not 0 <= value <= 1:
                return f"题面所求为概率，取值必须在区间 [0,1] 内（当前 {answer}）"
        if _GATE_COUNT_RE.search(sentence) and not _GATE_AVERAGE_RE.search(sentence):
            if value < 0 or value.denominator != 1:
                return f"题面所求为计数，必须是非负整数（当前 {answer}）"
    return None


_GATE_MODE_PRIORITY = ("truncation", "conflict", "sanity", "unstructured", "placeholder", "no_answer")


def run_answer_checks(
    problem: str,
    problem_type: str,
    response: str,
    answer: str,
    structured: bool | None,
) -> dict[str, Any]:
    """Run B1's six deterministic checks without making a model call."""
    numeric_type = problem_type not in _NON_NUMERIC_TASK_TYPES
    signals = _truncation_signals(response, answer)
    structural = [signal for signal in signals if signal != "no_extractable_answer"]
    if structural:
        return {"status": "fail", "mode": "truncation", "detail": {"signals": structural}}

    pair = _conflicting_answer_pair(response or "")
    if pair:
        return {"status": "fail", "mode": "conflict", "detail": {"first": pair[0], "second": pair[1]}}

    if not numeric_type:
        if structured is False:
            return {"status": "fail", "mode": "unstructured", "detail": None}
        return {"status": "pass", "mode": None, "detail": None}

    if not answer:
        mode = "placeholder" if _has_placeholder_answer(response or "") else "no_answer"
        return {"status": "fail", "mode": mode, "detail": {"signals": signals}}
    violation = _sanity_violation(problem, answer)
    if violation:
        return {"status": "fail", "mode": "sanity", "detail": {"constraint": violation, "answer": answer}}
    return {"status": "pass", "mode": None, "detail": None}

class ReasoningAgent:
    def __init__(self, client: Any, config: AgentConfig | None = None, sympy_adapter: Any | None = None, method_rag_retriever: Any | None = None, **_: Any) -> None:
        self.client = client
        # Official platform path (config=None) uses the promoted submission
        # profile; explicitly passed configs (local experiments) win as-is.
        self.config = config or SUBMISSION_CONFIG
        self.sympy_adapter = sympy_adapter
        self.method_rag_retriever = method_rag_retriever

    # ── Public API ──────────────────────────────────────────────────────

    def solve(self, problem: str, metadata: dict) -> dict:
        del metadata
        # P0: classify problem type (universal, text-based)
        problem_type = classify_problem_type(problem)

        trace, candidates = [], []
        generation_calls, level = self._generation_plan(problem)
        # P0: per-solve budget dict carries time for call isolation (no shared instance field).
        budget: dict[str, Any] = {"used": 0, "limit": self._model_call_limit(level),
                                   "diagnostic_reasons": [],
                                   "solve_start": time.monotonic() if self.config.enable_time_convergence else None}
        # P3: boost call budget so verification + revision have room beyond gen+audit.
        if self.config.enable_step_verification:
            budget["limit"] += self.config.p3_call_boost
        trace.append({"step":"route_budget","level":level,"generation_calls":generation_calls,"max_model_calls":budget["limit"],"problem_type":problem_type})
        if self.config.enable_method_rag:
            cards = self._retrieve_method_cards(problem)
            trace.append({"step":"method_rag","status":"used" if cards else "empty","top_k":self.config.method_rag_top_k,"card_ids":[str(card.get("id", "")) for card in cards]})
        if self.config.enable_deterministic_solver:
            deterministic_result = self._try_deterministic_solver(problem)
            trace.append({"step": "deterministic_solver", "status": deterministic_result.get("status", "unsupported"), "reason": deterministic_result.get("reason")})
            if deterministic_result.get("status") == "supported":
                answer = str(deterministic_result.get("answer", ""))
                trace.append({"step": "finalize", "status": "deterministic_selected", "model_calls": 0, "problem_type": problem_type})
                return {"final_response": answer, "extracted_answer": answer, "trace": trace}

        # ── Candidate generation ──
        # P2: heterogeneous reasoners — replace same-prompt sampling with complementary strategies.
        if self.config.enable_heterogeneous_reasoners:
            self._generate_heterogeneous(problem, generation_calls, level, candidates, trace, budget, problem_type)
        else:
            task_prompt = self._task_policy_prompt(problem_type)
            self._generate_candidates(problem, generation_calls, candidates, trace, budget, self._policy_max_tokens(level), task_prompt=task_prompt, problem_type=problem_type)

        # ── P0 stop-bleeding: conditional retry (≤1 recovery call) ──
        # A truncated / malformed main call yields no clear answer; allow exactly
        # one recovery generation.  Audit and P3 are off by default, so a bad
        # response can no longer fan out into many extra model calls.
        if self.config.enable_adaptive_voting and level != "L0":
            self._adaptive_vote(problem, level, candidates, trace, budget,
                                task_prompt=self._task_policy_prompt(problem_type),
                                problem_type=problem_type)
        else:
            self._conditional_recovery(problem, level, candidates, trace, budget,
                                       problem_type=problem_type)

        if self._should_escalate_l2(level, candidates):
            trace.append({"step":"route_budget","level":"L2","generation_calls":1,"max_model_calls":budget["limit"],"reason":"answer_conflict"})
            task_prompt = self._task_policy_prompt(problem_type)
            self._generate_candidates(problem, 1, candidates, trace, budget, self._policy_max_tokens("L2"), task_prompt=task_prompt, problem_type=problem_type)

        self._attach_substitution_evidence(problem, problem_type, candidates, trace, budget)
        self._attach_controlled_tool_evidence(problem, candidates, trace)
        for group_id, group in self._answer_groups(candidates).items():
            for _ in range(self.config.verifier_voting_times):
                calls_before = budget["used"]
                representative = group[0]
                response, error = self._request(VERIFIER_PROMPT, f"题目：\n{problem}\n\n候选解答：\n{representative['solution']}", self.config.verifier_temperature, self.config.verifier_max_tokens, budget)
                verdict = self._parse_verdict(response)
                for candidate in group:
                    candidate["model_calls_used"] += budget["used"] - calls_before if candidate is representative else 0
                    candidate["evidence"].append({"source":"llm_audit","verdict":verdict, "group_id":group_id})
                    candidate["verification_status"] = self._merge_verdict(candidate["verification_status"], verdict)
                trace.append({"step":"audit_answer_group","status":verdict if response else "skipped","group_id":group_id,"candidate_ids":[candidate["candidate_id"] for candidate in group],"found_error":verdict=="fail","reason":error})
        self._repair_refuted_candidate(problem, candidates, trace, budget)

        # ── Finalize ──
        if not candidates:
            if any(entry.get("status") == "rejected" for entry in trace if entry.get("step") == "generate_candidate"):
                self._record_diagnostic(budget, "all_candidates_rejected")
            self._record_diagnostic(budget, "fallback")
            trace.append({"step":"finalize","status":"fallback","reason":"no_valid_candidate","model_calls":budget["used"],"problem_type":problem_type})
            trace[-1]["diagnostic_reasons"] = list(budget["diagnostic_reasons"])
            return {"final_response":"未能生成有效数学答案。","trace":trace, "extracted_answer": ""}
        best = self._select_candidate(candidates)

        # ── P3: step verification + targeted revision ──
        if self.config.enable_step_verification and best.get("solution"):
            self._verify_and_revise(problem, best, candidates, trace, budget, problem_type)

        # P0: task-aware final_response formatting
        final_answer = self._format_task_final_response(best, problem_type)
        # Evaluator-facing compact answer (independent of final_response formatting)
        extracted_answer = best.get("normalized_answer") or best.get("answer", "")
        trace.append({"step":"finalize","status":"selected","candidate_id":best["candidate_id"],"selection_basis":best["selection_basis"],"model_calls":budget["used"],"problem_type":problem_type,"diagnostic_reasons":list(budget["diagnostic_reasons"])})
        return {"final_response":final_answer,"trace":trace, "extracted_answer": extracted_answer}

    # ── Candidate generation ─────────────────────────────────────────────

    def _generate_candidates(
        self, problem: str, generation_calls: int,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, int], max_tokens: int,
        task_prompt: str | None = None,
        problem_type: str = TASK_TYPE_CALCULATION,
        reasoner: str | None = None,  # P2: "direct" | "alternative" | None
        instruction: str | None = None,
    ) -> None:
        prompt = task_prompt or self.config.policy_prompt
        if self.config.enable_method_rag:
            prompt = prompt + self._method_context(problem)
        candidate_start = max((item["candidate_id"] for item in candidates), default=-1) + 1

        def _tr(status: str, cid: int, **extras: Any) -> dict[str, Any]:
            entry: dict[str, Any] = {"step": "generate_candidate", "status": status, "candidate_id": cid, **extras}
            if reasoner:
                entry["reasoner"] = reasoner
            return entry

        for candidate_id in range(generation_calls):
            if self._time_hard_exceeded(budget.get("solve_start")):
                trace.append(_tr("skipped", candidate_id + candidate_start, reason="solve_time_budget_exhausted"))
                continue
            if self._time_converge_exceeded(budget.get("solve_start")):
                trace.append(_tr("skipped", candidate_id + candidate_start, reason="solve_time_convergence_triggered"))
                continue
            candidate_id += candidate_start
            user_prompt = f"题目：\n{problem}\n\n请给出完整解答。候选编号：{candidate_id}"
            if instruction:
                user_prompt = f"{instruction}\n\n{user_prompt}"
            response, error = self._request(prompt, user_prompt, self.config.policy_temperature, max_tokens, budget)
            if response is None:
                self._record_diagnostic(budget, "model_error")
                trace.append(_tr("skipped", candidate_id, reason=error, diagnostic_reason="model_error")); continue
            if (self.config.enable_numeric_answer_first_prompt
                    and not self.config.enable_strict_numeric_salvage
                    and problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION)):
                answer = extract_answer_first(response)
            elif self.config.enable_strict_numeric_salvage and problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION):
                answer = extract_numeric_answer(response)
            else:
                answer = extract_final_answer(response)
            structured = True  # 数值题型：answer 非空即清晰答案
            parse_status: str | None = None  # 仅非数值题型记录（实验 F trace 契约）
            if problem_type in _NON_NUMERIC_TASK_TYPES:
                # 13.2 实验 F：用三状态行解析替代 extract_answer_segment——答案标记
                # 必须是独立结构行，嵌在 thinking/约束说明/引号/列表里的伪标记不识别；
                # 占位符（<…>/[Core Answer]/[Option Letter]/…）在解析内拒绝。
                if _has_placeholder_answer(response):
                    self._record_failure_notes(budget, reason="placeholder_answer")
                    trace.append(_tr("rejected", candidate_id, reason="placeholder_answer"))
                    continue
                parsed = parse_structure_f(response, problem_type)
                parse_status = parsed["status"]
                if parse_status == "structured":
                    answer = parsed["answer"]
                    structured = True
                else:
                    # 无真实答案块（no_answer_block / no_body）→ 完整响应兜底，
                    # structured=False，可触发至多一次条件重试（F1 契约）。
                    answer = response.strip()
                    structured = False
            elif not answer:
                diagnostic_reason = "placeholder" if _has_placeholder_answer(response) else "no_marker"
                signals = _truncation_signals(response, answer)
                self._record_failure_notes(
                    budget,
                    reason="answer_not_extractable",
                    truncation_signals=[signal for signal in signals if signal != "no_extractable_answer"],
                    diagnostic_reason=diagnostic_reason,
                )
                self._record_diagnostic(budget, diagnostic_reason)
                trace.append(_tr("rejected", candidate_id, reason="answer_not_extractable",
                                 truncation_signals=signals,
                                 diagnostic_reason=diagnostic_reason))
                continue
            candidates.append({"candidate_id":candidate_id,"answer":answer,"normalized_answer":normalize_answer(answer),"solution":response,"structured":structured,"evidence":[],"verification_status":"unverified","model_calls_used":1,"problem_type":problem_type,"explicit_answer_conflict":has_conflicting_explicit_answers(response)})
            if parse_status is not None:
                trace.append(_tr("ok", candidate_id, parse_status=parse_status))
            else:
                trace.append(_tr("ok", candidate_id))

    # ── P2: heterogeneous candidate generation ───────────────────────────

    def _generate_heterogeneous(
        self, problem: str, total_calls: int, level: str,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, Any], problem_type: str,
    ) -> None:
        """Generate candidates with two complementary reasoning strategies.

        L0 arithmetic stays single-path (1 direct generation).
        Non-L0 splits calls between DirectReasoner and AlternativeReasoner.
        Distribution: >=2 calls → 1 alternative + rest direct; 1 call → direct only.

        Task-aware prompts are merged with reasoner strategies so that
        choice / proof / explanation format constraints are not lost.
        """
        if level == "L0":
            self._generate_candidates(problem, 1, candidates, trace, budget,
                                      self._policy_max_tokens(level),
                                      task_prompt=DIRECT_REASONER_PROMPT,
                                      problem_type=problem_type,
                                      reasoner="direct")
            return

        max_tokens = self._policy_max_tokens(level)

        # ── Task-aware prompt (preserve format constraints) ──
        task_prompt = self._task_policy_prompt(problem_type)
        # Only append task constraint when it differs from the default calculation prompt
        task_extra = ""
        if task_prompt not in (POLICY_PROMPT, CALCULATION_PROMPT):
            task_extra = "\n" + task_prompt

        direct_prompt = DIRECT_REASONER_PROMPT + task_extra
        alt_prompt = ALTERNATIVE_REASONER_PROMPT + task_extra

        # ── Call distribution: ensure total  == total_calls ──
        if total_calls <= 1:
            self._generate_candidates(problem, total_calls, candidates, trace, budget,
                                      max_tokens, task_prompt=direct_prompt,
                                      problem_type=problem_type, reasoner="direct")
            return

        # >=2 calls: 1 alternative, remainder direct
        alt_calls = 1
        direct_calls = total_calls - alt_calls

        self._generate_candidates(problem, direct_calls, candidates, trace, budget,
                                  max_tokens, task_prompt=direct_prompt,
                                  problem_type=problem_type, reasoner="direct")
        self._generate_candidates(problem, alt_calls, candidates, trace, budget,
                                  max_tokens, task_prompt=alt_prompt,
                                  problem_type=problem_type, reasoner="alternative")

    # ── Model request ────────────────────────────────────────────────────

    def _request(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, budget: dict[str, Any]) -> tuple[str|None, str|None]:
        if budget["used"] >= budget["limit"]: return None, "model_call_budget_exhausted"
        # P0: hard time limit — refuse all new calls (per-solve isolation via budget dict).
        if self._time_hard_exceeded(budget.get("solve_start")): return None, "solve_time_budget_exhausted"
        budget["used"] += 1
        try: response = self.client.chat(messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_prompt}],temperature=temperature,max_tokens=max_tokens)
        except Exception as exc: return None, f"model_call_failed:{getattr(exc, 'category', type(exc).__name__)}"
        return (response.strip(), None) if isinstance(response,str) and response.strip() else (None,"empty_model_response")

    # ── P0: time convergence helpers (call-isolated via explicit start_time) ─

    def _time_converge_exceeded(self, start_time: float | None = None) -> bool:
        """True when soft timeout reached — stop generating new candidates."""
        if not self.config.enable_time_convergence or start_time is None:
            return False
        return (time.monotonic() - start_time) >= self.config.solve_converge_timeout_seconds

    def _time_hard_exceeded(self, start_time: float | None = None) -> bool:
        """True when hard timeout reached — stop all new model calls."""
        if not self.config.enable_time_convergence or start_time is None:
            return False
        return (time.monotonic() - start_time) >= self.config.solve_hard_timeout_seconds

    # ── P0: task-aware prompt selection ──────────────────────────────────

    def _task_policy_prompt(self, problem_type: str) -> str:
        """Return the generation prompt for a given problem type."""
        if not self.config.enable_task_aware_prompt:
            return self.config.policy_prompt
        if self.config.enable_numeric_answer_only_prompt and problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION):
            return ANSWER_ONLY_POLICY_PROMPT
        if self.config.enable_numeric_answer_first_prompt and problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION):
            return NUMERIC_ANSWER_FIRST_PROMPT
        return TASK_PROMPTS.get(problem_type, self.config.policy_prompt)

    def _retrieve_method_cards(self, problem: str) -> list[dict[str, Any]]:
        if not self.config.enable_method_rag or self.method_rag_retriever is None:
            return []
        try:
            cards = self.method_rag_retriever.search(problem, top_k=max(0, int(self.config.method_rag_top_k)))
        except Exception:
            return []
        return [card for card in cards if isinstance(card, dict)]

    @staticmethod
    def _try_deterministic_solver(problem: str) -> dict[str, Any]:
        try:
            from deterministic_math import solve_deterministic
            result = solve_deterministic(problem)
            return result if isinstance(result, dict) else {"status": "unsupported", "reason": "invalid_solver_result"}
        except Exception as exc:
            return {"status": "unsupported", "reason": f"solver_error:{type(exc).__name__}"}

    def _method_context(self, problem: str) -> str:
        cards = self._retrieve_method_cards(problem)
        if not cards:
            return ""
        snippets = []
        for card in cards:
            snippets.append(
                "方法：{title}\n适用信号：{signals}\n必要条件：{conditions}\n标准变换：{method}\n常见误用：{pitfalls}".format(
                    title=card.get("title", ""), signals=card.get("signals", ""),
                    conditions=card.get("conditions", ""), method=card.get("method", ""),
                    pitfalls=card.get("pitfalls", ""),
                )
            )
        context = "\n\n参考方法卡（仅作方法提示；必须自行核对条件，不得把卡片示例当作本题答案）：\n" + "\n\n".join(snippets)
        limit = max(0, int(self.config.method_rag_max_context_chars))
        return context[:limit] if limit else ""

    def _format_task_final_response(self, best: dict[str, Any], problem_type: str) -> str:
        """Format final_response according to problem type conventions.

        - choice / fill_blank / calculation: return the compact normalized answer
        - derivation / proof / explanation: rebuild a clean answer-first response
          (drop thinking / prompt echo, keep the conclusion + body)
        """
        if problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION):
            return best.get("normalized_answer") or best["answer"]
        solution = best.get("solution") or best.get("answer", "")
        return reconstruct_final_response_f(solution, problem_type)

    def _generation_plan(self, problem: str) -> tuple[int, str]:
        if not self.config.enable_dynamic_budget:
            if self.config.enable_l0_extended_tokens and self._extract_simple_arithmetic_expression(problem):
                return 1, "L0"
            return self.config.policy_sample_times, "fixed"
        if self._extract_simple_arithmetic_expression(problem):
            return 1, "L0"
        return min(2, self.config.policy_sample_times), "L1"
    def _model_call_limit(self, level: str) -> int:
        if self.config.enable_l2_routing and level != "L0":
            return max(self.config.max_model_calls, self.config.l2_max_model_calls)
        return self.config.max_model_calls
    def _policy_max_tokens(self, level: str) -> int:
        if level == "L0" and self.config.enable_l0_extended_tokens:
            return self.config.l0_max_tokens
        return self.config.max_tokens

    def _retry_max_tokens(self, level: str) -> int:
        if self.config.enable_conditional_token_retry:
            return max(self._policy_max_tokens(level), int(self.config.conditional_retry_max_tokens))
        return self._policy_max_tokens(level)

    @staticmethod
    def _record_failure_notes(budget: dict[str, Any], **notes: Any) -> None:
        stored = budget.setdefault("failure_notes", {})
        stored.clear()
        stored.update(notes)

    def _gate_check(self, problem: str, problem_type: str,
                    candidates: list[dict[str, Any]], budget: dict[str, Any]) -> dict[str, Any]:
        """Return the highest-priority explicit B1 failure, or pass."""
        worst: dict[str, Any] | None = None
        for candidate in candidates:
            verdict = run_answer_checks(
                problem,
                problem_type,
                candidate.get("solution") or "",
                candidate.get("answer", ""),
                candidate.get("structured"),
            )
            if verdict["status"] == "pass":
                return verdict
            if worst is None or _GATE_MODE_PRIORITY.index(verdict["mode"]) < _GATE_MODE_PRIORITY.index(worst["mode"]):
                worst = verdict
        if worst is not None:
            return worst

        notes = budget.get("failure_notes", {}) or {}
        signals = list(notes.get("truncation_signals") or [])
        if signals:
            return {"status": "fail", "mode": "truncation", "detail": {"signals": signals}}
        if notes.get("reason") == "placeholder_answer":
            return {"status": "fail", "mode": "placeholder", "detail": None}
        return {"status": "fail", "mode": "no_answer", "detail": {"signals": ["no_extractable_answer"]}}

    @staticmethod
    def _retry_instruction(mode: str | None, check: dict[str, Any] | None) -> str | None:
        if mode == "truncation":
            return GATED_TRUNCATION_INSTRUCTION
        if mode == "conflict" and check:
            detail = check.get("detail") or {}
            return GATED_CONFLICT_INSTRUCTION.format(first=detail.get("first", ""), second=detail.get("second", ""))
        if mode == "sanity" and check:
            detail = check.get("detail") or {}
            return GATED_SANITY_INSTRUCTION.format(answer=detail.get("answer", ""), constraint=detail.get("constraint", ""))
        if mode == "unstructured":
            return GATED_UNSTRUCTURED_INSTRUCTION
        if mode == "placeholder":
            return GATED_PLACEHOLDER_INSTRUCTION
        return None

    def _conditional_recovery(
        self, problem: str, level: str,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, Any], problem_type: str,
    ) -> None:
        """Use legacy recovery when off; use B1 gate and fail-closed retry when on."""
        task_prompt = self._task_policy_prompt(problem_type)
        gated = self.config.enable_verification_gated_retry
        check = self._gate_check(problem, problem_type, candidates, budget) if gated else None
        if gated:
            trace.append({
                "step": "verification_check",
                "status": check["status"],
                "mode": check["mode"],
                "candidate_count": len(candidates),
            })
            trigger = check["status"] == "fail"
            mode = check["mode"]
        else:
            explicit_answer_conflict = any(candidate.get("explicit_answer_conflict") for candidate in candidates)
            conflict_retry = self.config.enable_explicit_answer_conflict_retry and explicit_answer_conflict
            trigger = (not self._has_clear_answer(candidates)) or conflict_retry
            mode = "explicit_answer_conflict" if conflict_retry else "no_clear_answer"

        instruction = None
        if not trigger:
            return
        if gated:
            instruction = self._retry_instruction(mode, check)
        elif (
            mode == "no_clear_answer"
            and self.config.enable_truncation_recovery_prompt
            and budget.get("failure_notes", {}).get("truncation_signals")
        ):
            mode = "truncation"
            instruction = GATED_TRUNCATION_INSTRUCTION

        trace.append({"step": "conditional_retry", "reason": mode, "model_calls": budget["used"]})
        if self.config.enable_failure_retry_backoff and "model_error" in budget["diagnostic_reasons"]:
            time.sleep(self.config.failure_retry_backoff_seconds)
            trace.append({"step": "conditional_retry_backoff", "seconds": self.config.failure_retry_backoff_seconds})

        retry_trace_start = len(trace)
        retry_bucket: list[dict[str, Any]] = []
        self._generate_candidates(
            problem,
            1,
            retry_bucket,
            trace,
            budget,
            self._retry_max_tokens(level),
            task_prompt=task_prompt,
            problem_type=problem_type,
            instruction=instruction,
        )
        if not gated:
            candidates.extend(retry_bucket)
            return

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        if not retry_bucket:
            rejected_generation = next(
                (
                    entry for entry in trace[retry_trace_start:]
                    if entry.get("step") == "generate_candidate" and entry.get("status") == "rejected"
                ),
                None,
            )
            if rejected_generation:
                signals = rejected_generation.get("truncation_signals") or []
                rejection_mode = (
                    "placeholder"
                    if rejected_generation.get("reason") == "placeholder_answer"
                    or rejected_generation.get("diagnostic_reason") == "placeholder"
                    else "truncation"
                    if any(signal != "no_extractable_answer" for signal in signals)
                    else "no_answer"
                )
                rejected.append({"candidate_id": rejected_generation.get("candidate_id", 0)})
                trace.append({
                    "step": "gated_retry_rejected",
                    "candidate_id": rejected_generation.get("candidate_id", 0),
                    "mode": rejection_mode,
                })
        for candidate in retry_bucket:
            verdict = run_answer_checks(
                problem,
                problem_type,
                candidate.get("solution") or "",
                candidate.get("answer", ""),
                candidate.get("structured"),
            )
            if verdict["status"] == "pass":
                accepted.append(candidate)
            else:
                rejected.append(candidate)
                trace.append({
                    "step": "gated_retry_rejected",
                    "candidate_id": candidate["candidate_id"],
                    "mode": verdict["mode"],
                })

        selection: dict[str, Any] = {
            "step": "verification_gate_selection",
            "accepted": len(accepted),
            "rejected_retry_ids": [item["candidate_id"] for item in rejected],
        }
        if accepted:
            selection["removed_original_ids"] = [item["candidate_id"] for item in candidates]
            candidates[:] = accepted
        else:
            selection["kept_originals"] = True
        trace.append(selection)

    @staticmethod
    def _record_diagnostic(budget: dict[str, Any], reason: str) -> None:
        reasons = budget.setdefault("diagnostic_reasons", [])
        if reason not in reasons:
            reasons.append(reason)
    def _should_escalate_l2(self, level: str, candidates: list[dict[str, Any]]) -> bool:
        return self.config.enable_l2_routing and level != "L0" and len(self._answer_groups(candidates)) > 1
    def _repair_refuted_candidate(self, problem: str, candidates: list[dict[str, Any]], trace: list[dict[str, Any]], budget: dict[str, int]) -> None:
        if not self.config.enable_local_repair or not candidates:
            return
        repairs, has_pass = 0, any(candidate["verification_status"] == "pass" for candidate in candidates)
        for candidate in list(candidates):
            trigger = "fail" if candidate["verification_status"] == "fail" else "uncertain_without_pass" if self.config.enable_uncertain_repair and not has_pass and candidate["verification_status"] == "uncertain" else None
            if repairs >= self.config.max_repairs or trigger is None:
                continue
            response, error = self._request(
                POLICY_PROMPT,
                f"题目：\n{problem}\n\n原候选答案：{candidate['answer']}\n审核已判定其错误。请仅修复受影响推导，并给出新的完整解答。",
                self.config.policy_temperature,
                self.config.max_tokens,
                budget,
            )
            repairs += 1
            answer = extract_final_answer(response or "")
            if not answer:
                trace.append({"step":"repair_candidate","status":"skipped","candidate_id":candidate["candidate_id"],"trigger":trigger,"reason":error or "answer_not_extractable"})
                continue
            repaired = {"candidate_id": max(item["candidate_id"] for item in candidates) + 1, "answer":answer,"normalized_answer":normalize_answer(answer),"solution":response,"evidence":[],"verification_status":"unverified","model_calls_used":1}
            calls_before = budget["used"]
            audit_response, audit_error = self._request(VERIFIER_PROMPT, f"题目：\n{problem}\n\n候选解答：\n{repaired['solution']}", self.config.verifier_temperature, self.config.verifier_max_tokens, budget)
            verdict = self._parse_verdict(audit_response)
            repaired["model_calls_used"] += budget["used"] - calls_before
            repaired["evidence"].append({"source":"llm_audit","verdict":verdict})
            repaired["verification_status"] = self._merge_verdict("unverified", verdict)
            candidates.append(repaired)
            trace.append({"step":"repair_candidate","status":"ok","candidate_id":repaired["candidate_id"],"from_candidate_id":candidate["candidate_id"],"trigger":trigger,"audit_status":verdict if audit_response else "skipped","reason":audit_error})
    @staticmethod
    def _parse_verdict(response: str|None) -> str:
        match = re.search(r"\bVERDICT\s*[:：]\s*(A|B|UNCERTAIN)\b", response or "", re.IGNORECASE)
        return {"A":"pass","B":"fail","UNCERTAIN":"uncertain"}[match.group(1).upper()] if match else "uncertain"
    @staticmethod
    def _merge_verdict(current: str, verdict: str) -> str:
        return "fail" if verdict=="fail" or current=="fail" else "pass" if verdict=="pass" or current=="pass" else "uncertain"
    _extract_final_answer = staticmethod(extract_final_answer)
    _normalize_answer = staticmethod(normalize_answer)
    def _attach_controlled_tool_evidence(self, problem: str, candidates: list[dict[str, Any]], trace: list[dict[str, Any]]) -> None:
        if not self.config.enable_sympy_evidence or not candidates:
            return
        expected_expression = self._extract_simple_arithmetic_expression(problem)
        if not expected_expression:
            trace.append({"step":"controlled_tool","status":"skipped","reason":"unsupported_problem"})
            return
        adapter = self.sympy_adapter
        if adapter is None:
            from sympy_adapter import SympyEvidenceAdapter
            adapter = SympyEvidenceAdapter()
        for candidate in candidates:
            evidence = adapter.check_equivalence(candidate["normalized_answer"], expected_expression, claim_id=f"candidate:{candidate['candidate_id']}")
            evidence["source"] = "controlled_tool"
            candidate["evidence"].append(evidence)
            trace.append({"step":"controlled_tool","status":evidence["execution_status"],"claim_status":evidence["claim_status"],"candidate_id":candidate["candidate_id"]})

    def _attach_substitution_evidence(
        self,
        problem: str,
        problem_type: str,
        candidates: list[dict[str, Any]],
        trace: list[dict[str, Any]],
        budget: dict[str, Any],
    ) -> None:
        if not self.config.enable_substitution_check or not candidates:
            return
        if problem_type not in (TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION):
            trace.append({"step": "substitution_check", "status": "skipped", "reason": "unsupported_problem"})
            return
        from substitution_check import check_substitution, extract_constraint_program

        for candidate in candidates:
            response, error = self._request(
                SUBSTITUTION_CHECK_PROMPT,
                f"题目：\n{problem}\n\n候选答案：\n{candidate['answer']}",
                0.0,
                self.config.substitution_max_tokens,
                budget,
            )
            if response is None:
                evidence = {
                    "source": "substitution_check",
                    "execution_status": "ERROR",
                    "claim_status": "UNKNOWN",
                    "evidence": error or "model_call_failed",
                    "deterministic": True,
                    "error": error or "model_call_failed",
                }
            else:
                evidence = check_substitution(
                    extract_constraint_program(response), candidate["answer"]
                )
            candidate["evidence"].append(evidence)
            trace.append({
                "step": "substitution_check",
                "status": evidence["execution_status"],
                "claim_status": evidence["claim_status"],
                "candidate_id": candidate["candidate_id"],
            })

    @staticmethod
    def _extract_simple_arithmetic_expression(problem: str) -> str | None:
        match = re.fullmatch(r"\s*(?:计算|求值|calculate|evaluate)?\s*([0-9+\-*/().\s]+)\s*[?？]?\s*", problem, re.IGNORECASE)
        return match.group(1).strip() if match else None
    @staticmethod
    def _is_clear_candidate(candidate: dict[str, Any]) -> bool:
        if candidate.get("problem_type") in _NON_NUMERIC_TASK_TYPES:
            return bool(candidate.get("structured"))
        return bool(candidate.get("answer"))

    @classmethod
    def _clear_candidates(cls, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [candidate for candidate in candidates if cls._is_clear_candidate(candidate)]

    @classmethod
    def _has_clear_answer(cls, candidates: list[dict[str, Any]]) -> bool:
        """True when at least one candidate carries a clear answer.

        Non-numeric types (proof/derivation/explanation) require a real
        structured answer block (``structured=True``); a fallback full-response
        candidate does NOT count as clear, so a conditional retry can fire.
        """
        return any(cls._is_clear_candidate(candidate) for candidate in candidates)

    @classmethod
    def _top_clear_group_size(cls, candidates: list[dict[str, Any]]) -> int:
        """Size of the largest equivalence group among clear answers (0 if none)."""
        clear = cls._clear_candidates(candidates)
        if not clear:
            return 0
        return max(len(group) for group in cls._answer_groups(clear).values())

    def _adaptive_vote(
        self, problem: str, level: str,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, Any], task_prompt: str | None = None,
        problem_type: str = TASK_TYPE_CALCULATION,
    ) -> None:
        """Independent resampling with equivalence-group consensus.

        Stops early when the top group of provably equivalent clear answers
        reaches ``vote_agree_threshold``; otherwise samples until ``vote_k_max``
        candidates exist, the call budget runs out, or the wall-clock guard
        trips. Selection itself stays in ``_select_candidate``, which already
        ranks by consensus group size.
        """
        max_tokens = self._policy_max_tokens(level)
        while True:
            top_group_size = self._top_clear_group_size(candidates)
            if top_group_size >= self.config.vote_agree_threshold:
                status = "consensus_reached"
                break
            if len(candidates) >= self.config.vote_k_max:
                status = "k_max_reached"
                break
            if budget["used"] >= budget["limit"]:
                status = "budget_exhausted"
                break
            if self._time_hard_exceeded(budget.get("solve_start")):
                status = "solve_time_budget_exhausted"
                break

            vote_prompt = task_prompt
            reasoner = None
            if self.config.enable_heterogeneous_reasoners:
                constraint = task_prompt or self._task_policy_prompt(problem_type)
                task_extra = "" if constraint in (POLICY_PROMPT, CALCULATION_PROMPT) else "\n" + constraint
                alternative_used = any(
                    entry.get("step") == "generate_candidate"
                    and entry.get("reasoner") == "alternative"
                    for entry in trace
                )
                reasoner = "direct" if alternative_used else "alternative"
                vote_prompt = (
                    DIRECT_REASONER_PROMPT if reasoner == "direct" else ALTERNATIVE_REASONER_PROMPT
                ) + task_extra
            self._generate_candidates(problem, 1, candidates, trace, budget,
                                      max_tokens, task_prompt=vote_prompt,
                                      problem_type=problem_type, reasoner=reasoner)
        trace.append({"step": "adaptive_vote", "status": status,
                      "samples": len(candidates),
                      "top_group_size": self._top_clear_group_size(candidates),
                      "agree_threshold": self.config.vote_agree_threshold,
                      "k_max": self.config.vote_k_max,
                      "model_calls": budget["used"]})

    @staticmethod
    def _answer_groups(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            answer = candidate["answer"]
            matching_group = next(
                (group_id for group_id, group in groups.items() if answer_equivalence(answer, group[0]["answer"]) == "EQUIVALENT"),
                None,
            )
            key = matching_group if matching_group is not None else f"group:{candidate['candidate_id']}"
            groups.setdefault(key, []).append(candidate)
        return groups
    @classmethod
    def _select_candidate(cls, candidates: list[dict[str,Any]]) -> dict[str,Any]:
        clusters = {key: len(group) for key, group in cls._answer_groups(candidates).items()}
        for candidate in candidates:
            key = next(group_id for group_id, group in cls._answer_groups(candidates).items() if candidate in group)
            candidate["consensus"] = clusters[key]
            tool_claims = [
                evidence.get("claim_status")
                for evidence in candidate["evidence"]
                if evidence.get("source") in {"controlled_tool", "substitution_check"}
            ]
            candidate["tool_rank"] = 1 if "SUPPORTED" in tool_claims else -1 if "REFUTED" in tool_claims else 0
            if candidate["tool_rank"]:
                sources = {
                    evidence.get("source")
                    for evidence in candidate["evidence"]
                    if evidence.get("source") in {"controlled_tool", "substitution_check"}
                }
                candidate["selection_basis"] = (
                    "substitution_check_evidence"
                    if "substitution_check" in sources and "controlled_tool" not in sources
                    else "controlled_tool_evidence"
                )
            else:
                candidate["selection_basis"] = "answer_consensus"
        has_unrefuted_candidate = any(candidate["tool_rank"] >= 0 for candidate in candidates)
        return max(candidates,key=lambda item:((item["tool_rank"] >= 0) if has_unrefuted_candidate else True, item["tool_rank"], item.get("structured", True), item["consensus"], sum(evidence.get("verdict")=="pass" for evidence in item["evidence"]), -item["candidate_id"]))

    # ── P3: step verification and targeted revision ──────────────────────

    def _verify_and_revise(
        self, problem: str, best: dict[str, Any],
        _candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, Any], problem_type: str,
    ) -> None:
        """Verify best candidate's solution, optionally revise, re-verify.

        All data is per-solve; never persists across problems.
        """
        solution = best.get("solution", "")
        if not solution:
            return

        # ── Verify ──
        step_errors, gaps, conclusive = self._verify_solution(problem, solution, trace, budget)
        if conclusive is False:
            trace.append({"step":"verify","status":"inconclusive","error_count":0,"gap_count":0})
            return  # malformed verifier output → skip revision
        if conclusive is None:
            # _verify_solution already recorded skipped; no extra entry.
            return

        # Verify ran and produced meaningful output (may have 0 errors — that's ok).
        trace.append({"step":"verify","status":"ok","error_count":len(step_errors),"gap_count":len(gaps)})

        # ── Revise (if enabled and issues found) ──
        if not self.config.enable_step_revision or not (step_errors or gaps):
            return
        revised = self._revise_with_guidance(
            problem, solution, step_errors, gaps, trace, budget, problem_type,
        )
        if revised is None:
            return
        revised_answer = extract_final_answer(revised)
        if not revised_answer:
            trace.append({"step":"revise","status":"rejected","reason":"answer_not_extractable"})
            return

        # Save original in case re-verify fails.
        saved = {"solution": best["solution"], "answer": best["answer"],
                 "normalized_answer": best.get("normalized_answer", "")}
        best["solution"] = revised
        best["answer"] = revised_answer
        best["normalized_answer"] = normalize_answer(revised_answer)
        trace.append({"step":"revise","status":"ok"})

        # ── Re-verify; rollback if new errors found ──
        if budget["used"] < budget["limit"]:
            re_errors, re_gaps, re_conclusive = self._verify_solution(problem, revised, trace, budget, step_label="reverify")
            if re_conclusive is None:
                pass  # skipped — keep revision.
            elif re_conclusive is False:
                trace.append({"step":"reverify","status":"inconclusive","error_count":0,"gap_count":0})
                # Keep revision (verifier broken, not solution).
            elif re_errors or re_gaps:
                trace.append({"step":"reverify","status":"fail","error_count":len(re_errors),"gap_count":len(re_gaps)})
                # Rollback: re-verify found errors the revision didn't fix.
                best["solution"] = saved["solution"]
                best["answer"] = saved["answer"]
                best["normalized_answer"] = saved["normalized_answer"]
            else:
                trace.append({"step":"reverify","status":"ok","error_count":0,"gap_count":0})

    def _verify_solution(
        self, problem: str, solution: str,
        trace: list[dict[str, Any]], budget: dict[str, Any],
        step_label: str = "verify",
    ) -> tuple[list[dict[str, Any]], list[str], bool | None]:
        """Single-call step-by-step verification + completeness check.

        Returns (step_errors, gaps, conclusive):
          - None → request failed / budget exhausted (skipped).
          - False → response did not follow protocol (malformed verifier output).
          - True  → response parsed; may have 0 errors (all clear).

        ``step_label`` distinguishes first verify ("verify") from re-verify
        after revision ("reverify") so trace entries don't collide.
        """
        user_prompt = f"题目：\n{problem}\n\n解答：\n{solution}"
        response, error = self._request(STEP_VERIFY_PROMPT, user_prompt, 0.1, 1024, budget)
        if response is None:
            trace.append({"step": step_label, "status": "skipped", "reason": error})
            return [], [], None
        errors: list[dict[str, Any]] = []
        gaps: list[str] = []
        has_conclusive = False  # requires ERROR: / ALL_OK:COMPLETE, or validated GAPS/ERRORS
        saw_errors_line = False  # "ERRORS" without preceding ERROR: is malformed
        for line in response.splitlines():
            stripped = line.strip()
            if stripped.startswith("ERROR:"):
                has_conclusive = True
                parts = stripped[len("ERROR:"):].split(":", 1)
                errors.append({"step": parts[0].strip() if parts else "",
                               "reason": parts[1].strip() if len(parts) > 1 else stripped})
            elif stripped == "ALL_OK:COMPLETE":
                has_conclusive = True
            elif stripped.startswith("ALL_OK:GAPS:"):
                gap_text = stripped[len("ALL_OK:GAPS:"):]
                gaps = [g.strip() for g in gap_text.split(";") if g.strip()]
                if gaps:
                    has_conclusive = True  # only if at least one non-empty gap parsed
            elif stripped == "ERRORS":
                saw_errors_line = True
        if saw_errors_line and errors:
            has_conclusive = True  # ERRORS only valid when preceded by ERROR: lines
        if not has_conclusive:
            return [], [], False  # malformed — no protocol verdict found
        return errors, gaps, True

    def _revise_with_guidance(
        self, problem: str, solution: str,
        step_errors: list[dict[str, Any]], gaps: list[str],
        trace: list[dict[str, Any]], budget: dict[str, Any], problem_type: str,
    ) -> str | None:
        parts = []
        if step_errors:
            first = step_errors[0]
            parts.append(f"错误步骤：{first.get('step','?')}\n原因：{first.get('reason','?')}")
        if gaps:
            parts.append(f"遗漏：{'；'.join(gaps)}")
        if not parts:
            return None
        error_text = "\n".join(parts)
        user_prompt = (
            f"原题：\n{problem}\n\n原解答：\n{solution}\n\n发现的问题：\n{error_text}\n\n请修正推导并给出新的完整解答。"
        )
        task_prompt = self._task_policy_prompt(problem_type)
        response, error = self._request(STEP_REVISE_PROMPT, user_prompt, 0.4,
                                        self.config.max_tokens, budget)
        if response is None:
            trace.append({"step":"revise","status":"skipped","reason":error})
            return None
        return response.strip() or None
