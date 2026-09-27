import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests


DEFAULT_API_BASE = "https://chat.intern-ai.org.cn/api/v1/chat/completions"
# The provider's API identifier for the current Intern-S2 model.
DEFAULT_MODEL = "intern-s2"


def _load_local_env() -> None:
    """Load simple KEY=VALUE settings from the repository .env, overriding Windows values."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name:
            os.environ[name] = value


_load_local_env()


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
        thinking_mode: bool | None = None,
    ) -> None:
        raw_api_key = os.environ.get("INTERN_API_KEY")
        if not raw_api_key:
            raise ChatClientError("configuration")
        self.authorization = (
            raw_api_key if raw_api_key.startswith("Bearer ") else f"Bearer {raw_api_key}"
        )
        self.api_base = os.environ.get("INTERN_API_BASE", DEFAULT_API_BASE)
        self.model = os.environ.get("INTERN_MODEL", DEFAULT_MODEL)
        # Explicit kwarg wins over the env switch so experiments can pin the
        # thinking switch per arm without touching process env.
        self.thinking_mode = (
            thinking_mode if thinking_mode is not None else _optional_bool_env("INTERN_THINKING_MODE")
        )
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
        # Sanitized per-attempt metadata for local diagnosis; never stores
        # authorization headers, prompts, or response content.
        self.request_diagnostics: List[dict[str, Any]] = []
        self._logical_call_count = 0
        self._request_sequence = 0
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

        message_bytes = json.dumps(
            messages, ensure_ascii=False, sort_keys=True, default=str
        ).encode("utf-8")
        logical_call_index = self._logical_call_count
        self._logical_call_count += 1
        request_metadata = {
            "logical_call_index": logical_call_index,
            "request_model_id": self.model,
            "api_host": urlparse(self.api_base).netloc,
            "thinking_mode": self.thinking_mode,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": self.timeout,
            "attempts_configured": self.retry,
            "message_count": len(messages),
            "message_roles": [str(message.get("role", "")) for message in messages],
            "messages_sha256": hashlib.sha256(message_bytes).hexdigest(),
        }
        last_category = "request"
        started = time.perf_counter()
        for attempt in range(self.retry):
            attempt_started = time.perf_counter()
            request_event: dict[str, Any] = {
                **request_metadata,
                "request_sequence": self._request_sequence,
                "attempt_index": attempt + 1,
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
            response = None
            failure: BaseException | None = None
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
                finish_reason = choice.get("finish_reason") or ""
                request_event.update(
                    status="success",
                    http_status=response.status_code,
                    response_id=data.get("id") if isinstance(data.get("id"), str) else None,
                    response_model_id=(
                        data.get("model") if isinstance(data.get("model"), str) else None
                    ),
                    finish_reason=finish_reason,
                )
                self.finish_reasons.append(finish_reason)
                usage = data.get("usage") or {}
                try:
                    completion_tokens = int(usage.get("completion_tokens") or 0)
                except (TypeError, ValueError):
                    completion_tokens = 0
                self.completion_tokens.append(completion_tokens)
                for usage_field in ("prompt_tokens", "total_tokens"):
                    try:
                        request_event[usage_field] = int(usage.get(usage_field) or 0)
                    except (TypeError, ValueError):
                        request_event[usage_field] = None
                request_event["completion_tokens"] = completion_tokens
                content = choice["message"]["content"]
                self.raw_contents.append(content if isinstance(content, str) else "")
                request_event["response_content_chars"] = (
                    len(content) if isinstance(content, str) else None
                )
                self.latencies.append(time.perf_counter() - started)
                return content
            except requests.Timeout as exc:
                last_category = "timeout"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.exceptions.ProxyError as exc:
                last_category = "proxy"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.exceptions.SSLError as exc:
                last_category = "tls"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.ConnectionError as exc:
                last_category = "connectivity"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.HTTPError as exc:
                last_category = "http_status"
                failure = exc
                self._record_failure(last_category, exc)
            except (KeyError, TypeError, ValueError) as exc:
                last_category = "invalid_response"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.RequestException as exc:
                last_category = "request"
                failure = exc
                self._record_failure(last_category, exc)
            except Exception as exc:
                failure = exc
                last_category = "client_exception"
                self._record_failure(last_category, exc)
                raise
            finally:
                request_event["duration_seconds"] = round(
                    time.perf_counter() - attempt_started, 3
                )
                if failure is not None:
                    failure_response = (
                        response if response is not None else getattr(failure, "response", None)
                    )
                    request_event.update(
                        status="error",
                        error_category=last_category,
                        error_type=type(failure).__name__,
                        http_status=(
                            getattr(failure_response, "status_code", None)
                            if failure_response is not None
                            else None
                        ),
                    )
                self.request_diagnostics.append(request_event)
                self._request_sequence += 1
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

