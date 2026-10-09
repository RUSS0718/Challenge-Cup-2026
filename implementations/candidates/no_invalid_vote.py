"""Protect solve-local complete answers without changing the imported generator."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import re
from typing import Any
from uuid import uuid4

from .sl_v3_cont.postprocess import (
    _FINAL_LINE_RE, _delimiters_balanced, _is_high_confidence_candidate,
    _latex_environments_balanced, _line_is_complete, _truncation_signal,
    guarded_normalize,
)
from implementations.postprocess.normalizer import (
    _REASONING_REQUIRED, _extract_multipart, _has_unsupported_multipart, _json_prefix,
    _json_covers_parts, _labeled_part_values, _problem_parts,
)


_UNAVAILABLE = re.compile(
    r"^(?:无法确定|无法解答|无法求解|不知道|待定|unknown|unavailable|"
    r"cannot\s+(?:determine|solve)|null|undefined|undetermined|n/?a|答案|answer|\.{3,}|…+)[。.!！]*$", re.I,
)
_COLLECTION_REQUEST = re.compile(
    r"\b(?:solution\s+set|set\s+of|(?:list|array)\s+of|"
    r"JSON\s+(?:list|array)|as\s+(?:a\s+)?(?:list|array))\b|集合|解集|列表|数组", re.I,
)


def _json_answers_complete(parsed: Any, *, allow_empty_list: bool = False) -> bool:
    """Reject missing leaves; empty lists require an explicit single collection request.

    Empty objects carry no answer member. Multipart empty leaves stay ambiguous
    and unprotected rather than inheriting a collection request from another part.
    """
    pending = [parsed]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if not value:
                return False
            pending.extend(value.values())
        elif isinstance(value, list):
            if not value and not allow_empty_list:
                return False
            pending.extend(value)
        elif value is None or isinstance(value, str) and (
            _UNAVAILABLE.fullmatch(value.strip()) or not _line_is_complete(value)
        ):
            return False
    return True


def complete_supported_answer(answer: object, problem: str) -> bool:
    """Reuse deterministic shape checks; completeness is not mathematical validity.

    Only supported scalar/structured terminal forms, numeric labeled multipart,
    or a closed derivation with a complete final declaration are retained.
    Unsupported shapes remain eligible for imported recovery, not protection.
    """
    if not isinstance(answer, str) or not answer.strip():
        return False
    text = answer.strip()
    if _UNAVAILABLE.fullmatch(text) or _truncation_signal(text):
        return False
    if not _delimiters_balanced(text) or not _latex_environments_balanced(text):
        return False
    final_lines = list(_FINAL_LINE_RE.finditer(text))
    if any(_UNAVAILABLE.fullmatch(item.group("answer").strip()) for item in final_lines):
        return False
    if _has_unsupported_multipart(problem):
        return False
    parts = _problem_parts(problem)
    if parts:
        multipart = _extract_multipart(text, problem, parts)
        structured = _json_prefix(multipart or text)
        if structured is not None:
            if not _json_covers_parts(structured[1], parts) or not _json_answers_complete(structured[1]):
                return False
        else:
            values = _labeled_part_values(multipart, parts) if multipart else None
            if values is None or any(_UNAVAILABLE.fullmatch(value) or not _line_is_complete(value)
                                     for value in values.values()):
                return False
    if _REASONING_REQUIRED.search(problem):
        if not final_lines or not _line_is_complete(final_lines[-1].group("answer")):
            return False
        # A bare assertion cannot replace a requested proof or derivation.
        return bool(text[:final_lines[-1].start()].strip())
    if parts:
        return True
    normalized = guarded_normalize(text, problem).final_response
    if normalized.startswith(("{", "[")):
        structured = _json_prefix(normalized)
        if structured is None or not _json_answers_complete(
            structured[1], allow_empty_list=bool(_COLLECTION_REQUEST.search(problem))
        ):
            return False
    return _is_high_confidence_candidate(normalized) and not _UNAVAILABLE.fullmatch(normalized)


@dataclass(frozen=True)
class Candidate:
    """Bind exact delivered bytes and their source to one problem and solve."""

    solve_id: str
    problem_id: str
    candidate_id: str
    path: int
    source: str
    result: dict[str, Any]


def text_identity(value: str) -> str:
    """Use a digest for replay identity without logging problem or answer text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CompleteAnswerProtection:
    """Retain a complete incumbent across optional paths and handled deadlines."""

    def _reset_candidates(self, problem: str) -> None:
        """Reset all identities before each solve, including on reused instances."""
        self._candidate_problem = problem
        self._candidate_problem_id = text_identity(problem)
        self._candidate_solve_id = uuid4().hex
        self._candidate_path = 1
        self._candidate_records: list[Candidate] = []
        self._incumbent: Candidate | None = None

    def _record_candidate(self, result: dict, source: str) -> None:
        """Retain supported complete output; fragments keep baseline recovery only."""
        answer = result.get("final_response")
        if not complete_supported_answer(answer, self._candidate_problem):
            return
        record = Candidate(
            self._candidate_solve_id, self._candidate_problem_id,
            text_identity(answer), self._candidate_path, source, deepcopy(result),
        )
        if not any(item.candidate_id == record.candidate_id and item.path == record.path
                   for item in self._candidate_records):
            self._candidate_records.append(record)
        if self._incumbent is None or self._incumbent.path == record.path:
            self._incumbent = record

    def _remember_result(self, result: dict) -> None:
        """Keep the imported recovery state and separately retain complete results."""
        super()._remember_result(result)
        self._record_candidate(result, "path_result")

    def _remember_answer(self, answer: str, status: str) -> None:
        """Capture a complete response before a possible asynchronous deadline."""
        super()._remember_answer(answer, status)
        normalized = self._postprocess_or_original(answer, self._candidate_problem)
        self._record_candidate(self._result_from_answer(normalized, status), status)

    def _start_extra_path(self) -> None:
        """Reset only imported path state; solve-level candidates survive."""
        super()._start_extra_path()
        self._candidate_path += 1

    def _best_effort_result(self, status: str, error_type: str | None = None) -> dict:
        """Prefer a retained complete answer at handled error/deadline boundaries."""
        if self._incumbent is not None:
            retained = deepcopy(self._incumbent.result)
            trace = retained.get("trace", [])
            if trace and isinstance(trace[0].get("content"), dict):
                trace[0]["content"]["status"] = status
                if error_type is not None:
                    trace[0]["content"]["error_type"] = error_type
            return super()._finalize_result(retained)
        return super()._best_effort_result(status, error_type)

    def _finalize_result(self, result: dict) -> dict:
        """Capture complete path output before optional work starts."""
        final = super()._finalize_result(result)
        self._record_candidate(final, "finalized_path")
        return final

    def _select_among_paths(self, results: list[dict]) -> dict:
        """Filter only voting inputs, preserving generation gates and path numbering."""
        eligible = [complete_supported_answer(
            item.get("final_response"), self._candidate_problem
        ) for item in results]
        if not any(eligible):
            return super()._select_among_paths(results)
        voting = [item if supported else {**item, "final_response": ""}
                  for item, supported in zip(results, eligible)]
        return super()._select_among_paths(voting)

    def _deliver_candidate(self, result: dict) -> dict:
        """Attach sanitized identities and enforce the final completeness boundary."""
        reason = "selected_complete" if complete_supported_answer(
            result.get("final_response"), self._candidate_problem
        ) else "baseline_without_complete_candidate"
        if reason == "selected_complete":
            if not any(item.result.get("final_response") == result.get("final_response")
                       for item in self._candidate_records):
                self._record_candidate(result, "selected_path")
        elif self._incumbent is not None:
            result = self._with_model_calls(self._incumbent.result, self._model_calls)
            reason = "retained_complete_incumbent"
        answer = result.get("final_response")
        chosen = next((item for item in self._candidate_records
                       if item.result.get("final_response") == answer), None)
        if chosen is not None:
            result.setdefault("trace", []).append({
                "step": "complete_incumbent", "content": {
                    "solve_id": chosen.solve_id, "problem_id": chosen.problem_id,
                    "candidate_id": chosen.candidate_id, "source": chosen.source,
                    "path": chosen.path, "complete": True, "reason": reason,
                    "model_calls": self._model_calls,
                },
            })
        return result
