import json
import os
import time
from typing import Dict, List

import requests


DEFAULT_API_BASE = "https://chat.intern-ai.org.cn/api/v1/chat/completions"
DEFAULT_MODEL = "intern-s2-preview"


class ChatClientError(RuntimeError):
    """A sanitized failure category suitable for trace and local reports."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class InternChatClient:
    """Small OpenAI-compatible chat client for the competition sample."""

    def __init__(
        self,
        timeout: int | None = None,
        retry: int | None = None,
    ) -> None:
        raw_api_key = os.environ.get("INTERN_API_KEY")
        if not raw_api_key:
            raise ChatClientError("configuration")
        self.authorization = (
            raw_api_key if raw_api_key.startswith("Bearer ") else f"Bearer {raw_api_key}"
        )
        self.api_base = os.environ.get("INTERN_API_BASE", DEFAULT_API_BASE)
        self.model = os.environ.get("INTERN_MODEL", DEFAULT_MODEL)
        self.timeout = timeout if timeout is not None else _positive_int_env("INTERN_TIMEOUT_SECONDS", 30)
        self.retry = retry if retry is not None else _positive_int_env("INTERN_RETRY_COUNT", 1)
        # P0.1: per-call finish_reason log (local diagnostic only; the official
        # client keeps its own counters).  Appended in call order for serial runs.
        self.finish_reasons: List[str] = []
        # 13.2 A/B diagnostics: per-call completion token count and raw content,
        # so the evaluator can measure thinking-leak rate / marker rate / output
        # tokens without re-requesting.  Local-only; the official client is
        # untouched and never sees these lists.
        self.completion_tokens: List[int] = []
        self.raw_contents: List[str] = []

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.authorization,
        }

        last_category = "request"
        for attempt in range(self.retry):
            try:
                response = requests.post(
                    self.api_base,
                    headers=headers,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                self.finish_reasons.append(choice.get("finish_reason") or "")
                usage = data.get("usage") or {}
                try:
                    self.completion_tokens.append(int(usage.get("completion_tokens") or 0))
                except (TypeError, ValueError):
                    self.completion_tokens.append(0)
                content = choice["message"]["content"]
                self.raw_contents.append(content if isinstance(content, str) else "")
                return content
            except requests.Timeout:
                last_category = "timeout"
            except requests.ConnectionError:
                last_category = "connectivity"
            except requests.HTTPError:
                last_category = "http_status"
            except (KeyError, TypeError, ValueError):
                last_category = "invalid_response"
            except requests.RequestException:
                last_category = "request"
                if attempt + 1 < self.retry:
                    time.sleep(2**attempt)
                continue
            if attempt + 1 < self.retry:
                time.sleep(2**attempt)

        raise ChatClientError(last_category)


def _positive_int_env(name: str, default: int) -> int:
    """Read a bounded local diagnostic setting without exposing environment values."""
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
