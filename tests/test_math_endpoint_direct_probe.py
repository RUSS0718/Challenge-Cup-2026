import unittest

from scripts.run_math_endpoint_direct_probe import CASES, REPETITIONS


class MathEndpointDirectProbeTest(unittest.TestCase):
    def test_probe_is_minimal_and_bounded(self):
        self.assertEqual(2, len(CASES))
        self.assertEqual(3, REPETITIONS)
        self.assertEqual({"plain_text", "basic_math"}, {case for case, _ in CASES})


if __name__ == "__main__":
    unittest.main()
