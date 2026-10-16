"""reference_query_for reads identifiers a BibTeX entry carries in its fields."""

from backend.src.audit_models import ReferenceEntry
from backend.src.models import BibEntryRecord
from backend.src.services.reference_query import reference_query_for


def bibtex_entry(**fields):
    record = BibEntryRecord(
        key="dosovitskiy2020image",
        title="An image is worth 16x16 words",
        raw_text="@article{dosovitskiy2020image, ...}",
        **fields,
    )
    return ReferenceEntry(entry_id="e1", metadata=record, metadata_source="bibtex")


def test_arxiv_id_is_read_from_a_bibtex_journal_field():
    query = reference_query_for(bibtex_entry(venue="arXiv preprint arXiv:2010.11929"))
    assert query.arxiv_id == "2010.11929"


def test_arxiv_id_is_read_from_an_arxiv_doi():
    query = reference_query_for(bibtex_entry(doi="10.48550/arXiv.2010.11929"))
    assert query.arxiv_id == "2010.11929"


def test_a_conference_venue_carries_no_arxiv_id():
    venue = "International Conference on Learning Representations"
    query = reference_query_for(bibtex_entry(venue=venue))
    assert query.arxiv_id == ""
