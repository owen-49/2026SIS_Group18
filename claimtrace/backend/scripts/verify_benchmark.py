"""Measure POST /api/verify/citation: accuracy against the annotated pairs, and time.

Usage: python backend/scripts/verify_benchmark.py --mode estimate
       python backend/scripts/verify_benchmark.py --mode record --provider deepseek \\
           --model deepseek-chat --confirm-calls 103
       python backend/scripts/verify_benchmark.py --mode replay --check

The Audit benchmark holds the network still with pinned bytes; this one cannot.
Its subject is the product's own endpoint, its input is the team's annotated pair
set, and the only way to measure either is to run it. So the split is by price
rather than by tier: ``--mode estimate`` says what a run would cost and which
pairs would abstain, and touches no network at all; ``--mode record`` spends the
user's credits once and writes what came back; ``--mode replay`` scores that
recording for free, for as long as the annotations keep changing.

Design notes:
- **A pair names its source paper, so the request does not resolve a marker.**
  The pairs come from ``claim_worksheet.py``, where each claim is a citation
  context harvested from a paper that cites the source. The marker in that
  sentence belongs to the *citing* paper's reference list, which this library
  does not hold, so ``citation_marker`` cannot be resolved here and the request
  carries ``source_paper_id`` instead. That is the Verify-only source branch of
  the endpoint, and it is the branch every pair takes. A pair with no such source
  falls back to the marker branch when ``--manuscript-id`` names a bibliography
  to resolve against; that path exists for the small marker slice, not for the
  harvested set.
- **Registering a source is part of the run.** A Verify-only source is a separate
  upload; the pairs name the library's copy of the paper, which is not selectable
  as a source. ``--mode record`` uploads the missing ones through
  ``POST /api/verify/sources`` from the library's own PDF before spending
  anything, and says which ones it registered. ``--no-register`` refuses instead.
- **A status that is not ``COMPARED`` is an abstention, not a wrong answer.**
  Scoring it as wrong would mix "the engine declined to judge" with "the engine
  judged wrongly", which is the distinction the endpoint's own contract is built
  around (``docs/audit-contract.md`` states the same rule for Audit). Every
  non-``COMPARED`` status is mapped to no prediction, counted in
  ``abstention_statuses``, and held out of accuracy, F1 and kappa.
- **The verdict is only read when the status says there is one.** ``status`` is
  the field that carries the meaning and ``judgement`` is null otherwise; reading
  a verdict out of a response that did not produce one would invent the exact
  finding the contract forbids. :func:`check` asserts this over a recording
  rather than trusting it.
- **The recording is written in the harness's own shape.**
  ``recorded_claims/judgements.json`` and ``passages.json`` are what
  ``engine/tests/benchmarks/passage_harness.py --mode replay`` reads, so the same
  paid run produces the team's headline bars without paying twice. Those two
  files drop what this report needs -- ranks, similarity, page, seconds, HTTP
  status -- so ``verify_run.json`` keeps them, and it is the file
  :func:`score` and :func:`timing_report` read.
- **The key never leaves a local variable.** It is read with ``getpass``, put
  into one request body per call and dropped; it is never passed on the command
  line, read from the environment, or written anywhere. Every file this script
  writes is passed through :func:`assert_no_secret` first, which fails the run
  rather than writing it.
- **Replay is offline and deterministic**, so it is the half that can run in CI:
  the arithmetic is :mod:`engine.passage_eval`, unchanged, over a recording.
  Timing never runs in CI -- it would measure the runner, and a live half would
  spend money from a shared machine.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "parser")]

from engine.passage_eval import (  # noqa: E402
    DEFAULT_K,
    LABELS,
    AnnotatedPair,
    Judgement,
    load_pairs,
    render_retrieval_report,
    render_verdict_report,
    score_retrieval,
    score_verdicts,
)

DEFAULT_PAIRS = ROOT / "engine" / "tests" / "benchmarks" / "claim_passages.json"
DEFAULT_RECORDINGS = ROOT / "engine" / "tests" / "benchmarks" / "recorded_claims"
DEFAULT_REPORT = ROOT / "backend" / "tests" / "benchmarks" / "verify_run.json"

# The corpus view ``claim_worksheet.py --corpus-view`` links: every parsed paper
# (the library's and the Verify-only uploads') in one directory. Replay needs it
# only to know which pairs have a source whose text was ever read; the retrieval
# numbers come from the recording.
DEFAULT_CORPUS = ROOT / "backend" / "tests" / "benchmarks" / "corpus"

# Every status the comparison route can report. Restated from
# ``backend.src.models.ComparisonStatus`` rather than imported, so that replay and
# ``--check`` run on a machine with no FastAPI; a unit test asserts the two agree,
# which is what keeps the copy honest.
COMPARISON_STATUSES = (
    "COMPARED",
    "NO_BIBLIOGRAPHY",
    "MARKER_UNSUPPORTED",
    "REFERENCE_NOT_FOUND",
    "REFERENCE_AMBIGUOUS",
    "SOURCE_NOT_AVAILABLE",
    "SOURCE_EMPTY",
    "LLM_FAILED",
    "MANUAL_SOURCE_NOT_FOUND",
    "MANUAL_SOURCE_NOT_READY",
    "MANUAL_SOURCE_INVALID",
)

# Keys that must never reach a file this script writes. ``ai_config`` carries the
# key itself; the spelling of the key's own name would mean the body, not the
# response, had been written out.
SECRET_KEYS = frozenset({"ai_config", "api_key", "apikey", "authorization", "api_secret"})

# What a provider key looks like when it is not known by value. Replay has no key
# in hand -- that is the point of replay -- so a recording is checked for the
# shapes a key comes in, as a whole string rather than as a substring: a passage
# of prose may contain "sk-" by accident, and one that is exactly a key is not an
# accident.
KEY_LIKE = re.compile(r"^(sk|sk-proj|sk-ant|dsk|gsk)-[A-Za-z0-9_\-]{16,}$")

STATUS_COMPARED = "COMPARED"


# ── The library on disk ───────────────────────────────────────────


def upload_dir() -> Path:
    """Where the paper store lives, as the application would resolve it."""
    return Path(os.environ.get("UPLOAD_DIR") or (ROOT / "backend" / "uploads"))


def load_records() -> list[dict]:
    """Read the paper store's records, oldest first.

    Read from the file rather than through the API so that ``--mode estimate``
    needs no server: the store is the same file either way, and the estimation
    half has to run before anything is started.
    """
    path = upload_dir() / "papers.json"
    if not path.exists():
        raise SystemExit(f"no paper store at {path}; nothing to benchmark against")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("papers") if isinstance(payload, dict) else payload
    if isinstance(records, dict):
        records = list(records.values())
    return [record for record in records or [] if isinstance(record, dict)]


def _by_prefix(records: list[dict], wanted: str) -> dict | None:
    """The one record an id or unambiguous prefix names, or ``None``.

    The same rule the rest of the project uses for naming papers in prose: the id
    itself, or a prefix that matches exactly one. Nothing is guessed past that.
    """
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    exact = [record for record in records if record.get("paper_id") == wanted]
    if exact:
        return exact[0]
    matches = [record for record in records if str(record.get("paper_id", "")).startswith(wanted)]
    return matches[0] if len(matches) == 1 else None


def verify_sources(records: list[dict]) -> list[dict]:
    """The records a ``source_paper_id`` may name."""
    return [
        record
        for record in records
        if record.get("scope") == "verify_source" and record.get("file_type") == "pdf"
    ]


def resolve_sources(pairs: list[AnnotatedPair], records: list[dict]) -> tuple[dict, dict]:
    """Map every pair's source paper onto a Verify-only source record.

    Two lookups, in order. A pair that already names a Verify-only source resolves
    to itself. Otherwise the pair names a library paper -- which is what the
    worksheet wrote, since that is where the source text lives -- and the match is
    made on the uploaded file's name: the library copy of a paper and its
    Verify-only copy came from the same PDF, and the filename is the one piece of
    provenance the store keeps that a parse cannot change.

    Returns:
        ``(mapping, needs_upload)``: pair source key to Verify-only paper id, and
        the keys that would need an upload first (paper id to its record). A key
        in neither names a paper the store does not hold at all.
    """
    mapping: dict[str, str] = {}
    needs_upload: dict[str, dict] = {}
    twins: dict[str, list[str]] = {}
    # Sorted, so that a paper uploaded twice picks the same copy on every machine
    # rather than whichever the store happened to list first.
    for record in sorted(verify_sources(records), key=lambda item: str(item.get("paper_id", ""))):
        twins.setdefault(str(record.get("original_filename") or ""), []).append(
            str(record["paper_id"])
        )

    for key in sorted({pair.source_paper for pair in pairs if pair.source_paper.strip()}):
        record = _by_prefix(records, key)
        if record is None:
            continue
        if record.get("scope") == "verify_source" and record.get("file_type") == "pdf":
            mapping[key] = str(record["paper_id"])
            continue
        candidates = twins.get(str(record.get("original_filename") or ""))
        if candidates:
            mapping[key] = candidates[0]
        else:
            needs_upload[key] = record
    return mapping, needs_upload


# ── The corpus view ───────────────────────────────────────────────


def load_corpus(directory: str | Path) -> dict[str, list[str]]:
    """Read every parsed paper in a directory as its list of passages.

    The same reading ``passage_harness.load_corpus`` does, and deliberately the
    same shape: this file only needs it to decide which pairs have a source whose
    text was ever read. It is kept here rather than imported from the engine tests
    so that a backend script does not depend on the engine's test tree.
    """
    corpus: dict[str, list[str]] = {}
    for path in sorted(Path(directory).glob("*.json")):
        if path.name.endswith(".references.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        paragraphs = payload.get("paragraphs") if isinstance(payload, dict) else None
        if not isinstance(paragraphs, list):
            continue
        texts = [
            str(item.get("text", "")).strip()
            for item in paragraphs
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        if texts:
            corpus[path.stem] = texts
    return corpus


def resolve_corpus_key(wanted: str, corpus: dict[str, list[str]]) -> str:
    """Expand a paper's short id to the corpus key, or fail to."""
    wanted = (wanted or "").strip()
    if not wanted:
        return ""
    if wanted in corpus:
        return wanted
    matches = [key for key in corpus if key.startswith(wanted)]
    return matches[0] if len(matches) == 1 else ""


# ── What a run would send ─────────────────────────────────────────


@dataclass
class Planned:
    """One pair, the request it produces, and whether that request can be made."""

    pair: AnnotatedPair
    body: dict[str, Any] = field(default_factory=dict)
    path: str = ""
    blocked: str = ""
    note: str = ""
    predicted_abstention: str = ""

    @property
    def sends(self) -> bool:
        return not self.blocked

    @property
    def calls_the_model(self) -> bool:
        """Whether this request would reach the LLM if the pair resolves.

        An unresolvable marker or an empty source stops before the model, so those
        pairs are excluded from the estimate's budget rather than counted and then
        refunded.
        """
        return self.sends and not self.predicted_abstention.startswith("unpredictable")


def plan_requests(
    pairs: list[AnnotatedPair],
    mapping: dict[str, str],
    corpus: dict[str, list[str]],
    *,
    manuscript_id: str = "",
    k: int = DEFAULT_K,
    pending_uploads: dict[str, dict] | None = None,
) -> list[Planned]:
    """Turn the pair set into the requests a run would send.

    Nothing here reaches the network, which is what lets the estimate half be
    honest about its own budget: a pair that cannot resolve is reported before a
    key is ever asked for.

    ``pending_uploads`` names the source keys whose Upload has not happened yet
    -- the estimate's view of the library. Their request cannot be built (the
    source has no id until it is uploaded), so they carry a note instead of a
    body, and they are not called blocked: an upload the same run would perform
    is a step, not a gap.
    """
    planned: list[Planned] = []
    for pair in pairs:
        marker = pair.citation_marker.strip()
        if not pair.source_paper.strip():
            planned.append(Planned(pair=pair, blocked="the pair names no source paper"))
            continue
        source_id = mapping.get(pair.source_paper)
        if source_id:
            body: dict[str, Any] = {
                "claim": pair.claim,
                # Required by the request model and unused by this branch: the
                # source is named outright, so no marker is resolved. The pairs
                # carry a marker for provenance; a hand-written one may not.
                "citation_marker": marker or "manual",
                "source_paper_id": source_id,
                "k": k,
            }
            if pair.pair_id:
                body["claim_id"] = pair.pair_id
            if not corpus.get(resolve_corpus_key(source_id, corpus)):
                planned.append(
                    Planned(
                        pair=pair,
                        body=body,
                        path="source_paper_id",
                        predicted_abstention="SOURCE_EMPTY (the source parsed without text)",
                    )
                )
                continue
            planned.append(Planned(pair=pair, body=body, path="source_paper_id"))
            continue
        pending = (pending_uploads or {}).get(pair.source_paper)
        if pending is not None:
            # The library's own copy stands in for the source's text here: it is
            # the same PDF, and the upload parses it with the same parser.
            local = corpus.get(resolve_corpus_key(str(pending.get("paper_id") or ""), corpus))
            planned.append(
                Planned(
                    pair=pair,
                    path="source_paper_id",
                    note=(
                        f"register {pending.get('original_filename')!r} as a Verify-only source, "
                        "then send it like the rest"
                    ),
                    predicted_abstention=(
                        "" if local else "SOURCE_EMPTY (the library copy parsed without text)"
                    ),
                )
            )
            continue
        if manuscript_id and marker:
            planned.append(
                Planned(
                    pair=pair,
                    body={
                        "claim": pair.claim,
                        "citation_marker": marker,
                        "manuscript_id": manuscript_id,
                        **({"claim_id": pair.pair_id} if pair.pair_id else {}),
                        "k": k,
                    },
                    path="citation_marker",
                    predicted_abstention=(
                        f"unpredictable until the marker is resolved against {manuscript_id[:8]}"
                    ),
                )
            )
            continue
        planned.append(
            Planned(
                pair=pair,
                blocked=(
                    f"no Verify-only source PDF for {pair.source_paper!r}; upload it through "
                    "POST /api/verify/sources (or drop --no-register)"
                ),
            )
        )
    return planned


def assert_unique_claims(pairs: list[AnnotatedPair]) -> None:
    """Refuse a pair set two recordings cannot tell apart.

    Both recording shapes are keyed by claim text, which is the harness's
    convention and the only field every pair is guaranteed to have. Two pairs
    with the same claim would silently share one entry -- the second would read
    the first's verdict -- so the run stops instead.
    """
    seen: dict[str, int] = {}
    for index, pair in enumerate(pairs):
        key = pair.claim.strip()
        if key in seen:
            raise SystemExit(
                f"pairs {seen[key]} and {index} carry the same claim text; a recording keyed by "
                f"claim cannot tell them apart: {key[:72]!r}"
            )
        seen[key] = index


# ── Secrets ───────────────────────────────────────────────────────


def assert_no_secret(payload: Any, secrets: list[str], where: str) -> None:
    """Fail rather than write a key, or the field that carries one.

    Walks the whole structure: the key could be nested in a provider's error text
    as easily as sitting in a field of its own, and the point of the check is that
    it does not depend on knowing where the leak would be.
    """
    for secret in secrets:
        if secret and secret in json.dumps(payload, ensure_ascii=False, default=str):
            raise SystemExit(f"refusing to write {where}: it contains the API key")


def _assert_no_secret_keys(node: Any, where: str) -> None:
    """Fail on a ``api_key``-shaped field, or a value shaped like a key."""
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in SECRET_KEYS:
                raise SystemExit(f"refusing to write {where}: it carries a {key!r} field")
            _assert_no_secret_keys(value, where)
    elif isinstance(node, list):
        for item in node:
            _assert_no_secret_keys(item, where)
    elif isinstance(node, str) and KEY_LIKE.match(node.strip()):
        raise SystemExit(f"refusing to write {where}: it carries what looks like a key")


def write_json(path: Path, payload: Any, secrets: list[str], *, overwrite: bool = True) -> None:
    """Write one JSON file, after proving it holds neither the key nor its field."""
    assert_no_secret(payload, secrets, str(path))
    _assert_no_secret_keys(payload, str(path))
    if path.exists() and not overwrite:
        raise SystemExit(
            f"{path} already exists; a re-record would replace a measurement that was paid for. "
            "Move it aside, or pass --overwrite."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {path}")


def _relative(path: Any) -> str:
    """The path as the repository sees it, or as it is when it sits outside."""
    resolved = Path(path).resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


# ── Estimate ──────────────────────────────────────────────────────


def estimate(
    pairs: list[AnnotatedPair],
    planned: list[Planned],
    *,
    mapping: dict[str, str],
    needs_upload: dict[str, dict],
) -> int:
    """Print what a run would send, cost and skip. Touches nothing."""
    sending = [item for item in planned if item.sends]
    blocked = [item for item in planned if not item.sends]
    abstaining = [item for item in sending if item.predicted_abstention]
    calling = [item for item in sending if item.calls_the_model]
    unpredictable = [
        item for item in sending if item.predicted_abstention.startswith("unpredictable")
    ]
    pending = [item for item in sending if item.note]

    print(f"pairs        : {len(pairs)}")
    print(f"source papers: {len(mapping)} resolved, {len(needs_upload)} to upload")
    for key, record in sorted(needs_upload.items()):
        print(f"  upload {key:<10} from {record.get('original_filename')}")
    paths: dict[str, int] = {}
    for item in sending:
        paths[item.path] = paths.get(item.path, 0) + 1
    for path, count in sorted(paths.items()):
        print(f"  request path {path}: {count}")
    if pending:
        print(f"  {len(pending)} of those send only after the upload above")
    print()
    print(f"LLM calls    : {len(calling)}  (plus {len(unpredictable)} marker request(s))")
    print(f"abstentions  : {len(abstaining)}  decided before the model")
    for item in abstaining[:10]:
        print(f"  {item.predicted_abstention:<56} {item.pair.claim[:48]!r}")
    if len(abstaining) > 10:
        print(f"  ... and {len(abstaining) - 10} more")
    if blocked:
        print(f"blocked      : {len(blocked)} pair(s) cannot be sent as they stand")
        for item in blocked[:10]:
            print(f"  {item.blocked}")
        if len(blocked) > 10:
            print(f"  ... and {len(blocked) - 10} more")
    if not pairs:
        print(
            "\nThe pair file is empty. It is the annotation target, not a fixture: run\n"
            "claim_worksheet.py --harvest to build the worksheet, and annotate it."
        )
    return 1 if blocked else 0


# ── Record ────────────────────────────────────────────────────────


def register_missing(client, keys: list[str], records: list[dict]) -> int:
    """Upload the library's PDF for each source key that has no Verify-only copy.

    The upload is the product's own route, multipart and all, rather than a
    hand-written store entry: a record this script fabricated could differ from
    one the route produces in ways later steps would have to know about.
    """
    uploaded = 0
    for key in keys:
        record = _by_prefix(records, key)
        if record is None:
            print(f"  cannot register {key!r}: no paper record matches it")
            continue
        path = Path(str(record.get("file_path") or ""))
        if not path.exists():
            print(f"  cannot register {key!r}: {path} is not on disk")
            continue
        with path.open("rb") as handle:
            response = client.post(
                "/api/verify/sources",
                files={"file": (path.name, handle, "application/pdf")},
            )
        body = response.json() if response.content else {}
        if response.status_code != 200 or body.get("status") != "completed":
            print(f"  {key!r}: upload returned HTTP {response.status_code} {body.get('status')}")
            continue
        print(f"  registered {key} -> {body['paper_id'][:8]} from {path.name}")
        uploaded += 1
    return uploaded


def _record_entry(planned: Planned, response: dict, http_status: int, seconds: float) -> dict:
    """One recording entry: everything a later reader needs, and no secret."""
    judgement = response.get("judgement") or {}
    evidence = response.get("evidence") or []
    status = str(response.get("status") or "")
    return {
        "pair_id": planned.pair.pair_id,
        "claim": planned.pair.claim,
        "citation_marker": planned.pair.citation_marker,
        "source_paper": planned.pair.source_paper,
        "source_paper_id": planned.body.get("source_paper_id") or "",
        "path": planned.path,
        "http_status": http_status,
        # A verdict is read only when the status says one was produced. Anywhere
        # else there is no judgement, and inventing one is what the contract
        # forbids.
        "status": status,
        "verdict": str(judgement.get("verdict") or "") if status == STATUS_COMPARED else "",
        "confidence": judgement.get("confidence"),
        "rationale": str(judgement.get("rationale") or ""),
        "message": str(response.get("message") or ""),
        "cited_title": str(((response.get("cited_source") or {}) or {}).get("title") or ""),
        "evidence": [
            {
                "rank": int(item.get("rank") or 0),
                "page": item.get("page"),
                "similarity": item.get("similarity"),
                "passage_text": str(item.get("passage_text") or ""),
            }
            for item in sorted(evidence, key=lambda item: int(item.get("rank") or 0))
        ],
        "seconds": round(seconds, 4),
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def record(pairs: list[AnnotatedPair], args, *, model: str, provider: str, key: str) -> int:
    """Spend the user's credits: send every pair, keep every answer."""
    # The audit benchmark's server helper, imported rather than copied: it is the
    # same real-socket-in-this-process arrangement, and a second copy would drift.
    from backend.scripts.audit_benchmark import serving
    from backend.src.main import app

    secrets = [key]
    ai_config = {"provider": provider, "model": model, "api_key": key}

    with serving(app) as client:
        records = load_records()
        mapping, needs_upload = resolve_sources(pairs, records)
        if needs_upload:
            if args.no_register:
                print(f"--no-register: {len(needs_upload)} source paper(s) would need an upload")
                return 2
            print("registering Verify-only sources")
            register_missing(client, sorted(needs_upload), records)
            records = load_records()
            mapping, needs_upload = resolve_sources(pairs, records)

        corpus = load_corpus(args.corpus)
        planned = plan_requests(pairs, mapping, corpus, manuscript_id=args.manuscript_id, k=args.k)
        unknown = {item.pair.source_paper for item in planned if not item.sends}
        running = [item for item in planned if item.sends]
        print(
            f"{len(running)} request(s) over {len({item.pair.source_paper for item in running})} "
            f"source paper(s), k={args.k}"
        )
        if unknown:
            print(f"cannot send {len(unknown)} pair(s): {', '.join(sorted(unknown))}")

        expected = len([item for item in running if item.calls_the_model])
        if args.confirm_calls != expected:
            print(
                f"\n--confirm-calls {args.confirm_calls} does not match the {expected} call(s) "
                "this run would make.\nA confirmation that cannot be wrong is not one; pass the "
                "number "
                "the estimate printed."
            )
            return 2
        if not running:
            return 2
        print(f"confirmed: {expected} LLM call(s), spending the key's credits")

        entries: list[dict] = []
        for index, item in enumerate(running, start=1):
            posted = dict(item.body)
            posted["ai_config"] = ai_config
            started = time.perf_counter()
            response = client.post("/api/verify/citation", json=posted)
            elapsed = time.perf_counter() - started
            body = response.json() if response.content else {}
            entry = _record_entry(
                item,
                body if isinstance(body, dict) else {},
                response.status_code,
                elapsed,
            )
            entries.append(entry)
            print(
                f"  {index:>4}/{len(running)}  {elapsed:>7.3f}s  HTTP {response.status_code}  "
                f"{entry['status']:<24} {item.pair.claim[:44]!r}",
                flush=True,
            )

        components = [] if args.skip_components else measure_components(running, corpus)
        run = {
            "contract_version": 1,
            "kind": "verify-run",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "provider": provider,
            "model": model,
            "k": args.k,
            "pairs_file": _relative(args.pairs),
            "boundary": (
                "real uvicorn on 127.0.0.1 over loopback; the HTTP boundary and the live "
                "provider are both inside the measurement"
            ),
            "pairs": entries,
            "components": components,
        }
        write_json(Path(args.report), run, secrets, overwrite=args.overwrite)
        write_json(
            Path(args.recordings) / "verify_run.json",
            run,
            secrets,
            overwrite=args.overwrite,
        )
        write_json(
            Path(args.recordings) / "judgements.json",
            {
                "model": model,
                "pairs": [
                    {
                        "claim": entry["claim"],
                        "status": entry["status"],
                        "verdict": entry["verdict"],
                        "confidence": entry["confidence"],
                        "rationale": entry["rationale"],
                    }
                    for entry in entries
                ],
            },
            secrets,
            overwrite=args.overwrite,
        )
        write_json(
            Path(args.recordings) / "passages.json",
            {
                "embedder": "engine default",
                "limit": args.k,
                "corpus_sizes": {
                    key: len(corpus[key])
                    for key in sorted(
                        {resolve_corpus_key(entry["source_paper"], corpus) for entry in entries}
                        - {""}
                    )
                },
                "pairs": [
                    {
                        "claim": entry["claim"],
                        "source_paper": entry["source_paper"],
                        "retrieved": [item["passage_text"] for item in entry["evidence"]],
                    }
                    for entry in entries
                ],
            },
            secrets,
            overwrite=args.overwrite,
        )
    return 0


def measure_components(planned: list[Planned], corpus: dict[str, list[str]]) -> list[dict]:
    """Time the retrieval half in process, so the LLM's share can be subtracted.

    This is an engine component measurement, not the API path: it calls the same
    ``Retriever`` the endpoint builds, but it skips source location, the response
    models and the HTTP hop, and it reuses the process-wide cached embedder rather
    than the endpoint's own. It is reported as a component with that label
    attached, and the residual between it and the HTTP total is reported as what
    it is -- everything else in the request, the model call included.
    """
    from backend.src.services.engine_adapter import _get_embedder
    from engine.retriever import Retriever

    retriever = Retriever(embedder=_get_embedder())
    measured: list[dict] = []
    for item in planned:
        key = resolve_corpus_key(item.body.get("source_paper_id", ""), corpus)
        passages = corpus.get(key) or []
        if not passages:
            continue
        started = time.perf_counter()
        retriever.build_index(passages)
        indexed = time.perf_counter()
        results = retriever.retrieve(item.pair.claim, k=item.body.get("k", DEFAULT_K))
        finished = time.perf_counter()
        measured.append(
            {
                "pair_id": item.pair.pair_id,
                "source_passages": len(passages),
                "index_seconds": round(indexed - started, 4),
                "retrieve_seconds": round(finished - indexed, 4),
                "seconds": round(finished - started, 4),
                "retrieved": len(results),
            }
        )
        print(
            f"  component {item.pair.pair_id or item.pair.claim[:24]!r:<28} "
            f"index={measured[-1]['index_seconds']:>7.3f}s "
            f"retrieve={measured[-1]['retrieve_seconds']:>6.3f}s",
            flush=True,
        )
    return measured


# ── Replay ────────────────────────────────────────────────────────


def load_run(path: str | Path) -> dict:
    """Read one recorded run, or raise with the command that would make it."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"no recording at {path}\n"
            "A recording is the output of a paid run: pass --mode record first, or point --run "
            "at one that exists. Scoring cannot be re-derived from nothing."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("pairs"), list):
        raise SystemExit(f"{path}: not a recorded run (expected an object with a pairs list)")
    return payload


def entries_by_pair(runs: list[dict]) -> dict[str, dict]:
    """One entry per pair across several runs, the deepest recording winning.

    Two runs of the same pair differ in depth rather than in kind, and only the
    deeper one can be scored against a bar stated at five. Ties go to the earlier
    run, so the choice is a rule rather than an accident of argument order.
    """
    chosen: dict[str, dict] = {}
    for run in runs:
        depth = int(run.get("k") or 0)
        for entry in run.get("pairs") or []:
            item = dict(entry)
            item.setdefault("k", depth)
            key = str(entry.get("pair_id") or entry.get("claim") or "")
            if not key:
                continue
            current = chosen.get(key)
            if current is None or int(item.get("k") or 0) > int(current.get("k") or 0):
                chosen[key] = item
    return chosen


def judge_from(entries: dict[str, dict]):
    """A ``judge(pair)`` that answers from the recording."""

    def judge(pair: AnnotatedPair) -> Judgement:
        entry = entries.get(pair.pair_id) or entries.get(pair.claim)
        if entry is None:
            return Judgement(predicted="", status="NO_RECORDING")
        status = str(entry.get("status") or "")
        predicted = str(entry.get("verdict") or "") if status == STATUS_COMPARED else ""
        return Judgement(predicted=predicted, status=status)

    return judge


def retrieve_from(entries: dict[str, dict]):
    """A ``retrieve(claim, passages, k)`` that answers from the recording.

    Keyed by claim, not by pair id: ``score_retrieval`` hands its callback the
    claim and nothing else, which is what lets the same arithmetic score a live
    retriever and a recording.
    """
    by_claim = {str(entry.get("claim") or ""): entry for entry in entries.values()}

    def retrieve(claim: str, passages: list[str], k: int) -> list[str]:
        entry = by_claim.get(claim)
        if entry is None:
            return []
        return [str(item.get("passage_text") or "") for item in entry.get("evidence") or []][:k]

    return retrieve


def passages_by_paper(pairs: list[AnnotatedPair], corpus: dict[str, list[str]]) -> dict:
    """The corpus lookup ``score_retrieval`` needs, keyed as the pairs name papers."""
    lookup: dict[str, list[str]] = {}
    for pair in pairs:
        key = resolve_corpus_key(pair.source_paper, corpus)
        if key:
            lookup[pair.source_paper] = corpus[key]
    return lookup


# ── Timing ────────────────────────────────────────────────────────


def percentile(values: list[float], fraction: float) -> float | None:
    """The nearest-rank percentile, stated rather than assumed.

    Rank ``ceil(fraction * n)`` of the sorted values, 1-based. No interpolation
    and no library: with a hundred samples the difference between definitions is
    smaller than the difference a noisy machine makes, and a reader can check this
    one by counting.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(-(-fraction * len(ordered) // 1))))
    return ordered[rank - 1]


def _summary(seconds: list[float]) -> dict:
    return {
        "n": len(seconds),
        "min": round(min(seconds), 4),
        "median": round(percentile(seconds, 0.5) or 0.0, 4),
        "p95": round(percentile(seconds, 0.95) or 0.0, 4),
        "max": round(max(seconds), 4),
    }


def timing_report(runs: list[dict]) -> dict:
    """Summarise the recorded seconds by group, with the first call held out.

    The first call carries the embedding model's load, which is seconds against a
    median in the hundreds of milliseconds; leaving it in would move every
    percentile of a hundred-pair run. It is reported on its own instead.
    """
    calls: list[dict] = []
    for run in runs:
        for entry in run.get("pairs") or []:
            calls.append({**entry, "k": entry.get("k", run.get("k"))})
    http = [float(entry["seconds"]) for entry in calls if entry.get("seconds") is not None]
    held_out = http[:1]
    steady = http[1:] if len(http) > 1 else []

    def grouped(field: str) -> dict:
        buckets: dict[str, list[float]] = {}
        for entry in calls:
            if entry.get("seconds") is None:
                continue
            buckets.setdefault(str(entry.get(field) or "?"), []).append(float(entry["seconds"]))
        return {name: _summary(values) for name, values in sorted(buckets.items())}

    components = [item for run in runs for item in run.get("components") or []]
    component_seconds = [float(item["seconds"]) for item in components]
    residual = None
    if steady and component_seconds:
        residual = round(
            (percentile(steady, 0.5) or 0.0) - (percentile(component_seconds, 0.5) or 0.0), 4
        )
    by_size: dict[str, list[float]] = {}
    for item in components:
        by_size.setdefault(str(item.get("source_passages")), []).append(float(item["seconds"]))

    return {
        "http": _summary(http) if http else None,
        "first_call": held_out[0] if held_out else None,
        "steady": _summary(steady) if steady else None,
        "by_status": grouped("status"),
        "by_k": grouped("k"),
        "by_source": grouped("source_paper"),
        "component": {
            "n": len(component_seconds),
            "median": (
                round(percentile(component_seconds, 0.5) or 0.0, 4) if component_seconds else None
            ),
            "p95": (
                round(percentile(component_seconds, 0.95) or 0.0, 4) if component_seconds else None
            ),
            # Grouped by how many passages the paper had: the component embeds the
            # whole source on every request, so its cost is the paper's size, and a
            # single median across a 277-passage paper and a 49-passage one would
            # describe neither.
            "by_source_passages": {
                size: _summary(values) for size, values in sorted(by_size.items())
            },
        },
        "llm_residual_median": residual,
        "percentile_definition": "nearest rank, ceil(fraction x n), 1-based, no interpolation",
    }


def render_timing(timing: dict, runs: list[dict]) -> str:
    """Render the timing half as plain text."""
    lines = ["== verify timing =="]
    if not timing["http"]:
        lines.append("no recorded seconds: run --mode record first")
        return "\n".join(lines)
    depth = ", ".join(f"k={run.get('k')}" for run in runs)
    lines.append(f"runs         : {len(runs)}  ({depth})")
    lines.append(
        f"first call   : {timing['first_call']:.3f}s"
        "   (the embedding model's load lands here, so it is held out of the rest)"
    )
    for name in ("http", "steady"):
        summary = timing[name]
        if summary:
            lines.append(
                f"{name:<13}: n={summary['n']:<4} median={summary['median']:>7.3f}s "
                f"p95={summary['p95']:>7.3f}s min={summary['min']:>7.3f}s "
                f"max={summary['max']:>7.3f}s"
            )
    component = timing["component"]
    if component["median"] is not None:
        lines.append(
            f"component    : n={component['n']:<4} median={component['median']:>7.3f}s "
            f"p95={component['p95']:>7.3f}s   (engine Retriever in process, not the API path)"
        )
        lines.append(
            f"LLM residual : {timing['llm_residual_median']:>7.3f}s   steady median minus "
            "component median"
        )
        lines.append(
            "               a bound, not a measurement: it also holds the claim embedding, the "
            "source lookup, serialization and the HTTP hop"
        )
    if len(timing["by_k"]) > 1:
        lines.append("")
        lines.append("-- by k --")
        for name, summary in timing["by_k"].items():
            lines.append(f"  k={name:<3} n={summary['n']:<4} median={summary['median']:.3f}s")
    lines.append("")
    lines.append("-- by status --")
    for name, summary in timing["by_status"].items():
        lines.append(f"  {name:<24} n={summary['n']:<4} median={summary['median']:>7.3f}s")
    lines.append("")
    lines.append("-- by source paper --")
    for name, summary in timing["by_source"].items():
        lines.append(f"  {name:<12} n={summary['n']:<4} median={summary['median']:>7.3f}s")
    lines.append("")
    lines.append(
        "These are baseline numbers, reported as they came out: this report has no\n"
        "pass/fail line for latency, by decision."
    )
    return "\n".join(lines)


# ── The CI half ───────────────────────────────────────────────────


def check(runs: list[dict]) -> list[str]:
    """The assertions a recording must satisfy, run without a network.

    These are invariants, not accuracy: a wrong verdict is a measurement, and
    these are the ways a run could be *broken* -- a verdict invented for a status
    that produced none, a status this build does not know, a key that reached the
    file. Any of them failing makes every number in the recording unreadable.
    """
    problems: list[str] = []
    for run in runs:
        where = str(run.get("pairs_file") or run.get("generated_at") or "run")
        if run.get("k") is None:
            problems.append(f"{where}: the run does not record its retrieval depth k")
        for entry in run.get("pairs") or []:
            claim = str(entry.get("claim") or "")[:48]
            status = str(entry.get("status") or "")
            verdict = str(entry.get("verdict") or "")
            if not entry.get("pair_id"):
                problems.append(
                    f"{where}: {claim!r} has no pair_id, so two annotators cannot align"
                )
            if status not in COMPARISON_STATUSES:
                problems.append(f"{where}: {claim!r} reports unknown status {status!r}")
            if verdict and status != STATUS_COMPARED:
                problems.append(
                    f"{where}: {claim!r} carries verdict {verdict!r} under status {status!r}; "
                    "only COMPARED produces a judgement"
                )
            if verdict and verdict not in LABELS:
                problems.append(f"{where}: {claim!r} carries verdict {verdict!r}, not a label")
            if status == STATUS_COMPARED and not verdict:
                problems.append(f"{where}: {claim!r} is COMPARED with no verdict")
            if status == STATUS_COMPARED and not entry.get("evidence"):
                problems.append(f"{where}: {claim!r} is COMPARED with no evidence retrieved")
            ranks = [int(item.get("rank") or 0) for item in entry.get("evidence") or []]
            if ranks and ranks != list(range(1, len(ranks) + 1)):
                problems.append(f"{where}: {claim!r} has evidence ranks {ranks}, not 1..n")
            if entry.get("seconds") is None:
                problems.append(f"{where}: {claim!r} has no recorded duration")
        try:
            # No key in hand at replay, so this half is the field names and the
            # key shapes; the value check runs where a value exists, at write time.
            _assert_no_secret_keys(run, where)
        except SystemExit as exc:
            problems.append(str(exc))
    return problems


# ── Command line ──────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("replay", "estimate", "record"), default="replay")
    parser.add_argument("--estimate", action="store_true", help="alias for --mode estimate")
    parser.add_argument("--pairs", default=str(DEFAULT_PAIRS))
    parser.add_argument("--recordings", default=str(DEFAULT_RECORDINGS))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument(
        "--report", default=str(DEFAULT_REPORT), help="record mode: where the run is written"
    )
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="replay only: a recorded run to score; repeat to combine a k sweep",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="passages to retrieve per claim")
    parser.add_argument(
        "--manuscript-id",
        default="",
        help="resolve citation markers against this bibliography instead of naming the source",
    )
    parser.add_argument("--provider", choices=("openai", "deepseek"), default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument(
        "--confirm-calls",
        type=int,
        default=-1,
        help="record mode: the number of LLM calls the estimate printed; a mismatch aborts",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="record mode: refuse to upload source PDFs instead of registering them",
    )
    parser.add_argument(
        "--skip-components",
        action="store_true",
        help="record mode: skip the in-process retrieval timing, which is free but slow",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="allow replacing an existing recording"
    )
    parser.add_argument("--check", action="store_true", help="replay only: assert the invariants")
    parser.add_argument("--output", type=Path, help="replay only: write the reports as JSON here")
    args = parser.parse_args(argv)
    if args.estimate:
        args.mode = "estimate"

    pairs = load_pairs(args.pairs)
    if len(pairs) > 1:
        assert_unique_claims(pairs)

    if args.mode == "record":
        key = getpass.getpass("Your API key (not saved; this run spends your credits): ").strip()
        if not key:
            print("an API key is required for a live run")
            return 2
        return record(pairs, args, model=args.model, provider=args.provider, key=key)

    if args.mode == "estimate":
        records = load_records()
        mapping, needs_upload = resolve_sources(pairs, records)
        corpus = load_corpus(args.corpus)
        planned = plan_requests(
            pairs,
            mapping,
            corpus,
            manuscript_id=args.manuscript_id,
            k=args.k,
            pending_uploads=needs_upload,
        )
        return estimate(pairs, planned, mapping=mapping, needs_upload=needs_upload)

    # ── replay ──
    run_paths = args.run or [str(Path(args.recordings) / "verify_run.json")]
    runs = [load_run(path) for path in run_paths]
    entries = entries_by_pair(runs)
    corpus = load_corpus(args.corpus)

    problems = check(runs) if args.check else []
    retrieval = score_retrieval(pairs, passages_by_paper(pairs, corpus), retrieve_from(entries))
    verdicts = score_verdicts(pairs, judge_from(entries))
    print(render_retrieval_report(retrieval))
    print()
    print(render_verdict_report(verdicts))
    print()
    timing = timing_report(runs)
    print(render_timing(timing, runs))
    if args.check:
        print()
        if problems:
            print("== recording checks ==")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"recording checks: pass ({len(entries)} recorded pair(s), no invented verdicts)")
    if args.output:
        payload = {
            "contract_version": 1,
            "kind": "verify-measurement",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "pairs_file": _relative(args.pairs),
            "runs": [_relative(path) for path in run_paths],
            "accuracy": {
                "pairs": verdicts.total,
                "judged": verdicts.judged,
                "abstained": verdicts.abstained,
                "unannotated": verdicts.unannotated,
                "accuracy": verdicts.accuracy,
                "f1_support_vs_rest": verdicts.f1_support_vs_rest,
                "kappa": verdicts.kappa,
                "abstention_statuses": verdicts.abstention_statuses,
            },
            "retrieval": {
                "scored": retrieval.scored,
                "unscorable": len(retrieval.unscorable),
                "recall_at_1": retrieval.recall_at_1,
                "recall_at_5": retrieval.recall_at_5,
            },
            "timing": timing,
            "problems": problems,
        }
        write_json(args.output, payload, [])
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
