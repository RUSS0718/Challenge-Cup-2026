"""Load the vendored 18-domain ICMA skill manuals for prompt-time retrieval."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .skill_excerpt import (
    _GATE_LINE_RE,
    _MODULE_RE,
    _split_modules,
    select_skill_excerpt,
)


SKILL_ROOT = Path(__file__).with_name("full_skills")


def _skill_paths() -> dict[str, Path]:
    paths = {
        path.parent.name: path
        for path in SKILL_ROOT.glob("*/*skill.md")
        if path.is_file()
    }
    if len(paths) != 18:
        raise RuntimeError(f"Expected 18 vendored skill manuals, found {len(paths)}")
    return paths


def categories() -> tuple[str, ...]:
    return tuple(sorted(_skill_paths()))


def _matched_cross_category_cards(problem: str, paths: dict[str, Path]) -> list[dict[str, Any]]:
    text = problem.casefold()
    matched: list[dict[str, Any]] = []
    for category, path in paths.items():
        document = path.read_text(encoding="utf-8")
        _, modules = _split_modules(document, _MODULE_RE)
        for module in modules:
            gate = _GATE_LINE_RE.search(module)
            if not gate:
                continue
            tokens = [token.casefold() for token in gate.group(1).split() if token]
            if tokens and all(token in text for token in tokens):
                matched.append(
                    {
                        "category": category,
                        "title": module.split("\n", 1)[0].strip(),
                        "text": module.strip(),
                    }
                )
    return matched


def select_full_skill_context(
    category: str,
    problem: str,
    *,
    limit: int = 3000,
) -> tuple[str, dict[str, Any]]:
    """Return the reference implementation's category excerpt plus gated cards.

    The complete manuals remain on disk. Only a topic-matched excerpt enters an
    individual API request, so copying the full corpus does not inflate context.
    """

    paths = _skill_paths()
    path = paths.get(category)
    if path is None:
        return "", {
            "status": "unknown_category",
            "category": category,
            "available_categories": list(sorted(paths)),
            "selected_chars": 0,
            "matched_cards": [],
        }

    document = path.read_text(encoding="utf-8")
    base = select_skill_excerpt(document, problem, limit)
    cards = _matched_cross_category_cards(problem, paths)
    extras = [card["text"] for card in cards if card["text"][:60] not in base]
    if extras:
        cards_text = "\n\n".join(extras)
        keep = max(min(limit - len(cards_text), limit), min(1200, limit // 2))
        context = cards_text + "\n\n" + (base if len(base) <= keep else base[:keep])
    else:
        context = base

    return context, {
        "status": "selected" if context else "empty",
        "category": category,
        "source": str(path.relative_to(SKILL_ROOT.parent)),
        "manual_chars": len(document),
        "manual_sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
        "selected_chars": len(context),
        "matched_cards": [
            {"category": card["category"], "title": card["title"]}
            for card in cards
        ],
    }


__all__ = ["SKILL_ROOT", "categories", "select_full_skill_context"]
