"""Measure the audit's field comparison over recorded audits.

Usage: python backend/scripts/audit_comparison_measurement.py DIR

DIR holds the ``*.json`` audits the audit route persisted (by default they land
under ``backend/uploads/parsed/audits/``). ``uploads/`` is gitignored, so this is
a tool a reviewer runs against their own corpus, not a test CI can run -- the
same standing as ``audit_live_acceptance.py``, which needs the network.

It answers one question: what does the comparison layer do with the records the
lookup actually found? Every recorded result carrying an external record is
re-run over the same entry and the same record, three ways:

  recorded   the status the audit wrote at the time. The baseline.
  naive      the values recovered from the raw text, read by the pre-change
             rule: any difference is METADATA_MISMATCH. This is the obvious fix
             -- swap the field source and stop -- and the reason the change is
             larger than a field-source swap.
  current    ``compare_external_metadata`` as it stands now.

Two things changed between "recorded" and "current", and the columns separate
them: which values are handed to the Engine comparator (stored structured fields
-> the query the lookup searched), and how its results are read (any difference
accuses -> a recovered difference withholds, and the author gate reads names
rather than spellings). "naive" is the first change without the second.

The "recorded" column is what makes the others readable, so the script
re-derives it by running the pre-change path over the stored fields and checks
the two agree. If they do not, the corpus was not recorded by the code this
measures and every number below it is suspect, so that is a failure.

Nothing here writes, and no lookup is performed: the external records come out
of the audit files themselves.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "parser")]

from backend.src.audit_models import (  # noqa: E402
    AuditStatus,
    ExternalRecord,
    ReferenceEntry,
)
from backend.src.services.bibliography_audit_service import (  # noqa: E402
    _normalise,
    _recovered_fields,
    compare_external_metadata,
)
from backend.src.services.reference_query import reference_query_for  # noqa: E402
from engine.bib_parser import BibEntry  # noqa: E402
from engine.bib_verifier import PdfMetadata, verify_bib_against_pdf  # noqa: E402

FIELDS = ("title", "authors", "year", "venue", "doi")
REQUIRED = ("title", "authors", "year", "venue")
COLUMNS = ("recorded", "naive", "current")


def engine_statuses(entry, record, use_query):
    """The Engine comparator's per-field status for this entry and record.

    ``use_query`` picks the values it is handed: the recovered ones, or the
    stored structured fields the pre-change code passed.
    """
    metadata = entry.metadata
    query = reference_query_for(entry) if use_query else metadata
    compared = verify_bib_against_pdf(
        BibEntry(
            key=metadata.key,
            entry_type=metadata.entry_type,
            title=query.title,
            authors=list(query.authors),
            year=query.year,
            venue=query.venue,
            doi=query.doi,
            raw_text=metadata.raw_text,
        ),
        PdfMetadata(**record.metadata.model_dump()),
    )
    return {check.field_name: check.status.value for check in compared.fields}


def legacy_verdict(statuses, metadata, record):
    """The verdict rule as it stood before the change.

    Kept as code rather than described in a comment, so the "recorded" and
    "naive" columns are produced by running the old rule instead of by
    remembering it. The author clause is the old one exactly -- ``_normalise``
    element by element -- and it is the clause the change replaces, so it has to
    be reproduced faithfully rather than approximated.
    """
    if "MISMATCH" in statuses.values():
        return AuditStatus.METADATA_MISMATCH
    complete = all(statuses.get(field) == "MATCH" for field in REQUIRED)
    exact = (
        _normalise(metadata.title) == _normalise(record.metadata.title)
        and [_normalise(name) for name in metadata.authors]
        == [_normalise(name) for name in record.metadata.authors]
        and _normalise(metadata.venue) == _normalise(record.metadata.venue)
    )
    return AuditStatus.VERIFIED if complete and exact else AuditStatus.NEEDS_REVIEW


def recorded_rows(directory):
    """Every recorded result carrying an external record, deduplicated.

    The same entry appears in every audit of its paper, and the survey below is
    about entries rather than about runs, so one record per (paper, entry).
    """
    rows = {}
    entries = {}
    for path in sorted(Path(directory).glob("*.json")):
        audit = json.loads(path.read_text(encoding="utf-8"))
        paper_id = audit["input_paper_id"]
        for result in audit.get("results", []):
            key = (paper_id, result["entry"]["entry_id"])
            entries.setdefault(key, (audit.get("input_type", "unknown"), result["entry"]))
            if result.get("matched_record"):
                rows.setdefault(key, (audit.get("input_type", "unknown"), result))
    return rows, entries


def corpus_field_sources(entries):
    """Which fields an entry carries structurally, and which the query supplies."""
    by_type = {}
    for input_type, entry_json in entries.values():
        entry = ReferenceEntry.model_validate(entry_json)
        query = reference_query_for(entry)
        counts = by_type.setdefault(input_type, [Counter(), Counter()])
        for field in FIELDS:
            if getattr(entry.metadata, field):
                counts[0][field] += 1
            if getattr(query, field):
                counts[1][field] += 1
    for input_type, (stored, query) in sorted(by_type.items()):
        total = sum(1 for kind, _ in entries.values() if kind == input_type)
        print(f"Entries from {input_type} input: {total}")
        print(f"  {'field':<10}{'structured':>12}{'query':>10}")
        for field in FIELDS:
            print(f"  {field:<10}{stored[field]:>12}{query[field]:>10}")
        print()


def measure(rows):
    distributions = {name: Counter() for name in COLUMNS}
    field_status = {field: Counter() for field in FIELDS}
    mismatches = Counter()
    accusations = Counter()
    examples = []
    disagreeing = []
    recovered_on_bib = 0
    stored_paths_reaching_exact = 0

    for _, (input_type, result) in sorted(rows.items()):
        entry = ReferenceEntry.model_validate(result["entry"])
        record = ExternalRecord.model_validate(result["matched_record"])
        recovered = _recovered_fields(entry, reference_query_for(entry))
        if input_type == "bib" and any(recovered.values()):
            recovered_on_bib += 1

        distributions["recorded"][result["status"]] += 1

        stored_statuses = engine_statuses(entry, record, False)
        if "MISMATCH" not in stored_statuses.values() and all(
            stored_statuses.get(field) == "MATCH" for field in REQUIRED
        ):
            stored_paths_reaching_exact += 1
        replayed = legacy_verdict(stored_statuses, entry.metadata, record)
        if replayed.value != result["status"]:
            disagreeing.append((result["entry"]["entry_id"], result["status"], replayed.value))

        query = reference_query_for(entry)
        distributions["naive"][
            legacy_verdict(engine_statuses(entry, record, True), query, record).value
        ] += 1

        status, checks, _ = compare_external_metadata(entry, record)
        distributions["current"][status.value] += 1
        for check in checks:
            field_status[check.field_name][check.status] += 1
            if check.status == "MISMATCH":
                mismatches[check.field_name] += 1
                if not recovered.get(check.field_name):
                    accusations[check.field_name] += 1
        if len(examples) < 6:
            for check in checks:
                if check.status == "MISMATCH" and len(examples) < 6:
                    examples.append(
                        (
                            check.field_name,
                            check.input_value[:58],
                            check.source_value[:58],
                            recovered.get(check.field_name, False),
                        )
                    )

    print(f"Matched records measured: {len(rows)}")
    print()
    print(f"{'status':<20}" + "".join(f"{name:>12}" for name in COLUMNS))
    for status in AuditStatus:
        counts = [distributions[name][status.value] for name in COLUMNS]
        if any(counts):
            print(f"{status.value:<20}" + "".join(f"{count:>12}" for count in counts))
    print()
    print("Per-field agreement under the current comparator:")
    shown = ("MATCH", "MISMATCH", "INPUT_MISSING", "SOURCE_MISSING")
    print(f"{'field':<10}" + "".join(f"{status:>15}" for status in shown))
    for field in FIELDS:
        print(f"{field:<10}" + "".join(f"{field_status[field][status]:>15}" for status in shown))
    print()

    if examples:
        print("Differences under the current comparator:")
        for field, left, right, was_recovered in examples:
            origin = "recovered" if was_recovered else "stored"
            print(f"  {field:<8} ({origin:<9}) {left!r} vs {right!r}")
        print()
    print(f"MISMATCHes, by field:        {dict(mismatches) or 'none'}")
    print(f"  of which from stored data: {dict(accusations) or 'none'}")
    print()

    failed = False
    bib_entries = sum(1 for kind, _ in rows.values() if kind == "bib")
    print(
        f"Fields recovered from raw text on the BibTeX path: {recovered_on_bib} "
        f"(of {bib_entries} matched BibTeX records)."
    )
    print("  A BibTeX entry's raw text is the @block itself, so nothing is recovered from it")
    print("  and its stored fields are compared exactly as before. Stated structurally:")
    print("  the corpus holds no matched BibTeX record to observe it on.")
    print()
    if recovered_on_bib:
        print(f"FAIL: {recovered_on_bib} BibTeX entries had a field 'recovered' from raw text.")
        print("The BibTeX path is supposed to be untouched by this change.")
        failed = True
    if disagreeing:
        print(f"FAIL: {len(disagreeing)} recorded statuses are not reproduced by the")
        print("pre-change path, so the corpus was not recorded by the code measured here:")
        for entry_id, recorded, replayed in disagreeing[:10]:
            print(f"  {entry_id}: recorded {recorded}, replayed {replayed}")
        failed = True
    if not failed:
        print("Recorded statuses reproduced exactly by the pre-change path, so the table")
        print("above holds the corpus fixed and varies only the comparison.")
        print()
        print(
            f"Rows where the old author clause decided the outcome: {stored_paths_reaching_exact}."
        )
        if stored_paths_reaching_exact == 0:
            print("  None: the stored fields are empty, so the old verdict was already")
            print("  NEEDS_REVIEW before the author clause was read. The replay therefore")
            print("  pins the field comparison but not that clause -- the 'naive' column is")
            print("  what exercises it, and it is the same code the replay validated.")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory of recorded audit JSON files.")
    arguments = parser.parse_args()
    if not arguments.directory.is_dir():
        parser.error(f"{arguments.directory} is not a directory")
    rows, entries = recorded_rows(arguments.directory)
    if not rows:
        print(f"No recorded audit under {arguments.directory} carries a matched record.")
        return 1
    corpus_field_sources(entries)
    return measure(rows)


if __name__ == "__main__":
    sys.exit(main())
