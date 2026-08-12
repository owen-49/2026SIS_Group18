"""BibTeX (.bib) file parser.

Parses bibliography files into structured BibEntry objects,
enabling cross-validation between what the .bib claims and
what the actual source PDF contains.

Handles common BibTeX quirks:
- Unescaped special characters (%, $, &, #, _, ~)
- Multi-line field values
- Abbreviated vs. full first names
- Missing optional fields
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BibEntry:
    """A single parsed BibTeX entry."""

    key: str                                    # citation key, e.g. "wei2022emergent"
    entry_type: str = "article"                  # article | inproceedings | book | misc | ...
    title: str = ""
    authors: list[str] = field(default_factory=list)  # "Last, First" format
    year: int | None = None
    venue: str = ""                              # journal or booktitle
    volume: str = ""
    number: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    publisher: str = ""
    raw_text: str = ""                           # original bib block

    @property
    def author_last_names(self) -> list[str]:
        """Return just the last names for fuzzy matching."""
        return [a.split(",")[0].strip().lower() for a in self.authors]

    @property
    def first_author_last_name(self) -> str:
        """Return the first author's last name (lowercase)."""
        if not self.authors:
            return ""
        return self.authors[0].split(",")[0].strip().lower()

    @property
    def short_title(self) -> str:
        """Return title with case normalised and punctuation stripped."""
        return re.sub(r"[^a-z0-9\s]", "", self.title.lower())


def parse_bib_file(file_path: Path) -> list[BibEntry]:
    """Parse a .bib file and return all entries.

    Args:
        file_path: Path to a .bib file.

    Returns:
        List of BibEntry objects.
    """
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return parse_bib_text(text)


def parse_bib_text(text: str) -> list[BibEntry]:
    """Parse BibTeX text content and return all entries.

    Args:
        text: Raw BibTeX content as a string.

    Returns:
        List of BibEntry objects.
    """
    entries: list[BibEntry] = []

    # Split on @entry_type{...} — handles @article, @inproceedings, @book, @misc, etc.
    pattern = re.compile(r"@(\w+)\s*\{\s*([^,]+)\s*,\s*(.+?)\s*\}", re.DOTALL)
    matches = pattern.findall(text)

    for entry_type, key, fields_text in matches:
        key = key.strip()
        entry = _parse_fields(entry_type.lower(), key, fields_text)
        entry.raw_text = f"@{entry_type}{{{key},\n{fields_text}\n}}"
        entries.append(entry)

    return entries


def _parse_fields(entry_type: str, key: str, fields_text: str) -> BibEntry:
    """Parse field-value pairs from a BibTeX entry's content.

    Args:
        entry_type: The BibTeX entry type (article, inproceedings, etc.).
        key: The citation key.
        fields_text: Raw text between the outer braces.

    Returns:
        BibEntry with extracted fields.
    """
    entry = BibEntry(key=key, entry_type=entry_type)

    # Split fields on "=" but handle nested braces
    # Strategy: find "fieldname = {value}" or "fieldname = "value""
    field_pattern = re.compile(
        r"(\w+)\s*=\s*[{\"]([^}\"]*)[}\"]", re.DOTALL
    )
    fields = field_pattern.findall(fields_text)

    for field_name, field_value in fields:
        field_name = field_name.lower().strip()
        field_value = field_value.strip()

        # Remove leading/trailing whitespace from multi-line values
        field_value = re.sub(r"\s+", " ", field_value).strip()

        if field_name == "title":
            entry.title = _clean_title(field_value)
        elif field_name == "author":
            entry.authors = _parse_authors(field_value)
        elif field_name == "year":
            entry.year = _parse_year(field_value)
        elif field_name in ("journal", "booktitle"):
            entry.venue = field_value
        elif field_name == "volume":
            entry.volume = field_value
        elif field_name == "number":
            entry.number = field_value
        elif field_name == "pages":
            entry.pages = field_value
        elif field_name == "doi":
            entry.doi = field_value
        elif field_name == "url":
            entry.url = field_value
        elif field_name == "publisher":
            entry.publisher = field_value

    return entry


def _clean_title(raw: str) -> str:
    """Normalise a BibTeX title field.

    Removes LaTeX commands, extra braces, and normalises whitespace.
    """
    # Remove LaTeX commands like \textit{}, \textbf{}, \emph{}
    cleaned = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", raw)
    # Remove stray braces
    cleaned = cleaned.replace("{", "").replace("}", "")
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_authors(raw: str) -> list[str]:
    """Parse the author field into individual names.

    Handles:
    - "Last, First and Last, First"
    - "First Last and First Last"
    - "Last, First and First Last" (mixed — Google Scholar's favorite)

    Args:
        raw: Raw author field string.

    Returns:
        List of author name strings.
    """
    # Split on " and " (case-insensitive)
    parts = re.split(r"\s+and\s+", raw, flags=re.IGNORECASE)
    authors = []
    for part in parts:
        part = part.strip().rstrip(",").strip()
        if part:
            authors.append(part)
    return authors


def _parse_year(raw: str) -> int | None:
    """Extract a four-digit year from a year field.

    Args:
        raw: Raw year field value.

    Returns:
        Integer year, or None if not parseable.
    """
    match = re.search(r"(19|20)\d{2}", raw)
    if match:
        return int(match.group(0))
    return None


def find_entry_by_key(entries: list[BibEntry], key: str) -> BibEntry | None:
    """Find a BibEntry by citation key.

    Args:
        entries: List of parsed BibEntry objects.
        key: Citation key to search for (e.g. "wei2022emergent").

    Returns:
        Matching BibEntry or None.
    """
    key = key.strip()
    for entry in entries:
        if entry.key.lower() == key.lower():
            return entry
    return None


def find_entry_by_title(
    entries: list[BibEntry], title: str, threshold: float = 0.8
) -> BibEntry | None:
    """Find a BibEntry by fuzzy title matching.

    Args:
        entries: List of parsed BibEntry objects.
        title: Title string to search for (from PDF extraction).
        threshold: Minimum similarity ratio (0-1) to consider a match.

    Returns:
        Best-matching BibEntry, or None if no match exceeds threshold.
    """
    from difflib import SequenceMatcher

    cleaned_query = re.sub(r"[^a-z0-9\s]", "", title.lower())
    cleaned_query = re.sub(r"\s+", " ", cleaned_query).strip()

    best_score = 0.0
    best_entry: BibEntry | None = None

    for entry in entries:
        score = SequenceMatcher(None, cleaned_query, entry.short_title).ratio()
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_score >= threshold:
        return best_entry
    return None
