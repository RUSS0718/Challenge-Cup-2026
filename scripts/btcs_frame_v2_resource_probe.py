"""Independent workers=1 resource qualification for BTCS Frame v2."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient


RUN_ID = "BTCS-FRAME-V2-RESOURCE-001"
_ERROR_CATEGORIES = {
    "configuration",
    "connectivity",
    "http_status",
    "invalid_response",
    "proxy",
    "request",
    "timeout",
    "tls",
}
_FINISH_REASONS = {"length", "stop"}


def _items(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _safe_error_category(exc: BaseException) -> str:
    category = str(getattr(exc, "category", "")).lower()
    return category if category in _ERROR_CATEGORIES else "model_error"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="sample_data/dev.jsonl")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--deadline", type=float, default=360.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    rows_input = _items(input_path)
    if len(rows_input) != 3:
        print(json.dumps({
            "run_id": RUN_ID,
            "status": "VOID_RESOURCE_HEALTH",
            "error_category": "input_count_mismatch",
            "expected_count": 3,
            "actual_count": len(rows_input),
        }, ensure_ascii=False))
        return 2

    client = InternChatClient(timeout=args.timeout, retry=1, request_deadline=args.deadline)
    rows: list[dict] = []
    started = time.perf_counter()
    for item in rows_input:
        item_started = time.perf_counter()
        try:
            response = client.chat(
                messages=[
                    {"role": "system", "content": "你是数学求解器。请完成题目并给出最终答案。"},
                    {"role": "user", "content": str(item["problem"])},
                ],
                temperature=0.6,
                max_tokens=4096,
            )
            finish_reason = client.finish_reasons[-1] if client.finish_reasons else ""
            rows.append({
                "idx": item.get("idx"),
                "status": "ok",
                "nonempty": bool(isinstance(response, str) and response.strip()),
                "finish_reason": finish_reason if finish_reason in _FINISH_REASONS else "other",
                "completion_tokens": client.completion_tokens[-1] if client.completion_tokens else 0,
                "latency_seconds": round(time.perf_counter() - item_started, 3),
            })
        except Exception as exc:
            rows.append({
                "idx": item.get("idx"),
                "status": "error",
                "error_category": _safe_error_category(exc),
                "latency_seconds": round(time.perf_counter() - item_started, 3),
            })

    snapshot = client.diagnostic_snapshot()
    host = urlparse(client.api_base).netloc
    ok = sum(row["status"] == "ok" for row in rows)
    deadline_count = client.deadline_exceeded_count
    orphan_count = client.orphan_completions
    passed = (
        len(rows) == 3
        and ok == 3
        and deadline_count == 0
        and orphan_count == 0
    )
    report = {
        "run_id": RUN_ID,
        "method_id": "btcs_frame_v2",
        "status": "RESOURCE_PASS" if passed else "VOID_RESOURCE_HEALTH",
        "workers": 1,
        "input": {
            "path": str(input_path).replace("\\", "/"),
            "count": len(rows_input),
            "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        },
        "endpoint_host": host,
        "model": snapshot.get("model"),
        "timeout_seconds": args.timeout,
        "request_deadline_seconds": args.deadline,
        "temperature": 0.6,
        "solver_max_tokens": 4096,
        "client_retry": 1,
        "rows": rows,
        "completed_count": len(rows),
        "ok": ok,
        "error": len(rows) - ok,
        "deadline_exceeded_count": deadline_count,
        "orphan_completions": orphan_count,
        "probe_http_attempts": len(rows),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "capability_conclusion": None,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
