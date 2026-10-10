import { useRef, useState } from "react";
import { setAISettings, useAISettings } from "../data/aiSettings";
import { aiProviders } from "../data/aiProviders";
import type { AIConfig } from "../types/api";

export function AISettings() {
  const settings = useAISettings();
  const dialog = useRef<HTMLDialogElement>(null);
  const [provider, setProvider] = useState<AIConfig["provider"]>("openai");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [region, setRegion] = useState("global");
  const [workspace, setWorkspace] = useState("");
  const regions = aiProviders.find((item) => item.id === provider)!.regions;
  return (
    <>
      <button
        className="button button-secondary"
        type="button"
        onClick={() => {
          setProvider(settings.config?.provider || "openai");
          setModel(settings.config?.model || "");
          setKey(settings.config?.api_key || "");
          setRegion(
            settings.config?.region ||
              aiProviders.find(
                (item) => item.id === (settings.config?.provider || "openai"),
              )!.regions[0],
          );
          setWorkspace(settings.config?.workspace || "");
          dialog.current?.showModal();
        }}
      >
        AI settings{settings.config ? " · Configured" : ""}
      </button>
      <dialog
        ref={dialog}
        className="direct-upload-dialog ai-settings-dialog"
        aria-label="AI settings"
        onClose={() => setKey("")}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!model.trim() || !key.trim()) return;
            setAISettings({
              provider,
              model: model.trim(),
              api_key: key.trim(),
              ...(region !==
              aiProviders.find((item) => item.id === provider)!.regions[0]
                ? { region }
                : {}),
              ...(provider === "qwen" && region !== "us" && workspace.trim()
                ? { workspace: workspace.trim() }
                : {}),
            });
            dialog.current?.close();
            setKey("");
          }}
        >
          <h2 id="ai-settings-title">AI settings</h2>
          <p>
            Required for Verify. Also used automatically to extract missing
            reference metadata for Audit. Choose a text model that can return
            JSON.
          </p>
          <label className="field">
            <span>Provider</span>
            <select
              aria-label="Provider"
              value={provider}
              onChange={(event) => {
                setProvider(event.target.value as AIConfig["provider"]);
                setModel("");
                setKey("");
                setWorkspace("");
                setRegion(
                  aiProviders.find((item) => item.id === event.target.value)!
                    .regions[0],
                );
              }}
            >
              {aiProviders.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Model</span>
            <input
              aria-label="Model"
              required
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="Enter a model ID"
              autoComplete="off"
            />
          </label>
          <label className="field">
            <span>API key</span>
            <input
              aria-label="API key"
              required
              type="password"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          {regions.length > 1 && (
            <label className="field">
              <span>API region</span>
              <select
                aria-label="API region"
                value={region}
                onChange={(event) => {
                  setRegion(event.target.value);
                  setKey("");
                  setWorkspace("");
                }}
              >
                {regions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          )}
          <p className="ai-settings-note">
            Use an API key for the selected region: {region}. Model availability
            depends on your account.
          </p>
          {provider === "qwen" && region !== "us" && (
            <label className="field">
              <span>Qwen workspace ID (optional)</span>
              <input
                aria-label="Qwen workspace ID"
                value={workspace}
                onChange={(event) => setWorkspace(event.target.value)}
                pattern="[a-zA-Z0-9](?:(?:[a-zA-Z0-9]|-){0,61}[a-zA-Z0-9])?"
                autoComplete="off"
              />
            </label>
          )}
          <p className="ai-settings-note">
            Your key stays in memory until you refresh or clear it. It is sent
            to the backend only for Verify and Audit requests. Provider usage
            may incur charges.
          </p>
          <footer className="upload-dialog-footer">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => {
                setAISettings(null);
                setKey("");
                setModel("");
                setWorkspace("");
                dialog.current?.close();
              }}
            >
              Clear configuration
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="button button-primary"
              type="submit"
              disabled={!model.trim() || !key.trim()}
            >
              Save configuration
            </button>
          </footer>
        </form>
      </dialog>
    </>
  );
}
