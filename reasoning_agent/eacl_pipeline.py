"""Evaluation-aligned GRH control plane with a bounded candidate ladder.

This module is an experimental integration seam.  ARM remains the control
plane for route selection, budgets, candidate lifecycle, and escalation; this
module keeps solver calls, host verification, conservative decision, and ARH
serialization separate.  It never reads gold data and it never treats model
self-reported checks as mathematical evidence.
"""

from __future__ import annotations

import hashlib
import inspect
import re
import time
from typing import Any, Callable, Iterable

from deterministic_math import solve_deterministic
from reasoning_agent.answer_contract import AnswerType, Candidate as ContractCandidate
from reasoning_agent.answer_contract import TaskContract, infer_task_contract
from reasoning_agent.candidate_canonicalizer import ParseResult, parse_response
from reasoning_agent.candidate_validation import validate_candidate_shape
from reasoning_agent.eacl_contracts import (
    FAIL,
    METHOD_ID,
    PASS,
    UNKNOWN,
    CandidateLedger,
    CandidateRecord,
    DecisionRecord,
    EACLConfig,
    RoutePlan,
    VerificationResult,
)
from reasoning_agent.eacl_prompts import recovery_input, recovery_prompt, solver_prompt
from reasoning_agent.harness_contracts import normalize_value, value_equivalence
from reasoning_agent.host_intake import build_host_intake, normalize_problem

_SAFE_SERIALIZE_TYPES = frozenset(
    {
        AnswerType.INTEGER,
        AnswerType.RATIONAL,
        AnswerType.EXPRESSION,
        AnswerType.TUPLE,
        AnswerType.SET,
        AnswerType.CHOICE,
        AnswerType.UNKNOWN,
    }
)
_TRUSTED_UNVERIFIED_SOURCES = frozenset({"answer_marker", "typed_answer", "boxed", "choice"})


class EACLControlPlane:
    """Run ARM routing, candidate evidence, decision, and ARH serialization."""

    def __init__(
        self,
        client: Any,
        *,
        config: EACLConfig | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Bind a public client and immutable per-solve limits."""

        self.client = client
        self.config = config or EACLConfig()
        self.clock = clock or time.monotonic

    def solve(self, problem: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Solve one problem with bounded escalation and fail-closed selection."""

        started = self.clock()
        ledger = CandidateLedger()
        calls = 0
        requested_tokens = 0
        metadata = metadata if isinstance(metadata, dict) else {}
        try:
            normalized_problem = normalize_problem(problem, max_chars=self.config.max_problem_chars)
            intake = build_host_intake(normalized_problem, metadata)
        except Exception as exc:  # malformed host input is an explicit abstention
            ledger.add_event("intake", status="rejected", reason=type(exc).__name__)
            return self._result(ledger, None, DecisionRecord("ABSTAIN", None, None, UNKNOWN, "invalid_problem"), calls, requested_tokens)

        contract = infer_task_contract(intake.problem)
        route = self._route(intake, contract)
        ledger.add_event(
            "route",
            status="selected",
            risk=route.risk,
            answer_type=route.answer_type.value,
            reasoning_mode=route.reasoning_mode,
            reason=route.reason,
        )

        response_a, call_a, token_a = self._call(
            route_name="route_a",
            system_prompt=solver_prompt(route, alternative=False),
            problem=intake.problem,
            reasoning_mode=route.reasoning_mode,
            max_tokens=self.config.route_a_max_tokens,
            started=started,
            calls=calls,
            requested_tokens=requested_tokens,
            ledger=ledger,
        )
        calls += call_a
        requested_tokens += token_a
        candidates_a = self._extract_candidates(
            response_a,
            route="route_a",
            contract=contract,
            reasoning_mode=route.reasoning_mode,
            finish_reason=self._last_finish_reason(),
        )
        self._verify_candidates(candidates_a, intake.problem, contract)
        ledger.add_candidates(candidates_a)

        primary = self._choose_best(candidates_a)
        needs_route_b = self._needs_route_b(primary, candidates_a, route)
        candidates_b: list[CandidateRecord] = []
        response_b: str | None = None
        if needs_route_b and calls < self.config.max_model_calls:
            route_b_mode = "on" if self.config.allow_thinking_on and route.risk != "direct" else "off"
            response_b, call_b, token_b = self._call(
                route_name="route_b",
                system_prompt=solver_prompt(route, alternative=True),
                problem=intake.problem,
                reasoning_mode=route_b_mode,
                max_tokens=self.config.route_b_max_tokens,
                started=started,
                calls=calls,
                requested_tokens=requested_tokens,
                ledger=ledger,
            )
            calls += call_b
            requested_tokens += token_b
            candidates_b = self._extract_candidates(
                response_b,
                route="route_b",
                contract=contract,
                reasoning_mode=route_b_mode,
                finish_reason=self._last_finish_reason(),
            )
            self._verify_candidates(candidates_b, intake.problem, contract)
            ledger.add_candidates(candidates_b)

        decision = self._decide(primary, candidates_b, route)
        selected = self._find_candidate(ledger.candidates, decision.selected_id)
        recoverable_gap = not candidates_b or all(
            not candidate.complete or not candidate.shape_valid for candidate in candidates_b
        )
        if selected is None and recoverable_gap and calls < self.config.max_model_calls:
            recovery_fragment = response_b or response_a or ""
            recovery_response, recovery_call, recovery_tokens = self._call(
                route_name="recovery",
                system_prompt=recovery_prompt(),
                problem=recovery_input(intake.problem, recovery_fragment),
                reasoning_mode="off",
                max_tokens=self.config.recovery_max_tokens,
                started=started,
                calls=calls,
                requested_tokens=requested_tokens,
                ledger=ledger,
            )
            calls += recovery_call
            requested_tokens += recovery_tokens
            candidates_recovery = self._extract_candidates(
                recovery_response,
                route="recovery",
                contract=contract,
                reasoning_mode="off",
                finish_reason=self._last_finish_reason(),
            )
            self._verify_candidates(candidates_recovery, intake.problem, contract)
            ledger.add_candidates(candidates_recovery)
            if len(candidates_recovery) == 1:
                decision = self._decide(primary, candidates_recovery, route)
                selected = self._find_candidate(ledger.candidates, decision.selected_id)
        if (
            selected is not None
            and decision.action == "SELECT"
            and selected.answer_type in {answer.value for answer in _SAFE_SERIALIZE_TYPES}
            and self.config.enable_off_finalizer
            and calls < self.config.max_model_calls
        ):
            selected, finalizer_call = self._run_off_finalizer(
                selected,
                contract,
                started=started,
                calls=calls,
                requested_tokens=requested_tokens,
                ledger=ledger,
            )
            calls += finalizer_call
            decision = DecisionRecord(
                decision.action,
                decision.selected_id,
                decision.selected_route,
                decision.verification,
                f"{decision.reason}; off_finalizer_checked",
            )

        return self._result(ledger, selected, decision, calls, requested_tokens)

    def _route(self, intake: Any, contract: TaskContract) -> RoutePlan:
        """Choose a coarse risk lane without reading answers or past questions."""

        complexity = intake.complexity
        if complexity.has_proof_language or complexity.has_universal_language or complexity.profile == "long":
            risk = "deep"
        elif complexity.profile == "structured":
            risk = "structured"
        else:
            risk = "direct"
        if risk == "direct":
            mode = "off"
            reason = "direct_low_risk_off_first"
        else:
            mode = "on" if self.config.allow_thinking_on else "off"
            reason = "structured_or_deep_reasoning"
        return RoutePlan(risk, contract.answer_type, mode, reason)

    def _call(
        self,
        *,
        route_name: str,
        system_prompt: str,
        problem: str,
        reasoning_mode: str,
        max_tokens: int,
        started: float,
        calls: int,
        requested_tokens: int,
        ledger: CandidateLedger,
    ) -> tuple[str | None, int, int]:
        """Perform one bounded request and record sanitized runtime telemetry."""

        elapsed = self.clock() - started
        if calls >= self.config.max_model_calls:
            ledger.add_event("call", route=route_name, status="skipped", reason="call_cap")
            return None, 0, 0
        if elapsed >= self.config.hard_deadline_seconds:
            ledger.add_event("call", route=route_name, status="skipped", reason="hard_deadline")
            return None, 0, 0
        if requested_tokens + max_tokens > self.config.total_token_budget:
            ledger.add_event("call", route=route_name, status="skipped", reason="token_budget")
            return None, 0, 0
        if calls > 0 and elapsed >= self.config.soft_deadline_seconds:
            ledger.add_event("call", route=route_name, status="skipped", reason="soft_deadline")
            return None, 0, 0

        user_prompt = f"题目：\n{problem}\n\n请按候选协议完成。"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        call_started = self.clock()
        try:
            mode_support = self._client_supports_reasoning_mode()
            call_kwargs = {
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": max_tokens,
            }
            if mode_support:
                call_kwargs["reasoning_mode"] = reasoning_mode
            response = self.client.chat(**call_kwargs)
        except Exception as exc:  # public client failures are represented, not raised
            ledger.add_event(
                "call",
                route=route_name,
                status="error",
                error_category=self._error_category(exc),
                reasoning_mode=reasoning_mode,
                duration_ms=round((self.clock() - call_started) * 1000, 1),
            )
            return None, 1, max_tokens

        if self.clock() - started >= self.config.hard_deadline_seconds:
            ledger.add_event(
                "call",
                route=route_name,
                status="late_response_discarded",
                reasoning_mode=reasoning_mode,
                mode_support=mode_support,
                duration_ms=round((self.clock() - call_started) * 1000, 1),
            )
            return None, 1, max_tokens

        if not isinstance(response, str) or not response.strip():
            ledger.add_event(
                "call",
                route=route_name,
                status="invalid_response",
                reasoning_mode=reasoning_mode,
                mode_support=mode_support,
                duration_ms=round((self.clock() - call_started) * 1000, 1),
            )
            return None, 1, max_tokens

        ledger.add_event(
            "call",
            route=route_name,
            status="ok",
            reasoning_mode=reasoning_mode,
            mode_support=mode_support,
            finish_reason=self._last_finish_reason(),
            completion_tokens=self._last_completion_tokens(),
            duration_ms=round((self.clock() - call_started) * 1000, 1),
        )
        return response.strip(), 1, max_tokens

    def _client_supports_reasoning_mode(self) -> bool:
        """Detect keyword support before calling so a TypeError cannot duplicate a request."""

        try:
            parameters = inspect.signature(self.client.chat).parameters.values()
        except (TypeError, ValueError):
            return True
        return any(
            parameter.name == "reasoning_mode"
            or parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def _extract_candidates(
        self,
        response: str | None,
        *,
        route: str,
        contract: TaskContract,
        reasoning_mode: str,
        finish_reason: str | None,
    ) -> list[CandidateRecord]:
        """Parse one response into bounded candidate records."""

        if not isinstance(response, str) or not response.strip():
            return []
        parsed: ParseResult = parse_response(response, contract)
        truncated = (finish_reason or "").casefold() in {"length", "max_tokens", "truncated"}
        if not parsed.candidates:
            return []
        records: list[CandidateRecord] = []
        for index, candidate in enumerate(parsed.candidates, 1):
            shape_valid, shape_reason = validate_candidate_shape(
                candidate,
                self._validation_type(contract.answer_type),
            )
            canonical = self._canonical_candidate_value(candidate, contract)
            records.append(
                CandidateRecord(
                    candidate_id=f"{route}-{index}",
                    route=route,
                    value=candidate.value,
                    canonical_value=canonical,
                    source=candidate.source,
                    answer_type=candidate.answer_type.value,
                    complete=candidate.accepted and not parsed.rejection_reason,
                    shape_valid=shape_valid,
                    truncated=truncated,
                    reasoning_mode=reasoning_mode,
                    raw_span_hash=hashlib.sha256(candidate.value.encode("utf-8")).hexdigest(),
                    rejection_reason="" if shape_valid else shape_reason,
                )
            )
        return records

    @staticmethod
    def _canonical_candidate_value(candidate: ContractCandidate, contract: TaskContract) -> str:
        """Canonicalize numeric surfaces without changing ordered structures."""

        surface = candidate.canonical_value or candidate.value
        if contract.answer_type in {
            AnswerType.INTEGER,
            AnswerType.RATIONAL,
            AnswerType.CHOICE,
        }:
            return normalize_value(surface)
        if re.fullmatch(r"[+-]?(?:\d+(?:/\d+)?|\d+(?:\.\d+)?)", surface.strip()):
            return normalize_value(surface)
        if re.fullmatch(
            r"[+-]?\\(?:frac|dfrac|tfrac)\{[^{}]+\}\{[^{}]+\}",
            surface.strip(),
        ):
            return normalize_value(surface)
        return surface

    @staticmethod
    def _validation_type(answer_type: AnswerType) -> str:
        """Map the public contract enum to the existing validator vocabulary."""

        if answer_type == AnswerType.EXPRESSION:
            return "exact_expression"
        if answer_type == AnswerType.TUPLE:
            return "unknown"
        return answer_type.value

    @staticmethod
    def _verify_candidates(
        candidates: Iterable[CandidateRecord],
        problem: str,
        contract: TaskContract,
    ) -> None:
        """Apply only deterministic, bounded verification adapters."""

        del contract
        deterministic = solve_deterministic(problem)
        for candidate in candidates:
            if not candidate.complete or not candidate.shape_valid:
                candidate.verification = FAIL
                candidate.verification_reason = candidate.rejection_reason or "incomplete_or_invalid_shape"
                continue
            if deterministic.get("status") == "supported":
                expected = str(deterministic.get("answer") or "")
                relation = value_equivalence(candidate.canonical_value, expected)
                if relation == "EQUIVALENT":
                    candidate.verification = PASS
                    candidate.verification_reason = "deterministic_solver_match"
                elif relation == "NOT_EQUIVALENT":
                    candidate.verification = FAIL
                    candidate.verification_reason = "deterministic_solver_mismatch"
                else:
                    candidate.verification = UNKNOWN
                    candidate.verification_reason = "deterministic_comparison_unknown"
            else:
                candidate.verification = UNKNOWN
                candidate.verification_reason = "no_safe_verifier_for_problem"

    def _needs_route_b(
        self,
        primary: CandidateRecord | None,
        candidates_a: list[CandidateRecord],
        route: RoutePlan,
    ) -> bool:
        """Trigger bounded escalation only on missing, conflict, or weak evidence."""

        if not self.config.allow_route_b_on_unknown:
            return primary is None or len(candidates_a) != 1 or primary.verification == FAIL
        if primary is None or len(candidates_a) != 1:
            return True
        if primary.verification == FAIL or primary.truncated or not primary.complete:
            return True
        if primary.verification == UNKNOWN:
            return route.risk != "direct" or self.config.allow_route_b_on_unknown
        return False

    @staticmethod
    def _choose_best(candidates: list[CandidateRecord]) -> CandidateRecord | None:
        """Choose a single route-local incumbent without hiding conflicts."""

        if len(candidates) != 1:
            return None
        candidate = candidates[0]
        if not candidate.complete or not candidate.shape_valid:
            return None
        if candidate.verification == UNKNOWN and candidate.source not in _TRUSTED_UNVERIFIED_SOURCES:
            return None
        return candidate

    @staticmethod
    def _find_candidate(candidates: Iterable[CandidateRecord], candidate_id: str | None) -> CandidateRecord | None:
        """Find a selected candidate by its stable ledger id."""

        if not candidate_id:
            return None
        return next((candidate for candidate in candidates if candidate.candidate_id == candidate_id), None)

    def _decide(
        self,
        primary: CandidateRecord | None,
        candidates_b: list[CandidateRecord],
        route: RoutePlan,
    ) -> DecisionRecord:
        """Select only on deterministic support or conservative agreement."""

        secondary = self._choose_best(candidates_b)
        if primary is not None and secondary is None:
            if primary.verification == FAIL:
                return DecisionRecord("ABSTAIN", None, None, FAIL, "primary_refuted_without_replacement")
            return DecisionRecord("SELECT", primary.candidate_id, primary.route, primary.verification, "route_a_only")
        if primary is None and secondary is not None:
            if secondary.verification == FAIL:
                return DecisionRecord("ABSTAIN", None, None, FAIL, "route_b_candidate_refuted")
            return DecisionRecord("SELECT", secondary.candidate_id, secondary.route, secondary.verification, "route_b_recovered")
        if primary is None and secondary is None:
            return DecisionRecord("ABSTAIN", None, None, UNKNOWN, "no_closed_candidate")

        assert primary is not None and secondary is not None
        relation = value_equivalence(primary.canonical_value, secondary.canonical_value)
        if relation == "EQUIVALENT":
            if primary.verification == FAIL and secondary.verification == FAIL:
                return DecisionRecord("ABSTAIN", None, None, FAIL, "agreed_candidate_refuted")
            status = PASS if primary.verification == PASS or secondary.verification == PASS else UNKNOWN
            return DecisionRecord("SELECT", primary.candidate_id, primary.route, status, "route_agreement")
        if primary.verification == PASS and secondary.verification == FAIL:
            return DecisionRecord("SELECT", primary.candidate_id, primary.route, PASS, "primary_pass_secondary_fail")
        if secondary.verification == PASS and primary.verification == FAIL:
            return DecisionRecord("SELECT", secondary.candidate_id, secondary.route, PASS, "secondary_pass_primary_fail")
        return DecisionRecord("ABSTAIN", None, None, UNKNOWN, f"unresolved_conflict:{route.risk}")

    def _run_off_finalizer(
        self,
        selected: CandidateRecord,
        contract: TaskContract,
        *,
        started: float,
        calls: int,
        requested_tokens: int,
        ledger: CandidateLedger,
    ) -> tuple[CandidateRecord, int]:
        """Ask OFF mode only to repeat the selected canonical value."""

        prompt = (
            "只做格式收束，不重新解题，不改变数学值。\n"
            f"已有 canonical candidate: {selected.canonical_value}\n"
            f"answer_type: {contract.answer_type.value}\n"
            "严格输出：FINAL_CANDIDATE: <同一个 canonical candidate>。"
        )
        response, used, _ = self._call(
            route_name="off_finalizer",
            system_prompt="你是 OFF 模式的最终答案格式化器。",
            problem=prompt,
            reasoning_mode="off",
            max_tokens=self.config.finalizer_max_tokens,
            started=started,
            calls=calls,
            requested_tokens=requested_tokens,
            ledger=ledger,
        )
        if not response:
            ledger.add_event("finalizer", status="kept_incumbent", reason="no_response")
            return selected, used
        parsed = parse_response(response, contract)
        if not parsed.complete:
            ledger.add_event("finalizer", status="kept_incumbent", reason="parse_failed")
            return selected, used
        candidate = parsed.candidates[0]
        if value_equivalence(candidate.canonical_value, selected.canonical_value) != "EQUIVALENT":
            ledger.add_event("finalizer", status="kept_incumbent", reason="value_changed")
            return selected, used
        ledger.add_event("finalizer", status="accepted", candidate_id=selected.candidate_id)
        return selected, used

    def _result(
        self,
        ledger: CandidateLedger,
        selected: CandidateRecord | None,
        decision: DecisionRecord,
        calls: int,
        requested_tokens: int,
    ) -> dict[str, Any]:
        """Serialize one solve result through the host-side answer contract."""

        if (
            selected is None
            or decision.action != "SELECT"
            or selected.answer_type not in {answer.value for answer in _SAFE_SERIALIZE_TYPES}
        ):
            final_response = "UNKNOWN"
            extracted = ""
        elif selected.answer_type in {answer.value for answer in _SAFE_SERIALIZE_TYPES}:
            extracted = selected.canonical_value
            final_response = f"最终答案：{extracted}\n\\boxed{{{extracted}}}"
        else:
            extracted = selected.canonical_value
            final_response = f"最终答案：{extracted}"
        ledger.add_event(
            "decision",
            action=decision.action,
            selected_id=decision.selected_id,
            selected_route=decision.selected_route,
            verification=decision.verification,
            reason=decision.reason,
        )
        return {
            "final_response": final_response,
            "extracted_answer": extracted,
            "model_calls": calls,
            "requested_tokens": requested_tokens,
            "decision": decision.as_dict(),
            "trace": ledger.as_trace(model_calls=calls, requested_tokens=requested_tokens),
        }

    def _last_finish_reason(self) -> str | None:
        """Read optional local-client finish metadata without requiring it."""

        value = getattr(self.client, "last_response_metadata", None)
        return value.get("finish_reason") if isinstance(value, dict) else None

    def _last_completion_tokens(self) -> int | None:
        """Read optional local-client token metadata without exposing prompts."""

        value = getattr(self.client, "last_response_metadata", None)
        if not isinstance(value, dict):
            return None
        raw = value.get("completion_tokens")
        return int(raw) if isinstance(raw, int) else None

    @staticmethod
    def _error_category(exc: BaseException) -> str:
        """Reduce arbitrary client exceptions to a safe diagnostic category."""

        text = f"{type(exc).__name__} {exc}".casefold()
        if "timeout" in text:
            return "timeout"
        if "429" in text or "rate" in text:
            return "rate_limit"
        if "connection" in text or "proxy" in text:
            return "connectivity"
        return "client_error"


__all__ = [
    "CandidateLedger",
    "CandidateRecord",
    "DecisionRecord",
    "EACLConfig",
    "EACLControlPlane",
    "FAIL",
    "METHOD_ID",
    "PASS",
    "UNKNOWN",
    "VerificationResult",
]
