import unittest
from pathlib import Path

from scripts.run_math_deep_formation_probe import (
    EXPECTED_ITEMS,
    SELECTION_IDS,
    _load_items,
    build_report,
    formation_config,
)


class DeepFormationProbeTest(unittest.TestCase):
    def test_selection_is_prompt_safe_and_deep_routed(self):
        items = _load_items(Path(
            "sample_data/external_hard_sets/set_a_olymmath_hard.jsonl"
        ))
        self.assertEqual(list(SELECTION_IDS), [item["item_id"] for item in items])
        self.assertEqual(EXPECTED_ITEMS, len(items))
        self.assertTrue(all(item["contract"]["reasoning_risk"] in {"deep", "structured"} for item in items))
        self.assertTrue(all("answer" not in item and "gold" not in item for item in items))

    def test_profile_is_deep_and_bank_off(self):
        config = formation_config()
        self.assertTrue(config.enable_constraint_fit_harness)
        self.assertTrue(config.enable_constraint_fit_deep_lane)
        self.assertFalse(config.enable_temporary_answer_bank)
        self.assertEqual("off", config.harness_bank_mode)
        self.assertEqual(3, config.harness_deep_max_model_calls)
        self.assertEqual(16384, config.harness_total_token_budget)

    def test_first_three_zero_is_a_failed_stop_gate(self):
        rows = [
            {
                "item_id": item_id,
                "typed_complete": False,
                "model_error": True,
                "timeout": True,
                "route_ok": True,
                "bank_violation": False,
                "output_contract_ok": True,
                "budget_violated": False,
                "model_calls": 1,
                "requested_tokens": 8192,
                "finish_reasons": ["missing"],
                "duration_seconds": 1200.0,
            }
            for item_id in SELECTION_IDS[:3]
        ]
        report = build_report(
            rows,
            1200.0,
            final=True,
            stopped_early=True,
            stop_reason="first_three_typed_complete_zero",
        )
        self.assertTrue(report["first_three_stop_triggered"])
        self.assertFalse(report["formation_gate"]["pass"])
        self.assertEqual(3, report["model_errors"])
        self.assertEqual(3, report["timeout_count"])


if __name__ == "__main__":
    unittest.main()
