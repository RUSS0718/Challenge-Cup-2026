import json
import unittest
from pathlib import Path

from scripts.build_length_pressure_set import build_pressure_set
from scripts.validate_length_pressure_set import validate


def _source_item(idx: int) -> dict:
    return {
        "idx": idx,
        "task_type": "calculation",
        "subject": "离散数学",
        "source": "historical_fixture",
        "source_url": "https://example.invalid/source",
        "source_ref": "fixture",
        "adaptation": "fixture",
        "problem": f"计算 {idx}+1。",
        "answer": str(idx + 1),
        "verification": "fixture answer",
        "is_long": 1,
        "is_multi_domain": 0,
    }


class LengthPressureSetTest(unittest.TestCase):
    def test_build_pressure_set_uses_per_item_evidence_and_strips_answers(self):
        source = [_source_item(idx) for idx in range(20)]
        telemetry = [
            {
                "idx": idx,
                "completion_tokens": 3072,
                "ceiling_tokens": 4096,
                "finish_reason": "length",
                "variant": "legacy_4k_k5",
            }
            for idx in range(20)
        ]

        result = build_pressure_set(
            source,
            telemetry,
            telemetry_source="docs/history.jsonl",
            target_size=20,
        )

        self.assertEqual(20, len(result))
        self.assertTrue(all("answer" not in item and "verification" not in item for item in result))
        self.assertEqual(
            {
                "completion_tokens": 3072,
                "ceiling_tokens": 4096,
                "completion_fraction": 0.75,
                "finish_reason": "length",
                "variant": "legacy_4k_k5",
                "telemetry_source": "docs/history.jsonl",
            },
            result[0]["length_evidence"],
        )


    def test_build_pressure_set_rejects_missing_or_below_threshold_evidence(self):
        source = [_source_item(idx) for idx in range(20)]
        telemetry = [
            {"idx": idx, "completion_tokens": 2048, "ceiling_tokens": 4096}
            for idx in range(20)
        ]

        with self.assertRaisesRegex(ValueError, "fewer than target size"):
            build_pressure_set(source, telemetry, telemetry_source="history.jsonl", target_size=20)


    def test_validate_rejects_answer_leakage_and_invalid_length_evidence(self):
        with self.subTest("invalid dataset"):
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "pressure.jsonl"
                path.write_text(
                    json.dumps(
                        {
                            "idx": 1,
                            "problem": "计算 1+1。",
                            "task_type": "calculation",
                            "source": "fixture",
                            "source_ref": "fixture",
                            "length_evidence": {
                                "completion_tokens": 2048,
                                "ceiling_tokens": 4096,
                                "completion_fraction": 0.5,
                                "telemetry_source": "history.jsonl",
                            },
                            "answer": "2",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                errors = validate(path, min_size=1, max_size=1)

                self.assertIn("answer_field_present:1", errors)
                self.assertIn("completion_below_threshold:1", errors)
