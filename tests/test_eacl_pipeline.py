"""Regression tests for the evaluation-aligned GRH control-plane pipeline."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from reasoning_agent.eacl_contracts import EACLConfig
from reasoning_agent.eacl_pipeline import EACLControlPlane
from scripts.run_eacl import (
    _load_existing_answers,
    _load_manifest,
    _metrics_from_answers,
    _percentile,
    _validate_resume_manifest,
)


class ScriptedClient:
    """Minimal public-contract client with optional reasoning-mode support."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, **kwargs):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "kwargs": kwargs,
            }
        )
        if not self.responses:
            raise AssertionError("scripted client exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class LegacyClient:
    """Public-contract client without request-scoped reasoning support."""

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def chat(self, messages, temperature, max_tokens):
        self.calls += 1
        return self.response


class EACLControlPlaneTests(unittest.TestCase):
    """Cover bounded calls, host verification, and ARH serialization."""

    def test_verified_candidate_is_serialized_without_extra_model_call(self):
        client = ScriptedClient(["FINAL_CANDIDATE: 120\n理由：直接计算"])
        result = EACLControlPlane(client).solve("计算 5!", {})

        self.assertEqual("120", result["extracted_answer"])
        self.assertIn("最终答案：120", result["final_response"])
        self.assertIn(r"\boxed{120}", result["final_response"])
        self.assertEqual(1, result["model_calls"])
        self.assertEqual("PASS", result["decision"]["verification"])

    def test_invalid_first_response_uses_independent_route_b(self):
        client = ScriptedClient([
            "推理被截断，没有形成答案",
            "FINAL_CANDIDATE: 7\n理由：代入核对",
        ])
        result = EACLControlPlane(client).solve("计算 7", {})

        self.assertEqual("7", result["extracted_answer"])
        self.assertEqual(2, result["model_calls"])
        self.assertEqual("route_b", result["decision"]["selected_route"])
        route_b_prompt = client.calls[1]["messages"][1]["content"]
        self.assertNotIn("推理被截断", route_b_prompt)

    def test_bounded_recovery_extracts_existing_answer_as_third_call(self):
        client = ScriptedClient([
            "推理被截断",
            "仍然没有 marker，但片段接近完成",
            "FINAL_CANDIDATE: 11",
        ])
        result = EACLControlPlane(client).solve("求 n", {})

        self.assertEqual("11", result["extracted_answer"])
        self.assertEqual(3, result["model_calls"])
        self.assertEqual("recovery", result["decision"]["selected_route"])
        self.assertIn("已有片段", client.calls[2]["messages"][1]["content"])

    def test_deterministic_failure_does_not_allow_wrong_candidate(self):
        client = ScriptedClient([
            "FINAL_CANDIDATE: 121",
            "FINAL_CANDIDATE: 120",
        ])
        result = EACLControlPlane(client).solve("计算 5!", {})

        self.assertEqual("120", result["extracted_answer"])
        self.assertEqual("route_b", result["decision"]["selected_route"])
        self.assertEqual("PASS", result["decision"]["verification"])
        self.assertEqual(2, result["model_calls"])

    def test_conflicting_unverified_candidates_fail_closed(self):
        client = ScriptedClient([
            "FINAL_CANDIDATE: 8",
            "FINAL_CANDIDATE: 9",
        ])
        config = EACLConfig(allow_thinking_on=False)
        result = EACLControlPlane(client, config=config).solve("求 n", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("ABSTAIN", result["decision"]["action"])
        self.assertEqual(2, result["model_calls"])

    def test_call_cap_and_unknown_are_reported(self):
        client = ScriptedClient([RuntimeError("down")])
        result = EACLControlPlane(client, config=EACLConfig(max_model_calls=1)).solve("求 n", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual(1, result["model_calls"])
        self.assertEqual("ABSTAIN", result["decision"]["action"])
        self.assertTrue(result["trace"])

    def test_route_b_refutation_fails_closed(self):
        client = ScriptedClient(["没有形成候选", "FINAL_CANDIDATE: 121"])
        result = EACLControlPlane(client).solve("计算 5!", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("ABSTAIN", result["decision"]["action"])
        self.assertEqual("FAIL", result["decision"]["verification"])

    def test_unmarked_unverified_terminal_line_is_not_submitted(self):
        client = ScriptedClient(["121"])
        result = EACLControlPlane(client, config=EACLConfig(max_model_calls=1)).solve("求 n", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("ABSTAIN", result["decision"]["action"])

    def test_equal_refuted_candidates_fail_closed(self):
        client = ScriptedClient(["FINAL_CANDIDATE: 121", "FINAL_CANDIDATE: 121"])
        result = EACLControlPlane(client).solve("计算 5!", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("ABSTAIN", result["decision"]["action"])
        self.assertEqual("FAIL", result["decision"]["verification"])

    def test_legacy_client_is_called_once_per_logical_request(self):
        client = LegacyClient("FINAL_CANDIDATE: 120")
        result = EACLControlPlane(client).solve("计算 5!", {})

        self.assertEqual(1, client.calls)
        self.assertEqual(1, result["model_calls"])

    def test_proof_candidate_is_not_serialized_as_scalar_answer(self):
        client = ScriptedClient(["FINAL_CANDIDATE: x^2+y^2=1"])
        result = EACLControlPlane(client).solve("证明 x^2+y^2=1", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("", result["extracted_answer"])

    def test_expression_contract_accepts_signed_latex_fraction(self):
        client = ScriptedClient(["FINAL_CANDIDATE: -\\dfrac{1}{8}"])
        result = EACLControlPlane(client).solve(
            "Find the numerical value of the residue.",
            {},
        )

        self.assertEqual("-1/8", result["extracted_answer"])
        self.assertIn(r"\boxed{-1/8}", result["final_response"])

    def test_runner_percentile_is_deterministic(self):
        self.assertEqual(3.0, _percentile([1.0, 2.0, 4.0], 0.75))

    def test_runner_loads_last_durable_checkpoint_and_recomputes_metrics(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "answers.jsonl"
            path.write_text(
                '{"idx": 1, "status": "success", "final_response": "UNKNOWN", "model_calls": 2}\n'
                'not-json\n'
                '{"idx": 1, "status": "success", "final_response": "7", "model_calls": 1}\n',
                encoding="utf-8",
            )
            loaded = _load_existing_answers(path)

        self.assertEqual("7", loaded["1"]["final_response"])
        metrics = _metrics_from_answers(list(loaded.values()))
        self.assertEqual(1, metrics["completed"])
        self.assertEqual(1, metrics["model_calls"])
        self.assertEqual(1, metrics["records"])

    def test_runner_manifest_loader_rejects_malformed_json_without_raising(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run_manifest.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual({}, _load_manifest(path))

    def test_runner_resume_contract_is_immutable(self):
        manifest = {
            "dataset_sha256": "abc",
            "thinking_on": True,
            "off_finalizer": False,
            "max_model_calls": 3,
            "total_token_budget": 12288,
        }
        _validate_resume_manifest(
            manifest,
            dataset_sha256="abc",
            thinking_on=True,
            off_finalizer=False,
            max_model_calls=3,
            total_token_budget=12288,
        )
        with self.assertRaisesRegex(ValueError, "resume_config_mismatch:max_model_calls"):
            _validate_resume_manifest(
                manifest,
                dataset_sha256="abc",
                thinking_on=True,
                off_finalizer=False,
                max_model_calls=2,
                total_token_budget=12288,
            )


if __name__ == "__main__":
    unittest.main()
