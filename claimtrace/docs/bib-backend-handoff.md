# Bib 功能交接文档（给 Backend 组员）

> 目的：让后端组员拿到就能开工，把 bib 验证的 stub 接成真实实现。  
> 状态：engine 层**已完成**，后端层**待接**，parser 层有一个**依赖缺口**（见 §5）。  
> 最后更新：2026-08-14

---

## 1. 这个功能是什么（30 秒理解）

ClaimTrace 除了验证「论文里的 claim 是否被源 PDF 支撑」外，还有一个**第二层验证**：验证 **`.bib` 文件里的元数据（标题/年份/作者/venue/DOI）是否与源 PDF 第一页印的真实信息一致**。

它抓的是这类错误：
- Google Scholar 导出 `.bib` 时年份错了（bib 写 2023，PDF 是 2024）
- 标题被 LaTeX 转义搞坏
- DOI 指向了 arXiv preprint 而不是正式发表版本
- 作者名拼写错误 / 顺序错误

```
用户上传:
  1. references.bib  → 解析成 N 个 BibEntry
  2. 源论文 PDF      → 提取首页元数据 → PdfMetadata

对每个 BibEntry:
  verify_bib_against_pdf(bib_entry, pdf_meta)
  → 逐字段比对: title / year / authors / venue / doi
  → 每个字段返回 MATCH / MISMATCH / BIB_MISSING / PDF_MISSING
```

---

## 2. 已完成 vs 待完成（一张表看清）

| 层 | 文件 | 状态 | 说明 |
|----|------|------|------|
| engine | `engine/engine/bib_parser.py` | ✅ 完成 | 解析 .bib → `list[BibEntry]` |
| engine | `engine/engine/bib_verifier.py` | ✅ 完成 | 比对 bib vs PDF metadata |
| backend | `backend/src/models.py` | ✅ 完成 | API 的 Pydantic 模型已定义 |
| backend | `backend/src/routes/bib.py` | ⚠️ **stub** | `verify_bib` 是硬编码假数据，要接真 |
| backend | `backend/src/routes/parse.py` | ⚠️ **半成品** | 解析了 bib 但**丢弃了 entries** |
| parser | `parser/parser/pdf_parser.py` | ⚠️ 缺口 | `ParsedPaper.title/authors` 有字段但**未填充** |

**后端组员要做的 4 件事**（详见 §4）：
1. 共享 `_paper_store`（现在是 parse.py 的局部变量，bib.py 访问不到）
2. `parse.py` 存下 bib entries（现在只存了 `entry_count`）
3. `bib.py` 的 `verify_bib` 替换 stub，接真实逻辑
4. 写一个 PDF metadata → `PdfMetadata` 的适配函数（依赖 parser 组）

---

## 3. engine 层已完成的 API（直接 import 用）

### 3.1 解析 bib 文件

```python
from engine.bib_parser import parse_bib_file, BibEntry

entries: list[BibEntry] = parse_bib_file(Path("references.bib"))
# 返回每个条目的结构化信息

entry = entries[0]
entry.key          # "wei2022emergent"
entry.entry_type   # "article" | "inproceedings" | "misc" | ...
entry.title        # "Emergent Abilities of Large Language Models"
entry.authors      # ["Wei, Jason", "Tay, Yi", ...]  ← 统一 "Last, First" 格式
entry.year         # 2022
entry.venue        # journal 或 booktitle
entry.doi          # "10.xxxx/..."
entry.volume / entry.number / entry.pages / entry.url / entry.publisher
```

### 3.2 比对 bib vs PDF 元数据

```python
from engine.bib_verifier import (
    verify_all_entries,
    verify_bib_against_pdf,
    PdfMetadata,
    BibVerificationResult,
    FieldStatus,
)

# PDF 首页提取的元数据（你从 parser 拿到后构造这个对象）
pdf_meta = PdfMetadata(
    title="Emergent Abilities of Large Language Models",
    authors=["Wei, Jason", "Tay, Yi"],
    year=2022,
    venue="Transactions on Machine Learning Research",
    doi="10.1234/tmlr.2022",
)

# 单个比对
result: BibVerificationResult = verify_bib_against_pdf(entry, pdf_meta)
result.has_errors      # bool — 是否有 MISMATCH 字段
result.error_count     # int — MISMATCH 字段数
result.warning_count   # int — BIB_MISSING / PDF_MISSING 字段数
result.summary         # str — 一行总结
result.fields          # list[FieldResult] — 每个字段的比对结果

for f in result.fields:
    f.field_name  # "title" | "year" | "authors" | "venue" | "doi"
    f.bib_value   # bib 里写的
    f.pdf_value   # PDF 里印的
    f.status      # FieldStatus.MATCH / MISMATCH / BIB_MISSING / PDF_MISSING
    f.detail      # 人类可读的解释

# 批量比对（推荐用这个）
results = verify_all_entries(
    bib_entries=entries,                        # list[BibEntry]
    pdf_metadata_map={"wei2022emergent": pdf_meta},  # dict[citation_key, PdfMetadata]
)
```

> 关键：`pdf_metadata_map` 的 key 是 **citation key**（和 `.bib` 里的 key 对应）。如果某个 bib entry 找不到对应的 PDF metadata，`verify_all_entries` 会返回一个 `PDF_MISSING` 的结果（不是崩溃），所以后端可以放心传部分数据。

---

## 4. 后端要做的 4 件事（按顺序）

### TODO 1：把 `_paper_store` 提取成共享模块

**问题**：`_paper_store` 现在定义在 `parse.py` 里，`bib.py` 访问不到。

**做法**：新建 `backend/src/store.py`：

```python
"""In-memory paper store shared across routes.

For now a dict; upgrade to JSON-file persistence in W4-W5 if needed.
See docs/bib-backend-handoff.md §5 for the storage decision.
"""
from pathlib import Path

# paper_id → {file_path, file_type, status, entry_count, bib_entries, pdf_metadata, ...}
paper_store: dict[str, dict] = {}

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
```

然后 `parse.py` 和 `bib.py` 都改成 `from ..store import paper_store, UPLOAD_DIR`，删掉各自局部的定义。

### TODO 2：`parse.py` 存下 bib entries

现在的问题在 [parse.py](backend/src/routes/parse.py) 第 52-58 行——解析了 `entries` 却只用了 `len(entries)`，把结果丢了。

```python
# 现在（丢了 entries）
if file_type == "bib":
    try:
        from engine.bib_parser import parse_bib_file
        entries = parse_bib_file(file_path)
        entry_count = len(entries)
    except Exception:
        entry_count = 0

# 改成（存下来）
bib_entries = []
if file_type == "bib":
    try:
        from engine.bib_parser import parse_bib_file
        bib_entries = parse_bib_file(file_path)
        entry_count = len(bib_entries)
    except Exception:
        entry_count = 0

paper_store[paper_id] = {
    "file_path": str(file_path),
    "file_type": file_type,
    "status": ...,
    "entry_count": entry_count,
    "bib_entries": bib_entries,      # ← 新增，供 bib.py 读取
}
```

> 注意：`from engine.bib_parser import parse_bib_file` 放在 try 里。如果 engine 没装好，`entry_count=0` 但**不会**报 500——保持这个宽容行为，别改成硬失败。

### TODO 3：`bib.py` 的 `verify_bib` 替换 stub

现在 [bib.py](backend/src/routes/bib.py) 的 `verify_bib` 是硬编码的假数据。替换成真实逻辑：

```python
@router.post("/verify/bib", response_model=BibVerifyResponse)
async def verify_bib(request: BibVerifyRequest, req: Request):
    from ..store import paper_store
    from engine.bib_parser import BibEntry
    from engine.bib_verifier import (
        PdfMetadata,
        verify_all_entries,
    )

    # 1. 取 bib entries
    bib_record = paper_store.get(request.bib_paper_id)
    if not bib_record:
        raise HTTPException(status_code=404, detail="Bib file not found.")
    bib_entries: list[BibEntry] = bib_record.get("bib_entries", [])

    # 2. 取每个 source PDF 的 metadata，构造成 PdfMetadata
    pdf_metadata_map: dict[str, PdfMetadata] = {}
    for pid in request.source_paper_ids:
        pdf_record = paper_store.get(pid)
        if not pdf_record:
            continue  # 跳过缺失的 PDF，verify_all_entries 会标记 PDF_MISSING
        pdf_meta = pdf_record.get("pdf_metadata")
        if pdf_meta is None:
            continue
        # pdf_meta 需要是 PdfMetadata 实例，见 TODO 4
        key = pdf_meta.title or pid  # 理想情况用 citation key；见 §5 的缺口
        pdf_metadata_map[key] = pdf_meta

    # 3. 批量验证
    results = verify_all_entries(bib_entries, pdf_metadata_map)

    # 4. 转成 API response
    bib_results = [_bib_result_to_response(r) for r in results]
    error_entries = sum(1 for r in results if r.has_errors)
    matched_entries = len(results) - error_entries

    return BibVerifyResponse(
        bib_paper_id=request.bib_paper_id,
        total_entries=len(results),
        matched_entries=matched_entries,
        error_entries=error_entries,
        results=bib_results,
    )
```

`_bib_result_to_response` 已经写好了，**不用改**，直接复用。

### TODO 4：PDF metadata → `PdfMetadata` 适配函数

这是**唯一的真实依赖**，见 §5。你需要一个函数，从 parser 的 `ParsedPaper` 构造 `PdfMetadata`。建议先写一个**占位版本**，等 parser 组填好字段后自动生效：

```python
# 建议放在 backend/src/services/metadata.py

from engine.bib_verifier import PdfMetadata

def pdf_metadata_from_parsed(parsed_paper) -> PdfMetadata:
    """Construct PdfMetadata from parser's ParsedPaper.

    依赖 parser 组填充 ParsedPaper.title / authors 字段。
    在他们完成之前，这里返回空 metadata —— 所有字段会变成
    PDF_MISSING，功能仍能跑，只是验证结果暂时都是 missing。
    """
    return PdfMetadata(
        title=parsed_paper.title or "",
        authors=parsed_paper.authors or [],
        year=None,          # TODO: parser 组加 year 字段
        venue="",           # TODO: parser 组加 venue 字段
        doi="",             # TODO: parser 组加 doi 字段
    )
```

---

## 5. 依赖缺口（重要，务必读）

**bib 验证依赖 `PdfMetadata`，而 `PdfMetadata` 需要「源 PDF 首页的元数据」，但 parser 组还没实现这个提取。**

现状盘点：

| 想要的东西 | 现在有吗 | 在哪 |
|-----------|:---:|------|
| `PdfMetadata` dataclass（engine 定义） | ✅ | `engine.bib_verifier` |
| PDF 首页的 title / authors 提取 | ⚠️ **字段有、值空** | `parser.pdf_parser.ParsedPaper` 有 `title`/`authors` 字段，但 `parse_pdf()` 没填充 |
| PDF 首页的 year / venue / doi | ❌ 无 | `ParsedPaper` 连字段都没有 |

**这意味着**：
- 后端可以先把整个链路接好（TODO 1-4），用**空 metadata** 跑通
- 跑通后，验证结果里所有字段都是 `PDF_MISSING`（因为 PdfMetadata 是空的）——**这是预期行为，不是 bug**
- 等 parser 组填充 `ParsedPaper.title/authors` 并加上 year/venue/doi 字段后，适配函数自动生效，验证结果变成真的 MATCH/MISMATCH

**你和 parser 组的接口约定**（建议去 Discord 对齐）：
- parser 组要在 `ParsedPaper` 里填充 `title`、`authors`
- 并新增 `year: int | None`、`venue: str`、`doi: str` 字段
- 后端只依赖这 5 个字段，通过 `pdf_metadata_from_parsed()` 这一个适配函数隔离——parser 组改字段，后端只改这个函数

---

## 6. 测试方法

engine 层已有测试，后端接完后跑这些确认没破坏：

```bash
# 1. engine 测试（49 个，应全部通过，或只有 sentence-transformers 下载报错）
cd claimtrace/engine
pip install -e ".[dev]"
python -m pytest tests/test_bib_parser.py tests/test_bib_verifier.py -v

# 2. 后端启动 + 手动验证
cd claimtrace/backend
uvicorn src.main:app --reload
# 打开 http://localhost:8000/docs，手动调:
#   POST /api/parse  (上传 references.bib)  → 拿到 bib_paper_id
#   POST /api/verify/bib  (传 bib_paper_id + source_paper_ids)  → 看结果
```

**后端验收标准（`verify_bib` 接好后）**：
- 上传一个含 3 个条目的 `.bib` → `POST /api/verify/bib` 返回 `total_entries=3`
- 每个条目返回 `fields`，且当前（parser 未完成前）都是 `PDF_MISSING`
- 传一个不存在的 `bib_paper_id` → 返回 404 而不是 500

---

## 7. 快速速查

| 我想知道 | 答案 |
|----------|------|
| bib 解析的入口函数 | `engine.bib_parser.parse_bib_file(Path)` |
| 比对的入口函数 | `engine.bib_verifier.verify_all_entries(entries, pdf_map)` |
| PDF 元数据长什么样 | `engine.bib_verifier.PdfMetadata(title, authors, year, venue, doi)` |
| 状态枚举在哪 | `engine.bib_verifier.FieldStatus`（和 `models.BibFieldStatusEnum` 对应） |
| `_bib_result_to_response` 要改吗 | 不用，已写好 |
| 最大的卡点 | `PdfMetadata` 依赖 parser 组填 `ParsedPaper` 的元数据字段（§5） |
| 存储用数据库吗 | 暂不，`paper_store` dict 够用（见之前数据库讨论） |
