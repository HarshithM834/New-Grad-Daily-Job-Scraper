"""Conservative, explainable title-level filtering for new-graduate searches.

The upstream feed's ``isNewGrad`` flag is not trustworthy as a strict filter.
Roles without strong title evidence are *unknown*, not automatically rejected.
"""
from __future__ import annotations

import re
from typing import Literal

Eligibility = Literal["likely", "unlikely", "unknown"]

# Prefer explicit evidence rather than a guessed numerical score.
NEGATIVE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|manager|architect|head of|vice president|"
    r"vp|tech lead|technical lead|lead engineer|engineer (?:iii|iv|v|3|4|5))\b",
    re.IGNORECASE,
)
POSITIVE = re.compile(
    r"\b(?:new\s*grad(?:uate)?|recent\s*grad(?:uate)?|university\s*grad(?:uate)?|"
    r"early[ -]career|entry[ -]level|junior|jr\.?|graduate program|graduate engineer|"
    r"associate (?:software|data|machine learning|ml|ai|backend|frontend|full[ -]?stack|cloud|"
    r"security|systems|platform|devops) engineer|"
    r"(?:software|data|machine learning|ml|ai|backend|frontend|cloud|security|systems|platform|"
    r"devops) engineer (?:i|1)|202[6-9] (?:graduate|university))\b",
    re.IGNORECASE,
)


def classify_role(title: str) -> Eligibility:
    """Return likely/unlikely/unknown, without inventing experience requirements."""
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    if not cleaned:
        return "unknown"
    if NEGATIVE.search(cleaned):
        return "unlikely"
    if POSITIVE.search(cleaned):
        return "likely"
    return "unknown"


def select_categories(value: str, available=("SWE", "DE", "AI/ML")) -> tuple[str, ...]:
    """Parse friendly comma-separated category choices; reject unknown values."""
    aliases = {
        "swe": "SWE", "software": "SWE", "software engineering": "SWE",
        "de": "DE", "data": "DE", "data engineering": "DE",
        "aiml": "AI/ML", "ai/ml": "AI/ML", "ai": "AI/ML", "ml": "AI/ML",
    }
    text = (value or "").strip()
    if not text or text.casefold() == "all":
        return tuple(available)
    selected = []
    for token in text.split(","):
        choice = aliases.get(token.strip().casefold())
        if choice is None or choice not in available:
            raise ValueError(f"Unsupported category {token.strip()!r}; choose SWE, DE, AI/ML or all")
        if choice not in selected:
            selected.append(choice)
    return tuple(selected)