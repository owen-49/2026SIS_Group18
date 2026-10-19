export const aiProviders = [
  {
    id: "openai",
    docsUrl: "https://developers.openai.com/api/docs/models",
    label: "OpenAI",
    regions: ["global"],
  },
  {
    id: "deepseek",
    docsUrl: "https://api-docs.deepseek.com/quick_start/pricing",
    label: "DeepSeek",
    regions: ["global"],
  },
  {
    id: "anthropic",
    docsUrl: "https://platform.claude.com/docs/en/about-claude/models/overview",
    label: "Anthropic Claude",
    regions: ["global"],
  },
  {
    id: "gemini",
    docsUrl: "https://ai.google.dev/gemini-api/docs/models",
    label: "Google Gemini",
    regions: ["global"],
  },
  {
    id: "xai",
    docsUrl: "https://docs.x.ai/developers/models",
    label: "xAI",
    regions: ["global"],
  },
  {
    id: "mistral",
    docsUrl: "https://docs.mistral.ai/models",
    label: "Mistral",
    regions: ["global"],
  },
  {
    id: "cohere",
    docsUrl: "https://docs.cohere.com/docs/models",
    label: "Cohere",
    regions: ["global"],
  },
  {
    id: "qwen",
    docsUrl: "https://www.alibabacloud.com/help/en/model-studio/models",
    label: "Alibaba Cloud Qwen",
    regions: ["china", "singapore", "us"],
  },
  {
    id: "moonshot",
    docsUrl: "https://platform.kimi.ai/docs/models",
    label: "Moonshot Kimi",
    regions: ["global", "china"],
  },
  {
    id: "zhipu",
    docsUrl: "https://docs.bigmodel.cn/cn/guide/models/text",
    label: "Zhipu GLM",
    regions: ["china"],
  },
  {
    id: "minimax",
    docsUrl:
      "https://platform.minimax.io/docs/api-reference/models/openai/list-models",
    label: "MiniMax",
    regions: ["global", "china"],
  },
  {
    id: "doubao",
    docsUrl: "https://docs.volcengine.com/docs/ark/model-list?lang=zh",
    label: "Volcengine Doubao",
    regions: ["china"],
  },
  {
    id: "groq",
    docsUrl: "https://console.groq.com/docs/models",
    label: "Groq",
    regions: ["global"],
  },
  {
    id: "together",
    docsUrl: "https://docs.together.ai/docs/serverless-models",
    label: "Together AI",
    regions: ["global"],
  },
  {
    id: "fireworks",
    docsUrl: "https://docs.fireworks.ai/getting-started/models",
    label: "Fireworks AI",
    regions: ["global"],
  },
  {
    id: "siliconflow",
    docsUrl:
      "https://docs.siliconflow.com/en/api-reference/models/get-model-list",
    label: "SiliconFlow",
    regions: ["china", "global"],
  },
  {
    id: "openrouter",
    docsUrl: "https://openrouter.ai/models",
    label: "OpenRouter",
    regions: ["global"],
  },
] as const;
export type AIProvider = (typeof aiProviders)[number]["id"];
