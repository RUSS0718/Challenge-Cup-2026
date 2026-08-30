import json
import os
import threading
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
        request_deadline: float | None = None,
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
        # PRE0-EXT-001 amendment A1: opt-in wall-clock deadline per request.
        # A stalled (trickle-fed) response defeats the per-read requests timeout
        # and hung three solves for ~6.3h in the EXT attempt-1 window.  When
        # set, each attempt runs in a daemon thread; a live thread past the
        # deadline raises a timeout-category failure (retry logic unchanged).
        # Default None keeps the historical behavior byte-for-byte.
        self.request_deadline = (
            request_deadline
            if request_deadline is not None
            else _optional_float_env("INTERN_REQUEST_DEADLINE_SECONDS")
        )
        self.deadline_exceeded_count = 0
        # Zombie completions after a deadline abandonment (diagnostic only).
        self.orphan_completions = 0
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
                if self.request_deadline is not None:
                    return self._post_with_deadline(payload, headers)
                return self._post_once(payload, headers, started)
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

    def _post_once(self, payload: dict, headers: dict, started: float | None = None,
                   ticket: dict | None = None) -> str:
        response = requests.post(
            self.api_base,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage") or {}
        try:
            completion_tokens = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            completion_tokens = 0
        content = choice["message"]["content"]
        if ticket is not None and ticket.get("abandoned"):
            # Zombie completion after the deadline already fired (audit finding #4):
            # a late success must never append to the ordered telemetry slices that
            # callers index per solve, or it would shift every subsequent record.
            self.orphan_completions += 1
            return content
        self.finish_reasons.append(choice.get("finish_reason") or "")
        self.completion_tokens.append(completion_tokens)
        self.raw_contents.append(content if isinstance(content, str) else "")
        self.latencies.append(time.perf_counter() - (started if started is not None else time.perf_counter()))
        return content

    def _post_with_deadline(self, payload: dict, headers: dict) -> str:
        """Run one attempt under a wall-clock deadline (PRE0-EXT-001 amendment A1).

        The attempt thread is a daemon: a stalled trickle response is abandoned
        (leaked until process exit, documented) instead of hanging the solve.
        A zombie that completes after abandonment is counted but keeps its
        telemetry out of the ordered lists.
        """
        box: dict = {}
        ticket: dict = {"abandoned": False}
        started = time.perf_counter()

        def _run() -> None:
            try:
                box["result"] = self._post_once(payload, headers, started, ticket)
            except BaseException as exc:  # noqa: BLE001 — relayed to the caller below
                box["error"] = exc

        worker = threading.Thread(target=_run, daemon=True, name="intern-chat-deadline")
        worker.start()
        worker.join(self.request_deadline)
        if worker.is_alive():
            ticket["abandoned"] = True
            self.deadline_exceeded_count += 1
            raise requests.Timeout(
                f"request_deadline_exceeded:{self.request_deadline}s"
            )
        if "error" in box:
            raise box["error"]
        return box["result"]

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



def _optional_float_env(name: str) -> float | None:
    """Optional positive float setting; unset/invalid -> None (feature off)."""
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None

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

