# PR20：PDF Audit 接线进度

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

当前机器直连 Scholar 返回 HTTP 429（限流）。scholarly 内部重试导致请求长时间不返回。
后端启动时改用 BoundedScholarLookup：每条查询在独立进程中执行，30 秒超时后终止并返回 SCHOLAR_TIMEOUT / LOOKUP_FAILED。
Windows 进程输入输出使用临时文件，避免超时清理等待管道；原有 GoogleScholarLookup 继续负责 Engine 结果转换。
该限制针对每条查询，不是整份文档：N 条引用最坏仍需约 N × 30 秒，另加 PDF 转换和进程开销。

浏览器实际上传合成 IEEE PDF、解析出两条引用并发起真实 Scholar 查询，页面结束等待并展示两条 Lookup failed、元数据、页码和超时原因。失败报告已落盘且 GET 读回成功；没有把超时当成 NOT_FOUND。
新增 5 项测试覆盖工作进程协议、实际终止、异常处理与结果传递；已有 Audit/adapter 相关 40 项测试通过。
单引用合成样例未被 Parser 识别，页面正确显示空列表警告；没有修改 Parser 行为。

## 仍待联调

需要 Sichen 提供已验证可用的运行环境或网络配置，再完成真实文献候选返回、字段比对和网页展示的成功路径验收。
当前不能将模拟搜索测试或真实失败报告当成联网成功。未更换检索来源，也未接入 LLM。

PR20 保持 Draft，暂不合并。
