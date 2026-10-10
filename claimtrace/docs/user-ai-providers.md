# User AI providers and default Audit extraction

This change expands user supplied text AI configuration to 17 providers. A provider adapter being implemented and tested offline does not mean every model or account has passed live acceptance.

## API contract

`ai_config` contains `provider`, `model` and `api_key`. Optional `region` selects a finite official endpoint preset. Omitted region uses the first preset below, preserving existing OpenAI and DeepSeek requests. Optional `workspace` is accepted only for Qwen China and Singapore and constructs an official workspace hostname from a validated DNS label. Arbitrary base URLs remain rejected.

| Provider value | Name | Regions, default first |
| :--- | :--- | :--- |
| openai | OpenAI | global |
| deepseek | DeepSeek | global |
| anthropic | Anthropic Claude | global |
| gemini | Google Gemini | global |
| xai | xAI | global |
| mistral | Mistral | global |
| cohere | Cohere | global |
| qwen | Alibaba Cloud Qwen | china, singapore, us |
| moonshot | Moonshot Kimi | global, china |
| zhipu | Zhipu GLM | china |
| minimax | MiniMax | global, china |
| doubao | Volcengine Doubao | china |
| groq | Groq | global |
| together | Together AI | global |
| fireworks | Fireworks AI | global |
| siliconflow | SiliconFlow | china, global |
| openrouter | OpenRouter | global |

Use API credentials for the selected service and region, rather than a consumer chat subscription or coding plan. The model field accepts an account model ID; availability and JSON capability are model dependent. Doubao may use an account inference endpoint ID. Fireworks and aggregation platforms may require fully qualified model IDs. Invalid or unavailable models produce safe errors; no model substitution or billable retry is performed.

For Qwen, a workspace ID selects the newer workspace endpoint; without one, the existing regional DashScope endpoint is used. Keys cannot be moved between regions. The implementation uses the explicit China `cn-beijing` and Singapore `ap-southeast-1` workspace domains described in the migration notes.

## Default Audit behavior

The frontend removes `Use AI for incomplete Audit references` and its `auditEnabled` state. A saved configuration is automatically included in Audit and Verify requests. Missing configuration still allows deterministic bibliography Audit with its existing warnings, and Verify still requires configuration. Complete metadata and successful extraction caches do not trigger repeated extraction.

No implicit team key is used. Keys remain in browser memory and request lifetime; refresh and clear forget them. Changing provider or region clears the draft key. Upload, source management and claim discovery do not receive credentials.

## Protocol boundaries

Most adapters use the existing OpenAI chat client with fixed official endpoints. Claude uses native Messages over HTTP, converts system messages and text results, and rejects incomplete generations. Its OpenAI compatibility layer is not used because it ignores `response_format`.

New providers omit fixed temperature to avoid incompatible reasoning model parameters. Qwen3 requests disable thinking for JSON extraction. MiniMax requests ask for JSON in the prompt without an unsupported `response_format`; a leading complete reasoning block is removed before existing local JSON validation. JSON output is still validated downstream, rather than trusted because a provider promises JSON mode. OpenRouter requires downstream support for requested parameters.

Truncated, filtered or tool based completions are rejected before they can become verdicts. Calls have a 30 second timeout and no automatic retries. Native Claude limits output to 4096 tokens; larger or truncated extraction results fail safely instead of being accepted. Authentication, permissions, quota, rate limit and timeout errors preserve existing safe error codes. Upstream bodies and keys are not returned to callers.

## Scope and review

Azure OpenAI, Amazon Bedrock, Google Vertex AI and Perplexity are outside this change. Engine and Parser source are unchanged. Frontend changes are included with backend changes so the provider list and Audit behavior can be reviewed together.

Siyuan Sun (`Archieee-coderr`) is the sole proposed PR reviewer, as requested by Hongyang. Frontend and extraction coordination can occur without requesting additional formal reviewers. Approval has not been obtained merely by naming a reviewer.

## Validation boundary

Wire tests use the real OpenAI serializer and native Claude HTTP adapter with `httpx.MockTransport`, including all 17 providers, region validation, official destinations, JSON parameter differences and safe failures. Browser tests cover all provider options, automatic Audit configuration, region changes, credential clearing and refresh.

No real provider requests or paid calls are part of these tests. Live account acceptance remains outstanding per provider; offline success must not be reported as real model quality or latency. Existing bibliography replay fixture disagreements are separate and are not silently changed.

## Official references

Checked on 10 October 2026:

* [Claude native and compatibility guidance](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk)
* [Gemini compatibility](https://ai.google.dev/gemini-api/docs/openai)
* [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/)
* [xAI API](https://docs.x.ai/docs/api-reference)
* [Mistral API](https://docs.mistral.ai/api)
* [Cohere compatibility](https://docs.cohere.com/docs/compatibility-api)
* [Qwen endpoints and region migration](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
* [Qwen structured output](https://help.aliyun.com/en/model-studio/qwen-structured-output)
* [Kimi API](https://platform.kimi.ai/docs/overview)
* [Zhipu compatibility](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)
* [MiniMax compatibility](https://platform.minimax.io/docs/api-reference/text-openai-api)
* [Doubao integration](https://docs.volcengine.com/docs/ark/integrate-third-party-tools?lang=zh)
* [Groq compatibility](https://console.groq.com/docs/openai)
* [Together compatibility](https://docs.together.ai/docs/inference/openai-compatibility)
* [Fireworks compatibility](https://docs.fireworks.ai/tools-sdks/openai-compatibility)
* [SiliconFlow quickstart](https://docs.siliconflow.cn/docs/userguide/quickstart)
* [OpenRouter quickstart](https://openrouter.ai/docs/quickstart)
