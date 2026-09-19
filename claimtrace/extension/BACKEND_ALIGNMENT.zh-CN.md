# 插件 Audit / 文献搜索对齐（2026-09-19）

分支：`fix/extension-audit-paper-search`。本次改动集中在插件 Audit 流程，并补了后端本地数据目录与 paper 列表读取的修复；没有改 React 前端或打包密钥。

## 可以直接转发给后端同学

我已在新分支修插件侧接入：Bib Audit 自动/手动路径都只调用 `POST /api/audit`，不再调用 claim Verify；保留 Audit 结果和候选文献网页链接、结构化错误提示，并处理后端删除 Bib 记录后插件缓存 ID 失效的问题。PDF Audit 发送已选 ID 后直接由后端校验，不再重复依赖 `/api/papers`。

此前报告的 `GET /api/papers` HTTP 500 由运行时 paper 元数据读取触发。后端现在将默认 `uploads` 固定到 backend 包目录，避免从仓库根目录启动时误读其他 `uploads/papers.json`；列表读取也会跳过单条损坏记录并记录日志，不再让一条坏记录阻塞全部 PDF 列表。若整个 JSON 不是合法 store 格式，接口仍会返回 500，避免静默丢失数据。修改后需要重启后端。

另外，当前仓库路由和本机 OpenAPI 都没有独立 paper search 接口。插件现在支持本地 Bib 条目筛选、跳转原始 URL/DOI，以及打开 Audit 的 matched_record.url / candidates[].url；无链接时可按标题跳转 Google Scholar 搜索页，这不代表已找到或验证该文献。如果你们已完成另一个文献搜索接口，请发接口路径、请求参数、返回示例及所在分支，我再对齐到插件。

周一建议一起验：Overleaf .bib 检测 → POST /api/parse（已有记录用 PUT /api/parse/{id}）→ POST /api/audit {bib_paper_id} → 展示状态与文献网页；另验上传 PDF → GET /api/papers → POST /api/audit {manuscript_id}。Audit 保持 contract_version=2，结构化错误读取 detail.message，候选记录保持未确认。

## 本次验证与限制

- Node 插件回归测试：41 项通过，包含旧 ID 恢复、手动重试、Audit-only 自动路径、PDF Audit 无列表依赖、结构化错误和链接渲染。
- 三个插件 JS 语法检查、manifest 资源存在检查、git diff --check 通过。
- 实际后端只做了 health、OpenAPI 和 papers 只读检查，未上传或删除用户数据。
- 尚未完成真实 Chrome + Overleaf + 外部文献服务端到端验收；Node DOM 测试不能证明浏览器布局或扩展服务进程的长请求稳定性。
- 后端默认地址仍为 localhost:8000，网页工作区为 localhost:3000。
- 插件现有 bibliography 状态仍是全局存储，多 Overleaf 项目隔离不在本次修复范围内。

## 本地验收

在 chrome://extensions 对已加载的 claimtrace/extension 点重新加载，并刷新 Overleaf 页面。选中 .bib 文件，打开侧栏 → Audit / retry BibTeX。在 Papers 下检查 Audit 状态及 Open paper / Review candidate 链接，再输入关键词验证本地过滤与外部搜索入口。后端恢复 papers 接口后，重新打开侧栏加载 PDF 列表再验 Audit PDF。

## 3b00fd4 后续复测与提示修复

- 自动 Bib 上传/解析失败现在写入单独的 claimtraceBibSyncError，Audit 区显示具体错误；重试时清除，避免恢复后仍显示旧错误。不会用 Bib 解析错误覆盖 PDF Audit 的运行/完成状态。
- 实时 paper 列表失败或回退缓存的警告由侧栏保存并统一渲染；首次打开、切换视图及状态刷新不会丢失提示，成功重新加载列表后清除。
- 插件回归测试：45 项通过。真实 Chrome 模拟失败响应：两个错误场景均可见；正常的浮层操作及 320/390/520px 布局检查通过。
- 后端测试：临时使用 Temurin Java 17 后，201 项全部通过。此前 Java 8 下的 10 个 PDF 相关失败未再出现。未修改系统 Java 默认配置，也未重启用户的 8000 服务。
- 仍未完成登录状态下真实 Overleaf 与外部检索服务的端到端验收。

本机复测命令（临时目录清理后需重新准备测试环境）：

```sh
cd /Users/lijunli/Code/Hub/2026SIS_Group18
PATH="/tmp/claimtrace-jre17/jdk-17.0.20.1+1-jre/Contents/Home/bin:$PATH" \
PYTHONPATH=claimtrace:claimtrace/engine:claimtrace/parser \
/tmp/claimtrace-3b00fd4-venv/bin/python -m pytest claimtrace/backend/tests -q
```
