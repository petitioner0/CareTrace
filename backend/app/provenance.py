from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteMatch:
    start: int
    end: int
    method: str
    support: str


def quote_digest(quote: str) -> str:
    return hashlib.sha256(quote.encode()).hexdigest()


def _normalized_with_map(text: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    positions: list[int] = []
    in_space = False
    for index, character in enumerate(text):
        expanded = unicodedata.normalize("NFKC", character)
        for item in expanded:
            if item.isspace():
                if not in_space:
                    normalized.append(" ")
                    positions.append(index)
                in_space = True
            else:
                normalized.append(item)
                positions.append(index)
                in_space = False
    return "".join(normalized).strip(), positions


def match_quotes(source: str, quote: str) -> list[QuoteMatch]:
    if not quote:
        return []
    exact = [match.start() for match in re.finditer(re.escape(quote), source)]
    if exact:
        return [QuoteMatch(start, start + len(quote), "exact", "verified") for start in exact]

    normalized_source, source_positions = _normalized_with_map(source)
    normalized_quote, _ = _normalized_with_map(quote)
    if not normalized_quote:
        return []
    matches = [match for match in re.finditer(re.escape(normalized_quote), normalized_source)]
    return [
        QuoteMatch(
            source_positions[match.start()],
            source_positions[match.end() - 1] + 1,
            "normalized",
            "supported",
        )
        for match in matches
    ]


def match_quote(source: str, quote: str) -> QuoteMatch | None:
    """Return a match only when it is unique; retained for single-source callers."""
    matches = match_quotes(source, quote)
    return matches[0] if len(matches) == 1 else None
