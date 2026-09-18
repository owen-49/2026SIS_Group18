"""Structural identity selection: which returned record, if any, is the cited work.

:func:`select_identity` answers one question with a rule rather than a score:
given a reference as a manuscript wrote it, and the records two metadata
providers returned for it, is there exactly one record that *is* that work?

Design notes:
- The decision is structural, never a weighted sum. A live query for
  "Attention Is All You Need" returns records registered by an unrelated
  organisation in 2025, with the real author list copied verbatim, no venue at
  all, and a ``posted-content`` type. Against the reference's 2017 they would
  earn an exact-title score plus an agreeing first author -- over any bar a
  weighted rule would plausibly set. What rejects them is structural: they have
  no venue and their year is eight years out. So the rule is written as
  independent hard filters, and no amount of title agreement can buy a way past
  one.
- ``preprint`` is therefore eligible, and must be. The correct record for
  several references in the manuscript set is an OpenAlex preprint; rejecting
  preprints would remove the reason to query OpenAlex at all. The spoof above is
  not stopped by its type, and the type filter is not a security boundary.
- ``YEAR_TOLERANCE`` is measured and is exactly 1. 0 rejects the correct IEEE
  TPAMI record, which Crossref dates 2015 where the reference says 2014; swept
  over the annotated set it scores 8 of 13 with recall at 50%. 2 admits the
  superseded CVPR version of the same paper, which the reference does not cite.
  Both were observed, so the value is pinned from both sides, and the sweep
  reports a flip at each.
- The identifier pre-pass deliberately bypasses the year veto and the venue
  requirement but not the type filter. A publisher's issued year drifts between
  providers for the same DOI, so requiring year agreement on a DOI match would
  reject records that are the same work by construction. For the same reason it
  accepts a DOI matched by more than one record: a shared identifier makes them
  one work, and demanding a single hit only pushed those references onto the
  weaker title path.
- Two records are the same work when they share a DOI, or when they agree on
  title, first author and year. The DOI relation was added after the annotated
  benchmark showed a reference left ambiguous between two records carrying one
  DOI and differing only in the year the two providers assigned it.
- A record that fails a filter is reported in ``rejected`` rather than dropped.
  ``not_found`` here means "the returned records do not include this work"; a
  caller that shows a person the rejected records is showing them records a
  provider did associate with the citation, which is the honest failure.
- There is no fuzzy tier, and the last step is threshold-free. An earlier
  revision selected a record whose title merely resembled the reference when the
  similarity cleared a floor and a second signal corroborated it. Measured
  against the annotated fixture, sweeping both of its constants across their
  whole usable range, it never once decided a case: the six resolvable references
  all settle on an identifier or an exact title, and the remaining candidates
  never reach it. A threshold nothing depends on cannot be measured, which is the
  one thing this module's constants are supposed to be, so the tier was removed
  rather than tuned. What replaced it asks only whether a record shares an
  informative title token with the reference -- a question with no constant in
  it. Records that do are handed back as ``ambiguous`` for a person to review;
  records that do not are ``not_found``, since a record sharing no informative
  token is not a near miss but a different work.
"""

from collections import Counter
from dataclasses import dataclass, field

from .title_matching import (
    extract_arxiv_id,
    first_author_surname,
    normalize_doi,
    normalize_title,
    normalize_venue,
    title_similarity,
    venue_match_share,
)

# Measured, not chosen. See the module docstring for both sides of the pin.
YEAR_TOLERANCE = 1

# A candidate venue must reproduce at least this share of the reference's venue
# tokens before it may break a tie, and it is only ever used to break a tie,
# never to reject. The shares on either side of the floor are measured -- the
# cited journal shares every token (1.0) where the conference version of the same
# paper shares two of six (0.33) -- but no case in the annotated set reaches the
# tiebreak, so the floor is placed between two measured shares rather than swept
# to a value. The sweep reports that plainly: 0 flips across the whole range.
VENUE_MIN_MATCH_SHARE = 0.5

# A deny-list, not an allow-list. A provider that starts emitting a publication
# type this module has never seen should not have it silently dropped, so the
# venue, year, and title filters carry the weight instead.
NON_PUBLICATION_KINDS = frozenset(
    {
        "component",
        "database",
        "dataset",
        "erratum",
        "grant",
        "journal",
        "journal-issue",
        "paratext",
        "peer-review",
        "reference-entry",
        "retraction",
        "software",
        "supplementary-materials",
    }
)


@dataclass
class ReferenceQuery:
    """A single reference as the manuscript gives it.

    Every field is optional: a reference list entry may carry nothing but a
    title, and :func:`select_identity` decides on whatever is present.
    """

    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""


@dataclass
class PublicationCandidate:
    """One record a provider returned for a query."""

    provider: str
    record_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    kind: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    is_repository: bool = False


@dataclass
class RejectedCandidate:
    """A candidate that failed a filter, and the filter it failed."""

    candidate: PublicationCandidate
    reason: str


@dataclass
class IdentityDecision:
    """The outcome of comparing one reference against one set of records.

    Attributes:
        status: ``"found"``, ``"ambiguous"``, or ``"not_found"``. Transport
            failures are not represented here; they belong to the provider
            layer, so a caller never has to read "not found" as "the request
            failed".
        selected: The record chosen, for ``"found"`` only.
        rule: Which tier decided, e.g. ``"doi"``, ``"exact-title+venue"``. Lets
            a report say whether a tier ever fires at all.
        reason: Human-readable justification.
        candidates: The records the deciding tier compared and passed over. For
            ``"ambiguous"`` that is every record still in contention; for a
            tie-break it is the losing side, so a reviewer can see what the
            venue overruled. Empty when nothing was in contention.
        rejected: Records dropped by the eligibility filter, each with the
            filter it failed.
    """

    status: str  # "found" | "ambiguous" | "not_found"
    selected: PublicationCandidate | None = None
    rule: str = ""
    reason: str = ""
    candidates: list[PublicationCandidate] = field(default_factory=list)
    rejected: list[RejectedCandidate] = field(default_factory=list)


def select_identity(
    query: ReferenceQuery,
    candidates: list[PublicationCandidate],
) -> IdentityDecision:
    """Decide which candidate record, if any, is the work the reference cites.

    Args:
        query: The reference as the manuscript wrote it.
        candidates: Every record the providers returned, across all providers.

    Returns:
        An :class:`IdentityDecision`. Never raises.
    """
    query_doi = normalize_doi(query.doi)
    query_arxiv = _normalize_arxiv(query.arxiv_id)
    query_title = normalize_title(query.title)

    if not query_title and not query_doi and not query_arxiv:
        return IdentityDecision(
            status="not_found",
            reason="the reference carries neither a usable title nor an identifier",
        )

    candidates = list(candidates or [])
    if not candidates:
        return IdentityDecision(
            status="not_found",
            reason="the providers returned no records for this reference",
        )

    # Step 1: identifiers first. An exact DOI or arXiv identifier is the work
    # itself, not evidence about it, so this path skips the year veto and the
    # venue requirement -- but not the type filter, since a component or a
    # peer-review record can share a DOI and is still not the work.
    for rule, wanted, extractor in (
        ("doi", query_doi, _candidate_doi),
        ("arxiv", query_arxiv, _candidate_arxiv),
    ):
        if not wanted:
            continue
        hits = [c for c in candidates if _kind_is_eligible(c.kind) and extractor(c) == wanted]
        if hits:
            # Every hit carries the reference's own identifier, so every hit is
            # the work. Two of them is the providers indexing one work twice --
            # measured, not hypothetical: one reference's DOI matched an OpenAlex
            # record and a Crossref record, and requiring exactly one hit sent the
            # reference down the title path, where it was settled by a weaker
            # rule than the identifier that was already in hand.
            return IdentityDecision(
                status="found",
                selected=_representative(hits),
                rule=rule,
                reason=(
                    f"the reference's {rule} identifies this record exactly"
                    if len(hits) == 1
                    else f"{len(hits)} records carry the reference's {rule}; they are one work"
                ),
            )

    eligible, rejected = _apply_eligibility_filter(query, candidates)

    if not query_title:
        return IdentityDecision(
            status="not_found",
            rule="identifier",
            reason=(
                f"no record carries the reference's identifier; "
                f"{_describe_rejections(rejected, len(candidates))}"
            ),
            rejected=rejected,
        )

    # Step 2: exact titles, compared as normalised strings rather than by
    # overlap, so that agreement cannot be accumulated gradually.
    exact = [c for c in eligible if normalize_title(c.title) == query_title]

    if len(exact) == 1:
        return IdentityDecision(
            status="found",
            selected=exact[0],
            rule="exact-title",
            reason="exactly one record's title matches the reference exactly",
            rejected=rejected,
        )

    if len(exact) > 1:
        groups = _group_same_work(exact)
        if len(groups) == 1:
            group = groups[0]
            selected = _representative(group)
            return IdentityDecision(
                status="found",
                selected=selected,
                rule="exact-title+dedup",
                reason=(
                    f"{len(group)} records match the title exactly and describe one work "
                    f"(same first author and year); one of them was kept"
                ),
                candidates=[c for c in group if c is not selected],
                rejected=rejected,
            )
        representatives = [_representative(group) for group in groups]
        tied = _venue_tiebreak(query, representatives)
        if tied is not None:
            return IdentityDecision(
                status="found",
                selected=tied,
                rule="exact-title+venue",
                reason="the reference's venue selects one of the exactly-matching records",
                candidates=[c for c in representatives if c is not tied],
                rejected=rejected,
            )
        return IdentityDecision(
            status="ambiguous",
            rule="exact-title",
            reason=(
                f"{len(representatives)} distinct works match the title exactly and the "
                f"reference does not separate them"
            ),
            candidates=representatives,
            rejected=rejected,
        )

    if not eligible:
        return IdentityDecision(
            status="not_found",
            rule="eligibility",
            reason=_describe_rejections(rejected, len(candidates)),
            rejected=rejected,
        )

    # Step 3: nothing matched exactly, so the only question left is what to hand
    # back for review. Ordering is by shared title tokens, but the decision is
    # not: a record goes to the caller if it shares an informative title token
    # with the reference, and one that shares none is not a near miss but a
    # different work, which offering as a choice would make a false one.
    scored = sorted(
        ((title_similarity(query.title, c.title), c) for c in eligible),
        key=lambda pair: -pair[0],
    )
    contenders = [candidate for score, candidate in scored if score > 0.0]

    if not contenders:
        return IdentityDecision(
            status="not_found",
            rule="title-overlap",
            reason=(
                "no record shares an informative title token with the reference; "
                f"{_describe_rejections(rejected, len(candidates))}"
            ),
            rejected=rejected,
        )

    return IdentityDecision(
        status="ambiguous",
        rule="title-overlap",
        reason=(
            f"no record's title matches the reference exactly; {len(contenders)} share "
            f"part of it and none of them is established"
        ),
        candidates=contenders[:3],
        rejected=rejected,
    )


def _kind_is_eligible(kind: str) -> bool:
    """Return whether a provider's record type can be a cited publication."""
    return (kind or "").strip().casefold() not in NON_PUBLICATION_KINDS


def _normalize_arxiv(value: str) -> str:
    """Return a bare arXiv identifier for a value that may be bare or dressed."""
    value = (value or "").strip()
    if not value:
        return ""
    return extract_arxiv_id(value) or extract_arxiv_id(f"arXiv:{value}")


def _candidate_doi(candidate: PublicationCandidate) -> str:
    return normalize_doi(candidate.doi)


def _candidate_arxiv(candidate: PublicationCandidate) -> str:
    for value in (candidate.arxiv_id, candidate.doi, candidate.url, candidate.record_id):
        found = _normalize_arxiv(value)
        if found:
            return found
    return ""


def _ineligibility_reason(query: ReferenceQuery, candidate: PublicationCandidate) -> str:
    """Return why a candidate cannot be the cited work, or an empty string."""
    if not _kind_is_eligible(candidate.kind):
        return "not a publication type"
    if not normalize_venue(candidate.venue):
        return "no venue"
    if query.year is not None and candidate.year is not None:
        if abs(query.year - candidate.year) > YEAR_TOLERANCE:
            return "year disagrees"
    if not normalize_title(candidate.title):
        return "no title"
    return ""


def _apply_eligibility_filter(
    query: ReferenceQuery,
    candidates: list[PublicationCandidate],
) -> tuple[list[PublicationCandidate], list[RejectedCandidate]]:
    eligible: list[PublicationCandidate] = []
    rejected: list[RejectedCandidate] = []
    for candidate in candidates:
        reason = _ineligibility_reason(query, candidate)
        if reason:
            rejected.append(RejectedCandidate(candidate=candidate, reason=reason))
        else:
            eligible.append(candidate)
    return eligible, rejected


def _group_same_work(
    candidates: list[PublicationCandidate],
) -> list[list[PublicationCandidate]]:
    """Group exactly-matching records by the work they describe.

    Two records describe one work when they carry the same DOI, and also when
    they agree on the normalised title, the first author's surname, and the
    year. Neither relation subsumes the other, which is why both are applied and
    their results merged rather than one being preferred.

    The identifier relation is the work itself, as directly as a statement about
    a record can be made. Measured: the correct record for one reference comes
    back from OpenAlex dated 2014 and from Crossref dated 2015, and a grouping
    that asked the year pair to agree split one work into two -- leaving the
    reference ambiguous between a record and itself. The second relation is what
    folds in a repository copy carrying no DOI at all, which the identifier
    relation cannot see.

    Year equality is required of the second relation rather than tolerated:
    without it the superseded conference version of a journal article would be
    folded into the cited journal record, and the two are different works with
    different DOIs. That protection does not depend on the year rule alone, since
    the two versions also carry different DOIs.

    Records are merged transitively, so a DOI pair and a title pair that share
    one record end up in one group rather than two.
    """
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def merge(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            # The lower index stays the root, so group order does not depend on
            # the order the relations happened to be applied in.
            parent[max(root_left, root_right)] = min(root_left, root_right)

    by_doi: dict[str, int] = {}
    by_work: dict[tuple[str, str, int | None], int] = {}
    for index, candidate in enumerate(candidates):
        doi = normalize_doi(candidate.doi)
        if doi:
            if doi in by_doi:
                merge(index, by_doi[doi])
            else:
                by_doi[doi] = index
        key = (
            normalize_title(candidate.title),
            first_author_surname(candidate.authors),
            candidate.year,
        )
        if key in by_work:
            merge(index, by_work[key])
        else:
            by_work[key] = index

    groups: dict[int, list[PublicationCandidate]] = {}
    for index, candidate in enumerate(candidates):
        groups.setdefault(find(index), []).append(candidate)
    return list(groups.values())


def _representative(group: list[PublicationCandidate]) -> PublicationCandidate:
    """Return the record to keep for a work the providers indexed more than once.

    Prefers a published record over a repository copy, since the published one
    carries the venue and DOI a person would cite. Ties break on provider and
    record id so the same input always yields the same record.
    """
    if len(group) == 1:
        return group[0]
    published = [c for c in group if not c.is_repository]
    return min(published or group, key=lambda c: (c.provider, c.record_id))


def _venue_tiebreak(
    query: ReferenceQuery,
    candidates: list[PublicationCandidate],
) -> PublicationCandidate | None:
    """Return the one candidate the reference's venue selects, or None.

    Abstains unless a single candidate has the strictly highest share, so a
    reference that names no venue, or names one that matches several records
    equally, is left to the caller as ambiguous.
    """
    shares = [(venue_match_share(query.venue, c.venue), c) for c in candidates]
    best = max(share for share, _ in shares)
    if best < VENUE_MIN_MATCH_SHARE:
        return None
    winners = [candidate for share, candidate in shares if share == best]
    return winners[0] if len(winners) == 1 else None


def _describe_rejections(rejected: list[RejectedCandidate], total: int) -> str:
    if not rejected:
        return f"none of the {total} returned records is the cited work"
    counts = Counter(item.reason for item in rejected)
    detail = ", ".join(f"{count} {reason}" for reason, count in counts.most_common())
    return f"{len(rejected)} of {total} records were ineligible ({detail})"
