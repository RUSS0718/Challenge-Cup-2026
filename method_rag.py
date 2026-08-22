"""Small offline method-card retriever for controlled experiments.

The retriever is deliberately dependency-free and is not imported by
``user_agent``.  It returns only committed method cards, never dataset answers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


class MethodCardRetriever:
    def __init__(self, cards_path: str | Path) -> None:
        path = Path(cards_path)
        with path.open("r", encoding="utf-8") as handle:
            self.cards = [json.loads(line) for line in handle if line.strip()]
        self._tokens = [self._tokenize(self._search_text(card)) for card in self.cards]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        tokens: set[str] = set()
        for chunk in TOKEN_RE.findall(text.lower()):
            tokens.add(chunk)
            if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
                tokens.update(chunk[index:index + 2] for index in range(len(chunk) - 1))
                tokens.update(chunk[index:index + 3] for index in range(len(chunk) - 2))
        return tokens

    @staticmethod
    def _search_text(card: dict[str, Any]) -> str:
        return " ".join(str(card.get(field, "")) for field in ("title", "signals", "method", "conditions", "example"))

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip() or top_k <= 0:
            return []
        query_tokens = self._tokenize(query)
        scored = []
        for card, tokens in zip(self.cards, self._tokens):
            overlap = len(query_tokens & tokens)
            if overlap:
                scored.append((overlap, card))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
        return [card for _, card in scored[:top_k]]
