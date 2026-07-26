import os
import unittest
from unittest.mock import patch

from llm_client import ChatClientError, InternChatClient


class InternChatClientTest(unittest.TestCase):
    def test_missing_key_has_sanitized_category(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ChatClientError, "configuration") as context:
                InternChatClient()
        self.assertEqual("configuration", context.exception.category)

    def test_timeout_has_sanitized_category(self):
        with patch.dict(os.environ, {"INTERN_API_KEY": "test"}, clear=True):
            client = InternChatClient(timeout=1, retry=1)
        with patch("llm_client.requests.post", side_effect=__import__("requests").Timeout):
            with self.assertRaisesRegex(ChatClientError, "timeout") as context:
                client.chat([], 0.0, 1)
        self.assertEqual("timeout", context.exception.category)


if __name__ == "__main__":
    unittest.main()
