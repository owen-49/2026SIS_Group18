# ClaimTrace — Market Deck 逐页内容

> 对应 `ClaimTrace-Market-Competitor-Analysis.pptx`（7 页，26.66 × 15.00 in）
> 本文是**幻灯片正文本身**，逐字从 pptx 抽取，未改写。不是讲稿（见 `ClaimTrace-Market-Deck-Script.md`），
> 也不是书面报告（见 `ClaimTrace-Market-Analysis.md`）。
> 数据核对日期：**2026-09-24**。

**用途：** 给组员核对文字、给需要提交文字版的人、以及改 deck 时确认改动点。
每页末尾的「出处」一栏摘自该页 speaker notes，**做 deck 时不要把出处删掉** —— 这套 deck 的立论就是「每个数字都能追到来源」。

---

## Slide 1 — 封面

**版式：** 模板版式 `TITLE_AND_BODY`

| 位置 | 内容 |
|---|---|
| 标题占位符 | `Software Innovation Studio` |
| 副标题框 | `ClaimTrace — the academic citation audit engine`<br>`Market & Competitor Analysis` |
| 署名框 | `Group 18 · Sichen Liu · Hongyang Chen · Siyuan Sun · Jun Li · Yi Jiang · Zheng Fu · Sam`<br>`41129 Software Innovation Studio · 22 Oct 2026` |

前两行是模板自带文字，未改动。

**出处：** 无数据。

---

## Slide 2 — The targeted market

**版式：** 模板版式 `1_Title, text 2 column and image`
**标题：** `The targeted market`

正文框（单栏通栏，四个编号小节）：

### 1.  The targeted market

- Academic writing. Overleaf alone reports 20M+ users, and 5.7M papers were published in 2024, up from 3.9M in 2019 (+46%). Every claim in every paper cites a source.
- One in six quotations is wrong and half of those are major — 16.9% incorrect, 8.0% major, across 46 studies and 32,074 quotations, with no improvement in 40 years.

### 2.  How large, and the trend

- Demand grows; the tooling market is small and inconsistently sized. Vendors put reference-management software at $371M–$1,150M for the same year — 3× apart. The one audited number is Clarivate's Academia & Government segment (Web of Science + EndNote): $1,266.0M, FY2025, filed with the SEC.
- *（缩进小字）* So we quote a report, its scope and its CAGR — or we quote the one an auditor has seen.

### 3.  What already exists

- Reference managers — Zotero (14.4M users), Mendeley, EndNote: store and format metadata.
- Similarity checkers — Turnitin, iThenticate: match text. Turnitin's own help centre: “Turnitin does not check for plagiarism.”
- Reference checkers — ReciteWorks, Edifix, CiteTrue, Paperpile, SciSpace: confirm the record exists.
- Citation-intent platforms — scite (1.6B Smart Citations), Semantic Scholar: classify how OTHERS cited the paper.

### 4.  The gap

- No established product answers: “does MY cited source support MY sentence?” ReciteWorks' FAQ answers “No, not currently” — and the price list agrees: $175/manuscript buys metadata checking, $125 buys text similarity, neither buys claim support.
- It is getting worse, not better: fabricated citations rose 12-fold, from 1 in 2,828 papers (2023) to about 1 in 277 (early 2026), and 98.4% of affected papers saw no publisher action.

**出处（讲这页时必须能说出年份）：**

- Overleaf `overleaf.com/about` 写 “20 million+ users”；同页另有 “over 30 million people trust Overleaf”。本 deck 取较小且明确的那个，并说明取的是哪一个。
- 5.7M (2024) / 3.9M (2019)：Dimensions 数据，经 STM 与 Research Consulting 报告，2026-01-13。
- 16.9% / 8.0%：Baethge & Jergas (2025), *Research Integrity and Peer Review* 10(1):13 —— 46 项研究、约 32,074 条引文的 meta 分析；meta 回归斜率 −0.002，p = 0.85（即四十年无改善）。**全 deck 的头号数字。**
- 市场规模：globalinforesearch.com $371M、yhresearch $385M、wiseguyreports.com $1.1–1.2B（同为 2024、同为 reference-management software）。商业估算，口径不一 —— 所以本页给区间而不给点估计。
- Clarivate A&G segment $1,266.0M FY2025（FY2024 $1,326.4M；FY2023 $1,323.3M），SEC Form 10-K。**全 deck 唯一经过审计的数字。**
- Zotero 14.4M 用户、同比 +25%：Corporation for Digital Scholarship Annual Report 2024。
- Turnitin / iThenticate：均为厂商自述。ReciteWorks FAQ 原话 “No, not currently”。
- $175：EditVerse 参考文献核验（仅元数据与存在性）。$125：iThenticate 直购单篇，仅相似度。
- 1 in 2,828 (2023) → 1 in 458 (2025) → ~1 in 277 (2026 年前七周)、98.4% 无出版商处理：审计 2,471,758 篇 PMC 文章、125.6M 条参考文献，*Lancet* 2026，经 *Nature* 报道。

---

## Slide 3 — The targeted market（三图页）

**版式：** 模板版式 `1_Title, text 2 column and image`
**标题：** `The targeted market`（与 Slide 2 同题，模板如此）

**图（三张，位置与模板图框完全一致）：**

| 位置 | 文件 | 图框尺寸 | 纵横比 |
|---|---|---|---|
| 左上（跨至左下） | `ClaimTrace-Market-Figures/surface.png` | 11.90 × 7.66 in | 1.554 |
| 右上 | `ClaimTrace-Market-Figures/market_size.png` | 14.16 × 7.50 in | 1.888 |
| 右下 | `ClaimTrace-Market-Figures/gap_matrix.png` | 13.78 × 6.21 in | 2.219 |

> 替换图片时**必须保持上述纵横比**，`add_picture` 会拉伸填满图框。

**说明文字框（左下角）：**

- Bottom left: the people who write citations, against the far smaller group that pays to have them checked.
- Top right: the volume of research keeps growing, but the tooling market that serves it is sized 3× apart by different vendors for the same year.
- Bottom right: what each class of tool actually checks. The outlined column is the gap.

**出处：**

- 写作面 vs 付费面：Overleaf 20M+ 使用者；scite 被收购时约 21,000 名付费订阅者 —— 约 **950:1**。
- 市场图：左panel 3.9M→5.7M（+46%）；右 panel 四个数（$371M / $385M / $1,150M / Clarivate $1,266.0M），红括号标出 371 与 1150 相差 3 倍。
- 能力矩阵：13 个产品 × 4 个问题。前 3 列已有人占；第 4 列（**你的来源是否支撑你的句子**）无成熟产品占据。“Yes” = 厂商有文档；“partial” = 相邻能力或厂商单方声称、无独立评测。

---

## Slide 4 — Case Study

**版式：** 模板版式 `1_Title, text 2 column and image`
**标题：** `Case Study`

**导语（通栏）：**
`scite.ai — the biggest competitor, and the one every reviewer names first`

**左栏 — What it is**

- Founded 2018 in Brooklyn; co-founder & CEO Josh Nicholson.
- Smart Citations label how a paper has been cited — supporting, contrasting or mentioning — one label per citation statement.
- 1.6B+ Smart Citations, 317M+ articles indexed, 44+ publisher partners.
- Acquired by Research Solutions (NASDAQ: RSSS), announced 27 Nov 2023, closed 1 Dec 2023 — about $20.9M net of cash acquired.
- At acquisition: ~21,000 paying subscribers, $3.6M annualised subscription revenue, $1.1M FY2023 revenue.

**右栏 — Why it is the case to study**

- It is the only competitor with a comparable data pipeline: full-text ingestion, a trained classifier, published methods.
- It proves the category is paid for. A NASDAQ-listed company bought it.
- Its own peer-reviewed paper publishes its accuracy — including where it is weak.
- It answers a different question from ours, and says so on its own product page.

**蓝色结论条（通栏）：**
`The category is real and funded. But the market leader answers “how have others cited this paper?” — never “does my sentence match my source?”`

**出处：**

- 成立、规模、功能：`scite.ai/features`（2026-09-24 核对）。
- 收购：Research Solutions (Nasdaq: RSSS) 新闻稿 2023-11-27，2023-12-01 交割。**被追问时要精确：** 初次对价约 **$21.1M**（FY2025 10-K），earn-out 于 2025 年 7 月敲定为 **$15.4M**，全口径约 **$29M**。slide 上的 “$20.9M net of cash” 是初次对价扣现金后的数字，不是总额 —— A1 讲稿把它当成总额了。
- 订阅数与营收：截至 2023-10-31，约 21,000 名付费 B2C 订阅者、$3.6M 年化订阅收入、$1.1M FY2023 收入（SEC 文件／新闻稿）。

---

## Slide 5 — Case Study – Function 1

**版式：** 模板版式 `1_Title, text 2 column and image`
**标题：** `Case Study – Function 1`

**导语（通栏）：**
`Smart Citations — classify how a paper has been cited, at scale`

**三张卡片（Empathise / Define / Ideate）：**

**Empathise**
- A researcher holding an unfamiliar paper asks one question: can I trust this?
- Reading every citing paper is impossible; the citation count alone says nothing about whether anyone disagreed.
- They want a signal that survives scrutiny, not a score.

**Define**
- For each citation statement in each citing paper, decide whether it supports, contrasts with, or merely mentions the cited work.
- Constraint: a label must rest on scientific evidence, not sentiment. scite states it is explicitly not sentiment analysis.

**Ideate**
- Fine-tuned SciBERT over 38,925 labelled citation statements with a 9,708 holdout; ~2 years of annotation, at least two blind annotators, up to 8 experts.
- Three classes: supporting / mentioning / disputing, surfaced as Smart Citations.
- Production targets >80% precision on every class.

**左栏 — What its own paper measures**（每条附灰色小注）

| 正文 | 小注 |
|---|---|
| F-score at first publication: 96.3 mentioning · 55.3 supporting · 20.5 disputing | weak where it matters |
| Disputing later reached 58.97 F-score at 85.19 precision | improved, still low |
| Real-world distribution: ~92.6% mentioning, 6.5% supporting, 0.8% disputing | the classes that matter are the rarest |
| Ingestion “fails to identify approximately 30% of citation statements/references in PDF files” | their own stated limit |

**右栏 — An independent peer-reviewed audit found worse**（红标题）

- Bakker, Theis-Mahon & Brown (2023), *Hypothesis* 35(2), doi:10.18060/26528
- 324 citations of retracted works; scite classified only 98 (no full text for 118).
- scite returned 2 supporting / 96 mentioning / 0 contrasting.
- Human assessors found 42 supporting / 39 mentioning / 17 contrasting.
- F-measures ranged 0.0–0.58.

**底部评论条（通栏）— Our comment**

- The engineering is serious and openly documented — this is the strongest competitor, not a straw man.
- The failure mode is not a wrong label; it is a label that reads as reassurance. A human saw 17 contrasting citations where the product showed none.
- Aggregate labels about a paper cannot answer a question about your sentence. That is a scope limit, not a bug to be tuned away.
- ClaimTrace's response is the opposite discipline: a verdict is only ever carried by a state that actually judged, and every other state stays visibly unjudged.

**出处：**

- 方法与精度：Nicholson et al. (2021), *Quantitative Science Studies* 2(3):882–898, doi:10.1162/qss_a_00146。
- 独立审计：Bakker, Theis-Mahon & Brown (2023), *Hypothesis* 35(2), doi:10.18060/26528。
- **若被问及：** scite 相关作者 2025 年发过 reply 质疑该审计的方法，争议未定 —— 承认它，不要把批评说成定论。
- 演示：scite 免费版任一论文页可看 Smart Citations；没网则指截图。**没跑过就不要说跑过。**

---

## Slide 6 — Case Study – Function 2

**版式：** 模板版式 `1_Title, text 2 column and image`
**标题：** `Case Study – Function 2`

**导语（通栏）：**
`Reference Check — point the same corpus at your own manuscript`

**三张卡片：**

**Empathise**
- The moment before submission: the bibliography is the part nobody re-reads until a reviewer does.
- Authors inherit references from co-authors, from Google Scholar exports, from AI assistants.
- The fear is specific — that one entry is retracted, or describes a different paper.

**Define**
- Upload a manuscript PDF and see, for every reference, how it has been cited by others: retractions, editorial notices, contrasting findings.
- The unit of analysis moves from “a paper” to “my reference list”.

**Ideate**
- Reuse the Smart Citations corpus and the retraction and editorial-notice data.
- Report per reference rather than per paper, so the output is a submission checklist.
- Keep it inside the existing subscription rather than a separate product.

**左栏 — Our comment — where this stops**（粗体小标题 + 灰色小注）

| 小标题 | 小注 |
|---|---|
| It looks like it checks your manuscript. It still reports on third parties. | Reference Check tells you reference #12 has been retracted. It cannot tell you that your sentence about #12 is wrong, and it does not claim to. |
| Metadata, not meaning. | Retraction and editorial notices are facts about a record. They are silent on whether the record supports the claim it was attached to. |
| No published accuracy figure for Reference Check. | Smart Citations has a peer-reviewed evaluation; this feature does not. |
| Pricing is per user and unpublished institutionally. | $20/mo Basic, $50/mo Pro, both billed yearly; no public institutional price. |

**右栏 — ClaimTrace covers the two layers Reference Check leaves open**（粗体小标题 + 灰色小注）

| 小标题 | 小注 |
|---|---|
| Audit — the record | Reference exists; title, authors, year, venue agree. OpenAlex first, Crossref as fallback, both keyless. |
| Verify — the meaning | The source passage that supports or contradicts your sentence, with the passage shown, not just a label. |
| The failure rule | A failed lookup stays LOOKUP_FAILED. NOT_FOUND means the search completed and found nothing — never “looks fabricated”. |

**出处：**

- `scite.ai/features`：功能原文 “Upload a manuscript PDF and instantly see how every reference has been cited by others”，含 retractions、editorial notices、contrasting findings。
- 定价 `scite.ai/pricing`：Basic $20/mo、Pro $50/mo，均按年计费；无公开机构价。
- 最后一条规则见 `claimtrace/docs/audit-contract.md` §2、§4。
- 演示：若没实际跑过 Reference Check，不要说跑过 —— 本页引的是官方文档原文。

---

## Slide 7 — Thank you

**版式：** 模板版式 `1_Thankyou`

| 位置 | 内容 |
|---|---|
| 标题占位符 | `Thank you` |

模板原文，未改动（原文中间有一个制表符）。

**出处：** 无数据。

---

## 附：全 deck 的数据纪律

1. **每个数字都带出处和年份。** 说 “sixteen point nine percent” 后面要跟 “Baethge and Jergas, 2025”。
2. **范围必须说明。** “reference-management software market” 和 “scholarly publishing market” 差两个数量级。没有口径的数字不是证据。
3. **厂商自述要标明是厂商自述。** Turnitin、Overleaf、scite 自己的宣称照用，但归给它们，不当作已审计事实。
4. **来源冲突时报冲突，不挑好看的那个。**

### A1 讲稿里必须改口的数字

| 别再说 | 改说 |
|---|---|
| “12,402 papers, 7.1%” | “16.9% of quotations are incorrect, 8% are major — 46 studies, 32,000 quotations” |
| “375 retracted, 76%, 9,662 citations” | “70–94% of retracted papers keep being cited；一篇 Nature Index 研究里是 93.9%” |
| “$371M → $617M, 7.6% CAGR” | “vendors 估到 3 倍差距（$371M–$1,150M），能审计的只有 Clarivate 的 $1.266B” |
| “GhostCite 76.7% of reviewers” | 不说。用 BMJ 2023 + 审稿人实验（漏掉 2/3 major errors）代替 |
| “scite acquired for $20.9M” | “≈$29M all-in：$21.1M initial + $15.4M earn-out（2025 年 7 月敲定）” |
| “Overleaf 25M users / 200M documents” | “Overleaf 自己的 about 页写的是 20 million+ users” |

**保留不变：** GPT-4o 19.9% / 45.4%、GPT-3.5 55% / 43% —— 这两个数字站得住，继续用。
