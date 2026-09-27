"""Verify that local diagnostics preserve failure causes without model text."""

import unittest

from reasoning_agent.diagnostic_trace import summarize_agent_trace
from scripts.run_instrumented_diagnostic_smoke import (
    _build_report,
    _request_summary,
    attach_agent_stages_to_requests,
)


class DiagnosticTraceTest(unittest.TestCase):
    """Check that stage summaries retain causes without answer or prompt text."""

    def test_summarize_agent_trace_keeps_decisions_and_drops_content(self):
        """Keep route/evidence/final states while excluding raw candidate data."""
        trace = [
            {
                "stage": "route",
                "method": "typed_contract_adaptive_deep_v1",
                "reason": "typed_deep_contract",
                "target": "harness",
                "lane": "deep",
                "answer_type": "scalar",
                "problem_contract": {
                    "answer_shape": "single_numeric",
                    "reasoning_risk": "structured",
                    "route_confidence": "medium",
                    "raw_prompt": "private prompt",
                },
            },
            {
                "stage": "evidence_ledger",
                "states": [
                    {
                        "state": "candidate_a",
                        "reason": "no_typed_complete_candidate",
                        "answer_shape": "single_numeric",
                        "status": "typed_missing",
                    }
                ],
                "candidates": [{"candidate_id": "A", "status": "untyped", "value": "private answer"}],
                "typed_parses": [{"state": "candidate_a", "status": "typed_missing", "raw": "private answer"}],
                "calls": [{"stage": "deep_primary", "status": "error", "error_category": "timeout", "raw_prompt": "private prompt"}],
                "budget": {"calls": 1, "call_limit": 3, "records": [{"stage": "deep_primary", "status": "error", "error_category": "timeout"}]},
            },
            {"stage": "finalize", "status": "abstained", "reason": "deep_typed_evidence_incomplete"},
            {"stage": "legacy_backend", "status": "returned", "legacy_trace": [{"stage": "D", "status": "failed", "error_category": "timeout", "response": "private answer"}]},
        ]

        summary = summarize_agent_trace(trace)

        self.assertEqual("typed_deep_contract", summary[0]["reason"])
        self.assertEqual("medium", summary[0]["problem_contract"]["route_confidence"])
        self.assertEqual("no_typed_complete_candidate", summary[1]["states"][0]["reason"])
        self.assertEqual("deep_primary", summary[1]["calls"][0]["stage"])
        self.assertEqual("timeout", summary[1]["budget"]["records"][0]["error_category"])
        self.assertEqual("abstained", summary[2]["status"])
        self.assertEqual("timeout", summary[3]["legacy_trace"][0]["error_category"])
        serialized = str(summary)
        self.assertNotIn("private prompt", serialized)
        self.assertNotIn("private answer", serialized)

    def test_request_summary_keeps_timeout_and_http_failure_denominators(self):
        """Aggregate failed attempts separately from successful completions."""
        events = [
            {"status": "error", "error_category": "timeout", "http_status": None},
            {"status": "error", "error_category": "http_status", "http_status": 429},
            {
                "status": "success",
                "finish_reason": "stop",
                "request_model_id": "intern-s2",
                "response_model_id": "Intern-S2",
                "prompt_tokens": 12,
                "completion_tokens": 4,
                "total_tokens": 16,
            },
        ]

        summary = _request_summary(events)

        self.assertEqual(3, summary["attempts"])
        self.assertEqual(1, summary["successful_responses"])
        self.assertEqual(2, summary["failed_attempts"])
        self.assertEqual({"timeout": 1, "http_status": 1}, summary["error_categories"])
        self.assertEqual({"429": 1}, summary["http_statuses"])
        self.assertEqual({"stop": 1}, summary["finish_reasons"])
        self.assertEqual(4, summary["completion_tokens"])
        self.assertEqual(0, summary["response_model_mismatches"])

    def test_report_keeps_unknown_and_stage_request_failure_counts(self):
        """Keep route, finalization, and timeout outcomes in the denominator."""
        record = {
            "item_id": "fixture-1",
            "set_id": "set_a",
            "status": "ok",
            "duration_seconds": 31.0,
            "final_response_class": "unknown",
            "native": {"verdict": "invalid"},
            "contract": {"verdict": "invalid"},
            "route_summary": {"reason": "typed_deep_contract"},
            "finalize_summary": {"status": "abstained"},
            "request_summary": {"successful_responses": 0, "failed_attempts": 1},
            "request_diagnostics": [
                {"status": "error", "error_category": "timeout", "duration_seconds": 30.0}
            ],
        }

        report = _build_report([record], {"run_id": "fixture-run", "model_id": "intern-s2", "profile": "submission"})

        self.assertEqual(1, report["items"])
        self.assertEqual(1, report["unknown_final"])
        self.assertEqual({"typed_deep_contract": 1}, report["route_reasons"])
        self.assertEqual({"abstained": 1}, report["finalize_statuses"])
        self.assertEqual({"timeout": 1}, report["requests"]["error_categories"])
        self.assertEqual(1, report["by_set"]["set_a"]["items"])
        self.assertEqual(1, report["items_with_recorded_failure_category"])

    def test_request_events_map_to_harness_and_legacy_stages(self):
        """Correlate per-call HTTP failures with the stage's call number."""
        trace = [
            {
                "stage": "evidence_ledger",
                "calls": [{"call_number": 1, "stage": "deep_primary", "status": "error"}],
            },
            {
                "stage": "legacy_backend",
                "legacy_trace": [
                    {"stage": "analyze", "status": "failed", "model_calls": 2},
                ],
            },
        ]
        requests = [
            {"logical_call_index": 0, "status": "error", "error_category": "timeout"},
            {"logical_call_index": 1, "status": "error", "error_category": "timeout"},
        ]

        mapped = attach_agent_stages_to_requests(requests, trace)

        self.assertEqual("deep_primary", mapped[0]["agent_stage"])
        self.assertEqual("analyze", mapped[1]["agent_stage"])
