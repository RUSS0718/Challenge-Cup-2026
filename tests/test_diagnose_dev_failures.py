import unittest

from scripts.diagnose_dev_failures import classify_response


class DiagnoseDevelopmentFailuresTest(unittest.TestCase):
    def test_missing_final_marker_is_classified_without_claiming_a_math_error(self):
        result = classify_response("Thinking Process:\n1. calculate 1 +", "2")

        self.assertEqual("missing_final_marker", result["failure_category"])
        self.assertTrue(result["basis"])
        self.assertFalse(result["correct"])
        self.assertTrue(result["starts_thinking_process"])

    def test_explicit_wrong_and_correct_answers_are_distinguished(self):
        self.assertEqual(
            "incorrect_final_answer",
            classify_response("最终答案：3", "2")["failure_category"],
        )
        self.assertEqual("correct", classify_response("最终答案：2", "2")["failure_category"])

    def test_format_placeholder_is_not_counted_as_a_math_answer(self):
        result = classify_response('Output format: "最终答案：[Answer]".', "2")

        self.assertEqual("format_placeholder_echo", result["failure_category"])
        self.assertFalse(result["correct"])

    def test_request_error_has_a_separate_category(self):
        result = classify_response(None, "2", error="timeout")

        self.assertEqual("request_error:timeout", result["failure_category"])
        self.assertFalse(result["correct"])


if __name__ == "__main__":
    unittest.main()
