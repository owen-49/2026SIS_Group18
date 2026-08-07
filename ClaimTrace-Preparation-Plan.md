# ClaimTrace — 前期准备计划

> 项目: ClaimTrace (学术文献引用上下文验证工具)  
> 团队: 7 人 (3 Pair + 1 Solo)  
> 学期: 2026 Spring, Week 1-12  
> 关键日期: A1 Pitch 20 Aug | A4 Demo 22 Oct  

---

## 目录

1. [总览: 12 周节奏](#一总览-12-周节奏)
2. [Phase 0: 团队启动 (W1)](#二phase-0-团队启动)
3. [Phase 1: 技术验证 (W1-W2)](#三phase-1-技术验证-spike)
4. [Phase 2: 用户研究 (W1-W3)](#四phase-2-用户研究)
5. [Phase 3: 竞品深潜 (W2-W3)](#五phase-3-竞品深潜)
6. [Phase 4: 基础设施搭建 (W1-W2)](#六phase-4-基础设施搭建)
7. [Phase 5: Pitch 准备 (W2-W3)](#七phase-5-pitch-准备)
8. [风险登记表](#八风险登记表)
9. [W1-W3 任务看板](#九w1-w3-任务看板)

---

## 一、总览: 12 周节奏

```
W1         W2         W3         W4 ────────── W10 ──── W11 ── W12
│          │          │          │               │        │      │
│ 准备期   │ 准备期   │ 过渡     │  Sprint 执行   │ 收尾   │ Demo │
│          │          │          │               │        │      │
├──────────┼──────────┼──────────┤               │        │      │
│          │          │          │               │        │      │
│ ● Spike  │ ● Pitch  │ ● 架构   │  W4-W10:      │ ● A4视频│ ● Demo│
│ ● 用户   │   制作    │   定稿   │  每两周一个    │   录制  │   Day │
│   研究   │ ● 竞品   │ ● Sprint │  可交付增量    │ ● 用户  │       │
│ ● 基础   │   分析   │   Kickoff│               │   测试  │       │
│   设施   │          │          │               │        │       │
│          │          │          │               │        │       │
│ ▲ A1 Pitch Due: 20 Aug              ▲ A4 Due: 22 Oct          │
│    (W3 周五)                            (W11 周三)              │
└──────────────────────────────────────────────────────────────────┘
```

**核心理念**: W1-W3 不做产品功能开发。这三周只做三件事 — **证明技术可行、确认用户真实、搭好工程地基**。

---

## 二、Phase 0: 团队启动

> 时间: W1 第一天 workshop  
> 负责人: 全员 + Product Lead 主持  
> 产出: Team Charter 一页纸

### 2.1 启动会议议程 (60 min)

| 时间 | 议题 | 具体内容 |
|------|------|----------|
| 0-10 min | 项目共识 | 全员大声朗读 ClaimTrace 的 one-pager，确认每个人都理解并认同项目方向 |
| 10-25 min | 角色确认 | 宣读 Pair 分工草案，每个人表态第一志愿和第二志愿 |
| 25-40 min | 工作协议 | 讨论并达成一致: 每周投入时间期望、代码审查规则、沟通渠道、决策机制 |
| 40-55 min | 恐惧与希望 | 每人写一张 post-it: 最担心什么 + 最期待什么。贴在共享白板上。 |
| 55-60 min | 下一步 | 确认本周每个人的行动项 |

### 2.2 Team Charter 模板

```markdown
# ClaimTrace Team Charter

## 团队身份
- 队名: [待定]
- 成员: [7 人姓名 + 角色]
- 项目: ClaimTrace — Academic Citation Audit Engine

## 工作协议
- 每人每周投入: [X] 小时 (含 workshop)
- 代码审查: 所有 PR 至少 1 人 approve 才能合并
- 沟通: MS Teams (正式) + Discord (日常)
- 决策: 技术决策由 Pair Lead 做，方向决策全员投票

## 会议节奏
- 周一全员 standup: 15 min
- 周四跨-Pair 对齐: 20 min  
- 周五 Sprint Review: 45 min

## 我们的成功标准 (12 周后)
1. 至少 3 个真人在 W10 前用过 ClaimTrace
2. Demo 视频让一个非技术观众 2 分钟内理解产品的价值
3. 团队每个人都说: "这个项目让我学到了我本专业学不到的东西"

## 恐惧清单 (W1)
- [成员 A]: 最担心 ______
- [成员 B]: 最担心 ______
- ...
```

### 2.3 角色分配流程

```
Step 1 (W1 周一): 每人匿名提交 1st + 2nd 志愿
  Pair 1 (Document Intel): 需要 — 对底层工程有兴趣、耐心、细节导向
  Pair 2 (Semantic Engine): 需要 — NLP/ML 经验、对 LLM 有关注
  Pair 3 (Application): 需要 — Web 开发经验、对 UI/UX 有感觉
  Solo  (Product): 需要 — 沟通强、对研究流程有经验、愿意做非代码工作

Step 2 (W1 周二): 全员讨论 + 最终确认
  → 原则: 如果两个人抢同一个角色，让他们各自说 1 分钟 why，其他 5 人投票

Step 3 (W1 周三): 角色锁定
  → 写入 Team Charter，存入 GitHub README
```

---

## 三、Phase 1: 技术验证 (Spike)

> 时间: W1-W2  
> 负责人: Pair 1 + Pair 2 (并行)  
> 产出: Spike 报告 (Go / No-Go 决策)

### 3.1 最危险假设

ClaimTrace 有三个危险假设。按照「如果不成立整个产品就死了」的致命度排序:

```
致命度 🔴🔴🔴
  H1: RAG 技术能在双栏 PDF 中准确提取出对应的段落
       (如果召回率 < 60% → 产品不可行)

致命度 🔴🔴
  H2: LLM 对「claim 是否被原文支撑」的 entailment 判断足够准确
       (如果准确率 < 70% → 用户不信任，产品无用)

致命度 🔴
  H3: Overleaf DOM 结构允许稳定注入 hover popup
       (如果不行 → 用 Web Dashboard 替代，产品仍可用)
```

### 3.2 Spike 1: PDF 解析 + 语义检索可行性 (Pair 1 + Pair 2-A)

**目标**: 证明 H1 — 我们能从真实学术 PDF 中找到 claim 对应的原文段落。

**输入**:
- 5 篇已发表的 CS 论文 PDF（覆盖 3 种格式：双栏 IEEE、单栏 NeurIPS、带公式的 ICLR）
- 20 个已知 ground truth 的 claim-passage 对（人工标注: 哪句 claim 引用的是哪篇论文的哪段话）

**方法**:

```python
# Spike 脚本骨架
import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# === Pair 1: PDF Parser ===
def parse_pdf(pdf_path):
    """提取文本 + 恢复段落边界"""
    doc = fitz.open(pdf_path)
    paragraphs = []
    for page in doc:
        blocks = page.get_text("blocks")
        # Challenge: 双栏排序 ← key risk
        paragraphs.extend(reorder_blocks_2col(blocks))
    return paragraphs

# === Pair 2-A: Retriever ===
model = SentenceTransformer('all-MiniLM-L6-v2')

def build_index(paragraphs):
    embeddings = model.encode(paragraphs)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index, embeddings

def retrieve(claim, index, paragraphs, k=5):
    query_emb = model.encode([claim])
    scores, indices = index.search(query_emb, k)
    return [(paragraphs[i], scores[0][j]) for j, i in enumerate(indices[0])]

# === Evaluation ===
def evaluate(test_pairs):
    """test_pairs: list of (claim, ground_truth_passage)"""
    recall_at_5 = 0
    for claim, gt in test_pairs:
        results = retrieve(claim, index, paragraphs, k=5)
        if any(gt in r[0] for r in results):
            recall_at_5 += 1
    return recall_at_5 / len(test_pairs)
```

**评估指标**:

| 指标 | 定义 | Go 阈值 | No-Go 阈值 |
|------|------|---------|------------|
| Recall@5 | Top-5 段落中包含 ground truth 的比例 | ≥ 0.80 | < 0.50 |
| Recall@1 | Top-1 段落就是正确答案的比例 | ≥ 0.50 | < 0.25 |
| Parse Accuracy | PDF 提取的段落边界与手动标注一致的比例 | ≥ 0.80 | < 0.50 |

**执行计划**:

| 时间 | 谁 | 做什么 |
|------|-----|--------|
| W1 周一-二 | Pair 1 | 收集 5 篇测试 PDF + 写 baseline parser |
| W1 周三-四 | Pair 2-A | 建 embedding index + 写 baseline retriever |
| W1 周五 | Pair 1+2 | 一起标注 ground truth (每人标注 10 对，半天集中标注) |
| W2 周一 | Pair 2-A | 跑评估，出第一版数字 |
| W2 周三 | Pair 1+2 | 错误分析: 哪些 case 失败了？为什么？ |
| W2 周五 | Pair 1+2 | 提交 Spike Report: Go / No-Go with evidence |

### 3.3 Spike 2: Entailment 判定准确率 (Pair 2-B)

**目标**: 证明 H2 — LLM 能可靠判断 claim 是否被原文支撑。

**输入**:
- 50 个 claim-passage 对（人工标注 label: Support / Partial / Contradict / Not Found）
- 直接用 GPT-4o / Gemini / Claude API

**Prompt 设计**:

```python
ENTAILMENT_PROMPT = """You are a citation verification assistant. 
Your job is to determine whether a claim made in an academic paper 
is supported by the source text it cites.

SOURCE TEXT (from the cited paper):
\"\"\"
{source_passage}
\"\"\"

CLAIM (from the paper being audited):
\"\"\"
{claim}
\"\"\"

Classify the relationship as ONE of:
- SUPPORT: The source text directly supports the claim. The claim is an 
  accurate representation of what the source says.
- PARTIAL: The source text partially supports the claim, but the claim 
  overstates, overgeneralizes, or omits important caveats.
- CONTRADICT: The source text contradicts or disagrees with the claim.
- NOT_FOUND: The claim's content is not addressed in the source text.

Respond in JSON: {"label": "...", "rationale": "..."}
"""
```

**评估指标**:

| 指标 | 定义 | Go 阈值 |
|------|------|---------|
| Accuracy (4-class) | 正确分类比例 | ≥ 0.80 |
| F1 (Support vs Rest) | Support 类别的 F1 | ≥ 0.85 |
| Cohen's Kappa | 与人工标注的一致性 | ≥ 0.70 |

**执行计划**:

| 时间 | 谁 | 做什么 |
|------|-----|--------|
| W1 周四-五 | Pair 2-B | 准备 50 个 claim-passage 对, 3 人分别标注, 用 majority vote 确定 ground truth |
| W2 周一 | Pair 2-B | 跑 GPT-4o + Gemini + Claude 三个模型各一遍 |
| W2 周三 | Pair 2-B | 计算准确率 + 错误分析 + 模型对比 |
| W2 周五 | Pair 2-B | 提交 Spike Report: 选哪个模型 + 准确率证据 |

### 3.4 Spike 3: Overleaf DOM 可行性 (Pair 3-B)

**目标**: 证明 H3 — 能在 Overleaf 编辑器中注入 UI。

**调查清单**:

```
□ Overleaf 编辑器 DOM 结构分析
  → \cite{...} 是如何渲染的？有稳定的 CSS class 吗？
  → 编辑器内容在哪个 element 下？

□ Hover 事件捕获
  → 能否在 \cite{...} span 上注册 mouseenter 事件？
  → 协作模式下 DOM 会频繁刷新吗？如何应对？

□ Popup 注入策略
  → 直接注入 Overleaf 页面 DOM？
  → 还是用独立的 Chrome Extension popup window？

□ 鉴权
  → Extension 能复用 Overleaf 的登录态吗？
  → 我们的 API 如何验证请求来自合法用户？

□ Overleaf 更新频率
  → 查 Overleaf changelog: 过去一年前端改了多少次？
  → 如果 Overleaf 大改版，我们的注入逻辑多久需要适配？
```

**输出**: 一份「DOM 分析报告」+ 一个能捕获 hover 事件并打印 console.log 的最简 extension。

---

## 四、Phase 2: 用户研究

> 时间: W1-W3  
> 负责人: Product Lead  
> 产出: 用户研究报告 + Persona + 5 User Stories

### 4.1 访谈计划

**目标**: 深度访谈 5 位近期向顶会投过论文的博士生或研究员。

**招募策略**:
```
来源 1: 课程内的同学 (其他团队) — "你有投过论文吗？"
来源 2: 王老师实验室的博士生 — 通过 Coordinator 介绍
来源 3: UTS CS PhD Slack / 微信群 — 发一个礼貌的邀请
来源 4: 你们团队自己 — 至少做 3 次自我访谈 (记录自己验证引用的过程)
```

**访谈提纲** (30 min):

```
Part 1: 背景 (5 min)
  - 你最近一次投稿是什么会？你主要负责论文的哪些部分？
  - 论文有多少引用？你的合作者通常怎么分工写论文？

Part 2: 引用验证现状 (10 min)
  - 你在交稿前会专门验证合作者引用的文献吗？怎么做的？
  - 带我走一遍流程: 从发现一个可疑引用到确认它有没有问题
  - 你遇到过的最糟糕的引用错误是什么？怎么发现的？

Part 3: 工具使用 (5 min)
  - 在这个流程中你用了哪些工具？Zotero？Google Scholar？Ctrl+F？
  - 这些工具你最不满意的 3 个点是什么？

Part 4: 概念验证 (5 min)
  - [展示 ClaimTrace 的 mockup 截图]
  - 如果 Overleaf 里 hover 引用就能看到原文字段，你觉得有用吗？
  - 你最担心什么功能做不好？（负向问题 — 获取真实顾虑）

Part 5: 定价 / 使用意愿 (5 min)
  - 如果这个工具存在，你下次投稿会用它吗？
  - 你觉得它会是你工作流里的「必需品」还是「锦上添花」？
```

### 4.2 访谈输出格式

每场访谈后，24 小时内整理成 1 页笔记:

```markdown
## 用户访谈 #N: [代号]
- 日期: 
- 角色: 第 N 年 PhD / 导师 / 博士后
- 投稿经验: [最近投的会议/期刊]

### 关键引用
> "..."

### 痛点 (Top 3)
1. ...
2. ...
3. ...

### 对 ClaimTrace 的反应
- 最吸引的点: ...
- 最大的顾虑: ...

### 我们之前不知道的事
- ...
```

### 4.3 综合输出: 用户画像 + 核心 User Stories

5 场访谈完成后，Product Lead 提炼为:

```
Persona 1: 焦虑的博士生 Xiaowei
  → "我还有三天截稿，合作者写的 Related Work 我还没来得及验证"
  → 核心需求: 速度、批量审计、不打断写作流

Persona 2: 审稿人 / 导师 Dr. Chen
  → "我需要快速判断这篇投稿的引用是否诚实"
  → 核心需求: 高亮可疑引用、证据截图

5 Core User Stories:
  1. As a PhD student, I want to hover \cite{...} and see 
     the original text so that I don't have to leave Overleaf.
  2. As a co-author, I want to batch-audit all citations 
     before submission so that I don't miss any errors.
  3. ...
```

---

## 五、Phase 3: 竞品深潜

> 时间: W2-W3  
> 负责人: Product Lead  
> 产出: 竞品矩阵 + 差异化定位陈述

### 5.1 需要深潜的产品

每个竞品，实际操作 30 分钟，回答以下问题:

| 竞品 | 深潜方向 |
|------|----------|
| **scite.ai** | 它的 Smart Citation 是怎么判断 Support/Mention/Contradict 的？准确率如何？有 API 吗？ |
| **Semantic Scholar** | TLDR 摘要怎么生成的？引用上下文提取 (Citation Context Extraction) 是怎么做的？ |
| **Elicit** | 它的文献发现和引用验证有什么区别？用户评价如何？ |
| **Zotero** | Zotero 7 有什么新功能？Overleaf 集成到了什么程度？ |
| **ChatGPT / Claude** | 测试: "帮我验证这段引用是否准确" — 它的回答可靠吗？幻觉率多高？ |
| **Perplexity** | 它对学术文献的检索能力比 Google Scholar 强在哪？ |

### 5.2 竞品矩阵模板

| 维度 | ClaimTrace | scite.ai | S2 | Elicit | Zotero | ChatGPT |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 逐句引用验证 | ✅ | ⚠️ 宏观 | ❌ | ❌ | ❌ | ❌ |
| Overleaf 集成 | ✅ | ❌ | ❌ | ❌ | ⚠️ 部分 | ❌ |
| Semantic Match | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ |
| Hallucination-Free | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| 开源 / 可自部署 | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |

### 5.3 差异化定位陈述

> ClaimTrace 是唯一一个嵌入 Overleaf 写作流的引用验证工具。  
> 不像 scite.ai 告诉你「这篇论文被引了多少次」，  
> 不像 ChatGPT 替你「编一个看似合理的答案」，  
> ClaimTrace 做一件更小、更确定的事 —  
> **把你论文里的 claim 和它引用的原文，逐句对齐。**

---

## 六、Phase 4: 基础设施搭建

> 时间: W1-W2  
> 负责人: Pair 3-A (Backend) + Pair 3-B (Frontend)  
> 产出: 能跑的 CI/CD + 空壳 App

### 6.1 代码仓库结构

```
claimtrace/
├── README.md
├── docs/
│   ├── team-charter.md
│   ├── architecture.md
│   ├── spike-reports/
│   └── user-research/
├── parser/              # Pair 1: Document Intelligence
│   ├── pyproject.toml
│   ├── src/
│   │   ├── pdf_parser.py
│   │   ├── element_extractor.py
│   │   └── reference_extractor.py
│   └── tests/
│       └── test_data/   # 测试用 PDF
├── engine/              # Pair 2: Semantic Engine
│   ├── pyproject.toml
│   ├── src/
│   │   ├── retriever.py
│   │   ├── verifier.py
│   │   └── embedder.py
│   └── tests/
│       └── benchmarks/  # 50 claim-passage pairs
├── backend/             # Pair 3-A: API Server
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py      # FastAPI app
│   │   ├── routes/
│   │   ├── services/    # 调用 parser + engine
│   │   └── models/
│   └── tests/
├── frontend/            # Pair 3-B: Web Dashboard
│   ├── package.json
│   └── src/
└── extension/           # Pair 3-B: Chrome Extension
    ├── manifest.json
    └── src/
```

### 6.2 CI/CD 搭建清单

```
□ GitHub Repo 创建 + 7 人全部加入
□ Branch 保护规则:
  → main: 需要 1 个 approve + CI 通过
  → 每个 Pair 有自己的 dev branch
□ GitHub Actions:
  → Parser: pytest + coverage report
  → Engine: pytest + benchmark regression (准确率不能下降)
  → Backend: pytest + lint (ruff)
  → Frontend: lint (eslint) + build
□ Pre-commit hooks:
  → ruff (Python)
  → prettier (JS/TS)
□ Docker Compose (dev):
  → backend + frontend + FAISS 一键启动
□ 环境变量管理: .env.example (API keys 不提交)
```

### 6.3 W2 结束时应该有什么

```
✅ 7 个人都能 git clone + docker compose up → 看到 Hello World
✅ Parser 的 CI 在每次 push 时自动跑 pytest
✅ Engine 的 benchmark 结果自动记录 (accuracy 趋势线)
✅ 每个人至少 merge 过一个 PR
```

---

## 七、Phase 5: Pitch 准备

> 时间: W2-W3  
> 截止: 8 月 20 日 (Slides) | 8 月 21 日 (Presentation)  
> 负责人: Product Lead (主) + 全员 (审阅)

### 7.1 Pitch Deck 制作时间线

| 日期 | 里程碑 | 负责人 |
|------|--------|--------|
| W2 周一 (8/10) | Slides 大纲 V1 (基于本文件的 Pitch) | Product Lead |
| W2 周三 (8/12) | 补充 Spike 结果 + 用户访谈引用 | Pair 1, Pair 2, Product |
| W2 周五 (8/14) | Slides V1 内部审阅 (全员 30 min) | 全员 |
| W3 周一 (8/17) | Slides V2 + Demo 脚本 V1 | Product Lead |
| W3 周三 (8/19) | 预演 (Dry Run) — 全员 + 计时 | 全员 |
| W3 周四 (8/20) | **Slides 提交** | Product Lead |
| W3 周五 (8/21) | **课堂 Presentation** | 指定 1-2 位演讲者 |

### 7.2 Pitch 分工

| Slide | 内容来源 | 制作 |
|-------|----------|------|
| 封面 + Tagline | 团队讨论 | Product Lead |
| Problem + Pain Points | 用户访谈 | Product Lead |
| Market + 竞品 | 竞品深潜 | Product Lead |
| Solution + Demo | Spike 结果 + 真实 demo | Pair 3-B (录制), Product Lead (脚本) |
| Team | Team Charter | Product Lead |

### 7.3 Demo 准备

Pitch 里的 Demo 不需要是真产品，但必须是**真实运行**的（不是 PPT 动画）。

```
Demo 方案:
  → 录一个 60 秒的视频 (避免现场网络问题)
  → 用真实的论文 PDF + 真实的 claim
  → 展示: PDF 上传 → 解析 → hover \cite{...} → popup 显示结果
  → 如果 Extension 没做好 → 用 Web Dashboard 录屏 (更可控)

备用方案:
  → 如果 Spike 结果不理想 → 展示最乐观的 case + 坦诚说明当前局限
  → "This is a work in progress, and here's what we've proven is possible"
```

---

## 八、风险登记表

> 在 W1 创建，每周 Sprint Review 更新状态

| ID | 风险 | 影响 | 概率 | 缓解措施 | 触发信号 | 负责人 |
|----|------|:---:|:---:|----------|----------|--------|
| R1 | PDF 双栏解析准确率 < 60% | 🔴 Block | 中 | Spike W1-W2 就测；先用 arXiv LaTeX source 作为 fallback | Spike W2 Recall < 0.5 | Pair 1 |
| R2 | LLM entailment 准确率 < 70% | 🔴 Block | 低 | 多模型对比；few-shot prompt 调优；缩小 scope 到 well-defined claims | Spike W2 Accuracy < 0.7 | Pair 2-B |
| R3 | Overleaf 改版破坏 DOM 注入 | 🟡 Delay | 中 | Extension 不强依赖 DOM — fallback 到独立 Dashboard | Overleaf changelog 有 breaking change | Pair 3-B |
| R4 | 用户表示「不需要」 | 🔴 Pivot | 低 | W1-W3 密集访谈，如果信号不对及时 pivot | 3/5 访谈说 not essential | Product |
| R5 | 团队技能不匹配 | 🟡 Delay | 中 | Pair 分配前做 skills inventory；文档化关键决策 | W2 结束时某 Pair 无交付 | Product |
| R6 | LLM API 费用超预算 | 🟡 Cost | 低 | 用开源 embedding（all-MiniLM）；caching 减少重复调用；Gemini Flash 做 entailment | 月度账单 > $50 | Pair 2 |
| R7 | 7 人协作 Git 冲突频繁 | 🟡 Delay | 中 | Monorepo + Pair-level branches + CI gate | 每天 > 2 次合并冲突 | Pair 3-A |

---

## 九、W1-W3 任务看板

### W1: 启动 + Spike 启动 (7 月 31 日 - 8 月 6 日)

| # | 任务 | 负责人 | 状态 |
|---|------|--------|:---:|
| T1 | 团队启动会议 + Team Charter | Product + 全员 | ☐ |
| T2 | 角色分配确认 | Product | ☐ |
| T3 | GitHub Repo 创建 + 7 人加入 | Pair 3-A | ☐ |
| T4 | CI/CD 搭建 (lint + test) | Pair 3-A | ☐ |
| T5 | 收集 5 篇测试 PDF (3 种格式) | Pair 1 | ☐ |
| T6 | Baseline PDF Parser (PyMuPDF) | Pair 1 | ☐ |
| T7 | 50 claim-passage pair 标注开始 | Pair 2-B + Product | ☐ |
| T8 | Baseline Embedding + FAISS Index | Pair 2-A | ☐ |
| T9 | Overleaf DOM 初步调查 | Pair 3-B | ☐ |
| T10 | 用户访谈 #1, #2 | Product | ☐ |
| T11 | Team Charter 写入 GitHub README | Product | ☐ |

### W2: Spike 完成 + Pitch 启动 (8 月 7 日 - 8 月 13 日)

| # | 任务 | 负责人 | 状态 |
|---|------|--------|:---:|
| T12 | Spike 1 评估: PDF Recall@5 | Pair 1 + 2-A | ☐ |
| T13 | Spike 2 评估: Entailment Accuracy | Pair 2-B | ☐ |
| T14 | Spike Report 提交 (Go/No-Go) | Pair 1 + Pair 2 | ☐ |
| T15 | Overleaf Extension 最简原型 (console.log hover) | Pair 3-B | ☐ |
| T16 | FastAPI 骨架 + Mock API | Pair 3-A | ☐ |
| T17 | Web Dashboard 骨架 (React + Mock) | Pair 3-B | ☐ |
| T18 | 用户访谈 #3, #4, #5 | Product | ☐ |
| T19 | 竞品深潜 (scite.ai, S2, Elicit) | Product | ☐ |
| T20 | Pitch Slides 大纲 V1 | Product | ☐ |
| T21 | Docker Compose dev 环境可用 | Pair 3-A | ☐ |

### W3: Pitch 完成 + Sprint Kickoff (8 月 14 日 - 8 月 21 日)

| # | 任务 | 负责人 | 状态 |
|---|------|--------|:---:|
| T22 | 用户研究报告 (5 场访谈综合) | Product | ☐ |
| T23 | Persona + 5 User Stories | Product | ☐ |
| T24 | 竞品矩阵 + 差异化陈述 | Product | ☐ |
| T25 | Pitch Slides V1 → 内部审阅 | Product + 全员 | ☐ |
| T26 | Pitch Slides V2 → 最终版 | Product | ☐ |
| T27 | Pitch 预演 (Dry Run + 计时) | 全员 | ☐ |
| T28 | Demo 视频录制 (如果 Spike 成功) | Pair 3-B | ☐ |
| T29 | **A1 Pitch Slides 提交 (8/20)** | Product | ☐ |
| T30 | **A1 Pitch 课堂 Presentation (8/21)** | 指定演讲者 | ☐ |
| T31 | Sprint 1 架构设计文档定稿 | Pair 1 + Pair 2 | ☐ |
| T32 | Sprint 1 Kickoff + Backlog grooming | Product + 全员 | ☐ |

---

## 附录 A: Skills Inventory 模板

> W1 每位成员填写，帮助 Product Lead 做 Pair 分配

```markdown
## Skills Inventory: [Name]

### 编程语言 (1-5: 1=Hello World, 5=可以教别人)
- Python: [ ]
- JavaScript/TypeScript: [ ]
- Other: [ ]

### 技术与框架 (1-5)
- NLP / Information Retrieval: [ ]
- LLM / Prompt Engineering: [ ]
- PDF / Document Processing: [ ]
- Web Backend (FastAPI/Flask/Django): [ ]
- Web Frontend (React/Vue/Next.js): [ ]
- Browser Extension: [ ]
- Docker / CI/CD: [ ]

### 软技能 (1-5)
- 用户访谈 / User Research: [ ]
- UI/UX 设计 (Figma): [ ]
- 技术写作 / 文档: [ ]
- Presentation / Pitch: [ ]
- 项目管理 / 组织: [ ]

### 志愿 (第一志愿 + 第二志愿)
1st: [ ]  (Pair 1 Doc Intel / Pair 2 Semantic / Pair 3 App / Solo Product)
2nd: [ ]  (Pair 1 Doc Intel / Pair 2 Semantic / Pair 3 App / Solo Product)

### 我最想从这个项目学到什么？
...

### 我最大的担心？
...
```

---

## 附录 B: W1-W3 会议日历

```
W1 周五 (Aug 1)
  Workshop 11:00-14:00
  ├── 11:00-12:00: 团队启动会议 (全员)
  ├── 12:00-13:00: 技术讨论 + 角色分配
  └── 13:00-14:00: 开始 Pair 工作

W2 周五 (Aug 8)
  Workshop 11:00-14:00
  ├── 11:00-11:30: Spike 进展汇报 (Pair 1 + 2)
  ├── 11:30-12:30: 用户研究分享 (Product)
  └── 12:30-14:00: Pair 独立工作

  周四 23:59: Weekly Journal #1 (Individual)

W3 周五 (Aug 15)
  Workshop 11:00-14:00
  ├── 11:00-11:45: Pitch 预演 (全员)
  ├── 11:45-12:30: 反馈 + 修改
  └── 12:30-14:00: Sprint 1 Kickoff

  周三 (Aug 20) 23:59: A1 Pitch Slides Due
  周四 (Aug 21): A1 In-Class Presentation
  周四 23:59: Weekly Journal #2 (Individual)
```

---

> **一句话总结**: W1-W3 不写产品代码。做三件事 — 证明能做 (Spike)、确认该做 (User Research)、搭好地基 (Infra)。W4 Sprint 1 从干净的起跑线出发。
