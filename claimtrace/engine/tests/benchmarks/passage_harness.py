"""Measure the retriever and the verifier against annotated claim-passage pairs.

The two committed bars -- the ground-truth passage in the top 5 for at least 80%
of claims, and the four-way judgement right for at least 80% of the annotated
set -- need an instrument, and this is it. The pair set is the team's to
annotate: the harness reads ``claim_passages.json``, and until that file has
pairs in it there is nothing to measure and the report says so.

This file is not collected by pytest: the configured ``python_files`` is
``test_*.py``, and nothing here is a test. It lives under ``tests/`` so that the
CI lint step (``ruff check engine/ tests/``) covers it.

Usage, from ``claimtrace/engine``::

    python tests/benchmarks/passage_harness.py --mode record --only retrieval
    python tests/benchmarks/passage_harness.py --mode replay

Design notes:
- The two halves are measured separately and composed rather than run
  end-to-end. Retrieval is scored on the claim alone; the judgement is scored
  against the passage the **annotator** marked, not against what retrieval
  returned. Feeding the verdict half retrieved text would fold a retrieval miss
  into the judgement error and leave the two bars unable to say which half
  moved. The end-to-end figure is their product, so it is reported as a product
  of the two rather than as a third number that hides the split.
- Recordings hold what the retriever returned and what the model said; the rank
  is recomputed from them at replay. Editing an annotation -- correcting a
  marked passage, adding a label -- therefore re-scores offline without paying
  for another embedding run or another model call. The retrieval depth is
  recorded with them and checked on the way back in, since replay can only score
  Recall@5 against a run that went at least that deep.
- ``--mode record`` refuses to run the judgement half without a client. Fifty
  recorded ``NO_CLIENT`` results look like evidence of something and are evidence
  of nothing, and a file of them would be read as a measurement that happened.
- The environment is read for key *names* only, and the run prints which one it
  used. The key itself is handed to the client and never printed.
- The corpus is read from the backend's parsed papers, which is where the source
  text lives. The loader is kept here rather than in :mod:`engine.passage_eval`
  so that the scoring module knows nothing about this repository's layout.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Run as a script, so ``tests/benchmarks`` is on the path and the package root is
# not. Set before the engine imports below, which is why they carry a noqa.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine import passage_eval  # noqa: E402
from engine.embedder import DEFAULT_MODEL as DEFAULT_EMBEDDER  # noqa: E402
from engine.embedder import Embedder  # noqa: E402
from engine.passage_eval import (  # noqa: E402
    DEFAULT_K,
    AnnotatedPair,
    Judgement,
    load_pairs,
    render_retrieval_report,
    render_verdict_report,
    score_retrieval,
    score_verdicts,
)
from engine.retriever import Retriever  # noqa: E402
from engine.verifier import Verifier  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_PAIRS = HERE / "claim_passages.json"
DEFAULT_RECORDINGS = HERE / "recorded_claims"

# ClaimTrace's parsed papers, relative to this file. A convenience default for
# this repository's layout; pass --corpus anywhere else.
DEFAULT_CORPUS = HERE.parents[2] / "backend" / "uploads" / "parsed"

# The OpenAI-compatible endpoints to try, in order: provider name, then the two
# variable names to read. Names are printed; values never are.
CLIENT_ENV = (
    ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
    ("openai", "OPENAI_API_KEY", "OPENAI_BASE_URL"),
)
DEFAULT_MODEL = "deepseek-chat"


def load_corpus(directory: str | Path) -> dict[str, list[str]]:
    """Load every parsed paper in a directory as its list of passages.

    Reads the backend's parse output: one JSON object per paper carrying a
    ``paragraphs`` list of ``{text, page_start, page_end}``. A file with no
    paragraphs yields no entry, so a pair pointing at it is reported unscorable
    rather than scored against nothing.
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


def resolve_paper(source_paper: str, corpus: dict[str, list[str]]) -> str:
    """Return the corpus key a pair's ``source_paper`` refers to, or an empty string.

    Accepts the paper's id or any unambiguous prefix of it, which is how the rest
    of the project names papers in prose. Nothing is guessed past that: a name
    matching no paper, or more than one, resolves to nothing and the pair is
    reported unscorable with the available keys named.
    """
    wanted = (source_paper or "").strip()
    if not wanted:
        return ""
    if wanted in corpus:
        return wanted
    matches = [key for key in corpus if key.startswith(wanted)]
    return matches[0] if len(matches) == 1 else ""


def corpus_by_pair(
    pairs: list[AnnotatedPair], corpus: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Return the subset of the corpus the pairs actually reference."""
    referenced: dict[str, list[str]] = {}
    for pair in pairs:
        key = resolve_paper(pair.source_paper, corpus)
        if key:
            referenced[key] = corpus[key]
    return referenced


def scorable(pairs: list[AnnotatedPair], corpus: dict[str, list[str]]) -> list[AnnotatedPair]:
    """Return the pairs retrieval can actually be scored on."""
    return [
        pair
        for pair in pairs
        if pair.source_passage.strip() and resolve_paper(pair.source_paper, corpus)
    ]


def build_client():
    """Return an OpenAI-compatible client from the environment, or None.

    Prints which variable supplied the credential, by name. The key itself is
    passed to the client and never printed, returned, or logged.
    """
    from openai import OpenAI

    for provider, key_name, base_name in CLIENT_ENV:
        key = os.getenv(key_name, "").strip()
        if not key:
            continue
        base = os.getenv(base_name, "").strip()
        print(f"client       : {provider}, key from {key_name}, base {base or '(default)'}")
        return OpenAI(api_key=key, base_url=base) if base else OpenAI(api_key=key)
    if os.getenv("OLLAMA_BASE_URL", "").strip():
        print("client       : ollama, from OLLAMA_BASE_URL")
        return OpenAI(api_key="ollama", base_url=os.environ["OLLAMA_BASE_URL"].strip())
    return None


def record_retrieval(pairs, corpus, *, embedder_name, limit):
    """Run the real retriever over every scorable pair and return the recording.

    Each source paper's index is built once and reused across the pairs that cite
    it. Embedding the paper per pair would repeat the whole of the expensive half
    of the run, fifty times for a fifty-pair set drawn from five papers.
    """
    print(f"embedder     : {embedder_name} (loading)")
    retriever = Retriever(Embedder(model_name=embedder_name))
    referenced = corpus_by_pair(pairs, corpus)
    built: set[str] = set()

    recorded: list[dict] = []
    for pair in pairs:
        key = resolve_paper(pair.source_paper, corpus)
        if not key or not pair.source_passage.strip():
            print(f"  skip {pair.claim[:52]!r}: no marked passage or no loaded source paper")
            continue
        if key not in built:
            retriever.build_index(referenced[key])
            built.add(key)
            print(f"  indexed {key[:8]} ({len(referenced[key])} passages)")
        passages = [item.passage for item in retriever.retrieve(pair.claim, k=limit)]
        rank = passage_eval.find_rank(pair.source_passage, passages)
        recorded.append({"claim": pair.claim, "source_paper": key, "retrieved": passages})
        print(f"  {key[:8]}  rank {rank if rank else '-'}  {pair.claim[:52]!r}")
    return recorded


def record_verdicts(pairs, *, client, model):
    """Run the real verifier over every annotated pair and return the recording."""
    verifier = Verifier(model=model)
    recorded: list[dict] = []
    for pair in pairs:
        if not pair.label:
            print(f"  skip {pair.claim[:52]!r}: no label to score against")
            continue
        result = verifier.verify(pair.claim, pair.source_passage, client=client)
        verdict = result.verdict.value if result.verdict is not None else ""
        recorded.append(
            {
                "claim": pair.claim,
                "status": result.status.value,
                "verdict": verdict,
                "confidence": result.confidence,
                "rationale": result.rationale,
            }
        )
        print(f"  {result.status.value:<14} {verdict or '-':<11} {pair.claim[:52]!r}")
    return recorded


def save(directory, name, payload):
    """Write one recording and return the path written."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load(directory, name):
    """Load one recording as its full payload, or ``None`` when there is none."""
    path = Path(directory) / f"{name}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {"pairs": list(payload or [])}


def retrieval_retrieve(recording):
    """Return a ``retrieve()`` that answers from a recording rather than a model."""
    by_claim = {entry["claim"]: list(entry.get("retrieved") or []) for entry in recording or []}

    def retrieve(claim, passages, k):
        return by_claim.get(claim, [])[:k]

    return retrieve


def verdict_judge(recording):
    """Return a ``judge()`` that answers from a recording rather than a model."""
    by_claim = {entry["claim"]: entry for entry in recording or []}

    def judge(pair):
        entry = by_claim.get(pair.claim)
        if entry is None:
            return Judgement(predicted="", status="NO_RECORDING")
        return Judgement(predicted=str(entry.get("verdict") or ""), status=str(entry.get("status")))

    return judge


def warn_missing(recording, expected, *, half, consequence):
    """Name the pairs a recording does not cover, so a green report is not read as one."""
    present = {entry["claim"] for entry in recording or []}
    missing = [pair.claim for pair in expected if pair.claim not in present]
    if not missing:
        return
    shown = ", ".join(item[:40] for item in missing[:5]) + (" ..." if len(missing) > 5 else "")
    print(
        f"\nWARNING: no {half} recording for {len(missing)} pair(s): {shown}\n"
        f"         They score as {consequence}, which is not a measurement of anything.\n"
        f"         Run --mode record before reading this report."
    )


def report_payload(pairs, retrieval_report, verdict_report):
    """Return the machine-readable form of both reports."""
    payload: dict = {"pairs": len(pairs)}
    if retrieval_report is not None:
        payload["retrieval"] = {
            "total": retrieval_report.total,
            "scored": retrieval_report.scored,
            "unscorable": retrieval_report.unscorable,
            "recall_at_1": retrieval_report.recall_at_1,
            "recall_at_5": retrieval_report.recall_at_5,
            "outcomes": [
                {"claim": item.claim, "source_paper": item.source_paper, "rank": item.rank}
                for item in retrieval_report.outcomes
            ],
        }
    if verdict_report is not None:
        payload["entailment"] = {
            "total": verdict_report.total,
            "judged": verdict_report.judged,
            "abstained": verdict_report.abstained,
            "unannotated": verdict_report.unannotated,
            "accuracy": verdict_report.accuracy,
            "f1_support_vs_rest": verdict_report.f1_support_vs_rest,
            "kappa": verdict_report.kappa,
            "confusion": verdict_report.confusion,
            "abstention_statuses": verdict_report.abstention_statuses,
        }
    return payload


def main(argv=None):
    """Run the harness. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("live", "record", "replay"), default="replay")
    parser.add_argument("--pairs", default=str(DEFAULT_PAIRS))
    parser.add_argument("--recordings", default=str(DEFAULT_RECORDINGS))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument(
        "--only",
        choices=("retrieval", "entailment", "both"),
        default="both",
        help="which half to run; the other is skipped entirely",
    )
    parser.add_argument("--embedder", default=DEFAULT_EMBEDDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=DEFAULT_K)
    parser.add_argument("--output", help="write the reports as JSON here")
    args = parser.parse_args(argv)

    pairs = load_pairs(args.pairs)
    corpus = load_corpus(args.corpus)
    print(f"pairs        : {args.pairs} ({len(pairs)} loaded)")
    print(f"corpus       : {args.corpus} ({len(corpus)} paper(s) with text)")

    if not pairs:
        print(
            "\nThe pair file is empty. It is the annotation target, not a fixture: neither\n"
            "metric can exist until the team's pairs are in it. CLAIM_PASSAGES.md holds the\n"
            "protocol and the annotation guidelines."
        )
        return 0

    unnamed = sorted(
        {pair.source_paper for pair in pairs if not resolve_paper(pair.source_paper, corpus)}
    )
    if unnamed:
        shown = ", ".join(unnamed[:5]) + (" ..." if len(unnamed) > 5 else "")
        available = ", ".join(sorted(corpus)[:6]) + (" ..." if len(corpus) > 6 else "")
        print(
            f"\nWARNING: {len(unnamed)} pair(s) name a source paper the corpus has no text for: "
            f"{shown}\n         Available papers: {available}"
        )

    wants_retrieval = args.only in ("retrieval", "both")
    wants_verdicts = args.only in ("entailment", "both")
    client = None
    if wants_verdicts and args.mode in ("live", "record"):
        client = build_client()
        if client is None:
            names = " or ".join(name for _, name, _ in CLIENT_ENV)
            print(
                f"\nNo LLM client is configured: set {names}.\n"
                "Refusing to run the judgement half without one -- a recording of NO_CLIENT\n"
                "results would be read later as a measurement that happened."
            )
            return 1

    passages_payload = load(args.recordings, "passages")
    judgements_payload = load(args.recordings, "judgements")
    retrieval_recording = (passages_payload or {}).get("pairs")
    verdict_recording = (judgements_payload or {}).get("pairs")
    recorded_limit = (passages_payload or {}).get("limit")

    if args.mode in ("live", "record"):
        referenced = corpus_by_pair(pairs, corpus)
        if wants_retrieval:
            retrieval_recording = record_retrieval(
                pairs, corpus, embedder_name=args.embedder, limit=args.limit
            )
            recorded_limit = args.limit
            if args.mode == "record":
                path = save(
                    args.recordings,
                    "passages",
                    {
                        "embedder": args.embedder,
                        "limit": args.limit,
                        "corpus_sizes": {key: len(text) for key, text in referenced.items()},
                        "pairs": retrieval_recording,
                    },
                )
                print(f"wrote {path}")
        if wants_verdicts:
            verdict_recording = record_verdicts(pairs, client=client, model=args.model)
            if args.mode == "record":
                path = save(
                    args.recordings,
                    "judgements",
                    {"model": args.model, "pairs": verdict_recording},
                )
                print(f"wrote {path}")

    if wants_retrieval and recorded_limit is not None and recorded_limit < DEFAULT_K:
        # Replay truncates a recording to the depth the bar is stated at, so a
        # shallow run caps Recall@5 below what the retriever could reach and the
        # report cannot tell that apart from a retriever that missed.
        print(
            f"\nWARNING: the recording was taken at limit {recorded_limit}, below the "
            f"top-{DEFAULT_K} the recall bar is\n         stated at. Recall@{DEFAULT_K} cannot "
            f"exceed that depth; re-record with --limit {DEFAULT_K} or deeper."
        )

    retrieval_report = verdict_report = None
    payload: dict = {"mode": args.mode, "only": args.only}

    if wants_retrieval:
        print()
        if args.mode == "replay":
            warn_missing(
                retrieval_recording,
                scorable(pairs, corpus),
                half="retrieval",
                consequence="misses",
            )
        retrieval_report = score_retrieval(
            pairs, corpus_by_pair(pairs, corpus), retrieval_retrieve(retrieval_recording)
        )
        print(render_retrieval_report(retrieval_report))
        if retrieval_report.unscorable:
            print(
                "\nthe pairs above were scored against no text at all, which is a gap in the\n"
                "corpus rather than a retrieval failure:"
            )
            for claim in retrieval_report.unscorable[:10]:
                print(f"  {claim[:88]}")

    if wants_verdicts:
        print()
        if args.mode == "replay":
            warn_missing(
                verdict_recording,
                [pair for pair in pairs if pair.label],
                half="entailment",
                consequence="abstentions",
            )
        verdict_report = score_verdicts(pairs, verdict_judge(verdict_recording))
        print(render_verdict_report(verdict_report))

    if retrieval_report is not None and verdict_report is not None:
        payload.update(report_payload(pairs, retrieval_report, verdict_report))
        if retrieval_report.recall_at_5 is not None and verdict_report.accuracy is not None:
            ceiling = retrieval_report.recall_at_5 * verdict_report.accuracy
            print(
                f"\nend-to-end ceiling: {ceiling * 100:.1f}%  (recall@5 x accuracy)\n"
                "                   the share of claims answered correctly when retrieval feeds\n"
                "                   the judgement. Each half is measured alone above, so a move\n"
                "                   in this number belongs to one of them."
            )

    if args.output:
        Path(args.output).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
