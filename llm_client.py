import json
import os
import time
from typing import Dict, List
from urllib.parse import urlparse

import requests


DEFAULT_API_BASE = "https://chat.intern-ai.org.cn/api/v1/chat/completions"
# The legacy ``intern-s2-preview`` alias now points to a smaller model.  Use
# the explicit 397B identifier for local experiments; callers can still pin a
# different provider-supported model with INTERN_MODEL.
DEFAULT_MODEL = "intern-s2-preview-397b"


class ChatClientError(RuntimeError):
    """A sanitized failure category suitable for trace and local reports."""

    def __init__(self, category: str, detail: str | None = None) -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail


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
        self.thinking_mode = _optional_bool_env("INTERN_THINKING_MODE")
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
        # 13.2 token A/B: per-call wall-clock latency (aligned with the lists above,
        # appended once per successful chat call so before/after slicing works).
        self.latencies: List[float] = []
        self.last_failure_category: str | None = None
        self.last_failure_type: str | None = None

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
        if self.thinking_mode is not None:
            payload["thinking_mode"] = self.thinking_mode
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.authorization,
        }

        last_category = "request"
        started = time.perf_counter()
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
                self.latencies.append(time.perf_counter() - started)
                return content
            except requests.Timeout as exc:
                last_category = "timeout"
                self._record_failure(last_category, exc)
            except requests.exceptions.ProxyError as exc:
                last_category = "proxy"
                self._record_failure(last_category, exc)
            except requests.exceptions.SSLError as exc:
                last_category = "tls"
                self._record_failure(last_category, exc)
            except requests.ConnectionError as exc:
                last_category = "connectivity"
                self._record_failure(last_category, exc)
            except requests.HTTPError as exc:
                last_category = "http_status"
                self._record_failure(last_category, exc)
            except (KeyError, TypeError, ValueError) as exc:
                last_category = "invalid_response"
                self._record_failure(last_category, exc)
            except requests.RequestException as exc:
                last_category = "request"
                self._record_failure(last_category, exc)
                if attempt + 1 < self.retry:
                    time.sleep(2**attempt)
                continue
            if attempt + 1 < self.retry:
                time.sleep(2**attempt)

        raise ChatClientError(last_category, self.last_failure_type)

    def diagnostic_snapshot(self) -> dict[str, str | None]:
        """Return safe local diagnostics; never includes credentials or prompts."""
        parsed = urlparse(self.api_base)
        return {
            "model": self.model,
            "thinking_mode": self.thinking_mode,
            "api_host": parsed.netloc,
            "last_failure_category": self.last_failure_category,
            "last_failure_type": self.last_failure_type,
        }

    def _record_failure(self, category: str, exc: BaseException) -> None:
        self.last_failure_category = category
        if isinstance(exc, requests.HTTPError) and getattr(exc, "response", None) is not None:
            status = getattr(exc.response, "status_code", None)
            self.last_failure_type = f"HTTPError:{status}" if status is not None else "HTTPError"
        else:
            self.last_failure_type = type(exc).__name__


def _positive_int_env(name: str, default: int) -> int:
    """Read a bounded local diagnostic setting without exposing environment values."""
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _optional_bool_env(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


