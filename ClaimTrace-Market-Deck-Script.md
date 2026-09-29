# ClaimTrace — Market Deck 逐页讲稿

> 对应 `ClaimTrace-Market-Competitor-Analysis.pptx`（7 页）
> 目标时长：**8 分钟**（英文台词 1,020 词，140 wpm 约 7 分 20 秒，余下约 40 秒给停顿、翻页和现场演示）
> 每页标注了分页时间，加起来正好 8:00。**超时就砍 Slide 5/6 的演示，不要砍 Slide 2。**
> 体例同 `ClaimTrace-Pitch-Script-and-QA.md`：中文提示 + 英文可直接照读

**开场前提醒：** 这套 deck 的数字和 A1 讲稿**不完全一样**——A1 里 12,402/7.1%、371M→617M、GhostCite 76.7%、20.9M 这几个数字经核查站不住，已替换。文末有一节列出必须改口的地方，**上台前务必看那一段**。

**压缩说明：** 这是 8 分钟版。原 9–11 分钟版见 `git log -- ClaimTrace-Market-Deck-Script.md`。被砍掉的主要是**屏幕上已经写着的内容**（Slide 5/6 的三张卡片、各页条目），所有数字和出处一个没删。

---

## Slide 1 — 封面（30 秒）

**建议主讲：** Sichen（组长）

> "Good morning. We're Group 18 — this is our market and competitor analysis for **ClaimTrace**, a citation audit tool for academic writing.
>
> One thing about method, because it shapes every slide: **we re-checked every number in this deck.** Where we couldn't trace a figure to a source, we cut it — including numbers from our own earlier pitch."

**提示：** 最后一句是关键——它把「换数字」这件事变成了方法论上的加分项，而不是被抓包。说完停半秒再翻页。

---

## Slide 2 — The targeted market（2 分 30 秒，全 deck 的核心）

**建议主讲：** Hongyang（①②④）+ Sichen（③）

### ① 市场是什么

> "Our market is academic writing. Overleaf alone reports **twenty million users**, and **five point seven million papers** were published in 2024 — up from three point nine million in 2019. **Forty-six percent growth in five years.**
>
> Every claim in every one of those papers cites a source."

### ② 问题有多大

> "And **one in six of those citations is wrong.** **Sixteen point nine percent** of quotations are incorrect; **eight percent** are major — the source says something different from what the author claimed.
>
> That pools **forty-six studies and thirty-two thousand quotations**. Baethge and Jergas, 2025. And the trend line is flat — **no improvement in forty years.**"

**提示：** "Sixteen point nine" 和 "no improvement in forty years" 放慢、重读。这是全场最有力的数字。

### ③ 谁在拦

> "Nothing downstream catches it. Reviewers missed **two-thirds of major errors** in one experiment, and **three out of nine** planted errors in another.
>
> A **BMJ** analysis in 2023 said responsibility for auditing citations *'rests with those who selected it, not reviewers'* — and proposed **AI tools at submission** to do exactly this.
>
> That's our product thesis. Published in a medical journal."

### ④ 市场多大，缺口在哪

> "Now the market size — and this is where the easy answer is wrong.
>
> Three commercial estimates, same category, same year: **three hundred seventy-one million, three hundred eighty-five million, and one point one five billion.** That's **three times apart.** The only audited number is Clarivate's — **one point two six six billion**, from their SEC filing.
>
> So we show the spread and quote the audited figure. **A number without its scope isn't evidence.**"

> "Four kinds of tool exist. **Reference managers** format metadata. **Turnitin** checks text overlap — in its own words, *'Turnitin does not check for plagiarism.'* **Reference checkers** confirm a record exists. And **scite** classifies how *other people* cited a paper.
>
> None of them answers our question: **does my source support my sentence?**
>
> ReciteWorks' own FAQ says *'No, not currently.'* And the price list agrees — **a hundred and seventy-five dollars buys metadata checking, a hundred and twenty-five buys similarity.** Neither buys claim support."

**提示：** "Neither buys claim support" 是全页落点。说完停顿，再翻到 Slide 3。

---

## Slide 3 — 三张图（1 分 25 秒）

**建议主讲：** Sichen

**动作：** 按「左下 → 右上 → 右下」的顺序讲，和鼠标走位一致。

### 左下：写作面 vs 付费面

> "Three figures, one argument. Start bottom-left.
>
> **Twenty million people** write in Overleaf. scite — the category leader — had about **twenty-one thousand paying subscribers** when it was acquired. Roughly **nine hundred and fifty to one.**
>
> Every researcher writes citations. **Almost nobody pays to have them verified.**"

### 右上：市场

> "Top right. Research output keeps growing — but the tooling market that serves it is sized **three times apart** by different vendors for the same year.
>
> That disagreement *is* the finding. It's why we name a scope instead of quoting a point estimate."

### 右下：能力矩阵

> "Bottom right: thirteen products, four questions. The first three columns are occupied. **The fourth — does your source support your sentence — is owned by no established product.**
>
> One honest note: **unoccupied is not empty.** RefVerifier, Grounded AI and sci2sci are trying it. We're not claiming nobody's trying — we're claiming **no established product owns it.**
>
> And the partial marks are deliberate. The matrix distinguishes **'documents this'** from **'claims this.'**"

**提示：** 「unoccupied is not empty」这句主动交代弱点，比被 tutor 问出来强得多。**这句不能砍。**

---

## Slide 4 — Case Study: scite.ai（1 分钟）

**建议主讲：** Siyuan

> "For the case study we picked scite.ai — the biggest competitor, and the one every reviewer names first. **Research Solutions — NASDAQ-listed — bought it in December 2023**, so the category is real and paid for.
>
> **Be precise about the price.** The initial consideration was about **twenty-one million**, and the earn-out was finalised at **fifteen point four million** in July 2025 — **roughly twenty-nine million all-in.** The commonly-quoted twenty point nine million is only the first part.
>
> But it answers a different question. scite tells you how *other people* cited a paper. It never tells you whether *your sentence* matches *your source.*
>
> The category is real and funded. It's just pointed somewhere else."

**提示：** 主动纠正 20.9M 这个数字，是**加分动作**——它证明你们核过账，而不是抄了个数。**这段不能砍**，它是全场唯一一处当场纠错的示范。

---

## Slide 5 — Function 1: Smart Citations（1 分 10 秒）

**建议主讲：** Yi Jiang

**动作：** 三张卡片（Empathise / Define / Ideate）**不要念**，指一下就说「as the template asks」。时间留给下面的数字。有网就现场开 scite 免费版演示。

> "Function one: Smart Citations. We analysed it the way the template asks — empathise, define, ideate.
>
> Now the part I'd want you to look at. **These are their own published numbers.** Mentioning: ninety-six. Supporting: **fifty-five.** Disputing: **twenty.**
>
> The classes that carry the scientific signal are the rarest, and the hardest to classify."

> "And an **independent peer-reviewed audit** found worse. It took three hundred and twenty-four citations of retracted papers. scite returned **two supporting, ninety-six mentioning, and zero contrasting.** Human assessors found **seventeen contrasting** — citations the product showed as none, in a study of retracted papers, which is exactly where a contrasting signal matters most.
>
> **Our comment:** the engineering is serious and openly documented. This is the strongest competitor, not a straw man. But the failure mode isn't a wrong label — **it's a label that reads as reassurance.** And an aggregate label about a paper can't answer a question about your sentence. That's a scope limit, not a bug."

**提示：** 如果 tutor 追问「scite 作者反驳了怎么办」——承认：2025 年有 scite 相关作者发过 reply 质疑方法，争议未定，不要说成定论。

---

## Slide 6 — Function 2: Reference Check（1 分 10 秒）

**建议主讲：** Zheng Fu

**动作：** 同样不念卡片。左栏四条评论挑「Metadata, not meaning」一条讲透，其余留给观众读。

> "Function two is Reference Check — the same corpus, pointed at your own manuscript. It's the closest thing in the market to our Audit feature, so let's be fair to it, then precise about where it stops.
>
> **It reports on third parties.** It tells you reference number twelve has been retracted. **It cannot tell you that your sentence about number twelve is wrong** — and to its credit, it doesn't claim to."

> "ClaimTrace covers the two layers it leaves open.
>
> **Audit — the record.** Existence, and whether title, authors, year and venue agree. OpenAlex first, Crossref as fallback, both keyless.
>
> **Verify — the meaning.** The source passage that supports or contradicts your sentence — **the passage shown, not just a label.**
>
> And the third one is genuinely ours. **The failure rule.** A failed lookup stays `LOOKUP_FAILED`. `NOT_FOUND` means the search *completed* and found nothing. **We never turn a failed lookup into a verdict.**"

**提示：** 「never turn a failed lookup into a verdict」是本项目唯一的、可被验证的独占设计。**这是全场最该被记住的一句，任何情况下都不砍。**

---

## Slide 7 — Thank you（25 秒）

**建议主讲：** Sichen

> "So that's the analysis. The market is real, the leader is funded, and the column we're going after is unoccupied.
>
> We can show you two things live — the Overleaf hover flow, and an audit run on a real bibliography.
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

## 时间不够时的取舍顺序

砍到这个顺序为止，**越靠前越先砍**：

1. Slide 5 的现场演示（省 20–30 秒，改成指截图）
2. Slide 3 右下的「unoccupied is not empty」补充说明（省 15 秒，但**被问到一定要说**）
3. Slide 6 的 Audit / Verify 两层细节（省 20 秒，卡片上写着）
4. Slide 2 ④ 的四类工具逐一点名（省 20 秒，只说 Turnitin 和 scite 两个代表）

**永远不砍：** Slide 2 ② 的 16.9% / 8.0%、Slide 4 的价格纠正、Slide 6 的 failure rule。

---

## 分工建议

按现有分组，7 人 7 页，每人一分钟左右，平衡且每个人都有台词：

| Slide | 主讲 | 时长 | 理由 |
|---|---|---|---|
| 1 封面 | Sichen | 0:30 | 组长开场 |
| 2 市场 | Hongyang | 2:30 | 后端组，市场数据部分 |
| 3 三张图 | Sichen | 1:25 | 图表是组长做的，讲得最顺 |
| 4 Case Study | Siyuan | 1:00 | 后端组 |
| 5 Function 1 | Yi Jiang | 1:10 | Parser 组 |
| 6 Function 2 | Zheng Fu | 1:10 | Parser 组 |
| 7 收尾 | Sichen | 0:25 | 收尾 + 接 Q&A |

Jun Li 和 Sam（前端组）建议负责 Slide 5/6 的**现场演示**——由他们操作 Overleaf 悬停和审计演示，讲解交给台上的人。这样前端组也有明确任务。
