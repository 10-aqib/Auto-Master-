"""Business-name normalisation and similarity (for evidence scoring, never for auto-merging)."""

from __future__ import annotations

import re
import unicodedata

_STOP = frozenset(
    {
        "the", "and", "of", "ltd", "limited", "llc", "inc", "incorporated", "co", "company",
        "corp", "corporation", "pvt", "private", "plc", "gmbh", "sa", "srl", "bv", "pty",
        "smc", "official", "website", "home", "welcome", "to",
    }
)  # fmt: skip
_TITLE_SEPARATORS = re.compile(r"\s+[|\-\u2013\u2014:\u00b7\u2022\u00bb]\s+")


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(t for t in text.split() if t not in _STOP)


def tokens(name: str) -> set[str]:
    return set(normalize_name(name).split())


def similarity(a: str, b: str) -> float:
    """1.0 for the same name. Containment counts only for multi-word names covering most of the
    other name, so a generic one-word title ("Dental") never matches a specific business."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    inter = ta & tb
    jaccard = len(inter) / len(ta | tb)
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    contained = inter == small and len(small) >= 2 and len(small) / len(large) >= 0.6
    return max(jaccard, 0.9 if contained else 0.0)


def title_segments(title: str) -> list[str]:
    return [s.strip() for s in _TITLE_SEPARATORS.split(title) if s.strip()]
