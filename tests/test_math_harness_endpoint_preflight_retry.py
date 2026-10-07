import unittest

from scripts.run_math_harness_endpoint_preflight_retry import _build_report


class MathHarnessEndpointPreflightRetryTest(unittest.TestCase):
    def test_precheck_failure_stops_before_full_probe(self):
        report = _build_report(
            [{"status": "model_error", "response_present": False, "finish_reason": ""}],
            [],
            elapsed_seconds=1.0,
            stopped_after_error=True,
            full_run_started=False,
        )
        self.assertTrue(report["void"])
        self.assertIn("endpoint_availability_precheck_failed", report["void_reasons"])
        self.assertIn("full_extraction_probe_not_started", report["void_reasons"])
        self.assertEqual(1, report["remote_model_calls"])


if __name__ == "__main__":
    unittest.main()
