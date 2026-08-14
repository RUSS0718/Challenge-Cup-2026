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
POLICY_PROMPT = """你是严谨的数学推理智能体。解决用户给出的数学问题。优先收敛到答案，不要复述题意、不要输出格式说明或无关说明；给出简洁但充分的推导。最后一行必须使用“最终答案：”明确写出答案。"""
ANSWER_FIRST_POLICY_PROMPT = POLICY_PROMPT
ANSWER_ONLY_POLICY_PROMPT = """你是数学求解器。直接解题，不要输出 Thinking Process、计划、标题或格式说明。只输出一行“最终答案：”后接数学答案。"""
VERIFIER_PROMPT = """你是数学解答审核员。独立检查候选答案是否能正确解决题目。
若发现错误，指出第一个可证实的错误位置；不要复述完整解答。
最后一行必须且只能为：VERDICT: A、VERDICT: B 或 VERDICT: UNCERTAIN。
A 表示未发现可证实错误，B 表示发现可证实错误，UNCERTAIN 表示无法判断。"""

# ── Task-aware prompts ─────────────────────────────────────────────────────
# Each prompt guides the model toward the expected output format for a specific
# question type.  All are universal (never refer to sample idx or answer).

CHOICE_PROMPT = """你是数学求解器。这是一道选择题。分析每个选项，选出唯一正确的一项。只需给出选项字母和一行简要理由。最后一行必须使用"最终答案：X"写出选项字母。"""

FILL_BLANK_PROMPT = """你是数学求解器。这是一道填空题。直接计算并填入结果。最后一行必须使用"最终答案："写出填入值。"""

CALCULATION_PROMPT = POLICY_PROMPT  # 复用已验证的 answer-first 提示词

DERIVATION_PROMPT = """你是严谨的数学推理智能体。这是一道推导题。不要输出 Thinking Process、内部计划、元分析或格式说明；直接输出面向用户的正式答案，保留完整、必要的关键推导链、中间步骤和定理引用。最后一行必须使用"最终答案："写出推导结果。"""

PROOF_PROMPT = """你是严谨的数学推理智能体。这是一道证明题。不要输出 Thinking Process、内部计划、元分析或格式说明；直接输出面向用户的正式答案，保留完整而紧凑的证明（命题陈述、关键推理步骤、结论）。最后一行必须使用"最终答案：证毕"或"最终答案："后接证明结论。"""

EXPLANATION_PROMPT = """你是严谨的数学推理智能体。这是一道解释/说明题。不要输出 Thinking Process、内部计划、元分析或格式说明；直接输出面向用户的正式答案，保留清晰、紧凑的数学解释（关键定义和逻辑推理）。最后一行必须使用"最终答案："写出核心结论。"""

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
    # and no verify-only P3.  3072 tokens is the P0.1 ladder result: the lowest
    # cap that clears Gate 2 (finish_reason=length <= 20%, marker coverage >=
    # 95%) with reproducible accuracy (81.2% / 80.4% across two runs).
    policy_sample_times: int = 1
    verifier_voting_times: int = 0
    max_model_calls: int = 2
    policy_temperature: float = 0.6
    policy_prompt: str = POLICY_PROMPT
    verifier_temperature: float = 0.0
    max_tokens: int = 3072
    l0_max_tokens: int = 3072
    verifier_max_tokens: int = 256
    enable_sympy_evidence: bool = False
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


_ANSWER_MARKER_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]\s*([^\n\r]+)", re.IGNORECASE)
_CHOICE_LINE_RE = re.compile(r"^(?:选项\s*)?([A-Da-d])(?:[.。)）]?)\s*$")
# A standalone answer line must be pure math (no CJK prose / sentence punctuation).
_MATH_ONLY_LINE_RE = re.compile(r"^[\sA-Za-z0-9+\-*/=<>≤≥.,(){}[\]^_'\\|±×÷]+$")
# Natural-language connectives that mark a truncated / prose fragment.
_CONNECTIVE_RE = re.compile(r"(因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)")


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

class ReasoningAgent:
    def __init__(self, client: Any, config: AgentConfig | None = None, sympy_adapter: Any | None = None, **_: Any) -> None:
        self.client, self.config = client, config or AgentConfig()
        self.sympy_adapter = sympy_adapter

    # ── Public API ──────────────────────────────────────────────────────

    def solve(self, problem: str, metadata: dict) -> dict:
        del metadata
        # P0: classify problem type (universal, text-based)
        problem_type = classify_problem_type(problem)

        trace, candidates = [], []
        generation_calls, level = self._generation_plan(problem)
        # P0: per-solve budget dict carries time for call isolation (no shared instance field).
        budget: dict[str, Any] = {"used": 0, "limit": self._model_call_limit(level),
                                   "solve_start": time.monotonic() if self.config.enable_time_convergence else None}
        # P3: boost call budget so verification + revision have room beyond gen+audit.
        if self.config.enable_step_verification:
            budget["limit"] += self.config.p3_call_boost
        trace.append({"step":"route_budget","level":level,"generation_calls":generation_calls,"max_model_calls":budget["limit"],"problem_type":problem_type})

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
        if not self._has_clear_answer(candidates):
            trace.append({"step": "conditional_retry", "reason": "no_clear_answer",
                          "model_calls": budget["used"]})
            task_prompt = self._task_policy_prompt(problem_type)
            self._generate_candidates(problem, 1, candidates, trace, budget,
                                      self._policy_max_tokens(level),
                                      task_prompt=task_prompt, problem_type=problem_type)

        if self._should_escalate_l2(level, candidates):
            trace.append({"step":"route_budget","level":"L2","generation_calls":1,"max_model_calls":budget["limit"],"reason":"answer_conflict"})
            task_prompt = self._task_policy_prompt(problem_type)
            self._generate_candidates(problem, 1, candidates, trace, budget, self._policy_max_tokens("L2"), task_prompt=task_prompt, problem_type=problem_type)

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
            trace.append({"step":"finalize","status":"fallback","reason":"no_valid_candidate","model_calls":budget["used"],"problem_type":problem_type})
            return {"final_response":"未能生成有效数学答案。","trace":trace, "extracted_answer": ""}
        best = self._select_candidate(candidates)

        # ── P3: step verification + targeted revision ──
        if self.config.enable_step_verification and best.get("solution"):
            self._verify_and_revise(problem, best, candidates, trace, budget, problem_type)

        # P0: task-aware final_response formatting
        final_answer = self._format_task_final_response(best, problem_type)
        # Evaluator-facing compact answer (independent of final_response formatting)
        extracted_answer = best.get("normalized_answer") or best.get("answer", "")
        trace.append({"step":"finalize","status":"selected","candidate_id":best["candidate_id"],"selection_basis":best["selection_basis"],"model_calls":budget["used"],"problem_type":problem_type})
        return {"final_response":final_answer,"trace":trace, "extracted_answer": extracted_answer}

    # ── Candidate generation ─────────────────────────────────────────────

    def _generate_candidates(
        self, problem: str, generation_calls: int,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, int], max_tokens: int,
        task_prompt: str | None = None,
        problem_type: str = TASK_TYPE_CALCULATION,
        reasoner: str | None = None,  # P2: "direct" | "alternative" | None
    ) -> None:
        prompt = task_prompt or self.config.policy_prompt
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
            response, error = self._request(prompt, f"题目：\n{problem}\n\n请给出完整解答。候选编号：{candidate_id}", self.config.policy_temperature, max_tokens, budget)
            if response is None:
                trace.append(_tr("skipped", candidate_id, reason=error)); continue
            answer = extract_final_answer(response)
            if problem_type in _NON_NUMERIC_TASK_TYPES:
                # Proof / derivation / explanation deliver the full response as
                # the answer; only reject format-instruction echoes carrying a
                # placeholder answer token.
                if _has_placeholder_answer(response):
                    trace.append(_tr("rejected", candidate_id, reason="placeholder_answer"))
                    continue
                answer = response.strip()
            elif not answer:
                trace.append(_tr("rejected", candidate_id, reason="answer_not_extractable",
                                 truncation_signals=_truncation_signals(response, answer)))
                continue
            candidates.append({"candidate_id":candidate_id,"answer":answer,"normalized_answer":normalize_answer(answer),"solution":response,"evidence":[],"verification_status":"unverified","model_calls_used":1,"problem_type":problem_type})
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
        return TASK_PROMPTS.get(problem_type, self.config.policy_prompt)

    def _format_task_final_response(self, best: dict[str, Any], problem_type: str) -> str:
        """Format final_response according to problem type conventions.

        - choice / fill_blank / calculation: return the compact normalized answer
        - derivation / proof / explanation: return the full solution text
        """
        if problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK, TASK_TYPE_CALCULATION):
            return best.get("normalized_answer") or best["answer"]
        return best.get("solution") or best.get("answer", "")

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

    @staticmethod
    def _extract_simple_arithmetic_expression(problem: str) -> str | None:
        match = re.fullmatch(r"\s*(?:计算|求值|calculate|evaluate)?\s*([0-9+\-*/().\s]+)\s*[?？]?\s*", problem, re.IGNORECASE)
        return match.group(1).strip() if match else None
    @staticmethod
    def _has_clear_answer(candidates: list[dict[str, Any]]) -> bool:
        """True when at least one candidate carries a non-empty extracted answer."""
        return any(bool(candidate.get("answer")) for candidate in candidates)

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
                if evidence.get("source") == "controlled_tool"
            ]
            candidate["tool_rank"] = 1 if "SUPPORTED" in tool_claims else -1 if "REFUTED" in tool_claims else 0
            candidate["selection_basis"] = "controlled_tool_evidence" if candidate["tool_rank"] else "answer_consensus"
        has_unrefuted_candidate = any(candidate["tool_rank"] >= 0 for candidate in candidates)
        return max(candidates,key=lambda item:((item["tool_rank"] >= 0) if has_unrefuted_candidate else True, item["tool_rank"], item["consensus"], sum(evidence.get("verdict")=="pass" for evidence in item["evidence"]), -item["candidate_id"]))

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
