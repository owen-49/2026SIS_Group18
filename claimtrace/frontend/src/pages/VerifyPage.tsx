import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface Match {
  passage_text: string;
  similarity: number;
  entailment_label: string;
  confidence: number;
}

interface VerifyResult {
  claim: string;
  verdict: string;
  confidence: number;
  rationale: string;
  matches: Match[];
}

export function VerifyPage() {
  const [claim, setClaim] = useState("");
  const [paperId, setPaperId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    if (!claim.trim() || !paperId.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const resp = await fetch(`${API_BASE}/api/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          claim: claim.trim(),
          source_paper_id: paperId.trim(),
        }),
      });

      if (!resp.ok) throw new Error(`Verification failed: ${resp.statusText}`);

      const data: VerifyResult = await resp.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    }

    setLoading(false);
  }

  return (
    <div className="page">
      <h2>Verify a Claim</h2>
      <p>Paste a claim from your paper and the ID of the source paper it cites.</p>

      <form onSubmit={handleVerify} className="verify-form">
        <label>
          Claim:
          <textarea
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            placeholder="e.g., The model exhibits emergent capabilities at scale..."
            rows={3}
          />
        </label>
        <label>
          Source Paper ID:
          <input
            type="text"
            value={paperId}
            onChange={(e) => setPaperId(e.target.value)}
            placeholder="Paper ID from Upload page"
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Verifying..." : "Verify"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="verify-result">
          <div className={`verdict verdict-${result.verdict.toLowerCase()}`}>
            <h3>
              {result.verdict === "SUPPORT" && "🟢 Supported"}
              {result.verdict === "PARTIAL" && "🟡 Partially Supported"}
              {result.verdict === "CONTRADICT" && "🔴 Contradicted"}
              {result.verdict === "NOT_FOUND" && "⚪ Not Found"}
            </h3>
            <span className="confidence">
              Confidence: {(result.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="rationale">{result.rationale}</p>
          {result.matches.length > 0 && (
            <div className="matches">
              <h4>Matched Passages</h4>
              {result.matches.map((m, i) => (
                <div key={i} className="match-card">
                  <p className="passage">{m.passage_text}</p>
                  <div className="match-meta">
                    <span>Similarity: {(m.similarity * 100).toFixed(0)}%</span>
                    <span>Label: {m.entailment_label}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
