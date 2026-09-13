# PR #18 审核后续：分工与可转发消息

PR：https://github.com/owen-49/2026SIS_Group18/pull/18

本轮只修复后端参考文献产物复用。按作者要求，暂不进行新的 Engine
对接或外部查询服务接入。以下消息由作者确认后自行转发，尚未发送或分派。
PR 保留 Ready for review，但两个端到端阻塞项仍然存在，不代表可直接合并。

## 已完成的后端修复

- PDF Audit 优先读取 `PARSED_DIR/{paper_id}.references.json`。
- 兼容现有 Parser 公共 JSON：`source_file` 与 `references[].raw_text`；不会编造缺失页码。
- 文件缺失时调用已有抽取器一次，原子保存结果；有效空列表同样保存和复用。
- 后端保存时额外保留编号、页码、警告、论文 ID 和源 PDF SHA-256。
- 文件损坏、论文 ID/来源文件不符、已保存 SHA 与现有 PDF 不符时，返回
  HTTP 500 / `REFERENCE_ARTIFACT_ERROR`，不静默重新抽取或覆盖原文件。
- 显式重新解析 PDF 会使旧 Reference JSON 失效。
- 同一后端进程内并发请求共用抽取锁；多进程同时首次抽取尚无跨进程协调。

当前 `19722f4` 上传 pipeline 没有调用 Reference JSON 保存函数。因此这是
“已有文件优先读取＋缺失时首次 Audit 生成”的修复，并非声称上传时已经生成。
若其他分支已有上传持久化实现，请先对齐产物路径和 schema，避免另写一套。
现有最小 Parser JSON 没有指纹和页码，后端只能检查文件名/可选论文 ID；
不能对历史产物作出与新 SHA-256 产物相同的溯源保证。

验证：后端及相关 Engine Bib 回归共 141 项通过，Ruff 通过；本轮新增 10 个
参考文献产物场景。没有运行真实外部查询，也未修改前端或 Engine/Parser 包代码。

## 发给前端同学

> PR #18 的 Audit 后端已经从批量语义验证改为参考文献真实性和元数据核实，
> 但当前页面仍用旧 v1 契约。请你负责前端 v2 迁移，保留当前布局和差异展示结构，
> 将展示内容改为参考文献字段差异，不比较声明和论文正文的匹配度。
>
> 请修改 `frontend/src/api/client.ts`、`frontend/src/types/api.ts`、
> `frontend/src/pages/AuditPage.tsx`，以及相关 mock 和测试。
> `POST /api/audit` 只传 `{"bib_paper_id":"..."}` 或
> `{"manuscript_id":"..."}` 其中一个；输入选择器支持已完成的 Bib/PDF，
> 来源 PDF 不再必选，也不需要传 `source_paper_ids`。
>
> 响应使用 `contract_version: 2`、`total_entries`、`counts`、`results`；
> 每行读 `entry.metadata` / `entry.metadata.raw_text`、`status`、`reason`、
> `field_checks`、`matched_record`、`candidates` 和 `lookup_attempts`。
> 不再读取 `claim`、`verdict`、`confidence`、`supported`、`partial`、`contradicted`。
> 标题、作者、年份、venue、DOI 的差异用 `input_value` 与 `source_value` 展示。
> `matched_record` 可空，证据链接用记录的 `url`，同时显示 provider 和 retrieved_at。
>
> 五种状态分别展示：VERIFIED 已核实、METADATA_MISMATCH 信息不一致、
> NEEDS_REVIEW 待人工确认、NOT_FOUND 未找到、LOOKUP_FAILED 查询失败。
> 不要把 NOT_FOUND 显示为假文献，也不要把查询失败计入已核实。
> `completed` 只是处理完成；有效空结果应显示未抽取到参考文献，不能显示全部通过。
> HTTP 错误要兼容 `detail: {code,message}`、字符串和 FastAPI 422 错误数组。
>
> 目前外部查询尚未接入，真实非空结果仍返回 LOOKUP_FAILED /
> EXTERNAL_LOOKUP_NOT_CONFIGURED，请如实展示“查询服务未接入”。
> 其他状态可先用符合 v2 schema 的测试数据联调，不能把 mock 当作真实核实结果。
> 验收需要实际检查 v2 响应渲染、五种状态、缺失字段、空结果及错误展示，
> 不能仅以 TypeScript/build 通过为完成。
>
> 建议从最新 `backend/bibtex-integration` 建个人分支，将配套 PR 的目标分支设为
> `backend/bibtex-integration`，便于单独审核并汇入 PR #18，避免直接互相覆盖。

## 发给 Parser 同学

> PR #18 已改成优先读持久化 Reference JSON，缺失时才抽取并保存，
> 路径约定是 `PARSED_DIR/{paper_id}.references.json`。目前兼容你们现有的
> `source_file`、`references[].raw_text` 最小 JSON，同时保留可选编号、页码和警告。
> 请确认你们是否已在其他分支实现“上传时保存 references.json”，提供对应 commit、
> 保存路径和样例。`19722f4` 的上传 pipeline 尚未接入该保存调用。
>
> 另一个需要你们补齐的问题是 PDF 引用的结构化字段。请提供标题、作者数组、年份、
> venue、DOI，以及 raw_text、编号、页码；无法抽取的字段保持缺失，并保留字段对应的
> 原文片段或位置和抽取警告。不要用查询命中的外部元数据回填输入字段，再拿它与自身
> 比较，否则会掩盖原引用里的错误。
>
> 请先给 schema 与样例，我们共同确认后由后端接入。当前后端还没有承诺自动读取
> 尚未约定的结构化扩展字段。建议样例至少包含：有 DOI、无 DOI、多行作者、
> 无法识别字段、未找到参考文献标题。有效空结果要显式给出 `references: []`。
> 此前最小 PDF 样例未识别出 References 标题，返回空结果；请协助排查识别边界。

## 给 Engine 同学的待办说明（本轮暂不对接）

> 先同步 PR #18 的需求边界，当前不要求你立即开始对接：Verify 判断单条声明支持关系，
> Audit 判断文献身份与元数据。后端暂时继续复用已有元数据比较器，不修改 Engine 包。
>
> 后续请一起确认外部查询与候选消歧的归属。当前只有
> `BibliographyLookup.lookup(ReferenceEntry) -> LookupResult` 接口，没有生产查询实现。
> 候选检索应覆盖 DOI 和无 DOI 情况；自动确认身份不能只取第一条搜索结果，
> 多个可能候选返回 ambiguous，由后端映射 NEEDS_REVIEW。
> 记录需提供 provider、record_id、url、retrieved_at 和 metadata；
> 查询 outcome 使用 found / ambiguous / not_found / failed，并附 attempts 和 reason。
> 超时、限流和无凭据不能伪装成 not_found，未找到也不能判定为假文献。
>
> 请特别复核当前作者仅按姓氏、标题模糊匹配等规则；后端已有保守的人工确认兜底，
> 后续仍需明确哪些字段算一致、不一致或信息不足。
> 数据源、费用、凭据和模块负责人未确认前，先不要引入新的付费或账户依赖。

## 给审核人的进度回复

> 已针对“PDF Audit 重复抽取”补充持久化优先读取、首次抽取保存、错误处理和重解析失效。
> 正在按模块协调其他问题：前端负责迁移 v2，Parser 确认产物并补结构化字段；
> 作者要求本轮暂不进行 Engine/外部查询新对接。
> 因此前端契约不兼容和生产查询未配置这两个阻塞项仍保留，没有标为已解决。
> 请先复核本轮后端修复，端到端功能完成后再重新评估是否 Approve/merge。
