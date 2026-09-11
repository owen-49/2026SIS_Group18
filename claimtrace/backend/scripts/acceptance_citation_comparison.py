"""Manual acceptance run for POST /api/verify/citation against a real LLM.

Seeds the paper library directly (bypassing PDF parsing, which is covered by
the audit pipeline's own acceptance runs) and exercises the whole comparison
chain for real: sentence-transformers embedding, FAISS retrieval, and a live
call to the provider configured in claimtrace/.env.

Run from the repository root so ``backend.src`` is importable:

    cd claimtrace && python backend/scripts/acceptance_citation_comparison.py

It never prints API keys.
"""

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# backend/ is not installed as a package, so make the repository root importable
# no matter which directory the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.src.config import get_settings  # noqa: E402
from backend.src.models import (
    BibEntryRecord,
    PaperRecord,
    ParsedBibDocument,
    ParsedDocument,
    ParsedParagraph,
    ParseStatus,
)
from backend.src.storage import (
    bib_document_store,
    paper_store,
    parsed_document_store,
)
from backend.src.storage.bib_document_store import save_bib_document
from backend.src.storage.paper_store import create_paper
from backend.src.storage.parsed_document_store import save_parsed_document
from fastapi.testclient import TestClient

SOURCE_TITLE = "Attention Is All You Need"

# A faithful excerpt of the cited paper's own wording.
SOURCE_PARAGRAPHS = [
    "We call our particular attention “Scaled Dot-Product Attention”. "
    "The input consists of queries and keys of dimension dk, and values of "
    "dimension dv.",
    "Self-attention, sometimes called intra-attention, is an attention mechanism "
    "relating different positions of a single sequence in order to compute a "
    "representation of the sequence. Self-attention has been used successfully in "
    "a variety of tasks including reading comprehension and summarization.",
    "The Transformer follows this overall architecture using stacked self-attention "
    "and point-wise, fully connected layers for both the encoder and decoder.",
    "We trained the base model for 100,000 steps or 12 hours on 8 NVIDIA P100 GPUs.",
]

CASES = [
    (
        "expect SUPPORT",
        "Self-attention is an attention mechanism that relates different positions of a "
        "single sequence in order to compute a representation of that sequence.",
    ),
    (
        "expect CONTRADICT",
        "The paper's self-attention mechanism depends on recurrence to relate different "
        "positions of a single sequence.",
    ),
    (
        "expect NOT_FOUND",
        "The paper reports that the method reduced carbon emissions by forty percent.",
    ),
]


def seed(upload_dir: Path) -> None:
    """Point the stores at a scratch library and write one source paper."""
    parsed_dir = upload_dir / "parsed"
    bib_dir = parsed_dir / "bib"

    paper_store.PAPERS_FILE = upload_dir / "papers.json"
    parsed_document_store.PARSED_DIR = parsed_dir
    bib_document_store.BIB_PARSED_DIR = bib_dir

    now = datetime.now(UTC)
    document = ParsedDocument(
        paper_id="src-transformer",
        title=SOURCE_TITLE,
        authors=["Vaswani, Ashish"],
        year=2017,
        venue="NeurIPS",
        doi="10.5555/3295222.3295349",
        pages=1,
        paragraphs=[
            ParsedParagraph(text=text, page_start=1, page_end=1)
            for text in SOURCE_PARAGRAPHS
        ],
    )
    create_paper(
        PaperRecord(
            paper_id="src-transformer",
            original_filename="attention.pdf",
            stored_filename="attention.pdf",
            file_path=str(upload_dir / "attention.pdf"),
            parsed_result_path=str(save_parsed_document(document)),
            file_type="pdf",
            file_size=1024,
            status=ParseStatus.COMPLETED,
            pages=1,
            created_at=now,
            updated_at=now,
        )
    )

    bibliography = ParsedBibDocument(
        paper_id="bib-manuscript",
        entries=[
            BibEntryRecord(
                key="vaswani2017attention",
                title=SOURCE_TITLE,
                authors=["Vaswani, Ashish"],
                year=2017,
                doi="10.5555/3295222.3295349",
            )
        ],
    )
    create_paper(
        PaperRecord(
            paper_id="bib-manuscript",
            original_filename="references.bib",
            stored_filename="references.bib",
            file_path=str(upload_dir / "references.bib"),
            parsed_result_path=str(save_bib_document(bibliography)),
            file_type="bib",
            file_size=512,
            status=ParseStatus.COMPLETED,
            pages=1,
            created_at=now,
            updated_at=now,
        )
    )


def main() -> int:
    settings = get_settings()
    print(f"provider     : {settings.llm_provider}")
    print(f"model        : {settings.llm_model_name}")
    print(f"llm ready    : {settings.is_llm_configured}")
    if not settings.is_llm_configured:
        print("No API key configured — run from the repository root so .env is found.")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        seed(Path(tmp))

        from backend.src.main import app

        with TestClient(app) as client:
            print(f"startup llm  : {type(app.state.llm_client).__name__}")
            print("-" * 78)
            for expectation, claim in CASES:
                response = client.post(
                    "/api/verify/citation",
                    json={"claim": claim, "citation_marker": r"\cite{vaswani2017attention}"},
                )
                body = response.json()
                print(f"[{expectation}]  HTTP {response.status_code}  status={body['status']}")
                print(f"  claim      : {claim[:72]}...")
                judgement = body.get("judgement")
                if judgement:
                    print(f"  verdict    : {judgement['verdict']}  ({judgement['confidence']})")
                    print(f"  rationale  : {judgement['rationale'][:200]}")
                else:
                    print(f"  message    : {body['message']}")
                for item in body.get("evidence", [])[:2]:
                    print(
                        f"  evidence   : rank={item['rank']} page={item['page']} "
                        f"sim={item['similarity']:.3f}"
                    )
                    print(f"               {item['passage_text'][:88]}...")
                print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
