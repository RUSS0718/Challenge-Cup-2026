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

DERIVATION_PROMPT = """你是严谨的数学推理智能体。这是一道推导题。给出完整的关键推导链，包含必要的中间步骤和定理引用。最后一行必须使用"最终答案："写出推导结果。"""

PROOF_PROMPT = """你是严谨的数学推理智能体。这是一道证明题。给出完整而紧凑的证明，包含命题陈述、关键推理步骤和结论。最后一行必须使用"最终答案：证毕"或"最终答案："后接证明结论。"""

EXPLANATION_PROMPT = """你是严谨的数学推理智能体。这是一道解释/说明题。给出清晰、紧凑的数学解释，包含关键定义和逻辑推理。最后一行必须使用"最终答案："写出核心结论。"""

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
    policy_sample_times: int = 3
    verifier_voting_times: int = 1
    max_model_calls: int = 6
    policy_temperature: float = 0.6
    policy_prompt: str = POLICY_PROMPT
    verifier_temperature: float = 0.0
    max_tokens: int = 1024
    l0_max_tokens: int = 1024
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

def extract_final_answer(response: str) -> str:
    if not isinstance(response, str) or not response.strip(): return ""
    boxed = _extract_boxed_answers(response)
    if boxed: return boxed[-1]
    markers = re.findall(r"(?:最终答案|答案|final\s+answer)\s*[:：]\s*([^\n\r]+)", response, re.IGNORECASE)
    if markers:
        for marker in reversed(markers):
            answer = marker.strip()
            if not is_placeholder_answer(answer): return answer
        return ""
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    for line in reversed(lines):
        choice = re.fullmatch(r"(?:选项\s*)?([A-D])(?:[.。)])?", line, re.IGNORECASE)
        if choice: return choice.group(1).upper()
    return next((line for line in reversed(lines) if not re.fullmatch(r"(?:最终答案|答案|final\s+answer)\s*[:：]?", line, re.IGNORECASE)), "")

def is_placeholder_answer(answer: str) -> bool:
    """Reject output-format placeholders that are not mathematical answers."""
    compact = answer.strip().lower().strip("。；;.,\"'”’ ")
    return compact in {"[answer]", "<answer>", "答案", "answer"}

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
    compact = re.sub(r"\s+", "", answer).rstrip("。；;.,")
    if not compact: return ""
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
        trace.append({"step":"route_budget","level":level,"generation_calls":generation_calls,"max_model_calls":budget["limit"],"problem_type":problem_type})

        # P0: use task-aware prompt when enabled
        task_prompt = self._task_policy_prompt(problem_type)
        self._generate_candidates(problem, generation_calls, candidates, trace, budget, self._policy_max_tokens(level), task_prompt=task_prompt, problem_type=problem_type)

        if self._should_escalate_l2(level, candidates):
            trace.append({"step":"route_budget","level":"L2","generation_calls":1,"max_model_calls":budget["limit"],"reason":"answer_conflict"})
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
            return {"final_response":"未能生成有效数学答案。","trace":trace}
        best = self._select_candidate(candidates)
        # P0: task-aware final_response formatting
        final_answer = self._format_task_final_response(best, problem_type)
        trace.append({"step":"finalize","status":"selected","candidate_id":best["candidate_id"],"selection_basis":best["selection_basis"],"model_calls":budget["used"],"problem_type":problem_type})
        return {"final_response":final_answer,"trace":trace}

    # ── Candidate generation ─────────────────────────────────────────────

    def _generate_candidates(
        self, problem: str, generation_calls: int,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, int], max_tokens: int,
        task_prompt: str | None = None,
        problem_type: str = TASK_TYPE_CALCULATION,
    ) -> None:
        prompt = task_prompt or self.config.policy_prompt
        candidate_start = max((item["candidate_id"] for item in candidates), default=-1) + 1
        for candidate_id in range(generation_calls):
            # P0: time convergence — stop at soft/hard limits (per-solve, isolated via budget dict).
            if self._time_hard_exceeded(budget.get("solve_start")):
                trace.append({"step":"generate_candidate","status":"skipped","candidate_id":candidate_id + candidate_start,"reason":"solve_time_budget_exhausted"})
                continue
            if self._time_converge_exceeded(budget.get("solve_start")):
                trace.append({"step":"generate_candidate","status":"skipped","candidate_id":candidate_id + candidate_start,"reason":"solve_time_convergence_triggered"})
                continue
            candidate_id += candidate_start
            response, error = self._request(prompt, f"题目：\n{problem}\n\n请给出完整解答。候选编号：{candidate_id}", self.config.policy_temperature, max_tokens, budget)
            if response is None:
                trace.append({"step":"generate_candidate","status":"skipped","candidate_id":candidate_id,"reason":error}); continue
            answer = extract_final_answer(response)
            # P0: non-numeric types — answer IS the full solution text (never a
            #      short marker like "证毕" that would group different proofs together).
            #      Placeholder detection uses extract_final_answer semantics, not
            #      a hard length threshold (which would reject short valid proofs).
            if problem_type in _NON_NUMERIC_TASK_TYPES:
                if not answer or is_placeholder_answer(answer):
                    trace.append({"step":"generate_candidate","status":"rejected","candidate_id":candidate_id,"reason":"placeholder_answer"})
                    continue
                answer = response.strip()
            elif not answer:
                trace.append({"step":"generate_candidate","status":"rejected","candidate_id":candidate_id,"reason":"answer_not_extractable"}); continue
            candidates.append({"candidate_id":candidate_id,"answer":answer,"normalized_answer":normalize_answer(answer),"solution":response,"evidence":[],"verification_status":"unverified","model_calls_used":1,"problem_type":problem_type})
            trace.append({"step":"generate_candidate","status":"ok","candidate_id":candidate_id})

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

        - choice / fill_blank: return normalized answer (compact)
        - calculation: return solution text with concise steps preserved
        - derivation / proof / explanation: return the full solution text
        """
        if problem_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK):
            return best.get("normalized_answer") or best["answer"]
        # Calculation keeps steps; non-numeric types keep full reasoning.
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
