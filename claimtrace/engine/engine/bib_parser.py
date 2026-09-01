"""BibTeX (.bib) file parser.

Parses bibliography files into structured BibEntry objects,
enabling cross-validation between what the .bib claims and
what the actual source PDF contains.

Handles common BibTeX quirks:
- @string macros and # concatenation
- @comment entries (silently skipped)
- Unescaped special characters (%, $, &, #, _, ~)
- LaTeX diacritics (umlauts, acute accents, tilde, etc.)
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
        return [_extract_last_name(a) for a in self.authors]

    @property
    def first_author_last_name(self) -> str:
        """Return the first author's last name (lowercase)."""
        if not self.authors:
            return ""
        return _extract_last_name(self.authors[0])

    @property
    def short_title(self) -> str:
        """Return title with case normalised and punctuation stripped."""
        return re.sub(r"[^a-z0-9\s]", "", self.title.lower())


# ── Public API ────────────────────────────────────────────────


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

    Supports @string macros, # concatenation, and skips @comment entries.

    Args:
        text: Raw BibTeX content as a string.

    Returns:
        List of BibEntry objects.
    """
    entries: list[BibEntry] = []
    strings: dict[str, str] = {}  # @string macro definitions

    # Find each @type{...} entry using brace counting.
    # Regex can't handle nested braces in BibTeX values.
    i = 0
    while i < len(text):
        # Find next @ that starts an entry
        at_pos = text.find("@", i)
        if at_pos == -1:
            break

        # Extract entry type
        match = re.match(r"@(\w+)\s*\{\s*", text[at_pos:])
        if not match:
            i = at_pos + 1
            continue

        entry_type = match.group(1).lower()
        brace_start = at_pos + match.end()  # position right after opening {

        # Find the closing brace for the whole entry
        depth = 1
        close_pos = brace_start
        while close_pos < len(text) and depth > 0:
            ch = text[close_pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            close_pos += 1

        body_text = text[brace_start:close_pos].strip()

        # ── Handle special entry types ──────────────────────
        if entry_type == "comment":
            # Silently skip @comment entries
            i = close_pos + 1
            continue

        if entry_type == "string":
            # @string{name = "value"} or @string{name = {value}}
            _store_string_macro(strings, body_text)
            i = close_pos + 1
            continue

        # ── Regular entry: extract citation key ─────────────
        # Key is everything up to the first comma not inside braces
        depth = 1
        key_end = 0
        while key_end < len(body_text) and depth > 0:
            ch = body_text[key_end]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            elif ch == "," and depth == 1:
                break
            key_end += 1

        key = body_text[:key_end].strip()
        fields_text = body_text[key_end + 1:].strip() if key_end < len(body_text) else ""

        entry = _parse_fields(entry_type, key, fields_text, strings)
        entry.raw_text = text[at_pos : close_pos + 1]
        entries.append(entry)

        i = close_pos + 1

    return entries


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


# ── Internal: @string macros ──────────────────────────────────


def _store_string_macro(strings: dict[str, str], body_text: str) -> None:
    """Extract and store an @string macro definition.

    Handles both formats:
        @string{KEY = "value"}
        @string{KEY = {value}}
    """
    # Find the = sign — split into name and value
    eq_pos = body_text.find("=")
    if eq_pos == -1:
        return

    macro_name = body_text[:eq_pos].strip()
    value_text = body_text[eq_pos + 1:].strip()

    # Strip delimiters
    if value_text.startswith('"') and value_text.endswith('"'):
        value_text = value_text[1:-1]
    elif value_text.startswith("{") and value_text.endswith("}"):
        value_text = value_text[1:-1]

    if macro_name:
        strings[macro_name.lower()] = value_text.strip()


# ── Internal: field parsing ───────────────────────────────────


def _parse_fields(
    entry_type: str, key: str, fields_text: str, strings: dict[str, str] | None = None
) -> BibEntry:
    """Parse field-value pairs from a BibTeX entry's content.

    Args:
        entry_type: The BibTeX entry type (article, inproceedings, etc.).
        key: The citation key.
        fields_text: Raw text between the outer braces.
        strings: Optional @string macro dictionary for expansion.

    Returns:
        BibEntry with extracted fields.
    """
    if strings is None:
        strings = {}

    entry = BibEntry(key=key, entry_type=entry_type)

    # Parse fields using brace counting (handles nested braces in LaTeX values)
    i = 0
    while i < len(fields_text):
        # Find next "fieldname ="
        fmatch = re.match(r"\s*(\w+)\s*=\s*", fields_text[i:])
        if not fmatch:
            i += 1
            continue

        field_name = fmatch.group(1).lower().strip()
        i += fmatch.end()

        # Extract possibly concatenated value
        field_value = _extract_concat_value(fields_text, i, strings)
        if field_value is None:
            break
        i = field_value[1]  # update position from returned index

        value = field_value[0]

        # Normalise whitespace
        value = re.sub(r"\s+", " ", value).strip()

        if field_name == "title":
            entry.title = _clean_title(value)
        elif field_name == "author":
            entry.authors = _parse_authors(value)
        elif field_name == "year":
            entry.year = _parse_year(value)
        elif field_name in ("journal", "booktitle"):
            entry.venue = value
        elif field_name == "volume":
            entry.volume = value
        elif field_name == "number":
            entry.number = value
        elif field_name == "pages":
            entry.pages = value
        elif field_name == "doi":
            entry.doi = value
        elif field_name == "url":
            entry.url = value
        elif field_name == "publisher":
            entry.publisher = value

    return entry


def _extract_concat_value(
    text: str, start: int, strings: dict[str, str]
) -> tuple[str, int] | None:
    """Extract a field value that may use # concatenation.

    Handles:
        "text"
        {text}
        macro_name
        "text" # macro_name
        macro_name # "text"
        "text" # macro_name # "more text"

    Args:
        text: The full fields text.
        start: Position to start extracting from.
        strings: @string macro dictionary.

    Returns:
        Tuple of (concatenated_value, new_position), or None on failure.
    """
    parts: list[str] = []
    i = start
    first = True

    while i < len(text):
        # Skip whitespace
        while i < len(text) and text[i] in (" ", "\t", "\n", "\r"):
            i += 1

        if i >= len(text):
            break

        ch = text[i]

        if ch == "," and first:
            # Empty value
            i += 1
            break

        if ch == ",":
            # End of this field
            i += 1
            break

        if ch == "#":
            # Concatenation operator — continue to next part
            if not first:
                i += 1
                continue
            else:
                # # at start of value is unusual, skip
                i += 1
                continue

        if ch in ('"', "{"):
            # Delimited value
            delim = ch
            close_delim = "}" if delim == "{" else '"'
            i += 1  # skip opening delimiter

            value_start = i
            if delim == "{":
                depth = 1
                while i < len(text) and depth > 0:
                    c = text[i]
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    i += 1
            else:
                # Quoted value — find closing "
                while i < len(text) and text[i] != '"':
                    if text[i] == "\\":
                        i += 1  # skip escaped char
                    i += 1

            part_value = text[value_start:i]
            # Preserve spaces within concatenated parts — only trim newlines/tabs
            part_value = part_value.strip("\r\n\t")
            parts.append(part_value)
            i += 1  # skip closing delimiter
            first = False

        elif re.match(r"[a-zA-Z]", ch):
            # Macro name (unquoted reference to @string)
            m = re.match(r"([a-zA-Z_]\w*)", text[i:])
            if m:
                macro_name = m.group(1).lower()
                expanded = strings.get(macro_name, m.group(1))
                parts.append(expanded)
                i += len(m.group(1))
                first = False
            else:
                i += 1
        else:
            # Unknown, skip
            i += 1

    return ("".join(parts), i)


# ── Internal: title cleaning ──────────────────────────────────


# Mapping of LaTeX diacritic commands to plain characters.
# We strip the command and keep the base letter for matching purposes.
_LATEX_DIACRITICS = re.compile(
    r"""\\["'`^~Hckbduvr]\{[a-zA-Z]\}"""  # \"{o}, \'{e}, \~{n}, \^{o}, etc.
    r"""|\\[a-zA-Z]+\{([^}]*)\}"""          # \textit{...}, \textbf{...}, etc.
    r"""|\\[a-zA-Z]+\s+[a-zA-Z]"""          # \emph text (rare, no braces)
    r"""|\\[^a-zA-Z]"""                      # \&, \$, \#, \_, \%, etc.
)


def _clean_title(raw: str) -> str:
    """Normalise a BibTeX title field.

    Removes LaTeX commands, diacritics, extra braces, and normalises whitespace.
    Also handles TeX ligatures: -- → en-dash, --- → em-dash.
    """
    # Replace TeX dashes
    cleaned = raw.replace("---", "\u2014").replace("--", "\u2013")

    # Remove LaTeX diacritic commands, keeping the base letter
    # \"{o} → o, \'{e} → e, \~{n} → n, \^{o} → o
    cleaned = re.sub(
        r"""\\["'`^~Hckbduvr]\{([a-zA-Z])\}""",
        r"\1",
        cleaned,
    )

    # Remove LaTeX commands with brace groups: \textit{...} → content
    cleaned = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", cleaned)

    # Remove LaTeX commands with space-separated arg: \emph Word → Word
    cleaned = re.sub(r"\\[a-zA-Z]+\s+([a-zA-Z])", r"\1", cleaned)

    # Remove LaTeX special character escapes: \& → &, \$ → $, etc.
    cleaned = re.sub(r"\\([&$#_%{}])", r"\1", cleaned)

    # Remove stray braces (common in BibTeX for preserving case: {T}itle)
    cleaned = cleaned.replace("{", "").replace("}", "")

    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ── Internal: author parsing ──────────────────────────────────


def _parse_authors(raw: str) -> list[str]:
    """Parse the author field into individual names.

    Handles:
    - "Last, First and Last, First"
    - "First Last and First Last"
    - "Last, First and First Last" (mixed — Google Scholar's favorite)

    Names are normalized to "Last, First" format.

    Args:
        raw: Raw author field string.

    Returns:
        List of author name strings in "Last, First" format.
    """
    # Split on " and " (case-insensitive)
    parts = re.split(r"\s+and\s+", raw, flags=re.IGNORECASE)
    authors = []
    for part in parts:
        part = part.strip().rstrip(",").strip()
        if part:
            authors.append(_normalize_author_name(part))
    return authors


def _normalize_author_name(raw: str) -> str:
    """Normalize a single author name to 'Last, First' format.

    Args:
        raw: A single author name string.

    Returns:
        Name in "Last, First" format.
    """
    if "," in raw:
        # Already "Last, First" or "Last, First Middle"
        return raw

    # "First Middle Last" format — extract last name
    parts = raw.split()
    if len(parts) == 1:
        return raw
    # Last word is the last name
    last = parts[-1]
    first = " ".join(parts[:-1])
    return f"{last}, {first}"


def _extract_last_name(author: str) -> str:
    """Extract just the last name from an author string.

    Handles both "Last, First" and "First Last" formats.
    """
    author = author.strip()
    if "," in author:
        # "Last, First" format
        return author.split(",")[0].strip().lower()
    else:
        # "First Last" format — take the last word
        parts = author.split()
        if parts:
            return parts[-1].strip(".,;").lower()
    return author.lower()


# ── Internal: year parsing ────────────────────────────────────


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
