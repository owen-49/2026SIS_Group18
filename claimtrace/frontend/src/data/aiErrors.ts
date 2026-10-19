export const aiErrors: Record<string, { message: string; field?: string }> = {
  AI_CONFIG_REQUIRED: {
    message: "Add your provider, model and API key in AI settings to continue.",
  },
  AI_CONFIG_INVALID: {
    message: "Check your provider, region and API key in AI settings.",
  },
  AI_AUTH_FAILED: {
    field: "api_key",
    message:
      "Your API key was rejected. Copy a valid key from this provider's console.",
  },
  AI_MODEL_UNAVAILABLE: {
    field: "model",
    message:
      "This model is unavailable. Load models or copy an accessible model ID from your provider's console.",
  },
  AI_MODEL_INCOMPATIBLE: {
    field: "model",
    message:
      "This model does not support the JSON output ClaimTrace needs. Choose another text chat model.",
  },
  AI_REQUEST_REJECTED: {
    field: "model",
    message:
      "The provider rejected the request. Check the model ID or choose a model that supports this request.",
  },
  AI_QUOTA_EXCEEDED: {
    message:
      "Your AI balance or quota is exhausted. Check billing in your provider's console.",
  },
  AI_RATE_LIMITED: {
    message:
      "Your provider is receiving too many requests. Wait a moment and try again.",
  },
  AI_TIMEOUT: {
    message:
      "Your provider did not respond within 30 seconds. Try again or choose another model.",
  },
  AI_ACCESS_DENIED: {
    message:
      "Your account cannot access this resource. Check the region and model permissions.",
  },
  AI_PROVIDER_FAILED: {
    message:
      "Your provider could not complete the request. Try again or check its service status.",
  },
};
export function describeAIError(message: string) {
  const code = message.match(/\bAI_[A-Z_]+\b/)?.[0];
  return code && aiErrors[code] ? { code, ...aiErrors[code] } : null;
}
