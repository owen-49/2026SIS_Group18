"""Run real Parser/Audit/storage with live or controlled metadata providers.

Usage: python backend/scripts/audit_live_acceptance.py --mode controlled --output DIR
       python backend/scripts/audit_live_acceptance.py --mode live --output DIR
No production data or developer .env is used. Controlled mode replaces only the
bytes each provider's HTTP request receives; the provider, the URL it builds,
the response mapper, the identity rules, the adapter and storage all stay real.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "parser")]


def verify_process_restart(reports):
    """Reload reports over HTTP in a new uvicorn process from backend/ cwd."""
    import httpx

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT / "backend",
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                deadline = time.monotonic() + 60
                while True:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read().decode(errors="replace"))
                    try:
                        if client.get("/health", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() >= deadline:
                        raise TimeoutError("uvicorn startup exceeded 60 seconds")
                    time.sleep(0.25)
                for report in reports:
                    result = client.get("/api/audit/" + report["audit_id"])
                    result.raise_for_status()
                    assert result.json() == report
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


# ── Controlled transport ─────────────────────────────────────────────────────
#
# Fixtures replace the bytes each provider's request receives, and nothing else:
# the provider builds its own URL, maps its own response and applies the real
# identity rules, so a fixture that stops matching the API's shape fails here
# rather than passing quietly.
#
# Both providers are patched at the name they imported, because each does
# ``from .metadata_lookup import http_get_json``. Patching
# ``engine.metadata_lookup.http_get_json`` instead would leave both providers
# calling the real function and silently reach the network.

# The work the fixtures hold. The provider spells the author "Family, Given",
# while the two fixtures below cite the same work in the other order -- the
# BibTeX entry as "Vaswani, A." and the PDF entry as "A. Vaswani". Both verify.
# compare_external_metadata's exact gate reads an author's surname and the given
# names the reference states, so the order a source happens to write a name in,
# and whether it abbreviates the given name, are not differences -- which keeps
# the fixture's outcome a property of the reference's content rather than of the
# spelling convention its loader used. Spelling both fixtures differently is
# deliberate: it is what holds that.
_OPENALEX_WORK = {
    "id": "https://openalex.org/W2963403868",
    "doi": "https://doi.org/10.48550/arxiv.1706.03762",
    "title": "Attention Is All You Need",
    "display_name": "Attention Is All You Need",
    "publication_year": 2017,
    "type": "article",
    "authorships": [{"author": {"display_name": "Vaswani, A."}}],
    "primary_location": {
        "landing_page_url": "https://arxiv.org/abs/1706.03762",
        "source": {"display_name": "NeurIPS"},
    },
}

_CROSSREF_ITEM = {
    "DOI": "10.48550/arxiv.1706.03762",
    "URL": "https://arxiv.org/abs/1706.03762",
    "title": ["Attention Is All You Need"],
    "author": [{"given": "A.", "family": "Vaswani"}],
    "issued": {"date-parts": [[2017]]},
    "container-title": ["NeurIPS"],
    "type": "proceedings-article",
}

_ABSENT = "Acceptance absent fixture"
_TIMEOUT = "Acceptance timeout fixture"
_FAILURE = "Acceptance worker failure fixture"
_RATE_LIMIT = "Acceptance rate limit fixture"
_MATCHING = "Attention Is All You Need"


def _queried_title(url: str) -> str:
    """Return the reference title a provider's request URL is asking about."""
    params = parse_qs(urlsplit(url).query)
    asked = " ".join(params.get("filter", []) + params.get("query.bibliographic", []))
    for title in (_MATCHING, _ABSENT, _TIMEOUT, _FAILURE, _RATE_LIMIT):
        if title in asked:
            return title
    return ""


def controlled_http_get_json(provider):
    """Return a stand-in for one provider's ``http_get_json``."""
    from engine.metadata_lookup import HttpResult

    def fake(url, **kwargs):
        title = _queried_title(url)
        if title == _TIMEOUT:
            return HttpResult(status_code=0, error="request failed: timed out")
        if title == _FAILURE:
            return HttpResult(status_code=500, error="HTTP 500 Internal Server Error")
        if title == _RATE_LIMIT:
            return HttpResult(status_code=429, error="HTTP 429 Too Many Requests")
        if title == _MATCHING:
            body = (
                {"results": [_OPENALEX_WORK]}
                if provider == "openalex"
                else {"message": {"items": [_CROSSREF_ITEM]}}
            )
            return HttpResult(status_code=200, body=body)
        # The absent fixture, and anything the fixtures do not know: an API
        # answer that holds no such record.
        body = {"results": []} if provider == "openalex" else {"message": {"items": []}}
        return HttpResult(status_code=200, body=body)

    return fake


def run(mode, output):
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    output.mkdir(parents=True, exist_ok=True)
    evidence = {"mode": mode, "started_at": datetime.now(UTC).isoformat(), "cases": []}
    with tempfile.TemporaryDirectory(prefix="audit-live-acceptance-") as temporary:
        upload = Path(temporary) / "new-parent" / "uploads"
        os.environ.update(
            {
                "CLAIMTRACE_ENV_FILE": os.devnull,
                "UPLOAD_DIR": str(upload),
                "PAPERS_FILE": str(upload / "papers.json"),
                "PARSED_DIR": str(upload / "parsed"),
                "PARSER_HYBRID": "off",
                "CLAIMTRACE_LLM_PROVIDER": "openai",
                "METADATA_LOOKUP_TIMEOUT_SECONDS": "30",
                "PYTHONPATH": os.pathsep.join(map(str, [ROOT, ROOT / "engine", ROOT / "parser"])),
            }
        )
        for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(name, None)

        import engine.crossref_lookup
        import engine.openalex_lookup
        from backend.src.main import app

        # Both names, because each provider imported the function into its own
        # namespace. See the note above controlled_http_get_json. Live mode
        # patches nothing and reaches the real APIs.
        if mode == "controlled":
            transports = (
                patch.object(
                    engine.openalex_lookup,
                    "http_get_json",
                    controlled_http_get_json("openalex"),
                ),
                patch.object(
                    engine.crossref_lookup,
                    "http_get_json",
                    controlled_http_get_json("crossref"),
                ),
            )
        else:
            transports = (nullcontext(),)

        reports = []
        with ExitStack() as stack:
            for transport in transports:
                stack.enter_context(transport)
            with TestClient(app) as client:
                assert client.get("/health").json()["status"] == "ok"
                evidence["startup"] = "passed: fresh nested upload directory"
                fixtures = [("bib", output / "references.bib"), ("pdf", output / "manuscript.pdf")]
                for kind, path in fixtures:
                    started = time.monotonic()
                    response = client.post(
                        "/api/parse", files={"file": (path.name, path.read_bytes())}
                    )
                    response.raise_for_status()
                    parsed = response.json()
                    assert parsed["status"] == "completed", parsed
                    parse_state = client.get("/api/parse/" + parsed["paper_id"])
                    assert parse_state.status_code == 200
                    assert parse_state.json()["status"] == "completed"
                    request = {
                        "bib_paper_id" if kind == "bib" else "manuscript_id": parsed["paper_id"]
                    }
                    response = client.post("/api/audit", json=request)
                    response.raise_for_status()
                    report = response.json()
                    (output / (mode + "-" + kind + "-response.json")).write_text(
                        json.dumps(report, indent=2) + "\n", encoding="utf-8"
                    )
                    assert report["contract_version"] == 2
                    assert report["total_entries"] == len(report["results"]) > 0, report
                    assert sum(report["counts"].values()) == report["total_entries"]
                    assert client.get("/api/audit/" + report["audit_id"]).json() == report
                    reports.append(report)
                    evidence["cases"].append(
                        {
                            "input": path.name,
                            "parse": parsed,
                            "audit_request": request,
                            "audit": report,
                            "elapsed_seconds": round(time.monotonic() - started, 2),
                        }
                    )
                assert client.post("/api/audit", json={}).status_code == 422
                assert (
                    client.post(
                        "/api/audit", json={"bib_paper_id": "x", "manuscript_id": "y"}
                    ).status_code
                    == 422
                )
                assert (
                    client.post(
                        "/api/parse", files={"file": ("broken.pdf", b"not a PDF")}
                    ).status_code
                    == 415
                )
                evidence["invalid_requests"] = {
                    "empty_audit": 422,
                    "two_inputs": 422,
                    "invalid_pdf": 415,
                }
            # A fresh lifespan/client uses the same on-disk store, not a response cache.
            with TestClient(app) as client:
                for report in reports:
                    assert client.get("/api/audit/" + report["audit_id"]).json() == report
                    saved = upload / "parsed" / "audits" / (report["audit_id"] + ".json")
                    assert json.loads(saved.read_text(encoding="utf-8")) == report
                evidence["retrieval_after_lifespan_restart"] = True
        verify_process_restart(reports)
        evidence["retrieval_after_process_restart_over_http"] = True
        if mode == "controlled":
            provider_report = reports[0]
            assert [row["status"] for row in provider_report["results"]] == [
                "VERIFIED",
                "NOT_FOUND",
                "NOT_FOUND",
                "LOOKUP_FAILED",
                "LOOKUP_FAILED",
                "LOOKUP_FAILED",
            ], [row["status"] for row in provider_report["results"]]
            # The second entry differs from the first only by its year, and the
            # identity rules reject the record outright rather than matching it
            # and reporting a field difference: abs(2020 - 2017) > YEAR_TOLERANCE.
            # So it never reaches a comparison, and no field checks exist for it.
            assert provider_report["results"][1]["field_checks"] == []
            assert "No acceptable record" in provider_report["results"][1]["reason"]
            # Each failure names the provider and the reason, so a reader can
            # tell a throttled source from a broken one from an absent record.
            codes = [
                (row["lookup_attempts"][0]["provider"], row["lookup_attempts"][0]["error_code"])
                for row in provider_report["results"][3:]
            ]
            assert codes == [
                ("openalex", "OPENALEX_TRANSPORT"),
                ("openalex", "OPENALEX_HTTP_500"),
                ("openalex", "OPENALEX_RATE_LIMITED"),
            ], codes
            # The PDF fixture's first reference resolves and its second is
            # rejected on the year, exactly as above. The first one verifies
            # although it spells the author "A. Vaswani" where the provider
            # writes "Vaswani, A.": the exact gate reads an author's surname and
            # the given names the reference states, so name order and an
            # abbreviated given name are not metadata differences.
            assert [row["status"] for row in reports[1]["results"]] == [
                "VERIFIED",
                "NOT_FOUND",
            ], [row["status"] for row in reports[1]["results"]]
            assert reports[1]["results"][0]["matched_record"]["provider"] == "openalex"
            evidence["expected_statuses_and_year_rejection"] = "passed"
    (output / (mode + "-evidence.json")).write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "mode": mode,
                "statuses": [
                    [r["status"] for r in c["audit"]["results"]] for c in evidence["cases"]
                ],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "controlled"], default="controlled")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        run(args.mode, args.output.resolve())
    else:
        parser.error(
            "--output is required; directory must contain references.bib and manuscript.pdf"
        )
