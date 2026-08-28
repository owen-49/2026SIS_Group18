# User Stories

> 关联画像：见 [personas.md](personas.md)。  
> 优先级定义：**P0** = MVP 必须有（12 周 demo 的核心闭环）；**P1** = 重要、尽量做；**P2** = 锦上添花、可延后。

---

## 功能分组总览

```
A. 文档摄入        B. 引用验证        C. 元数据校验      D. 批量审计
   ├ US-01 上传PDF    ├ US-02 hover     ├ US-04 上传bib    ├ US-05 全篇审计
   │                 ├ US-03 判定       │                  │
   └ US-07 论文库    └ US-06 看证据     └                  └ US-09 导出报告
```

---

## P0 — MVP 核心（必须交付）

### US-01 · 上传并解析源论文 PDF

> **As a** 研究者（P1），**I want** 上传一篇源论文 PDF 并让它被解析成结构化段落，**so that** 系统能针对它做后续的引用验证。

- **Priority**: P0
- **Persona**: P1 博士生（主要）、P2 导师
- **Acceptance Criteria**:
  - [ ] 接受 ≤50MB 的 PDF 上传，非 PDF 返回明确错误而非 500
  - [ ] 解析返回 `paper_id` + 段落数 + 页数
  - [ ] 正确恢复双栏 PDF 的阅读顺序（不混栏）
  - [ ] 修复跨行断字符（`repre-\nsentation` → `representation`）
  - [ ] 解析结果可通过 `paper_id` 查询状态
- **Story Points**: 8

---

### US-02 · 在 Overleaf 中 hover 引用查看原文

> **As a** 研究者（P1），**I want** 在 Overleaf 里把鼠标悬停在 `\cite{...}` 上就能看到它指向的源原文段落，**so that** 我不离开写作流就能核对引用。

- **Priority**: P0
- **Persona**: P1 博士生（核心）
- **Acceptance Criteria**:
  - [ ] 浏览器扩展能识别 `\cite{key}` 并捕获 hover 事件
  - [ ] hover 时弹窗展示源 PDF 中匹配的原文段落（高亮）
  - [ ] 弹窗显示判定标签（🟢/🟡/🔴）
  - [ ] 端到端延迟 < 1s（在已索引的论文上）
- **Story Points**: 13

---

### US-03 · 验证一条 claim 是否被源文献支撑

> **As a** 研究者（P1），**I want** 输入/选定一句论文声明并得到「被支撑 / 部分支撑 / 相矛盾 / 未找到」的判定，**so that** 我知道这个引用是准确、夸大还是曲解。

- **Priority**: P0
- **Persona**: P1 博士生、P3 审稿人
- **Acceptance Criteria**:
  - [ ] 返回四分类判定：`SUPPORT` / `PARTIAL` / `CONTRADICT` / `NOT_FOUND`
  - [ ] 每个判定附带置信度 + 匹配到的原文段落
  - [ ] 语义匹配能处理 paraphrase（措辞不同但含义一致）
  - [ ] 判定附带人类可读的 rationale
- **Story Points**: 13

---

### US-04 · 上传 .bib 文件并校验元数据

> **As a** 研究者（P1），**I want** 上传 `.bib` 文件并与源 PDF 的真实信息交叉比对，**so that** 我能发现参考文献条目里的年份错、标题乱码、DOI 指错论文这类错误。

- **Priority**: P0
- **Persona**: P1 博士生
- **Acceptance Criteria**:
  - [ ] 解析 `.bib` 文件得到结构化条目（title/authors/year/venue/DOI）
  - [ ] 逐字段返回 `MATCH` / `MISMATCH` / `BIB_MISSING` / `PDF_MISSING`
  - [ ] 支持常见 BibTeX 特性（`@string` 宏、`#` 拼接、LaTeX 转义、作者名归一化）
  - [ ] 缺失源 PDF 时优雅降级（返回 `PDF_MISSING` 而非崩溃）
- **Story Points**: 8

---

## P1 — 重要（尽量交付）

### US-05 · 一键批量审计整篇论文的引用

> **As a** 研究者（P1），**I want** 上传论文草稿 + 所有引用 PDF 后一键运行全量审计，**so that** 交稿前能系统性地而不是凭感觉检查所有引用。

- **Priority**: P1
- **Persona**: P1 博士生、P2 导师
- **Acceptance Criteria**:
  - [ ] 返回总引用数、supported/partial/contradicted/not_found 计数
  - [ ] 结果按风险等级排序，红色标出最该人工复核的引用
  - [ ] 每个条目可展开查看判定依据
- **Story Points**: 8

---

### US-06 · 查看每条判定的原文证据

> **As a** 研究者（P1/P3），**I want** 每条判定都附带它匹配到的原文段落和引用来源，**so that** 我自己能判断 AI 判得对不对，而不是盲信结论。

- **Priority**: P1
- **Persona**: 全部（这是「信任」的核心）
- **Acceptance Criteria**:
  - [ ] 判定结果旁展示原文段落（而非只有标签）
  - [ ] 段落标注来源（页码 / section / 引用 key）
  - [ ] 用户能一键跳转到源 PDF 对应位置
- **Story Points**: 5

---

### US-07 · 管理论文库（复用已解析论文）

> **As a** 研究者（P1），**I want** 上传过的论文能保存在库中、下次复用而不必重新上传，**so that** 多篇论文引用同一文献时不用重复处理。

- **Priority**: P1
- **Persona**: P1 博士生、P2 导师
- **Acceptance Criteria**:
  - [ ] 已解析的论文持久化（重启后仍在）
  - [ ] 论文库支持列出/查询已上传论文
  - [ ] 同一篇论文可被多次验证复用
- **Story Points**: 5

---

## P2 — 锦上添花（可延后）

### US-08 · 审稿人快速核查投稿

> **As a** 审稿人（P3），**I want** 对一篇投稿的核心主张快速核查其引用是否准确，**so that** 我能在 review 里给出有据可依的评审意见。

- **Priority**: P2
- **Acceptance Criteria**:
  - [ ] 支持导入投稿 PDF + 自动提取其引用列表
  - [ ] 批量比对投稿 claim 与引用原文
- **Story Points**: 8

---

### US-09 · 导出审计报告

> **As a** 研究者（P1/P2），**I want** 导出审计结果为可分享的报告（Markdown/PDF），**so that** 我能发给合著者或导师沟通修改。

- **Priority**: P2
- **Acceptance Criteria**:
  - [ ] 导出包含风险排序 + 证据的报告
  - [ ] 报告含针对每个问题的修改建议
- **Story Points**: 3

---

### US-10 · 团队共享论文库

> **As a** 合著团队（P1），**I want** 团队共享一个论文库，**so that** 合著者之间的引用验证结果可以复用、避免重复劳动。

- **Priority**: P2
- **Acceptance Criteria**:
  - [ ] 多用户可访问同一论文库
  - [ ] 验证结果可共享给团队成员
- **Story Points**: 8

---

## 优先级矩阵（价值 × 成本）

| Story | 价值 | 成本 | 结论 |
|-------|:---:|:---:|------|
| US-01 上传解析 PDF | 高 | 中 | **P0 必做** |
| US-02 hover 验证 | 极高 | 高 | **P0 必做**（差异化核心） |
| US-03 claim 判定 | 极高 | 高 | **P0 必做**（核心价值） |
| US-04 bib 校验 | 高 | 低 | **P0 必做**（成本低收益好） |
| US-05 批量审计 | 高 | 中 | P1 优先做 |
| US-06 看证据 | 极高 | 低 | P1 优先做（信任基石） |
| US-07 论文库 | 中 | 低 | P1 优先做 |
| US-08 审稿人场景 | 中 | 高 | P2 可延后 |
| US-09 导出报告 | 中 | 低 | P2 可延后 |
| US-10 团队共享 | 中 | 高 | P2 可延后 |
