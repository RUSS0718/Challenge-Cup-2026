"""Tests for historical-document status detection."""

from pathlib import Path
import tempfile
import unittest

from scripts.check_doc_freshness import scan_docs


class DocFreshnessTest(unittest.TestCase):
    """Ensure current-state claims in historical paths carry status metadata."""

    def test_unlabelled_historical_claim_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "docs" / "experiments" / "old.md"
            path.parent.mkdir(parents=True)
            path.write_text("当前默认路径是 old\n", encoding="utf-8")
            self.assertEqual("docs/experiments/old.md", scan_docs(root)[0].path)

    def test_archived_marker_clears_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "docs" / "experiments" / "old.md"
            path.parent.mkdir(parents=True)
            path.write_text("status: archived\n当前默认路径是 old\n", encoding="utf-8")
            self.assertEqual([], scan_docs(root))
