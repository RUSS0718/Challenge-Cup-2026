import unittest

from reference_skills import classify_skill_subject, select_reference_skill_context
from reference_reasoning_runtime.full_skill_loader import categories


class ReferenceSkillsTest(unittest.TestCase):
    def test_vendored_skill_catalog_has_18_subjects(self):
        self.assertEqual(18, len(categories()))

    def test_subject_classifier_routes_matrix_problem(self):
        route = classify_skill_subject("求矩阵 A 的特征值和特征向量")
        self.assertEqual("高等代数", route["category"])
        self.assertIn("特征值", route["matched_terms"])

    def test_runtime_projection_removes_answer_specific_sections(self):
        context, trace = select_reference_skill_context(
            "求矩阵 A 的特征值并判断是否可对角化", limit=3200
        )
        self.assertEqual("used", trace["status"])
        self.assertTrue(context)
        for marker in ("解法直达", "判分口径", "答案集", "官方答案", "对应习题"):
            self.assertNotIn(marker, context)

    def test_high_similarity_suppresses_skill_context(self):
        context, trace = select_reference_skill_context(
            "求矩阵 A 的特征值", limit=1000, suppress=True
        )
        self.assertEqual("", context)
        self.assertEqual("suppressed_by_high_similarity", trace["status"])


if __name__ == "__main__":
    unittest.main()
