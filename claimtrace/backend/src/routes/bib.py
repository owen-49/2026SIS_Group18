"""BibTeX upload, parsing, and cross-verification endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    BibEntryVerificationResult,
    BibFieldResult,
    BibFieldStatusEnum,
    BibVerifyRequest,
    BibVerifyResponse,
    ParseResponse,
    ParseStatus,
)

router = APIRouter()


@router.post("/parse/bib", response_model=ParseResponse)
async def parse_bib(request: Request):
    """Parse an uploaded .bib file and return structured entries.

    The .bib file must first be uploaded via POST /api/parse.
    This endpoint triggers the actual parsing.

    Request body: { "paper_id": "abc123" }
    """
    from fastapi import Body

    body = await request.json()
    paper_id = body.get("paper_id", "")

    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required.")

    # TODO W4: Retrieve uploaded .bib from store and parse it.
    # For now, stub response.
    return ParseResponse(
        paper_id=paper_id,
        status=ParseStatus.PENDING,
        file_type="bib",
        entry_count=0,
    )


@router.post("/verify/bib", response_model=BibVerifyResponse)
async def verify_bib(request: BibVerifyRequest, req: Request):
    """Cross-verify .bib entries against source PDF metadata.

    For each bib entry, compares title, year, authors, venue, and DOI
    against what's actually printed on the source PDF.

    Returns a per-field comparison with MATCH/MISMATCH/BIB_MISSING/PDF_MISSING status.
    """
    # ── Resolve bib entries ────────────────────────────────
    # TODO W4-W5: Fetch parsed bib entries from bib store
    # For now, demonstrate the API shape with a stub

    from engine.src.bib_parser import BibEntry
    from engine.src.bib_verifier import (
        BibVerificationResult,
        FieldResult,
        FieldStatus,
        PdfMetadata,
        verify_bib_against_pdf,
    )

    # Stub: simulate one verified entry to show the API contract
    stub_entry = BibEntry(
        key="wei2022emergent",
        entry_type="article",
        title="Emergent Abilities of Large Language Models",
        authors=["Wei, Jason", "Tay, Yi", "Bommasani, Rishi"],
        year=2022,
        venue="Transactions on Machine Learning Research",
    )

    stub_pdf_meta = PdfMetadata(
        title="Emergent Abilities of Large Language Models",
        authors=["Wei, Jason", "Tay, Yi", "Bommasani, Rishi"],
        year=2022,
        venue="Transactions on Machine Learning Research",
    )

    result = verify_bib_against_pdf(stub_entry, stub_pdf_meta)

    bib_results = [_bib_result_to_response(result)]

    return BibVerifyResponse(
        bib_paper_id=request.bib_paper_id,
        total_entries=1,
        matched_entries=1,
        error_entries=0,
        results=bib_results,
    )


def _bib_result_to_response(
    result,
) -> BibEntryVerificationResult:
    """Convert engine BibVerificationResult to API response model."""
    from engine.src.bib_verifier import BibVerificationResult

    fields = [
        BibFieldResult(
            field_name=f.field_name,
            bib_value=f.bib_value,
            pdf_value=f.pdf_value,
            status=BibFieldStatusEnum(f.status.value),
            detail=f.detail,
        )
        for f in result.fields
    ]

    return BibEntryVerificationResult(
        citation_key=result.citation_key,
        has_errors=result.has_errors,
        error_count=result.error_count,
        warning_count=result.warning_count,
        summary=result.summary,
        fields=fields,
    )
