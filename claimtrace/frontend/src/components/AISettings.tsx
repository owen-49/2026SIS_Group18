import { useRef, useState } from "react";
import { setAISettings, useAISettings } from "../data/aiSettings";
import { aiProviders } from "../data/aiProviders";
import type { AIConfig } from "../types/api";
import { Icon } from "./Icon";
import "./AISettings.css";

const regionLabels: Record<string, string> = { global: "Global", china: "China", singapore: "Singapore", us: "United States" };
const workspacePattern = "[a-zA-Z0-9](?:(?:[a-zA-Z0-9]|-){0,61}[a-zA-Z0-9])?";

export function AISettings() {
  const settings = useAISettings();
  const dialog = useRef<HTMLDialogElement>(null);
  const [provider, setProvider] = useState<AIConfig["provider"]>("openai");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [region, setRegion] = useState("global");
  const [workspace, setWorkspace] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const selectedProvider = aiProviders.find((item) => item.id === provider)!;
  const regions = selectedProvider.regions;
  const hasWorkspace = provider === "qwen" && region !== "us";

  function clearError(field: string) {
    setErrors((current) => { const next = { ...current }; delete next[field]; return next; });
  }

  return <>
    <button className="button button-secondary ai-settings-trigger" type="button" onClick={() => {
      const config = settings.config;
      setProvider(config?.provider || "openai"); setModel(config?.model || ""); setKey(config?.api_key || "");
      setRegion(config?.region || aiProviders.find((item) => item.id === (config?.provider || "openai"))!.regions[0]);
      setWorkspace(config?.workspace || ""); setErrors({}); setShowKey(false);
      dialog.current?.showModal();
    }}><Icon name="spark" size={15} /> AI settings{settings.config && <span className="ai-configured-dot" aria-label="Configured" />}</button>
    <dialog ref={dialog} className="direct-upload-dialog ai-settings-dialog ai-settings-panel" aria-label="AI settings" onClose={() => { setKey(""); setShowKey(false); }}>
      <form noValidate onSubmit={(event) => {
        event.preventDefault();
        // Read actual input values so browser autofill is included even without a React change event.
        const values = new FormData(event.currentTarget);
        const nextModel = String(values.get("model") || "").trim();
        const nextKey = String(values.get("api_key") || "").trim();
        const nextWorkspace = String(values.get("workspace") || "").trim();
        const nextErrors: Record<string, string> = {};
        if (!nextModel) nextErrors.model = "Enter the model ID from your provider account.";
        else if (nextModel.length > 200 || [...nextModel].some((char) => char.charCodeAt(0) < 32)) nextErrors.model = "Use a model ID of up to 200 characters, without control characters.";
        if (!nextKey) nextErrors.api_key = "Enter your API key to save this configuration.";
        else if (nextKey.length > 4096 || (/\s/.test(nextKey) || [...nextKey].some((char) => char.charCodeAt(0) < 32))) nextErrors.api_key = "Your API key cannot contain spaces or line breaks.";
        if (hasWorkspace && nextWorkspace && !new RegExp(`^${workspacePattern}$`).test(nextWorkspace)) nextErrors.workspace = "Use 1–63 letters, numbers or hyphens. Start and end with a letter or number.";
        setErrors(nextErrors);
        if (Object.keys(nextErrors).length) {
          event.currentTarget.querySelector<HTMLInputElement>(`[name="${Object.keys(nextErrors)[0]}"]`)?.focus();
          return;
        }
        setAISettings({ provider, model: nextModel, api_key: nextKey,
          ...(region !== regions[0] ? { region } : {}),
          ...(hasWorkspace && nextWorkspace ? { workspace: nextWorkspace } : {}),
        });
        dialog.current?.close(); setKey("");
      }}>
        <div className="ai-settings-hero">
          <div className="ai-settings-topline"><span className="ai-settings-eyebrow"><Icon name="spark" size={14} /> YOUR AI CONNECTION</span><button className="ai-settings-close" type="button" aria-label="Close AI settings" onClick={() => dialog.current?.close()}><Icon name="x" size={18} /></button></div>
          <h2>AI settings</h2>
          <p>Bring your preferred model to ClaimTrace.</p>
          <div className="ai-usage-chips"><span><Icon name="verify" size={13} /> Verify · required</span><span><Icon name="audit" size={13} /> Audit · automatic</span></div>
        </div>
        <div className="ai-settings-body">
          <div className="ai-provider-row">
            <label className="field"><span>Provider</span><select aria-label="Provider" name="provider" value={provider} onChange={(event) => {
              if (event.target.value === provider) return;
              const next = aiProviders.find((item) => item.id === event.target.value)!;
              setProvider(next.id); setModel(""); setKey(""); setWorkspace(""); setRegion(next.regions[0]); setErrors({}); setShowKey(false);
            }}>{aiProviders.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
            {regions.length > 1 && <label className="field"><span>API region</span><select aria-label="API region" value={region} onChange={(event) => {
              if (event.target.value === region) return;
              setRegion(event.target.value); setKey(""); setWorkspace(""); setErrors({}); setShowKey(false);
            }}>{regions.map((item) => <option key={item} value={item}>{regionLabels[item] || item}</option>)}</select></label>}
          </div>
          <label className="field"><span>Model <small>Required</small></span><input aria-label="Model" name="model" required value={model} onChange={(event) => { setModel(event.target.value); clearError("model"); }} placeholder="Model ID from your provider" autoComplete="off" spellCheck={false} aria-invalid={Boolean(errors.model)} aria-describedby={errors.model ? "ai-model-error" : "ai-model-hint"} />{errors.model ? <span className="ai-field-error" role="alert" id="ai-model-error">{errors.model}</span> : <small id="ai-model-hint">Choose a text model that supports JSON responses.</small>}</label>
          <div className="field"><label htmlFor="ai-api-key">API key <small>Required</small></label><div className="ai-key-input"><input id="ai-api-key" aria-label="API key" name="api_key" required type={showKey ? "text" : "password"} value={key} onChange={(event) => { setKey(event.target.value); clearError("api_key"); }} placeholder="Paste your API key" autoComplete="off" spellCheck={false} aria-invalid={Boolean(errors.api_key)} aria-describedby={errors.api_key ? "ai-key-error" : "ai-key-hint"} /><button type="button" aria-label={showKey ? "Hide API key" : "Show API key"} aria-pressed={showKey} onClick={() => setShowKey(!showKey)}>{showKey ? "Hide" : "Show"}</button></div>{errors.api_key ? <span className="ai-field-error" role="alert" id="ai-key-error">{errors.api_key}</span> : <small id="ai-key-hint">Use a key for {selectedProvider.label} · {regionLabels[region] || region}.</small>}</div>
          {hasWorkspace && <label className="field ai-workspace-field"><span>Qwen workspace ID <small>Optional</small></span><input aria-label="Qwen workspace ID" name="workspace" value={workspace} onChange={(event) => { setWorkspace(event.target.value); clearError("workspace"); }} pattern={workspacePattern} autoComplete="off" placeholder="Workspace ID" aria-invalid={Boolean(errors.workspace)} aria-describedby={errors.workspace ? "ai-workspace-error" : undefined} />{errors.workspace && <span className="ai-field-error" role="alert" id="ai-workspace-error">{errors.workspace}</span>}</label>}
          <div className="ai-privacy-note"><Icon name="shield" size={17} /><p>Your key stays in this session. Refreshing clears it.<br /><span>Used for Verify and Audit. Provider charges may apply.</span></p></div>
        </div>
        <footer className="ai-settings-footer">
          <button className="ai-clear-button" type="button" onClick={() => { setAISettings(null); setKey(""); setModel(""); setWorkspace(""); setErrors({}); dialog.current?.close(); }}>Clear configuration</button>
          <div><button className="button button-secondary" type="button" onClick={() => dialog.current?.close()}>Cancel</button><button className="button button-primary ai-save-button" type="submit">Save configuration <Icon name="arrow" size={15} /></button></div>
        </footer>
      </form>
    </dialog>
  </>;
}
