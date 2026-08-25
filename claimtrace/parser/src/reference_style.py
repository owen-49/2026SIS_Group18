"""Reference-format family detection.

The classifier intentionally identifies extraction-relevant families rather
than claiming an exact citation standard. APA and Harvard, for example, can
look nearly identical after PDF text extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol


class TextElement(Protocol):
    """Small structural interface used by the style classifier."""

    content: str


BRACKET_NUMBER_PATTERN = re.compile(r"^\s*\[\d+\]\s+")
PLAIN_NUMBER_PATTERN = re.compile(r"^\s*\d+[.)]\s+")
PARENTHESIZED_DATE_PATTERN = re.compile(
    r"\((?:(?:18|19|20)\d{2}[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?\)",
    flags=re.IGNORECASE,
)
APA_AUTHOR_DATE_PATTERN = re.compile(
    r"^[^()]{2,180}?\.\s*"
    r"\((?:(?:18|19|20)\d{2}[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?\)\.",
    flags=re.IGNORECASE,
)
AUTHOR_LEAD_PATTERN = re.compile(
    r"^[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019-]+"
    r"(?:,|\s+[A-Z]{1,4}(?:\s|,))"
)
AUTHOR_TITLE_PATTERN = re.compile(
    r"^[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019-]+,\s+"
    r"[A-Z\u00c0-\u024f][^()]{2,120}\."
)
INLINE_AUTHOR_YEAR_START_PATTERN = re.compile(
    r"(?<![\w])"
    r"(?:"
    r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019-]+"
    r"(?:,\s*|\s+)[A-Z]{1,4}(?:\.|\b)"
    r"(?:[A-Za-z\u00c0-\u024f'\u2019.,&\s-]{0,160}?)"
    r"|"
    r"[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019-]+"
    r"(?:\s+[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019-]+){1,8}\."
    r")\s*"
    r"\((?:(?:18|19|20)\d{2}[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?\)",
)


@dataclass(frozen=True)
class ReferenceStyleDetection:
    """Detected reference family plus inspectable scoring evidence."""

    family: str
    confidence: float
    evidence: dict[str, float] = field(default_factory=dict)


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def looks_like_reference_start(text: str) -> bool:
    """Return whether text has a common reference-entry opening."""

    normalized = " ".join(text.split()).strip()
    if not normalized:
        return False

    if BRACKET_NUMBER_PATTERN.match(normalized) or PLAIN_NUMBER_PATTERN.match(normalized):
        return True

    author_year = INLINE_AUTHOR_YEAR_START_PATTERN.match(normalized)
    if author_year and author_year.end() <= 220:
        return True

    if APA_AUTHOR_DATE_PATTERN.match(normalized[:240]):
        return True

    return bool(AUTHOR_TITLE_PATTERN.match(normalized[:180]))


def find_author_year_starts(text: str) -> list[int]:
    """Find likely author-year entry starts inside one text element."""

    return [match.start() for match in INLINE_AUTHOR_YEAR_START_PATTERN.finditer(text)]


def detect_reference_family(
    elements: Iterable[TextElement],
    sample_size: int = 30,
) -> ReferenceStyleDetection:
    """Classify a reference list using several weak signals together."""

    texts = [
        " ".join(element.content.split()).strip()
        for element in elements
        if element.content.strip()
    ][:sample_size]
    total = len(texts)

    if not total:
        return ReferenceStyleDetection("unknown", 0.0, {"sample_size": 0.0})

    bracketed = sum(bool(BRACKET_NUMBER_PATTERN.match(text)) for text in texts)
    plain = sum(bool(PLAIN_NUMBER_PATTERN.match(text)) for text in texts)
    parenthesized_date = sum(
        bool(PARENTHESIZED_DATE_PATTERN.search(text[:220])) for text in texts
    )
    apa_date = sum(bool(APA_AUTHOR_DATE_PATTERN.search(text[:240])) for text in texts)
    author_lead = sum(bool(AUTHOR_LEAD_PATTERN.search(text[:180])) for text in texts)
    author_title = sum(bool(AUTHOR_TITLE_PATTERN.search(text[:180])) for text in texts)

    evidence = {
        "sample_size": float(total),
        "bracketed_number_ratio": _ratio(bracketed, total),
        "plain_number_ratio": _ratio(plain, total),
        "parenthesized_date_ratio": _ratio(parenthesized_date, total),
        "apa_punctuation_ratio": _ratio(apa_date, total),
        "author_lead_ratio": _ratio(author_lead, total),
        "author_title_ratio": _ratio(author_title, total),
    }

    minimum_repeated_signal = 2 if total >= 2 else 1

    if bracketed >= minimum_repeated_signal and bracketed >= plain:
        return ReferenceStyleDetection(
            "bracket-numbered",
            min(1.0, 0.55 + 0.45 * bracketed / total),
            evidence,
        )

    if plain >= minimum_repeated_signal:
        return ReferenceStyleDetection(
            "plain-numbered",
            min(1.0, 0.55 + 0.45 * plain / total),
            evidence,
        )

    if parenthesized_date >= minimum_repeated_signal:
        apa_share = apa_date / parenthesized_date
        if apa_share >= 0.55:
            return ReferenceStyleDetection(
                "author-year-parenthesized",
                min(0.98, 0.5 + 0.3 * parenthesized_date / total + 0.18 * apa_share),
                evidence,
            )

        if author_lead >= minimum_repeated_signal:
            return ReferenceStyleDetection(
                "author-year-inline",
                min(0.95, 0.48 + 0.35 * parenthesized_date / total),
                evidence,
            )

    if author_title >= minimum_repeated_signal and parenthesized_date == 0:
        return ReferenceStyleDetection(
            "author-title",
            min(0.85, 0.45 + 0.35 * author_title / total),
            evidence,
        )

    return ReferenceStyleDetection(
        "unknown-unnumbered",
        max(0.1, min(0.49, 0.2 + 0.2 * author_lead / total)),
        evidence,
    )
