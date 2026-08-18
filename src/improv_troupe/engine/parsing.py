"""Clean up raw model output into a single in-character line.

Small models tend to (a) prefix their own name, (b) keep going and write other
characters' lines, or (c) wrap everything in quotes. We trim all three so the
transcript stays a clean script.
"""

from __future__ import annotations

import re

_LABEL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _'.-]{0,30}):\s*")


def clean_line(raw: str, speaker: str, other_names: list[str]) -> str:
    text = raw.strip()
    if not text:
        return ""

    # Drop a leading "SPEAKER:" the model added itself.
    m = _LABEL_RE.match(text)
    if m and _norm(m.group(1)) == _norm(speaker):
        text = text[m.end() :].lstrip()

    # Cut the moment the model starts speaking as someone else.
    others = {_norm(n) for n in other_names}
    kept: list[str] = []
    for line in text.splitlines():
        lm = _LABEL_RE.match(line)
        if lm and _norm(lm.group(1)) in others:
            break
        kept.append(line)
    text = "\n".join(kept).strip()

    # Strip symmetric wrapping quotes.
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()

    return text


def _norm(name: str) -> str:
    return name.strip().lower()
