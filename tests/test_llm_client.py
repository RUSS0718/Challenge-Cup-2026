import contextlib
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


if __name__ == "__main__":
    unittest.main()
