"""Find historical Markdown files that make unlabelled current-state claims."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


CURRENT_CLAIM = re.compile(r"当前默认|当前正式|当前工作区实验配置|current default|current release", re.I)
HISTORICAL_PARTS = ("experiments", "9.28", ".workbuddy")


@dataclass(frozen=True)
class Finding:
    """Describe one historical document requiring an explicit status marker."""

    path: str
    reason: str


def scan_docs(root: Path) -> list[Finding]:
    """Return historical documents containing current-state language."""

    findings: list[Finding] = []
    candidates = list(root.rglob("*.md")) + [root / ".workbuddy/memory/MEMORY.md"]
    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        relative = path.relative_to(root).as_posix()
        parts = set(Path(relative).parts)
        if not parts.intersection(HISTORICAL_PARTS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if CURRENT_CLAIM.search(text) and not re.search(r"status\s*:\s*(archived|historical)", text, re.I):
            findings.append(Finding(relative, "historical_document_missing_status"))
    return sorted(findings, key=lambda item: item.path)


def main() -> int:
    """Print freshness findings; ``--strict`` turns findings into failure."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    findings = scan_docs(args.root.resolve())
    if not findings:
        print("doc-freshness: clean")
        return 0
    for finding in findings:
        print(f"{finding.path}: {finding.reason}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
