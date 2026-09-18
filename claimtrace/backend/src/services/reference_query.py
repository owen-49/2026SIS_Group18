"""Turn one stored reference entry into the query the metadata chain searches.

A reference reaches the audit with two possible descriptions of itself: the
structured fields a parser filled in, and the entry's raw text. Neither is
complete on its own, and which one is complete depends on how the paper was
loaded. Measured over the 174 reference entries stored under
``uploads/parsed``:

- The PDF path's structured fields are almost always empty -- one entry in 174
  carries a title -- because the reference-list parser implements only a couple
  of citation styles. Its raw text, on the other hand, yields a title for 173.
- The BibTeX path is the reverse. Its structured fields are complete by
  construction, while its raw text is the ``@article{...}`` block itself.

So both sources are consulted and the structured one wins where it has
something, which is why this lives in one function rather than in each caller.

Design notes:
- A raw text that is a BibTeX block is not parsed at all, and that is
  load-bearing rather than tidy. Running the reference-text parser over
  ``@article{sample, title={...}, doi={10.1234/example}}`` recovers a corrupted
  DOI (``10.1234/example}``) and splits the block's punctuation into author
  names. The corrupted DOI is the dangerous half: it silently disables
  :func:`engine.identity.select_identity`'s identifier pre-pass, because a
  normalised DOI can never equal the reference's, so the one tier that settles
  an identity outright stops firing. The junk authors displace the ranking of
  any provider given a surname hint. Skipping the parse costs nothing, since a
  BibTeX entry's structured fields are the complete description of it.
- The test for that is a prefix check on ``@`` and nothing more. A false
  positive leaves the fields to the structured values, which costs an
  abstention at worst; it can never produce a wrong query, which is the failure
  this module exists to avoid.
- Never raises. This runs over every string a PDF extractor produced.
"""

from engine.identity import ReferenceQuery
from engine.reference_text import parse_reference_text

from ..audit_models import ReferenceEntry

# What a BibTeX entry starts with. ``@string``, ``@comment`` and ``@preamble``
# are blocks of the same grammar, so one prefix covers them all.
_BIBTEX_PREFIX = "@"


def reference_query_for(entry: ReferenceEntry) -> ReferenceQuery:
    """Return the search query for one reference, from whichever source has it.

    Args:
        entry: The stored reference, carrying both the structured metadata a
            parser filled in and the entry's raw text.

    Returns:
        A :class:`engine.identity.ReferenceQuery`. Fields neither source
        supplies are left empty, and ``select_identity`` decides on whatever is
        present. Never raises.
    """
    try:
        return _build(entry)
    except Exception:
        # The helpers below are total, so this is unreachable by construction.
        # It stays because a lookup that degrades is worth more than one that
        # takes the audit down.
        return ReferenceQuery()


def _build(entry: ReferenceEntry) -> ReferenceQuery:
    metadata = entry.metadata
    parsed = _parsed(metadata.raw_text or "")
    return ReferenceQuery(
        title=(metadata.title or "").strip() or parsed.title,
        authors=list(metadata.authors) or parsed.authors,
        year=metadata.year if metadata.year is not None else parsed.year,
        venue=(metadata.venue or "").strip() or parsed.venue,
        doi=(metadata.doi or "").strip() or parsed.doi,
        # BibEntryRecord has no arXiv field, so an identifier of that kind can
        # only ever come from the raw text.
        arxiv_id=parsed.arxiv_id,
    )


def _parsed(raw_text: str) -> ReferenceQuery:
    """Parse the entry's raw text, unless it is a BibTeX block rather than one."""
    if raw_text.lstrip().startswith(_BIBTEX_PREFIX):
        return ReferenceQuery()
    return parse_reference_text(raw_text)
