"""PRE0-STATIC-001 unit tests: pairing contract, health gate, cluster test.

Complements scripts/pre0_static_selftest.py (which also exercises the real
local datasets); these cases stay hermetic via sha maps and tmp files.
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_paired_ab import (
    detect_dataset_overlap,
    item_cluster_counts,
    mcnemar_exact,
    paired_counts,
    resolve_dataset_sha256,
    window_void_state,
)

SHA_MAP = {"synthetic://ds.jsonl": "c" * 64}


def _row(round_no, variant, idx, verdict, result_status="ok", diagnostics=None, input_file="synthetic://ds.jsonl"):
    return {
        "input_file": input_file,
        "round": round_no,
        "variant": variant,
        "idx": idx,
        "verdict": verdict,
        "result_status": result_status,
        "diagnostic_reasons": diagnostics or [],
    }


class ResolveDatasetShaTest(unittest.TestCase):
    def test_sha_map_short_circuits_disk(self):
        self.assertEqual("a" * 64, resolve_dataset_sha256("any/path.jsonl", {"any/path.jsonl": "a" * 64}))

    def test_unresolvable_fails_closed(self):
        with self.assertRaises(SystemExit):
            resolve_dataset_sha256("no/such/file.jsonl")

    def test_real_file_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ds.jsonl"
            path.write_bytes(b"hello\n")  # binary: avoids Windows text-mode \r\n translation
            import hashlib

            self.assertEqual(hashlib.sha256(b"hello\n").hexdigest(), resolve_dataset_sha256(str(path)))


class HealthGateTest(unittest.TestCase):
    def _rows(self, errors_left: int, errors_right: int) -> list[dict]:
        rows = []
        for variant, errors in (("left", errors_left), ("right", errors_right)):
            for idx in range(100):
                is_error = idx < errors
                rows.append(_row(1, variant, idx, "unknown",
                                 result_status="error" if is_error else "ok",
                                 diagnostics=["model_error"] if is_error else []))
        return rows

    def test_nine_percent_is_healthy(self):
        state = window_void_state(self._rows(9, 9), ["left", "right"], expected_n=100, sha_map=SHA_MAP)
        self.assertFalse(state["void"])
        self.assertIsNone(state["void_reason"])

    def test_eleven_percent_voids_with_error_rate_reason(self):
        state = window_void_state(self._rows(11, 9), ["left", "right"], expected_n=100, sha_map=SHA_MAP)
        self.assertTrue(state["void"])
        self.assertEqual("error_rate_above_threshold", state["void_reason"])
        self.assertFalse(state["breaker_tripped"])

    def test_breaker_reason_is_distinct_field_value(self):
        state = window_void_state(self._rows(0, 0), ["left", "right"], expected_n=100, sha_map=SHA_MAP,
                                  breaker_report={"void": True, "consecutive_failures_max": 8})
        self.assertTrue(state["breaker_tripped"])
        self.assertEqual("consecutive_model_errors", state["breaker_reason"])
        self.assertFalse(state["error_rate_void"])
        self.assertTrue(state["void"])

    def test_incomplete_window_voids(self):
        rows = self._rows(0, 0)[:-1]
        state = window_void_state(rows, ["left", "right"], expected_n=100, sha_map=SHA_MAP)
        self.assertTrue(state["void"])
        self.assertEqual("incomplete_window", state["void_reason"])

    def test_error_row_detection_covers_both_markers(self):
        rows = [
            _row(1, "left", 0, "unknown", result_status="error"),
            _row(1, "left", 1, "unknown", diagnostics=["model_error"]),
            _row(1, "right", 0, "correct"),
            _row(1, "right", 1, "correct"),
        ]
        counts = paired_counts(rows, "left", "right", expected_n=2, sha_map=SHA_MAP)
        self.assertEqual(2, counts["baseline_errors"])
        self.assertEqual(0, counts["treatment_errors"])


class ClusterTest(unittest.TestCase):
    def test_cluster_sign_test_hand_case(self):
        rows = []
        # item0: treat wins both rounds; item1: baseline wins both; item2: round1 treat, round2 tie
        outcomes = {
            (0, 1): (False, True), (0, 2): (False, True),
            (1, 1): (True, False), (1, 2): (True, False),
            (2, 1): (False, True), (2, 2): (False, False),
        }
        for (idx, round_no), (base_hit, treat_hit) in outcomes.items():
            rows.append(_row(round_no, "ctl", idx, "correct" if base_hit else "unknown"))
            rows.append(_row(round_no, "treat", idx, "correct" if treat_hit else "unknown"))
        cluster = item_cluster_counts(rows, "ctl", "treat", sha_map=SHA_MAP)
        self.assertEqual((2, 1, 0), (cluster["b"], cluster["c"], cluster["ties"]))
        self.assertEqual(mcnemar_exact(2, 1), cluster["sign_test_exact_p"])
        self.assertEqual(2, cluster["baseline_cluster_correct"])
        self.assertEqual(3, cluster["treatment_cluster_correct"])

    def test_round_set_mismatch_fails_closed(self):
        rows = [
            _row(1, "ctl", 0, "correct"),
            _row(1, "treat", 0, "correct"),
            _row(2, "treat", 0, "correct"),  # treatment covers a round baseline does not
        ]
        with self.assertRaises(SystemExit):
            item_cluster_counts(rows, "ctl", "treat", sha_map=SHA_MAP)

    def test_ties_excluded_from_sign_test(self):
        rows = []
        for round_no in (1, 2):
            rows.append(_row(round_no, "ctl", 0, "correct"))
            rows.append(_row(round_no, "treat", 0, "correct"))
        cluster = item_cluster_counts(rows, "ctl", "treat", sha_map=SHA_MAP)
        self.assertEqual((0, 0, 1), (cluster["b"], cluster["c"], cluster["ties"]))
        self.assertEqual(1.0, cluster["sign_test_exact_p"])


class OverlapTest(unittest.TestCase):
    def test_overlap_detected_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.jsonl"
            b = Path(tmp) / "b.jsonl"
            a.write_text(json.dumps({"problem": "  Solve x+1=2  "}) + "\n"
                         + json.dumps({"problem": "second"}) + "\n", encoding="utf-8")
            b.write_text(json.dumps({"problem": "SOLVE X+1=2"}) + "\n"
                         + json.dumps({"problem": "third"}) + "\n", encoding="utf-8")
            report = detect_dataset_overlap([a, b])
            self.assertEqual(1, report["total_overlap_pairs"])
            self.assertEqual(3, report["union_unique"])


if __name__ == "__main__":
    unittest.main()
