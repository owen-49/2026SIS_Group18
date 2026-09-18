"""Measure the identity rule against an annotated set of real references.

The thresholds in :mod:`engine.identity` are meant to be measured rather than
chosen, and this is the instrument. It scores the rule over
``reference_identity_fixture.json``, and with ``--sweep`` it re-scores at every
value of a threshold so the report says which case moves where rather than
asserting a number.

This file is not collected by pytest: the configured ``python_files`` is
``test_*.py``, and nothing here is a test. It lives under ``tests/`` so that the
CI lint step (``ruff check engine/ tests/``) covers it.

Usage, from ``claimtrace/engine``::

    python tests/benchmarks/identity_harness.py --mode record
    python tests/benchmarks/identity_harness.py --mode replay --sweep

Design notes:
- The two query sources are separated on purpose. Scoring the fixture's own
  query asks whether the identity rule is right; scoring ``--query-source
  parsed`` asks whether the reference parser and the rule together are right.
  Conflating them makes a parser bug look like an identity bug. Passing
  ``parsed`` prints both, so the difference is visible either way.
- ``--mode record`` writes what each provider returned, per provider, before the
  chain's short-circuit. A recorded set is the evidence, so it is kept whole: a
  later change to the provider order has to be re-recorded, not reinterpreted.
- A case that carries its own candidates is skipped by ``--mode record``. There
  is nothing to record -- its subject is a response the providers do not return
  -- and re-recording it would silently replace the constructed set with a live
  one, which is the one thing the case exists to avoid.
- Scoring is done over the union of every provider's records rather than through
  :func:`engine.metadata_lookup.lookup_reference`. The chain's early exit is
  covered by offline tests; measuring it here would mean the recorded evidence
  changes depending on the order the providers happen to be consulted in.
- A case with no recording scores against nothing, which reads as ``not_found``.
  That is indistinguishable from a provider that genuinely returned nothing, so
  the missing recordings are counted and named rather than left to be inferred
  from a green report.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Run as a script, so ``tests/benchmarks`` is on the path and the package root is
# not. Set before the engine imports below, which is why they carry a noqa.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine import identity  # noqa: E402
from engine.crossref_lookup import CrossrefLookup  # noqa: E402
from engine.metadata_eval import (  # noqa: E402
    candidate_to_dict,
    load_cases,
    load_recordings,
    query_for,
    render_report,
    render_sweep,
    save_recording,
    score_all,
    summarize,
    sweep_threshold,
    sweep_values,
)
from engine.openalex_lookup import OpenAlexLookup  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURE = HERE / "reference_identity_fixture.json"
DEFAULT_RECORDINGS = HERE / "recorded"

# OpenAlex first: it indexes the preprints and conference papers that several
# references in the manuscript set actually are, which Crossref covers thinly.
PROVIDER_NAMES = ("openalex", "crossref")

# The sweeps, and what each one is for. ``YEAR_TOLERANCE`` is the constant the
# annotated set is actually pinned by, so most of the report is about it.
# ``VENUE_MIN_MATCH_SHARE`` only ever breaks a tie, and is swept to show that --
# a constant nothing moves is worth stating as such rather than leaving a reader
# to wonder whether it was measured.
YEAR_SWEEP = ("YEAR_TOLERANCE", (0.0, 4.0, 1.0))
VENUE_SWEEP = ("VENUE_MIN_MATCH_SHARE", (0.0, 1.0, 0.05))
SWEEPS = (YEAR_SWEEP, VENUE_SWEEP)


def build_providers(names=PROVIDER_NAMES):
    """Return the providers to query, in chain order."""
    available = {"openalex": OpenAlexLookup, "crossref": CrossrefLookup}
    return [available[name]() for name in names]


def record(cases, *, source, limit, timeout, recordings_dir):
    """Ask the providers about every case that does not carry its own records."""
    collected: dict[str, list] = {}
    for case in cases:
        if case.candidates is not None:
            print(f"  skip {case.case_id}: the case carries its own candidates")
            continue
        query = query_for(case, source)
        per_provider = []
        union = []
        for provider in build_providers():
            response = provider.search(query, limit=limit, timeout_seconds=timeout)
            per_provider.append(
                {
                    "name": provider.name,
                    "status": response.status,
                    "error_code": response.error_code,
                    "error": response.error,
                    "candidates": [candidate_to_dict(item) for item in response.candidates],
                }
            )
            union.extend(response.candidates)
            print(
                f"  {case.case_id} {provider.name}: {response.status}, "
                f"{len(response.candidates)} record(s)"
                + (f" [{response.error_code}]" if response.error_code else "")
            )
        save_recording(
            recordings_dir,
            case.case_id,
            {
                "case_id": case.case_id,
                "query_source": source,
                "query": asdict(query),
                "providers": per_provider,
                "candidates": [candidate_to_dict(item) for item in union],
            },
        )
        collected[case.case_id] = union
    return collected


def describe(cases, recordings, *, source):
    """Print what each case resolved to, which is what the annotation is made from."""
    print("\n-- what the recorded candidates say --")
    for case in cases:
        score = score_all([case], recordings, source=source)[0]
        print(f"  {case.case_id}: {score.actual_status}/{score.rule or '-'} {score.selected_id}")
        print(f"      {score.detail}")


def report_payload(report, *, title, source):
    """Return the machine-readable form of a report."""
    return {
        "title": title,
        "query_source": source,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "precision": report.precision,
        "recall": report.recall,
        "unannotated": report.unannotated,
        "rules": report.rules,
        "statuses": report.actual_statuses,
        "cases": [asdict(score) for score in report.scores],
    }


def sweep_payload(points, *, attribute):
    """Return the machine-readable form of a sweep."""
    return {
        "attribute": attribute,
        "points": [
            {
                "value": point.value,
                "passed": point.passed,
                "total": point.total,
                "precision": point.precision,
                "recall": point.recall,
                "flips": point.flips,
            }
            for point in points
        ],
    }


def _missing_recordings(cases, recordings):
    return [
        case.case_id
        for case in cases
        if case.candidates is None and case.case_id not in recordings
    ]


def main(argv=None):
    """Run the harness. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("live", "record", "replay"), default="replay")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--recordings", default=str(DEFAULT_RECORDINGS))
    parser.add_argument(
        "--query-source",
        choices=("fixture", "parsed"),
        default="fixture",
        help="score the fixture's hand-checked query, or the one parsed from raw_text",
    )
    parser.add_argument("--sweep", action="store_true", help="sweep the identity thresholds")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", help="write the report, and any sweep, as JSON here")
    args = parser.parse_args(argv)

    cases = load_cases(args.fixture)
    print(f"fixture: {args.fixture} ({len(cases)} cases)")

    if args.mode in ("live", "record"):
        if args.mode == "record":
            print(f"recording into {args.recordings}")
        recordings = record(
            cases,
            source=args.query_source,
            limit=args.limit,
            timeout=args.timeout,
            recordings_dir=Path(args.recordings),
        )
        describe(cases, recordings, source=args.query_source)
    else:
        recordings = load_recordings(args.recordings)
        print(f"recordings: {args.recordings} ({len(recordings)} loaded)")

    missing = _missing_recordings(cases, recordings)
    if missing:
        print(
            f"\nWARNING: no recording for {len(missing)} case(s): {', '.join(missing)}.\n"
            "         They are scored against no records at all, which reads as not_found.\n"
            "         Run --mode record before reading this report."
        )

    sources = [args.query_source]
    # Both, whenever the parsed query is what is being scored: the difference
    # between the two is the part worth seeing.
    if args.query_source == "parsed":
        sources.insert(0, "fixture")

    payload = {"mode": args.mode, "reports": [], "sweeps": []}
    for source in sources:
        scores = score_all(cases, recordings, source=source)
        report = summarize(cases, scores)
        title = f"identity {args.mode}"
        print()
        print(render_report(report, title=title, source=source))
        payload["reports"].append(report_payload(report, title=title, source=source))

    if args.sweep:
        if args.mode != "replay":
            print("\n--sweep needs a recorded candidate set; ignored outside --mode replay")
        else:
            for attribute, (start, stop, step) in SWEEPS:
                points = sweep_threshold(
                    cases,
                    recordings,
                    sweep_values(start, stop, step),
                    attribute=attribute,
                    source=args.query_source,
                )
                print()
                print(render_sweep(points, attribute=attribute))
                payload["sweeps"].append(sweep_payload(points, attribute=attribute))

    if args.output:
        Path(args.output).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.output}")

    print(
        f"\nconstants in force: YEAR_TOLERANCE={identity.YEAR_TOLERANCE} "
        f"VENUE_MIN_MATCH_SHARE={identity.VENUE_MIN_MATCH_SHARE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
