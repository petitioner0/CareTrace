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


def match_quote(source: str, quote: str) -> QuoteMatch | None:
    if not quote:
        return None
    exact = [match.start() for match in re.finditer(re.escape(quote), source)]
    if len(exact) == 1:
        return QuoteMatch(exact[0], exact[0] + len(quote), "exact", "verified")
    if len(exact) > 1:
        return None

    normalized_source, source_positions = _normalized_with_map(source)
    normalized_quote, _ = _normalized_with_map(quote)
    if not normalized_quote:
        return None
    matches = [match for match in re.finditer(re.escape(normalized_quote), normalized_source)]
    if len(matches) != 1:
        return None
    match = matches[0]
    start = source_positions[match.start()]
    end = source_positions[match.end() - 1] + 1
    return QuoteMatch(start, end, "normalized", "supported")

