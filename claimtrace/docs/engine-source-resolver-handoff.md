# Engine 新功能对接文档（给 Backend 组员）

> 本文涵盖 engine 新增的两个功能，状态都是 **engine 层已完成、backend 层待接**：
> 1. **SourceResolver**（Part 1）—— 把 claim 的引用自动定位并解析成源论文段落，供 verify 判定。
> 2. **ScholarSearch**（Part 2）—— 在 Google Scholar 上搜索 reference，供 audit 判定文献是否真实存在。
>
> 最后更新：2026-09-08

---

## 1. 这个功能解决什么问题

现有 `/api/verify` 的链路是：**用户手动指定 `source_paper_id`** → 后端加载已解析文档 → overlap 检索 → LLM 判定。

问题：定位 claim 之后，claim 已经带了一个 citation marker（`\cite{wei2022emergent}` / `[1]` / `(Smith, 2020)`），但系统没有「从这个引用自动找到源论文并解析」的能力——这一步目前散落在 `analysis_service` 里，且只解析了**元数据**，没解析**源论文内容**。

`SourceResolver` 补齐这段：**citation_key → 源论文 → 解析段落 → 语义检索证据**，输出可直接喂给 `Verifier.verify_with_retrieval` 做 LLM 判定。

---

## 2. engine 已完成（直接用，不用改）

### 数据类

```python
from engine.source_resolver import SourcePaper, ResolvedSource, SourceResolver

@dataclass
class SourcePaper:
    source_id: str                 # 源论文的唯一标识（如 paper_id）
    title: str | None = None
    metadata: dict = field(default_factory=dict)   # 放 doi/year 等，便于匹配

@dataclass
class ResolvedSource:
    citation_key: str
    resolved: bool                 # False 表示定位或解析失败
    source_id: str | None = None
    title: str | None = None
    passages: list[str] = []       # 解析后的段落
    retrieval: list[RetrievalResult] = []  # 语义检索出的证据段落
    reason: str = ""               # 失败原因
```

### 类

```python
class SourceResolver:
    def __init__(
        self,
        locate: Callable[[str], SourcePaper | None],   # 你要实现
        parse: Callable[[SourcePaper], list[str]],     # 你要实现
        retriever: Retriever | None = None,            # 可省略，用默认
    ): ...

    def resolve(self, claim: str, citation_key: str, k: int = 5) -> ResolvedSource:
        """citation_key → 源论文 → 解析 → 检索证据段落"""
```

**关键**：`locate` 和 `parse` 是两个**由 backend 注入的 callable**，engine 不依赖 backend 的 storage 或 parser 包。这就是你要实现的部分。

---

## 3. backend 要实现的三件事

### Task 1: 实现 `locate`

**签名**：`locate(citation_key: str) -> SourcePaper | None`

**职责**：给定一个引用标识，在论文库里找到对应的源论文，返回 `SourcePaper`；找不到返回 `None`。

**citation_key 的语义**：就是 claim 的引用标识，可能是：
- BibTeX key（`wei2022emergent`）
- LaTeX marker（`\cite{wei2022emergent}`）
- 数字 marker（`[1]`）
- 作者-年份 marker（`(Smith, 2020)`）

**复用现有代码**：`analysis_service.py` 里已经有这套逻辑，直接封装：

```python
# backend/src/services/source_locator.py（新文件，建议放这里）
from engine.source_resolver import SourcePaper
from .analysis_service import _find_bib_entry, _match_pdf_to_bib_entry, _load_completed_pdf_catalog
from ..storage.paper_store import list_papers

def locate_source(citation_key: str) -> SourcePaper | None:
    """把引用标识解析成 SourcePaper（复用 analysis_service 的匹配逻辑）。"""
    records = list_papers()
    # 1. 找 bib 条目（citation_key → BibEntry）
    #    注意 _find_bib_entry 需要 entries 和 marker，见下方说明
    # 2. 把 bib 条目匹配到本地 PDF（_match_pdf_to_bib_entry）
    # 3. 返回 SourcePaper(source_id=<pdf paper_id>, title=<pdf title>, metadata={...})
    ...
```

**注意**：`_find_bib_entry(marker, entries)` 接收的是 **marker**（完整引用文本），不是纯 key。而 `SourceResolver.resolve` 传的是 `citation_key`。你需要决定：

- 方案 A：`citation_key` 直接传 bib key，locate 里用 `find_entry_by_key(entries, key)`（engine 的 bib_parser 已提供）
- 方案 B：`citation_key` 传完整 marker，locate 里复用 `_find_bib_entry`

**建议方案 A**：让 `citation_key` 就是干净的 bib key（LaTeX 场景直接从 `\cite{...}` 里提取，数字/作者-年份场景先通过 `analysis_service._citation_keys` 或 `_find_bib_entry` 解析）。这样 locate 最干净，也最贴合 engine 的语义。

### Task 2: 实现 `parse`

**签名**：`parse(source_paper: SourcePaper) -> list[str]`

**职责**：把定位到的源论文解析成段落字符串列表。

**复用现有代码**：两种来源，选其一：

```python
# 来源 1：论文已经解析过（parsed JSON 落盘）——推荐，避免重复解析
from ..storage.parsed_document_store import load_parsed_document

def parse_source(source_paper: SourcePaper) -> list[str]:
    record = get_paper(source_paper.source_id)
    document = load_parsed_document(Path(record.parsed_result_path))
    return [p.text for p in document.paragraphs]

# 来源 2：论文还没解析，调用 parser 现解析
from .parser_adapter import parse_document

def parse_source(source_paper: SourcePaper) -> list[str]:
    record = get_paper(source_paper.source_id)
    document = parse_document(record.paper_id, Path(record.file_path))
    return [p.text for p in document.paragraphs]
```

**推荐来源 1**：论文通常在上传时已经解析落盘，直接读 JSON 比重新跑 parser（尤其 opendataloader-pdf 要 Java）快得多、稳得多。

### Task 3: 串联到 verify 链路

把 `SourceResolver.resolve` 的输出喂给 `Verifier.verify_with_retrieval`：

```python
from engine.source_resolver import SourceResolver
from engine.verifier import Verifier
from engine.llm_client import build_llm_client
from ..config import get_settings

def verify_citation(claim: str, citation_key: str) -> ...:
    settings = get_settings()
    resolver = SourceResolver(locate=locate_source, parse=parse_source)
    resolved = resolver.resolve(claim, citation_key, k=5)

    if not resolved.resolved:
        return {..., "verdict": "NOT_FOUND", "rationale": resolved.reason}

    client = build_llm_client(provider=settings.llm_provider, ...)
    verifier = Verifier(model=settings.llm_model_name)
    result = verifier.verify_with_retrieval(claim, resolved.retrieval, client=client)
    return result
```

**决策点**：新增一个端点，还是改造现有 `/api/verify`？

- 现有 `/api/verify` 收 `{claim, source_paper_id}`（手动指定论文）
- 新流程是 `{claim, citation_key}`（自动定位）

**建议**：新增 `/api/verify/citation`（收 `{claim, citation_key}`），保留现有 `/api/verify` 不动。两者共用底层 verifier，只是「source 从哪来」不同。

---

## 4. 完整数据流

```
claim 已定位（analysis_service.extract_claims 产出，带 citation_marker）
        │
        ▼
citation_key = 从 marker 提取的 bib key（如 "wei2022emergent"）
        │
        ▼
SourceResolver.resolve(claim, citation_key, k=5)
   ├─ locate(citation_key) → SourcePaper     ← Task 1（找源论文）
   │     └─ 复用 analysis_service._find_bib_entry + _match_pdf_to_bib_entry
   ├─ parse(source_paper) → list[str]        ← Task 2（解析成段落）
   │     └─ 复用 parsed_document_store / parser_adapter
   └─ Retriever.retrieve(claim) → RetrievalResult[]  ← engine 已做（语义检索）
        │
        ▼
Verifier.verify_with_retrieval(claim, retrieval, client)   ← engine 已做（LLM 判定）
        │
        ▼
verdict (SUPPORT/PARTIAL/CONTRADICT/NOT_FOUND) + rationale
```

---

## 5. 可复用的现有代码（别重写）

| 已有函数 | 位置 | 用途 |
|----------|------|------|
| `_find_bib_entry(marker, entries)` | `analysis_service.py` | marker → BibEntry |
| `_match_pdf_to_bib_entry(entry, pdfs)` | `analysis_service.py` | BibEntry → 本地 PDF（DOI/标题匹配） |
| `_load_completed_pdf_catalog(records)` | `analysis_service.py` | 加载所有已解析 PDF |
| `find_entry_by_key(entries, key)` | `engine.bib_parser` | 干净的 key → BibEntry |
| `load_parsed_document(path)` | `storage.parsed_document_store` | 读已解析段落 |
| `parse_document(paper_id, file_path)` | `services.parser_adapter` | 现解析 PDF |
| `get_paper` / `list_papers` | `storage.paper_store` | 论文库查询 |

---

## 6. 边界与注意事项

1. **定位失败不是错误**：`locate` 返回 `None` 时，`resolve` 返回 `resolved=False` + `reason`，不要抛异常。前端要能优雅展示「找不到源论文」。

2. **cite_key 语义要统一**：locate 的实现必须清楚 `citation_key` 是 bib key 还是完整 marker。**建议用 bib key**，这样和 engine 的 `find_entry_by_key` 对齐。

3. **parse 优先读已解析 JSON**：opendataloader-pdf 需要 Java 11+，重新解析慢且可能有环境问题。优先 `load_parsed_document`，只有没解析过才 fallback 到 `parse_document`。

4. **Retriever 会重复 embed**：`SourceResolver.resolve` 每次都会 `build_index`（重新 embed 段落）。如果一次 verify 多个 claim，可以考虑缓存。MVP 阶段先不管。

5. **LLM client 别重复构建**：`engine_adapter._get_llm_client` 已经用 `lru_cache` 缓存了 client，新代码里复用它，不要每次 verify 都新建。

---

## 7. 测试方法

engine 层已有测试（`engine/tests/test_source_resolver.py`，4 个用例）。backend 接入后，加测试验证：

```bash
# engine 测试（确认 SourceResolver 本身没问题）
cd claimtrace/engine && python -m pytest tests/test_source_resolver.py -v

# backend 测试（接入后）
cd claimtrace/backend && python -m pytest tests/ -v
```

**backend 验收标准**：
- `locate` 对已知 bib key 返回 `SourcePaper`，对未知 key 返回 `None`
- `parse` 对已解析论文返回非空段落列表
- 端到端：上传论文 + 上传 bib → 对某个 citation 调 `/api/verify/citation` → 返回真实 LLM verdict（非 mock）

---

## 8. 最小可跑示例（伪代码，串联全流程）

```python
# 1. 上传论文（已有）
#    POST /api/parse  → 得到 paper_id（已解析，段落落盘）

# 2. 提取 claim（已有 analysis_service）
#    GET /api/papers/{manuscript_id}/claims → 得到 claim + citation_marker

# 3. 新端点：自动定位源论文并验证
#    POST /api/verify/citation {claim, citation_key}
#    → locate 找到源论文 → parse 出段落 → 检索 → LLM 判定 → verdict
```

这就是 SourceResolver 要接的最后一环。engine 的「引用 → 段落 → 检索」已经就绪，backend 只需补 `locate` 和 `parse` 两个函数。

---

# Part 2: ScholarSearch 对接（audit 文献搜索）

## 1. 功能概述

`engine/scholar_search.py` 是 audit 的「外部文献查找」实现——之前 `bibliography_lookup.py` 的 `BibliographyLookup` Protocol 是空的（返回 `EXTERNAL_LOOKUP_NOT_CONFIGURED`）。这个模块在 Google Scholar 上搜索 reference，判断文献是否真实存在。

它对应 audit 的核心问题：**「这条引用的文献真的存在吗？」**（区别于 verify 的「claim 被源文献支撑吗？」）。

## 2. engine 已完成的 API

```python
from engine.scholar_search import search_scholar, ScholarSearchOutcome, ScholarResult

outcome = search_scholar(
    title="Attention Is All You Need",
    authors=["Vaswani, Ashish"],
    year=2017,
    max_results=3,
)
# outcome.status  → "found" | "ambiguous" | "not_found" | "failed"
# outcome.results → list[ScholarResult]
# outcome.error   → 失败原因（failed 时）
```

`ScholarResult` 字段：`title`, `authors`, `year`, `venue`, `url`。

**查询策略**：精确标题（引号包住）+ 第一作者姓氏 + 年份限定。

## 3. backend 要做的：实现 `BibliographyLookup`

`backend/src/services/bibliography_lookup.py` 里的 Protocol 目前是空的。实现一个 `GoogleScholarLookup`：

```python
# backend/src/services/bibliography_lookup.py（改造）
from engine.scholar_search import search_scholar
from ..audit_models import (
    BibliographicMetadata, ExternalRecord, LookupAttempt, LookupResult, ReferenceEntry,
)
from datetime import UTC, datetime


class GoogleScholarLookup:
    """Resolve references against Google Scholar via the engine module."""

    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        outcome = search_scholar(
            title=entry.metadata.title,
            authors=entry.metadata.authors,
            year=entry.metadata.year,
        )

        attempt = LookupAttempt(
            provider="google_scholar",
            outcome=outcome.status,  # found/ambiguous/not_found/failed 直接对齐
            error_code=("SCHOLAR_SEARCH_FAILED" if outcome.status == "failed" else None),
            detail=outcome.error,
        )

        records = [
            ExternalRecord(
                provider="google_scholar",
                record_id=f"scholar:{r.url or r.title}",  # 需要稳定的 id，见注意事项
                url=r.url or "https://scholar.google.com/",  # ExternalRecord.url 是 HttpUrl 必填
                retrieved_at=datetime.now(UTC),
                metadata=BibliographicMetadata(
                    title=r.title,
                    authors=r.authors,
                    year=r.year,
                    venue=r.venue,
                    doi="",  # Scholar snippet 通常不含 DOI
                ),
            )
            for r in outcome.results
        ]

        return LookupResult(
            outcome=outcome.status,
            records=records,
            attempts=[attempt],
            reason=_reason_for(outcome),
        )
```

**注意**：`LookupResult` 的 validator 有约束——`found` 要求恰好 1 条 record，`ambiguous` 要求 ≥1 条，`not_found` 要求无 record。engine 的 `search_scholar` 已经保证了这些对应关系（found=1 条、ambiguous=多条、not_found=0 条），所以直接映射即可。

## 4. 字段映射速查

| `ScholarSearchOutcome.status` | `LookupResult.outcome` | 后续 `AuditStatus` |
|-------------------------------|------------------------|--------------------|
| `found` | `found` | `VERIFIED` 或 `METADATA_MISMATCH`（由 `compare_external_metadata` 决定） |
| `ambiguous` | `ambiguous` | `NEEDS_REVIEW` |
| `not_found` | `not_found` | `NOT_FOUND` |
| `failed` | `failed` | `LOOKUP_FAILED` |

## 5. 数据流

```
reference entry（title/authors/year）
   → search_scholar()   [engine，Google Scholar]
   → ScholarSearchOutcome
   → GoogleScholarLookup.lookup()   [backend，转 LookupResult]
   → bibliography_audit_service.audit_reference()
   → compare_external_metadata()   [复用 engine 的 bib_verifier 比对元数据]
   → AuditStatus (VERIFIED/MISMATCH/NEEDS_REVIEW/NOT_FOUND/LOOKUP_FAILED)
```

## 6. 已知限制（务必知道）

1. **scholarly 会被 Google 反爬限流**：连续搜索多个 reference 容易触发验证码/block，返回 `failed`。这是免费方案（scholarly）的固有限制。如果 demo 要连续搜很多条，需要 SerpAPI（付费稳定）或代理轮换。`failed` 会正确降级，不会崩。

2. **year 和 venue 可能缺失**：Scholar 的搜索 snippet 有时不给 `pub_year`（显示 `None`）或 `venue` 显示 `"NA"`。这是 scholarly 的限制，不影响核心的 title/authors 匹配。audit 主要靠 title 匹配。

3. **结果不稳定**：同一个查询两次可能返回不同结果（依赖 free-proxy 轮换）。测试时不要断言精确的搜索结果，用 mock（见 §7）。

4. **ExternalRecord.url 是必填的 HttpUrl**：Scholar 的 `pub_url` 可能是相对路径或空。映射时要兜底一个合法 URL。

5. **依赖已加**：`scholarly>=1.7.0` 已加进 `engine/pyproject.toml`，backend 装 engine 时会自动带上。

## 7. 测试方法

engine 层已有测试（`engine/tests/test_scholar_search.py`，7 个用例，用 mock scholarly 不依赖网络）。backend 接入后：

```bash
# engine 测试（确认搜索模块本身没问题）
cd claimtrace/engine && python -m pytest tests/test_scholar_search.py -v

# backend 测试（接入后，用 mock 的 search_scholar）
cd claimtrace/backend && python -m pytest tests/test_bibliography_audit.py -v
```

**backend 验收标准**：
- `GoogleScholarLookup.lookup` 对 `found` 返回 `LookupResult(outcome="found", 1 条 record)`
- 对 `not_found` 返回空 records + `not_found` outcome
- 对 `failed` 返回 `failed` + 明确 error_code

## 8. 真实搜索已验证

2026-09-08 实测（真实网络）：
- `"Attention Is All You Need" + Vaswani` → `ambiguous`（arXiv + NeurIPS 两个版本，正确）
- `"Emergent Abilities of Large Language Models" + Wei` → `found`（1 个结果，正确）

结论：搜索能返回正确的 title/authors，year/venue 依赖 scholarly snippet 的完整度。
