"""API contract tests use an explicit fake external adapter, never live queries."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.src.audit_models import (
    BibliographicMetadata,
    ExternalRecord,
    LookupAttempt,
    LookupResult,
)
from backend.src.main import app
from backend.src.models import PaperRecord, ParsedDocument, ParseStatus
from backend.src.routes import audit as audit_route
from backend.src.services import pipeline_service, reference_input_service
from backend.src.services.analysis_service import _find_bib_entry, _load_bibliography_entries
from backend.src.services.bibliography_audit_service import _authors_agree
from backend.src.storage.paper_store import create_paper
from backend.src.storage.reference_store import ReferenceStoreError, reference_path
from engine.bib_parser import BibEntry
from pydantic import ValidationError

BIB = b"""@article{sample,
 title={Retrieval with citations}, author={Smith, Jane},
 year={2024}, journal={Journal of Retrieval}, doi={10.1234/example}
}"""


def upload_bib(client, content=BIB):
    response = client.post("/api/parse", files={"file": ("references.bib", content, "text/plain")})
    assert response.status_code == 200
    return response.json()["paper_id"]


def external_record(**changes):
    metadata = {
        "title": "Retrieval with citations",
        "authors": ["Smith, Jane"],
        "year": 2024,
        "venue": "Journal of Retrieval",
        "doi": "10.1234/example",
    }
    metadata.update(changes)
    return ExternalRecord(
        provider="test-registry",
        record_id="test-record",
        url="https://example.org/record",
        retrieved_at=datetime.now(UTC),
        metadata=BibliographicMetadata(**metadata),
    )


def lookup_result(outcome="found", records=None):
    if records is None:
        records = [external_record()] if outcome in ("found", "ambiguous") else []
    return LookupResult(
        outcome=outcome,
        records=records,
        attempts=[LookupAttempt(provider="test-registry", outcome=outcome)],
        reason="Test registry result",
    )


class FakeLookup:
    def __init__(self, result):
        self.result = result
        self.seen = []

    def lookup(self, entry):
        self.seen.append(entry)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_no_lookup_returns_explicit_failure_without_source_pdf_and_persists(client, monkeypatch):
    monkeypatch.delattr(app.state, "bibliography_lookup", raising=False)
    paper_id = upload_bib(client)
    response = client.post("/api/audit", json={"bib_paper_id": paper_id})
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == 2
    assert body["total_entries"] == 1
    assert body["status"] == "completed_with_errors"
    row = body["results"][0]
    assert row["status"] == "LOOKUP_FAILED"
    assert row["lookup_attempts"][0]["error_code"] == "EXTERNAL_LOOKUP_NOT_CONFIGURED"
    assert row["matched_record"] is None
    assert row["field_checks"] == []
    assert not {"claim", "verdict", "confidence", "source_passage"} & row.keys()
    assert not {"supported", "partial", "contradicted"} & body.keys()
    assert client.get(f"/api/audit/{body['audit_id']}").json() == body


def test_delete_waits_for_audit_and_removes_its_late_artifacts(
    client, storage_paths, monkeypatch
):
    paper_id = upload_bib(client)
    audit_started = Event()
    release_audit = Event()
    original_run_audit = audit_route.run_bibliography_audit

    def blocked_audit(request, lookup):
        audit_started.set()
        if not release_audit.wait(timeout=5):
            raise TimeoutError("test did not release the audit")
        return original_run_audit(request, lookup)

    monkeypatch.setattr(audit_route, "run_bibliography_audit", blocked_audit)

    with ThreadPoolExecutor(max_workers=2) as pool:
        audit_future = pool.submit(
            client.post,
            "/api/audit",
            json={"bib_paper_id": paper_id},
        )
        assert audit_started.wait(timeout=5)
        delete_future = pool.submit(client.delete, f"/api/papers/{paper_id}")
        release_audit.set()
        audit_response = audit_future.result(timeout=10)
        delete_response = delete_future.result(timeout=10)

    assert audit_response.status_code == 200
    assert delete_response.status_code == 204
    audit_id = audit_response.json()["audit_id"]
    audit_path = storage_paths["parsed_dir"] / "audits" / f"{audit_id}.json"
    assert not audit_path.exists()
    assert client.get(f"/api/audit/{audit_id}").status_code == 404


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (lookup_result(), "VERIFIED"),
        (lookup_result(records=[external_record(year=2023)]), "METADATA_MISMATCH"),
        (lookup_result(records=[external_record(authors=[])]), "NEEDS_REVIEW"),
        (
            lookup_result("ambiguous", [external_record(), external_record(year=2023)]),
            "NEEDS_REVIEW",
        ),
        (lookup_result("not_found"), "NOT_FOUND"),
        (lookup_result("failed"), "LOOKUP_FAILED"),
        (TimeoutError("test timeout"), "LOOKUP_FAILED"),
    ],
)
def test_external_adapter_statuses_and_engine_field_comparison(
    client, monkeypatch, result, expected
):
    lookup = FakeLookup(result)
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    response = client.post("/api/audit", json={"bib_paper_id": upload_bib(client)})
    assert response.status_code == 200
    body = response.json()
    assert sum(body["counts"].values()) == body["total_entries"] == 1
    row = body["results"][0]
    assert row["status"] == expected
    assert lookup.seen[0].metadata.title == "Retrieval with citations"
    if expected == "METADATA_MISMATCH":
        year = next(field for field in row["field_checks"] if field["field_name"] == "year")
        assert (year["input_value"], year["source_value"], year["status"]) == (
            "2024",
            "2023",
            "MISMATCH",
        )
        assert row["matched_record"]["url"] == "https://example.org/record"
    if expected == "NOT_FOUND":
        assert "does not prove fabrication" in row["reason"]


def test_fuzzy_engine_author_match_is_not_fully_verified(client, monkeypatch):
    lookup = FakeLookup(lookup_result(records=[external_record(authors=["Smith, John"])]))
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    row = client.post("/api/audit", json={"bib_paper_id": upload_bib(client)}).json()["results"][0]
    assert row["status"] == "NEEDS_REVIEW"


def audit_pdf_reference(client, monkeypatch, storage_paths, raw_text, record):
    """Audit one PDF-shaped reference against one explicit external record."""
    record_entry = persist_manuscript(storage_paths)

    def extract(path):
        return SimpleNamespace(
            references=[SimpleNamespace(raw_text=raw_text, number=1, page_start=2, page_end=2)],
            warnings=[],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    lookup = FakeLookup(lookup_result(records=[record]))
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    body = client.post("/api/audit", json={"manuscript_id": record_entry.paper_id}).json()
    return body["results"][0]


def test_a_pdf_reference_is_compared_on_the_text_it_was_searched_with(
    client, monkeypatch, storage_paths
):
    # The corpus shape: no structured fields at all, everything in the raw text.
    # Before this change the comparison read the stored fields, so a record the
    # lookup had found was compared against empty strings: every check came back
    # INPUT_MISSING and no PDF reference could reach VERIFIED.
    row = audit_pdf_reference(
        client,
        monkeypatch,
        storage_paths,
        "[3] Devamanyu Hazarika, Soujanya Poria, Rada Mihalcea, Erik Cambria, and "
        "Roger Zimmermann. 2018. Icon: Interactive conversational memory network for "
        "multimodal emotion detection. In Proceedings of the 2018 conference on empirical "
        "methods in natural language processing.",
        external_record(
            title="Icon: Interactive conversational memory network for multimodal emotion "
            "detection",
            authors=[
                "Hazarika, Devamanyu",
                "Poria, Soujanya",
                "Mihalcea, Rada",
                "Cambria, Erik",
                "Zimmermann, Roger",
            ],
            year=2018,
            venue="Proceedings of the 2018 conference on empirical methods in natural language "
            "processing",
        ),
    )
    assert row["status"] == "VERIFIED"
    title = next(check for check in row["field_checks"] if check["field_name"] == "title")
    assert title["status"] == "MATCH"
    # The value the lookup searched on is the value compared, not the empty
    # stored field -- otherwise the report shows a comparison against nothing.
    assert title["input_value"].startswith("Icon: Interactive conversational")
    assert "raw text" in title["detail"]


def test_name_order_is_not_a_metadata_difference(client, monkeypatch, storage_paths):
    # A reference list writes "Bastian Epping"; a provider record writes
    # "Epping, Bastian". The element-wise rule this replaces compared the two
    # normalised strings, so it measured which order each source happened to use.
    row = audit_pdf_reference(
        client,
        monkeypatch,
        storage_paths,
        "[1] Bastian Epping and Michael Schaub. Graph Neural Networks Do Not Always "
        "Oversmooth. Advances in Neural Information Processing Systems, 2024.",
        external_record(
            title="Graph Neural Networks Do Not Always Oversmooth",
            authors=["Epping, Bastian", "Schaub, Michael"],
            year=2024,
            venue="Advances in Neural Information Processing Systems",
        ),
    )
    assert row["status"] == "VERIFIED"
    authors = next(check for check in row["field_checks"] if check["field_name"] == "authors")
    assert authors["status"] == "MATCH"


def test_a_recovered_field_difference_is_not_an_accusation(client, monkeypatch, storage_paths):
    # Measured over the 91 stored matched records: venue differs in 50 of them and
    # nearly every one is the reference abbreviating a venue the record spells
    # out. Reporting those as METADATA_MISMATCH told the user their reference was
    # wrong. A recovered value can withhold VERIFIED; it cannot accuse.
    row = audit_pdf_reference(
        client,
        monkeypatch,
        storage_paths,
        "[2] Jacob Devlin, Ming-Wei Chang, Kenton Lee, and Kristina Toutanova. 2019. BERT: "
        "Pre-training of Deep Bidirectional Transformers for Language Understanding. ACL.",
        external_record(
            title="BERT: Pre-training of Deep Bidirectional Transformers for Language "
            "Understanding",
            authors=[
                "Devlin, Jacob",
                "Chang, Ming-Wei",
                "Lee, Kenton",
                "Toutanova, Kristina",
            ],
            year=2019,
            venue="Proceedings of the 2019 Conference of the North American Chapter of the "
            "Association for Computational Linguistics",
        ),
    )
    assert row["status"] == "NEEDS_REVIEW"
    venue = next(check for check in row["field_checks"] if check["field_name"] == "venue")
    assert (venue["input_value"], venue["status"]) == ("ACL", "MISMATCH")
    assert "extraction rather than in the reference" in venue["detail"]


def test_a_stored_field_difference_is_still_reported_as_a_mismatch(client, monkeypatch):
    # The other half of the rule: a value the reference's own metadata states is
    # the user's, so a difference there is still the reference's difference.
    lookup = FakeLookup(lookup_result(records=[external_record(year=2023)]))
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    row = client.post("/api/audit", json={"bib_paper_id": upload_bib(client)}).json()["results"][0]
    assert row["status"] == "METADATA_MISMATCH"
    year = next(check for check in row["field_checks"] if check["field_name"] == "year")
    assert "raw text" not in year["detail"]


def test_no_doi_is_sent_to_bibliographic_lookup(client, monkeypatch):
    lookup = FakeLookup(lookup_result(records=[external_record(doi="")]))
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    paper_id = upload_bib(client, BIB.replace(b", doi={10.1234/example}", b""))
    row = client.post("/api/audit", json={"bib_paper_id": paper_id}).json()["results"][0]
    assert lookup.seen[0].metadata.doi == ""
    assert row["status"] == "VERIFIED"


def test_failed_entry_does_not_discard_other_entries(client, monkeypatch):
    class MixedLookup:
        def lookup(self, entry):
            if entry.metadata.key == "bad":
                raise TimeoutError()
            return lookup_result()

    monkeypatch.setattr(app.state, "bibliography_lookup", MixedLookup(), raising=False)
    content = BIB + BIB.replace(b"{sample,", b"{bad,")
    body = client.post("/api/audit", json={"bib_paper_id": upload_bib(client, content)}).json()
    assert [row["status"] for row in body["results"]] == ["VERIFIED", "LOOKUP_FAILED"]
    assert body["status"] == "completed_with_errors"


def persist_manuscript(storage_paths):
    path = storage_paths["upload_dir"] / "manuscript.pdf"
    path.write_bytes(b"Parser is substituted at its integration boundary in this test")
    timestamp = datetime.now(UTC)
    record = PaperRecord(
        paper_id=str(uuid4()),
        original_filename="manuscript.pdf",
        stored_filename=path.name,
        file_path=str(path),
        file_type="pdf",
        file_size=path.stat().st_size,
        status=ParseStatus.COMPLETED,
        created_at=timestamp,
        updated_at=timestamp,
    )
    create_paper(record)
    return record


def test_manuscript_reference_parser_preserves_raw_text_and_location(
    client, storage_paths, monkeypatch
):
    record = persist_manuscript(storage_paths)

    def extract(path):
        assert str(path) == record.file_path
        return SimpleNamespace(
            references=[
                SimpleNamespace(
                    raw_text="[7] Smith. Retrieval with citations. 2024.",
                    number=7,
                    page_start=4,
                    page_end=5,
                )
            ],
            warnings=["Parser sample warning"],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    lookup = FakeLookup(lookup_result())
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    body = client.post("/api/audit", json={"manuscript_id": record.paper_id}).json()
    entry = body["results"][0]["entry"]
    assert (entry["number"], entry["page_start"], entry["page_end"]) == (7, 4, 5)
    assert entry["metadata"]["title"] == ""
    assert entry["metadata"]["raw_text"].startswith("[7]")
    # This entry used to be refused before any lookup ran, because the guard
    # read the stored title -- empty for every PDF reference but one in the
    # corpus -- rather than the title the raw text yields. It is searchable now,
    # so the lookup must be reached.
    assert [seen.entry_id for seen in lookup.seen] == [body["results"][0]["entry"]["entry_id"]]
    # The point of the change: existence is now actually checked, and the record
    # that was found reaches the report.
    assert body["results"][0]["matched_record"]["metadata"]["title"] == "Retrieval with citations"
    # Still NEEDS_REVIEW, and now for a reason the report can name: the reference
    # text "[7] Smith. Retrieval with citations. 2024." leaves "2024" in the venue
    # position, and the record calls it "Journal of Retrieval". The comparison
    # reads the raw text now, so it has an opinion at all -- but a recovered value
    # disagreeing withholds VERIFIED rather than reporting a mismatch.
    assert body["results"][0]["status"] == "NEEDS_REVIEW"
    assert "Parser sample warning" in body["warnings"]


def test_a_corpus_shaped_pdf_reference_reaches_the_provider_chain(
    client, storage_paths, monkeypatch
):
    # The shape every PDF reference in the corpus actually has: no structured
    # fields at all, everything worth having in the raw text. This is the
    # regression test for the guard reading the stored title, which made the
    # whole provider chain dead code on the primary input path.
    from engine.metadata_lookup import ProviderResponse

    record = persist_manuscript(storage_paths)
    raw = (
        "[3] Devamanyu Hazarika, Soujanya Poria, Rada Mihalcea, Erik Cambria, and "
        "Roger Zimmermann. 2018. Icon: Interactive conversational memory network for "
        "multimodal emotion detection. In Proceedings of the 2018 conference on empirical "
        "methods in natural language processing, pages 2594-2604."
    )

    def extract(path):
        return SimpleNamespace(
            references=[SimpleNamespace(raw_text=raw, number=3, page_start=4, page_end=5)],
            warnings=[],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)

    seen = []

    class RecordingProvider:
        name = "openalex"

        def search(self, query, *, limit, timeout_seconds):
            seen.append(query)
            return ProviderResponse(status="ok", candidates=[])

    from backend.src.services.provider_chain_lookup import ProviderChainLookup

    monkeypatch.setattr(
        app.state,
        "bibliography_lookup",
        ProviderChainLookup([RecordingProvider()]),
        raising=False,
    )
    body = client.post("/api/audit", json={"manuscript_id": record.paper_id}).json()

    # The provider was asked, and asked with the reference as the raw text gives
    # it -- which is the only description of it that exists.
    assert len(seen) == 1
    assert seen[0].title == (
        "Icon: Interactive conversational memory network for multimodal emotion detection"
    )
    assert seen[0].authors[0] == "Devamanyu Hazarika"
    assert seen[0].year == 2018
    # A completed search that identifies nothing is NOT_FOUND, not NEEDS_REVIEW.
    assert body["results"][0]["status"] == "NOT_FOUND"
    # The attempt names the provider that answered, so a report says which
    # source was searched rather than naming the adapter that drove it.
    assert body["results"][0]["lookup_attempts"][0]["provider"] == "openalex"


def test_empty_reference_list_is_not_a_successful_audit(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(references=[], warnings=[]),
    )
    body = client.post("/api/audit", json={"manuscript_id": record.paper_id}).json()
    assert body["status"] == "needs_review"
    assert body["total_entries"] == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_pdf_metadata_reaches_the_provider_chain_and_survives_reload(
    client, storage_paths, monkeypatch, legacy
):
    from backend.src.services.provider_chain_lookup import ProviderChainLookup
    from engine.identity import PublicationCandidate
    from engine.metadata_lookup import ProviderResponse
    from parser.reference_json_extractor import parse_reference_metadata

    record = persist_manuscript(storage_paths)
    raw = '[1] J. Smith, "Retrieval with citations," Journal of Retrieval, 2024.'
    metadata = parse_reference_metadata(raw)
    if legacy:
        artifact = reference_path(record.paper_id)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({
            "source_file": record.stored_filename,
            "references": [{"raw_text": raw, "number": 1, "page_start": 2}],
        }), encoding="utf-8")

    calls = []

    def extract(path):
        calls.append(path)
        return SimpleNamespace(references=[SimpleNamespace(
            raw_text=raw, number=1, page_start=2, page_end=2,
            title=metadata.title, authors=metadata.authors, year=metadata.year,
            venue=metadata.venue, doi=metadata.doi,
        )], warnings=[])

    queries = []

    class EchoProvider:
        """Answer with the reference itself, so the search is the only variable."""

        name = "test-registry"

        def search(self, query, *, limit, timeout_seconds):
            queries.append(query)
            return ProviderResponse(status="ok", candidates=[PublicationCandidate(
                provider=self.name,
                record_id="test-record",
                title=query.title,
                authors=list(query.authors),
                year=query.year,
                venue=query.venue,
                kind="journal-article",
                doi=query.doi,
                url="https://example.org/publication",
            )])

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    monkeypatch.setattr(
        app.state, "bibliography_lookup", ProviderChainLookup([EchoProvider()]), raising=False
    )
    bodies = [client.post("/api/audit", json={"manuscript_id": record.paper_id}).json()
              for _ in range(2)]
    assert len(calls) == (0 if legacy else 1)
    # Asserted on the parsed reference rather than on a query string: what the
    # provider receives is the reference's fields, and that is the contract that
    # survives a change of provider.
    assert [(q.title, q.authors, q.year) for q in queries] == [
        ("Retrieval with citations", ["J. Smith"], 2024)
    ] * 2
    row = bodies[0]["results"][0]
    assert row["entry"]["metadata"]["authors"] == ["J. Smith"]
    assert row["entry"] == bodies[1]["results"][0]["entry"]
    assert row["status"] == "VERIFIED"
    assert row["matched_record"]["url"] == "https://example.org/publication"
    assert row["matched_record"]["provider"] == "test-registry"
    assert client.get(f"/api/audit/{bodies[0]['audit_id']}").json() == bodies[0]
    saved = json.loads(reference_path(record.paper_id).read_text(encoding="utf-8"))
    assert saved["references"][0]["title"] == "Retrieval with citations"
    assert saved["metadata_version"] == 2


def test_real_pdf_upload_to_audit(client, monkeypatch):
    """Exercise PDF conversion too; only the external providers are substituted."""
    import pymupdf
    from backend.src.services.provider_chain_lookup import ProviderChainLookup
    from engine.metadata_lookup import ProviderResponse

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Audit integration fixture", fontsize=20)
    page.insert_text((72, 110), "This synthetic document cites two publications [1], [2].")
    page = document.new_page()
    page.insert_text((72, 72), "References", fontsize=20)
    page.insert_text(
        (72, 115), '[1] J. Smith, "Retrieval with citations," Journal of Retrieval, 2024.'
    )
    page.insert_text((72, 155), '[2] A. Jones, "Citation checking," Journal of Testing, 2023.')
    content = document.tobytes()
    document.close()
    queries = []

    class EmptyProvider:
        """A source that answers every query and holds neither reference."""

        name = "test-registry"

        def search(self, query, *, limit, timeout_seconds):
            queries.append(query)
            return ProviderResponse(status="ok", candidates=[])

    monkeypatch.setattr(
        app.state, "bibliography_lookup", ProviderChainLookup([EmptyProvider()]), raising=False
    )
    upload = client.post("/api/parse", files={"file": (
        "audit-fixture.pdf", content, "application/pdf"
    )})
    assert upload.status_code == 200, upload.text
    assert upload.json()["status"] == "completed", upload.text
    response = client.post("/api/audit", json={"manuscript_id": upload.json()["paper_id"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_entries"] == 2, body
    assert [q.title for q in queries] == ["Retrieval with citations", "Citation checking"]
    # Every provider completed and neither held the work: negative evidence,
    # reported as such rather than as an unchecked reference.
    assert all(row["status"] == "NOT_FOUND" for row in body["results"])
    assert all(
        attempt["outcome"] == "not_found"
        for row in body["results"]
        for attempt in row["lookup_attempts"]
    )
    assert client.get(f"/api/audit/{body['audit_id']}").json() == body


def test_parser_dependency_error_is_explained(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)

    def extract(path):
        raise reference_input_service.AuditInputError(
            503, "REFERENCE_PARSER_UNAVAILABLE", "Not installed"
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REFERENCE_PARSER_UNAVAILABLE"


@pytest.mark.parametrize("raw_entries", [[], [{"raw_text": "Smith (2024). Example."}]])
def test_reads_parser_public_reference_json_without_reextracting(
    client,
    storage_paths,
    monkeypatch,
    raw_entries,
):
    record = persist_manuscript(storage_paths)
    artifact = reference_path(record.paper_id)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "source_file": record.stored_filename,
                "references": raw_entries,
            }
        ),
        encoding="utf-8",
    )
    # Legacy metadata enrichment needs no original PDF or Java conversion.
    Path(record.file_path).unlink()

    def unexpected_extract(path):
        pytest.fail("Persisted Reference JSON must be reused")

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", unexpected_extract)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 200
    assert response.json()["total_entries"] == len(raw_entries)
    assert json.loads(artifact.read_text(encoding="utf-8"))["metadata_version"] == 2
    if raw_entries:
        entry = response.json()["results"][0]["entry"]
        assert entry["metadata"]["raw_text"] == raw_entries[0]["raw_text"]
        assert entry["page_start"] is None
    else:
        assert response.json()["status"] == "needs_review"


def test_extracts_once_then_reuses_fields_and_warnings(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    calls = []

    def extract(path):
        calls.append(path)
        return SimpleNamespace(
            references=[
                SimpleNamespace(
                    raw_text="[7] Smith (2024). Example.",
                    number=7,
                    page_start=3,
                    page_end=4,
                )
            ],
            warnings=["Check the reference boundary"],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    bodies = [
        client.post("/api/audit", json={"manuscript_id": record.paper_id}).json() for _ in range(2)
    ]
    assert len(calls) == 1
    assert bodies[0]["results"][0]["entry"] == bodies[1]["results"][0]["entry"]
    assert bodies[0]["warnings"] == bodies[1]["warnings"]
    assert bodies[1]["results"][0]["entry"]["page_end"] == 4
    saved = json.loads(reference_path(record.paper_id).read_text(encoding="utf-8"))
    assert saved["paper_id"] == record.paper_id
    assert len(saved["source_sha256"]) == 64

    Path(record.file_path).write_bytes(b"different manuscript")
    stale = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert stale.status_code == 500
    assert stale.json()["detail"]["code"] == "REFERENCE_ARTIFACT_ERROR"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        "{}",
        '{"source_file":"manuscript.pdf","references":[{}]}',
        '{"source_file":"unrelated.pdf","references":[]}',
        '{"source_file":"manuscript.pdf","paper_id":"another-paper","references":[]}',
    ],
)
def test_bad_artifact_is_not_silently_replaced(client, storage_paths, monkeypatch, payload):
    record = persist_manuscript(storage_paths)
    artifact = reference_path(record.paper_id)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(payload, encoding="utf-8")

    def unexpected_extract(path):
        pytest.fail("A damaged artifact must not trigger a hidden re-extraction")

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", unexpected_extract)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "REFERENCE_ARTIFACT_ERROR"
    assert artifact.read_text(encoding="utf-8") == payload


def test_reference_storage_failure_is_reported(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(references=[], warnings=[]),
    )

    def fail_save(*args):
        raise ReferenceStoreError("Disk unavailable")

    monkeypatch.setattr(reference_input_service, "save_references", fail_save)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "REFERENCE_ARTIFACT_ERROR"


def test_explicit_pdf_reprocessing_invalidates_old_references(storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    artifact = reference_path(record.paper_id)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("old artifact", encoding="utf-8")

    def parse(paper_id, *args, **kwargs):
        assert not artifact.exists()
        return ParsedDocument(paper_id=paper_id, pages=1)

    monkeypatch.setattr(pipeline_service, "parse_document", parse)
    completed = pipeline_service.process_uploaded_paper(record.paper_id)
    assert completed.status == ParseStatus.COMPLETED
    assert not artifact.exists()


def test_legacy_source_ids_are_not_treated_as_existence_evidence(client):
    body = client.post(
        "/api/audit",
        json={
            "bib_paper_id": upload_bib(client),
            "source_paper_ids": ["nonexistent-pdf"],
        },
    ).json()
    assert body["results"][0]["status"] == "LOOKUP_FAILED"
    assert any("ignored" in warning for warning in body["warnings"])


@pytest.mark.parametrize(
    "body", [{}, {"bib_paper_id": "a", "manuscript_id": "b"}, {"bib_paper_id": " "}]
)
def test_audit_input_is_unambiguous(client, body):
    assert client.post("/api/audit", json=body).status_code == 422


def test_unknown_input_and_history(client):
    assert client.post("/api/audit", json={"bib_paper_id": "missing"}).status_code == 404
    assert client.get(f"/api/audit/{uuid4()}").status_code == 404
    assert client.get("/api/audit/invalid").status_code == 422


def test_failed_query_cannot_be_reported_as_not_found():
    with pytest.raises(ValidationError):
        LookupResult(
            outcome="not_found",
            reason="incorrect",
            attempts=[
                LookupAttempt(provider="test-registry", outcome="failed", error_code="TIMEOUT"),
            ],
        )


def test_claim_resolution_does_not_guess_numeric_order_or_duplicate_keys():
    entries = [BibEntry(key="one", title="First paper")]
    assert _find_bib_entry("[1]", entries) is None
    assert _find_bib_entry(r"\cite{one}", entries) is entries[0]
    assert _find_bib_entry(r"\cite{one}", entries + entries) is None
    assert _find_bib_entry(r"\cite{one,two}", entries) is None


def test_claims_do_not_combine_unrelated_bibliographies():
    records = [SimpleNamespace(file_type="bib", status=ParseStatus.COMPLETED) for _ in range(2)]
    assert _load_bibliography_entries(records) == []


@pytest.mark.parametrize(
    ("left", "right", "agree"),
    [
        # Order, on both axes, is how a source spells a name rather than what it says.
        (["Jason Wei"], ["Wei, Jason"], True),
        (["Wei, Jason", "Tay, Yi"], ["Tay, Yi", "Wei, Jason"], True),
        (["Jason Wei", "Yi Tay"], ["Tay, Yi", "Wei, Jason"], True),
        # An initial is a source abbreviating a name, not stating a different one.
        (["Wei, Jason"], ["Wei, J."], True),
        (["Vaswani, A."], ["Vaswani, Ashish"], True),
        # Diacritics and non-ASCII hyphens: one person, two spellings.
        (["Tomas Mikolov"], ["Mikolov, Tomáš"], True),
        (["Ming-Wei Chang"], ["Chang, Ming‐Wei"], True),
        # Middle names are stated on one side only.
        (["Brown, Tom B."], ["Brown, Tom"], True),
        # Different people sharing a surname are not the same author, and the count
        # is part of it: a reference that lists three authors does not name two.
        (["Smith, Jane"], ["Smith, John"], False),
        (["Smith, Jane"], ["Smith", "John"], False),
        (["Wei, Jason"], ["Tay, Yi"], False),
        (["Wei, Jason"], ["Wei, Jason", "Tay, Yi"], False),
        (["Wei, Jason"], [], False),
        ([], ["Wei, Jason"], False),
    ],
)
def test_author_agreement_reads_names_not_spellings(left, right, agree):
    assert _authors_agree(left, right) is agree


def test_author_agreement_does_not_require_a_matching_partner_to_be_adjacent():
    # "Wei, Jason" has to find its partner among the surnames still unmatched, not
    # at a fixed position, or a reordered list would be read as a disagreement.
    assert _authors_agree(
        ["Wei, Jason", "Tay, Yi", "Brown, Tom"],
        ["Brown, Tom", "Wei, Jason", "Tay, Yi"],
    )
