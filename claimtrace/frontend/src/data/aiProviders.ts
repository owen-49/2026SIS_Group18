export const aiProviders = [
  { id: "openai", label: "OpenAI", regions: ["global"] },
  { id: "deepseek", label: "DeepSeek", regions: ["global"] },
  { id: "anthropic", label: "Anthropic Claude", regions: ["global"] },
  { id: "gemini", label: "Google Gemini", regions: ["global"] },
  { id: "xai", label: "xAI", regions: ["global"] },
  { id: "mistral", label: "Mistral", regions: ["global"] },
  { id: "cohere", label: "Cohere", regions: ["global"] },
  {
    id: "qwen",
    label: "Alibaba Cloud Qwen",
    regions: ["china", "singapore", "us"],
  },
  { id: "moonshot", label: "Moonshot Kimi", regions: ["global", "china"] },
  { id: "zhipu", label: "Zhipu GLM", regions: ["china"] },
  { id: "minimax", label: "MiniMax", regions: ["global", "china"] },
  { id: "doubao", label: "Volcengine Doubao", regions: ["china"] },
  { id: "groq", label: "Groq", regions: ["global"] },
  { id: "together", label: "Together AI", regions: ["global"] },
  { id: "fireworks", label: "Fireworks AI", regions: ["global"] },
  { id: "siliconflow", label: "SiliconFlow", regions: ["china", "global"] },
  { id: "openrouter", label: "OpenRouter", regions: ["global"] },
] as const;
export type AIProvider = (typeof aiProviders)[number]["id"];
