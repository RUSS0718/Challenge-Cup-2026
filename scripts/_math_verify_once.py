"""One-shot Math-Verify helper. Invoked as a subprocess to avoid Windows spawn bugs."""
from __future__ import annotations

import json
import sys


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    payload = json.loads(raw)
    gold = str(payload.get("gold", ""))
    pred = str(payload.get("pred", ""))
    try:
        from math_verify import parse, verify

        ok = bool(verify(parse(gold), parse(pred))) or bool(verify(parse(pred), parse(gold)))
        print(json.dumps({"ok": bool(ok), "error": None}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}))


if __name__ == "__main__":
    main()
