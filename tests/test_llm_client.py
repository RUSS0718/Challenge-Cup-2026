import contextlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
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

    def test_default_model_is_intern_s2_and_snapshot_is_safe(self):
        with _patch_env(INTERN_API_KEY="test", remove=["INTERN_MODEL"]):
            client = InternChatClient()
        snapshot = client.diagnostic_snapshot()
        self.assertEqual("intern-s2", snapshot["model"])
        self.assertNotIn("test", str(snapshot))

    def test_request_diagnostics_capture_retry_without_prompt_or_response(self):
        """Keep retry metadata while excluding prompts, answers, and errors."""
        import requests

        response = requests.Response()
        response.status_code = 200
        response._content = (
            b'{"id":"request-1","model":"intern-s2",'
            b'"choices":[{"message":{"content":"private answer"},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":17,"completion_tokens":3,"total_tokens":20}}'
        )
        with _patch_env(INTERN_API_KEY="private key", INTERN_MODEL="intern-s2"):
            client = InternChatClient(timeout=4, retry=2)
        with patch(
            "llm_client.requests.post",
            side_effect=[requests.Timeout("private failure detail"), response],
        ) as post:
            self.assertEqual("private answer", client.chat([{"role": "user", "content": "private prompt"}], 0.1, 64))

        self.assertEqual(2, post.call_count)
        self.assertEqual(2, len(client.request_diagnostics))
        failed, succeeded = client.request_diagnostics
        self.assertEqual("error", failed["status"])
        self.assertEqual("timeout", failed["error_category"])
        self.assertEqual("Timeout", failed["error_type"])
        self.assertEqual(1, failed["attempt_index"])
        self.assertEqual("success", succeeded["status"])
        self.assertEqual(2, succeeded["attempt_index"])
        self.assertEqual("intern-s2", succeeded["request_model_id"])
        self.assertEqual("intern-s2", succeeded["response_model_id"])
        self.assertEqual("stop", succeeded["finish_reason"])
        self.assertEqual(17, succeeded["prompt_tokens"])
        self.assertEqual(3, succeeded["completion_tokens"])
        self.assertEqual(20, succeeded["total_tokens"])
        serialized = str(client.request_diagnostics)
        for private_value in ("private key", "private prompt", "private answer", "private failure detail"):
            self.assertNotIn(private_value, serialized)

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
        self.assertEqual("http_status", client.request_diagnostics[0]["error_category"])
        self.assertEqual(401, client.request_diagnostics[0]["http_status"])

    def test_thinking_mode_is_optional_and_added_only_when_configured(self):
        """Keep inherited mode behavior when no request override is given."""
        with _patch_env(INTERN_API_KEY="test", INTERN_THINKING_MODE="false"):
            client = InternChatClient(timeout=1, retry=1)
        import requests
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
        with patch("llm_client.requests.post", return_value=response) as post:
            self.assertEqual("ok", client.chat([], 0.0, 1))
        self.assertFalse(post.call_args.kwargs["data"].find(b'"thinking_mode": false') < 0)

    def test_request_mode_overrides_default_without_mutating_it(self):
        """Send explicit OFF and ON values per request while retaining the default."""
        import requests

        response = requests.Response()
        response.status_code = 200
        response._content = b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
        with _patch_env(INTERN_API_KEY="test", remove=["INTERN_THINKING_MODE"]):
            client = InternChatClient(timeout=1, retry=1, thinking_mode=True)
        with patch("llm_client.requests.post", return_value=response) as post:
            self.assertEqual("ok", client.chat([], 0.0, 1, reasoning_mode="off"))
            self.assertEqual("ok", client.chat([], 0.0, 1, reasoning_mode="on"))

        payloads = [json.loads(call.kwargs["data"]) for call in post.call_args_list]
        self.assertEqual([False, True], [payload["thinking_mode"] for payload in payloads])
        self.assertTrue(client.thinking_mode)
        self.assertEqual(["off", "on"], [event["reasoning_mode"] for event in client.request_diagnostics])
        self.assertEqual([False, True], [event["thinking_mode"] for event in client.request_diagnostics])

    def test_concurrent_request_modes_do_not_cross_contaminate(self):
        """Keep two calls on one client isolated when their requests overlap."""
        import requests

        from threading import Barrier

        barrier = Barrier(2)

        def post(_url, *, headers, data, timeout):
            """Wait for the peer request and echo its resolved boolean mode."""
            payload = json.loads(data)
            barrier.wait(timeout=2)
            response = requests.Response()
            response.status_code = 200
            content = "on" if payload["thinking_mode"] else "off"
            response._content = (
                f'{{"choices":[{{"message":{{"content":"{content}"}},'
                f'"finish_reason":"stop"}}]}}'
            ).encode("utf-8")
            return response

        with _patch_env(INTERN_API_KEY="test", remove=["INTERN_THINKING_MODE"]):
            client = InternChatClient(timeout=2, retry=1)
        with patch("llm_client.requests.post", side_effect=post):
            with ThreadPoolExecutor(max_workers=2) as pool:
                off = pool.submit(client.chat, [], 0.0, 1, reasoning_mode="off")
                on = pool.submit(client.chat, [], 0.0, 1, reasoning_mode="on")
                results = {off.result(timeout=3), on.result(timeout=3)}

        self.assertEqual({"off", "on"}, results)
        self.assertIsNone(client.thinking_mode)
        diagnostics = {
            event["reasoning_mode"]: event["thinking_mode"]
            for event in client.request_diagnostics
        }
        self.assertEqual({"off": False, "on": True}, diagnostics)


if __name__ == "__main__":
    unittest.main()
