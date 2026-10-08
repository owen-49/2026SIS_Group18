"""Build the Verify annotation worksheet from real citation contexts.

``CLAIM_PASSAGES.md`` fixes the protocol: one hundred pairs of (claim in a citing
paper, the passage in the cited paper that decides it), each labelled by a person
who read both. What that document leaves open is where a hundred real claim
sentences come from. Reading them out of the library's own manuscripts was
measured and rejected -- the corpus holds exactly one in-library citation -- and
downloading the cited PDFs would need on the order of a hundred fetches at a
yield near sixty percent.

So the claims come from Semantic Scholar's citation contexts instead: one request
per source paper returns up to a hundred sentences that cite it, written by real
authors about that exact work. The source paper is already parsed in this
repository, so the passage that decides each claim is a paragraph away.

Design notes:
- **Nothing here annotates.** The script produces candidates and the plumbing to
  fill them in; every label is written by a person. It writes ``label: ""``, which
  ``load_pairs`` reads as unannotated and every metric holds out, so a worksheet
  cannot be mistaken for a measured set.
- **The claim is captured verbatim**, including its citation marker. It is the
  thing being judged, and editing it would silently change the question.
- **The escape hatch is the point.** The worksheet shows the retriever's top five
  for each claim, but an annotator who finds the deciding passage elsewhere
  pastes it in: Recall@5 is then computed against that passage and honestly
  records a miss. A worksheet that offered only the retrieved passages would
  manufacture a perfect recall figure.
- **Provenance is a separate file.** ``load_pairs`` drops keys it does not know,
  silently and by design, so anything the pairs file needs to keep must be a
  field of ``AnnotatedPair``. The citing paper's title, year and link are not,
  and live in ``*.meta.json`` beside it.
- **The retrieval recording is the engine's own.** The prefetch is
  ``passage_harness.py --mode record --only retrieval``, which is what the
  scoring half reads back. Re-implementing it here would give the worksheet and
  the report two different notions of what the retriever returned.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "parser")]

from engine.passage_eval import DEFAULT_K, cohen_kappa, load_pairs, normalize_text  # noqa: E402

BENCHMARKS = ROOT / "engine" / "tests" / "benchmarks"
PARSED = ROOT / "backend" / "uploads" / "parsed"
VERIFY_SOURCES = PARSED / "verify-sources"

DEFAULT_WORKSHEET = BENCHMARKS / "claim_passages.worksheet.json"
DEFAULT_PAIRS = BENCHMARKS / "claim_passages.json"
DEFAULT_META = BENCHMARKS / "claim_passages.worksheet.meta.json"
DEFAULT_HTML = BENCHMARKS / "worksheet.html"
DEFAULT_CACHE = ROOT / "backend" / "tests" / "benchmarks" / "harvest"
DEFAULT_PREFETCH = BENCHMARKS / "worksheet_passages.json"
DEFAULT_CORPUS_VIEW = ROOT / "backend" / "tests" / "benchmarks" / "corpus"

S2_ENDPOINT = (
    "https://api.semanticscholar.org/graph/v1/paper/{identity}/citations"
    "?fields=contexts,title,year,externalIds&limit=100&offset={offset}"
)
USER_AGENT = "claimtrace-verify-worksheet/1.0 (+local annotation build)"


# ── The source papers the worksheet may draw claims for ───────────


@dataclass(frozen=True)
class Source:
    """One cited paper: where its text lives, and how to find who cites it.

    ``logical_key`` is the parsed-paper id the pairs name. For a paper already
    registered as a Verify source it is that record's id, so
    ``verify_sources.json`` maps it to itself; for the others it is the library
    copy's id, and the mapping is filled in when the PDF is uploaded through
    ``POST /api/verify/sources``. Either way the pair names a paper whose text is
    on disk, which is what retrieval scoring needs.
    """

    slug: str
    logical_key: str
    identity: str
    title: str
    aliases: tuple[str, ...]
    wanted: int


SOURCES: tuple[Source, ...] = (
    Source(
        slug="rag",
        logical_key="92574678",
        identity="arXiv:2005.11401",
        title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        aliases=("RAG", "retrieval-augmented generation", "Lewis et al"),
        wanted=35,
    ),
    Source(
        slug="memorylayers",
        logical_key="e61642a2",
        identity="arXiv:1907.05242",
        title="Large Memory Layers with Product Keys",
        aliases=("product key", "memory layer", "Lample", "product-key"),
        wanted=35,
    ),
    Source(
        slug="realm",
        logical_key="18b97d29",
        identity="arXiv:2002.08909",
        title="REALM: Retrieval-Augmented Language Model Pre-Training",
        aliases=("REALM", "Guu"),
        wanted=25,
    ),
    Source(
        slug="howtoread",
        logical_key="15ff6540",
        identity="DOI:10.1145/1273445.1273458",
        title="How to Read a Paper (Keshav)",
        aliases=("three-pass", "three pass", "Keshav", "how to read a paper"),
        wanted=15,
    ),
)


# ── Harvest: ask Semantic Scholar who cites each source ───────────


def fetch_json(url: str, *, attempts: int = 6, quiet: bool = False) -> dict:
    """Fetch one URL as JSON, backing off on the rate limit.

    Semantic Scholar's unauthenticated pool answers 429 readily; the retry is
    the documented behaviour rather than an optimisation. A 4xx that is not 429
    is returned to the caller so a bad source identity fails loudly.
    """
    delay = 4.0
    last = ""
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code != 429 and exc.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = type(exc).__name__
        if attempt < attempts:
            if not quiet:
                print(f"    {last}; retrying in {delay:.0f}s ({attempt}/{attempts})")
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise RuntimeError(f"gave up on {url} after {attempts} attempts ({last})")


def harvest(source: Source, cache: Path, *, pages: int, refresh: bool) -> list[dict]:
    """Return the raw citation pages for one source, from cache when present."""
    cache.mkdir(parents=True, exist_ok=True)
    pages_payload: list[dict] = []
    for page in range(pages):
        path = cache / f"{source.slug}-{page}.json"
        if refresh or not path.exists():
            url = S2_ENDPOINT.format(identity=source.identity, offset=page * 100)
            print(f"  {source.slug}: fetching page {page}")
            payload = fetch_json(url)
            path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("data") or []
        pages_payload.extend(entries)
        if not entries or payload.get("next") is None:
            break
    return pages_payload


# ── Filter: which contexts are a claim someone can actually judge ─

BRACKET = re.compile(r"\[[^\]]*\]")
PAREN_CITE = re.compile(r"\((?:[^()]*?\b(?:19|20)\d{2}[a-z]?[^()]*?)\)")
# Mathematical and private-use glyphs that come out of a PDF's equation layer,
# and the space-hyphen-space that a line break leaves behind.
GARBAGE = re.compile(r"[ -⁯⁰-₟ᴀ-ᵿⱠ-Ɀ꜠-ꟿ＀-￯]| - |−")
MIN_LENGTH = 40
MAX_LENGTH = 400


def collapse(text: str) -> str:
    return " ".join((text or "").split())


def single_citation(text: str) -> bool:
    """Whether the sentence cites exactly one work.

    A sentence citing several works cannot say which one it makes a claim about,
    and the annotator would be judging the wrong paper.
    """
    groups = BRACKET.findall(text) + PAREN_CITE.findall(text)
    if len(groups) != 1:
        return False
    return len(re.split(r",|;| and ", groups[0][1:-1])) == 1


def marker_of(text: str) -> str:
    """The one citation marker in a sentence, verbatim."""
    groups = BRACKET.findall(text) + PAREN_CITE.findall(text)
    return groups[0] if groups else ""


def usable(text: str) -> bool:
    """Whether a harvested context is a complete, self-contained sentence."""
    if not (MIN_LENGTH <= len(text) <= MAX_LENGTH):
        return False
    if not text.endswith((".", "!", "?")):
        return False
    if not (text[0].isupper() or text[0].isdigit() or text[0] in '"“('):
        return False
    if GARBAGE.search(text) or "http" in text:
        return False
    if not looks_english(text):
        return False
    if re.match(r"^\d+\s", text):  # a reference-list entry, not a claim
        return False
    return single_citation(text)


# Letters that are not English and not a PDF ligature. A sentence with several
# of them is in another language, or has been mangled by an encoding.
FOREIGN_LETTERS = re.compile(r"[^\x00-\x7f\ufb00-\ufb06]")
LIGATURES = "\ufb00\ufb01\ufb02\ufb03\ufb04\ufb05\ufb06"
# Words that appear in nearly every English sentence; a sentence with none of
# them and enough words to have some is not English.
FUNCTION_WORDS = frozenset(
    "the of and to in is that for with as by are this we it on be an which from at "
    "can has have not but its their our these those was were".split()
)


def looks_english(text: str) -> bool:
    """Whether the annotation protocol -- which is written in English -- can judge it.

    A claim in another language is not a harder case of the same task, it is a
    different one, and the team would be labelling it in translation. Short
    claims are exempt from the function-word test because a three-word claim can
    legitimately contain none.
    """
    letters = [letter for letter in FOREIGN_LETTERS.findall(text) if letter not in LIGATURES]
    if len(letters) >= 3:
        return False
    words = text.split()
    if len(words) < 6:
        return True
    lowered = {word.strip(".,;:()[]\u201c\u201d\"'").lower() for word in words}
    return bool(lowered & FUNCTION_WORDS)


def names_source(text: str, source: Source) -> bool:
    lowered = text.lower()
    return any(alias.lower() in lowered for alias in source.aliases)


def candidates_for(source: Source, entries: list[dict]) -> list[dict]:
    """Turn one source's citing papers into deduplicated candidate claims.

    Ranked so that the sentences naming the work come first -- those are the ones
    whose claim is unambiguously about it -- and shorter ones before longer, so
    the annotator reads a sentence rather than a paragraph. The order is total,
    so the worksheet is reproducible from the cache.
    """
    seen: set[str] = set()
    kept: list[dict] = []
    for entry in entries:
        citing = entry.get("citingPaper") or {}
        citing_id = str(citing.get("paperId") or "")
        for index, raw in enumerate(entry.get("contexts") or []):
            text = collapse(raw)
            if not usable(text):
                continue
            key = normalize_text(text)
            if key in seen:
                continue
            seen.add(key)
            kept.append(
                {
                    "claim": text,
                    "marker": marker_of(text),
                    "names_source": names_source(text, source),
                    "citing_id": citing_id,
                    "citing_title": collapse(str(citing.get("title") or "")),
                    "citing_year": citing.get("year"),
                    "citing_doi": (citing.get("externalIds") or {}).get("DOI") or "",
                    "index": index,
                }
            )
    kept.sort(key=lambda item: (not item["names_source"], len(item["claim"]), item["claim"]))
    return kept[: source.wanted]


def pair_id_for(source: Source, candidate: dict) -> str:
    """A stable, readable id: source, the citing paper, and which of its sentences."""
    return f"{source.slug}-{candidate['citing_id'][:8]}-{candidate['index']}"


# ── Writing the worksheet ─────────────────────────────────────────


def build_worksheet(cache: Path, *, pages: int, refresh: bool) -> tuple[list[dict], dict]:
    """Harvest every source and return the pairs and their provenance."""
    pairs: list[dict] = []
    meta: dict[str, dict] = {}
    for source in SOURCES:
        print(f"== {source.slug} ({source.title})")
        entries = harvest(source, cache, pages=pages, refresh=refresh)
        chosen = candidates_for(source, entries)
        print(f"  {len(entries)} citing paper(s) -> {len(chosen)} candidate(s)")
        for candidate in chosen:
            pair_id = pair_id_for(source, candidate)
            pairs.append(
                {
                    "claim": candidate["claim"],
                    "source_passage": "",
                    "label": "",
                    "source_paper": source.logical_key,
                    "citing_paper": candidate["citing_id"],
                    "annotator": "",
                    "notes": "",
                    "pair_id": pair_id,
                    "citation_marker": candidate["marker"],
                }
            )
            meta[pair_id] = {
                "source_slug": source.slug,
                "source_title": source.title,
                "source_logical_key": source.logical_key,
                "cited_s2_id": source.identity,
                "citing_s2_id": candidate["citing_id"],
                "citing_title": candidate["citing_title"],
                "citing_year": candidate["citing_year"],
                "citing_doi": candidate["citing_doi"],
                "names_source": candidate["names_source"],
            }
    pairs.sort(key=lambda pair: pair["pair_id"])
    return pairs, {"sources": [source.slug for source in SOURCES], "pairs": meta}


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # A caller may name a file outside the repository, so the path is only
    # shortened when shortening it means something.
    print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


def load_view(view: Path) -> dict[str, list[str]]:
    """Read the corpus view as ``paper id -> passage texts``."""
    corpus: dict[str, list[str]] = {}
    for path in sorted(Path(view).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        texts = [
            str(item.get("text", "")).strip()
            for item in payload.get("paragraphs") or []
            if str(item.get("text", "")).strip()
        ]
        if texts:
            corpus[path.stem] = texts
    return corpus


def resolve_key(wanted: str, corpus: dict[str, list[str]]) -> str:
    """Expand a paper's short id to the corpus key, or fail to.

    The same rule as ``passage_harness.resolve_paper``: the id, or an
    unambiguous prefix of it. A prefix matching nothing, or more than one paper,
    resolves to nothing rather than to a guess.
    """
    if wanted in corpus:
        return wanted
    matches = [key for key in corpus if key.startswith(wanted)]
    return matches[0] if len(matches) == 1 else ""


def prefetch(worksheet: Path, view: Path, out: Path, *, embedder_name: str, limit: int) -> int:
    """Retrieve the passages an annotator should see beside each claim.

    The engine harness records retrieval for *annotated* pairs only, since its
    recording carries the rank of the marked passage -- which is what makes it
    the wrong tool to run first. This is the display half of the same retrieval:
    the same embedder, the same depth, one index per source paper. Each source
    paper's index is built once and reused, so the four papers are embedded four
    times rather than a hundred and three.
    """
    from engine.embedder import Embedder
    from engine.retriever import Retriever

    pairs = json.loads(Path(worksheet).read_text(encoding="utf-8"))
    corpus = load_view(view)
    resolved = {pair["pair_id"]: resolve_key(pair["source_paper"], corpus) for pair in pairs}
    missing = sorted({pair["source_paper"] for pair in pairs if not resolved[pair["pair_id"]]})
    if missing:
        print(f"WARNING: no text for {len(missing)} source paper(s): {', '.join(missing)}")

    retriever = Retriever(Embedder(model_name=embedder_name))
    built: set[str] = set()
    recorded: list[dict] = []
    for pair in pairs:
        key = resolved[pair["pair_id"]]
        if not key:
            continue
        if key not in built:
            retriever.build_index(corpus[key])
            built.add(key)
            print(f"  indexed {key[:8]} ({len(corpus[key])} passages)")
        retrieved = [result.passage for result in retriever.retrieve(pair["claim"], k=limit)]
        recorded.append(
            {
                "claim": pair["claim"],
                "source_paper": key,
                "pair_id": pair["pair_id"],
                "retrieved": retrieved,
            }
        )
    write_json(out, {"embedder": embedder_name, "limit": limit, "pairs": recorded})
    return len(recorded)


def corpus_view(view: Path) -> int:
    """Link every parsed paper into one directory the engine harness can read.

    ``load_corpus`` globs a single directory, and the source papers live in two
    (the library's and the Verify-only uploads'). Linking both into one view lets
    ``passage_harness.py --corpus`` see all of them without teaching the engine
    about this repository's storage layout.
    """
    view.mkdir(parents=True, exist_ok=True)
    linked = 0
    for directory in (PARSED, VERIFY_SOURCES):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            if path.name.endswith(".references.json"):
                continue
            target = view / path.name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(path.resolve())
            linked += 1
    return linked


# ── The HTML worksheet ────────────────────────────────────────────

_HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim-passage worksheet</title>
<style>
:root { --ink:#1a1a1a; --dim:#5c5c5c; --line:#d8d4cc; --ground:#fbfaf7;
        --card:#ffffff; --accent:#7a4b2a; --ok:#2f6b45; }
* { box-sizing:border-box; }
body { margin:0; background:var(--ground); color:var(--ink);
       font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
header { position:sticky; top:0; background:var(--ground); border-bottom:1px solid var(--line);
         padding:14px 20px; display:flex; flex-wrap:wrap; gap:12px; align-items:baseline; }
h1 { font-size:17px; margin:0; font-weight:650; }
.hint { color:var(--dim); font-size:13px; }
main { padding:20px; display:flex; flex-direction:column; gap:16px; max-width:1100px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px;
        display:flex; flex-direction:column; gap:12px; }
.card.done { border-left:4px solid var(--ok); }
.claim { font-size:16px; }
.mark { font-variant-numeric:tabular-nums; color:var(--accent); font-weight:600; }
.prov { color:var(--dim); font-size:13px; }
.row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.passage { border:1px solid var(--line); border-radius:6px; padding:10px; font-size:14px;
           background:#faf9f6; display:flex; gap:10px; align-items:flex-start; }
.passage p { margin:0; flex:1; }
.passage .rank { color:var(--dim); font-size:12px; min-width:22px; }
button { font:inherit; border:1px solid var(--line); background:#fff; border-radius:6px;
         padding:5px 10px; cursor:pointer; }
button:hover { border-color:var(--accent); color:var(--accent); }
textarea { width:100%; min-height:64px; font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
           border:1px solid var(--line); border-radius:6px; padding:8px; background:#fff; }
label.choice { display:inline-flex; gap:5px; align-items:center; padding:5px 10px;
               border:1px solid var(--line); border-radius:999px; cursor:pointer; font-size:14px; }
label.choice input { margin:0; }
label.choice:has(input:checked) { border-color:var(--accent); background:#f6efe8; }
footer { padding:0 20px 40px; max-width:1100px; color:var(--dim); font-size:13px; }
</style>
</head>
<body>
<header>
  <h1>Claim-passage worksheet</h1>
  <span class="hint" id="counts"></span>
  <span class="hint">Label each claim, then click <b>Export</b> and send the file back.</span>
  <span class="row" style="margin-left:auto">
    <input id="filter" placeholder="filter claims"
           style="padding:5px 8px;border:1px solid var(--line);border-radius:6px">
    <button id="export">Export filled pairs</button>
  </span>
</header>
<main id="pairs"></main>
<footer>
  <p><b>Label.</b> SUPPORT — the cited paper states what the claim says it does.
  PARTIAL — the claim overstates it, drops a caveat, or mixes it with something else.
  CONTRADICT — the cited paper says the opposite. NOT_FOUND — the cited paper does not
  contain anything that decides the claim either way.</p>
  <p><b>Source passage.</b> Copy the sentence or two in the cited paper that decides the
  label. The five candidates shown are the retriever's top 5; use one, or paste a passage
  from elsewhere in the paper if none of them is the deciding one — a passage that is not
  among the candidates is recorded as a retrieval miss, and that is a real result rather
  than a mistake. Paste the text, do not paraphrase it.</p>
</footer>
<script>
const PAIRS = __PAIRS__;
const META = __META__;
const PASSAGES = __PASSAGES__;
const state = {};

function esc(text) {
  const node = document.createElement('div');
  node.textContent = text == null ? '' : String(text);
  return node.innerHTML;
}

function render() {
  const needle = document.getElementById('filter').value.trim().toLowerCase();
  const host = document.getElementById('pairs');
  host.innerHTML = '';
  let shown = 0;
  for (const pair of PAIRS) {
    const claim = pair.claim;
    const meta = META[pair.pair_id] || {};
    if (needle && !(claim.toLowerCase().includes(needle)
                    || (meta.citing_title || '').toLowerCase().includes(needle))) continue;
    shown += 1;
    const card = document.createElement('section');
    card.className = 'card' + (state[pair.pair_id].label ? ' done' : '');
    let candidates = (PASSAGES[claim] || []).map((passage, index) => `
      <div class="passage">
        <span class="rank">${index + 1}</span>
        <p>${esc(passage)}</p>
        <button data-pair="${esc(pair.pair_id)}" data-passage="${index}">use</button>
      </div>`).join('');
    if (!candidates) {
      candidates = '<p class="hint">No retrieved passages are recorded yet: run '
        + '<code>passage_harness.py --mode record --only retrieval</code>, then rebuild.</p>';
    }
    card.innerHTML = `
      <div class="claim">${esc(claim)} <span class="mark">${esc(pair.citation_marker)}</span></div>
      <div class="prov">${esc(meta.citing_title || pair.citing_paper)}
        ${meta.citing_year ? '(' + esc(meta.citing_year) + ')' : ''}
        &middot; cited paper: ${esc(meta.source_title || pair.source_paper)}
        &middot; <span class="mark">${esc(pair.pair_id)}</span></div>
      <div class="row">
        ${['SUPPORT', 'PARTIAL', 'CONTRADICT', 'NOT_FOUND'].map(label => `
          <label class="choice"><input type="radio" name="${esc(pair.pair_id)}"
            value="${label}" data-label="${esc(pair.pair_id)}"
            ${state[pair.pair_id].label === label ? 'checked' : ''}>${label}</label>`).join('')}
      </div>
      <div class="row">${candidates}</div>
      <textarea data-passage-text="${esc(pair.pair_id)}"
        placeholder="the deciding passage, copied verbatim"
        >${esc(state[pair.pair_id].source_passage)}</textarea>
      <input data-notes="${esc(pair.pair_id)}" placeholder="one sentence: why this label"
        value="${esc(state[pair.pair_id].notes)}"
        style="padding:6px 8px;border:1px solid var(--line);border-radius:6px">
      <input data-annotator="${esc(pair.pair_id)}" placeholder="your name"
        value="${esc(state[pair.pair_id].annotator)}"
        style="padding:6px 8px;border:1px solid var(--line);border-radius:6px">`;
    host.appendChild(card);
  }
  const labelled = PAIRS.filter(pair => state[pair.pair_id].label).length;
  document.getElementById('counts').textContent =
    `${shown} shown, ${labelled} of ${PAIRS.length} labelled`;
}

function download() {
  const filled = PAIRS.map(pair => Object.assign({}, pair, state[pair.pair_id]));
  const blob = new Blob([JSON.stringify(filled, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'claim_passages.annotated.json';
  link.click();
  URL.revokeObjectURL(link.href);
}

for (const pair of PAIRS) {
  state[pair.pair_id] = {
    label: pair.label || '', source_passage: pair.source_passage || '',
    notes: pair.notes || '', annotator: pair.annotator || '',
  };
}

document.addEventListener('change', event => {
  const target = event.target;
  if (target.dataset.label) state[target.dataset.label].label = target.value;
  if (target.dataset.notes !== undefined && target.dataset.notes) {
    state[target.dataset.notes].notes = target.value;
  }
  if (target.dataset.annotator) state[target.dataset.annotator].annotator = target.value;
  if (target.dataset.label) render();
});
document.addEventListener('input', event => {
  const target = event.target;
  if (target.dataset.passageText) state[target.dataset.passageText].source_passage = target.value;
  if (target.dataset.notes && target.dataset.notes !== '') {
    state[target.dataset.notes].notes = target.value;
  }
  if (target.dataset.annotator) state[target.dataset.annotator].annotator = target.value;
});
document.addEventListener('click', event => {
  const target = event.target;
  if (target.dataset.passage === undefined || !target.dataset.pair) return;
  const pair = PAIRS.find(item => item.pair_id === target.dataset.pair);
  const claim = pair ? pair.claim : '';
  const passage = (PASSAGES[claim] || [])[Number(target.dataset.passage)] || '';
  state[target.dataset.pair].source_passage = passage;
  render();
});
document.getElementById('filter').addEventListener('input', render);
document.getElementById('export').addEventListener('click', download);
render();
</script>
</body>
</html>
"""


def render_html(pairs: list[dict], meta: dict, prefetched: Path) -> str:
    """Fill the page template with the pairs, their provenance and the prefetch."""
    passages: dict[str, list[str]] = {}
    path = Path(prefetched)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload.get("pairs") or []:
            passages[entry["claim"]] = list(entry.get("retrieved") or [])[:DEFAULT_K]
    else:
        print(f"note: no prefetch at {path}; the page will show claims without candidates")
    return (
        _HTML_HEAD.replace("__PAIRS__", json.dumps(pairs, ensure_ascii=False))
        .replace("__META__", json.dumps(meta.get("pairs", {}), ensure_ascii=False))
        .replace("__PASSAGES__", json.dumps(passages, ensure_ascii=False))
    )


# ── Merge two annotators ──────────────────────────────────────────


def agreed_pairs(
    by_pair: list[dict[str, object]], usable: list[str], names: list[str]
) -> tuple[list[dict], int, int, int]:
    """Return the pairs both annotators labelled the same way, as file rows.

    A pair is written only when both annotators gave it the same non-empty label.
    A disagreement is not averaged, outvoted or settled by the first sheet: it
    stays unlabelled until a person adjudicates it, and an unlabelled pair is
    held out of every metric rather than counted as a question someone answered.

    The marked passage is carried from whichever sheet has one. Two different
    marked passages are a disagreement about the recall key, not about the label;
    the row keeps the first sheet's and the caller reports the count, because the
    pair is still scorable for the verdict half and dropping it would hide the
    conflict instead of showing it.

    Args:
        by_pair: Each annotator's pairs, keyed by ``pair_id``, in sheet order.
        usable: The shared ids whose claim text the sheets agree on.
        names: What to record as the annotator, one per sheet.

    Returns:
        The rows to write, the number of pairs held back for disagreeing, the
        number neither sheet has labelled yet, and the number whose two sheets
        marked different passages.
    """
    rows: list[dict] = []
    disagreed = 0
    unlabelled = 0
    contested = 0
    for pair_id in usable:
        first, second = (keyed[pair_id] for keyed in by_pair)
        if not first.label or not second.label:
            unlabelled += 1
            continue
        if first.label != second.label:
            disagreed += 1
            continue
        one, two = first.source_passage.strip(), second.source_passage.strip()
        if one and two and normalize_text(one) != normalize_text(two):
            contested += 1
        row = asdict(first)
        row["source_passage"] = one or two
        row["annotator"] = " & ".join(dict.fromkeys(names))
        row["notes"] = first.notes or second.notes
        rows.append(row)
    return rows, disagreed, unlabelled, contested


def write_pairs(target: Path, rows: list[dict]) -> int:
    """Write the agreed pairs into the pairs file, keeping what is already there.

    ``CLAIM_PASSAGES.md`` also offers a manual route that writes pairs straight
    into this file, so a merge that replaced the file would delete work done
    outside the worksheet. A row is only ever replaced by another row with the
    same ``pair_id``; everything else keeps its place.

    Returns:
        How many pairs were already in the file and kept.
    """
    existing: list = []
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        existing = payload if isinstance(payload, list) else payload.get("pairs") or []
    written = {row["pair_id"] for row in rows}
    kept = [row for row in existing if str(row.get("pair_id", "")) not in written]
    write_json(target, rows + kept)
    return len(kept)


def merge(files: list[Path], write_to: Path | None = None) -> int:
    """Report agreement between annotators and write the pairs they agree on."""
    annotators = [load_pairs(path) for path in files]
    by_pair = []
    for index, pairs in enumerate(annotators):
        keyed: dict[str, object] = {}
        for pair in pairs:
            if not pair.pair_id:
                print(f"{files[index]}: a pair has no pair_id; two annotators cannot be aligned")
                return 1
            keyed[pair.pair_id] = pair
        by_pair.append(keyed)

    # A sheet names its own annotator; the file name stands in when it does not,
    # so a written pair always records who stood behind it.
    names = [
        next(
            (pair.annotator.strip() for pair in keyed.values() if pair.annotator.strip()),
            path.stem,
        )
        for keyed, path in zip(by_pair, files)
    ]

    shared = sorted(set.intersection(*(set(keyed) for keyed in by_pair)))
    print(f"pairs        : {[len(keyed) for keyed in by_pair]} in {[path.name for path in files]}")
    print(f"shared ids   : {len(shared)}")

    disagreed_text = [
        pair_id
        for pair_id in shared
        if len({normalize_text(keyed[pair_id].claim) for keyed in by_pair}) > 1
    ]
    if disagreed_text:
        print(f"WARNING: {len(disagreed_text)} pair(s) carry different claim text; not compared:")
        for pair_id in disagreed_text[:5]:
            print(f"  {pair_id}")

    usable = [pair_id for pair_id in shared if pair_id not in disagreed_text]
    pairs_of_labels = [
        (by_pair[0][pair_id].label, by_pair[1][pair_id].label)
        for pair_id in usable
        if by_pair[0][pair_id].label and by_pair[1][pair_id].label
    ]
    agree = sum(1 for first, second in pairs_of_labels if first == second)

    print()
    for index, pairs in enumerate(annotators):
        count = sum(1 for pair in pairs if pair.label)
        print(f"annotator {index + 1}  : {count}/{len(pairs)} labelled")
    both = len(pairs_of_labels)
    if both:
        print(f"label agreement: {agree}/{both} = {agree / both * 100:.1f}%  (both labelled)")
        kappa = cohen_kappa(pairs_of_labels)
        print(f"cohen's kappa  : {'n/a' if kappa is None else f'{kappa:.3f}'}")
        tally: dict[str, int] = {}
        for first, second in pairs_of_labels:
            if first != second:
                tally[f"{first} vs {second}"] = tally.get(f"{first} vs {second}", 0) + 1
        if tally:
            listed = "  ".join(f"{name}={count}" for name, count in sorted(tally.items()))
            print(f"conflicts      : {listed}")
            print("                 (leave these unlabelled until they are adjudicated)")
    else:
        print("label agreement: n/a  (no pair has a label from both annotators)")

    marked = [
        pair_id
        for pair_id in usable
        if by_pair[0][pair_id].source_passage.strip() and by_pair[1][pair_id].source_passage.strip()
    ]
    same = sum(
        1
        for pair_id in marked
        if normalize_text(by_pair[0][pair_id].source_passage)
        == normalize_text(by_pair[1][pair_id].source_passage)
    )
    if marked:
        print(
            f"passage agree  : {same}/{len(marked)} = {same / len(marked) * 100:.1f}%"
            "   (the marked passage is what recall is scored against)"
        )

    if write_to is None:
        return 0
    rows, disagreed, unlabelled, contested = agreed_pairs(by_pair, usable, names)
    print()
    print(f"to write     : {len(rows)} pair(s) both annotators labelled the same")
    if disagreed:
        print(f"               {disagreed} disagreeing; adjudicate, then merge again")
    if unlabelled:
        print(f"               {unlabelled} not labelled by both yet")
    if contested:
        print(
            f"               {contested} marked two different passages; the first sheet's is kept"
        )
    kept = write_pairs(Path(write_to), rows)
    if kept:
        print(f"kept         : {kept} pair(s) already in the file, outside this worksheet")
    return 0


# ── Command line ──────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--harvest", action="store_true", help="fetch citation contexts and write the worksheet"
    )
    parser.add_argument(
        "--prefetch", action="store_true", help="retrieve candidates to show for each claim"
    )
    parser.add_argument("--html", action="store_true", help="render the local annotation page")
    parser.add_argument("--merge", nargs="+", type=Path, help="compare annotated files by pair_id")
    parser.add_argument(
        "--write",
        nargs="?",
        type=Path,
        const=DEFAULT_PAIRS,
        help="with --merge, write the agreed pairs into claim_passages.json",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="re-fetch even when the cache has the page"
    )
    parser.add_argument("--pages", type=int, default=3, help="citation pages per source (100 each)")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--html-out", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--prefetch-out", type=Path, default=DEFAULT_PREFETCH)
    parser.add_argument(
        "--embedder", default=None, help="embedding model; defaults to the engine's own"
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_K)
    parser.add_argument(
        "--corpus-view", action="store_true", help="link parsed papers into one corpus directory"
    )
    args = parser.parse_args(argv)

    if not any((args.harvest, args.prefetch, args.html, args.merge, args.corpus_view, args.write)):
        parser.print_help()
        return 1

    if args.corpus_view:
        linked = corpus_view(DEFAULT_CORPUS_VIEW)
        print(f"linked {linked} parsed paper(s) into {DEFAULT_CORPUS_VIEW.relative_to(ROOT)}")
        print(
            "now record the prefetch:\n"
            f"  cd {ROOT / 'engine'} && python tests/benchmarks/passage_harness.py "
            f"--mode record --only retrieval \\\n"
            f"      --pairs {args.worksheet.relative_to(ROOT)} "
            f"--corpus {DEFAULT_CORPUS_VIEW.relative_to(ROOT)}"
        )

    if args.harvest:
        pairs, meta = build_worksheet(args.cache, pages=args.pages, refresh=args.refresh)
        if not pairs:
            print("nothing harvested; the worksheet was not written")
            return 1
        write_json(args.worksheet, pairs)
        write_json(args.meta, meta)
        pooled = sum(1 for pair in pairs if meta["pairs"][pair["pair_id"]]["names_source"])
        print(
            f"\n{len(pairs)} pair(s), {pooled} naming the cited work; "
            "labels are the annotators' to write"
        )

    if args.prefetch:
        if not args.worksheet.exists():
            print(f"no worksheet at {args.worksheet.relative_to(ROOT)}; run --harvest first")
            return 1
        if not DEFAULT_CORPUS_VIEW.exists():
            linked = corpus_view(DEFAULT_CORPUS_VIEW)
            print(f"linked {linked} parsed paper(s) into {DEFAULT_CORPUS_VIEW.relative_to(ROOT)}")
        if args.embedder is None:
            # Resolved here rather than at import: prefetching is the only branch
            # that needs a model, and merging two sheets should not load one.
            from engine.embedder import DEFAULT_MODEL

            args.embedder = DEFAULT_MODEL
        count = prefetch(
            args.worksheet,
            DEFAULT_CORPUS_VIEW,
            args.prefetch_out,
            embedder_name=args.embedder,
            limit=args.limit,
        )
        print(f"{count} claim(s) prefetched")

    if args.html:
        if not args.worksheet.exists():
            print(f"no worksheet at {args.worksheet.relative_to(ROOT)}; run --harvest first")
            return 1
        pairs = json.loads(args.worksheet.read_text(encoding="utf-8"))
        meta = json.loads(args.meta.read_text(encoding="utf-8")) if args.meta.exists() else {}
        args.html_out.write_text(render_html(pairs, meta, args.prefetch_out), encoding="utf-8")
        print(f"wrote {args.html_out.relative_to(ROOT)}  ({len(pairs)} pair(s))")

    if args.write and not args.merge:
        print("--write needs --merge: it is the agreed pairs that are written")
        return 1
    if args.merge:
        if len(args.merge) != 2:
            print("--merge takes exactly two annotated files")
            return 1
        return merge(args.merge, args.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
