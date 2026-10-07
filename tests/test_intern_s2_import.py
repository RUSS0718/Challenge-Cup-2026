"""Integration checks for the unchanged imported agent and local Intern client."""

import json
import hashlib
from pathlib import Path
import os
import unittest
from unittest.mock import patch

import requests
from llm_client import InternChatClient
from user_agent import ReasoningAgent


class ImportIntegrationTest(unittest.TestCase):
    """Verify HTTP thinking switches and the imported agent entry contract."""

    def client(self):
        """Build a local client without a real credential or model request."""
        with patch.dict(os.environ, {"INTERN_API_KEY": "test", "INTERN_MODEL": "intern-s2"}):
            return InternChatClient(retry=1, thinking_mode=True)

    def response(self):
        """Return a completed answer usable by the imported agent verifier."""
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({
            "model": "intern-s2",
            "choices": [{"message": {"content": "最终答案：2"}, "finish_reason": "stop"}],
        }, ensure_ascii=False).encode()
        return response

    def test_source_snapshot_hashes(self):
        """All imported files must match the frozen source manifest byte for byte."""
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "docs/releases/intern-s-math-agent-s2-20261007/source_sha256.json").read_text(encoding="utf-8"))
        self.assertEqual(10, len(manifest["files"]))
        for name, digest in manifest["files"].items():
            with self.subTest(file=name):
                self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())

    def test_strict_three_argument_client_limitation(self):
        """Record the unchanged source incompatibility instead of claiming platform readiness."""
        class StrictClient:
            """Expose only the documented minimum platform contract."""

            def chat(self, messages, temperature, max_tokens):
                """Return a result only if the request meets the minimum contract."""
                return "最终答案：2"

        result = ReasoningAgent(client=StrictClient()).solve("计算 1+1", {})
        self.assertEqual("client_error", result["trace"][0]["content"]["status"])
        self.assertEqual("TypeError", result["trace"][0]["content"]["error_type"])

    def test_local_runner_default_config_and_independent_agents(self):
        """The runner must construct the new config and separate mutable state per problem."""
        import argparse
        import asyncio
        import tempfile
        import main

        agents = []

        async def capture(agent, item, manager, semaphore):
            """Capture agent identities without calling a provider."""
            agents.append(agent)

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "input.jsonl"
            source.write_text('{"idx": 1, "problem": "计算 1+1"}\n{"idx": 2, "problem": "计算 2+2"}\n', encoding="utf-8")
            args = argparse.Namespace(input_file=str(source), output_dir=str(Path(temporary) / "outputs"), profile="submission")
            with patch("main.InternChatClient", return_value=self.client()), patch("main.process_item", side_effect=capture):
                asyncio.run(main.run(args))
        self.assertEqual(2, len(agents))
        self.assertIsNot(agents[0], agents[1])
        self.assertEqual("implementations.candidates.sl_v3_cont.user_agent", type(agents[0].config).__module__)

    def test_request_local_thinking_mode(self):
        """A per-request false switch must override a true client default."""
        client = self.client()
        with patch("llm_client.requests.post", return_value=self.response()) as post:
            client.chat([], thinking_mode=False)
        self.assertIs(False, json.loads(post.call_args.kwargs["data"])["thinking_mode"])
        self.assertIs(True, client.thinking_mode)

    def test_explicit_reasoning_mode_wins(self):
        """Existing explicit reasoning modes retain their precedence."""
        client = self.client()
        with patch("llm_client.requests.post", return_value=self.response()) as post:
            client.chat([], thinking_mode=False, reasoning_mode="on")
        self.assertIs(True, json.loads(post.call_args.kwargs["data"])["thinking_mode"])

    def test_imported_agent_reaches_intern_s2(self):
        """Construction, solve, HTTP payload, and JSON output must work together."""
        client = self.client()
        with patch("llm_client.requests.post", return_value=self.response()) as post:
            result = ReasoningAgent(client=client).solve("计算 1+1", {})
        self.assertTrue(post.called, result)
        self.assertEqual("intern-s2", json.loads(post.call_args.kwargs["data"])["model"])
        self.assertIn("2", result["final_response"])
        json.dumps(result, ensure_ascii=False)

    def test_client_failure_returns_serializable_fallback(self):
        """An unavailable provider must still yield the required output field."""
        client = self.client()
        with patch("llm_client.requests.post", side_effect=requests.Timeout):
            result = ReasoningAgent(client=client).solve("计算 1+1", {})
        self.assertTrue(result["final_response"])
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
