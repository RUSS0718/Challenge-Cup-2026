import unittest

from pot_executor import execute_program
from substitution_check import check_substitution


class SubstitutionCheckTest(unittest.TestCase):
    def test_twenty_constraint_programs_map_true_and_false_to_evidence(self):
        for expected in range(20):
            with self.subTest(expected=expected):
                supported = check_substitution(f"print(candidate == {expected})", str(expected))
                refuted = check_substitution(f"print(candidate == {expected})", str(expected + 1))

                self.assertEqual("SUPPORTED", supported["claim_status"])
                self.assertEqual("REFUTED", refuted["claim_status"])
                self.assertEqual("substitution_check", supported["source"])

    def test_candidate_is_passed_as_environment_value_not_source_text(self):
        result = check_substitution("print(candidate == 42)", "42); import os")

        self.assertNotEqual("SUPPORTED", result.get("claim_status"))
        self.assertEqual("substitution_check", result["source"])

    def test_executor_rejects_rebinding_the_candidate_environment(self):
        result = execute_program(
            "candidate = 42\nprint(candidate == 42)",
            environment={"candidate": 42},
        )

        self.assertEqual("UNSUPPORTED", result["status"])
        self.assertEqual("unsupported:environment_rebind", result["reason"])

    def test_existing_escape_hatches_never_produce_supported_evidence(self):
        programs = (
            '__import__("os").system("dir")',
            'eval("1 + 1")',
            'exec("print(42)")',
            "import os\nprint(candidate == 42)",
            "print(candidate.__class__)",
        )
        for program in programs:
            with self.subTest(program=program):
                result = check_substitution(program, "42")
                self.assertNotEqual("SUPPORTED", result.get("claim_status"))
