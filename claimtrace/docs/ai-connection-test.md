# User AI connection checks

Configuration stays in browser memory. Neither model discovery nor a connection
check stores credentials, provider output, or connection results on the server.
A successful check verifies credentials, model access and the JSON completion
contract at that moment; it cannot guarantee future availability or quota.

`POST /api/ai/models` accepts provider, optional region/workspace, and api_key.
It uses the existing official endpoint preset and returns sorted, deduplicated
model IDs, at most 500 from the first response. It does not follow pagination
URLs. Obvious embedding, speech, image generation, moderation and reranking IDs
are excluded; vision chat IDs remain candidates. Discovery is guidance, not a
promise that every candidate supports JSON output.

`POST /api/ai/test` accepts UserAIConfig and uses user_ai_session and
UserAIRuntime.create, including the same preparation and normalization as
Verify. It requests JSON mode and validates a completed `{ "ok": true }` object
locally. No artificial small token cap is used. Native Anthropic retains the
adapter's 4096 token budget. Requests time out after 30 seconds without SDK
retries. The response contains only ok, the requested model, and latency_ms.

Save configuration tests before saving. Test connection tests only the draft.
Save without testing saves with an amber indicator; tested saves use green.
Editing configuration invalidates the test, and stale responses cannot save a
previous draft. Both Verify and Audit use the same error descriptions and can
open the settings dialog directly.

## Provider discovery documentation

Documentation reviewed on 2026-10-19. These are documentation findings, not live
credential tests. All automated provider requests use offline transports.
“Not confirmed” means the public documentation does not establish support at
ClaimTrace's existing compatible base URL. Discovery still attempts the official
preset; HTTP 404/405 or an unsupported protocol returns supported=false, with a
manual ID hint. Native or management endpoints are never substituted silently.

| Provider | Models endpoint at the configured protocol | Official source |
| --- | --- | --- |
| OpenAI | Documented GET /v1/models | [List models](https://developers.openai.com/api/reference/python/resources/models/methods/list) |
| DeepSeek | Documented GET /models | [List models](https://api-docs.deepseek.com/api/list-models/) |
| Anthropic | Documented native GET /v1/models | [List models](https://platform.claude.com/docs/en/api/models/list) |
| Gemini | Documented compatible models.list | [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai#list-models) |
| xAI | Documented GET /v1/models | [Models](https://docs.x.ai/developers/rest-api-reference/inference/models) |
| Mistral | Documented GET /v1/models | [Models API](https://docs.mistral.ai/api/endpoint/models) |
| Cohere | Compatible path not confirmed; native list API exists | [Compatibility API](https://docs.cohere.com/docs/compatibility-api), [native list](https://docs.cohere.com/v2/reference/list-models) |
| Qwen | Compatible path not confirmed; documented list uses /api/v1/models | [List models](https://help.aliyun.com/zh/model-studio/list-models) |
| Moonshot Kimi | Documented GET /v1/models | [List models](https://platform.kimi.ai/docs/api/list-models) |
| Zhipu | Compatible list path not confirmed | [Model documentation](https://docs.bigmodel.cn/cn/guide/models/text) |
| MiniMax | Documented compatible GET /v1/models | [List models](https://platform.minimax.io/docs/api-reference/models/openai/list-models) |
| Doubao | Compatible list path not confirmed | [Model catalog](https://docs.volcengine.com/docs/ark/model-list?lang=zh) |
| Groq | Documented GET /openai/v1/models | [Supported models](https://console.groq.com/docs/models) |
| Together | Documented GET /v1/models | [List models](https://docs.together.ai/reference/models) |
| Fireworks | Inference list path not confirmed; management list uses /v1/accounts/{account_id}/models | [Management list](https://docs.fireworks.ai/api-reference/list-models) |
| SiliconFlow | Documented GET /v1/models | [List models](https://docs.siliconflow.com/en/api-reference/models/get-model-list) |
| OpenRouter | Documented GET /api/v1/models | [List models](https://openrouter.ai/docs/api/api-reference/models/get-models) |

No example model IDs are hardcoded in the UI. Each provider has a Find model IDs
link to its official catalog or listing documentation. Available models and
regional access change; users can load IDs or copy them from their console.

## Safe errors

Only HTTP status and structured error code/type fields affect classification.
Provider message strings are never inspected or forwarded. Structured model
codes such as model_not_found, ModelNotFound and model_not_supported identify
unavailable models. Other HTTP 400 responses become AI_REQUEST_REJECTED, with
advice to check the ID or request capabilities. Existing completion failures in
Verify/Audit retain their error contract; the connection check translates
incomplete output and invalid JSON to AI_MODEL_INCOMPATIBLE.

DeepSeek's [error documentation](https://api-docs.deepseek.com/quick_start/error_codes/)
defines HTTP 400 for invalid format and 422 for invalid parameters, but does not
promise a structured model-not-found code. Its generic 400 therefore receives
AI_REQUEST_REJECTED instead of parsing message text. Qwen documents
[ModelNotFound/model_not_found and model_not_supported](https://help.aliyun.com/en/model-studio/error-code).

## Validation

Using E:\envs\claimtrace-dt, with caches and temporary files on E:, the full
backend suite passes: 661 tests, including 89 new connection tests. Existing
backend assertions were retained. Backend ruff check passes. Frontend build
(TypeScript plus Vite) and lint pass.

The complete Edge Playwright suite reports 75 passed and 3 failed. All 20 new
browser cases pass. The same three failures reproduce on an unmodified archive
of main at 4f5a011, using the same dependencies and browser:

| Existing demo test | Failure |
| --- | --- |
| citations throughout the complete Rich paper respond to pointer clicks | No data-citation-group elements |
| SQuAD and ELMo selections use their own source passages and clear stale results | No matching Rajpurkar citation link; click times out |
| a grouped author-year citation requires a source choice and missing source text stays unjudged | No matching grouped ELMo citation link; click times out |

The baseline archive and its test results are in
E:\cache\tmp\claimtrace-ai-baseline-20261019. Existing FastAPI startup/shutdown
deprecation warnings and the Vite chunk size advisory remain.

## Changed files

Paths below are relative to claimtrace/.

| File | Change |
| --- | --- |
| backend/src/main.py | Mount the user AI discovery and test router. |
| backend/src/routes/ai.py | Add safe model discovery and a JSON connection check through the Verify runtime. |
| backend/src/user_ai.py | Share destination/key validation with the model-less discovery request and register new error statuses. |
| backend/src/services/ai_providers.py | Add native Anthropic model discovery and typed completion compatibility failures. |
| backend/src/services/user_ai_runtime.py | Classify structured model errors and rejected requests; track incompatible completions without changing existing Verify failure codes. |
| backend/tests/test_user_ai_connection.py | Add offline endpoint, protocol, timeout, validation, filtering and secret handling regressions. |
| frontend/src/api/client.ts | Add model discovery and connection test requests. |
| frontend/src/components/AISettings.tsx | Add editable model candidates, discovery, testing, tested saves and explicit bypass. |
| frontend/src/components/AISettings.css | Style connection state, hints and wrapping action buttons. |
| frontend/src/components/AIErrorMessage.tsx | Share actionable error rendering and direct settings access. |
| frontend/src/data/aiErrors.ts | Map stable AI error codes to English explanations and fields. |
| frontend/src/data/aiProviders.ts | Add official model documentation links for all providers. |
| frontend/src/data/aiSettings.ts | Keep tested state in memory and expose the settings dialog action. |
| frontend/src/pages/VerifyPage.tsx | Use shared AI error explanations and settings access. |
| frontend/src/pages/AuditPage.tsx | Use the same shared error presentation. |
| frontend/tests/ai-helpers.mjs | Mock connection checks when existing tests configure AI. |
| frontend/tests/ai-providers.spec.mjs | Adapt existing settings coverage to tested saving. |
| frontend/tests/ai-connection.spec.mjs | Cover model discovery, field errors, stale responses, memory state and invalidation. |
| frontend/tests/verify-citation.spec.mjs | Cover new model errors and opening settings from Verify and Audit. |
| docs/ai-connection-test.md | Record protocol findings, official sources, behavior and validation results. |
