import contextlib
import os
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from scripts.archive.evaluate_token_ladder import gate_check, summarize


@contextlib.contextmanager
def _env(**kwargs):
    """Temporarily set env vars without patch.dict, which copies the whole
    os.environ and trips on >32K injected vars (e.g. ACC_PRODUCT_CONFIG_V3)."""
    saved = {k: os.environ.get(k) for k in kwargs}
    for k, v in kwargs.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Resp:
    def __init__(self, content, finish_reason):
        self._content, self._fr = content, finish_reason

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}, "finish_reason": self._fr}],
            "usage": {"completion_tokens": len(self._content)},
        }


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
        "output_tokens": 100,
        "main_completion_tokens": 100,
        "retry_completion_tokens": 0,
        "total_completion_tokens": 100,
        "main_latency_seconds": 1.0,
        "retry_latency_seconds": None,
        "thinking_leak": False,
        "answer_marker_present": True,
        "final_response_thinking": False,
    }
    base.update(overrides)
    return base


class TokenLadderTest(unittest.TestCase):
    def test_finish_reason_recorded_on_success(self):
        with _env(INTERN_API_KEY="test", INTERN_API_BASE="http://x", INTERN_RETRY_COUNT="1"):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", return_value=_Resp("x", "length")):
            self.assertEqual("x", client.chat([], 0.0, 1024))
        self.assertEqual(["length"], client.finish_reasons)

    def test_completion_tokens_and_raw_content_recorded(self):
        with _env(INTERN_API_KEY="test", INTERN_API_BASE="http://x", INTERN_RETRY_COUNT="1"):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", return_value=_Resp("最终答案：42", "stop")):
            self.assertEqual("最终答案：42", client.chat([], 0.0, 1024))
        self.assertEqual([len("最终答案：42")], client.completion_tokens)
        self.assertEqual(["最终答案：42"], client.raw_contents)

    def test_summarize_thinking_and_marker_rates(self):
        from scripts.archive.evaluate_token_ladder import _detect_thinking, _detect_answer_marker
        self.assertTrue(_detect_thinking("Thinking Process: 1. Analyze the problem"))
        self.assertFalse(_detect_thinking("推导过程如下：由定义得"))
        self.assertTrue(_detect_answer_marker("最终答案：3"))
        self.assertFalse(_detect_answer_marker("推导过程如下"))
        records = [
            _rec(output_tokens=120, thinking_leak=True, answer_marker_present=True),
            _rec(output_tokens=80, thinking_leak=False, answer_marker_present=False),
        ]
        report = summarize(records)
        self.assertEqual(0.5, report["thinking_leak_rate"])
        self.assertEqual(0.5, report["answer_marker_rate"])
        self.assertEqual(100, report["average_output_tokens"])
        self.assertEqual(120, report["p95_output_tokens"])

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

    def test_latency_recorded_per_call(self):
        with _env(INTERN_API_KEY="test", INTERN_API_BASE="http://x", INTERN_RETRY_COUNT="1"):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", return_value=_Resp("x", "stop")):
            self.assertEqual("x", client.chat([], 0.0, 1024))
        self.assertEqual(1, len(client.latencies))
        self.assertGreaterEqual(client.latencies[0], 0.0)

    def test_summarize_token_cost_metrics(self):
        records = [
            _rec(main_completion_tokens=500, retry_completion_tokens=0, total_completion_tokens=500),
            _rec(main_completion_tokens=400, retry_completion_tokens=300, total_completion_tokens=700,
                 had_conditional_retry=True, model_calls=2),
        ]
        report = summarize(records)
        self.assertEqual(500, report["main_completion_tokens_p95"])
        self.assertEqual(700, report["total_completion_tokens_p95"])
        self.assertEqual(1200, report["total_completion_tokens_sum"])
        # retry token 占比 = 300 / 1200 = 0.25
        self.assertAlmostEqual(0.25, report["retry_token_share"])
        # estimated wall time = avg_latency * ceil(112/3) = 1.0 * 38
        self.assertAlmostEqual(38.0, report["estimated_112_wall_time_seconds"])
        self.assertAlmostEqual(38.0, report["estimated_112_wall_time_upper_seconds"])


if __name__ == "__main__":
    unittest.main()
