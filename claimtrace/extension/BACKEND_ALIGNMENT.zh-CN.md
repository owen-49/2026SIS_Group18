# 插件 Audit / 文献搜索对齐（2026-09-19）

分支：`fix/extension-audit-paper-search`。本次仅改插件及其文档，没有改后端、React 前端或打包密钥。

## 可以直接转发给后端同学

我已在新分支修插件侧接入：补了 Bib Audit 手动重试、Audit 结果和候选文献网页链接、后端结构化错误提示，并处理后端删除 Bib 记录后插件缓存 ID 失效的问题。重试 Audit 不再依赖 claim Verify 成功。

目前本机 `http://localhost:8000/health` 正常，但 `GET /api/papers` 实测返回 HTTP 500，内容是 `{"detail":"Unable to read paper metadata."}`，导致插件 PDF 选择列表无法加载。请帮忙看一下该服务的存储路径、历史 paper JSON 与当前 PaperRecord 模型是否兼容，以及服务日志中的异常；这些是排查方向，还没有确认根因。

另外，当前仓库路由和本机 OpenAPI 都没有独立 paper search 接口。插件现在支持本地 Bib 条目筛选、跳转原始 URL/DOI，以及打开 Audit 的 matched_record.url / candidates[].url；无链接时可按标题跳转 Google Scholar 搜索页，这不代表已找到或验证该文献。如果你们已完成另一个文献搜索接口，请发接口路径、请求参数、返回示例及所在分支，我再对齐到插件。

周一建议一起验：Overleaf .bib 检测 → POST /api/parse（已有记录用 PUT /api/parse/{id}）→ POST /api/audit {bib_paper_id} → 展示状态与文献网页；另验上传 PDF → GET /api/papers → POST /api/audit {manuscript_id}。Audit 保持 contract_version=2，结构化错误读取 detail.message，候选记录保持未确认。

## 本次验证与限制

- Node 插件回归测试：35 项通过，包含旧 ID 恢复、手动重试、结构化错误和链接渲染。
- 三个插件 JS 语法检查、manifest 资源存在检查、git diff --check 通过。
- 实际后端只做了 health、OpenAPI 和 papers 只读检查，未上传或删除用户数据。
- 尚未完成真实 Chrome + Overleaf + 外部文献服务端到端验收；Node DOM 测试不能证明浏览器布局或扩展服务进程的长请求稳定性。
- 后端默认地址仍为 localhost:8000，网页工作区为 localhost:3000。
- 插件现有 bibliography 状态仍是全局存储，多 Overleaf 项目隔离不在本次修复范围内。

## 本地验收

在 chrome://extensions 对已加载的 claimtrace/extension 点重新加载，并刷新 Overleaf 页面。选中 .bib 文件，打开侧栏 → Audit / retry BibTeX。在 Papers 下检查 Audit 状态及 Open paper / Review candidate 链接，再输入关键词验证本地过滤与外部搜索入口。后端恢复 papers 接口后，重新打开侧栏加载 PDF 列表再验 Audit PDF。
