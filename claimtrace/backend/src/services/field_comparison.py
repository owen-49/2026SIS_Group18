"""Author and venue comparison for the bibliography audit.

The Engine's metadata comparator reads authors by surname alone: it compares
the first author's surname, accepts a count within one, and an overlap of 70%.
On a real bibliography that rule fails in both directions:

- It refuses names that are the same person. ``Tram{\\`e}r`` (BibTeX's accent
  markup) against ``Tramèr``, or ``Madry`` against ``Mądry``, differ only in how
  the accent is written. A multi-word surname such as ``Ghaffari Laleh, Narmin``
  against ``Narmin Ghaffari Laleh`` is read as two different surnames.
- It accepts lists that are not the same. ``and others`` is BibTeX for "the
  rest of the authors are not listed here", and a list cut off that way after
  ten of twelve authors passes the count-and-overlap rule.

These helpers answer the two questions the audit actually asks of a field: do
both sides name the same people in the same order, and if not, what exactly
differs. They never decide whether a record is the cited work -- identity is
settled before any field is compared.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# BibTeX accent commands and the Unicode combining mark each one stands for.
_ACCENT_MARKS = {
    "`": "\u0300",
    "'": "\u0301",
    "^": "\u0302",
    '"': "\u0308",
    "~": "\u0303",
    "=": "\u0304",
    ".": "\u0307",
    "u": "\u0306",
    "v": "\u030c",
    "H": "\u030b",
    "c": "\u0327",
    "k": "\u0328",
    "r": "\u030a",
}
# ``\'{e}``, ``{\'e}``, ``\'e``, ``\c{c}`` and ``\c c``.
_ACCENT_RE = re.compile(r"\\([`'^\"~=.uvHckr])\s*(?:\{\s*([A-Za-z])\s*\}|([A-Za-z]))")
_SPECIAL_LETTERS = {
    r"\o": "ø",
    r"\O": "Ø",
    r"\l": "ł",
    r"\L": "Ł",
    r"\ss": "ß",
    r"\ae": "æ",
    r"\AE": "Æ",
    r"\oe": "œ",
    r"\OE": "Œ",
    r"\aa": "å",
    r"\AA": "Å",
    r"\i": "ı",
}
_SPECIAL_RE = re.compile(r"\\(ss|ae|AE|oe|OE|aa|AA|[oOlLi])(?![A-Za-z])")
_TRUNCATION_MARKERS = {"others", "et al", "et al."}


def decode_latex(text: str) -> str:
    """Return ``text`` with BibTeX accent markup turned into Unicode letters."""
    if not text or "\\" not in text and "{" not in text:
        return text or ""

    def accent(match: re.Match) -> str:
        letter = match.group(2) or match.group(3)
        return unicodedata.normalize("NFC", letter + _ACCENT_MARKS[match.group(1)])

    decoded = _ACCENT_RE.sub(accent, text)
    decoded = _SPECIAL_RE.sub(lambda m: _SPECIAL_LETTERS["\\" + m.group(1)], decoded)
    return decoded.replace("{", "").replace("}", "")


def _fold(text: str) -> str:
    """Case-fold, strip accents and reduce punctuation to single spaces."""
    decomposed = unicodedata.normalize("NFKD", decode_latex(text))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Letters NFKD does not decompose, folded to the letter they are read as.
    stripped = stripped.translate(str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ı": "i"}))
    return re.sub(r"[\W_]+", " ", stripped.casefold()).strip()


@dataclass(frozen=True)
class _Name:
    surname: tuple[str, ...]
    given: tuple[str, ...]
    tokens: frozenset[str]


def _name(raw: str) -> _Name:
    """Read one author as surname and given names, in either name order."""
    raw = decode_latex(raw).strip()
    if "," in raw:
        last, _, first = raw.partition(",")
        surname, given = _fold(last).split(), _fold(first).split()
    else:
        words = _fold(raw).split()
        surname, given = words[-1:], words[:-1]
    return _Name(tuple(surname), tuple(given), frozenset(surname) | frozenset(given))


def _given_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Whether two first given names can belong to one person.

    Only the first given name is compared, and one may be an initial or a
    shortening of the other: "J" and "Jon" are both "Jonathon". A side that
    states no given name cannot contradict the other.
    """
    if not left or not right:
        return True
    a, b = left[0], right[0]
    return a.startswith(b) or b.startswith(a)


def same_surname(left: str, right: str) -> bool:
    """Whether two author strings carry the same surname.

    A multi-word surname is matched whole against the other side's words, so
    "Ghaffari Laleh, Narmin" is "Narmin Ghaffari Laleh" and "van Treeck, Marko"
    is "Marko van Treeck".
    """
    a, b = _name(left), _name(right)
    if not a.surname or not b.surname:
        return False
    return set(a.surname) <= b.tokens or set(b.surname) <= a.tokens


def same_person(left: str, right: str) -> bool:
    """Whether two author strings name the same person."""
    if not same_surname(left, right):
        return False
    a, b = _name(left), _name(right)
    # Compare given names with the surname words removed, so a surname a
    # "First Last" reading mistook for a given name does not count.
    given_a = tuple(t for t in a.given if t not in b.surname)
    given_b = tuple(t for t in b.given if t not in a.surname)
    return _given_compatible(given_a, given_b)


def is_truncation_marker(author: str) -> bool:
    """Whether an author entry is BibTeX's ``and others`` (or "et al.")."""
    return _fold(author) in {_fold(marker) for marker in _TRUNCATION_MARKERS}


@dataclass(frozen=True)
class AuthorComparison:
    status: str  # "MATCH" | "MISMATCH"
    detail: str
    # False when every surname and the count agree and only a given name
    # differs ("Smith, Jane" against "Smith, John"). That is shown for review
    # rather than asserted: it is as often a record's error as the reference's.
    decisive: bool = True


def compare_authors(reference: list[str], record: list[str]) -> AuthorComparison | None:
    """Compare a reference's author list with a record's, position by position.

    Returns ``None`` when either side has no authors, leaving the field to the
    caller's own missing-value handling.
    """
    listed = [author for author in reference if author.strip()]
    truncated = bool(listed) and is_truncation_marker(listed[-1])
    if truncated:
        listed = listed[:-1]
    record = [author for author in record if author.strip()]
    if not listed or not record:
        return None

    for index, (mine, theirs) in enumerate(zip(listed, record)):
        if not same_surname(mine, theirs):
            return AuthorComparison(
                "MISMATCH",
                f"Author {index + 1} differs: the reference has '{decode_latex(mine)}', "
                f"the record has '{theirs}'.",
            )
    given_conflict = next(
        (
            (index, mine, theirs)
            for index, (mine, theirs) in enumerate(zip(listed, record))
            if not same_person(mine, theirs)
        ),
        None,
    )

    missing = record[len(listed):]
    if truncated:
        if missing:
            return AuthorComparison(
                "MISMATCH",
                f"The author list is cut off with “and others”: it names {len(listed)} "
                f"of the {len(record)} authors in the record. Missing: {', '.join(missing)}.",
            )
        return AuthorComparison(
            "MATCH", "The listed authors agree; “and others” leaves no author out."
        )
    if missing:
        return AuthorComparison(
            "MISMATCH",
            f"The reference names {len(listed)} authors; the record has {len(record)}. "
            f"Missing: {', '.join(missing)}.",
        )
    if len(listed) > len(record):
        extra = listed[len(record):]
        return AuthorComparison(
            "MISMATCH",
            f"The reference names {len(listed)} authors; the record has {len(record)}. "
            f"Not in the record: {', '.join(decode_latex(a) for a in extra)}.",
        )
    if given_conflict is not None:
        index, mine, theirs = given_conflict
        return AuthorComparison(
            "MISMATCH",
            f"Author {index + 1} has the same surname but a different given name: the "
            f"reference has '{decode_latex(mine)}', the record has '{theirs}'. Review it.",
            decisive=False,
        )
    return AuthorComparison("MATCH", "Every author agrees, in the same order.")

