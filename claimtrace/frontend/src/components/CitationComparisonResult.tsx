import type { CitationComparisonResponse } from "../types/api";
import { VerdictBadge } from "./VerdictBadge";

export function CitationComparisonResult({ result, demo }: { result: CitationComparisonResponse; demo: boolean }) {
  const judgement = result.status === "COMPARED" ? result.judgement : null;
  return <section className="claim-comparison-result" aria-label="Citation comparison result">
    <div className="comparison-result-heading"><span><small>{demo ? "Example comparison · sample result" : "Citation comparison"}</small>
      {judgement ? <VerdictBadge verdict={judgement.verdict} /> : <strong>Not judged</strong>}
    </span>{judgement && <strong>{Math.round(judgement.confidence * 100)}%</strong>}</div>
    <p role="status">{result.message}</p>
    {!judgement && <small>{result.status.replace(/_/g, " ")}</small>}
    {judgement && <p>{judgement.rationale}</p>}
    {result.cited_source && <div className="database-source-card"><strong>{result.cited_source.title}</strong><p>{[result.cited_source.authors.join(", "), result.cited_source.venue, result.cited_source.year].filter(Boolean).join(" · ")}</p>{result.cited_source.url && <a href={result.cited_source.url} target="_blank" rel="noreferrer">Open source record</a>}</div>}
    {result.evidence.map((passage, index) => <blockquote key={`${passage.rank}-${index}`}>{passage.passage_text}<footer>Page {passage.page} · Passage {passage.rank + 1} · {Math.round(passage.similarity * 100)}% retrieval similarity</footer></blockquote>)}
  </section>;
}
