# PR #60 frontend acceptance

Reviewed head: efff4300f78f4841c4bdd454ed73d2cb4197fea0.

All 17 providers can be saved; Audit checkbox is removed. Provider/region changes clear draft credentials, reload clears saved configuration, and keys stay out of browser storage. Audit submits PDF/BibTeX IDs, omits AI configuration when absent, and automatically attaches saved configuration. Verify requires configuration and handles provider errors with retry.

Two reproduced frontend defects are fixed:
- Qwen workspace pattern was invalid in Chrome. The corrected pattern rejects dotted labels, leading/trailing hyphens and excessive length, and accepts a valid hyphenated label.
- Sanitized backend validation errors have a code but no message. Preserve INVALID_REQUEST and show a safe hint to check the request and AI settings instead of only Request failed (422).

Original tests: 43 passed. Both new regressions failed before fixes. After fixes: 45 Chrome tests passed; lint, production build and git diff --check passed.

Browser tests used intercepted API responses. No live paid provider calls or live backend end-to-end verification was performed. Formal review remains with Siyuan. Frontend fixes and AI settings refinements are included on backend/ai-provider-expansion, the source branch of PR #60.

Suggested reply:

Thanks! I checked the settings UI and Audit flow in PR #60. The provider options and automatic AI configuration work in the frontend tests. I found and fixed two frontend issues locally: Qwen workspace validation in Chrome and the display of sanitized validation errors. All 45 browser tests, lint, and build now pass. These checks used mocked API responses; live provider testing is still pending. Siyuan can continue with the formal review.

## AI settings follow-up

Save configuration stays enabled and validates on submission, with field-specific feedback and focus on the first invalid input. Read actual form input values to support browser autofill without React change events. Selecting the same provider/region preserves the draft; switching to a different one still clears credentials. Added Show/Hide key, a close button, a purple/graphite modal header, gentle motion with reduced-motion support, and a sticky footer for narrow windows. Verify page layout is unchanged.

Validation: 47 mocked Chrome integration tests pass, lint and build pass, desktop and 390px browser visuals checked, and the mobile Save button remains within the viewport. Live provider calls remain untested.
