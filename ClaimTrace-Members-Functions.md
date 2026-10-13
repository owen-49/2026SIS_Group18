# ClaimTrace — Members' Functions and Tasks

**Group 18 · 41129 Software Innovation Studio · UTS · 13 October 2026**

Seven people in four working groups. Ownership maps to **directories, not layers**: each group owns
one part of the repository and the contracts that connect them.

| Group | Members | Owns |
| --- | --- | --- |
| Backend | Hongyang Chen, Siyuan Sun | `claimtrace/backend/` |
| Frontend | Jun Li, Sam | `claimtrace/frontend/`, `claimtrace/extension/` |
| Parser | Yi Jiang, Zheng Fu | `claimtrace/parser/` |
| Engine | Sichen Liu (solo) | `claimtrace/engine/` |

---

| Your name | Key Functions/Tasks | Notes: |
| --- | --- | --- |
| **Hongyang Chen** | **Backend.** The Audit path end to end: connecting the parser's PDF reference metadata to the persisted bibliography audit, wiring the reference lookup into the audit flow, separating the bibliography audit from claim verification, and resolving Verify citations in both manuscript and bibliography context. Added isolated manual source-PDF selection for Verify. Delivered the user-provided AI credential work (Audit and Verify use the researcher's own key) and the expansion to 17 providers with Audit extraction enabled by default. Hardened local source metadata matching; fixed parser metadata extraction and the parser/extension integration. | GitHub `chy1145141919810`. Backend side of `docs/audit-contract.md`. Reviews and merges most backend integration pull requests. |
| **Siyuan Sun** | **Backend.** The upload, parse and library path: BibTeX parsing and verification integration, the uploaded-paper deletion API (made recoverable and safe under concurrent requests), fresh-storage startup and paper-listing fixes, and the venue-abbreviation measurement over the handoff corpus. Prepared and rehearsed the production deployment. Built the Verify acceptance harness's call budgeting and output caps, ran the DeepSeek thinking-mode comparison, and completed the first successful live paid-provider acceptance run. | GitHub `Archieee-coderr`. Owns the deployment rehearsal (`backend/deploy/`) and the written acceptance records `docs/verify-acceptance*.md`. |
| **Jun Li** | **Frontend.** The web dashboard: the Batch audit and claim-review workspace, paper management and selection-based claim review, the paper library with PDF and Bib upload, and source-PDF handling. Built the AI settings for Audit and Verify (the 17-provider configuration UI) with explicit validation errors. Implemented the citation Verify status contract in the interface — only a completed comparison renders a verdict. Fixed parse-error and cached-paper warnings, labels and interface polish. | GitHub `Li-Jun-Li0577`. Wrote the frontend acceptance record for the provider-expansion pull request. |
| **Sam** | **Frontend.** The Chrome extension: carrying the audit workflow alongside Verify, extension source matching with a manual candidate-review path, citation claim extraction from the editor and bibliography metadata, and citation-to-PDF matching with backend verification. Kept Verify sync independent of Audit through the extension's migration, including the intermediate audit-only step and the revert that restored both workflows. Fixed the development compose build and mount paths. | GitHub `Sam20051512`. The repository records this handle as the second Frontend member; an earlier handoff document had used a different name. |
| **Yi Jiang** | **Parser.** The PDF-to-Markdown converter that produces readable source text from uploaded papers, including de-duplicating repeated image references in its output. | GitHub `johnnyjiangyi01-code`. |
| **Zheng Fu** | **Parser.** The reference pipeline: robust PDF reference extraction to JSON (the reference list the Audit consumes), cited-sentence extraction and citation-marker location (bracketed numeric style), APA 7th citation-sentence support, matching citations to their references and adjusting the JSON fields, reference metadata parsing, and the reference-metadata LLM integration with its retry-on-model-error fix. Refactored the parser directory to align with the main branch. | GitHub `Fzddx`. |
| **Sichen Liu** | **Engine (solo).** The identity rule that decides whether a candidate record is the same work; the OpenAlex and Crossref metadata providers and the provider chain that replaced the earlier Scholar lookup; reference-text parsing into structured fields; the Verify path (retrieval and entailment, the claim-passage harness, the annotation target, and scoring against the pre-committed bars); the arXiv-identifier year defect fix; the hover card's source-passage display. Cross-group contracts and documentation (team structure, acceptance records), the market analysis, and the accuracy and timing benchmark design for Batch audit and Verify, including the 103-pair annotation worksheet. | GitHub `owen-49` (git `SichenLiu`). Team leader and A1 pitch presenter. Owns `claimtrace/engine/` and the engine-side contracts. |

---

The task descriptions above are derived from the repository's own record: the group and directory
ownership table in `claimtrace/docs/team.md`, and the commit history and pull requests under each
member's git identity.
