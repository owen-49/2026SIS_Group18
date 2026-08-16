import { useState } from "react";
import { verifyClaim } from "../api/client";
import { Icon } from "../components/Icon";
import { VerdictBadge } from "../components/VerdictBadge";
import { libraryPapers } from "../data/mockData";
import type { VerifyResponse } from "../types/api";

export function VerifyPage() {
  const [claim, setClaim] = useState("Self-attention enables the model to relate information from different positions in a sequence without recurrence.");
  const [paperId, setPaperId] = useState(libraryPapers[0].id);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!claim.trim() || !paperId) return;
    setLoading(true); setError(null); setResult(null);
    try { setResult(await verifyClaim(claim.trim(), paperId)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Verification failed"); }
    finally { setLoading(false); }
  }

  return (
    <div className="page-stack">
      <section className="page-heading"><span className="eyebrow">Single trace</span><h1>Verify a claim</h1><p>Compare one statement against its cited paper and inspect the strongest matching evidence.</p></section>
      <div className="verify-layout">
        <form className="panel form-panel" onSubmit={handleSubmit}>
          <div className="form-heading"><span className="step-number">1</span><div><h2>Claim and source</h2><p>Paste the exact sentence from your manuscript.</p></div></div>
          <label className="field"><span>Claim</span><textarea rows={6} value={claim} onChange={(event) => setClaim(event.target.value)} placeholder="Paste the claim you want to verify…" /><small>{claim.length} characters</small></label>
          <label className="field"><span>Cited source</span><select value={paperId} onChange={(event) => setPaperId(event.target.value)}>{libraryPapers.map((paper) => <option value={paper.id} key={paper.id}>{paper.title} ({paper.year})</option>)}</select></label>
          {error && <div className="inline-error">{error}</div>}
          <button className="button button-primary full-button" type="submit" disabled={loading || !claim.trim()}>{loading ? <><span className="spinner" /> Tracing evidence…</> : <><Icon name="verify" size={17} /> Verify claim</>}</button>
        </form>

        <section className={result ? "panel result-panel has-result" : "panel result-panel"}>
          {!result && !loading && <div className="result-empty"><span><Icon name="shield" size={28} /></span><h2>Your evidence trace appears here</h2><p>ClaimTrace will retrieve the closest source passage and assess how well it supports the claim.</p></div>}
          {loading && <div className="result-empty"><span className="scan-icon"><Icon name="search" size={28} /></span><h2>Reading the source</h2><p>Finding the strongest semantic match and checking entailment…</p></div>}
          {result && <>
            <div className="result-heading"><div><span className="eyebrow">Verdict</span><VerdictBadge verdict={result.verdict} /></div><div className="confidence-ring" style={{ "--confidence": `${result.confidence * 360}deg` } as React.CSSProperties}><span>{Math.round(result.confidence * 100)}%</span></div></div>
            <p className="result-rationale">{result.rationale}</p>
            <div className="evidence-section"><h3>Best matching passage</h3>{result.matches.map((match, index) => <blockquote key={index}><p>“{match.passage_text}”</p><footer><span>Semantic match {Math.round(match.similarity * 100)}%</span><span>Source passage</span></footer></blockquote>)}</div>
          </>}
        </section>
      </div>
    </div>
  );
}
