# ClaimTrace — Market Deck 逐页讲稿

> 对应 **`ClaimTrace Market & Competitor Analysis(1).pptx`**（7 页，16:9）
> 目标时长：**8 分钟**（英文台词 1,010 词，140 wpm 约 7 分 12 秒，余下约 45 秒给停顿、翻页和指图）
> 每页标注分页时间，加起来正好 8:00
> 体例同 `ClaimTrace-Pitch-Script-and-QA.md`：中文提示 + 英文可直接照读

**分工（本轮更新）：** 市场部分 = **Hongyang Chen + Siyuan Sun**；Case Study 与 Core Function = **Sichen Liu + Jun Li Li**。封面与收尾由 Sichen 负责。

**开场前提醒：** 这套 deck 的数字和 A1 讲稿**不一样**——A1 里 12,402/7.1%、371M→617M、GhostCite 76.7%、20.9M 这几个数字经核查站不住。新 deck 已全部换成可核查的来源，文末列了必须改口的地方。

**关于这份 deck：** 它和上一版结构完全不同（16:9、卡片式、每页底部自带 Sources 行），所以讲稿是重写的，不是改的。旧版讲稿见 `git log -- ClaimTrace-Market-Deck-Script.md`。

---

## Slide 1 — 封面（25 秒）

**主讲：** Sichen

> "Good morning — Group 18. This is our market and competitor analysis for **ClaimTrace**, a citation audit tool for academic writing.
>
> One note on method, because it shapes every slide: **every number here was re-checked**, and each slide carries its sources along the bottom. Where we couldn't trace a figure, we cut it."

**提示：** 最后一句把「换数字」变成方法论加分项。说完停半秒再翻页。

---

## Slide 2 — The targeted market（2 分钟）

**主讲：** Hongyang

**动作：** 按卡片 1 → 2 → 3 → 4 的顺序讲，鼠标跟着卡片走。

> "Our market is academic writing. Overleaf reports **twenty million users**. **Five point seven million papers** were published in 2024 — **up forty-six percent** from 3.9 million in 2019. Every claim in every one of them cites a source.
>
> And **one in six of those citations is wrong.** **Sixteen point nine percent** of quotations are incorrect; **eight percent** are major — the source says something different from what the author claimed. That pools **forty-six studies and thirty-two thousand quotations**. Baethge and Jergas, 2025. And **no improvement in forty years.**"

**提示：** "Sixteen point nine" 和 "no improvement in forty years" 放慢、重读。这是全场最有力的数字。

> "On size — **the vendors can't agree.** Three commercial estimates, same category, same year: **three hundred seventy-one million to one point one five billion.** That's **three times apart.** The only audited number is Clarivate's — **one point two six six billion**, from their SEC filing.
>
> So we quote a report's scope, or we quote the audited filing. **A number without its scope isn't evidence.**"

> "Four kinds of tool exist. **Reference managers** format metadata. **Turnitin and iThenticate** match text — in Turnitin's own words, *'Turnitin does not check for plagiarism.'* **Reference checkers** confirm a record exists. And **scite** classifies how *other people* cited a paper.
>
> None of them answers our question: **does my source support my sentence?** ReciteWorks' own FAQ says *'No, not currently.'* And the price list agrees — **a hundred seventy-five dollars buys metadata, a hundred twenty-five buys similarity.** Neither buys claim support."

> "And it's getting worse. Fabricated citations grew **twelve-fold** — to about **one in two hundred seventy-seven** papers — and **ninety-eight point four percent** of affected papers saw **no publisher action.**"

**提示：** "Neither buys claim support" 是落点。说完停顿，翻到 Slide 3。

---

## Slide 3 — Empirical Evidence（1 分 20 秒）

**主讲：** Siyuan

**动作：** 左 → 右上 → 右下（表格）。表格不要逐格念。

> "Two pieces of evidence. **Left: the writing surface against the paying surface.** Twenty million people write citations in Overleaf. scite — the category leader — had about **twenty-one thousand paying subscribers** when it was acquired. Roughly **nine hundred and fifty to one.**
>
> Every researcher writes citations. **Almost nobody pays to have them verified.**"

> "**Top right**: the same three-times disagreement, with Clarivate's audited figure alongside.
>
> **Bottom: the capability matrix.** Four tool classes against four questions. The first three questions are all answered by somebody. **The fourth — does the source support my claim — is the column we're aiming at.**"

> "Two honest notes, and I'd rather say them than be asked.
>
> **First: the ClaimTrace row is our own assessment of our own product.** We put ourselves in the table, so read that row as our claim, not as a third-party finding.
>
> **Second: unoccupied is not empty.** RefVerifier, Grounded AI and sci2sci are prototypes trying this. We're not saying nobody's trying — we're saying **no established product owns it.**"

**提示：** 这两句是全 deck 最容易被 tutor 抓住的地方，主动说是加分。**别跳过。**

---

## Slide 4 — Case Study: scite.ai（1 分 15 秒）

**主讲：** Jun Li Li

> "For the case study we picked **scite.ai** — the biggest competitor, and the one every reviewer names first. Four reasons it's the one worth studying.
>
> It has the **only comparable engineering pipeline** — full-text ingestion, a trained classifier, published methods. It **proves the category is paid for**: Research Solutions, NASDAQ-listed, acquired it in December 2023. And it **publishes its own accuracy**, including where it's weak."

> "**Be precise about the price.** The initial consideration was about **twenty-one million**, and the earn-out settled at **fifteen point four million** in July 2025 — **roughly twenty-nine million all-in.** The twenty point nine million you may have seen quoted is the initial figure *net of cash acquired*, not the total."

> "And the takeaway: **it answers a different question.** scite tells you how *other people* cited a paper. It never tells you whether *your sentence* matches *your source.*
>
> The category is real and funded. **It's just pointed somewhere else.**"

**提示：** 主动说清 $29M，是证明你们核过账的加分动作。**这段不能砍。**

---

## Slide 5 — Core Function One（1 分 20 秒）

**主讲：** Sichen

**动作：** 三张卡片（Empathise / Define / Ideate）**不要念**，手一指带过。时间留给数字和右图。

> "Function one: Smart Citations. We analysed it the way the template asks — empathise, define, ideate. **I'll skip reading the cards and go to the numbers.**
>
> **These are scite's own published figures.** Mentioning: ninety-six. Supporting: **fifty-five.** Disputing: **twenty.** The classes that carry the scientific signal are the rarest, and the hardest to classify. Their own paper also admits ingestion **fails on about thirty percent** of citation statements in PDFs."

> "And an **independent peer-reviewed audit** found worse: across three hundred twenty-four citations of retracted papers, **scite returned zero contrasting — human assessors found seventeen.**
>
> **Our comment:** the engineering is serious, and this is the strongest competitor, **not a straw man.** But the failure mode isn't a wrong label — **it's a label that reads as reassurance.**"

> "**One thing about the screenshot on the right** — it's a *prepared example comparison*, and it says so on the image itself: no backend analysis was performed for it. **Treat it as an illustration of the interface, not as a result.**"

**提示：** 最后这段必须说。图里明写着 "EXAMPLE COMPARISON · SAMPLE RESULT"，你不说而被 tutor 发现，效果完全相反。**主动说 = 严谨，被问出来 = 心虚。**

---

## Slide 6 — Core Function Two（1 分 20 秒）

**主讲：** Jun Li Li

**动作：** 左栏四条评论挑「Metadata, not meaning」讲透，其余留给观众读。右图是 ClaimTrace 自己的界面 —— 指一下五个状态。

> "Function two: **Reference Check** — the same corpus, pointed at your own manuscript. It's the closest thing in the market to our Audit feature, so let's be fair to it, and then precise about where it stops.
>
> **It reports on third parties.** It tells you reference number twelve has been retracted. **It cannot tell you that your sentence about number twelve is wrong** — and to its credit, it doesn't claim to. Notices are facts about a *record*; they're silent on whether the record supports the claim attached. And unlike Smart Citations, **Reference Check publishes no accuracy figure at all.**"

> "The screenshot on the right is **ours** — the Audit interface, with the five states and the field checks behind them. Audit checks the record: does the reference exist, and do title, authors, year and venue agree. OpenAlex first, Crossref as fallback, both keyless.
>
> And the line we'd want you to take away. **A failed lookup stays `LOOKUP_FAILED`.** `NOT_FOUND` means the search *completed* and found nothing. **We never turn a failed lookup into a verdict.**"

**提示：** 最后一句是本项目唯一可被验证的独占设计。**任何情况下都不砍。** 注意它现在**只写在界面上，不在这页文字里** —— 必须由你说出来。

---

## Slide 7 — Thank you（20 秒）

**主讲：** Sichen

> "So: the market is real, the leader is funded, and the column we're aiming at is owned by no established product.
>
> Thank you — we'd love your questions."

---

## 上台前必看：A1 讲稿里需要改口的数字

`ClaimTrace-Pitch-Script-and-QA.md` 里有几处和这套 deck 冲突。**如果被问到，按右边这列说：**

| 别再说 | 改说 |
|---|---|
| "12,402 papers, 7.1%" | "16.9% of quotations are incorrect, 8% are major — 46 studies, 32,000 quotations" |
| "375 retracted, 76%, 9,662 citations" | 用 "70–94% of retracted papers keep being cited；一篇 Nature Index 研究里是 93.9%" |
| "$371M → $617M, 7.6% CAGR" | "vendors 估到 3 倍差距（$371M–$1,150M），能审计的只有 Clarivate 的 $1.266B" |
| "GhostCite 76.7% of reviewers" | 不说。用 BMJ 2023 + 审稿人实验（漏掉 2/3 major errors）代替 |
| "scite acquired for $20.9M" | "≈$29M all-in：$21.1M initial + $15.4M earn-out（2025 年 7 月敲定）" |
| "Overleaf 25M users / 200M documents" | "Overleaf 自己的 about 页写的是 20 million+ users" |

**保留不变：** GPT-4o 19.9% / 45.4%、GPT-3.5 55% / 43% —— 这两个数字站得住，继续用。

---

## 这份 deck 里三处需要小心的地方

不是错误，但**被追问时要有准备好的说法**：

1. **Slide 3 表格里的 ClaimTrace 行是自评。**
   `Text Match? Yes` 要解释清楚：「是拿你的句子去比对**来源段落**，不是拿全文去比对语料库 —— 和 Turnitin 不是一回事。」
   `Cited by Others? (Fallback)` 这一格**目前的产品并没有这个功能**，被问到就直说「那是我们规划中的回退路径，不是已交付能力」。**不要临场把它说成已有功能。**

2. **Slide 3 的表格不再显示「prototypes 也在做」。** 原文的 "unoccupied is not empty" 提示没了，所以这句**必须由 Siyuan 口头补上**，否则 "★ SOLE FOCUS" 会被读成「没人在做」，而那是假的。

3. **Slide 5 的截图是示意，不是真实分析结果。** 图上自己写着 "Prepared example comparison; no backend analysis was performed" 和 "This score is illustrative"。**Sichen 必须主动说明**。Slide 6 的截图是真实界面，可以说「这就是我们的 Audit 页面」。

---

## 三条贯穿全场的原则

1. **每个数字都带出处和年份。** 新 deck 每页底部已有 Sources 行，**指着它说**比背出来更好。
2. **主动交代弱点。** 「表格里我们自己那一行是自评」「截图是示意」「unoccupied is not empty」—— 主动说 = 可信；被问出来 = 心虚。
3. **回到那一句。** 每个答案最后都落回：**"We never turn a failed lookup into a verdict."**

---

## 时间不够时的取舍顺序

越靠前越先砍：

1. Slide 5 的现场演示（改成指截图，省 20–30 秒）
2. Slide 3 的「自评」说明（省 15 秒，但**被问到一定要说**）
3. Slide 2 的四类工具逐一点名（省 20 秒，只说 Turnitin 和 scite 两个代表）
4. Slide 4 的「四个理由」（省 20 秒，只留 pipeline 和 paid-for 两条）

**永远不砍：** Slide 2 的 16.9% / 8.0%、Slide 4 的价格说明、Slide 6 的 failure rule、Slide 5 的「截图是示意」。

---

## 分工表

**本轮分工：** 市场 = Hongyang + Siyuan；Case Study + Core Function = Sichen + Jun Li Li。

| Slide | 内容 | 主讲 | 时长 |
|---|---|---|---|
| 1 | 封面 | Sichen | 0:25 |
| 2 | The targeted market | **Hongyang** | 2:00 |
| 3 | Empirical Evidence | **Siyuan** | 1:20 |
| 4 | Case Study — scite.ai | **Jun Li Li** | 1:15 |
| 5 | Core Function One | **Sichen** | 1:20 |
| 6 | Core Function Two | **Jun Li Li** | 1:20 |
| 7 | 收尾 | Sichen | 0:20 |
| | | **合计** | **8:00** |

各人时长：Hongyang 2:00 · Siyuan 1:20 · Sichen 2:05 · Jun Li Li 2:35。

**说明：** Slide 4/5/6 三人两两分配是建议方案（Jun Li Li 拿 4 和 6，Sichen 拿 5）。换成「Sichen 拿 4+5、Jun Li Li 只拿 6」的话，两人会变成 Sichen 3:20 / Jun Li Li 1:20，比现在更不平均 —— 所以建议维持上表。**要换告诉我，我重排时间。**

**建议：** 封面上的 Yi Jiang、Zheng Fu、Yiyang Yuan 本轮没有台词。可以让他们负责 **Slide 5/6 的现场操作**（切换截图、放大界面）或者 Q&A 环节接问题 —— 有明确任务比空着好。
