import { useRef, useState } from "react";
import { setAISettings, useAISettings } from "../data/aiSettings";
import type { AIConfig } from "../types/api";

export function AISettings() {
  const settings = useAISettings();
  const dialog = useRef<HTMLDialogElement>(null);
  const [provider, setProvider] = useState<AIConfig["provider"]>("openai");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [auditEnabled, setAuditEnabled] = useState(false);
  return <>
    <button className="button button-secondary" type="button" onClick={() => {
      setProvider(settings.config?.provider || "openai"); setModel(settings.config?.model || "");
      setKey(settings.config?.api_key || ""); setAuditEnabled(settings.auditEnabled); dialog.current?.showModal();
    }}>AI settings{settings.config ? " · Configured" : ""}</button>
    <dialog ref={dialog} className="direct-upload-dialog ai-settings-dialog" aria-label="AI settings" onClose={() => setKey("")}>
      <form onSubmit={(event) => {
        event.preventDefault();
        if (!model.trim() || !key.trim()) return;
        setAISettings({ provider, model: model.trim(), api_key: key.trim() }, auditEnabled);
        dialog.current?.close(); setKey("");
      }}>
        <h2 id="ai-settings-title">AI settings</h2>
        <p>Required for Verify. Use a model your account supports with chat completions and JSON responses.</p>
        <label className="field"><span>Provider</span><select aria-label="Provider" value={provider} onChange={(event) => { setProvider(event.target.value as AIConfig["provider"]); setModel(""); setKey(""); }}><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option></select></label>
        <label className="field"><span>Model</span><input aria-label="Model" required value={model} onChange={(event) => setModel(event.target.value)} placeholder="Enter a model ID" autoComplete="off" /></label>
        <label className="field"><span>API key</span><input aria-label="API key" required type="password" value={key} onChange={(event) => setKey(event.target.value)} autoComplete="off" spellCheck={false} /></label>
        <label className="ai-audit-option"><input type="checkbox" checked={auditEnabled} onChange={(event) => setAuditEnabled(event.target.checked)} /> Use AI for incomplete Audit references</label>
        <p className="ai-settings-note">Your key stays in memory until you refresh or clear it. It is sent to the backend only for Verify and enabled Audit requests. Provider usage may incur charges.</p>
        <footer className="upload-dialog-footer">
          <button className="button button-secondary" type="button" onClick={() => { setAISettings(null); setKey(""); setModel(""); setAuditEnabled(false); dialog.current?.close(); }}>Clear configuration</button>
          <button className="button button-secondary" type="button" onClick={() => dialog.current?.close()}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={!model.trim() || !key.trim()}>Save configuration</button>
        </footer>
      </form>
    </dialog>
  </>;
}
