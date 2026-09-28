# ClaimTrace — Market Deck 逐页讲稿

> 对应 `ClaimTrace-Market-Competitor-Analysis.pptx`（7 页）
> 目标时长：**约 9–11 分钟**（英文台词 1,243 词，正常语速 9 分钟左右，加停顿和演示约 11 分钟）
> 每页标注了分页时长，时间紧张就砍 Slide 4/5 的细节段
> 体例同 `ClaimTrace-Pitch-Script-and-QA.md`：中文提示 + 英文可直接照读

**开场前提醒：** 这套 deck 的数字和 A1 讲稿**不完全一样**——A1 里 12,402/7.1%、371M→617M、GhostCite 76.7%、20.9M 这几个数字经核查站不住，已替换。文末有一节列出必须改口的地方，**上台前务必看那一段**。

---

## Slide 1 — 封面（20 秒）

**建议主讲：** Sichen（组长）

> "Good morning. We're Group 18, and this is our market and competitor analysis for **ClaimTrace** — a citation audit tool for academic writing.
>
> One thing about method before we start, because it shapes every slide: **we re-checked every number in this deck.** Where we couldn't trace a figure to a source, we took it out. That includes numbers from our own earlier pitch. What's left is what we can defend."

**提示：** 最后一句是关键——它把「换数字」这件事变成了方法论上的加分项，而不是被抓包。说完停半秒再翻页。

---

## Slide 2 — The targeted market（3 分钟，全 deck 的核心）

**建议主讲：** Hongyang（市场部分）+ Sichen（gap 部分）

### ① 市场是什么

> "Our market is academic writing. Overleaf alone reports **twenty million users**, and **five point seven million papers** were published in 2024 — up from three point nine million in 2019. That's **forty-six percent growth in five years.**
>
> Every claim in every one of those papers cites a source."

### ② 问题有多大

> "And here's what that costs. The best estimate we have pools **forty-six studies and about thirty-two thousand quotations.**
>
> **Sixteen point nine percent** of quotations are wrong. **Eight percent** are major errors — meaning the source says something different from what the author claimed.
>
> And the trend line is flat. **No improvement in forty years.**"

**提示：** "Sixteen point nine" 和 "No improvement in forty years" 要放慢、重读。这是全场最有力的一个数字。

### ③ 谁在拦

> "Reviewers don't catch it. One experiment found they missed **two-thirds of major errors.** Another found reviewers caught **three out of nine** deliberately planted errors.
>
> And a **BMJ** analysis in 2023 said responsibility for auditing citations *'rests with those who selected it, not reviewers'* — and proposed **AI tools at submission** to do exactly this.
>
> That's our product thesis. Published in a medical journal."

### ④ 市场多大，缺口在哪

> "Now the market size — and I want to be careful here, because this is where the easy answer is wrong.
>
> The tooling market is small, and **the vendors can't agree on it.** Three commercial estimates, same category, same year: **three hundred seventy-one million, three hundred eighty-five million, and one point one five billion.** That's **three times apart.** The only audited number is Clarivate's — **one point two six six billion**, from their SEC filing.
>
> So we show the spread, and we quote the audited figure. **A number without its scope isn't evidence.**"

> "Four kinds of tool exist today. **Reference managers** format metadata. **Turnitin** checks text overlap — in its own words, *'Turnitin does not check for plagiarism.'* **Reference checkers** confirm a record exists. And **scite** classifies how *other people* cited a paper.
>
> None of them answers our question: **does my source support my sentence?**
>
> ReciteWorks' own FAQ says *'No, not currently.'* And the price list agrees — **a hundred and seventy-five dollars buys metadata checking, a hundred and twenty-five buys similarity.** Neither buys claim support."

**提示：** ④ 是全页落点。"Neither buys claim support" 说完停顿，再翻到 Slide 3。

---

## Slide 3 — 三张图（2.5 分钟）

**建议主讲：** Sichen

**动作：** 按「左下 → 右上 → 右下」的顺序讲，和鼠标走位一致。

### 左下：写作面 vs 付费面

> "Three figures, one argument. Start bottom-left.
>
> **Twenty million people** write in Overleaf. scite — the category leader — had about **twenty-one thousand paying subscribers** when it was acquired. That's roughly **nine hundred and fifty to one.**
>
> Every researcher writes citations. **Almost nobody pays to have them verified.**"

### 右上：市场

> "Top right. The volume of research keeps growing — but the tooling market that serves it is sized **three times apart** by different vendors for the same year.
>
> That disagreement *is* the finding. It's why we name a report and its scope instead of quoting a point estimate."

### 右下：能力矩阵

> "Bottom right is the competitive reality. Thirteen products, four questions.
>
> The first three columns are occupied — somebody does each of them. **The fourth column is the one we care about**, and no established product owns it.
>
> Two honest notes. First, **unoccupied is not empty** — there are prototypes trying it: RefVerifier at seventy-one percent end-to-end, Grounded AI, sci2sci. We're not claiming nobody's trying. We're claiming **no established product owns it.**
>
> Second, the partial marks are deliberate. Paperpal *claims* a relevance check with no independent evaluation. The matrix distinguishes **'documents this'** from **'claims this.'**"

**提示：** 「unoccupied is not empty」这句主动交代弱点，比被 tutor 问出来强得多。

---

## Slide 4 — Case Study: scite.ai（1.5 分钟）

**建议主讲：** Siyuan

> "For the case study we picked scite.ai — the biggest competitor, and the one every reviewer names first.
>
> Why this one? Because it proves the category is real. **A NASDAQ-listed company bought it.** It has **one point six billion Smart Citations**, three hundred million articles indexed, and it publishes its own methods."
>
> "It was acquired by Research Solutions in December 2023. **Be precise about the price:** the initial consideration was about **twenty-one million**, and the earn-out was finalised at **fifteen point four million** in July 2025 — so **roughly twenty-nine million all-in.** The commonly-quoted twenty point nine million is only the first part."
>
> "But here's the thing. **It answers a different question.** scite tells you how *other people* cited a paper. It never tells you whether *your sentence* matches *your source.*
>
> The category is real and funded. It's just pointed somewhere else."

**提示：** 主动纠正 20.9M 这个数字，是**加分动作**——它证明你们核过账，而不是抄了个数。

---

## Slide 5 — Function 1: Smart Citations（1.5 分钟）

**建议主讲：** Yi Jiang

**动作：** 如果有网，现场打开 scite 免费版任一论文页演示 Smart Citations；没网就指着截图讲。

> "Function one: Smart Citations. And we analysed it the way the template asks — empathise, define, ideate.
>
> **Empathise:** a researcher holding an unfamiliar paper asks one question — can I trust this?
> **Define:** for every citation statement, decide whether it supports, contrasts with, or merely mentions the cited work.
> **Ideate:** a fine-tuned SciBERT over thirty-eight thousand labelled citation statements, two years of annotation."
>
> "Now the part I'd want you to look at. **These are their own published numbers.**
>
> Mentioning: ninety-six. Supporting: **fifty-five.** Disputing: **twenty.**
>
> The classes that carry the scientific signal are the rarest, and the hardest to classify. Their own paper also says ingestion *'fails to identify approximately thirty percent of citation statements in PDF files.'*"
>
> "And an **independent peer-reviewed audit** found worse. It took three hundred and twenty-four citations of retracted papers. scite returned **two supporting, ninety-six mentioning, and zero contrasting.** Human assessors found **forty-two supporting, thirty-nine mentioning, and seventeen contrasting.**
>
> **Seventeen contrasting citations that the product showed as none** — in a study of retracted papers, which is exactly where a contrasting signal matters most."
>
> "**Our comment:** the engineering is serious and openly documented. This is the strongest competitor, not a straw man. But the failure mode isn't a wrong label — **it's a label that reads as reassurance.** And aggregate labels about a paper can't answer a question about your sentence. That's a scope limit, not a bug."

**提示：** 如果 tutor 追问「scite 作者反驳了怎么办」——承认：2025 年有 scite 相关作者发过 reply 质疑方法，争议未定，不要说成定论。

---

## Slide 6 — Function 2: Reference Check（1.5 分钟）

**建议主讲：** Zheng Fu

> "Function two is Reference Check — the same corpus, pointed at your own manuscript. Upload a PDF, and for every reference see how it's been cited by others: retractions, editorial notices, contrasting findings.
>
> This is the closest thing in the market to our Audit feature. So let's be fair to it, and then be precise about where it stops."
>
> "**Where it stops:** it looks like it checks your manuscript, but it still reports on third parties. It tells you reference number twelve has been retracted. **It cannot tell you that your sentence about number twelve is wrong** — and to its credit, it doesn't claim to.
>
> Retraction notices are facts about a *record.* They're silent on whether the record supports the claim attached to it."
>
> "ClaimTrace covers the two layers it leaves open.
>
> **Audit — the record.** Does the reference exist, and do title, authors, year and venue agree? OpenAlex first, Crossref as fallback, both keyless.
>
> **Verify — the meaning.** The source passage that supports or contradicts your sentence — **the passage shown, not just a label.**
>
> And the third one is the part that's genuinely ours. **The failure rule.** A failed lookup stays `LOOKUP_FAILED`. `NOT_FOUND` means the search *completed* and found nothing. **We never turn a failed lookup into a verdict.**
>
> No competitor documents that distinction. It matters because the most damaging thing this class of tool can output isn't a wrong answer — **it's a reassuring one.**"

**提示：** 「never turn a failed lookup into a verdict」是本项目唯一的、可被验证的独占设计。**这是全场最该被记住的一句。**

---

## Slide 7 — Thank you（20 秒）

**建议主讲：** Sichen

> "So that's the analysis. The market is real, the leader is funded, and the column we're going after is unoccupied.
>
> We can show you two things live if you'd like — the Overleaf hover flow, and an audit run on a real bibliography.
>
> Thank you — we'd love your questions."

---

## 上台前必看：A1 讲稿里需要改口的数字

`ClaimTrace-Pitch-Script-and-QA.md` 里有几处和这套 deck 冲突。**如果被问到，按右边这列说：**

| 别再说 | 改说 |
|---|---|
| "12,402 papers, 7.1%" | "16.9% of quotations are incorrect, 8% are major — 46 studies, 32,000 quotations" |
| "375 retracted, 76%, 9,662 citations" | 用 "70–94% of retracted papers keep being cited；一篇 Nature Index 研究里是 93.9%" |
| "$371M → $617M, 7.6% CAGR" | "venders 估到 3 倍差距（$371M–$1,150M），能审计的只有 Clarivate 的 $1.266B" |
| "GhostCite 76.7% of reviewers" | 不说。用 BMJ 2023 + 审稿人实验（漏掉 2/3 major errors）代替 |
| "scite acquired for $20.9M" | "≈$29M all-in：$21.1M initial + $15.4M earn-out（2025 年 7 月敲定）" |
| "Overleaf 25M users / 200M documents" | "Overleaf 自己的 about 页写的是 20 million+ users" |

**保留不变：** GPT-4o 19.9% / 45.4%、GPT-3.5 55% / 43% —— 这两个数字站得住，继续用。

**为什么值得主动改口：** 如果 tutor 去查，他会发现 A1 的数字对不上。你们**主动**说明「我们重新核过，换了站得住的来源」，比被指出来的效果好得多。Slide 4 的价格纠正就是故意留的示范。

---

## 三条贯穿全场的原则

1. **每个数字都带出处和年份。** 说 "sixteen point nine percent" 时后面跟一句 "Baethge and Jergas, 2025"。这套 deck 的整个卖点就是**你们比竞品更严谨**——如果自己报数不带来源，这个卖点就塌了。
2. **主动交代弱点。** "unoccupied is not empty"、"scite 作者发过 reply"、"vendors 差三倍"——这些是主动说的，不是被问出来的。主动说 = 可信；被问出来 = 心虚。
3. **回到那一句。** 每个答案最后都落回：**"We never turn a failed lookup into a verdict."**

---

## 分工建议

按现有分组，7 人 7 页，每人一分钟左右，平衡且每个人都有台词：

| Slide | 主讲 | 理由 |
|---|---|---|
| 1 封面 | Sichen | 组长开场 |
| 2 市场 | Hongyang | 后端组，市场数据部分 |
| 3 三张图 | Sichen | 图表是组长做的，讲得最顺 |
| 4 Case Study | Siyuan | 后端组 |
| 5 Function 1 | Yi Jiang | Parser 组 |
| 6 Function 2 | Zheng Fu | Parser 组 |
| 7 收尾 | Sichen | 收尾 + 接 Q&A |

Jun Li 和 Sam（前端组）建议负责 Slide 5/6 的**现场演示**——由他们操作 Overleaf 悬停和审计演示，讲解交给台上的人。这样前端组也有明确任务。

需要我把 `ClaimTrace-Pitch-Script-and-QA.md` 里那 12 个 Q&A 按新数字重写一遍吗？现在 Q1、Q6、Q7、Q11 的答案里都还带着旧数字。
