import contextlib
import os
import time
import unittest
from unittest.mock import patch

from llm_client import ChatClientError, InternChatClient


@contextlib.contextmanager
def _patch_env(remove=(), **set_vals):
    """Set/remove env vars without patch.dict, which copies the whole os.environ
    and trips on >32K injected vars (e.g. ACC_PRODUCT_CONFIG_V3)."""
    keys = set(remove) | set(set_vals)
    saved = {k: os.environ.get(k) for k in keys}
    for k in remove:
        os.environ.pop(k, None)
    for k, v in set_vals.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class InternChatClientTest(unittest.TestCase):
    def test_missing_key_has_sanitized_category(self):
        with _patch_env(remove=["INTERN_API_KEY"]):
            with self.assertRaisesRegex(ChatClientError, "configuration") as context:
                InternChatClient()
        self.assertEqual("configuration", context.exception.category)

    def test_timeout_has_sanitized_category(self):
        with _patch_env(INTERN_API_KEY="test"):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", side_effect=__import__("requests").Timeout):
            with self.assertRaisesRegex(ChatClientError, "timeout") as context:
                client.chat([], 0.0, 1)
        self.assertEqual("timeout", context.exception.category)

    def test_default_model_is_explicit_397b_and_snapshot_is_safe(self):
        with _patch_env(INTERN_API_KEY="test", remove=["INTERN_MODEL"]):
            client = InternChatClient()
        snapshot = client.diagnostic_snapshot()
        self.assertEqual("intern-s2-preview-397b", snapshot["model"])
        self.assertNotIn("test", str(snapshot))

    def test_tls_error_has_distinct_sanitized_category(self):
        with _patch_env(INTERN_API_KEY="test"):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", side_effect=__import__("requests").exceptions.SSLError("bad cert")):
            with self.assertRaisesRegex(ChatClientError, "tls") as context:
                client.chat([], 0.0, 1)
        self.assertEqual("tls", context.exception.category)
        self.assertEqual("SSLError", context.exception.detail)

    def test_http_error_snapshot_keeps_only_status(self):
        with _patch_env(INTERN_API_KEY="test"):
            client = InternChatClient(timeout=1, retry=1)
        import requests
        response = requests.Response()
        response.status_code = 401
        error = requests.HTTPError(response=response)
        with patch("llm_client.requests.post", side_effect=error):
            with self.assertRaises(ChatClientError) as context:
                client.chat([], 0.0, 1)
        self.assertEqual("http_status", context.exception.category)
        self.assertEqual("HTTPError:401", context.exception.detail)
        self.assertEqual("HTTPError:401", client.diagnostic_snapshot()["last_failure_type"])

    def test_thinking_mode_is_optional_and_added_only_when_configured(self):
        with _patch_env(INTERN_API_KEY="test", INTERN_THINKING_MODE="false"):
            client = InternChatClient(timeout=1, retry=1)
        import requests
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
        with patch("llm_client.requests.post", return_value=response) as post:
            self.assertEqual("ok", client.chat([], 0.0, 1))
        self.assertFalse(post.call_args.kwargs["data"].find(b'"thinking_mode": false') < 0)


if __name__ == "__main__":
    unittest.main()


class RequestDeadlineTest(unittest.TestCase):
    """PRE0-EXT-001 amendment A1: opt-in wall-clock deadline kills stalls."""

    def test_stalled_request_raises_timeout_and_counts(self):
        import requests

        with _patch_env(INTERN_API_KEY="test", INTERN_REQUEST_DEADLINE_SECONDS="0.2"):
            client = InternChatClient(timeout=30, retry=1)
        with patch("llm_client.requests.post", side_effect=lambda *a, **k: time.sleep(1.5)):
            with self.assertRaisesRegex(ChatClientError, "timeout"):
                client.chat(messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(1, client.deadline_exceeded_count)

    def test_fast_request_passes_through(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            "usage": {"completion_tokens": 1},
        }
        with _patch_env(INTERN_API_KEY="test", INTERN_REQUEST_DEADLINE_SECONDS="5"):
            client = InternChatClient(timeout=30, retry=1)
        with patch("llm_client.requests.post", return_value=response):
            self.assertEqual("ok", client.chat(messages=[{"role": "user", "content": "hi"}]))
        self.assertEqual(0, client.deadline_exceeded_count)
        self.assertEqual(["stop"], client.finish_reasons)

    def test_deadline_defaults_off(self):
        with _patch_env(INTERN_API_KEY="test", remove=["INTERN_REQUEST_DEADLINE_SECONDS"]):
            client = InternChatClient(timeout=30, retry=1)
        self.assertIsNone(client.request_deadline)
        self.assertEqual(0, client.deadline_exceeded_count)


if __name__ == "__main__":
    unittest.main()
