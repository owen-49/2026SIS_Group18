# ClaimTrace — Jira 项目管理完整指南

> 团队: 7 人 (Engine 4 / Backend 2 / Frontend 1)  
> 周期: 12 周 (W1-W3 准备 → W4-W9 Sprint → W10-W12 收尾)  
> 工具: Jira Software (Free tier, 最多 10 人)

---

## 目录

1. [项目创建与基础设置](#一项目创建)
2. [Issue 层级设计](#二issue-层级设计)
3. [工作流设计](#三工作流设计)
4. [Board 与 Sprint 配置](#四board-与-sprint-配置)
5. [Component 与 Label 体系](#五component-与-label-体系)
6. [每周操作节奏](#六每周操作节奏)
7. [各角色日常操作](#七各角色日常操作)
8. [GitHub 集成](#八github-集成)
9. [模板卡](#九模板卡)

---

## 一、项目创建

### 1.1 项目类型

```
Project type:  Scrum (不是 Kanban — 你们有固定 2 周 Sprint)
Project name:  ClaimTrace
Key:           CT (自动生成 issue key: CT-1, CT-2, ...)
Access:        Private (仅团队成员)
```

### 1.2 初始设置清单

创建项目后，按顺序做以下配置：

```
□ Settings → Features: 关闭不需要的模块
  → 关闭: Releases, Components (我们用 Label 替代)
  → 开启: Sprints, Backlog, Roadmap

□ Settings → People: 邀请 7 个成员
  → 角色: 所有人都是 Administrator (课程项目，不搞权限层级)
  → 你自己额外把自己加到 Project Lead

□ Settings → Issue types: 确认有以下类型
  → Epic, Story, Task, Sub-task, Bug (默认就有，不用改)
  → 关闭你不用的: 删掉 "新功能" 之类的中文默认类型，统一用英文

□ Settings → Screens: 简化字段
  → 关掉: "Fix Version", "Environment", 所有自定义字段
  → 保留: Summary, Description, Assignee, Story Points, Priority, Sprint, Labels
```

---

## 二、Issue 层级设计

### 2.1 四层结构

```
Epic                     "Sprint 1: Baseline Pipeline"
  │                      大的交付目标，跨 2 周，1 个队所有工作
  │
  ├── Story              "用户能上传 PDF 并获得结构化文本"
  │    │                 可演示的用户价值，通常 1-3 天完成
  │    │
  │    ├── Task          "实现 PyMuPDF 文本提取 + 位置元数据"
  │    │                 具体开发任务，半天到一天
  │    │
  │    └── Sub-task      "修复 IEEE 双栏重排序的边界情况"
  │                      极小的原子工作，几小时内完成 (可选，少用)
  │
  └── Bug                "双栏解析在 page_width < 400pt 时崩溃"
                         缺陷，不挂 Subtask，直接修
```

### 2.2 什么时候用什么

| 类型 | 由谁创建 | 粒度 | 例子 |
|------|----------|------|------|
| **Epic** | Tech Lead (你) | 一个 Sprint 一个队的全部工作 | "Sprint 2: Engine Quality Push" |
| **Story** | Sprint Planning 时全队讨论 | 可独立演示的用户价值 | "用户可以上传 PDF 并获得解析后的段落列表" |
| **Task** | 认领 Story 的人自己拆 | 半天到一天的开发任务 | "实现 two-column reorder 算法" |
| **Sub-task** | 需要时才拆 | 太小的东西不值得跟踪 | 一般不建，在 Task 的 Description 里打 checkbox |
| **Bug** | 任何人发现就建 | 一个具体缺陷 | "断字符修复没处理 em-dash 的情况" |

### 2.3 W4-W9 的标准 Epic 结构

```
Epic: Sprint 1 — Baseline Pipeline (W4-W5)
  │
  ├── Story: PDF → Structured Text
  │   ├── Task: Implement PyMuPDF text extraction pipeline
  │   ├── Task: Implement two-column reorder algorithm
  │   ├── Task: Implement hyphenation repair
  │   └── Task: Write unit tests + evaluation script
  │
  ├── Story: Embedding + FAISS Search
  │   ├── Task: Set up sentence-transformers with all-MiniLM
  │   ├── Task: Implement paragraph-level FAISS index builder
  │   └── Task: Implement two-stage retrieval (paragraph → sentence)
  │
  ├── Story: Verifier Pipeline
  │   ├── Task: Build entailment prompt template
  │   ├── Task: Wire LLM client (openai/gemini/anthropic/ollama)
  │   └── Task: Implement mock mode fallback
  │
  ├── Story: API Skeleton
  │   ├── Task: POST /api/parse endpoint
  │   └── Task: POST /api/verify endpoint (mock response)
  │
  └── Story: Frontend Upload + Verify Pages
      ├── Task: UploadPage with multi-file drag-and-drop
      └── Task: VerifyPage with claim input + result display
```

---

## 三、工作流设计

### 3.1 状态定义

```
Backlog → To Do → In Progress → In Review → Done
  ↑                                       │
  └───────────────────────────────────────┘ (Reopen: 只有 Bug)
```

| 状态 | 含义 | 谁操作 | 停留时间上限 |
|------|------|--------|:---:|
| **Backlog** | 还没排进 Sprint，排队中 | Tech Lead | — |
| **To Do** | 排进当前 Sprint，还没开始 | 认领者自己 | 3 天 |
| **In Progress** | 正在做 | 认领者自己 | 3 天 |
| **In Review** | 代码已提交，等 Code Review / QA | Reviewer | 1 天 |
| **Done** | 已合并到 main + 验证通过 | Jira 自动 (见下文) | — |

### 3.2 状态转换规则

```
Backlog → To Do:          Sprint Planning 时操作
To Do → In Progress:      开发者开始干活时自己拖
In Progress → In Review:  开发者提 PR 后自己拖
In Review → Done:         PR merged + 在 staging 上验证通过
In Review → In Progress:  Review 发现问题，打回去改
Done → To Do:             只有 Bug — 修复被 revert 了，重新修
```

### 3.3 一个 Task 的生命周期

```
周一 Sprint Planning
  → Task 从 Backlog 拖到 To Do
  → Assign 给具体的人
  → Estimate Story Points (1, 2, 3, 5, 8)

周二上午
  → 开发者把 Task 从 To Do 拖到 In Progress
  → 开始写代码

周三下午
  → 代码写完，开 PR
  → Task 从 In Progress 拖到 In Review
  → 在 PR description 里写 "Closes CT-42"

周四
  → Reviewer approve, PR merged
  → Jira 自动把 Task 从 In Review 移到 Done
  → (如果没自动移 → 手动拖一下)
```

---

## 四、Board 与 Sprint 配置

### 4.1 Board 设置

```
Board type:   Scrum
Board name:   ClaimTrace Board
Filter query: project = CT ORDER BY Rank ASC

Columns:
  Backlog   |  To Do  |  In Progress  |  In Review  |  Done
```

### 4.2 Sprint 配置

```
Sprint duration:  2 weeks
Sprint naming:    ClaimTrace Sprint 1, ClaimTrace Sprint 2, ...

Sprint 日历:
  Sprint 1: W4 Mon — W5 Fri  (W4-W5)
  Sprint 2: W6 Mon — W7 Fri  (W6-W7)
  Sprint 3: W8 Mon — W9 Fri  (W8-W9)
  Sprint 4: W10 Mon — W11 Fri (收尾 + 打磨)

W1-W3 不用 Sprint — Backlog 即可。
```

### 4.3 Story Points 基准

| Points | 工作量 | 例子 |
|:---:|------|------|
| **1** | 半天以内 | 修一个 typo，加一行配置 |
| **2** | 半天到一天 | 写一个工具函数 + 测试 |
| **3** | 一到两天 | 实现一个 API endpoint |
| **5** | 两到三天 | 实现 PDF 解析器核心 |
| **8** | 一整周 | 尽量拆 — 8 的东西一定能拆成 3+5 |

**规则**：
- Sprint 容量 = 每人 ~10 points / 2 周。全队 ~70 points / Sprint。
- 实际 Sprint 1 跑一轮后校准。如果 Sprint 1 估了 70 只完成 40 → Sprint 2 容量下调到 45。
- **Story Points 不是工时** — 是"这个东西相对于其他东西有多大"。不要换算成小时。

---

## 五、Component 与 Label 体系

### 5.1 Label（主干）

每个 Task 打 2 个 Label：**团队** + **类型**。

```yaml
团队标签:
  engine      # Parser / Embedder / Retriever / Verifier
  backend     # API / Pipeline / Infra
  frontend    # Dashboard / Extension

类型标签:
  feat        # 新功能
  fix         # Bug 修复
  chore       # 杂活 (CI, 文档, 重构)
  spike       # 调研 / 实验 (W1-W3 专用)
```

示例：一个 Task 的 Label = `engine` + `feat`

### 5.2 不用 Epic 名字区分团队工作

Epic 的命名直接用 `[团队] [Sprint] - [目标]`：

```
Epic 列表 (W4-W9):

├── Engine Sprint 1: Baseline Pipeline (W4-W5)
├── Engine Sprint 2: Quality Push (W6-W7)
├── Engine Sprint 3: Integration & Edge Cases (W8-W9)
│
├── Backend Sprint 1: Parse + Verify API (W4-W5)
├── Backend Sprint 2: Audit + Reliability (W6-W7)
├── Backend Sprint 3: Performance & Polish (W8-W9)
│
├── Frontend Sprint 1: Upload + Verify Pages (W4-W5)
├── Frontend Sprint 2: Audit Dashboard (W6-W7)
└── Frontend Sprint 3: Chrome Extension (W8-W9)
```

每个 Epic 只属于一个团队。跨队的集成工作挂在 Tech Lead 自己的 Task 里。

---

## 六、每周操作节奏

### 6.1 周五 Workshop 前 (Sprint Review 准备)

```
Tech Lead (你, 周四下午):
  □ 打开当前 Sprint Board
  □ 哪些 Task 卡在 In Review > 1 天? → Slack ping reviewer
  □ 哪些 Task 卡在 In Progress > 3 天? → 周五 Review 时问
  □ 打开 Burndown Chart → 截图, 周五 Retro 用
```

### 6.2 周五 Workshop — Sprint Review + Retro + Planning (75 min)

```
时间线:

11:00-11:20  Sprint Review (全员, 你主持)
  → 打开 Jira Board, 按 Done 列过一遍:
    "这 2 周我们完成了 X 个 Story, Y 个 Task"
  → 每个队 3 分钟 demo (真实的运行代码, 不是 PPT)
  → 点名表扬: 谁这周做了超出预期的贡献

11:20-11:35  Sprint Retro (全员)
  → 三个问题:
    1. 什么做得好? (keep)
    2. 什么要改进? (change)
    3. 下一 Sprint 试一件事? (try)
  → Retro 结果记在 Confluence page 或 Notion 或 #retro Discord 频道
  → 至少产出一个可执行的 Action Item

11:35-12:15  Sprint Planning (全员)
  → 演示 Backlog 里排好优先级的 Story
  → 每个队认领下个 Sprint 的 Story
  → 认领的人当场把 Story 拆成 Task (不要会后拆 — 会忘了拆)
  → 每个 Task 估 Story Points
  → 检查总量: 不超过团队容量

12:15  Start Sprint → 你点 Jira 上的 "Start Sprint" 按钮
```

### 6.3 周一 Standup (15 min，你主持)

```
打开 Jira Board, 每人 1 分钟:

1. 你上周 Done 了什么 (看 Done 列的 card)
2. 你这周在做哪个 Task (看 In Progress 列)
3. 卡在哪里 (看 To Do 列有没有积压)

你在 Jira 上同步操作:
  → 把 Done 但没拖的 card 立刻拖到 Done
  → 把明显卡住的 card 标 Flag ⚠️
```

### 6.4 周三 Engine Team Sync (30 min)

```
不需要 Jira 开屏。你们四个人坐下来或者 Discord 语音:

1. 每个人过一遍自己这周的 Task 进度
2. 这个 Sprint 有没有到不了 Done 的 Task? → 降优先级或砍
3. 有没有两个人的 Task 会冲突? → 对齐 merge 顺序
```

---

## 七、各角色日常操作

### 7.1 Tech Lead（你）的 Jira 操作

```
每天 (5 min):
  → 打开 Board, 扫描 In Review 列 — 超过 1 天没合就 @ Reviewer
  → 扫描 In Progress — 超过 3 天就问一句 "卡在哪里了?"

每 Sprint 初 (Planning):
  → 提前把下一个 Sprint 的 Story 写好放到 Backlog
  → Planning 时主持拆 Task 流程
  → 点击 Start Sprint

每 Sprint 末 (Review):
  → 截图 Burndown + Velocity Chart (Confluence / Notion)
  → 主持 Retro
  → Complete Sprint → 没做完的 Story 自动回 Backlog

随时:
  → 新建 Bug: "CT-XX: 双栏解析在 XX 时崩溃"
  → Assign 给对应团队的人
```

### 7.2 开发者的 Jira 操作

```
每天:
  → 开工: 把要做的 Task 从 To Do 拖到 In Progress
  → 收工: 在 Task 的 Comment 里写一句今天做了什么 (不强制, 但推荐)

每 Task:
  → 开始写代码: 把 Task 拖到 In Progress
  → 开 PR: 把 Task 拖到 In Review, PR description 里写 "Closes CT-XX"
  → PR merged: 确认 Task 自动移到 Done (没自动就手动拖)

遇到不是 Bug 但需要做的事:
  → 建一个新的 Task, Assign 给自己, 问 Tech Lead 优先级
  → 不要默默把 3-point Task 做成了 8-point — 提前说
```

### 7.3 Frontend Solo 的特殊处理

他的 Story 粒度和其他队不同（一个人，不能拆成多人并行的 Task）：

```
Story: "用户能在 Dashboard 里上传多个 PDF"
  ├── Task: 拖拽上传组件 + 状态管理       (3 pts)
  ├── Task: 调用 POST /api/parse           (2 pts)
  └── Task: 上传进度条 + 错误处理           (2 pts)
```

Frontend 的 Tasks 按**先后依赖**排序，而不是并行。这没问题 — 一个 Sprint 他能完成的 Story Points 是 8-12 而不是 20。

---

## 八、GitHub 集成

### 8.1 连接 Jira ↔ GitHub

```
Jira → Settings → Apps → GitHub Integration → Get started

配置:
  → 连接 ClaimTrace GitHub Repo
  → 勾选: Smart Commits, Deployment, Development Info
```

### 8.2 Smart Commit 语法

在 Git commit message 或 PR title 里加上 Jira issue key，Jira 自动关联：

```bash
# 最常用的三个:

git commit -m "CT-42: fix two-column reorder for IEEE format"
  → Jira 自动把 CT-42 链接到这个 commit

# PR description 里写:
Closes CT-42
  → PR merge 时 Jira 自动把 CT-42 移到 Done

# 记录时间 (可选, 课程项目不需要):
git commit -m "CT-42 #time 3h: implement reorder algorithm"
```

### 8.3 PR → Jira 自动流转

```
1. 开发者在 PR description 写 "Closes CT-42"
2. Reviewer approves, PR merges to main
3. Jira 检测到 "Closes CT-42" → 自动把 CT-42 从 In Review 拖到 Done
4. 如果没自动工作 → 检查 GitHub Integration 是否 connected
   → 手动拖一下也不到 2 秒，不要花时间 debug
```

### 8.4 Jira 里看开发进度

```
每个 Task 打开后:
  → Development 面板会显示关联的 branch / commit / PR
  → 点击直接跳到 GitHub

Board 视图:
  → Card 上有 GitHub 图标 = 有代码关联
  → Card 上无图标 = 可能还没开始写代码 → 跟进
```

---

## 九、模板卡

### 9.1 Epic 模板

```
Summary:  [Engine] Sprint 1: Baseline Pipeline (W4-W5)

Description:
  ## Goal
  PDF → ParsedPaper → Embedding → FAISS → Retriever → Verifier
  整条流水线跑通。不追求准确率，追求「能跑通」。

  ## Success Criteria
  - [ ] POST /api/parse 接受 PDF 并返回 paper_id + 段落列表
  - [ ] POST /api/verify 接受 claim + paper_id 并返回 verdict
  - [ ] 端到端延迟 < 10s

  ## Stories
  - PDF → Structured Text
  - Embedding + FAISS Search
  - Verifier Pipeline
  - API Skeleton

Labels: engine
```

### 9.2 Story 模板

```
Summary:  用户可以上传 PDF 并获得结构化段落列表

Description:
  ## User Story
  As a researcher, I want to upload a source paper PDF
  so that ClaimTrace can extract its text for citation verification.

  ## Acceptance Criteria
  - [ ] Accept PDF files up to 50MB
  - [ ] Return JSON with { paper_id, paragraphs: [{text, page, bbox}] }
  - [ ] Handle two-column IEEE format correctly
  - [ ] Repair broken hyphenation at line boundaries
  - [ ] Show meaningful error for non-PDF files

  ## Tasks (tbd in Sprint Planning)
  → 由认领此 Story 的开发者拆

Labels: engine, feat
Story Points: (Sprint Planning 时估)
```

### 9.3 Task 模板

```
Summary:  实现 PyMuPDF 文本提取 + 位置元数据

Description:
  ## What
  用 fitz.open() + page.get_text("blocks") 提取所有文字块，
  保存 text + bbox + page 信息。

  ## Out of Scope
  - 双栏重排 (单独 Task)
  - 表格提取 (单独 Task)

  ## Reference
  - PyMuPDF docs: https://pymupdf.readthedocs.io/
  - 参考 parser/src/pdf_parser.py → extract_blocks()

  ## Done = 
  - [ ] 代码在 parser/src/pdf_parser.py
  - [ ] pytest 测试通过
  - [ ] PR merged to main

Labels: engine, feat
Story Points: 3
Assignee: (认领的人)
```

### 9.4 Bug 模板

```
Summary:  双栏解析在 page_width < 400pt 时崩溃

Description:
  ## Steps to Reproduce
  1. Upload PDF "small_format_paper.pdf" (attached)
  2. Parser crashes with IndexError in reorder_two_column()

  ## Expected
  Should handle single-column papers gracefully.

  ## Actual
  ```python
  IndexError: list index out of range
    at pdf_parser.py:89 in reorder_two_column()
  ```

  ## Severity
  Medium — affects ~10% of test PDFs, has workaround (manual reformat)

Labels: engine, fix
Priority: Medium
Assignee: (负责修的人)
```

---

## 十、快速启动检查表

W1 第一天就建好以下内容:

```
Week 1 启动:
  □ Jira 项目创建 (Scrum, Project Key: CT)
  □ 7 人全部加入项目
  □ Workflow 简化 (Backlog → To Do → In Progress → In Review → Done)
  □ Labels 创建: engine, backend, frontend, feat, fix, chore, spike
  □ GitHub Integration 连接
  □ 第一个 Backlog 建好 (W1-W3 的 Spike + 用户研究 Tasks)

Week 1 Backlog 内容:
  □ CT-1: Spike 1 — PDF 解析 + 语义检索可行性 [engine, spike]
  □ CT-2: Spike 2 — Entailment 判定准确率 [engine, spike]
  □ CT-3: Spike 3 — Overleaf DOM 可行性调查 [frontend, spike]
  □ CT-4: 用户访谈 #1-#5 [chore]
  □ CT-5: 竞品深潜报告 [chore]
  □ CT-6: CI/CD + Docker Compose 开发环境 [backend, chore]
  □ CT-7: Pitch Deck slides [chore]

Week 3 Sprint Planning 产出:
  □ 9 个 Epic 建好 (3 teams × 3 Sprints)
  □ Sprint 1 Story 拆成 Task, 全部估完 Points
  □ 点击 Start Sprint
```

---

## 附录：常用 Jira 快捷键

| 操作 | 快捷键 |
|------|--------|
| 创建 Issue | `C` |
| 快速搜索 | `/` |
| Assign to me | `I` |
| 在 Board 上拖动 | 鼠标拖拽 |
| 批量修改 | 选中多张 Card → 右键 → Bulk Change |
