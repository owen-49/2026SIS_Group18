# ClaimTrace 展示材料

用于五分钟项目汇报的材料：两种格式的幻灯片、两种格式的 A1 海报，以及三个核心功能的交互演示。

> English version: [README.md](README.md)

| 文件 | 内容 | 使用方式 |
|---|---|---|
| `slides.html` | 8 页 16:9 网页版幻灯片 | 用 Chrome 打开。`←` `→` 翻页，`P` 打印，点击幻灯片左/右半区也可翻页 |
| `ClaimTrace-Showcase.pptx` | 同一套幻灯片的真实 PowerPoint 文件 | 用 PowerPoint、Keynote 或 Google Slides 打开，每页都有演讲备注 |
| `poster.html` | A1 竖版海报（594 × 841 mm） | 用浏览器打开可看到自适应预览；打印时选 A1、边距设为“无”、勾选“背景图形” |
| `ClaimTrace-Poster-A1.pdf` | 同一张海报的成品 PDF，594.1 × 841.0 mm | 直接送印，或在预览中打开；无需任何设置 |
| `rotating-poster.html` | 用于屏幕展示的四面 3D 海报 | 用浏览器打开。拖拽旋转，方向键翻面，每 6.5 秒自动切换；`#1`–`#4` 可直达某一面 |
| `demo.html` | Audit、Verify、Read 三个功能的交互演示 | 用浏览器打开；标签页可用 `#audit`、`#verify`、`#read` 直达 |
| `theme.css` | 共用的颜色、字体和标签样式变量 | 被三个 HTML 页面引用 |
| `build_pptx.py` | 从头重新生成 `.pptx` | `python3 build_pptx.py`（需要 `python-pptx`） |

所有内容都是自包含的：不会从网络加载任何字体、脚本或样式。

## 五分钟讲稿

| 时间 | 幻灯片 | 讲解要点 |
|---|---|---|
| 0:00 | 1 — 标题 | 用一句话说明 ClaimTrace 是什么。 |
| 0:25 | 2 — 问题 | “最后 48 小时”的抱怨；三类用户要的是同一件事——证据，而不只是结论。 |
| 1:05 | 3 — 三个功能 | 审计参考文献、核验论点与原文、在同一个面板里读论文。 |
| 2:00 | 4 — 架构 | 身份判定由引擎负责，产品从不猜测。一个进程，两个对外边界。 |
| 2:45 | 5 — Audit | 四条真实 fixture 用例；真正重要的是那两条“拒绝作答”的记录。 |
| 3:40 | 6 — Verify | 结论只是标题，原文段落才是论据。 |
| 4:20 | 7 — 数据 | 1,130 个测试、34/34 受控审计用例、12/12 在线验证用例、服务端不持有模型密钥。 |
| 4:50 | 8 — 收尾 | 后续计划和诉求。 |

如果要现场演示，在第 3 页之后打开 `demo.html`：先重放审计，再分别点一条 SUPPORT 和一条
NOT_FOUND 的 claim，最后展示 Read 面板。

## 哪些是实测数据，哪些是示意

幻灯片和海报里的每个数字都可以追溯：

- **1,130 个测试** — backend 552、engine 378、parser 101 通过 + 2 跳过、扩展 49、前端 50，
  基于本地 `main` 分支 `e171fb3`。
- **34/34 审计用例** — `docs/accuracy-baseline/audit_accuracy_subset.json`，生成时间
  `2026-10-08T07:55:20+00:00`：状态准确率 1.00，macro-F1 1.00；各状态分别为 7 条 verified、
  12 条 metadata mismatch、9 条 needs review、1 条 not found、2 条 lookup failed。
- **12/12 在线验证用例** — 6 条 claim 各跑两种模式，使用 DeepSeek，共 12 次模型调用。
- **每次审计请求 0.055 秒** — `docs/accuracy-baseline/audit_timing.json`。
- **审计表格中的用例** — `bert-exact`、`bert-year-plus-one`、`dialoguernn-year-minus-five` 和
  `provider-500` 都是 `backend/tests/benchmarks/audit_cases.json` 里的真实用例。
- **验证用的 claim 与段落** — 6 条 claim 和 5 段原文来自
  `backend/scripts/acceptance_citation_comparison.py`；引用的段落逐字取自
  *Attention Is All You Need*。

有意不做的声明：

- 这些是 **fixture 标签**，不是独立的专家标注。第 7 页已经写明这一点。
- 演示中的 claim 不显示检索排名或相似度分数，因为仓库里没有已录制的 verify 排名数据
  （`recorded_claims/passages.json` 中没有 pairs）。因此统一使用
  “Retrieved from the cited paper · quoted verbatim.”。产品本身确实会在
  `ComparisonEvidence` 中返回 `rank` 和 `similarity`——这句关于**产品**的陈述是准确的，
  只是展示材料里不出现编造的数值。
- `demo.html` 里的 Read 面板是**示意性节选**。它展示的 Markdown 管线
  （`rehype-raw` → `rehype-sanitize` → `rehype-katex`）和图片路由
  （`GET /api/papers/{paper_id}/images/{filename}`）都是真实的；配图是示意图，
  页面上已注明。
- 导师的引语是从中文用户研究翻译成英文的，标注为 “translated from user research”。

## 打印海报

`ClaimTrace-Poster-A1.pdf` 已经是 A1 尺寸（594.1 × 841.0 mm），不需要任何打印设置，直接送印即可。
它由 `poster.html` 通过无头 Chrome 生成：

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --no-pdf-header-footer --print-to-pdf=ClaimTrace-Poster-A1.pdf "file://$PWD/poster.html"
```

`poster.html` 会按窗口大小缩放预览。在浏览器打印对话框中选择 **A1**，边距设为 **无**，
并勾选 **背景图形**。页面声明了 `@page { size: 594mm 841mm; margin: 0 }`；打印时预览缩放会被移除。

旋转海报只用于屏幕展示。展台循环播放时，全屏打开 `rotating-poster.html` 即可：它会自动旋转，
鼠标悬停或拖拽时暂停。

## 重新生成 PPTX

```sh
cd claimtrace/showcase
python3 build_pptx.py
```

生成脚本使用 `python-pptx` 以及 Georgia、Arial、Courier New 三种字体，因此在 macOS 和 Windows
上打开都不会发生字体替换。文字溢出和形状边界已经通过程序检查，但这台机器上**没有做视觉渲染**
（没有 LibreOffice）。正式汇报前请用 PowerPoint 或 Keynote 打开确认一次；HTML 版是像素级参照。
