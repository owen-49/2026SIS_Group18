import { useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";

const extensionPath = "claimtrace/extension";

interface CopyButtonProps {
  label: string;
  value: string;
}

function CopyButton({ label, value }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function copyValue() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button className={copied ? "copy-button copied" : "copy-button"} type="button" onClick={() => void copyValue()}>
      {copied ? <><Icon name="check" size={14} /> Copied</> : label}
    </button>
  );
}

const steps = [
  {
    number: "01",
    title: "Open Chrome extensions",
    description: "Paste the address below into Chrome's address bar. Chrome does not allow websites to open this protected page automatically.",
    value: "chrome://extensions",
    copyLabel: "Copy address",
  },
  {
    number: "02",
    title: "Enable Developer mode",
    description: "Turn on Developer mode using the switch in the top-right corner of the Extensions page.",
  },
  {
    number: "03",
    title: "Load the extension folder",
    description: "Choose Load unpacked, then select the extension directory inside this repository.",
    value: extensionPath,
    copyLabel: "Copy folder path",
  },
  {
    number: "04",
    title: "Open a bibliography in Overleaf",
    description: "Open an Overleaf project and select a .bib file. ClaimTrace will detect visible BibTeX entries and offer to build the paper library.",
  },
  {
    number: "05",
    title: "Launch the Side Panel",
    description: "Click ClaimTrace in Chrome's toolbar or select Open ClaimTrace in the Overleaf prompt. Search and open papers without leaving the editor.",
  },
];

export function ExtensionSetupPage() {
  return (
    <div className="page-stack setup-page">
      <section className="page-heading heading-row">
        <div>
          <span className="eyebrow">Chrome extension</span>
          <h1>Set up ClaimTrace in Overleaf</h1>
          <p>Load the local Manifest V3 extension and turn your BibTeX file into a searchable paper library.</p>
        </div>
        <Link className="button button-secondary" to="/"><span aria-hidden="true">←</span> Back to overview</Link>
      </section>

      <section className="setup-hero panel">
        <div className="setup-preview" aria-hidden="true">
          <div className="preview-browser"><i /><i /><i /><span /></div>
          <div className="preview-editor"><span /><span /><span /><span /></div>
          <div className="preview-sidepanel"><strong>ClaimTrace</strong><i /><i /><i /></div>
        </div>
        <div>
          <span className="setup-status"><i /> No build step required</span>
          <h2>From repository to Side Panel in five steps.</h2>
          <p>The extension is plain Manifest V3 JavaScript, so Chrome can load the source directory directly.</p>
          <div className="setup-requirements"><span><Icon name="check" size={14} /> Google Chrome</span><span><Icon name="check" size={14} /> Overleaf project</span><span><Icon name="check" size={14} /> Local repository</span></div>
        </div>
      </section>

      <section className="setup-layout">
        <div className="setup-steps">
          {steps.map((step) => (
            <article className="setup-step panel" key={step.number}>
              <span className="setup-number">{step.number}</span>
              <div>
                <h2>{step.title}</h2>
                <p>{step.description}</p>
                {step.value && <div className="copy-field"><code>{step.value}</code><CopyButton label={step.copyLabel || "Copy"} value={step.value} /></div>}
                {step.number === "04" && <a className="inline-link" href="https://www.overleaf.com/project" target="_blank" rel="noreferrer">Open Overleaf <Icon name="external" size={14} /></a>}
              </div>
            </article>
          ))}
        </div>

        <aside className="setup-aside">
          <section className="panel setup-note">
            <span className="note-icon"><Icon name="shield" size={20} /></span>
            <h2>What the extension reads</h2>
            <p>ClaimTrace scans visible Overleaf editor content for BibTeX entries. Detected metadata is stored in Chrome extension storage for the local paper library.</p>
          </section>
          <section className="panel setup-note">
            <span className="note-icon amber"><Icon name="document" size={20} /></span>
            <h2>Seeing demo papers?</h2>
            <p>The four example papers appear until ClaimTrace can read a real bibliography. Select the <code>.bib</code> file and press Sync in the Side Panel.</p>
          </section>
          <section className="panel setup-note compact-note">
            <h2>After changing extension code</h2>
            <p>Return to <code>chrome://extensions</code> and press the reload icon on the ClaimTrace card.</p>
          </section>
        </aside>
      </section>

      <section className="setup-complete">
        <span><Icon name="check" size={20} /></span>
        <div><h2>Extension installed?</h2><p>Open the demo paper library or return to Overleaf and try the complete workflow.</p></div>
        <Link className="button button-light" to="/library">View paper library <Icon name="arrow" size={15} /></Link>
      </section>
    </div>
  );
}
