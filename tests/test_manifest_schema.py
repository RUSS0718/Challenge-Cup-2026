"""Tests for evaluation manifest provenance fields."""

import unittest

from reasoning_agent.manifest_schema import normalise_manifest, validate_manifest


class ManifestSchemaTest(unittest.TestCase):
    """Cover compatible defaults and strict promotion checks."""

    def test_legacy_manifest_keeps_unknown_scope_without_inventing_evidence(self):
        data = normalise_manifest(
            {
                "run_id": "r",
                "config": "c",
                "dataset": "d",
                "git_commit": None,
                "started_at": "now",
                "status": "completed",
            }
        )
        self.assertEqual("unknown", data["evaluation_scope"])
        self.assertIsNone(data["official_evaluation"])
        self.assertEqual([], validate_manifest(data))

    def test_strict_manifest_requires_hashes_and_clean_tree(self):
        data = normalise_manifest(
            {
                "run_id": "r",
                "config": "c",
                "dataset": "d",
                "git_commit": "a" * 40,
                "dataset_sha256": "b" * 64,
                "started_at": "now",
                "status": "completed",
                "evaluation_scope": "local_replay",
                "manifest_schema_version": 2,
                "official_evaluation": False,
                "working_tree_dirty": False,
            }
        )
        self.assertEqual([], validate_manifest(data, strict=True))

    def test_official_flag_requires_official_scope(self):
        data = normalise_manifest(
            {"run_id": "r", "config": "c", "official_evaluation": True}
        )
        self.assertIn(
            "invalid:official_evaluation_requires_official_scope",
            validate_manifest(data),
        )
