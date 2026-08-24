"""Tests for atomic JSON paper metadata persistence."""

from datetime import UTC, datetime, timedelta

import pytest
from backend.src.models import PaperRecord, ParseStatus
from backend.src.storage.paper_store import (
    create_paper,
    get_paper,
    list_papers,
    update_paper,
)


def _paper_record(
    paper_id: str = "paper-1",
    *,
    created_at: datetime | None = None,
) -> PaperRecord:
    timestamp = created_at or datetime.now(UTC)
    return PaperRecord(
        paper_id=paper_id,
        original_filename="paper.pdf",
        stored_filename=f"{paper_id}.pdf",
        file_path=f"uploads/{paper_id}.pdf",
        file_type="pdf",
        file_size=42,
        title="paper",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_create_and_get_paper(tmp_path):
    papers_file = tmp_path / "papers.json"
    record = _paper_record()

    created = create_paper(record, papers_file=papers_file)
    loaded = get_paper(record.paper_id, papers_file=papers_file)

    assert created == record
    assert loaded == record


def test_list_papers_orders_newest_first(tmp_path):
    papers_file = tmp_path / "papers.json"
    now = datetime.now(UTC)
    older = _paper_record("older", created_at=now - timedelta(minutes=5))
    newer = _paper_record("newer", created_at=now)
    create_paper(newer, papers_file=papers_file)
    create_paper(older, papers_file=papers_file)

    records = list_papers(papers_file=papers_file)

    assert [record.paper_id for record in records] == ["newer", "older"]


def test_update_paper_persists_mutable_fields(tmp_path):
    papers_file = tmp_path / "papers.json"
    record = _paper_record()
    create_paper(record, papers_file=papers_file)

    updated = update_paper(
        record.paper_id,
        {
            "status": ParseStatus.COMPLETED,
            "pages": 12,
            "paragraph_count": 84,
        },
        papers_file=papers_file,
    )
    loaded = get_paper(record.paper_id, papers_file=papers_file)

    assert updated is not None
    assert updated.status == ParseStatus.COMPLETED
    assert updated.pages == 12
    assert updated.paragraph_count == 84
    assert updated.updated_at >= record.updated_at
    assert loaded == updated


def test_update_unknown_paper_returns_none(tmp_path):
    assert update_paper(
        "missing",
        {"status": ParseStatus.FAILED},
        papers_file=tmp_path / "papers.json",
    ) is None


def test_update_rejects_immutable_fields(tmp_path):
    papers_file = tmp_path / "papers.json"
    record = _paper_record()
    create_paper(record, papers_file=papers_file)

    with pytest.raises(ValueError, match="paper_id"):
        update_paper(
            record.paper_id,
            {"paper_id": "different"},
            papers_file=papers_file,
        )
