"""Regression tests for the public model-client dispatch seam."""

import unittest

from reasoning_agent.client_dispatch import call_chat_compat


class ExtendedClient:
    """Accept the local request-control extension."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def chat(self, messages, temperature, max_tokens, **kwargs):
        """Record controls and return a stable response."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs,
            }
        )
        return "extended"


class StrictClient:
    """Implement exactly the public three-argument contract."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, temperature, max_tokens):
        """Count the compatible call and return a stable response."""
        del messages, temperature, max_tokens
        self.calls += 1
        return "public"


class InternalTypeErrorClient:
    """Accept keywords but fail inside the client implementation."""

    def chat(self, messages, temperature, max_tokens, **kwargs):
        """Raise a non-signature error that must not be retried."""
        del messages, temperature, max_tokens, kwargs
        raise TypeError("client implementation failed")


class ClientDispatchTest(unittest.TestCase):
    """Keep request-control compatibility narrow and fail-closed."""

    def test_extended_client_receives_optional_controls_once(self):
        client = ExtendedClient()

        response, used_fallback = call_chat_compat(
            client,
            [{"role": "user", "content": "x"}],
            0.2,
            64,
            reasoning_mode="off",
            timeout_seconds=12,
        )

        self.assertEqual("extended", response)
        self.assertFalse(used_fallback)
        self.assertEqual(1, len(client.calls))
        self.assertEqual("off", client.calls[0]["reasoning_mode"])
        self.assertEqual(12, client.calls[0]["timeout_seconds"])

    def test_strict_public_client_falls_back_without_extra_controls(self):
        client = StrictClient()

        response, used_fallback = call_chat_compat(
            client,
            [{"role": "user", "content": "x"}],
            0.2,
            64,
            reasoning_mode="off",
            timeout_seconds=12,
        )

        self.assertEqual("public", response)
        self.assertTrue(used_fallback)
        self.assertEqual(1, client.calls)

    def test_internal_type_error_is_not_retried(self):
        with self.assertRaisesRegex(TypeError, "implementation failed"):
            call_chat_compat(
                InternalTypeErrorClient(),
                [],
                0.2,
                64,
                reasoning_mode="off",
            )


if __name__ == "__main__":
    unittest.main()
