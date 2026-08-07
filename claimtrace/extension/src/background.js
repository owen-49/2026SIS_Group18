/**
 * ClaimTrace Background Service Worker.
 *
 * Handles extension-level events and API communication.
 * v0.1: Minimal — logs install event.
 */

chrome.runtime.onInstalled.addListener(() => {
  console.log("[ClaimTrace] Extension installed.");
});
