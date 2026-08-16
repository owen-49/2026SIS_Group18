import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { libraryPapers } from "../data/mockData";

const activity = [
  { title: "Attention Is All You Need", detail: "Citation evidence linked", time: "2 min ago", tone: "success" },
  { title: "BERT pre-training claim", detail: "Potential contradiction detected", time: "18 min ago", tone: "danger" },
  { title: "transformer-survey.pdf", detail: "12 citations audited", time: "1 hour ago", tone: "neutral" },
];

export function DashboardPage() {
  return (
    <div className="page-stack">
      <section className="page-heading heading-row">
        <div>
          <span className="eyebrow">Citation intelligence</span>
          <h1>Good afternoon.</h1>
          <p>Trace every academic claim back to the evidence that supports it.</p>
        </div>
        <Link className="button button-primary" to="/upload"><Icon name="upload" size={17} /> Upload papers</Link>
      </section>

      <section className="hero-card">
        <div className="hero-copy">
          <span className="hero-kicker"><Icon name="spark" size={14} /> Start a citation audit</span>
          <h2>Reviewer-proof your next paper.</h2>
          <p>Upload a manuscript and its sources. ClaimTrace finds the cited evidence, checks the claim, and ranks anything that needs your attention.</p>
          <div className="hero-actions">
            <Link className="button button-light" to="/audit">Run batch audit <Icon name="arrow" size={16} /></Link>
            <Link className="button button-ghost-light" to="/verify">Verify one claim</Link>
          </div>
        </div>
        <div className="trace-visual" aria-hidden="true">
          <div className="trace-paper trace-source"><span /><span /><span /></div>
          <div className="trace-line"><i /><i /><i /></div>
          <div className="trace-result"><Icon name="check" size={28} /><strong>Evidence found</strong><small>94% confidence</small></div>
        </div>
      </section>

      <section className="metric-grid">
        <article className="metric-card"><span className="metric-icon green"><Icon name="library" /></span><div><strong>{libraryPapers.length}</strong><p>Papers linked</p></div><small>All sources indexed</small></article>
        <article className="metric-card"><span className="metric-icon blue"><Icon name="verify" /></span><div><strong>12</strong><p>Claims checked</p></div><small className="positive">+12 this week</small></article>
        <article className="metric-card"><span className="metric-icon amber"><Icon name="audit" /></span><div><strong>3</strong><p>Need review</p></div><small>2 partial · 1 contradicted</small></article>
      </section>

      <section className="two-column-grid">
        <article className="panel">
          <div className="panel-heading"><div><h2>Recent activity</h2><p>Your latest traces and audits</p></div><button className="text-button" type="button">View all <Icon name="arrow" size={15} /></button></div>
          <div className="activity-list">
            {activity.map((item) => <div className="activity-row" key={item.title}><span className={`activity-dot ${item.tone}`} /><div><strong>{item.title}</strong><p>{item.detail}</p></div><time>{item.time}</time></div>)}
          </div>
        </article>
        <article className="panel extension-panel">
          <div className="extension-art"><span className="browser-bar" /><div className="mini-panel"><Icon name="search" size={15} /><span /><span /><span /></div></div>
          <div><span className="eyebrow">Chrome extension</span><h2>Trace citations in Overleaf</h2><p>Turn your <code>.bib</code> file into a searchable paper library without leaving the editor.</p><Link className="button button-secondary" to="/extension-setup">View setup guide</Link></div>
        </article>
      </section>
    </div>
  );
}
