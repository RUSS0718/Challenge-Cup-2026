import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_paired_ab import mcnemar_exact, paired_counts

# PRE0-STATIC-001: pairing is keyed by (dataset_sha256, round, idx, variant).
# Rows must carry an input_file resolvable through --sha-map or on disk.
SHA_MAP = {"synthetic://legacy_ds.jsonl": "b" * 64}


def _row(variant, idx, verdict, round_no=1):
    return {
        "input_file": "synthetic://legacy_ds.jsonl",
        "round": round_no,
        "variant": variant,
        "idx": idx,
        "verdict": verdict,
    }


class McnemarExactTest(unittest.TestCase):
    def test_equal_discordance_is_never_significant(self):
        self.assertEqual(1.0, mcnemar_exact(1, 1))

    def test_known_asymmetric_case_matches_closed_form(self):
        # b=8, c=1 -> p = 2*(C(9,0)+C(9,1))/2^9 = 20/512
        self.assertAlmostEqual(20 / 512, mcnemar_exact(8, 1))

    def test_zero_discordance_is_one(self):
        self.assertEqual(1.0, mcnemar_exact(0, 0))


class PairedCountsTest(unittest.TestCase):
    def test_counts_discordant_pairs_both_directions(self):
        rows = [
            _row("baseline86", 1, "correct"),
            _row("baseline86", 2, "unknown"),
            _row("adaptive_vote", 1, "unknown"),
            _row("adaptive_vote", 2, "correct"),
            _row("baseline86", 3, "correct"),
            _row("adaptive_vote", 3, "correct"),
        ]
        counts = paired_counts(rows, "baseline86", "adaptive_vote", sha_map=SHA_MAP)
        self.assertEqual(1, counts["b"])  # base wrong -> treatment right
        self.assertEqual(1, counts["c"])  # base right -> treatment wrong
        self.assertEqual(2, counts["baseline_correct"])
        self.assertEqual(2, counts["treatment_correct"])

    def test_round_filter_selects_matching_rows(self):
        rows = [
            _row("baseline86", 1, "correct", round_no=1),
            _row("adaptive_vote", 1, "correct", round_no=1),
            _row("baseline86", 2, "correct", round_no=2),
            _row("adaptive_vote", 2, "unknown", round_no=2),
        ]
        counts = paired_counts(rows, "baseline86", "adaptive_vote", round_no=2, sha_map=SHA_MAP)
        self.assertEqual(1, counts["c"])
        self.assertEqual(0, counts["b"])

    def test_same_idx_across_rounds_is_two_pairs_not_one(self):
        rows = [
            _row("baseline86", 1, "unknown", round_no=1),
            _row("adaptive_vote", 1, "correct", round_no=1),
            _row("baseline86", 1, "correct", round_no=2),
            _row("adaptive_vote", 1, "unknown", round_no=2),
        ]
        r1 = paired_counts(rows, "baseline86", "adaptive_vote", round_no=1, sha_map=SHA_MAP)
        r2 = paired_counts(rows, "baseline86", "adaptive_vote", round_no=2, sha_map=SHA_MAP)
        self.assertEqual(1, r1["b"])
        self.assertEqual(1, r2["c"])

    def test_duplicate_key_raises(self):
        rows = [_row("baseline86", 1, "correct"), _row("baseline86", 1, "unknown")]
        with self.assertRaises(SystemExit):
            paired_counts(rows, "baseline86", "adaptive_vote", sha_map=SHA_MAP)

    def test_missing_idx_in_either_arm_raises(self):
        rows = [_row("baseline86", 1, "correct"), _row("adaptive_vote", 2, "correct")]
        with self.assertRaises(SystemExit):
            paired_counts(rows, "baseline86", "adaptive_vote", sha_map=SHA_MAP)

    def test_jsonl_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answers.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in [
                _row("baseline86", 1, "correct"),
                _row("adaptive_vote", 1, "unknown"),
            ]) + "\n", encoding="utf-8")
            loaded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            counts = paired_counts(loaded, "baseline86", "adaptive_vote", sha_map=SHA_MAP)
            self.assertEqual(1, counts["c"])
            self.assertEqual(0, counts["b"])


if __name__ == "__main__":
    unittest.main()
