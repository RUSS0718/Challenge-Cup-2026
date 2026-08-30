"""Budgeted ReasoningAgent runtime; all state remains solve-local."""
from __future__ import annotations

import re
import time
from typing import Any

from reasoning_agent.policy import (
    ALTERNATIVE_REASONER_PROMPT,
    ANSWER_ONLY_POLICY_PROMPT,
    AgentConfig,
    CALCULATION_PROMPT,
    DIRECT_REASONER_PROMPT,
    GATED_CONFLICT_INSTRUCTION,
    GATED_PLACEHOLDER_INSTRUCTION,
    GATED_SANITY_INSTRUCTION,
    GATED_TRUNCATION_INSTRUCTION,
    GATED_UNSTRUCTURED_INSTRUCTION,
    GSA_AGGREGATE_PROMPT,
    NUMERIC_ANSWER_FIRST_PROMPT,
    NUMERIC_COD_ANSWER_FIRST_PROMPT,
    POLICY_PROMPT,
    STEP_REVISE_PROMPT,
    STEP_VERIFY_PROMPT,
    SUBMISSION_CONFIG,
    SUBSTITUTION_CHECK_PROMPT,
    TASK_PROMPTS,
    TASK_TYPE_CALCULATION,
    TASK_TYPE_CHOICE,
    TASK_TYPE_FILL_BLANK,
    VERIFIER_PROMPT,
    _NON_NUMERIC_TASK_TYPES,
    classify_problem_type,
)

from reasoning_agent.answers import (
    _GATE_MODE_PRIORITY,
    _has_placeholder_answer,
    _salvage_answer,
    _truncation_signals,
    answer_equivalence,
    extract_answer_first,
    extract_final_answer,
    extract_numeric_answer,
    has_conflicting_explicit_answers,
    is_placeholder_answer,
    normalize_answer,
    parse_structure_f,
    reconstruct_final_response_f,
    run_answer_checks,
)

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
        if self.config.enable_gsa_aggregation and level != "L0":
            # GSA replaces majority voting entirely (independent flag).
            self._gsa_aggregate(problem, level, candidates, trace, budget,
                                task_prompt=self._task_policy_prompt(problem_type),
                                problem_type=problem_type)
        elif self.config.enable_adaptive_voting and level != "L0":
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
            # P1 invalid reduction: salvage a best-effort judgeable answer
            # from rejected responses instead of the guaranteed-zero apology.
            salvaged = ""
            if self.config.enable_failure_salvage:
                salvaged = _salvage_answer(budget.get("rejected_responses", []), problem_type)
                if salvaged:
                    trace.append({"step": "finalize", "status": "salvaged",
                                  "reason": "no_valid_candidate",
                                  "model_calls": budget["used"], "problem_type": problem_type})
                    trace[-1]["diagnostic_reasons"] = list(budget["diagnostic_reasons"])
                    return {"final_response": f"最终答案：{salvaged}",
                            "extracted_answer": salvaged, "trace": trace}
            trace.append({"step":"finalize","status":"fallback","reason":"no_valid_candidate","model_calls":budget["used"],"problem_type":problem_type})
            trace[-1]["diagnostic_reasons"] = list(budget["diagnostic_reasons"])
            return {"final_response":"未能生成有效数学答案。","trace":trace, "extracted_answer": ""}
        best = self._select_candidate(candidates)

        # P1 invalid reduction: a structured=False candidate carries the raw
        # response as its "answer" (F no-answer-block path). Dumping it into
        # final_response is a guaranteed invalid; salvage instead.
        if (
            self.config.enable_failure_salvage
            and not best.get("structured")
            and problem_type in (TASK_TYPE_CALCULATION, TASK_TYPE_FILL_BLANK, TASK_TYPE_CHOICE)
        ):
            salvaged = _salvage_answer(
                [best.get("solution", "")] + budget.get("rejected_responses", []),
                problem_type,
            )
            if salvaged:
                best["answer"] = salvaged
                best["normalized_answer"] = normalize_answer(salvaged)
                trace.append({"step": "finalize", "status": "salvaged",
                              "reason": "unstructured_best",
                              "model_calls": budget["used"], "problem_type": problem_type})

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
            if self.config.enable_re2_reread:
                user_prompt = f"{user_prompt}\n\n请再次仔细阅读题目：\n{problem}"
            if instruction:
                user_prompt = f"{instruction}\n\n{user_prompt}"
            response, error = self._request(prompt, user_prompt, self.config.policy_temperature, max_tokens, budget)
            if response is None:
                self._record_diagnostic(budget, "model_error")
                trace.append(_tr("skipped", candidate_id, reason=error, diagnostic_reason="model_error")); continue
            if self.config.enable_failure_salvage:
                budget.setdefault("rejected_responses", []).append(response)
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
            if self.config.enable_numeric_chain_of_draft:
                return NUMERIC_COD_ANSWER_FIRST_PROMPT
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
            answer = best.get("normalized_answer") or best["answer"]
            if self.config.enable_answer_dual_form and answer.strip():
                # ARH dual form: answer line feeds positional/last-number
                # graders; trailing $\\boxed{}$ feeds last-boxed graders.
                return f"最终答案：{answer}\n$\\boxed{{{answer}}}$"
            return answer
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

    def _gsa_aggregate(
        self, problem: str, level: str,
        candidates: list[dict[str, Any]], trace: list[dict[str, Any]],
        budget: dict[str, Any], task_prompt: str | None = None,
        problem_type: str = TASK_TYPE_CALCULATION,
    ) -> None:
        """GSA: 3 independent samples + 1 generative aggregation call.

        The aggregate answer joins the candidate pool as a new candidate; if
        aggregation fails (no extractable answer), selection falls back to the
        plain consensus ranking over the 3 samples. Compute-matched: 4 calls.
        """
        max_tokens = self._policy_max_tokens(level)
        while len(candidates) < 3:
            top_group_size = self._top_clear_group_size(candidates)
            if top_group_size >= self.config.vote_agree_threshold and candidates:
                status = "consensus_reached"
                break
            if budget["used"] >= budget["limit"]:
                status = "budget_exhausted"
                break
            if self._time_hard_exceeded(budget.get("solve_start")):
                status = "solve_time_budget_exhausted"
                break
            self._generate_candidates(problem, 1, candidates, trace, budget,
                                      max_tokens, task_prompt=task_prompt,
                                      problem_type=problem_type)
        status = "aggregated"
        if candidates:
            listing = "\n".join(
                f"候选{i + 1}答案：{c.get('answer', '')}" for i, c in enumerate(candidates[:3])
            )
            response, _err = self._request(
                GSA_AGGREGATE_PROMPT,
                f"题目：\n{problem}\n\n候选答案：\n{listing}",
                self.config.policy_temperature, max_tokens, budget,
            )
            answer = extract_final_answer(response) if response else ""
            if answer and not is_placeholder_answer(answer):
                candidates.append({
                    "candidate_id": max((c["candidate_id"] for c in candidates), default=-1) + 1,
                    "answer": answer,
                    "normalized_answer": normalize_answer(answer),
                    "solution": response or "",
                    "structured": True,
                    "evidence": [{"source": "gsa_aggregate"}],
                    "verification_status": "unverified",
                    "model_calls_used": 1,
                    "problem_type": problem_type,
                    "explicit_answer_conflict": False,
                })
            else:
                status = "aggregate_unparseable"
        else:
            status = "no_samples"
        trace.append({"step": "gsa_aggregate", "status": status,
                      "samples": len(candidates),
                      "model_calls": budget["used"]})

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

            # Hetero k5 (port of runtime 18f4f5a): the first resample in the
            # vote loop uses AlternativeReasoner, later ones DirectReasoner;
            # early-consensus sequence is therefore Direct → Alternative → Direct.
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

        # ── Re-verify; fail-closed (2b4ba30 semantics, PRE0-PARITY-001 §3). ──
        # The 3bed2b7 merge regressed to main's keep-on-undecided behavior;
        # this restores the work-branch contract: any undecided re-verify
        # (budget exhausted, request failure, malformed output) rolls back.
        def _rollback_revision() -> None:
            best["solution"] = saved["solution"]
            best["answer"] = saved["answer"]
            best["normalized_answer"] = saved["normalized_answer"]

        if budget["used"] >= budget["limit"]:
            trace.append({"step": "reverify", "status": "skipped",
                          "reason": "model_call_budget_exhausted"})
            _rollback_revision()
            return

        re_errors, re_gaps, re_conclusive = self._verify_solution(
            problem, revised, trace, budget, step_label="reverify"
        )
        if re_conclusive is None:
            # Request failure/empty response is fail-closed: keep the original.
            _rollback_revision()
        elif re_conclusive is False:
            trace.append({"step": "reverify", "status": "inconclusive", "error_count": 0, "gap_count": 0})
            _rollback_revision()
        elif re_errors or re_gaps:
            trace.append({"step": "reverify", "status": "fail",
                          "error_count": len(re_errors), "gap_count": len(re_gaps)})
            _rollback_revision()
        else:
            trace.append({"step": "reverify", "status": "ok", "error_count": 0, "gap_count": 0})

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
