# Bib 后端交接文档

> 交接人：Siyuan Sun
>
> 交接对象：Hongyang Chen
>
> 更新时间：2026-08-29
>
> 分支：`backend/siyuan-bib-integration`

## 1. Siyuan 已完成

- `.bib` 文件通过 `POST /api/parse` 上传后立即进行真实解析。
- 后端复用 `engine.bib_parser.parse_bib_file()`，不再返回假的 `entry_count`。
- 解析结果以 JSON 保存，后端重启后仍可按 `bib_paper_id` 读取。
- `POST /api/verify/bib` 已移除硬编码 stub，改为读取真实 Bib entries。
- 后端复用 `engine.bib_verifier.verify_all_entries()` 返回逐条、逐字段结果。
- 已加入 PDF Parser 输出到 `PdfMetadata` 的适配入口。
- 已处理空文件、无 Bib entry、找不到 Bib ID、错误文件类型和缺失 PDF metadata。
- 保留 `POST /api/parse/bib` 作为旧两步调用方式的兼容入口；它与 `/api/parse` 使用同一个真实解析服务。

## 2. API 使用方式

### 上传并解析 BibTeX

```http
POST /api/parse
Content-Type: multipart/form-data

file=references.bib
```

示例响应：

```json
{
  "paper_id": "8dc26ad0-6177-4fd8-b6fd-8132a545ce2e",
  "status": "completed",
  "file_type": "bib",
  "pages": 0,
  "paragraph_count": 0,
  "entry_count": 3,
  "title": "references"
}
```

### 查询解析结果状态

```http
GET /api/parse/{paper_id}
```

### 验证 BibTeX metadata

```http
POST /api/verify/bib
Content-Type: application/json

{
  "bib_paper_id": "<bib-paper-id>",
  "source_paper_ids": ["<source-pdf-id>"]
}
```

接口会为每一个 Bib entry 返回 `MATCH`、`MISMATCH`、`BIB_MISSING` 或 `PDF_MISSING`。

## 3. 数据保存位置

- 上传原文件：`uploads/{paper_id}.bib`
- 文件索引：`uploads/papers.json`
- 解析后的 entries：`uploads/parsed/bib/{paper_id}.json`
- `papers.json` 中的 `parsed_result_path` 指向 entries JSON。

相关代码：

- `backend/src/services/bib_service.py`
- `backend/src/storage/bib_document_store.py`
- `backend/src/services/bib_verification_service.py`
- `backend/src/services/metadata_adapter.py`
- `backend/src/routes/bib.py`

## 4. 当前预期行为

当前 `backend/src/services/parser_adapter.py` 仍然是 Mock Parser，并且只提供 PDF title、pages 和 paragraphs。

因此：

- PDF title 能与 Bib title 匹配时，title 可以返回 `MATCH` 或 `MISMATCH`。
- authors、year、venue 和 DOI 暂时通常返回 `PDF_MISSING`。
- 找不到对应源 PDF 时，该 Bib entry 返回 `PDF_MISSING`，不会导致接口报 500。

这是当前阶段的正常行为。

## 5. Hongyang 下一步

1. 将 `backend/src/services/parser_adapter.py` 的 Mock Parser 替换为真实 Parser 调用。
2. 在后端 Parser contract 中加入并保存：
   - `authors`
   - `year`
   - `venue`
   - `doi`
3. 更新 `backend/src/services/metadata_adapter.py`，把真实 Parser 字段转换成 `PdfMetadata`。
4. 确认多份源 PDF 与 Bib entry 的 title 匹配效果。
5. 完成插件到后端的 API 调用；插件只处理 `.tex` 和 `.bib`，不处理 PDF。
6. 增加真实 Parser、PDF、Bib 和插件的端到端测试。

请尽量不要重新实现以下内容：

- Bib upload 和 JSON 存储；
- Bib response models；
- `POST /api/verify/bib` 的基础流程；
- `engine.bib_parser` 和 `engine.bib_verifier`。

如果真实 Parser 必须修改共享 model，请先与 Siyuan、Yi Jiang、Zheng Fu 确认，避免多人同时修改 `models.py` 或 `routes/parse.py`。

## 6. 测试

后端测试：

```bash
python -m pytest backend/tests -q
```

Bib Engine 测试：

```bash
python -m pytest engine/tests/test_bib_parser.py engine/tests/test_bib_verifier.py -q
```

完成交接时的结果：

- Backend：33 passed
- Bib Parser/Verifier：67 passed
- Ruff：All checks passed

Bib API 测试位于 `backend/tests/test_bib_api.py`。
