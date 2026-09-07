import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reasoning_agent.error_notebook import (
    NotebookEntry,
    validate_notebook_file,
    validate_notebook_rows,
)


def valid_row(entry_id="domain-check"):
    return {
        "entry_id": entry_id,
        "pattern": "symbolic denominator appears without a domain condition",
        "domain": "algebra",
        "mistake": "treating a rational expression as defined everywhere",
        "corrective_rule": "record a non-zero denominator obligation before simplification",
        "use_when": "a denominator contains a symbolic variable",
        "do_not_use": "a denominator is a known non-zero constant",
        "source_trace_ids": ["trace-001"],
        "validation": {"status": "draft", "held_out_total": 0, "held_out_pass": 0},
        "tags": ["domain"],
    }


class ErrorNotebookTest(unittest.TestCase):
    def test_entry_round_trip_and_valid_draft(self):
        entry = NotebookEntry(
            entry_id="finite-check",
            pattern="finite sample mistaken for proof",
            domain="proof",
            mistake="no universal coverage argument",
            corrective_rule="treat finite tests as evidence only",
            use_when="the claim quantifies over all values",
            do_not_use="the problem asks only for a listed finite set",
            source_trace_ids=("trace-002",),
            validation_status="validated",
            held_out_total=3,
            held_out_pass=3,
        )
        issues = validate_notebook_rows([entry.as_dict()])
        self.assertEqual((), issues)

    def test_forbidden_fields_and_duplicate_ids_are_rejected(self):
        row = valid_row()
        row["gold_answer"] = "secret"
        issues = validate_notebook_rows([row, valid_row()])
        codes = [issue.code for issue in issues]
        self.assertIn("forbidden_field", codes)
        self.assertIn("duplicate_entry_id", codes)

    def test_validated_entry_requires_held_out_cases(self):
        row = valid_row("needs-holdout")
        row["validation"] = {"status": "validated", "held_out_total": 0, "held_out_pass": 0}
        codes = [issue.code for issue in validate_notebook_rows([row])]
        self.assertIn("validated_without_holdout", codes)

    def test_file_validator_reports_bad_json_and_cli_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notebook.jsonl"
            path.write_text(json.dumps(valid_row(), ensure_ascii=False) + "\nnot-json\n", encoding="utf-8")
            report = validate_notebook_file(path)
            self.assertFalse(report.valid)
            self.assertEqual(1, report.entry_count)
            self.assertIn("json_invalid", [issue.code for issue in report.issues])

    def test_file_duplicate_reports_source_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notebook.jsonl"
            payload = "\n".join(
                json.dumps(valid_row(), ensure_ascii=False) for _ in range(2)
            )
            path.write_text(payload + "\n", encoding="utf-8")
            report = validate_notebook_file(path)
            duplicate = next(
                issue for issue in report.issues if issue.code == "duplicate_entry_id"
            )
            self.assertEqual(2, duplicate.line)

    def test_cli_exit_codes_valid_and_invalid_files(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "validate_error_notebook.py"
        with tempfile.TemporaryDirectory() as directory:
            valid_path = Path(directory) / "valid.jsonl"
            invalid_path = Path(directory) / "invalid.jsonl"
            valid_path.write_text(json.dumps(valid_row(), ensure_ascii=False) + "\n", encoding="utf-8")
            invalid_path.write_text("not-json\n", encoding="utf-8")
            valid_run = subprocess.run(
                [sys.executable, str(script), str(valid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            invalid_run = subprocess.run(
                [sys.executable, str(script), str(invalid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, valid_run.returncode, valid_run.stdout + valid_run.stderr)
            self.assertEqual(1, invalid_run.returncode, invalid_run.stdout + invalid_run.stderr)

    def test_raw_problem_prompt_response_and_answer_fields_are_rejected(self):
        for field in ("problem", "raw_problem", "prompt", "response", "answer", "gold", "solution"):
            with self.subTest(field=field):
                row = valid_row(f"bad-{field}")
                row[field] = "secret-original"
                codes = [issue.code for issue in validate_notebook_rows([row])]
                self.assertIn("forbidden_field", codes)

    def test_twelve_jsonl_cases_cover_valid_and_invalid_shapes(self):
        from tests.support.host_loop_foundations_cases import NOTEBOOK_VALID_ROWS

        script = Path(__file__).resolve().parents[1] / "scripts" / "validate_error_notebook.py"
        with tempfile.TemporaryDirectory() as directory:
            valid_path = Path(directory) / "valid.jsonl"
            valid_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in NOTEBOOK_VALID_ROWS) + "\n",
                encoding="utf-8",
            )
            valid_run = subprocess.run(
                [sys.executable, str(script), str(valid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, valid_run.returncode, valid_run.stdout + valid_run.stderr)

            invalid_specs = [
                {"missing": True},
                {"unknown_field": True},
                {"gold": "secret"},
                {"raw_json": "not-json"},
                {"duplicate": True},
                {"too_long": True},
                {"skill": "ExactEval"},
                {"holdout": True},
                {"problem": "raw problem"},
            ]
            self.assertGreaterEqual(len(NOTEBOOK_VALID_ROWS) + len(invalid_specs), 12)
            for index, spec in enumerate(invalid_specs):
                path = Path(directory) / f"invalid-{index}.jsonl"
                if spec.get("raw_json"):
                    path.write_text("not-json\n", encoding="utf-8")
                elif spec.get("duplicate"):
                    path.write_text(
                        "\n".join(json.dumps(valid_row(), ensure_ascii=False) for _ in range(2)) + "\n",
                        encoding="utf-8",
                    )
                else:
                    row = valid_row(f"invalid-{index}")
                    if spec.get("missing"):
                        row.pop("pattern")
                    if spec.get("unknown_field"):
                        row["unexpected"] = "x"
                    if "gold" in spec:
                        row["gold"] = spec["gold"]
                    if spec.get("too_long"):
                        row["pattern"] = "p" * 2000
                    if spec.get("skill"):
                        row["skill_name"] = spec["skill"]
                    if spec.get("holdout"):
                        row["validation"] = {"status": "validated", "held_out_total": 1, "held_out_pass": 2}
                    if spec.get("problem"):
                        row["problem"] = spec["problem"]
                    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
                run = subprocess.run(
                    [sys.executable, str(script), str(path)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(1, run.returncode, path.name + run.stdout + run.stderr)

    def test_runtime_solve_only_lazy_imports_read_only_temporary_bank(self):
        import ast
        import sys
        from pathlib import Path as PathType

        from user_agent import AgentConfig, ReasoningAgent

        source = PathType(__file__).resolve().parents[1] / "user_agent.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("error_notebook", imported)
        notebook_imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and "error_notebook" in (node.module or "")
        }
        self.assertEqual(
            {"reasoning_agent.error_notebook.temporary_answer_bank"},
            notebook_imports,
        )
        self.assertFalse(any("schema" in module for module in notebook_imports))

        class Scripted:
            def chat(self, messages, temperature, max_tokens):
                return "FINAL: 7"

        with tempfile.TemporaryDirectory() as directory:
            notebook_dir = Path(directory) / "error_notebook"
            notebook_dir.mkdir()
            before = {name: module for name, module in sys.modules.items() if "error_notebook" in name}
            agent = ReasoningAgent(Scripted(), AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False))
            result = agent.solve("计算 3+4", {})
            self.assertEqual("7", result["final_response"])
            self.assertEqual([], list(notebook_dir.iterdir()))
            after = {name: module for name, module in sys.modules.items() if "error_notebook" in name}
            self.assertEqual(set(before), set(after))


if __name__ == "__main__":
    unittest.main()
