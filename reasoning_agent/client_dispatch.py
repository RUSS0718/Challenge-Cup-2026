"""Dispatch model requests across the public and extended client contracts.

The official runner guarantees only ``client.chat(messages, temperature,
max_tokens)``.  Local clients may additionally accept request-local reasoning
and timeout controls, so this module keeps that optional extension at one
small, auditable seam.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.inference_policy import ReasoningMode


def call_chat_compat(
    client: Any,
    messages: Any,
    temperature: float,
    max_tokens: int,
    *,
    reasoning_mode: ReasoningMode = "inherit",
    timeout_seconds: int | None = None,
) -> tuple[Any, bool]:
    """Call a client and fall back only when optional keywords are unsupported.

    Returns the raw client response and whether the three-argument public
    contract was used after an ``unexpected keyword argument`` signature
    failure.  The fallback is a same-request compatibility retry: callers keep
    one logical budget reservation and no network retry is attempted for other
    ``TypeError`` instances.
    """
    request_kwargs: dict[str, Any] = {}
    if reasoning_mode != "inherit":
        request_kwargs["reasoning_mode"] = reasoning_mode
    if timeout_seconds is not None:
        request_kwargs["timeout_seconds"] = timeout_seconds
    if not request_kwargs:
        return client.chat(messages, temperature, max_tokens), False
    try:
        return client.chat(messages, temperature, max_tokens, **request_kwargs), False
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc).lower():
            raise
        return client.chat(messages, temperature, max_tokens), True


__all__ = ["call_chat_compat"]
