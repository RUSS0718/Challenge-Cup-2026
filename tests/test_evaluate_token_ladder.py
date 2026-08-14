import os
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from scripts.evaluate_token_ladder import gate_check, summarize


class _Resp:
    def __init__(self, content, finish_reason):
        self._content, self._fr = content, finish_reason

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}, "finish_reason": self._fr}]}


def _rec(**overrides):
    base = {
        "idx": 0,
        "main_finish_reason": "stop",
        "retry_finish_reason": None,
        "had_conditional_retry": False,
        "final_response_nonempty": True,
        "finalization_status": "selected",
        "model_calls": 1,
        "verdict": "correct",
        "latency_seconds": 1.0,
    }
    base.update(overrides)
    return base


class TokenLadderTest(unittest.TestCase):
    def test_finish_reason_recorded_on_success(self):
        with patch.dict(os.environ, {"INTERN_API_KEY": "test"}, clear=True):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", return_value=_Resp("x", "length")):
            self.assertEqual("x", client.chat([], 0.0, 1024))
        self.assertEqual(["length"], client.finish_reasons)

    def test_summarize_length_rate_and_marker_coverage(self):
        records = [
            _rec(),  # clean main call
            _rec(main_finish_reason="length", retry_finish_reason="stop",
                 had_conditional_retry=True, model_calls=2),
            _rec(main_finish_reason="length", retry_finish_reason="length",
                 had_conditional_retry=True, model_calls=2,
                 final_response_nonempty=False, finalization_status="fallback"),
        ]
        report = summarize(records)
        self.assertEqual(3, report["dataset_size"])
        # main length rate: 2 of 3 main calls truncated
        self.assertAlmostEqual(2 / 3, report["main_finish_reason_length_rate"])
        # marker coverage: 1 of 3 questions had a clean main answer
        self.assertAlmostEqual(1 / 3, report["answer_marker_coverage"])
        # nonempty: 2 of 3
        self.assertAlmostEqual(2 / 3, report["nonempty_final_response_rate"])
        # calls: 1 + 2 + 2 = 5
        self.assertEqual(5, report["total_model_calls"])

    def test_gate_check_fail_on_truncation(self):
        records = [_rec(main_finish_reason="length", retry_finish_reason="length",
                        had_conditional_retry=True, model_calls=2)]
        report = summarize(records)
        report["token"] = 1024
        gate = gate_check(report)
        self.assertFalse(gate["gate2_passed"])
        self.assertFalse(gate["checks"]["gate2_length_le_20pct"])

    def test_gate_check_pass_on_clean_run(self):
        records = [_rec() for _ in range(10)]
        report = summarize(records)
        gate = gate_check(report)
        self.assertTrue(gate["gate1_passed"])
        self.assertTrue(gate["gate2_passed"])
        self.assertEqual(0.0, gate["invalid_rate"])


if __name__ == "__main__":
    unittest.main()
