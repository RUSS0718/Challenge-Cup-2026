"""Run the ARM v2 thinking-on raw endpoint health matrix.

This experiment deliberately bypasses ``ReasoningAgent``, the harness, and
all answer parsers.  It measures only whether direct thinking-on requests
return a response within the registered timeout and token matrix; it does not
score mathematical accuracy or produce a promotion decision.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.artifacts import ArtifactManager, RunContext  # noqa: E402
from llm_client import InternChatClient  # noqa: E402


EXPERIMENT_ID = "ARM-ON-RAW-HEALTH-001"
DEFAULT_TIMEOUT_SECONDS = 130
DEFAULT_TOKEN_BUDGETS = (512, 2_048, 4_096)
DEFAULT_PROBES: tuple[dict[str, str], ...] = (
    {
        "probe_id": "easy",
        "difficulty": "easy",
        "problem": "Compute 17 * 19 and state the result.",
    },
    {
        "probe_id": "medium",
        "difficulty": "medium",
        "problem": (
            "A sequence starts with 1 and each term is obtained by adding the "
            "next odd number. Find the 20th term."
        ),
    },
    {
        "probe_id": "hard",
        "difficulty": "hard",
        "problem": (
            "Let a, b, c be positive real numbers with abc = 1. Determine the "
            "minimum of (a+b+c)^2/(ab+bc+ca)."
        ),
    },
)

SYSTEM_PROMPT = (
    "Solve the mathematical problem directly. Use thinking mode, but return "
    "a concise final response after reasoning."
)

ClientFactory = Callable[..., InternChatClient]


def _now_utc() -> str:
    """Return an ISO-8601 timestamp for the experiment manifest."""

    return datetime.now(timezone.utc).isoformat()


def _safe_error_category(exc: BaseException) -> str:
    """Map client failures to a bounded category without persisting details."""

    category = getattr(exc, "category", None)
    allowed = {
        "timeout",
        "rate_limit",
        "configuration",
        "connectivity",
        "proxy",
        "tls",
        "http_status",
        "invalid_response",
        "request",
    }
    return str(category) if category in allowed else "client_error"


def _last_value(client: Any, attribute: str, default: Any) -> Any:
    """Read the most recent bounded diagnostic value from a real or fake client."""

    values = getattr(client, attribute, None)
    return values[-1] if isinstance(values, list) and values else default


def run_probe(
    probe: dict[str, str],
    *,
    max_tokens: int,
    timeout_seconds: int,
    client_factory: ClientFactory = InternChatClient,
) -> dict[str, Any]:
    """Issue one direct thinking-on request and retain only health telemetry."""

    started = time.perf_counter()
    client: Any = None
    row: dict[str, Any] = {
        "probe_id": probe["probe_id"],
        "difficulty": probe["difficulty"],
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
        "status": "model_error",
        "error_category": None,
        "latency_seconds": 0.0,
        "completion_tokens": 0,
        "finish_reason": None,
        "response_formed": False,
    }
    try:
        client = client_factory(
            timeout=timeout_seconds,
            retry=1,
            thinking_mode=True,
        )
        response = client.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": probe["problem"]},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        row["finish_reason"] = _last_value(client, "finish_reasons", None) or None
        row["completion_tokens"] = int(_last_value(client, "completion_tokens", 0) or 0)
        row["response_formed"] = isinstance(response, str) and bool(response.strip())
        row["status"] = "ok" if row["response_formed"] else "invalid_response"
        if not row["response_formed"]:
            row["error_category"] = "empty_response"
    except Exception as exc:  # Persist only the sanitized category.
        row["error_category"] = _safe_error_category(exc)
        row["finish_reason"] = _last_value(client, "finish_reasons", None) if client else None
        row["completion_tokens"] = int(
            _last_value(client, "completion_tokens", 0) or 0
        ) if client else 0
    row["latency_seconds"] = round(time.perf_counter() - started, 3)
    return row


def _p95(values: Iterable[float]) -> float | None:
    """Return a nearest-rank p95 without requiring a statistics dependency."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return ordered[index]


def _group_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize health counters for one token or difficulty slice."""

    latencies = [float(row["latency_seconds"]) for row in rows]
    return {
        "n": len(rows),
        "status_counts": dict(Counter(str(row["status"]) for row in rows)),
        "response_formed_n": sum(bool(row.get("response_formed")) for row in rows),
        "timeout_n": sum(row.get("error_category") == "timeout" for row in rows),
        "average_latency_seconds": (
            round(sum(latencies) / len(latencies), 3) if latencies else 0.0
        ),
        "p95_latency_seconds": _p95(latencies),
        "max_latency_seconds": max(latencies, default=0.0),
        "completion_tokens_total": sum(
            int(row.get("completion_tokens") or 0) for row in rows
        ),
    }


def summarize(rows: list[dict[str, Any]], expected_records: int) -> dict[str, Any]:
    """Build a raw-health report with no mathematical correctness fields."""

    complete = len(rows) == expected_records
    response_formed_n = sum(bool(row.get("response_formed")) for row in rows)
    model_errors = sum(row.get("status") not in {"ok"} for row in rows)
    report: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "phase": "ON-RAW-HEALTH",
        "records": len(rows),
        "expected_records": expected_records,
        "complete": complete,
        "status_counts": dict(Counter(str(row["status"]) for row in rows)),
        "model_error_count": model_errors,
        "timeout_count": sum(row.get("error_category") == "timeout" for row in rows),
        "response_formed_count": response_formed_n,
        "response_formed_rate": response_formed_n / expected_records if expected_records else 0.0,
        "average_latency_seconds": _group_health(rows)["average_latency_seconds"],
        "p95_latency_seconds": _group_health(rows)["p95_latency_seconds"],
        "max_latency_seconds": _group_health(rows)["max_latency_seconds"],
        "by_token_budget": {},
        "by_difficulty": {},
        "capability_conclusion": "NONE",
    }
    for token_budget in sorted({int(row["max_tokens"]) for row in rows}):
        report["by_token_budget"][str(token_budget)] = _group_health(
            [row for row in rows if int(row["max_tokens"]) == token_budget]
        )
    for difficulty in sorted({str(row["difficulty"]) for row in rows}):
        report["by_difficulty"][difficulty] = _group_health(
            [row for row in rows if str(row["difficulty"]) == difficulty]
        )
    report["health_status"] = "healthy" if complete and model_errors == 0 else "degraded"
    return report


def _validate_probes(probes: Iterable[dict[str, str]]) -> tuple[dict[str, str], ...]:
    """Validate the small qualitative probe set before issuing requests."""

    result = tuple(probes)
    if not result:
        raise ValueError("probes_must_not_be_empty")
    ids = [probe.get("probe_id") for probe in result]
    if any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("probe_id_must_be_non_empty")
    if len(set(ids)) != len(ids):
        raise ValueError("probe_ids_must_be_unique")
    for probe in result:
        if probe.get("difficulty") not in {"easy", "medium", "hard"}:
            raise ValueError("probe_difficulty_must_be_easy_medium_or_hard")
        if not str(probe.get("problem") or "").strip():
            raise ValueError("probe_problem_must_be_non_empty")
    return result


def run(
    output_dir: Path,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    token_budgets: Iterable[int] = DEFAULT_TOKEN_BUDGETS,
    probes: Iterable[dict[str, str]] = DEFAULT_PROBES,
    client_factory: ClientFactory = InternChatClient,
) -> dict[str, Any]:
    """Run the sequential 3-by-3 matrix and write resumeless report artifacts."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds_must_be_positive")
    budgets = tuple(int(value) for value in token_budgets)
    if not budgets or any(value <= 0 for value in budgets):
        raise ValueError("token_budgets_must_be_positive")
    checked_probes = _validate_probes(probes)
    manager = ArtifactManager(output_dir)
    expected_records = len(checked_probes) * len(budgets)
    started = time.perf_counter()
    started_at = _now_utc()
    context = RunContext(
        run_id=output_dir.name or EXPERIMENT_ID,
        config=EXPERIMENT_ID,
        dataset="inline-probes",
        model="InternChatClient",
        started_at=started_at,
    )
    manifest = context.as_manifest()
    manifest.update({
        "experiment_id": EXPERIMENT_ID,
        "phase": "ON-RAW-HEALTH",
        "status": "running",
        "started_at_utc": started_at,
        "workers": 1,
        "direct_client": "InternChatClient.chat",
        "reasoning_mode": "thinking_on",
        "request_timeout_seconds": timeout_seconds,
        "token_budgets": list(budgets),
        "probe_count": len(checked_probes),
        "expected_records": expected_records,
        "probes": [
            {
                "probe_id": probe["probe_id"],
                "difficulty": probe["difficulty"],
                "problem_sha256": hashlib.sha256(
                    probe["problem"].encode("utf-8")
                ).hexdigest(),
            }
            for probe in checked_probes
        ],
        "answers": "answers.jsonl",
        "report": "report.json",
        "capability_conclusion": "NONE",
    })
    manager.save_manifest(manifest)

    rows: list[dict[str, Any]] = []
    manager.save_answers(rows)
    for max_tokens in budgets:
        for probe in checked_probes:
            rows.append(
                run_probe(
                    probe,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    client_factory=client_factory,
                )
            )
            manager.save_answers(rows)
            interim = summarize(rows, expected_records)
            interim["status"] = "running"
            interim["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            manager.save_report(interim)

    report = summarize(rows, expected_records)
    report.update({
        "status": "completed",
        "started_at_utc": manifest["started_at_utc"],
        "ended_at_utc": _now_utc(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    })
    manifest.update({
        "status": "completed",
        "ended_at_utc": report["ended_at_utc"],
        "records": len(rows),
        "health_status": report["health_status"],
    })
    manager.save_report(report)
    manager.save_manifest(manifest)
    manager.save_text(
        "result.md",
        (
            f"# {EXPERIMENT_ID}\n\n"
            f"端点健康状态：`{report['health_status']}`；"
            f"记录：{report['records']}/{report['expected_records']}；"
            f"响应形成：{report['response_formed_count']}/{report['expected_records']}；"
            f"timeout：{report['timeout_count']}。\n\n"
            "本实验只测 thinking-on 端点的请求健康，不判断数学正确率，"
            "不经过 ReasoningAgent、Harness 或 Parser，也不产生能力晋升结论。\n"
        ),
    )
    return report


def _parse_budgets(raw: str) -> tuple[int, ...]:
    """Parse a comma-separated positive token-budget list for the CLI."""

    values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("tokens must be comma-separated positive integers")
    return values


def main() -> int:
    """Parse CLI options and run the raw endpoint health experiment."""

    parser = argparse.ArgumentParser(description=__doc__)
    default_output_dir = ROOT / "artifacts" / RunContext.create(EXPERIMENT_ID).run_id
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir),
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--tokens",
        type=_parse_budgets,
        default=DEFAULT_TOKEN_BUDGETS,
        help="Comma-separated max_tokens values; default: 512,2048,4096.",
    )
    args = parser.parse_args()
    report = run(
        Path(args.output_dir),
        timeout_seconds=args.timeout,
        token_budgets=args.tokens,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
