"""Parse a reference-list entry into the fields the identity rule compares.

The parsed reference lists this project stores carry the entry's raw text and
nothing else -- every structured field is null -- so the year veto and the
venue comparison in :mod:`engine.identity` are dead code over real data until
something reads the text. This is that something.

Design notes:
- Deliberately conservative. A reference entry is a human-formatted string from
  a PDF, and no rule recovers all of them; the aim is to produce the fields when
  the entry follows the common shape and to leave them empty when it does not. A
  field left empty costs an abstention, while a field guessed wrong can select
  the wrong record.
- The shape assumed is the one the manuscript set actually uses, an ACL-style
  entry: ``[N] Authors. Title. Venue, Year.`` Author lists are separated by
  commas and ``and``.
- Sentence splitting has to ignore abbreviation periods, because the author
  lists contain initials: ``Marius Muja and David G. Lowe. Scalable nearest
  neighbor algorithms...`` ends the author list at ``Lowe``, not at ``G``. A
  period preceded by a single letter is treated as an initial and skipped.
- The year is taken from the last four-digit year in the entry, after URL and
  ``doi:`` fragments are removed so an identifier's digits cannot be mistaken
  for a date. Some entries put the year before the title rather than at the end,
  and taking the last year gets both without a separate rule.
- A venue that turns out to be an identifier is discarded rather than kept.
  ``arXiv:1710.10723 [cs]`` is what one entry yields in the venue position, and
  keeping it would let a non-name participate in the venue tie-break.
- The whole entry is searched for identifiers, not the parsed parts, because a
  DOI is usually the last thing in the entry and outside every field.
"""

import re

from .identity import ReferenceQuery
from .title_matching import extract_arxiv_id, extract_doi

# ``[5]``, ``(5)``, ``5.`` and ``5)`` all occur at the start of an entry, and
# the marker is not part of the first author's name.
_MARKER_RE = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+[.)])\s*")
# A period ends sentences here; "?" and "!" are consulted only when no period
# break exists. Titles end in a period by convention, so a "?" is usually
# mid-title ("Do LLMs Feel? Teaching Emotion Recognition...") -- but an entry
# whose title does end in "?" has no period break before its venue at all, and
# then the question mark is the only terminator there is.
_PERIOD_BREAK_RE = re.compile(r"\.\s+")
_OTHER_BREAK_RE = re.compile(r"[?!]\s+")
# "Xin Li et al." -- the first author is Xin Li, not "al".
_ET_AL_RE = re.compile(r"\s+et\s+al\.?\s*$", re.IGNORECASE)
# One letter and a period, possibly repeated: an initial, or a run of them as in
# "Victor O.K. Li". Not the end of a sentence.
_INITIAL_RE = re.compile(r"(?:[^\W\d]\.)+", re.UNICODE)
# Some entries omit the period after the title and put the year straight after a
# comma. Only a comma- or semicolon-joined year is removed, so a title that
# genuinely ends in a year ("The state of AI in 2024") is left alone.
_TRAILING_YEAR_RE = re.compile(r"[,;]\s*(?:19|20)\d{2}\.?\s*$")
_BARE_YEAR_RE = re.compile(r"^(?:19|20)\d{2}\.\s+")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_URL_RE = re.compile(r"\bURL\s+\S+", re.IGNORECASE)
_DOI_LABEL_RE = re.compile(r"\bdoi:\s*\S+", re.IGNORECASE)
_IN_PREFIX_RE = re.compile(r"^in\s+", re.IGNORECASE)
# Edited volumes list the editors between ``In`` and the venue name.
_EDITORS_RE = re.compile(r"^.*?\beditors?,\s*", re.IGNORECASE)


def parse_reference_text(raw_text: str) -> ReferenceQuery:
    """Parse one reference entry into the fields a lookup can use.

    Args:
        raw_text: The entry as it appears in the reference list, numbering
            marker and all.

    Returns:
        A :class:`engine.identity.ReferenceQuery`. Fields the entry does not
        clearly supply are left empty. Never raises.
    """
    text = (raw_text or "").strip()
    if not text:
        return ReferenceQuery()
    try:
        return ReferenceQuery(
            title=_title(text),
            authors=_authors(text),
            year=_year(text),
            venue=_venue(text),
            doi=extract_doi(text),
            arxiv_id=extract_arxiv_id(text),
        )
    except Exception:
        # The helpers are total, so this is unreachable by construction. It
        # stays because the callers run this over every string a PDF extractor
        # produced, and a lookup that degrades is worth more than one that
        # takes the audit down.
        return ReferenceQuery()


def _title(text: str) -> str:
    title, _ = _split_at_sentence_end(_after_authors(text))
    return _TRAILING_YEAR_RE.sub("", title).strip()


def _authors(text: str) -> list[str]:
    authors_text, _ = _split_at_sentence_end(_strip_marker(text))
    return _split_authors(authors_text)


def _year(text: str) -> int | None:
    years = _YEAR_RE.findall(_strip_identifiers(text))
    return int(years[-1]) if years else None


def _venue(text: str) -> str:
    _, remainder = _split_at_sentence_end(_after_authors(text))
    if not remainder:
        return ""
    head = _strip_identifiers(remainder).strip()
    in_prefix = _IN_PREFIX_RE.match(head)
    if in_prefix:
        head = head[in_prefix.end() :]
        editors = _EDITORS_RE.match(head)
        if editors:
            head = head[editors.end() :]
    # Whatever follows the venue name is the volume, the page range, the
    # location, or the date, and a comma separates it.
    head = head.split(",", 1)[0]
    head = _split_at_sentence_end(head)[0].strip(" .;")
    if extract_doi(head) or extract_arxiv_id(head):
        return ""
    return head


def _strip_marker(text: str) -> str:
    return _MARKER_RE.sub("", text)


def _after_authors(text: str) -> str:
    """Return what follows the author list, skipping a year placed before the title."""
    _, remainder = _split_at_sentence_end(_strip_marker(text))
    while True:
        bare_year = _BARE_YEAR_RE.match(remainder)
        if not bare_year:
            return remainder
        remainder = remainder[bare_year.end() :]


def _split_at_sentence_end(text: str) -> tuple[str, str]:
    """Split after the first sentence-ending period, ignoring initials.

    Returns:
        ``(before, after)``, where ``before`` excludes the period. When no
        sentence end is found, ``after`` is empty and ``before`` is the input.
    """
    for pattern in (_PERIOD_BREAK_RE, _OTHER_BREAK_RE):
        for match in pattern.finditer(text):
            head = text[: match.start()]
            # The terminator is outside ``head``, so reattach it before asking
            # whether the token it belongs to is an initial.
            token = (head + text[match.start()]).split()[-1]
            if _INITIAL_RE.fullmatch(token):
                continue
            return head.strip(), text[match.end() :]
    # A final terminator with no space after it still ends the sentence, which
    # is how an entry whose title runs straight into its year is split.
    stripped = text.rstrip()
    if stripped and stripped[-1] in ".?!":
        return stripped[:-1].strip(), ""
    return text.strip(), ""


def _split_authors(authors_text: str) -> list[str]:
    """Split an author list on commas and ``and``, keeping the order given."""
    separated = re.sub(r"\s+and\s+", ", ", _ET_AL_RE.sub("", authors_text))
    names = (name.strip(" .") for name in separated.split(","))
    return [name for name in names if name]


def _strip_identifiers(text: str) -> str:
    """Remove URL and ``doi:`` fragments so their digits cannot read as a year."""
    return _DOI_LABEL_RE.sub(" ", _URL_RE.sub(" ", text))
