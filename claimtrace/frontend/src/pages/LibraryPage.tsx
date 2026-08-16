import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { libraryPapers } from "../data/mockData";

export function LibraryPage() {
  const [query, setQuery] = useState("");
  const papers = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return libraryPapers;
    return libraryPapers.filter((paper) =>
      [paper.title, paper.authors, paper.venue, paper.citationKey].some((field) => field.toLowerCase().includes(value)),
    );
  }, [query]);

  return (
    <div className="page-stack">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Source collection</span><h1>Paper library</h1><p>Every source connected to this research workspace.</p></div>
        <button className="button button-primary" type="button"><Icon name="upload" size={17} /> Add sources</button>
      </section>

      <section className="toolbar panel">
        <label className="search-field"><Icon name="search" size={18} /><span className="sr-only">Search papers</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, author, venue, or citation key…" /></label>
        <span className="result-count">{papers.length} {papers.length === 1 ? "paper" : "papers"}</span>
      </section>

      <section className="paper-grid">
        {papers.map((paper) => (
          <article className="paper-card" key={paper.id}>
            <div className="paper-card-top"><span className={`paper-status status-${paper.status}`}><i />{paper.status === "linked" ? "Linked" : paper.status === "review" ? "Review metadata" : "PDF missing"}</span><span className="citation-key">{paper.citationKey}</span></div>
            <h2>{paper.title}</h2>
            <p>{paper.authors} · {paper.venue} {paper.year}</p>
            <div className="paper-card-footer"><span><Icon name="document" size={16} /> Source indexed</span>{paper.url && <a href={paper.url} target="_blank" rel="noreferrer">Open paper <Icon name="external" size={14} /></a>}</div>
          </article>
        ))}
      </section>

      {papers.length === 0 && <section className="empty-state panel"><span className="empty-icon"><Icon name="search" /></span><h2>No papers found</h2><p>Try another title, author, venue, or citation key.</p></section>}
    </div>
  );
}
