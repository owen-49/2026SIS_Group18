import { useMemo, useState } from "react";
import { runAudit } from "../api/client";
import { Icon } from "../components/Icon";
import { VerdictBadge } from "../components/VerdictBadge";
import { demoAudit } from "../data/mockData";
import type { AuditResponse, Verdict } from "../types/api";

type Filter = "ALL" | Verdict;

export function AuditPage() {
  const [audit, setAudit] = useState<AuditResponse | null>(demoAudit);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");

  async function refreshAudit() {
    setLoading(true);
    try { setAudit(await runAudit("transformer-survey.pdf", ["paper-attention", "paper-bert", "paper-gpt3", "paper-rag"])); }
    finally { setLoading(false); }
  }

  const results = useMemo(() => (audit?.results || []).filter((item) => {
    const matchesFilter = filter === "ALL" || item.verdict === filter;
    const value = query.toLowerCase();
    return matchesFilter && (!value || item.claim.toLowerCase().includes(value) || item.citation_key.toLowerCase().includes(value));
  }), [audit, filter, query]);

  return (
    <div className="page-stack">
      <section className="page-heading heading-row"><div><span className="eyebrow">Risk-ranked review</span><h1>Batch audit</h1><p>Review every cited claim, starting with the evidence gaps that matter most.</p></div><button className="button button-primary" type="button" disabled={loading} onClick={() => void refreshAudit()}>{loading ? <><span className="spinner" /> Auditing…</> : <><Icon name="audit" size={17} /> Run audit</>}</button></section>

      {audit && <>
        <section className="audit-summary panel">
          <div className="audit-score"><div className="score-ring"><strong>{Math.round((audit.supported / audit.total_citations) * 100)}</strong><small>% supported</small></div><div><span className="eyebrow">{audit.manuscript_id}</span><h2>{audit.total_citations} citations checked</h2><p>{audit.contradicted + audit.not_found} high-risk claims should be reviewed before submission.</p></div></div>
          <div className="summary-bars"><div><span>Supported <b>{audit.supported}</b></span><i><em style={{ width: `${audit.supported / audit.total_citations * 100}%` }} /></i></div><div><span>Partial <b>{audit.partial}</b></span><i><em className="partial-bar" style={{ width: `${audit.partial / audit.total_citations * 100}%` }} /></i></div><div><span>Contradicted / missing <b>{audit.contradicted + audit.not_found}</b></span><i><em className="danger-bar" style={{ width: `${(audit.contradicted + audit.not_found) / audit.total_citations * 100}%` }} /></i></div></div>
        </section>

        <section className="panel audit-table-panel">
          <div className="audit-toolbar"><div className="filter-tabs">{(["ALL", "CONTRADICT", "PARTIAL", "SUPPORT", "NOT_FOUND"] as Filter[]).map((value) => <button className={filter === value ? "active" : ""} key={value} onClick={() => setFilter(value)}>{value === "ALL" ? "All claims" : value.replace("_", " ")}</button>)}</div><label className="search-field compact"><Icon name="search" size={17} /><span className="sr-only">Search audit</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search claims…" /></label></div>
          <div className="audit-table-wrap"><table className="audit-table"><thead><tr><th>Risk</th><th>Claim</th><th>Citation</th><th>Verdict</th><th>Confidence</th><th /></tr></thead><tbody>{results.map((item) => <tr key={`${item.citation_key}-${item.claim}`}><td><span className={`risk-dot risk-${item.risk_level}`} /></td><td><strong>{item.claim}</strong></td><td><code>{item.citation_key}</code></td><td><VerdictBadge verdict={item.verdict} /></td><td>{Math.round(item.confidence * 100)}%</td><td><button className="icon-button" aria-label={`Open ${item.citation_key}`}><Icon name="arrow" size={16} /></button></td></tr>)}</tbody></table></div>
          {results.length === 0 && <div className="table-empty">No citations match this view.</div>}
        </section>
      </>}
    </div>
  );
}
