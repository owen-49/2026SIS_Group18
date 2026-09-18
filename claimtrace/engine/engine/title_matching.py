"""Title, venue, and identifier comparison helpers for metadata providers.

Pure string functions used by the identity rule in :mod:`engine.identity`.
Nothing here performs I/O or imports from the rest of the package, so the
comparison behaviour can be tested and reasoned about in isolation.

Design notes:
- ``normalize_title`` mirrors the manuscript-side comparison in the backend
  (``analysis_service._normalise_title``) with two deliberate changes. It also
  removes punctuation, so that string equality is exactly as permissive as the
  token comparison beside it, and it does **not** drop short tokens: a
  ``len(token) > 2`` filter makes ``"AI for Search"`` and ``"ML for Search"``
  compare equal, which is the wrong direction for an identity decision.
- Author surnames are extracted but are never evidence of identity. The spoofed
  records described in :mod:`engine.identity` copy the real author list
  verbatim, and a record whose first author is transliterated (Cyrillic
  ``Бабенко`` for ``Babenko``) would be rejected outright. Author agreement only
  ever corroborates or breaks a tie.
- ``venue_match_share`` is asymmetric on purpose: it answers "how much of the
  *reference's* venue appears in the candidate's", so a candidate venue is not
  penalised for the extra words a publisher prepends.
"""

import re
import unicodedata

# A hyphen followed by whitespace is usually a word split at a PDF or a
# Crossref container-title line break (``auto- encoders``); an ordinary hyphen
# separates title words. Mirrored from the backend comparison.
_TITLE_LINEBREAK_HYPHEN_RE = re.compile(r"(?<=\w)[-‐‑‒–—]\s+(?=\w)")
_TITLE_DASH_RE = re.compile(r"[-‐‑‒–—]")
_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Mirrored from ``analysis_service._STOP_WORDS`` plus its ``_TITLE_STOP_WORDS``
# additions. Kept in sync deliberately: the two comparisons should not drift.
STOP_WORDS = frozenset(
    {
        "a", "about", "after", "also", "an", "and", "are", "at", "been", "being", "between",
        "by", "could", "for", "from", "have", "in", "into", "more", "of", "on", "over", "such",
        "than", "that", "the", "their", "there", "these", "they", "this", "through", "to",
        "using", "via", "were", "which", "with", "without",
    }
)

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:")
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
_ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z][a-z-]*(?:\.[A-Z]{2})?/\d{7})"
# The separator also covers the DataCite form OpenAlex reports for preprints,
# ``10.48550/arXiv.1312.5663``, where the identifier follows a dot.
_ARXIV_RE = re.compile(rf"arxiv[:\s.]*({_ARXIV_ID})(?:v\d+)?", re.IGNORECASE)
_ARXIV_ABS_RE = re.compile(rf"abs/({_ARXIV_ID})(?:v\d+)?", re.IGNORECASE)
_ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)


def normalize_title(title: str) -> str:
    """Return the comparison form of a title.

    Args:
        title: A title from a reference list or a provider record.

    Returns:
        NFKC-normalised, case-folded text with line-wrap hyphens repaired,
        dashes and punctuation reduced to spaces, and runs of whitespace
        collapsed. Empty string for blank input.
    """
    value = unicodedata.normalize("NFKC", title or "").casefold().strip()
    value = _TITLE_LINEBREAK_HYPHEN_RE.sub("", value)
    value = _TITLE_DASH_RE.sub(" ", value)
    value = _PUNCTUATION_RE.sub(" ", value)
    return " ".join(value.split())


def title_tokens(title: str) -> set[str]:
    """Return the informative tokens of a title.

    Every token that is not a stop word is kept, including short ones, so that
    an acronym-only difference between two titles stays visible.
    """
    return {token for token in _TOKEN_RE.findall(normalize_title(title)) if token not in STOP_WORDS}


def title_similarity(left: str, right: str) -> float:
    """Return token overlap of two titles, normalised by the longer one.

    Returns 1.0 when the normalised titles are equal, and 0.0 when either side
    has no informative tokens.
    """
    if normalize_title(left) == normalize_title(right):
        return 1.0
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def normalize_venue(venue: str) -> str:
    """Return the comparison form of a venue name.

    Crossref container-titles carry the publisher's line wrapping, so this
    collapses whitespace and case-folds. Punctuation is left for
    :func:`venue_tokens` to discard.
    """
    value = unicodedata.normalize("NFKC", venue or "").casefold().strip()
    return " ".join(value.split())


def venue_tokens(venue: str) -> set[str]:
    """Return the informative tokens of a venue name."""
    return {
        token for token in _TOKEN_RE.findall(normalize_venue(venue)) if token not in STOP_WORDS
    }


def venue_match_share(reference_venue: str, candidate_venue: str) -> float:
    """Return the share of the reference's venue tokens present in a candidate.

    Asymmetric by design: a candidate venue that merely adds words (the
    publisher's prefix, a volume title) is not penalised. Returns 0.0 when the
    reference venue carries no informative tokens, which makes the caller
    abstain rather than match on nothing.
    """
    reference_tokens = venue_tokens(reference_venue)
    if not reference_tokens:
        return 0.0
    return len(reference_tokens & venue_tokens(candidate_venue)) / len(reference_tokens)


def first_author_surname(authors: list[str]) -> str:
    """Return a comparison form of the first author's surname.

    Handles both ``"Last, First"`` and ``"First Last"`` orders. The last
    whitespace-separated token is used for the latter, which also does the right
    thing for the IEEE initials form (``"D. M. Chiorean"``).
    """
    if not authors:
        return ""
    first = (authors[0] or "").strip()
    if not first:
        return ""
    if "," in first:
        surname = first.split(",", 1)[0]
    else:
        parts = first.split()
        surname = parts[-1] if parts else ""
    return normalize_title(surname)


def normalize_doi(doi: str) -> str:
    """Return the comparison form of a DOI: prefix stripped, lower-cased."""
    value = unicodedata.normalize("NFKC", doi or "").strip().casefold()
    for prefix in _DOI_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.strip().rstrip(".,;)")


def extract_doi(text: str) -> str:
    """Return the first DOI in free text, or an empty string.

    Recognises a bare ``10.…/…`` as well as the ``doi:`` and ``https://doi.org/``
    forms used by ACL-style reference lists.
    """
    match = _DOI_RE.search(_strip_doi_prefixes(text or ""))
    return normalize_doi(match.group(0)) if match else ""


def _strip_doi_prefixes(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    for prefix in _DOI_PREFIXES:
        value = re.sub(re.escape(prefix), "", value, flags=re.IGNORECASE)
    return value


def extract_arxiv_id(text: str) -> str:
    """Return the first arXiv identifier in free text, or an empty string.

    Recognises ``arXiv:1710.10723``, ``arXiv:1710.10723v2`` and the
    ``CoRR, abs/1308.3432`` form seen in older reference lists. The version
    suffix is dropped, because provider records identify the work rather than
    the revision.
    """
    value = unicodedata.normalize("NFKC", text or "")
    for pattern in (_ARXIV_RE, _ARXIV_ABS_RE):
        match = pattern.search(value)
        if match:
            return _ARXIV_VERSION_RE.sub("", match.group(1))
    return ""
