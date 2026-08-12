"""BibTeX-to-PDF cross-verification.

Compares the metadata in a .bib entry against what's actually
printed in the source PDF — catching discrepancies like:
- Wrong year in bib (Google Scholar export artifact)
- Garbled title (missing capitalization, stray LaTeX)
- Missing or wrong author order
- DOI pointing to wrong paper

These are real problems that happen constantly in academic writing.
"""

from dataclasses import dataclass, field
from enum import Enum

from .bib_parser import BibEntry


class FieldStatus(str, Enum):
    """Status of a single bib field verification."""

    MATCH = "MATCH"                   # Bib and PDF agree
    MISMATCH = "MISMATCH"             # Bib and PDF disagree — needs fixing
    PDF_MISSING = "PDF_MISSING"       # PDF didn't contain this field (parser limitation)
    BIB_MISSING = "BIB_MISSING"       # Bib entry is missing this field
    NOT_CHECKED = "NOT_CHECKED"       # Not verified (optional field, skipped)


@dataclass
class FieldResult:
    """Result of verifying a single metadata field."""

    field_name: str                     # "title", "year", "authors", "doi", "venue"
    bib_value: str                      # What the .bib says
    pdf_value: str                      # What the PDF says
    status: FieldStatus
    detail: str = ""                     # Human-readable explanation


@dataclass
class BibVerificationResult:
    """Complete result of cross-checking one bib entry against its source PDF."""

    citation_key: str
    bib_entry: BibEntry | None = None
    fields: list[FieldResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Are there any MISMATCH fields?"""
        return any(f.status == FieldStatus.MISMATCH for f in self.fields)

    @property
    def error_count(self) -> int:
        """How many fields are MISMATCH?"""
        return sum(1 for f in self.fields if f.status == FieldStatus.MISMATCH)

    @property
    def warning_count(self) -> int:
        """How many fields are missing (BIB_MISSING or PDF_MISSING)?"""
        return sum(
            1 for f in self.fields
            if f.status in (FieldStatus.BIB_MISSING, FieldStatus.PDF_MISSING)
        )

    @property
    def summary(self) -> str:
        """One-line summary of the verification."""
        if not self.bib_entry:
            return f"{self.citation_key}: No bib entry found"
        if not self.has_errors and self.warning_count == 0:
            return f"{self.citation_key}: All checked fields match ✅"
        parts = []
        if self.has_errors:
            parts.append(f"{self.error_count} mismatch(es)")
        if self.warning_count > 0:
            parts.append(f"{self.warning_count} warning(s)")
        return f"{self.citation_key}: {' ,'.join(parts)}"


# ── Metadata extracted from PDF by the parser ──────────────
# This is what Pair 1's reference_extractor + element_extractor
# produce from the first page of a source PDF.


@dataclass
class PdfMetadata:
    """Metadata extracted from a source PDF's first page."""

    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""


# ── Verification logic ──────────────────────────────────────


def verify_bib_against_pdf(
    bib_entry: BibEntry,
    pdf_meta: PdfMetadata,
) -> BibVerificationResult:
    """Cross-validate a bib entry against metadata extracted from the PDF.

    Args:
        bib_entry: Parsed BibEntry from a .bib file.
        pdf_meta: Metadata extracted from the source PDF.

    Returns:
        BibVerificationResult with per-field comparison.
    """
    result = BibVerificationResult(
        citation_key=bib_entry.key,
        bib_entry=bib_entry,
    )

    # ── Title ────────────────────────────────────────────
    result.fields.append(
        _compare_titles(bib_entry.title, pdf_meta.title)
    )

    # ── Year ─────────────────────────────────────────────
    result.fields.append(
        _compare_years(bib_entry.year, pdf_meta.year)
    )

    # ── Authors ──────────────────────────────────────────
    result.fields.append(
        _compare_authors(bib_entry.authors, pdf_meta.authors)
    )

    # ── Venue ────────────────────────────────────────────
    if bib_entry.venue or pdf_meta.venue:
        result.fields.append(
            _compare_venues(bib_entry.venue, pdf_meta.venue)
        )

    # ── DOI ──────────────────────────────────────────────
    if bib_entry.doi or pdf_meta.doi:
        result.fields.append(
            _compare_dois(bib_entry.doi, pdf_meta.doi)
        )

    return result


def _compare_titles(bib_title: str, pdf_title: str) -> FieldResult:
    """Compare bib title vs PDF title with fuzzy matching.

    Academic titles often differ subtly between bib and PDF:
    - Capitalization differences ("Emergent Abilities" vs "emergent abilities")
    - Subtitle presence ("Title: Subtitle" vs "Title")
    - LaTeX artifacts in bib (escaped underscores, braces)

    Strategy: Case-insensitive, punctuation-stripped comparison
    with a generous similarity threshold.
    """
    import re
    from difflib import SequenceMatcher

    if not bib_title:
        return FieldResult("title", bib_title, pdf_title, FieldStatus.BIB_MISSING,
                           "Bib entry has no title field.")
    if not pdf_title:
        return FieldResult("title", bib_title, pdf_title, FieldStatus.PDF_MISSING,
                           "PDF parser could not extract title.")

    def normalise(s: str) -> str:
        s = s.lower()
        s = re.sub(r"[^a-z0-9\s]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    bib_norm = normalise(bib_title)
    pdf_norm = normalise(pdf_title)

    similarity = SequenceMatcher(None, bib_norm, pdf_norm).ratio()

    # Use both sequence similarity AND Levenshtein ratio.
    # A single char typo in a long title can score >0.96 on SequenceMatcher
    # but still be a real error. Levenshtein catches these.
    from difflib import SequenceMatcher as SM

    levenshtein_ratio = 1 - _levenshtein_distance(bib_norm, pdf_norm) / max(len(bib_norm), len(pdf_norm), 1)

    if similarity >= 0.95 and levenshtein_ratio >= 0.98:
        return FieldResult("title", bib_title, pdf_title, FieldStatus.MATCH)
    elif similarity >= 0.80:
        return FieldResult(
            "title", bib_title, pdf_title, FieldStatus.MISMATCH,
            f"Titles are similar ({(similarity*100):.0f}%) but differ. "
            f"Bib: '{bib_title[:80]}...' vs PDF: '{pdf_title[:80]}...'"
        )
    else:
        return FieldResult(
            "title", bib_title, pdf_title, FieldStatus.MISMATCH,
            f"Titles are substantially different ({(similarity*100):.0f}%). "
            f"Bib may reference a different paper."
        )


def _compare_years(bib_year: int | None, pdf_year: int | None) -> FieldResult:
    """Compare bib year vs PDF year."""
    bib_str = str(bib_year) if bib_year else ""
    pdf_str = str(pdf_year) if pdf_year else ""

    if bib_year is None:
        return FieldResult("year", bib_str, pdf_str, FieldStatus.BIB_MISSING,
                           "Bib entry has no year field.")
    if pdf_year is None:
        return FieldResult("year", bib_str, pdf_str, FieldStatus.PDF_MISSING,
                           "PDF parser could not extract publication year.")

    if bib_year == pdf_year:
        return FieldResult("year", bib_str, pdf_str, FieldStatus.MATCH)

    diff = bib_year - pdf_year
    detail = (
        f"Bib says {bib_year} but PDF says {pdf_year} "
        f"(difference: {abs(diff)} year{'s' if abs(diff) > 1 else ''}). "
        f"{'Bib year is later — possibly a preprint vs published version issue.' if diff > 0 else 'Bib year is earlier — check if this is the correct edition.'}"
    )
    return FieldResult("year", bib_str, pdf_str, FieldStatus.MISMATCH, detail)


def _compare_authors(
    bib_authors: list[str], pdf_authors: list[str]
) -> FieldResult:
    """Compare author lists with fuzzy matching.

    Author names are the messiest field — abbreviations, middle names,
    different ordering conventions all cause spurious mismatches.

    Strategy: Compare last names only. If the first author and last author
    match, and the count is within 1, call it a match.
    """
    bib_str = "; ".join(bib_authors) if bib_authors else ""
    pdf_str = "; ".join(pdf_authors) if pdf_authors else ""

    if not bib_authors:
        return FieldResult("authors", bib_str, pdf_str, FieldStatus.BIB_MISSING,
                           "Bib entry has no author field.")
    if not pdf_authors:
        return FieldResult("authors", bib_str, pdf_str, FieldStatus.PDF_MISSING,
                           "PDF parser could not extract authors.")

    # Extract last names
    bib_last = _extract_last_names(bib_authors)
    pdf_last = _extract_last_names(pdf_authors)

    # Check first author
    if bib_last and pdf_last and bib_last[0] != pdf_last[0]:
        return FieldResult(
            "authors", bib_str, pdf_str, FieldStatus.MISMATCH,
            f"First author differs: Bib has '{bib_authors[0]}', "
            f"PDF first author last name is '{pdf_last[0]}'."
        )

    # Check count
    if abs(len(bib_last) - len(pdf_last)) > 1:
        return FieldResult(
            "authors", bib_str, pdf_str, FieldStatus.MISMATCH,
            f"Author count differs significantly: "
            f"Bib has {len(bib_last)}, PDF has {len(pdf_last)}."
        )

    # Check overlap
    overlap = set(bib_last) & set(pdf_last)
    if len(overlap) >= min(len(bib_last), len(pdf_last)) * 0.7:
        return FieldResult("authors", bib_str, pdf_str, FieldStatus.MATCH)

    return FieldResult(
        "authors", bib_str, pdf_str, FieldStatus.MISMATCH,
        f"Author lists differ. Bib: {len(bib_last)} authors, "
        f"PDF: {len(pdf_last)} authors. Overlap: {len(overlap)}/{min(len(bib_last), len(pdf_last))}."
    )


def _compare_venues(bib_venue: str, pdf_venue: str) -> FieldResult:
    """Compare venue/journal/booktitle fields."""
    import re
    from difflib import SequenceMatcher

    if not bib_venue:
        return FieldResult("venue", bib_venue, pdf_venue, FieldStatus.BIB_MISSING)

    if not pdf_venue:
        return FieldResult("venue", bib_venue, pdf_venue, FieldStatus.PDF_MISSING)

    def normalise(s: str) -> str:
        return re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()

    if normalise(bib_venue) == normalise(pdf_venue):
        return FieldResult("venue", bib_venue, pdf_venue, FieldStatus.MATCH)

    similarity = SequenceMatcher(None, normalise(bib_venue), normalise(pdf_venue)).ratio()
    if similarity >= 0.8:
        return FieldResult("venue", bib_venue, pdf_venue, FieldStatus.MATCH)

    return FieldResult(
        "venue", bib_venue, pdf_venue, FieldStatus.MISMATCH,
        f"Venue differs: Bib says '{bib_venue}', PDF says '{pdf_venue}'."
    )


def _compare_dois(bib_doi: str, pdf_doi: str) -> FieldResult:
    """Compare DOI fields (normalised — strip https://doi.org/ prefix)."""
    def normalise_doi(doi: str) -> str:
        doi = doi.strip().lower()
        doi = doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
        return doi

    if not bib_doi:
        return FieldResult("doi", bib_doi, pdf_doi, FieldStatus.BIB_MISSING,
                           "No DOI in bib entry. Consider adding one for traceability.")
    if not pdf_doi:
        return FieldResult("doi", bib_doi, pdf_doi, FieldStatus.PDF_MISSING,
                           "No DOI found in PDF. (May not be printed on the paper.)")

    if normalise_doi(bib_doi) == normalise_doi(pdf_doi):
        return FieldResult("doi", bib_doi, pdf_doi, FieldStatus.MATCH)

    return FieldResult(
        "doi", bib_doi, pdf_doi, FieldStatus.MISMATCH,
        f"DOI mismatch! Bib: {bib_doi}, PDF: {pdf_doi}. "
        f"Bib may be pointing to a different paper."
    )


def _extract_last_names(authors: list[str]) -> list[str]:
    """Extract last names from author strings."""
    last_names = []
    for author in authors:
        author = author.strip()
        if "," in author:
            last_names.append(author.split(",")[0].strip().lower())
        else:
            parts = author.split()
            if parts:
                last_names.append(parts[-1].strip(".,;").lower())
    return last_names


def _levenshtein_distance(a: str, b: str) -> int:
    """Compute Levenshtein (edit) distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            insert = prev[j + 1] + 1
            delete = curr[j] + 1
            replace = prev[j] + (0 if ca == cb else 1)
            curr.append(min(insert, delete, replace))
        prev = curr
    return prev[-1]
    """Extract last names from author strings.

    Handles both "Last, First" and "First Last" formats.
    """
    last_names = []
    for author in authors:
        author = author.strip()
        if "," in author:
            # "Last, First" format
            last_names.append(author.split(",")[0].strip().lower())
        else:
            # "First Last" format — take the last word
            parts = author.split()
            if parts:
                last_names.append(parts[-1].strip(".,;").lower())
    return last_names


# ── Batch verification ──────────────────────────────────────


def verify_all_entries(
    bib_entries: list[BibEntry],
    pdf_metadata_map: dict[str, PdfMetadata],
) -> list[BibVerificationResult]:
    """Verify all bib entries against their corresponding PDF metadata.

    Args:
        bib_entries: All BibEntry objects from a .bib file.
        pdf_metadata_map: Citation key → PdfMetadata from PDF parsing.

    Returns:
        List of BibVerificationResult, one per bib entry.
    """
    results: list[BibVerificationResult] = []

    for entry in bib_entries:
        pdf_meta = pdf_metadata_map.get(entry.key)
        if pdf_meta is None:
            # Try fuzzy title match as fallback
            pdf_meta = pdf_metadata_map.get(entry.key.lower())

        if pdf_meta is None:
            # Citation key not found in parsed PDFs
            results.append(BibVerificationResult(
                citation_key=entry.key,
                bib_entry=entry,
                fields=[FieldResult(
                    "all", "", "", FieldStatus.PDF_MISSING,
                    "No matching source PDF found for this citation key. "
                    "Upload the source PDF and re-run."
                )],
            ))
        else:
            results.append(verify_bib_against_pdf(entry, pdf_meta))

    return results
