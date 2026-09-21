"""Measure a conservative venue-abbreviation proposal without changing production.

Usage, from ``claimtrace``::

    python backend/scripts/venue_abbreviation_measurement.py \
        backend/uploads/parsed/audits

The audit directory is intentionally local and gitignored.  The script holds every
matched external record fixed, re-runs the current comparison, and then changes only
the venue decision.  It reports both the records newly promoted to ``VERIFIED`` and
every venue difference the proposal would admit.

The second half scores the same proposal against the annotated reference-identity
fixture.  Candidates explicitly marked forbidden (or belonging to a case whose
expected result is ``not_found``) are counted separately.  This prevents a coverage
number from hiding an unsafe admission.

This is a measurement instrument, not the proposed production implementation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "parser")]

from backend.src.audit_models import AuditStatus, ExternalRecord, ReferenceEntry  # noqa: E402
from backend.src.services.bibliography_audit_service import (  # noqa: E402
    _authors_agree,
    _normalise,
    _recovered_fields,
    compare_external_metadata,
)
from backend.src.services.reference_query import reference_query_for  # noqa: E402
from engine.title_matching import normalize_doi  # noqa: E402

DEFAULT_FIXTURE = ROOT / "engine" / "tests" / "benchmarks" / "reference_identity_fixture.json"
DEFAULT_RECORDINGS = ROOT / "engine" / "tests" / "benchmarks" / "recorded"

_TOKEN_RE = re.compile(r"[a-z]+|\d+(?:st|nd|rd|th)?", re.IGNORECASE)
_ORDINAL_RE = re.compile(r"\d+(?:st|nd|rd|th)?$")
_STOP_WORDS = {"a", "an", "and", "for", "in", "of", "on", "the"}
_LEADING_WRAPPERS = {
    "acm",
    "advances",
    "annual",
    "conference",
    "ieee",
    "meeting",
    "proceeding",
    "proceedings",
}
_TRAILING_WRAPPERS = {"long", "paper", "papers", "volume", "vol"}
_ABBREVIATION_ALIASES = {"neurips": "nips"}


@dataclass(frozen=True)
class AuditChange:
    paper_id: str
    entry_id: str
    current_status: str
    proposed_status: str
    input_venue: str
    source_venue: str
    recovered_from_raw_text: bool


def _tokens(value: str) -> list[str]:
    """Return venue words that contribute an initial."""
    return [
        token.casefold()
        for token in _TOKEN_RE.findall(value or "")
        if token.casefold() not in _STOP_WORDS and not _ORDINAL_RE.fullmatch(token)
    ]


def _short_abbreviation(value: str) -> str:
    """Return a compact abbreviation, or empty when ``value`` is not one."""
    raw_compact = "".join(_TOKEN_RE.findall(value or ""))
    compact = raw_compact.casefold()
    if not (2 <= len(compact) <= 10) or not compact.isalpha():
        return ""
    if len(_tokens(value)) != 1:
        return ""
    if compact not in _ABBREVIATION_ALIASES and sum(char.isupper() for char in raw_compact) < 2:
        return ""
    return _ABBREVIATION_ALIASES.get(compact, compact)


def _initialism_variants(value: str) -> set[str]:
    """Return conservative whole-name initialisms for a long venue name.

    Wrapper removal happens only at the edges.  That distinction prevents
    ``ACL`` from matching a NAACL venue merely because the longer organisation
    name contains "Association for Computational Linguistics" inside it.
    """
    tokens = _tokens(value)
    while tokens and tokens[-1] in _TRAILING_WRAPPERS:
        tokens.pop()
    variants: set[str] = set()
    current = list(tokens)
    while len(current) >= 2:
        variants.add("".join(token[0] for token in current))
        if current[0] not in _LEADING_WRAPPERS:
            break
        current = current[1:]
    # Provider names sometimes retain a literal acronym in the long name.
    variants.update(token for token in tokens if 2 <= len(token) <= 10)
    return {_ABBREVIATION_ALIASES.get(value, value) for value in variants}


def current_venues_agree(left: str, right: str) -> bool:
    """Reproduce the Engine comparator's current venue decision."""
    def normalise(value: str) -> str:
        return re.sub(r"[^a-z0-9\s]", "", (value or "").casefold()).strip()

    left_normalised = normalise(left)
    right_normalised = normalise(right)
    if not left_normalised or not right_normalised:
        return False
    if left_normalised == right_normalised:
        return True
    return SequenceMatcher(None, left_normalised, right_normalised).ratio() >= 0.8


def abbreviation_venues_agree(left: str, right: str) -> bool:
    """Return whether the current rule or the measured abbreviation rule agrees."""
    if current_venues_agree(left, right):
        return True
    for short, long in ((left, right), (right, left)):
        abbreviation = _short_abbreviation(short)
        if abbreviation and abbreviation in _initialism_variants(long):
            return True
    return False


def _project_status(entry: ReferenceEntry, record: ExternalRecord) -> tuple[AuditStatus, bool]:
    """Return the proposed status and whether a venue difference was admitted."""
    current_status, checks, _ = compare_external_metadata(entry, record)
    venue = next(check for check in checks if check.field_name == "venue")
    admitted = venue.status == "MISMATCH" and abbreviation_venues_agree(
        venue.input_value, venue.source_value
    )
    if not admitted:
        return current_status, False

    query = reference_query_for(entry)
    source = record.metadata
    recovered = _recovered_fields(entry, query)
    if any(
        check.status == "MISMATCH"
        and check.field_name != "venue"
        and not recovered.get(check.field_name)
        for check in checks
    ):
        return AuditStatus.METADATA_MISMATCH, True

    required = {"title", "authors", "year", "venue"}
    complete = all(
        check.status == "MATCH" or check.field_name == "venue"
        for check in checks
        if check.field_name in required
    )
    exact = (
        _normalise(query.title) == _normalise(source.title)
        and _authors_agree(list(query.authors), list(source.authors))
    )
    if complete and exact:
        return AuditStatus.VERIFIED, True
    return AuditStatus.NEEDS_REVIEW, True


def _audit_rows(directory: Path):
    """Yield unique matched records and retain their paper identifiers."""
    rows = {}
    audit_files = sorted(directory.glob("*.json"))
    for path in audit_files:
        audit = json.loads(path.read_text(encoding="utf-8"))
        paper_id = audit["input_paper_id"]
        for result in audit.get("results", []):
            if not result.get("matched_record"):
                continue
            key = (paper_id, result["entry"]["entry_id"])
            rows.setdefault(key, result)
    return audit_files, rows


def measure_audits(directory: Path) -> dict:
    """Measure projected Audit status changes over persisted results."""
    audit_files, rows = _audit_rows(directory)
    current_counts: Counter[str] = Counter()
    proposed_counts: Counter[str] = Counter()
    changes: list[AuditChange] = []
    for (paper_id, entry_id), result in sorted(rows.items()):
        entry = ReferenceEntry.model_validate(result["entry"])
        record = ExternalRecord.model_validate(result["matched_record"])
        current, _, _ = compare_external_metadata(entry, record)
        proposed, admitted = _project_status(entry, record)
        current_counts[current.value] += 1
        proposed_counts[proposed.value] += 1
        if admitted:
            query = reference_query_for(entry)
            changes.append(
                AuditChange(
                    paper_id=paper_id,
                    entry_id=entry_id,
                    current_status=current.value,
                    proposed_status=proposed.value,
                    input_venue=query.venue,
                    source_venue=record.metadata.venue,
                    recovered_from_raw_text=_recovered_fields(entry, query)["venue"],
                )
            )
    return {
        "audit_files": len(audit_files),
        "matched_records": len(rows),
        "current_counts": dict(current_counts),
        "proposed_counts": dict(proposed_counts),
        "new_verified": sum(
            change.current_status != AuditStatus.VERIFIED.value
            and change.proposed_status == AuditStatus.VERIFIED.value
            for change in changes
        ),
        "admitted_venue_differences": len(changes),
        "changes": [asdict(change) for change in changes],
    }


def _candidate_label(expected: dict, candidate: dict) -> str:
    doi = normalize_doi(candidate.get("doi", ""))
    acceptable = {normalize_doi(value) for value in expected.get("acceptable_dois", [])}
    forbidden = {normalize_doi(value) for value in expected.get("forbidden_dois", [])}
    forbidden_prefixes = [
        normalize_doi(value) for value in expected.get("forbidden_doi_prefixes", [])
    ]
    if expected.get("status") == "not_found":
        return "forbidden"
    if doi and doi in acceptable:
        return "acceptable"
    if doi and (doi in forbidden or any(doi.startswith(prefix) for prefix in forbidden_prefixes)):
        return "forbidden"
    return "unlabelled"


def measure_identity_fixture(fixture: Path, recordings: Path) -> dict:
    """Count newly admitted acceptable and forbidden recorded candidates."""
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
    counts: Counter[str] = Counter()
    admissions = []
    candidate_pairs = 0
    for case in cases:
        candidates = case.get("candidates")
        recording = recordings / f"{case['case_id']}.json"
        if candidates is None and recording.exists():
            candidates = json.loads(recording.read_text(encoding="utf-8")).get("candidates", [])
        for candidate in candidates or []:
            candidate_pairs += 1
            reference_venue = case["query"].get("venue", "")
            candidate_venue = candidate.get("venue", "")
            if current_venues_agree(reference_venue, candidate_venue):
                continue
            if not abbreviation_venues_agree(reference_venue, candidate_venue):
                continue
            label = _candidate_label(case["expected"], candidate)
            counts[label] += 1
            admissions.append(
                {
                    "case_id": case["case_id"],
                    "record_id": candidate.get("record_id", ""),
                    "label": label,
                    "input_venue": reference_venue,
                    "source_venue": candidate_venue,
                }
            )
    return {
        "cases": len(cases),
        "candidate_pairs": candidate_pairs,
        "new_acceptable_candidate_agreements": counts["acceptable"],
        "new_forbidden_candidate_agreements": counts["forbidden"],
        "new_unlabelled_candidate_agreements": counts["unlabelled"],
        "admissions": admissions,
    }


def _print_report(audits: dict, identity: dict) -> None:
    print(f"Audit files: {audits['audit_files']}")
    print(f"Matched records: {audits['matched_records']}")
    print(f"Current statuses: {audits['current_counts']}")
    print(f"Proposed statuses: {audits['proposed_counts']}")
    print(f"New VERIFIED: {audits['new_verified']}")
    print(f"Admitted venue differences: {audits['admitted_venue_differences']}")
    for change in audits["changes"]:
        print(
            f"  {change['entry_id']}: {change['input_venue']!r} -> "
            f"{change['source_venue']!r} "
            f"[{change['current_status']} -> {change['proposed_status']}]"
        )
    print("Identity-fixture candidate admissions:")
    print(
        f"  corpus: {identity['cases']} cases, "
        f"{identity['candidate_pairs']} candidate pairs"
    )
    print(f"  acceptable: {identity['new_acceptable_candidate_agreements']}")
    print(f"  forbidden:  {identity['new_forbidden_candidate_agreements']}")
    print(f"  unlabelled: {identity['new_unlabelled_candidate_agreements']}")
    for admission in identity["admissions"]:
        print(
            f"  {admission['case_id']} {admission['label']}: "
            f"{admission['input_venue']!r} -> {admission['source_venue']!r}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path, help="Directory containing persisted audit JSON")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--recordings", type=Path, default=DEFAULT_RECORDINGS)
    parser.add_argument("--output", type=Path, help="Write the complete measurement as JSON")
    args = parser.parse_args(argv)
    if not args.directory.is_dir():
        parser.error(f"{args.directory} is not a directory")

    payload = {
        "proposal": "current comparator plus conservative whole-name initialisms",
        "audits": measure_audits(args.directory),
        "identity_fixture": measure_identity_fixture(args.fixture, args.recordings),
    }
    _print_report(payload["audits"], payload["identity_fixture"])
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
