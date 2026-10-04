import { useSyncExternalStore } from "react";
import type { AIConfig } from "../types/api";

// Deliberately memory-only: never persist credentials to browser storage.
let settings: { config: AIConfig | null; auditEnabled: boolean } = { config: null, auditEnabled: false };
const listeners = new Set<() => void>();
export const getAISettings = () => settings;
export function setAISettings(config: AIConfig | null, auditEnabled = false) {
  settings = { config: config ? { ...config } : null, auditEnabled: Boolean(config && auditEnabled) };
  listeners.forEach((listener) => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function useAISettings() { return useSyncExternalStore(subscribe, getAISettings); }
export function requireAIConfig(): AIConfig {
  if (!settings.config) throw new Error("Add your provider, model and API key in AI settings before verifying.");
  return settings.config;
}
