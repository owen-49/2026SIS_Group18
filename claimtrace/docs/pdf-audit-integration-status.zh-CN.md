# PR20：PDF Audit 接线进度

> ⚠️ **2026-09-18 现状更正**：本文是 PR20 期间的进度日志，**正文保留原样**作为当时的记录，
> 但其中所有关于 **Google Scholar / scholarly / BoundedScholarLookup / worker 子进程 /
> `SCHOLAR_*` 环境变量 / bibtexparser 固定版本**的描述**均已过时**。
>
> 检索来源已替换为 **OpenAlex（主）+ Crossref（补）** 的 provider 链，由
> `backend/src/services/provider_chain_lookup.py::ProviderChainLookup` 适配到既有的
> `LookupResult` / Audit v2 契约。Scholar 路径、worker 子进程与上述依赖已整体删除；
> 新增 `METADATA_LOOKUP_TIMEOUT_SECONDS`（单次 socket 操作），`SCHOLAR_*` 全部移除。
> 详见 [backend-audit-handoff- scholar- search.md](backend-audit-handoff-%20scholar-%20search.md) §8
> 与 [audit-live-acceptance/audit-integration-handoff.md](audit-live-acceptance/audit-integration-handoff.md)。
>
> 仍**有效**的部分：PDF 上传 / Manage papers / Run audit 的入口接线、结构化元数据的保存与读取、
> raw-text 缓存升级、五种状态与报告落盘、前端契约（`contract_version: 2`）——这些都没有改动。
>
> **一处语义变化**，见下方"缺标题条目保留为 Needs review"：该守卫原先读**结构化** title，
> 而 PDF 引用里这个字段 174 条中只有 1 条非空，所以实际上**每一条** PDF 引用都在检索前被退回
> Needs review，lookup 从未被调用。现在守卫改读**可检索** title（结构化优先，空则用 raw_text 解析，
> 两者共用一个函数），该状态仍然存在，只是不再吞掉整条路径。

## 已完成

- 网页现有的 PDF 上传 / Manage papers / Run audit 入口接入后端 Audit。
- 保存并读取 Parser 的 title、authors、year、venue、doi，同时保留原文、编号、页码。
- 旧版 raw-text 缓存通过 Parser 补元数据，不重新转换 PDF；显式 null 保留。
- 元数据交给 Sichen 的 Scholar 搜索，再通过现有比对逻辑生成五种状态并保存报告。
- IEEE 作者首字母格式在查询边界转换为姓氏，原始作者字段不变。
- 缺标题条目保留为 Needs review；空引用列表不显示全部匹配成功。
- 固定 bibtexparser 为兼容 scholarly 的 1.x，避免新安装环境导入失败。

## 依赖与范围

PR20 分支已整合 PR23 的 b65f8e3 作为依赖，PR23 本身没有合并到 main。
因此当前 PR20 diff 包含 Parser 依赖代码；不要绕过 PR23 的审核直接合并 PR20。
之前讨论的两个 Parser 问题暂不修复。本轮没有接入 LLM。

## 验证

- 152 项测试通过：全部 backend 测试、Scholar/适配器测试、Reference List Parser 测试。
- 合成 IEEE PDF 实际经过上传、OpenDataLoader 转换、引用提取、Audit 和报告读回；仅外部搜索响应使用替身。
- 集成测试检查真实查询构造、元数据落盘、旧缓存升级和重复读取。
- 前端 TypeScript / Vite 生产构建、ESLint、改动 Python 文件 Ruff 通过。
- 前端验证使用 pnpm 安装 package.json 范围内依赖；没有修改 package-lock.json。

## 2026-09-10 查询联调更新

当前机器直连 Scholar 返回错误状态码。scholarly 内部重试导致请求长时间不返回。

> ⚠️ **2026-09-16 更正**：本节当时把观测到的 `SCHOLAR_TIMEOUT` 归因于 **HTTP 429**，这与代码路径矛盾。
> 裸 429 走 scholarly `_navigator.py:154-156` 的 `else` 分支，**会**自增重试计数并被正确约束，
> 应表现为 `SCHOLAR_RATE_LIMITED`，**而不是** 30 秒超时。真正会让请求永不返回的是
> **403 / captcha / DOS** 三条分支（`_navigator.py:134-164`）：它们每次 sleep 60–120 秒后 `continue`，
> 从不让重试计数前进。仓库内当时没有任何 artifact 记录过真实 HTTP 状态码——这正是后来补上
> stderr 捕获的原因。详见 [engine-scholar-timeout-diagnosis.zh-CN.md](engine-scholar-timeout-diagnosis.zh-CN.md)。
后端启动时改用 BoundedScholarLookup：每条查询在独立进程中执行，30 秒超时后终止并返回 SCHOLAR_TIMEOUT / LOOKUP_FAILED。
Windows 进程输入输出使用临时文件，避免超时清理等待管道；原有 GoogleScholarLookup 继续负责 Engine 结果转换。
该限制针对每条查询，不是整份文档：N 条引用最坏仍需约 N × 30 秒，另加 PDF 转换和进程开销。

浏览器实际上传合成 IEEE PDF、解析出两条引用并发起真实 Scholar 查询，页面结束等待并展示两条 Lookup failed、元数据、页码和超时原因。失败报告已落盘且 GET 读回成功；没有把超时当成 NOT_FOUND。
新增 5 项测试覆盖工作进程协议、实际终止、异常处理与结果传递；已有 Audit/adapter 相关 40 项测试通过。
单引用合成样例未被 Parser 识别，页面正确显示空列表警告；没有修改 Parser 行为。

## Worker 启动路径修复

复核发现，文档规定的 `cd claimtrace/backend; uvicorn src.main:app` 会让旧 worker 命令
`python -m backend.src.services.scholar_worker` 在搜索前直接失败。现在 worker 使用
`src.services.scholar_worker`，并从 `bounded_scholar_lookup.py` 的实际位置计算 package root，
不再依赖 API 进程的当前工作目录；Docker 的 `/app` 布局也使用同一逻辑。

从 `claimtrace/backend` 启动后端并上传 BibTeX 实测通过：Scholar worker 返回了两个真实候选，
Audit 正确生成 `NEEDS_REVIEW`（多候选），没有返回 `SCHOLAR_WORKER_FAILED`。报告也已保存。
此前遇到的 HTTP 429 仍可能在其他网络环境出现，但现在会进入真实查询的超时/失败处理，不会与本地启动错误混淆。

新增 backend 工作目录回归测试；本轮完整相关回归为 158 项通过，Ruff 和 diff 检查通过。
未更换检索来源，也未接入 LLM。PR20 可继续按 Ready for review 审阅，合并仍需考虑 PR23 依赖。

本周按代码交付范围收尾，提交 Ready for review；上述真实联网成功路径及 Parser 已知问题留待下周处理，不作为本周转入审核的前置条件。Ready for review 表示可以审阅，不表示真实 Scholar 成功路径已通过验收；合并仍需考虑 PR23 依赖。

## Weekly journal 可用说明

本周完成网页 PDF Audit 的后端集成，将 Parser 提取的引用元数据接入 Scholar 查询、字段比对和报告存储，并验证网页上传、解析、结果展示和报告读回。针对 Scholar 限流导致的长时间等待，增加每条查询 30 秒超时及明确失败状态。自动化测试和前端构建通过；真实联网测试返回限流/超时，成功检索验收留待下周与 Sichen 联调。本周提交 PR20 进入代码审核，未接入 LLM。
