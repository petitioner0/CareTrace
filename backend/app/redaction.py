from __future__ import annotations

import json
import re
from dataclasses import dataclass


PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s()-]{6,}\d)(?!\w)")
SG_ID_RE = re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE)
LABELLED_ID_RE = re.compile(r"\b(?:NRIC|ID|MRN)\s*[:#-]?\s*[A-Z0-9-]{5,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    boundary_map: list[int]
    replacements: list[dict]

    def to_json(self) -> str:
        return json.dumps({"boundary_map": self.boundary_map, "replacements": self.replacements})


def redact(text: str, known_names: list[str]) -> RedactionResult:
    matches: list[tuple[int, int, str]] = []
    for index, name in enumerate(sorted({n.strip() for n in known_names if n.strip()}, key=len, reverse=True), 1):
        for match in re.finditer(re.escape(name), text, re.IGNORECASE):
            matches.append((match.start(), match.end(), f"[NAME_{index}]"))
    for regex, label in ((PHONE_RE, "[PHONE]"), (SG_ID_RE, "[ID]"), (LABELLED_ID_RE, "[ID]")):
        for match in regex.finditer(text):
            matches.append((match.start(), match.end(), label))

    chosen: list[tuple[int, int, str]] = []
    for start, end, replacement in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(start < selected_end and end > selected_start for selected_start, selected_end, _ in chosen):
            continue
        chosen.append((start, end, replacement))

    output: list[str] = []
    boundary_map: list[int] = [0]
    replacements: list[dict] = []
    cursor = 0
    redacted_cursor = 0
    for start, end, replacement in chosen:
        unchanged = text[cursor:start]
        output.append(unchanged)
        for position in range(cursor + 1, start + 1):
            boundary_map.append(position)
        redacted_cursor += len(unchanged)
        replacement_start = redacted_cursor
        output.append(replacement)
        for offset in range(1, len(replacement) + 1):
            boundary_map.append(end if offset == len(replacement) else start)
        redacted_cursor += len(replacement)
        replacements.append(
            {
                "redacted_start": replacement_start,
                "redacted_end": redacted_cursor,
                "original_start": start,
                "original_end": end,
                "placeholder": replacement,
            }
        )
        cursor = end
    tail = text[cursor:]
    output.append(tail)
    for position in range(cursor + 1, len(text) + 1):
        boundary_map.append(position)

    redacted_text = "".join(output)
    if len(boundary_map) != len(redacted_text) + 1:
        raise RuntimeError("Redaction position mapping is inconsistent")
    return RedactionResult(redacted_text, boundary_map, replacements)


def assert_no_known_phi(redacted_text: str, known_names: list[str]) -> None:
    leaks = [name for name in known_names if name and re.search(re.escape(name), redacted_text, re.IGNORECASE)]
    if leaks or PHONE_RE.search(redacted_text) or SG_ID_RE.search(redacted_text) or LABELLED_ID_RE.search(redacted_text):
        raise ValueError("redaction_review_required")

