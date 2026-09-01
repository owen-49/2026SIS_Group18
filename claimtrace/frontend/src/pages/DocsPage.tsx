import { Link } from "react-router-dom";
import { Icon, type IconName } from "../components/Icon";

const workflows: { icon: IconName; title: string; text: string; to: string; action: string }[] = [
  { icon: "upload", title: "Add your files", text: "Open Paper Library to upload PDF manuscripts or BibTeX bibliographies and track their backend parsing status.", to: "/library?upload=1", action: "Open Paper Library" },
  { icon: "verify", title: "Review extracted claims", text: "Choose an uploaded manuscript, inspect its automatically extracted claims and identified cited papers, then run verification.", to: "/verify", action: "Review claims" },
  { icon: "audit", title: "Review a full paper", text: "Rank citations by risk and inspect unsupported, partial, or contradictory claims first.", to: "/audit", action: "Open batch audit" },
];

const verdicts = [
  { label: "Supported", className: "support", text: "The retrieved source passage directly supports the claim." },
  { label: "Partial", className: "partial", text: "The source supports part of the claim, but a caveat or limitation is missing." },
  { label: "Contradicted", className: "contradict", text: "The source passage disagrees with the claim." },
  { label: "Not found", className: "not-found", text: "No retrieved passage addresses the claim well enough." },
];

export function DocsPage() {
  return (
    <div className="page-stack docs-page">
      <section className="page-heading heading-row">
        <div>
          <span className="eyebrow">Product guide</span>
          <h1>Help & documentation</h1>
          <p>Learn the ClaimTrace workflow, understand the current demo, and connect the interface to the backend.</p>
        </div>
        <Link className="button button-secondary" to="/"><span aria-hidden="true">←</span> Back to overview</Link>
      </section>

      <section className="docs-callout" id="demo-workspace">
        <span className="docs-callout-icon"><Icon name="spark" size={22} /></span>
        <div>
          <span className="eyebrow">Current environment</span>
          <h2>What does “Demo workspace” mean?</h2>
          <p>The dashboard is using deterministic sample audit results. Uploaded paper names are kept in this browser session so you can switch manuscripts, but the findings are not yet generated from those files.</p>
        </div>
        <span className="demo-pill"><i /> Mock API active</span>
      </section>

      <section>
        <div className="section-heading"><span className="eyebrow">Start here</span><h2>Three core workflows</h2></div>
        <div className="docs-workflow-grid">
          {workflows.map((workflow, index) => (
            <article className="panel docs-workflow-card" key={workflow.title}>
              <div className="workflow-card-top"><span className="workflow-icon"><Icon name={workflow.icon} /></span><small>0{index + 1}</small></div>
              <h3>{workflow.title}</h3>
              <p>{workflow.text}</p>
              <Link to={workflow.to}>{workflow.action} <Icon name="arrow" size={14} /></Link>
            </article>
          ))}
        </div>
      </section>

      <section className="docs-two-column">
        <article className="panel docs-section-card">
          <div className="docs-section-heading"><span className="docs-heading-icon"><Icon name="shield" size={19} /></span><div><span className="eyebrow">Reading results</span><h2>What each verdict means</h2></div></div>
          <div className="verdict-doc-list">
            {verdicts.map((verdict) => <div key={verdict.label}><span className={`verdict-doc-dot ${verdict.className}`} /><div><strong>{verdict.label}</strong><p>{verdict.text}</p></div></div>)}
          </div>
          <div className="docs-warning"><strong>About confidence</strong><p>Confidence values are demonstration data today. The project documents define the API field but do not yet define a calibrated confidence algorithm.</p></div>
        </article>

        <article className="panel docs-section-card">
          <div className="docs-section-heading"><span className="docs-heading-icon"><Icon name="external" size={19} /></span><div><span className="eyebrow">Browser extension</span><h2>Use ClaimTrace in Overleaf</h2></div></div>
          <p className="docs-body-copy">Load the local extension into Chrome, select a <code>.bib</code> file in Overleaf, and open the ClaimTrace Side Panel to search the detected bibliography.</p>
          <div className="extension-mini-flow"><span>Overleaf <code>.bib</code></span><Icon name="arrow" size={15} /><span>Paper library</span><Icon name="arrow" size={15} /><span>Evidence trace</span></div>
          <Link className="button button-primary full-button" to="/extension-setup">Open extension setup guide <Icon name="arrow" size={15} /></Link>
        </article>
      </section>

      <section className="panel api-doc-card">
        <div><span className="eyebrow">Backend integration</span><h2>Switch from demo data to FastAPI</h2><p>Create <code>frontend/.env.local</code> with these values, then restart the Vite server. Automatic claim review expects <code>GET /api/papers/:paper_id/claims</code>; the interface shows an unavailable state until that analysis endpoint exists.</p></div>
        <pre><code>{`VITE_USE_MOCK_API=false\nVITE_API_URL=http://localhost:8000`}</code></pre>
      </section>
    </div>
  );
}
