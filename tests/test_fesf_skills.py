import json
import tempfile
import unittest
from pathlib import Path

from reasoning_agent.fork_evidence_synthesize_finish import SkillRegistry, evaluate_exact_request


class SkillDirectoryAcceptanceTest(unittest.TestCase):
    def test_registry_has_unique_valid_metadata_and_single_body(self):
        registry = SkillRegistry(strict=True)
        items = registry.metadata()
        self.assertEqual(["exact-evaluation"], [item.name for item in items])
        description = items[0].description.casefold()
        for phrase in ("bounded exact", "unbounded search", "exact_eval", "restricted"):
            self.assertIn(phrase, description)
        self.assertEqual("", registry.load_body("missing")[1])
        metadata, body = registry.load_body("exact-evaluation")
        self.assertIsNotNone(metadata)
        self.assertIn("Preconditions", body)
        self.assertIn("Required artifacts", body)
        self.assertIn("EXACT_EVAL", body)
        self.assertNotIn("__import__", body)

    def test_illegal_registry_path_and_duplicate_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "good").mkdir()
            (root / "good" / "SKILL.md").write_text(
                "---\nname: good\ndescription: Use when bounded exact evaluation is needed; do not use for unbounded work. Produce EXACT_EVAL with the host tool.\n---\nBody\n",
                encoding="utf-8",
            )
            (root / "other").mkdir()
            (root / "other" / "SKILL.md").write_text(
                "---\nname: good\ndescription: Use when bounded exact evaluation is needed; do not use for unbounded work. Produce EXACT_EVAL with the host tool.\n---\nBody\n",
                encoding="utf-8",
            )
            registry = SkillRegistry(root, strict=False)
            self.assertTrue(registry.errors)
            with self.assertRaises(ValueError):
                SkillRegistry(root, strict=True)

    def test_overlong_skill_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "long"
            folder.mkdir()
            name = "a" * 65
            (folder / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Use when bounded exact evaluation is needed; do not use for unbounded work. Produce EXACT_EVAL with the host tool.\n---\nBody\n",
                encoding="utf-8",
            )
            registry = SkillRegistry(root, strict=False)
            self.assertTrue(registry.errors)
            with self.assertRaises(ValueError):
                SkillRegistry(root, strict=True)

    def test_generic_strategy_skill_does_not_require_exact_eval_tool_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "factor-check"
            folder.mkdir()
            (folder / "SKILL.md").write_text(
                "---\nname: factor-check\n"
                "description: Use when a factorisation route is applicable; "
                "do not use for geometry or unbounded search.\n---\n"
                "# Strategy\nKeep factors visible.\n",
                encoding="utf-8",
            )
            registry = SkillRegistry(root, strict=True)
            self.assertEqual(["factor-check"], [item.name for item in registry.metadata()])
            self.assertIn("factor-check", registry.catalog_text())
            self.assertIn("Keep factors visible", registry.load_body("factor-check")[1])

    def test_catalog_exposes_all_registered_skills_under_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(4):
                folder = root / f"skill-{index}"
                folder.mkdir()
                (folder / "SKILL.md").write_text(
                    f"---\nname: skill-{index}\n"
                    "description: Use when this strategy applies; do not use when it does not.\n"
                    "---\nBody\n",
                    encoding="utf-8",
                )
            catalog = SkillRegistry(root, strict=True).catalog_text()
            for index in range(4):
                self.assertIn(f"skill-{index}", catalog)

    def test_skill_cases_are_jsonl_and_tool_outputs_are_serializable(self):
        path = Path(__file__).resolve().parents[1] / "reasoning_agent" / "fesf_skills" / "exact-evaluation" / "cases.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(rows), len({row["case_id"] for row in rows}))
        for row in rows:
            result = evaluate_exact_request(row["request"])
            json.dumps(result, ensure_ascii=False)
            self.assertIn(result["status"], {"EXACT", "REFUTED", "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
