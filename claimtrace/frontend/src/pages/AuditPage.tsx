export function AuditPage() {
  return (
    <div className="page">
      <h2>Batch Audit</h2>
      <p>
        Run a full citation audit on your manuscript. Coming in Sprint 2 (W5-W6).
      </p>
      <div className="placeholder">
        <p>
          This dashboard will show a risk-ranked report of all citations:
          🟢 Supported · 🟡 Partial · 🔴 Contradicted · ⚪ Not Found
        </p>
      </div>
    </div>
  );
}
