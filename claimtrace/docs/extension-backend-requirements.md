# Chrome 插件与后端联调需求

> 日期：2026-08-29
>
> 对象：Chrome 插件开发人员

## 目标

让插件把 Overleaf 中检测到的 BibTeX 和 citation 信息交给后端处理，并向用户显示后端返回的真实结果。

## 功能边界

- 插件支持 `.tex` 和 `.bib`；
- 插件不负责 PDF 上传或 PDF 解析；
- PDF 由用户通过网页上传并保存在本地 Library；
- 插件使用网页中已经存在的 PDF 记录进行验证。
- 插件负责读取 `.tex` 内容并提取 citation；当前后端不要求上传整个 `.tex` 文件。

## 后端当前已支持

- 接收和解析 BibTeX 文件；
- 返回 Bib paper ID 和 entry 数量；
- 返回本地 Library 中已有的 PDF 和 Bib；
- 验证 Bib metadata；
- 验证单条 claim 与源 PDF 的关系。

## 插件需求

1. 将 Overleaf 中检测到的 BibTeX 内容提交给后端。
2. 保存并使用后端返回的 Bib paper ID。
3. 使用网页 Library 中已经上传的 PDF，不在插件中增加 PDF 功能。
4. 将检测到的 citation key 和 claim 与后端验证结果正确对应。
5. 向用户展示后端返回的真实验证结果。
6. 后端不可用、没有源 PDF 或 metadata 缺失时，显示清楚的状态提示。
7. Demo 结果必须明确标注为 Demo，不能与真实后端结果混淆。
8. 保留现有的 Bib 检测、citation 检测和编辑器定位功能。

## 需要使用的后端接口

- `GET /health`：确认后端是否可用；
- `POST /api/parse`：提交 BibTeX；
- `GET /api/papers`：读取网页 Library 中已有的 PDF；
- `POST /api/verify/bib`：验证 Bib metadata；
- `POST /api/verify`：验证单条 claim。

## 当前预期情况

真实 PDF Parser 尚未完全接入，因此部分字段可能返回 `PDF_MISSING`。插件应将其显示为“PDF metadata 暂不可用”，而不是系统错误。

## 验收标准

- 插件能够把 BibTeX 成功提交给后端；
- 插件能够使用网页中已有的 PDF 记录；
- 后端结果能够对应到正确的 citation；
- 用户能够区分真实结果、缺失状态和 Demo 结果；
- 插件不提供 PDF 上传功能；
- 原有 Overleaf 检测和定位功能正常。
