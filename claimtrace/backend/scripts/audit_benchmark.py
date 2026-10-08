"""Run the bibliography Audit against constructed references and pinned provider bytes.

Usage: python backend/scripts/audit_benchmark.py --mode replay
       python backend/scripts/audit_benchmark.py --mode record

The controlled tier answers one question: given a reference and the records the
providers returned for it, does the audit reach the state the contract says it
should? Both halves are held still. The reference is authored in
``tests/benchmarks/audit_cases.json`` together with the state its construction
implies, and the records are the bytes the live APIs returned for that
reference's query, frozen under ``tests/benchmarks/audit_responses``.

Design notes:
- The transport replaces ``http_get_json`` in the module each provider imported
  it into -- the same seam ``audit_live_acceptance.py`` uses, and for the same
  reason. Patching ``engine.metadata_lookup.http_get_json`` instead would leave
  both providers calling the real function and silently reach the network.
- **An unpinned URL does not become an empty result, and a run with one is not
  scored.** Answering a request the fixture does not recognise with "no records"
  turns a fixture that stopped matching into a clean-looking ``NOT_FOUND``, which
  is the one failure this instrument exists to catch. A miss is answered with a
  transport failure instead, and :func:`run` then discards the whole run's
  results: a fixture with a gap reports the gap and nothing else.
  The miss is answered rather than raised because raising ended the run. It
  escaped through the route and the test client, came back as a ``CancelledError``
  from the client's shutdown, and reported the first missing URL and none of the
  others; answering collects them all in one pass, which is what makes a gap
  fixable in one edit rather than one edit per run.
- ``--mode record`` re-requests whatever the run asks for and **refuses to
  overwrite a capture whose bytes differ**. The recorded bytes are what a case's
  expected state was derived from, so a provider that changed its answer changes
  the case's meaning; that is a decision for a person, not a silent overwrite.
  A pin whose ``source`` is ``injected`` is never touched: it is a deliberate
  hand-written edit to a recorded answer, not a recording.
- Replay drives the real HTTP route through ``TestClient`` rather than calling
  the service directly, so the request model, the reference store and the audit
  route are inside the measurement rather than assumed. The application is
  imported after the environment points at a temporary store, which is why this
  has to run as its own process; :func:`_assert_environment` checks that it did.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "parser")]

from backend.scripts import audit_eval  # noqa: E402
from engine import crossref_lookup, openalex_lookup  # noqa: E402

CASE_FILE = ROOT / "backend" / "tests" / "benchmarks" / "audit_cases.json"
RESPONSE_DIR = ROOT / "backend" / "tests" / "benchmarks" / "audit_responses"

PROVIDERS = ("openalex", "crossref")

# The synthetic manuscript that carries the PDF-shaped cases. A fixed UUID
# because the reference store names its artifact after the paper id, and writing
# that artifact by hand is the point: those cases are about how the audit reads
# recovered metadata, not about whether the reference parser can read a PDF,
# which needs Java and is measured elsewhere.
MANUSCRIPT_ID = "a1d0f5c0-6c11-4c8e-9c2f-0000000000b1"
MANUSCRIPT_NAME = "audit-benchmark-manuscript.pdf"


@dataclass
class Pin:
    """One recorded provider response, keyed by the URL that asked for it."""

    url: str
    provider: str
    source: str
    status_code: int
    body: Any = None
    error: str = ""
    captured_at: str = ""
    note: str = ""
    path: Path | None = None

    @property
    def injected(self) -> bool:
        """Whether a person wrote this outcome rather than a provider returning it."""
        return self.source == "injected"

    @property
    def not_an_answer(self) -> bool:
        """Whether the network failed rather than the provider answering.

        ``http_get_json`` reports an HTTP error status, an unreachable host, a
        timeout and an unreadable body all by setting ``error``, and leaves it
        empty on a body it could parse -- including the 404 that means "no such
        record". So an empty error is exactly "the provider answered", which is
        what a case's expected state has to be derived from.
        """
        return bool(self.error)


@dataclass
class Case:
    """One case: the scorer's half of it, plus the input it is built from."""

    scored: audit_eval.AuditCase
    bib_source: str = ""
    reference: dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return self.scored.case_id

    @property
    def input_kind(self) -> str:
        return self.scored.input_kind


@dataclass
class RunReport:
    """Everything one replay produced, so a caller can print or persist it."""

    forms: list[tuple[str, list[audit_eval.AuditCase], Any]] = field(default_factory=list)
    pins_total: int = 0
    pins_used: list[str] = field(default_factory=list)
    pins_unused: list[str] = field(default_factory=list)
    pins_missing: list[str] = field(default_factory=list)
    sources: dict[str, int] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    """Every provider request in the order it was made, repeats kept.

    ``pins_used`` answers "which of the fixture's answers did this run need";
    this answers "how many requests did the chain actually make", which is the
    short-circuit evidence: a reference OpenAlex settles costs one request, and a
    run where every reference costs two is a run where nothing short-circuited.
    """


# ── The case file ─────────────────────────────────────────────────


def load_benchmark_cases(path: Path) -> list[Case]:
    """Load the case file: the scorer's half, plus the input each case is built from.

    :func:`audit_eval.load_cases` owns the annotation half --- the expected state
    and the join key --- and is called rather than re-implemented so the
    annotation rules live in one place. This adds the input half, and the checks
    that only make sense across cases: two cases claiming one join key would
    score each other's results.
    """
    scored = audit_eval.load_cases(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("cases") if isinstance(payload, dict) else payload
    by_id = {str(item.get("case_id", "")).strip(): item for item in items}
    cases = []
    for case in scored:
        item = by_id.get(case.case_id)
        if item is None:
            raise ValueError(f"{path}: no input block for case {case.case_id}")
        cases.append(
            Case(
                scored=case,
                bib_source=str(item.get("bib_source", "")),
                reference=item.get("reference") or {},
            )
        )
    _check_joins(cases, path)
    return cases


def _check_joins(cases: list[Case], path: Path) -> None:
    """Assert each case's input can reach exactly one result in the response."""
    seen_keys: dict[str, str] = {}
    for case in cases:
        if case.input_kind == "bib":
            if not case.bib_source.strip():
                raise ValueError(f"{path}: case {case.case_id} is a bib case with no source")
            if not case.bib_source.lstrip().startswith("@"):
                raise ValueError(
                    f"{path}: case {case.case_id} has a bib_source that is not a BibTeX block"
                )
            if not case.scored.bib_key:
                raise ValueError(f"{path}: case {case.case_id} is a bib case with no bib_key")
            if case.scored.bib_key in seen_keys:
                raise ValueError(
                    f"{path}: cases {seen_keys[case.scored.bib_key]} and {case.case_id} share "
                    f"the BibTeX key {case.scored.bib_key!r}; the join is ambiguous"
                )
            seen_keys[case.scored.bib_key] = case.case_id
        elif case.input_kind == "pdf":
            if not case.reference.get("raw_text"):
                raise ValueError(f"{path}: case {case.case_id} has no reference raw_text")
            needle = case.scored.raw_text_contains
            if not needle:
                raise ValueError(f"{path}: case {case.case_id} is a pdf case with no needle")
            for other in cases:
                if other.case_id != case.case_id and needle in str(
                    other.reference.get("raw_text", "")
                ):
                    raise ValueError(
                        f"{path}: case {case.case_id}'s needle also selects {other.case_id}"
                    )
        else:
            raise ValueError(f"{path}: case {case.case_id} has input_kind {case.input_kind!r}")


def bib_document(cases: list[Case]) -> str:
    """The .bib file the bib-form cases are uploaded as."""
    blocks = [case.bib_source.strip() for case in cases if case.input_kind == "bib"]
    return "\n\n".join(blocks) + "\n"


# ── The pinned responses ──────────────────────────────────────────


def load_pins(directory: Path) -> dict[str, Pin]:
    """Load every recorded response, keyed by the URL that asked for it."""
    pins: dict[str, Pin] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        url = str(payload.get("url", "")).strip()
        if not url:
            raise ValueError(f"{path}: a recorded response has no url")
        provider = str(payload.get("provider", "")).strip()
        if provider not in PROVIDERS:
            raise ValueError(f"{path}: provider {provider!r} is not one of {', '.join(PROVIDERS)}")
        if url in pins:
            raise ValueError(f"{path}: {pins[url].path.name} already records {url}")
        pins[url] = Pin(
            url=url,
            provider=provider,
            source=str(payload.get("source", "captured")),
            status_code=int(payload["status_code"]),
            body=payload.get("body"),
            error=str(payload.get("error", "")),
            captured_at=str(payload.get("captured_at", "")),
            note=str(payload.get("note", "")),
            path=path,
        )
    return pins


def transport(provider: str, pins: dict[str, Pin], misses: list[str], latency: float = 0.0):
    """Return a stand-in for one provider's ``http_get_json`` over the pins.

    A URL the fixture does not hold is answered with a failure, not with "no
    records". The distinction is the whole point of the stand-in: an empty
    result turns a fixture that stopped matching into a clean-looking
    ``NOT_FOUND``, which is the one failure this instrument exists to catch,
    while a failure leaves the case unable to reach any verdict at all.

    It is answered rather than raised so that one missing pin does not end the
    run. Raised, it escaped through the route and the test client and came back
    as a ``CancelledError`` from the client's shutdown, after the first miss and
    before any report existed -- one missing pin hid the other ten. Answering
    lets every miss be collected in one pass, and :func:`run` then refuses to
    score the run at all, so nothing a broken fixture produces is ever read as a
    result.

    ``latency`` is the timing tier's stand-in for the network: each request
    sleeps that long before answering, so a run's wall clock is dominated by a
    known quantity rather than by however fast the machine happens to be. The
    sleep happens in the request's own thread, so a serial chain accumulates it
    once per request and a concurrent one would overlap it --- which is exactly
    what :func:`timing` measures.
    """
    from engine.metadata_lookup import HttpResult

    def http_get_json(url, **kwargs):
        if latency:
            time.sleep(latency)
        pin = pins.get(url)
        if pin is None:
            misses.append(url)
            return HttpResult(
                status_code=0,
                error=f"no recorded response for this {provider} request: {url}",
            )
        return HttpResult(status_code=pin.status_code, body=pin.body, error=pin.error)

    return http_get_json


def recording_transport(provider: str, captures: dict[str, Pin], budget: int, delay: float):
    """Return a wrapper that performs the real request and keeps the response.

    Paced, because the first attempt at this fixture was not: OpenAlex answers a
    burst of title searches with 429 once the burst passes its limit, and the
    recording then holds throttle responses rather than search results. All
    eighteen OpenAlex pins were 429, every case's OpenAlex attempt read as
    ``failed``, and the run still looked like it had recorded a fixture. The
    delay is what makes the difference between recording providers and
    recording my own request rate.
    """
    from engine.metadata_lookup import http_get_json as real_http_get_json

    def http_get_json(url, **kwargs):
        if len(captures) >= budget:
            raise RuntimeError(
                f"--max-calls {budget} reached; refusing to make further requests. "
                "Raise the budget deliberately if the case set grew."
            )
        if delay and captures:
            time.sleep(delay)
        result = real_http_get_json(url, **kwargs)
        captures[url] = Pin(
            url=url,
            provider=provider,
            source="captured",
            status_code=result.status_code,
            body=result.body,
            error=result.error,
            captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        return result

    return http_get_json


def _answer(pin: Pin) -> tuple[int, str, list[Any]]:
    """The part of a recorded response that the audit actually reads.

    Compared instead of the raw bytes, because the bytes carry fields no case
    depends on: OpenAlex's ``db_response_time_ms`` differs on every request, and
    ``cited_by_count`` differs over days. Under a whole-body comparison either
    one reports a provider whose answer changed, which is a warning that fires
    every time and so is not a warning. A pin means to a case what it maps to,
    so the candidates are compared, through the same mapping the lookup calls --
    if that mapping changes, what the fixture means changed with it.

    Ordered by record rather than by the order the provider listed them in.
    Crossref reorders records it scores equally between requests -- six pins
    changed that way while this fixture was being recorded, none of which
    changed any case's state -- and identity selection reads the list only to
    choose between several distinct works that share an exact title, which no
    case here does. The replay is the second net for the rest: a case that
    changed its mind stops matching the state it declares and turns red.
    """
    mapper = openalex_lookup.map_items if pin.provider == "openalex" else crossref_lookup.map_items
    return (pin.status_code, pin.error, sorted(mapper(pin.body), key=lambda c: c.record_id))


def save_captures(
    directory: Path, captures: dict[str, Pin], existing: dict[str, Pin], *, accept: bool
) -> tuple[list[str], list[str], int, int]:
    """Write new captures; refuse to overwrite answers that changed.

    Returns the URLs that failed to be answered, the URLs whose answer changed,
    how many were written, and how many already matched. An injected pin is left
    alone in both directions: it is a person's edit to a recorded answer, so
    recording over it would delete a case's premise.

    A capture the network failed is not stored at all. It is not an answer a
    case can be built on, and storing one silently turns a fixture into a record
    of the recorder's own connectivity -- the throttle responses that fill it
    read as a provider that answered "no records" to nothing in particular. The
    four cases that do need a failed provider get one by injection, which is
    visible in the pin's ``source`` and in its note.
    """
    directory.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    drifted: list[str] = []
    taken: dict[Path, str] = {}
    written = unchanged = 0
    for url, pin in captures.items():
        previous = existing.get(url)
        if previous is not None and previous.injected:
            continue
        if pin.not_an_answer:
            failed.append(url)
            continue
        if previous is not None and previous.path is not None:
            pin.path = previous.path
        else:
            pin.path = _capture_path(directory, pin)
        if pin.path in taken:
            raise RuntimeError(
                f"{pin.path.name} would answer two different requests:\n"
                f"  {taken[pin.path]}  and  {url}\n"
                "One file cannot hold both, and the second write would replace the "
                "first, leaving the case that owned it with no recorded answer."
            )
        taken[pin.path] = url
        if previous is not None and previous.path is not None:
            if _answer(previous) == _answer(pin):
                unchanged += 1
                continue
            drifted.append(url)
            if not accept:
                continue
            pin.note = "Re-recorded; the candidates the provider returned changed."
        payload = {
            "url": pin.url,
            "provider": pin.provider,
            "source": pin.source,
            "captured_at": pin.captured_at,
            "status_code": pin.status_code,
            "error": pin.error,
            "body": pin.body,
        }
        if pin.note:
            payload["note"] = pin.note
        pin.path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written += 1
    return failed, drifted, written, unchanged


def _capture_path(directory: Path, pin: Pin) -> Path:
    """A readable, stable name for one recorded response.

    The name is a label only --- the file records the URL it answers, and the
    transport keys on that --- so the slug only has to be recognisable in a
    directory listing and unique.

    Unique is the part the eight-word truncation breaks. Two references that
    differ only in the first author's surname query the same title and differ
    only in the trailing word, which the truncation drops; both then want one
    filename and whichever is written second silently replaces the first. The
    suffix is therefore taken from the URL itself, which cannot collide and does
    not depend on which other cases are in the fixture.
    """
    params = parse_qs(urlsplit(pin.url).query)
    asked = " ".join(params.get("filter", []) + params.get("query.bibliographic", []))
    asked = re.sub(r"^\s*title\.search\s*:\s*", "", asked)
    slug = re.sub(r"[^a-z0-9]+", "-", asked.casefold()).strip("-")
    slug = "-".join(slug.split("-")[:8]) or "query"
    digest = hashlib.sha256(pin.url.encode()).hexdigest()[:8]
    return directory / f"{pin.provider}-{slug[:72]}-{digest}.json"


# ── The run ───────────────────────────────────────────────────────


def _environment(workdir: Path) -> None:
    """Point the application at a temporary store, before it is imported.

    ``PAPERS_FILE``, ``PARSED_DIR`` and the upload directory are read into
    module constants when the storage and route modules import, so this has to
    happen first and a process that already imported the application cannot
    change them. :func:`_assert_environment` turns that ordering rule into an
    error instead of a benchmark that quietly reads a developer's uploads.

    The provider keys are cleared so that a case whose artifact does not pin
    ``metadata_version`` cannot turn the run into a paid one.
    """
    upload = workdir / "uploads"
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


def _assert_environment(workdir: Path) -> None:
    from backend.src.config import get_settings

    if Path(get_settings().upload_dir).resolve() != (workdir / "uploads").resolve():
        raise RuntimeError(
            "The application was imported before the benchmark set its environment, so it is "
            "reading the developer's uploads. Run backend/scripts/audit_benchmark.py as its own "
            "process rather than importing it from an environment that already loaded the app."
        )


def seed_manuscript(cases: list[Case]) -> None:
    """Write the PDF-shaped cases at the reference-artifact boundary.

    Not a PDF and not a parse: the artifact the audit reads is written directly,
    with ``metadata_version: 3`` so no segmentation runs and no key is needed,
    and a paper record whose status is completed. What is under test is how the
    audit reads recovered metadata, and this is the boundary where it enters.

    The id is this script's own, so an existing record under it is a previous
    seeding and is replaced rather than duplicated. ``--mode record`` seeds once
    while recording and again while replaying what it recorded, and both passes
    run in one process.
    """
    from backend.src.models import PaperRecord, PaperScope, ParseStatus
    from backend.src.storage import paper_store
    from backend.src.storage.reference_store import (
        StoredReference,
        StoredReferenceList,
        save_references,
    )

    paper_store.delete_paper(MANUSCRIPT_ID)

    references = []
    for index, case in enumerate([c for c in cases if c.input_kind == "pdf"], start=1):
        block = case.reference
        references.append(
            StoredReference(
                raw_text=block["raw_text"],
                title=block.get("title"),
                authors=block.get("authors"),
                year=block.get("year"),
                venue=block.get("venue"),
                doi=block.get("doi"),
                number=index,
                metadata_source=block.get("metadata_source") or "raw_text_heuristic",
            )
        )
    save_references(
        MANUSCRIPT_ID,
        StoredReferenceList(
            metadata_version=3,
            source_file=MANUSCRIPT_NAME,
            references=references,
            paper_id=MANUSCRIPT_ID,
        ),
    )
    now = datetime.now(UTC)
    paper_store.create_paper(
        PaperRecord(
            paper_id=MANUSCRIPT_ID,
            original_filename=MANUSCRIPT_NAME,
            stored_filename=MANUSCRIPT_NAME,
            file_path=str(Path(os.environ["UPLOAD_DIR"]) / MANUSCRIPT_NAME),
            file_type="pdf",
            scope=PaperScope.LIBRARY,
            file_size=0,
            status=ParseStatus.COMPLETED,
            pages=1,
            paragraph_count=0,
            created_at=now,
            updated_at=now,
        )
    )


def _patch_providers(openalex_transport, crossref_transport) -> None:
    """Install both transports at the seam each provider imported the function into."""
    import engine.crossref_lookup
    import engine.openalex_lookup

    engine.openalex_lookup.http_get_json = openalex_transport
    engine.crossref_lookup.http_get_json = crossref_transport


def _upload(client, cases: list[Case]) -> str:
    """POST the document and return the paper id the audit is asked about.

    Kept apart from :func:`_audit` because the timing tier measures the audit
    POST alone. A number that spans parsing and auditing measures neither: the
    repository has one such number already (``audit_live_acceptance`` times
    parse and audit together) and it cannot say which half changed.
    """
    upload = client.post(
        "/api/parse",
        files={
            "file": (
                "audit-benchmark.bib",
                bib_document(cases).encode("utf-8"),
                "application/x-bibtex",
            )
        },
    )
    upload.raise_for_status()
    parsed = upload.json()
    if parsed.get("status") != "completed":
        raise RuntimeError(f"the benchmark .bib did not parse: {parsed}")
    return parsed["paper_id"]


def _audit(client, cases: list[Case], kind: str) -> Any:
    """Run one audit form and return the validated response."""
    from backend.src.audit_models import BibliographyAuditResponse

    if kind == "bib":
        body = {"bib_paper_id": _upload(client, cases)}
    else:
        body = {"manuscript_id": MANUSCRIPT_ID}
    response = client.post("/api/audit", json=body)
    response.raise_for_status()
    return BibliographyAuditResponse.model_validate(response.json())


def run(cases: list[Case], pins: dict[str, Pin], latency: float = 0.0) -> RunReport:
    """Drive both audit forms through the API with the pins standing in for the network."""
    from backend.src.main import app
    from fastapi.testclient import TestClient

    report = RunReport(pins_total=len(pins))
    misses: list[str] = []
    used: list[str] = []

    def counting(provider: str):
        inner = transport(provider, pins, misses, latency)

        def http_get_json(url, **kwargs):
            if url in pins:
                used.append(url)
            return inner(url, **kwargs)

        return http_get_json

    _patch_providers(counting("openalex"), counting("crossref"))
    if any(case.input_kind == "pdf" for case in cases):
        seed_manuscript(cases)

    with TestClient(app) as client:
        forms = []
        for kind in ("bib", "pdf"):
            group = [case for case in cases if case.input_kind == kind]
            if group:
                forms.append((kind, [case.scored for case in group], _audit(client, group, kind)))
    if not misses:
        report.forms = forms

    report.pins_used = sorted(set(used))
    report.pins_unused = sorted(set(pins) - set(used))
    report.pins_missing = sorted(set(misses))
    report.requests = list(used)
    counted: dict[str, int] = {}
    for pin in pins.values():
        counted[pin.source] = counted.get(pin.source, 0) + 1
    report.sources = counted
    return report


def record(cases: list[Case], existing: dict[str, Pin], args) -> int:
    """Run the cases live, capturing every provider response, then store them."""
    from backend.src.main import app
    from fastapi.testclient import TestClient

    captures: dict[str, Pin] = {}
    _patch_providers(
        recording_transport("openalex", captures, args.max_calls, args.delay),
        recording_transport("crossref", captures, args.max_calls, args.delay),
    )
    if any(case.input_kind == "pdf" for case in cases):
        seed_manuscript(cases)
    with TestClient(app) as client:
        for kind in ("bib", "pdf"):
            group = [case for case in cases if case.input_kind == kind]
            if group:
                _audit(client, group, kind)

    failed, drifted, written, unchanged = save_captures(
        RESPONSE_DIR, captures, existing, accept=args.accept_drift
    )
    print(f"\ncaptured {len(captures)} response(s): {written} written, {unchanged} unchanged")
    for url in sorted(captures):
        pin = captures[url]
        if pin.path is None:
            continue
        mark = "CHANGED" if url in drifted else ("have" if url in existing else "new")
        print(f"  [{mark}] {pin.path.name}")
    if failed:
        print(
            f"\n{len(failed)} request(s) were not answered -- the provider refused, throttled "
            "or did not reply -- and were NOT recorded. A case cannot be built on one, and "
            f"storing it would fill the fixture with failures instead of answers. Re-run "
            f"once the provider is answering (--delay {args.delay:g}s between requests):"
        )
        for url in failed:
            held = "already recorded" if url in existing else "NO RECORDED ANSWER"
            print(f"  [{held}] {captures[url].provider}: {captures[url].error}")
    if drifted:
        print(
            f"\n{len(drifted)} record(s) changed since they were captured. Those cases' expected "
            "states were derived from the old bytes, so they must be re-derived by hand before "
            "the fixture is trusted again:"
        )
        for url in drifted:
            print(f"  {url}")
        if not args.accept_drift:
            print("\nNothing was overwritten. Re-run with --accept-drift to replace them.")
            return 1
    return 0


# ── Reporting ─────────────────────────────────────────────────────


def render(report: RunReport) -> str:
    """Render every form's scored report, then what the fixture itself did."""
    blocks = [
        audit_eval.render_report(
            audit_eval.score_response(cases, response),
            title=f"bibliography audit, {form} form (pinned providers)",
            source=f"{len(cases)} constructed case(s), {len(response.results)} result(s)",
        )
        for form, cases, response in report.forms
    ]
    lines = [
        "== provider bytes ==",
        "  " + "  ".join(f"{name}={count}" for name, count in sorted(report.sources.items())),
        f"  pins used     : {len(report.pins_used)}/{report.pins_total}",
        f"  pins unused   : {len(report.pins_unused)}",
        f"  pins missing  : {len(report.pins_missing)}",
        f"  requests made : {len(report.requests)} (each one a provider query the chain "
        "decided to send)",
    ]
    lines += [f"    unused: {url}" for url in report.pins_unused]
    lines += [f"    missing: {url}" for url in report.pins_missing]
    if report.pins_missing:
        lines.append(
            "  NOT SCORED: the fixture has no recorded answer for the requests above, so "
            "the audit could not reach a verdict on the cases that made them. Record them "
            "and run again; until then no accuracy figure here means anything."
        )
    blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def payload(report: RunReport) -> dict:
    """The run as JSON, for the measurement output file."""
    return {
        "contract_version": 2,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "forms": [
            {
                "input_kind": form,
                "cases": len(cases),
                "results": audit_eval.report_payload(audit_eval.score_response(cases, response)),
            }
            for form, cases, response in report.forms
        ],
        "pins": {
            "total": report.pins_total,
            "sources": report.sources,
            "used": report.pins_used,
            "unused": report.pins_unused,
            "missing": report.pins_missing,
        },
        "requests": {
            "total": len(report.requests),
            "distinct": len(set(report.requests)),
        },
    }


def failures(report: RunReport) -> int:
    """How many cases did not score as expected, plus any fixture miss."""
    return len(report.pins_missing) + sum(
        1
        for _, cases, response in report.forms
        for score in audit_eval.score_response(cases, response).scores
        if not score.passed
    )


# ── Timing ────────────────────────────────────────────────────────

DEFAULT_SIZES = (5, 10, 20, 40, 80)
DEFAULT_LATENCY = 0.05
MAX_SIZE = 200

# What each shape costs the provider chain, and what it must return. Written
# from the contract rather than measured from a run, because this is the claim
# the tier exists to test: the chain short-circuits at the first provider that
# settles a reference, so a reference OpenAlex resolves costs one request and a
# reference it cannot resolve costs two. Asserting the total alone would pass on
# a chain that asked both providers every time and a fixture that happened to
# have two answers for everything, so each entry's own attempt list is checked.
SHAPES = {
    "bert-exact": (1, "VERIFIED"),
    "dialoguernn-year-minus-five": (2, "NOT_FOUND"),
    "provider-500": (2, "LOOKUP_FAILED"),
}
# The mix, as shares of a document. Half the entries are resolved by the first
# provider, which is the common case against real references; the rest are split
# between a search that completes negative and one the network broke.
TIMING_MIX = (("bert-exact", 0.5), ("dialoguernn-year-minus-five", 0.3), ("provider-500", 0.2))

# The synthetic attempt the backend appends to say what the chain concluded. It
# is not a provider request and must not be counted as one.
CHAIN_ATTEMPT = "metadata_providers"


def timing_slots(size: int) -> list[str]:
    """The case each entry in a document of this size replays."""
    counts = {case_id: round(size * share) for case_id, share in TIMING_MIX}
    # The shares round independently, so the last shape takes the remainder
    # rather than letting the document be a different length from the one asked
    # for -- a silently short document would still produce a plausible curve.
    counts[TIMING_MIX[-1][0]] = size - sum(counts[case_id] for case_id, _ in TIMING_MIX[:-1])
    return [case_id for case_id, share in TIMING_MIX for _ in range(counts[case_id])]


def timing_cases(cases: list[Case], size: int) -> list[Case]:
    """One document: the pinned shapes, repeated, each entry with a key of its own.

    The provider query is built from the title and the first author's surname, so
    a hundred copies of ``bert-exact`` under a hundred keys ask for the one URL
    the fixture already holds. Reusing the recorded shapes rather than inventing
    synthetic ones is what keeps this tier free of the network: every request it
    makes has a recorded answer, and :func:`run`'s miss check still applies.
    """
    by_id = {case.case_id: case for case in cases}
    missing = sorted({case_id for case_id in timing_slots(size)} - set(by_id))
    if missing:
        raise ValueError(f"the case file does not hold the timing shapes: {', '.join(missing)}")
    built = []
    for index, case_id in enumerate(timing_slots(size)):
        source = by_id[case_id]
        key = f"timing-{size}-{index:03d}"
        renamed = re.sub(r"^(@\w+\{)[^,]+,", rf"\1{key},", source.bib_source, count=1)
        if key not in renamed:
            raise RuntimeError(f"could not rename the entry key in {case_id}'s source")
        built.append(
            replace(
                source,
                scored=replace(source.scored, case_id=key, bib_key=key),
                bib_source=renamed,
            )
        )
    return built


def timing_document(size: int) -> tuple[int, dict[str, int]]:
    """What a document of this size must cost: requests, and result states."""
    slots = timing_slots(size)
    states: dict[str, int] = {}
    for case_id in slots:
        _, status = SHAPES[case_id]
        states[status] = states.get(status, 0) + 1
    return sum(SHAPES[case_id][0] for case_id in slots), states


@contextmanager
def serving(app):
    """Serve the application on a real socket, in this process.

    In this process, and not as a subprocess, because the pins are installed by
    patching the two provider modules: that reaches an application which imports
    them here, and a subprocess would reach the live network instead. The socket
    is real, so the numbers carry the HTTP boundary. What they do not carry is
    the network -- the pins answer with no socket at all -- and the report says
    so, because a latency figure that silently excludes the network is the kind
    of number this repository has already been burned by.
    """
    import httpx
    import uvicorn

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="audit-benchmark-server", daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 60
        while not server.started:
            if time.monotonic() >= deadline:
                raise TimeoutError("the benchmark server did not start within 60 seconds")
            time.sleep(0.05)
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=120
        ) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _entry_requests(result: dict) -> int:
    """How many provider requests one entry's result accounts for.

    Takes the response as the wire sends it: the timing tier reads the raw JSON
    rather than the models, because timing the serialization is the point.
    """
    return sum(1 for attempt in result["lookup_attempts"] if attempt["provider"] != CHAIN_ATTEMPT)


def scaling_problems(scaling: list[dict], latency: float) -> tuple[list[dict], list[str]]:
    """Whether a measured N curve is the curve a serial chain produces.

    Reads the curve by differencing consecutive sizes rather than by fitting:
    the difference between two sizes is the marginal cost of the extra requests
    between them, with the fixed cost of a request -- parsing, storage, building
    the response -- cancelled out. It is the same reason a two-point difference
    beats a slope through the origin here: the fixed cost is real and large
    enough to bend a two-point estimate either way.

    The band is wide on purpose. A number inside it says the chain sent its
    requests one after another and waited for each; a number below it says the
    requests overlapped, which no amount of machine noise produces. It is not a
    latency assertion -- the absolute seconds belong to the pins' injected delay,
    not to the product.
    """
    slopes: list[dict] = []
    problems: list[str] = []
    for first, second in zip(scaling, scaling[1:]):
        delta_requests = second["requests"] - first["requests"]
        delta_seconds = second["median"] - first["median"]
        slope = delta_seconds / delta_requests if delta_requests else 0.0
        slopes.append(
            {
                "sizes": [first["size"], second["size"]],
                "seconds_per_request": round(slope, 4),
                "latency": latency,
            }
        )
        if not 0.5 * latency <= slope <= 3.0 * latency:
            problems.append(
                f"n={first['size']}->{second['size']}: {delta_seconds:.3f}s for "
                f"{delta_requests} more requests is {slope:.4f}s per request, outside the "
                f"[{0.5 * latency:.4f}, {3.0 * latency:.4f}] band around the "
                f"{latency}s each pinned request was told to take"
            )
    return slopes, problems


def timing(cases: list[Case], pins: dict[str, Pin], args) -> int:
    """Measure the audit's N curve against pinned answers with an injected delay.

    Not a latency measurement of the live product. It is the structural half:
    the chain is serial, so the wall clock must grow with the number of requests
    the chain decides to send, and a run whose requests double while its wall
    clock does not is a run that overlapped them.
    """
    from backend.src.main import app

    misses: list[str] = []
    requests: list[str] = []

    def counting(provider: str):
        inner = transport(provider, pins, misses, args.latency)

        def http_get_json(url, **kwargs):
            requests.append(url)
            return inner(url, **kwargs)

        return http_get_json

    _patch_providers(counting("openalex"), counting("crossref"))

    sizes = list(args.sizes)
    if any(size > MAX_SIZE for size in sizes):
        print(f"refusing a document larger than {MAX_SIZE} entries: {sizes}")
        return 2

    scaling = []
    problems: list[str] = []
    with serving(app) as client:
        for size in sizes:
            document = timing_cases(cases, size)
            expected_requests, expected_states = timing_document(size)
            started = time.perf_counter()
            paper_id = _upload(client, document)
            parse_seconds = time.perf_counter() - started
            seconds: list[float] = []
            for _ in range(args.repeats):
                before = len(requests)
                started = time.perf_counter()
                response = client.post("/api/audit", json={"bib_paper_id": paper_id})
                elapsed = time.perf_counter() - started
                response.raise_for_status()
                payload = response.json()
                seconds.append(elapsed)
                made = len(requests) - before
                if made != expected_requests:
                    problems.append(
                        f"n={size}: the audit sent {made} provider requests, expected "
                        f"{expected_requests}"
                    )
                states: dict[str, int] = {}
                wrong = []
                # By position, not by lookup: two entries of the same shape produce
                # equal dicts, so searching the list for a match would compare each
                # entry against whichever identical entry came first.
                for index, result in enumerate(payload["results"]):
                    states[result["status"]] = states.get(result["status"], 0) + 1
                    want = SHAPES[timing_slots(size)[index]][0]
                    if _entry_requests(result) != want:
                        wrong.append((result["entry"]["metadata"]["key"], _entry_requests(result)))
                if states != expected_states:
                    problems.append(f"n={size}: result states {states}, expected {expected_states}")
                if wrong:
                    problems.append(
                        f"n={size}: entries whose attempts do not match their shape: {wrong[:4]}"
                    )
            seconds.sort()
            scaling.append(
                {
                    "size": size,
                    "repeats": args.repeats,
                    "requests": expected_requests,
                    "seconds": [round(value, 4) for value in seconds],
                    "min": round(seconds[0], 4),
                    "median": round(seconds[len(seconds) // 2], 4),
                    "max": round(seconds[-1], 4),
                    "parse_seconds": round(parse_seconds, 4),
                    "seconds_per_entry": round(seconds[len(seconds) // 2] / size, 4),
                    "seconds_per_request": round(seconds[len(seconds) // 2] / expected_requests, 4),
                }
            )
            print(
                f"  n={size:<4} requests={expected_requests:<4} "
                f"median={scaling[-1]['median']:>7.3f}s "
                f"min={scaling[-1]['min']:>7.3f}s max={scaling[-1]['max']:>7.3f}s "
                f"parse={parse_seconds:>6.3f}s",
                flush=True,
            )

    slopes, slope_problems = scaling_problems(scaling, args.latency)
    problems += slope_problems

    print()
    print("== audit timing, pinned providers with injected latency ==")
    print(f"  each provider request sleeps {args.latency}s before answering")
    print("  serial chain : an extra request costs about one latency")
    print("  concurrent   : a document's requests overlap, so the curve flattens: the")
    print("                 slope below would fall far short of the band")
    for row in slopes:
        print(
            f"  n={row['sizes'][0]:<4}->{row['sizes'][1]:<4} "
            f"{row['seconds_per_request']:.4f}s per request"
        )
    print()
    print("  this is the structural half only. The pins never open a socket, so these")
    print("  seconds are not the live product's latency -- the live tier measures that.")
    if misses:
        problems.append(f"the fixture has no answer for {len(set(misses))} request(s)")
    if problems:
        print()
        print("  structural failures:")
        for problem in problems:
            print(f"    {problem}")
    else:
        print()
        print("  structural checks: pass (request counts, result states, and the slope band)")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "contract_version": 2,
                    "kind": "audit-timing",
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "boundary": (
                        "real uvicorn on 127.0.0.1, in-process pins: the HTTP boundary is "
                        "inside the measurement and the network is not"
                    ),
                    "latency_seconds": args.latency,
                    "mix": {case_id: share for case_id, share in TIMING_MIX},
                    "scaling": scaling,
                    "slopes": slopes,
                    "problems": problems,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {args.report}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["replay", "record", "timing"], default="replay")
    parser.add_argument("--cases", type=Path, default=CASE_FILE)
    parser.add_argument("--responses", type=Path, default=RESPONSE_DIR)
    parser.add_argument("--report", type=Path, help="write the run as JSON")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="record mode only: seconds between provider requests, so a run paces itself "
        "below the provider's rate limit instead of recording its own 429s",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=120,
        help="record mode only: refuse to make more than this many provider requests",
    )
    parser.add_argument(
        "--accept-drift",
        action="store_true",
        help="record mode only: overwrite captures whose bytes changed",
    )
    parser.add_argument(
        "--sizes",
        type=lambda value: tuple(int(part) for part in value.split(",")),
        default=DEFAULT_SIZES,
        help="timing mode only: document sizes to measure, largest last",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="timing mode only: how many times to audit each document",
    )
    parser.add_argument(
        "--latency",
        type=float,
        default=DEFAULT_LATENCY,
        help="timing mode only: seconds each pinned provider request takes, standing in "
        "for the network so the curve is not dominated by machine noise",
    )
    args = parser.parse_args(argv)

    cases = load_benchmark_cases(args.cases)
    existing = load_pins(args.responses)
    counts = ", ".join(
        f"{kind}={sum(1 for case in cases if case.input_kind == kind)}" for kind in ("bib", "pdf")
    )
    print(f"{len(cases)} case(s): {counts}; {len(existing)} pinned response(s)")

    with tempfile.TemporaryDirectory(prefix="audit-benchmark-") as temporary:
        workdir = Path(temporary)
        (workdir / "uploads").mkdir()
        _environment(workdir)
        _assert_environment(workdir)
        if args.mode == "record":
            status = record(cases, existing, args)
            if status:
                return status
        pins = load_pins(args.responses)
        if args.mode == "timing":
            return timing(cases, pins, args)
        report = run(cases, pins)

    print()
    print(render(report))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.report}")
    return 1 if failures(report) else 0


if __name__ == "__main__":
    sys.exit(main())
