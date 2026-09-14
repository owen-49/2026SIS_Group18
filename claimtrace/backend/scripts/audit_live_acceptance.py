"""Run real Parser/Audit/storage with live Scholar or controlled Scholar transport.

Usage: python backend/scripts/audit_live_acceptance.py --mode controlled --output DIR
       python backend/scripts/audit_live_acceptance.py --mode live --output DIR
No production data or developer .env is used. Controlled mode replaces only the
Scholar worker's network iterator; it still runs the production worker adapter.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

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


def controlled_worker():
    """Subprocess-only transport fixtures, not another provider or API mode."""
    from backend.src.audit_models import ReferenceEntry
    from backend.src.services.google_scholar_lookup import GoogleScholarLookup
    from engine.scholar_search import scholarly

    entry = ReferenceEntry.model_validate_json(sys.stdin.buffer.read())
    title = entry.metadata.title
    if title == "Acceptance timeout fixture":
        time.sleep(60)
    if title == "Acceptance worker failure fixture":
        sys.exit(3)

    def search(*args, **kwargs):
        if title == "Acceptance rate limit fixture":
            from scholarly import DOSException

            raise DOSException("controlled acceptance rate limit")
        if title == "Acceptance absent fixture":
            return iter([])
        return iter(
            [
                {
                    "bib": {
                        "title": "Attention Is All You Need",
                        "author": ["Vaswani, A."],
                        "pub_year": "2017",
                        "venue": "NeurIPS",
                    },
                    "pub_url": "https://arxiv.org/abs/1706.03762",
                }
            ]
        )

    with patch.object(scholarly, "search_pubs", search):
        print(GoogleScholarLookup().lookup(entry).model_dump_json())


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
                "SCHOLAR_LOOKUP_TIMEOUT_SECONDS": "30",
                "SCHOLAR_LOOKUP_DELAY_SECONDS": "2" if mode == "live" else "0",
                "PYTHONPATH": os.pathsep.join(map(str, [ROOT, ROOT / "engine", ROOT / "parser"])),
            }
        )
        for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(name, None)

        from backend.src.main import app
        from backend.src.services import bounded_scholar_lookup

        original_run = subprocess.run

        def worker_run(command, **kwargs):
            if mode == "controlled" and command[1:] == ["-m", "src.services.scholar_worker"]:
                # Real child process, deadline, serialization and adapter; only
                # public Scholar responses are replaced by repeatable fixtures.
                source = kwargs["stdin"]
                payload = json.load(source)
                source.seek(0)
                if payload["metadata"]["title"] == "Acceptance timeout fixture":
                    command = [sys.executable, "-c", "import time; time.sleep(60)"]
                    kwargs["timeout"] = 0.2
                else:
                    command = [sys.executable, str(Path(__file__).resolve()), "--worker"]
            return original_run(command, **kwargs)

        reports = []
        with patch.object(bounded_scholar_lookup.subprocess, "run", worker_run):
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
            actual = [row["status"] for row in reports[0]["results"]]
            assert actual == [
                "VERIFIED",
                "METADATA_MISMATCH",
                "NOT_FOUND",
                "LOOKUP_FAILED",
                "LOOKUP_FAILED",
                "LOOKUP_FAILED",
            ], actual
            assert reports[1]["results"][0]["status"] == "NEEDS_REVIEW", reports[1]
            year = next(
                field
                for field in reports[0]["results"][1]["field_checks"]
                if field["field_name"] == "year"
            )
            assert (year["input_value"], year["source_value"], year["status"]) == (
                "2020",
                "2017",
                "MISMATCH",
            )
            evidence["expected_statuses_and_year_difference"] = "passed"
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
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=["live", "controlled"], default="controlled")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        controlled_worker()
    elif args.output:
        run(args.mode, args.output.resolve())
    else:
        parser.error(
            "--output is required; directory must contain references.bib and manuscript.pdf"
        )
