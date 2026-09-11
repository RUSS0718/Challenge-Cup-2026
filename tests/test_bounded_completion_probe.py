import json
import tempfile
from pathlib import Path
import unittest

from scripts.run_bounded_completion_probe import build_config, interface_checks, load_items, run


class BoundedCompletionProbeScriptTest(unittest.TestCase):
    def test_dry_fixture_is_prompt_safe_and_config_is_complete(self):
        items = load_items()
        config = build_config(items)
        self.assertEqual(3, len(items))
        self.assertEqual("off", config.bank_mode)
        self.assertEqual(0, config.max_retries)
        config.validate()

    def test_zero_model_acceptance_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run(Path(directory))
            self.assertTrue(report["zero_model_acceptance"])
            self.assertEqual(0, report["dispatched_requests"])
            self.assertTrue(report["capacity_checks"]["configuration_validated"])
            saved = json.loads((Path(directory) / "zero_model_report.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["zero_model_calls"])

    def test_interface_check_does_not_construct_network_client(self):
        checks = interface_checks()
        self.assertTrue(checks["public_client_contract_ok"])
        self.assertFalse(checks["real_client_constructed"])


if __name__ == "__main__":
    unittest.main()
