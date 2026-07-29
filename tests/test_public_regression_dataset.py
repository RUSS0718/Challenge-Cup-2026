from collections import Counter
from pathlib import Path
import unittest

from scripts.evaluate_dev import (
    EXPECTED_SUBJECT_COUNTS,
    load_items,
    validate_regression_items,
)


DATASET = Path(__file__).resolve().parents[1] / "sample_data" / "public_regression_112.jsonl"


class PublicRegressionDatasetTest(unittest.TestCase):
    def test_dataset_has_exact_public_distribution_and_traceability(self):
        items = load_items(DATASET)

        self.assertEqual([], validate_regression_items(items))
        self.assertEqual(Counter(EXPECTED_SUBJECT_COUNTS), Counter(item["subject"] for item in items))
        self.assertTrue(all(item["adaptation"] == "original_parameterized" for item in items))


if __name__ == "__main__":
    unittest.main()
