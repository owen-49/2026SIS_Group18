# PR #60 frontend acceptance

Reviewed head: efff4300f78f4841c4bdd454ed73d2cb4197fea0.

All 17 providers can be saved; Audit checkbox is removed. Provider/region changes clear draft credentials, reload clears saved configuration, and keys stay out of browser storage. Audit submits PDF/BibTeX IDs, omits AI configuration when absent, and automatically attaches saved configuration. Verify requires configuration and handles provider errors with retry.

Two reproduced frontend defects are fixed:
- Qwen workspace pattern was invalid in Chrome. The corrected pattern rejects dotted labels, leading/trailing hyphens and excessive length, and accepts a valid hyphenated label.
- Sanitized backend validation errors have a code but no message. Preserve INVALID_REQUEST and show a safe hint to check the request and AI settings instead of only Request failed (422).

Original tests: 43 passed. Both new regressions failed before fixes. After fixes: 45 Chrome tests passed; lint, production build and git diff --check passed.

Browser tests used intercepted API responses. No live paid provider calls or live backend end-to-end verification was performed. Formal review remains with Siyuan. Fixes are committed locally on codex/pr60-frontend-acceptance and are not yet pushed to PR #60.

Suggested reply:

Thanks! I checked the settings UI and Audit flow in PR #60. The provider options and automatic AI configuration work in the frontend tests. I found and fixed two frontend issues locally: Qwen workspace validation in Chrome and the display of sanitized validation errors. All 45 browser tests, lint, and build now pass. These checks used mocked API responses; live provider testing is still pending. Siyuan can continue with the formal review.
