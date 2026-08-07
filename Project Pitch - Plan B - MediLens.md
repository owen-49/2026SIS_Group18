# 🔬 Project Pitch — Plan B: MediLens

> 基于 41129 Software Innovation Studio 模板「Template of Project Pitch.pdf」格式  
> 准备日期: 2026-08-07

---

## Slide 1 — 封面

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║              Software Innovation Studio                      ║
║                                                              ║
║                    Team [Your Team Name]                     ║
║                                                              ║
║                        MediLens                              ║
║          Your AI-Powered Medical Knowledge Compass           ║
║                                                              ║
║      "每年有 400 万篇医学论文发表 —                              ║
║        你该读哪一篇来理解自己的体检报告？"                         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**Tagline**: From "my ALT is 45, what does that mean?" to an evidence-grounded answer with citations — in one search.

---

## Slide 2 — Project Scope and Users (What and Who)

### 2.1 The Problem: 我们发现了什么问题？

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   📋 全球每年进行数十亿次常规体检                                 │
│                                                                 │
│   🤷 收到报告后，大多数人在见到医生之前                           │
│       只能搜 Google → 被吓到 → 陷入焦虑循环                      │
│                                                                 │
│   📚 PubMed 收录 3700 万+ 篇生物医学论文                          │
│      每年新增 400 万篇 — 但没有给普通人的接口                      │
│                                                                 │
│   ⚠️ ChatGPT / 通用 AI 回答医学问题时:                            │
│      • 不引用来源（不知道是不是编的）                              │
│      • 不包含最新研究                                             │
│      • 不看图表和影像                                             │
│                                                                 │
│   🩺 基层医生也没时间读完所有最新文献                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Users' Pain Points: 用户的真实痛点

| # | 痛点 | 用户原话 (User Voice) |
|---|------|----------------------|
| 1 | **体检报告看不懂** | "报告上写着'ALT轻度偏高'，我 Google 了一下，有的说没事，有的说可能是肝癌 — 到底该信哪个？" |
| 2 | **网上信息不可靠** | "百度/Google 搜出来的要么是广告，要么是吓人的内容，真正靠谱的医学论文我又看不懂" |
| 3 | **AI 胡说不敢信** | "ChatGPT 说得头头是道，但没有任何引用 — 万一是它编的呢？" |
| 4 | **医学论文对普通人不友好** | "我知道 PubMed 上有答案，但我看不懂方法学和统计部分，我只想知道结论" |
| 5 | **信息孤岛** | "我的体检 PDF、B 超图片、血常规表格是三种格式 — 没有一个工具能同时处理它们" |

### 2.3 Target Users: 谁需要这个产品？

```
Primary Users (核心用户)
├── 🧑‍⚕️ 健康焦虑型消费者 (30-55岁)
│      → 收到体检报告后想要靠谱的初步解读
│      → 不想等到 2 周后医生有空才问
│
├── 🩺 基层社区医生 / 全科医生
│      → 需要快速检索最新文献辅助诊断
│      → 没时间读全文，需要 AI 摘要
│
└── 📚 医学生 / 健康科学学生
       → 学习如何将文献知识应用于具体病例

Secondary Users (扩展用户)
├── 🏥 小型诊所 (无大型文献订阅)
├── 💊 慢性病患者社区 (了解最新治疗进展)
└── 📰 健康科普内容创作者 (需要可信来源)
```

### 2.4 Project Scope: 我们要做什么（12 周）

```
Week 12 交付范围:

  ✅ Core Feature 1: 多格式报告解析
     • PDF 体检报告 → 结构化指标提取 (OCR + NER)
     • 图片上传 (B超/CT报告单拍摄)
     • 表格数据识别

  ✅ Core Feature 2: 多模态医学知识检索 (RAG)
     • PubMed OA 文献索引 (聚焦 2-3 个常见领域)
     • 文本 + 图片 + 表格联合检索
     • 按权威性 + 时效性排序
     → 每个回复附带 PMID 引用

  ✅ Core Feature 3: Evidence-Grounded 解读生成
     • 用户体检指标 → 文献检索 → 解读生成
     • Hallucination 检测 (生成内容 vs 检索文献交叉验证)
     • 可读性适配 (专业版 vs 通俗版)

  ⏳ Out of Scope (留到未来):
     • 实时更新文献库 (12 周内做静态索引)
     • 专业医学影像诊断 (放射/病理 — 需要 FDA 批准)
     • 多语言支持 (先做英文 + 中文)
```

### 2.5 Objective: 成功的标准

> 让用户上传一份体检报告后，在 **2 分钟内**获得一份「每个指标都有文献引用的、普通人看得懂的」解读。

Measurable:
- 成功索引 ≥500 篇医学文献 (FAISS)
- 检索 Precision@5 ≥ 0.70 (与 ChatGPT 对比)
- 生成内容的引用准确率 ≥ 85%（人工抽检 50 条声明）
- Demo 展示：体检报告 PDF → 3 个关键指标解读 + PMID 引用

---

## Slide 3 — The Targeted Market (Why)

### 3.1 Market Size: 市场有多大？

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│          Global AI in Healthcare Market                        │
│                                                                │
│    2025:  $31 Billion                                          │
│    2030:  $188 Billion    (CAGR 43.4%)                        │
│    Source: MarketsandMarkets, 2025                             │
│                                                                │
│    ┌──────────────────────────────────────────────┐            │
│    │  Clinical Decision Support (subset)          │            │
│    │  2025: $8.5 Billion                          │            │
│    │  2030: $28 Billion                           │            │
│    │  Source: Grand View Research, 2025           │            │
│    └──────────────────────────────────────────────┘            │
│                                                                │
│    ┌──────────────────────────────────────────────┐            │
│    │  Consumer Health Information (our niche)     │            │
│    │  Estimated: $5-12 Billion addressable        │            │
│    │  Key driver: health anxiety + information    │            │
│    │  asymmetry between doctors and patients       │            │
│    └──────────────────────────────────────────────┘            │
│                                                                │
│    Annual health checkups globally:      ~4 Billion+           │
│    PubMed searches per day:              3 Million+            │
│    % of people Googling symptoms:         ~65%                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Landscaping: 竞品格局

| 产品 | 做什么 | 缺失什么 |
|------|--------|----------|
| **Google / 百度** | 关键词搜索 | ❌ 不区分权威性 ❌ 广告驱动的结果 ❌ 不读 PDF/图片 |
| **ChatGPT / Claude** | 自然语言医学问答 | ❌ **不引用来源** ❌ 不包含最新研究 ❌ 可能有幻觉 |
| **WebMD / 丁香医生** | 结构化症状检查 / 科普文章 | ❌ 内容固定，不能自由提问 ❌ 不做个性化报告解读 |
| **UpToDate** | 医生用的临床决策支持 ($$$) | ❌ $500+/年 ❌ 写给医生看的 ❌ 不处理用户上传的报告 |
| **PubMed** | 医学文献搜索引擎 | ❌ 无 AI 摘要 ❌ 只搜文本 ❌ 用户需要自己读论文 |
| **Ada / Buoy Health** | Symptom checker (AI 分诊) | ❌ 只做症状 → 分诊 ❌ 不读体检报告 ❌ 不检索文献 |
| **OpenEvidence** | AI + 医学文献 | ❌ 只面向美国医生 ❌ 不面向消费者 |

### 3.3 The Gap: 我们看到的缺口

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│      高                                UpToDate                 │
│      ▲                                              MediLens   │
│  可  │                                               🎯         │
│  信  │                                                          │
│  度  │              丁香医生      OpenEvidence                  │
│      │                                                          │
│      │  Google        WebMD        ChatGPT                      │
│      │                                                          │
│      │  低交互性                                   高交互性      │
│      │                                                          │
│      └──────────────────────────────────────────────────▶       │
│                         可及性 (Cost + Accessibility)           │
│                                                                 │
│  🎯 MediLens 的定位:                                            │
│     "UpToDate 的可信度 × ChatGPT 的易用性"                       │
│     面向普通人的、基于真实文献的医学 AI 问答                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Competitive Advantage (为什么我们能赢)**:

1. **Evidence Transparency**: 每个 AI 生成的解读都附带 PMID 引用 — 用户可以自己去验证，这是 ChatGPT/通用 AI 做不到的
2. **Multimodal Understanding**: 能同时处理体检报告 PDF + B 超图片 + 化验表格 — 竞品只做文本
3. **Consumer-Grade UX**: 给普通人的通俗解读（可选"医生版"深度），不像 UpToDate 动辄 $500/年
4. **Hallucination Defense**: 内建 NLI 验证 — AI 说完之后自我检查：这个说法在检索到的文献里能找到依据吗？

### 3.4 Market Timing: 为什么是现在？

- ✅ **2025 Multimodal RAG 技术成熟** — MMed-RAG (ICLR 2025)、MIRA、AlzheimerRAG 验证了可行性
- ✅ **LLM 幻觉问题依然严重** — 医学场景最需要引用透明，而通用 AI 在这点进步缓慢
- ✅ **患者赋权趋势** — 越来越多的人想要理解自己的健康数据（"second opinion" 文化）
- ✅ **PubMed 完全开放** — 3700 万篇文献免费检索，不需要付费墙
- ✅ **OCR + 文档解析技术进步** — Unstructured.io、PyMuPDF、Gemini Vision 极大降低 PDF 解析门槛

---

## Slide 4 — Solution (How)

### 4.1 What It Looks Like: 产品形态

```
┌─────────────────────────────────────────────────────────────────┐
│                      MediLens                       [📤] [👤]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📄 Upload Report:                                              │
│  ┌─────────────────────────────────────┐  ┌──────────────────┐ │
│  │  physical_report_2026.pdf           │  │  🔍 Analyze      │ │
│  │  已上传 (3 页, 包含 18 项指标)      │  │                  │ │
│  └─────────────────────────────────────┘  └──────────────────┘ │
│                                                                 │
│  📊 Extracted Indicators:                                       │
│  ┌──────────────┬───────┬─────────┬──────────────────────┐     │
│  │ Indicator    │ Value │ Ref.    │ Status               │     │
│  ├──────────────┼───────┼─────────┼──────────────────────┤     │
│  │ ALT (谷丙)   │ 45    │ 7-40    │ 🔴 Mildly Elevated   │     │
│  │ AST (谷草)   │ 30    │ 13-35   │ 🟢 Normal            │     │
│  │ LDL-C        │ 130   │ <100    │ 🟡 Borderline High   │     │
│  │ HbA1c        │ 5.6   │ <5.7    │ 🟢 Normal            │     │
│  └──────────────┴───────┴─────────┴──────────────────────┘     │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  💬 "请帮我解读 ALT 偏高的指标"                                  │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  🩺 MediLens:                                                   │
│                                                                 │
│  **ALT (Alanine Aminotransferase) at 45 U/L** is mildly above   │
│  the upper reference limit of 40 U/L.                           │
│                                                                 │
│  **What the literature says:**                                  │
│                                                                 │
│  1️⃣ Common causes in asymptomatic adults:                      │
│     • Non-alcoholic fatty liver disease (NAFLD) — present in    │
│       ~25% of global adults [PMID: 36511234, Lancet 2024]       │
│     • Recent strenuous exercise can temporarily elevate ALT     │
│       by 10-20% within 24-48 hours [PMID: 37890123]             │
│     • Certain medications (statins, acetaminophen) [PMID: ...]  │
│                                                                 │
│  2️⃣ Clinical significance:                                      │
│     • Isolated mild ALT elevation (< 2× ULN) with normal AST   │
│       in asymptomatic patients has a benign course in ~80%      │
│       of cases [PMID: 36988701, Am J Gastro 2025]               │
│     • Your AST/ALT ratio = 0.67 (normal), which makes           │
│       alcohol-related liver injury less likely [PMID: ...]      │
│                                                                 │
│  3️⃣ Recommended next steps (per AASLD 2025 guidelines):        │
│     • Re-test in 4-6 weeks [PMID: ...]                          │
│     • Consider liver ultrasound if persistently elevated         │
│                                                                 │
│  📊 See Figure: Distribution of ALT in healthy adults            │
│  ┌─────────────────────────────────────────────┐               │
│  │         ▁▃▅▇█▇▅▃▁                           │               │
│  │       10   25  40  55   70  85              │               │
│  │                ↑ Your value: 45              │               │
│  │     [Source: NHANES 2023-2024, PMID: ...]   │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
│  ⚠️ This is NOT medical advice. Please consult your doctor.     │
│  📎 7 references cited | 🕐 Search time: 1.8s                  │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  [💡 Ask follow-up] [📋 Download Report] [🔄 Switch to Simple]  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Under the Hood: 技术架构

```
用户上传体检报告 PDF + 问题 "ALT 偏高怎么办？"
         │
         ▼
┌────────────────────────────────────────────┐
│          INPUT PROCESSING LAYER            │
│                                            │
│  PDF → PyMuPDF → Text + Tables + Images    │
│  Tables → Camelot/Tabula → Structured CSV  │
│  Images → Gemini Vision → Caption + OCR    │
│                                            │
│  NER Extraction:                           │
│  {indicator: "ALT", value: 45, unit: "U/L",│
│   ref_range: "7-40", status: "High"}       │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────▼─────────────────────────┐
│          QUERY UNDERSTANDING               │
│                                            │
│  • Intent: lab_interpretation              │
│  • Entities: ALT, elevated, liver          │
│  • Query Rewrite × 3:                      │
│    ① "ALT mildly elevated causes NAFLD"    │
│    ② "alanine aminotransferase isolated    │
│        elevation management guidelines"    │
│    ③ "mild ALT elevation prognosis benign" │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────▼─────────────────────────┐
│       MULTIMODAL RETRIEVAL (FAISS)         │
│                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Text    │  │  Image   │  │  Table   │ │
│  │  Index   │  │  Index   │  │  Index   │ │
│  │  → Top 5 │  │  → Top 3 │  │  → Top 3 │ │
│  │ (Abstract│  │ (ALT     │  │ (ALT     │ │
│  │  chunks) │  │  distribution │ ref range│ │
│  │          │  │  figures)│  │ tables)  │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       └──────────────┼─────────────┘       │
│                      ▼                     │
│            Adaptive Re-ranking             │
│     (by recency × authority × relevance)   │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────▼─────────────────────────┐
│      EVIDENCE-GROUNDED GENERATION          │
│                                            │
│  System Prompt:                            │
│  "You are a medical knowledge assistant.   │
│   EVERY factual claim MUST cite a PMID.    │
│   Express uncertainty where evidence is    │
│   mixed. Use plain language by default."   │
│                                            │
│  Generation → NLI Verification Loop:       │
│  ┌────────────────────────────────────┐    │
│  │ For each claim in response:        │    │
│  │  Can it be entailed from retrieved │    │
│  │  literature?                       │    │
│  │  ├─ YES → Keep, attach PMID        │    │
│  │  ├─ PARTIAL → Add uncertainty      │    │
│  │  └─ NO → Remove or flag ⚠️         │    │
│  └────────────────────────────────────┘    │
│                                            │
│  Readability Adaptation:                   │
│  • "Doctor Mode": full medical terminology │
│  • "Simple Mode": 6th grade reading level  │
└──────────────────┬─────────────────────────┘
                   │
                   ▼
         ┌────────────────────┐
         │  Response + Sources │
         │  with Citations     │
         └────────────────────┘
```

### 4.3 Why It's Better: 关键差异化

| | ChatGPT / 通用 AI | WebMD / 丁香医生 | **MediLens** |
|------|:---:|:---:|:---:|
| **引用来源** | ❌ 无 | ❌ 无 | ✅ 每条声明附 PMID |
| **最新研究** | ❌ 截止到训练日期 | ❌ 静态内容 | ✅ 实时检索最新文献 |
| **多模态输入** | ⚠️ 部分支持 (图片) | ❌ 纯文本 | ✅ PDF + 图片 + 表格 |
| **个性化** | ⚠️ 基于对话记忆 | ❌ 通用内容 | ✅ 基于你上传的报告 |
| **幻觉控制** | ❌ 无 | ✅ 人工编辑 (但慢) | ✅ 自动 NLI 验证 |
| **可及性** | ✅ 免费/便宜 | ✅ 免费 | ✅ 免费增值 |
| **可读性选择** | ⚠️ 可要求 | ❌ 固定 | ✅ Doctor / Simple 双模式 |

### 4.4 Demo Scenario (Week 12 演示剧本)

```
⏱ 3 分钟演示流程:

[00:00-00:30] Hook + Upload
   → 演示者: "昨天我收到了体检报告，ALT 偏高。
     我在 Google 上搜了一个小时，越搜越焦虑。"
   → 上传 PDF: physical_report_2026.pdf
   → 系统自动提取 18 项指标，高亮异常值

[00:30-01:30] 核心解读
   → 演示者: "ALT 45 U/L 意味着什么？"
   → MediLens: 展示解读 —
     • 5 个相关文献引用
     • 正常人群 ALT 分布图 (来自 NHANES)
     • 孤立轻度升高的预后数据
     • AASLD 2025 指南建议
   → 🔑 每个声明后都有蓝色 [PMID] 链接

[01:30-02:30] 多模态能力
   → 演示者: 上传一张手写化验单照片 (模拟)
   → MediLens: OCR → 结构提取 → 检索 → 对比
   → "与你的电子版报告一致，AST/ALT 比值 0.67"

[02:30-03:00] Trust + Close
   → 演示者切换到 Simple Mode
   → "同样的答案，用更通俗的语言 — 每条信息依然有引用"
   → 🎤 "MediLens — 让每一次健康搜索，都有据可依。"

⏱ 结束。
```

---

## Slide 5 — Thank You

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║                                                              ║
║                      Thank You                               ║
║                                                              ║
║                    Questions?                                ║
║                                                              ║
║                                                              ║
║      MediLens: Every health question deserves                ║
║                an evidence-grounded answer.                  ║
║                                                              ║
║                                                              ║
║         Contact: [Team Lead Name]                            ║
║         Email:    [xxx@student.uts.edu.au]                   ║
║         GitHub:   [github.com/your-team/medilens]            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Slide 6 — The Team

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║                     The Team                                 ║
║                                                              ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    ║
║  │          │  │          │  │          │  │          │    ║
║  │ [Photo]  │  │ [Photo]  │  │ [Photo]  │  │ [Photo]  │    ║
║  │          │  │          │  │          │  │          │    ║
║  │ [Name]   │  │ [Name]   │  │ [Name]   │  │ [Name]   │    ║
║  │ Tech     │  │ Backend  │  │ Frontend │  │ Medical  │    ║
║  │ Lead     │  │ + Search │  │ + UX     │  │ Advisor  │    ║
║  │          │  │          │  │          │  │          │    ║
║  │ RAG/NLP  │  │ Python   │  │ Next.js  │  │ PubMed   │    ║
║  │ LangChain│  │ FAISS    │  │ Tailwind │  │ Research │    ║
║  └──────────┘  └──────────┘  └──────────┘  └──────────┘    ║
║                                                              ║
║  ┌──────────┐  ┌──────────┐                                 ║
║  │          │  │          │                                 ║
║  │ [Photo]  │  │ [Photo]  │                                 ║
║  │          │  │          │                                 ║
║  │ [Name]   │  │ [Name]   │                                 ║
║  │ Document │  │ Product  │                                 ║
║  │ Pipeline │  │ + Pitch   │                                 ║
║  │          │  │          │                                 ║
║  │ PDF/OCR  │  │ Research │                                 ║
║  │ PyMuPDF  │  │ Design   │                                 ║
║  └──────────┘  └──────────┘                                 ║
║                                                              ║
║  Skills we cover: NLP/IR · Python · FastAPI · LangChain     ║
║  FAISS · PyMuPDF · Next.js · PubMed E-utilities · UX Design  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 附录: Pitch 演讲要点备忘

### 3 分钟演讲节奏

| 时间 | 内容 | 要点 |
|------|------|------|
| 0:00-0:30 | Hook | "昨天我拿到体检报告，ALT 偏高 — Google 了一个小时，越搜越焦虑。如果有一个工具能给我基于真实文献的答案呢？" |
| 0:30-1:00 | Problem + Market | 每年 400 万篇新论文，ChatGPT 不引用来源 — 医学信息领域存在"信任真空" |
| 1:00-1:30 | Gap | UpToDate $500/年给医生用，ChatGPT 免费但不可信 — 中间的地带谁来填？ |
| 1:30-2:30 | Solution Demo | Live demo — 上传报告 → 结构化提取 → 检索 500 篇文献 → 生成带引用的解读 |
| 2:30-3:00 | Close + Ask | "每一次健康搜索，都值得一个有据可依的答案" |

### Key Messages 必须重复 3 次

1. **"ChatGPT 可以回答医学问题，但它不告诉你答案从哪里来 — MediLens 每条声明都附带可验证的引用"**
2. **"3700 万篇医学文献 — 我们用多模态 RAG 让你用自然语言就能检索和理解"**
3. **"不是替代医生，是让你带着更好的问题去见医生"**

### ⚠️ 需要注意的「敏感地带」

| 话题 | 如何处理 |
|------|----------|
| 医疗责任 | 明确声明"这不是医疗建议"，每个回复都附带免责声明 |
| 诊断 vs 解读 | 我们做"信息检索 + 知识综合"，不做诊断 |
| 药物推荐 | 不推荐具体药物/剂量，只引用指南中的通用建议 |
| 紧急情况 | 检测到紧急关键词（胸痛、呼吸困难...）→ 提示"请立即就医" |
