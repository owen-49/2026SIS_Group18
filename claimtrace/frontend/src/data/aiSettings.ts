import { useSyncExternalStore } from "react";
import type { AIConfig } from "../types/api";

// Deliberately memory-only: never persist credentials to browser storage.
let settings: { config: AIConfig | null } = { config: null };
const listeners = new Set<() => void>();
export const getAISettings = () => settings;
export function setAISettings(config: AIConfig | null) {
  settings = { config: config ? { ...config } : null };
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
