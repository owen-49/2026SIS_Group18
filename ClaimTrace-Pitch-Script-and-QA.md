# ClaimTrace — Pitch Script & Tutor Q&A

> 基于 `Project pitch8.21.pdf`（20 页）  
> 主讲人：Sichen Liu（Team Leader）  
> 目标时长：3.5–4 分钟（A1 要求 3–5 分钟）

---

## Part 1: 演讲 Script（英文，可直接照读）

### 开场 Hook（0:00–0:30）— Slide 3

> "Let me start with a question. When your research team writes a paper, every single claim cites a source. But here's the uncomfortable truth: **nobody actually verifies whether the source says what the claim claims it says.**
>
> Because checking just *one* citation means downloading a PDF, searching for the right passage, and reading it carefully. That's minutes per citation, hours per paper — and honestly, it rarely gets done before submission."

### Problem & Pain Points（0:30–1:15）— Slide 5

> "Why does this matter to us? Because we live it. Three pain points, three seconds each.
>
> **First**, verifying a citation is slow and it breaks your writing flow — you leave Overleaf, search, read, come back, and you've lost your train of thought.
>
> **Second**, you can't trust co-authors' claims. You didn't write them, but *you're* responsible for them when the paper goes out.
>
> **Third**, and this is the scary one — AI tools can fabricate references that look completely real but don't exist."

### Market Evidence（1:15–2:00）— Slide 8

> "And this isn't a hypothetical problem. The data is alarming.
>
> An analysis of 12,402 biomedical papers published in 2025 found that **7.1%** cited at least one retracted, corrected, or questionable paper. Of 375 retracted papers, **76% continued to be cited after retraction** — accumulating 9,662 citations.
>
> When researchers tested GPT-4o, **19.9% of its citations were completely fabricated**, and of the ones that looked real, **45.4% contained errors**.
>
> And critically — a GhostCite survey found that **76.7% of reviewers don't carefully check references**, and 74.5% believe peer review is ineffective at catching citation errors.
>
> So the people whose job it is to catch this… aren't catching it."

### The Gap（2:00–2:40）— Slide 9 & 10

> "So what exists today? Three categories, and a clear gap.
>
> **Zotero** and **Mendeley** manage and format references — they never *verify* anything.
>
> **scite.ai** counts citation context, and they were acquired for 20.9 million dollars — which proves people pay for this problem. But scite doesn't live inside your writing flow.
>
> And **ChatGPT** can *generate* citations — which is precisely the problem we're trying to solve, not a solution.
>
> The gap: **nobody owns the 'hover-to-verify' moment inside the writing workflow.** That's our wedge. Overleaf has 25 million users and 200 million documents — that's a massive surface area with no verification tool on it."

### Solution（2:40–3:30）— Slide 11–14

> "So here's ClaimTrace. It's an academic citation audit tool embedded in Overleaf. You hover any `\cite{...}`, and instantly see the original source passage, aligned against the claim that cites it.
>
> Under the hood, four steps. First, you access it through the Overleaf extension or our web dashboard. Second, the system parses your cited papers and extracts what's needed. Third, we retrieve the relevant evidence passage and check whether the claim is actually supported. Fourth, you get a clear result — a support status, the matching passage, and an explanation.
>
> The web dashboard lets you upload papers, manage your library, verify a single claim, or run a batch audit. The Overleaf extension connects to your bibliography file and identifies cited sources directly inside the editor — so you check evidence without ever leaving your writing."

### Closing（3:30–4:00）— Slide 19

> "So that's ClaimTrace. We don't compete with Zotero on management, scite on counting, or ChatGPT on generation. We own the one moment that matters most — catching a misquoted, over-stated, or hallucinated citation **while you write, not after the reviewers do.**
>
> Thank you. We'd love your questions."

---

## Part 2: Tutor 可能问的问题 & 参考答案

### Q1. "scite.ai 已经在做 citation context 了，你和它有什么不同？"

**（这是最可能被问的问题，务必准备）**

> **Answer:** Great question. scite classifies *how a paper is cited* — supporting, mentioning, or contradicting — at the level of the *cited paper*. We verify *your specific claim* against the *specific source passage*, and we do it *inside Overleaf*.
>
> Concretely: scite tells you "this paper has been cited 40 times, 3 of them contradicting." ClaimTrace tells you "in your manuscript, the sentence you wrote says X, but the source actually says Y." That's a different, more precise job. Plus scite is a standalone research tool — we live in the writing flow, which is where the error happens and where the fix needs to happen.

---

### Q2. "你的工具本身用 LLM 来验证引用，但你自己的 pitch 说 LLM 会编造 19.9% 的引用。你怎么保证自己的工具不幻觉？"

**（这是最尖锐、最可能出现的问题）**

> **Answer:** This is exactly the right question, and it's the core design constraint we've built around.
>
> First, we **don't let the LLM generate any claim from memory.** The LLM's only job is to read *two inputs we give it* — the passage we retrieved from the actual source PDF, and the claim from the manuscript — and judge whether one supports the other. It's a constrained classification task, not generation.
>
> Second, we **always show the source passage alongside the verdict.** The user can see the evidence with their own eyes. We're a lens, not an oracle.
>
> Third, we ground against the PDF itself — if our parser can't extract a passage, we say "not found," we don't guess.
>
> And we measure this. Our riskiest assumption is exactly the entailment accuracy, so our Week-1 spike benchmarks it on a labeled set before we trust it. If it's below our threshold, we fall back to "show the matched passage and let the human decide" — which is still valuable on its own.

---

### Q3. "双栏 PDF、公式、图表这么多，你凭什么觉得能准确解析？技术可行性存疑。"

> **Answer:** Fair concern, and it's our single biggest risk, so we're testing it first, not assuming it.
>
> We deliberately benchmark against the *hard cases*: IEEE double-column, papers dense with formulas, even scanned PDFs. Our spike measures paragraph-level recall on a labeled test set. If double-column reordering or formula regions hurt accuracy below our bar, we have a fallback: many CS papers have their LaTeX source or arXiv HTML available, which is dramatically easier to parse.
>
> The key design decision is that we **don't need perfect parsing** — we need good *paragraph-level* localization. We're not trying to reproduce the PDF, just find the right passage. That's a much lower bar than full document reconstruction.

---

### Q4. "7 个人 12 周，这个 scope 是不是太大了？你的 MVP 到底是什么？"

> **Answer:** Our MVP is deliberately narrow. One core loop: **upload a source paper → hover a citation → see the matched passage and a support verdict.** We're explicitly *not* building real-time multi-user sync, citation-network graphs, or Word/Google Docs support in v1.
>
> We split into three parallel tracks — parser, engine, backend + frontend — so we can ship the loop incrementally. Week 1–3 is spike and validation; by mid-semester the loop runs end-to-end on real PDFs; the final weeks are polish and the demo. The bib-verification feature is a bonus layer on top, not a blocker — if it slips, the core claim-verification still ships.

---

### Q5. "你怎么衡量做得对不对？准确率怎么评估？"

> **Answer:** Two metrics, both measurable.
>
> **Retrieval**: does the passage we return actually contain the ground-truth source sentence? We measure Recall@5 on a labeled set of claim-passage pairs.
>
> **Verification**: is the SUPPORT/PARTIAL/CONTRADICT/NOT_FOUND label correct? We measure against human-annotated ground truth.
>
> We build the benchmark *before* we tune the system, and we track these numbers every sprint. If retrieval can't reliably find the passage, the product is useless regardless of the UI — so that's our go/no-go gate in the first spike.

---

### Q6. "你做过用户调研吗？跟真实研究者聊过吗？"

> **Answer:** We're our own first users — we've all written papers and felt this exact pain, which is why we picked it. But we're not stopping at self-report.
>
> Our plan is to interview 5 PhD students or researchers who recently submitted to a top venue, and to mine Overleaf community forums and Reddit academic threads for the citation-verification complaints. We also plan to actually time how long it takes our team to verify 10 citation claims manually, as a baseline to beat.
>
> The GhostCite data (76.7% of reviewers don't check references) already validates the demand externally — our interviews validate the *workflow* pain specifically.

---

### Q7. "商业模式？scite 被 2090 万收购了，你的 wedge 是什么？"

> **Answer:** Our wedge is the **hover-to-verify moment inside Overleaf** — nobody owns that. The reference-management market is 371 million dollars growing to 617 million, and scite's acquisition proves willingness to pay for citation verification.
>
> Monetization follows the freemium pattern that works in research tools: free for individual researchers, paid for teams and labs who need batch audit and collaboration features. But honestly, for this course our priority is nailing the workflow and proving real usage — the market data shows the opportunity exists, and the wedge is defensible because we're embedded where the work happens.

---

### Q8. "你强依赖 Overleaf 的 DOM 结构。如果他们改版，或者自己做了这个功能呢？"

> **Answer:** Two parts.
>
> **On dependency**: our extension is designed to be thin. The heavy logic lives in our backend, not in DOM scraping. The extension only needs to (1) find the citation key and (2) show a popup. If Overleaf changes their DOM, we update the thin adapter, not the core. And we have a standalone web dashboard as a fallback surface, so we're not a hostage to the extension.
>
> **On Overleaf building it**: that's a real strategic risk, but it's also validation of the problem. Our defensibility is the semantic verification engine and the claim-passage alignment — the hard part — not the popup UI. If anything, we'd be an acquisition target rather than a competitor, the same path scite took.

---

### Q9. "论文常常是未发表的、保密的。数据隐私怎么处理？"

> **Answer:** Privacy-first by default. Papers are processed locally where possible, and we only send the minimal extracted text needed for verification — not the full document — to any model. We don't retain user manuscripts after processing, and we'll be explicit about what gets processed where.
>
> This is actually a selling point for a research tool: researchers won't paste unpublished work into a public ChatGPT, but they'll use a tool that treats their drafts as sensitive.

---

### Q10. "bib 文件验证具体检查什么？和 claim 验证什么关系？"

> **Answer:** It's a second, complementary layer. Claim verification answers "does the source support what you wrote?" Bib verification answers "does your bibliography entry accurately describe the source?" — title, year, authors, venue, DOI.
>
> These are the errors that sneak in from Google Scholar exports and LaTeX mangling: wrong year, garbled title, a DOI pointing to a different paper. Together they cover the two ways a citation can be wrong: the *content* is misrepresented, or the *metadata* is wrong.

---

### Q11. "这个想法不难，为什么之前没人做？"

> **Answer:** The pieces only recently came together. Overleaf becoming the dominant writing platform (25M users) created the single surface to target. Semantic retrieval got good enough to match paraphrased claims — keyword search couldn't, which is why "Ctrl+F" was the state of the art. And LLMs made accurate entailment classification feasible, while *also* making fabricated citations a fast-growing problem — so the demand side exploded at the same moment the technology matured. That convergence is the "why now."

---

### Q12. "如果 ChatGPT 或 Google Scholar 直接加这个功能呢？"

> **Answer:** ChatGPT's incentive is generation, and it's the *source* of the fabricated-citation problem — researchers actively distrust it for verification. Google Scholar is about discovery, not about reading *your* manuscript's claims against sources.
>
> Our whole product is trust and accountability — we show the source passage and the judgment transparently. The big players *could* build it, but it's not their focus, and our narrow, workflow-embedded wedge is how small teams win against platforms.

---

## Part 3: 应对策略速记

| 问题类型 | 应对套路 |
|----------|----------|
| **差异化**（Q1, Q12） | 承认竞品价值 → 划清边界 → 强调「写作流内 hover 时刻」这个独占位置 |
| **自己会幻觉吗**（Q2） | 主动承认风险 → 说明「只分类不生成」+「永远展示原文」→ 用 spike 度量兜底 |
| **技术可行性**（Q3） | 承认是最大风险 → 「先测不假设」→ 给出 fallback（arXiv/HTML 源） |
| **Scope 太大**（Q4） | 收缩到「一个核心循环」→ 明确砍掉什么 → 三线并行保证增量交付 |
| **怎么衡量**（Q5） | 两个指标（Recall@5 + 标注准确率）→ 先建 benchmark 再调系统 |
| **用户调研**（Q6） | 自己是第一批用户 → 5 个访谈 + 论坛挖掘 + 手动计时基线 |
| **商业模式**（Q7） | 用 scite 被收购证明需求 → freemium → 课程内优先验证使用 |
| **依赖/被抄袭**（Q8, Q12） | 承认风险 → 核心在引擎不在 DOM → 被做=验证问题=收购目标 |
| **隐私**（Q9） | 本地处理 + 最小化上传 + 不保留 → 转成卖点 |
| **技术细节**（Q10） | 分层讲清 claim 验证 vs bib 验证两种错误类型 |

**三条黄金原则：**
1. **不辩解，先承认风险**——tutor 挑刺时，说"这是对的顾虑，我们的应对是……"永远比辩解好。
2. **永远能落到「我们的 spike 会测这个」**——把不确定性转成工程问题，而不是手挥愿景。
3. **重复一句核心价值**——"在写作时抓住引用错误，而不是等审稿人"——每个答案最后都回到这句。
