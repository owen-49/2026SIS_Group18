import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getPapers } from "../api/client";
import { Icon } from "../components/Icon";
import type { PaperListItem } from "../types/api";

export function LibraryPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [allPapers, setAllPapers] = useState<PaperListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getPapers()
      .then((response) => {
        if (active) setAllPapers(response.papers);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "Unable to load papers");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const papers = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return allPapers;
    return allPapers.filter((paper) =>
      [paper.title || "", paper.original_filename, paper.paper_id, paper.file_type, paper.status]
        .some((field) => field.toLowerCase().includes(value)),
    );
  }, [allPapers, query]);

  return (
    <div className="page-stack">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Source collection</span><h1>Paper library</h1><p>Every source connected to this research workspace.</p></div>
        <button className="button button-primary" type="button" onClick={() => navigate("/upload")}><Icon name="upload" size={17} /> Add sources</button>
      </section>

      <section className="toolbar panel">
        <label className="search-field"><Icon name="search" size={18} /><span className="sr-only">Search papers</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, author, venue, or citation key…" /></label>
        <span className="result-count">{papers.length} {papers.length === 1 ? "paper" : "papers"}</span>
      </section>

      <section className="paper-grid">
        {papers.map((paper) => {
          const statusClass = paper.status === "completed" ? "linked" : paper.status === "failed" ? "missing" : "review";
          return (
            <article className="paper-card" key={paper.paper_id}>
              <div className="paper-card-top"><span className={`paper-status status-${statusClass}`}><i />{paper.status}</span><span className="citation-key">{paper.paper_id.slice(0, 8)}</span></div>
              <h2>{paper.title || paper.original_filename}</h2>
              <p>{paper.original_filename} · {paper.file_type.toUpperCase()} · {paper.paragraph_count} paragraphs</p>
              <div className="paper-card-footer"><span><Icon name="document" size={16} /> {paper.status === "completed" ? "Source indexed" : "Source processing"}</span></div>
            </article>
          );
        })}
      </section>

      {loading && <section className="empty-state panel"><h2>Loading papers…</h2></section>}
      {error && <section className="empty-state panel"><h2>Unable to load papers</h2><p>{error}</p></section>}
      {!loading && !error && papers.length === 0 && <section className="empty-state panel"><span className="empty-icon"><Icon name="search" /></span><h2>No papers found</h2><p>Upload a PDF or try another search.</p></section>}
    </div>
  );
}
