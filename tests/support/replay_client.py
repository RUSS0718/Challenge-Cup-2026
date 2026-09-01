"""Replay-only client for BTCS tests; it implements the public chat method."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class ReplayError(Exception):
    def __init__(self, category: str, status_code: int | None = None) -> None:
        super().__init__(category)
        self.category = category
        if status_code is not None:
            self.status_code = status_code


class ReplayClient:
    """Return a fixed transcript and record only test-local call metadata."""

    def __init__(self, responses: Iterable[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if not self._responses:
            raise ReplayError("replay_exhausted")
        response = self._responses.pop(0)
        if isinstance(response, dict) and "error" in response:
            category = str(response["error"])
            status_code = {"rate_limit": 429, "503": 503}.get(category)
            raise ReplayError(category, status_code)
        if isinstance(response, BaseException):
            raise response
        return response


def load_cases() -> dict[str, list[Any]]:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "btcs_transcripts.jsonl"
    cases: dict[str, list[Any]] = {}
    for line in fixture.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            cases[str(record["name"])] = list(record["responses"])
    return cases
