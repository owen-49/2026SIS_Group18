# Claim × 原论文 语义对照 —— 后端交接文档

> 面向：接手前端接线或继续加固后端的组员
> 对应规格：`docs/engine-source-resolver-handoff.md` Part 1（引擎侧已完成，本文档是后端侧的实现说明）
> 状态：后端链路已打通并通过真实 DeepSeek 验收；**前端视图与 Chrome 扩展不在本次范围**

---

## 1. 状态与范围

### 1.1 本次做了什么

一句话：**让 `SourceResolver` 真正跑起来**。引擎侧早就写好了 `SourceResolver` / `Retriever` /
`Verifier.verify_with_retrieval`，但后端没有任何地方把它们串起来，所以用户看不到
"我的 claim 和原文到底怎么说的"。现在补上了这条链路，并新增一个端点。

| 新增 | 位置 |
|---|---|
| 端点 `POST /api/verify/citation` | [routes/verify.py:54](backend/src/routes/verify.py#L54) |
| 5 个响应模型 + `ComparisonStatus` 枚举 | [models.py:297-377](backend/src/models.py#L297-L377) |
| 引用定位（marker → 源论文 → 段落） | [services/source_locator.py](backend/src/services/source_locator.py) |
| 编排（定位 → 检索 → LLM 判定） | [services/citation_comparison_service.py](backend/src/services/citation_comparison_service.py) |
| 缓存的 Embedder 单例 | [engine_adapter.py:73](backend/src/services/engine_adapter.py#L73) |
| 让 `.env` 真正生效 | [config.py:130](backend/src/config.py#L130) |
| 测试隔离（离线、断网） | [tests/conftest.py](backend/tests/conftest.py) |
| 真实 LLM 验收脚本 | [backend/scripts/acceptance_citation_comparison.py](backend/scripts/acceptance_citation_comparison.py) |

### 1.2 有意**不**做

- **不动 `POST /api/verify`** —— 一行没改。新旧两个端点并存，职责不同（见 §1.3）。
- **不做批量端点** —— 前端可以循环调用，每次请求独立；批量需要并发与配额控制，单独排期。
- **不做 `risk_level`** —— 规格里的 `CitationAuditResult` 有这个字段，但它是前端展示层概念，
  不该由后端凭 confidence 硬编码。前端可以用 `confidence` 自行分档。
- **不改 Audit 的任何行为** —— Audit 管"参考文献是否存在"，Verify 管"主张是否被支持"，
  两条线继续互不干扰（见 `docs/backend-audit-handoff.md`）。
- **不修引擎** —— 引擎已冻结，本次只做"吸收"（见 §5）。
- **不做解析回退** —— 规格 §6.3 提到找不到解析结果时可以现场 `parse_document`。没做，理由：
  未解析的 PDF 本来就不会进 catalog；opendataloader 需要 Java 11+ 且单篇要跑几分钟，
  放在 HTTP 请求里不可接受。直接返回 `SOURCE_NOT_AVAILABLE` 并提示先解析。

### 1.3 两个 Verify 的区别

| | `POST /api/verify`（旧） | `POST /api/verify/citation`（新） |
|---|---|---|
| 源论文怎么来 | 调用方直接传 `source_paper_id` | 从 claim 的引用标记（marker）反查 |
| 检索 | 词元重叠排序（词法） | FAISS + MiniLM 向量检索（语义） |
| 取几段 | 1 段 | top-k（默认 5，实际送 LLM 前 3 段） |
| 页码溯源 | 无 | 有（`evidence[].page` / `location`） |
| 无 LLM 时 | 降级为词法判定 | **503 拒绝** |

> 旧端点的词法降级逻辑**保留不动**（`engine_adapter.verify_claim`）。它服务的是旧端点，
> 不影响新端点。

---

## 2. 接口契约

### 2.1 请求

```http
POST /api/verify/citation
Content-Type: application/json
```

```json
{
  "claim": "Self-attention relates different positions of a single sequence.",
  "citation_marker": "\\cite{vaswani2017attention}",
  "manuscript_id": "paper-abc123",
  "claim_id": "claim-9f3c1a2b",
  "k": 5
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `claim` | ✅ | 主张原文。`min_length=1`，两端空白会被 strip；全空白 ⇒ **422** |
| `citation_marker` | ✅ | **原样**取自 `GET /api/papers/{id}/claims` 的 `ExtractedClaim.citation_marker` |
| `manuscript_id` | ❌ | 手稿自身的 paper_id；传入后它会被排除出源论文目录，**避免拿自己当自己的证据** |
| `claim_id` | ❌ | 原样回显，方便批量循环时对账 |
| `k` | ❌ | 取回几段证据，`1..10`，默认 5 |

请求体 `extra="forbid"`：多传字段 ⇒ 422。

### 2.2 响应（200，成功判定）

```json
{
  "claim": "Self-attention relates different positions of a single sequence.",
  "citation_marker": "\\cite{vaswani2017attention}",
  "citation_key": "vaswani2017attention",
  "status": "COMPARED",
  "message": "Compared the claim against 5 passage(s) retrieved from 'Attention Is All You Need'.",
  "claim_id": "claim-9f3c1a2b",
  "cited_source": {
    "source_paper_id": "src-transformer",
    "citation_key": "vaswani2017attention",
    "title": "Attention Is All You Need",
    "authors": ["Vaswani, Ashish"],
    "venue": "NeurIPS", "year": 2017,
    "doi": "10.5555/3295222.3295349",
    "url": null, "database": "Uploaded BibTeX"
  },
  "source_paper_id": "src-transformer",
  "source_document": {
    "total_pages": 1,
    "pages": [{ "page": 1, "heading": null, "paragraphs": ["..."] }],
    "matched_location": { "page": 1, "paragraph_index": 1 }
  },
  "evidence": [
    {
      "passage_text": "Self-attention, sometimes called intra-attention, is an attention mechanism ...",
      "page": 1,
      "similarity": 0.856,
      "rank": 1,
      "location": { "page": 1, "paragraph_index": 1 }
    }
  ],
  "judgement": {
    "verdict": "SUPPORT",
    "confidence": 0.85,
    "rationale": "Passage 1 states verbatim: 'Self-attention, sometimes called intra-attention, ...'"
  }
}
```

### 2.3 ⭐ 双轴语义：`status` 与 `judgement`

**这是整个契约最重要的一条，前端必须照做：**

- `judgement` **只在 `status == "COMPARED"` 时存在**，否则恒为 `null`。
- **`status != "COMPARED"` 意味着"这次没能判定"，绝不意味着"这个 claim 不支持"。**

这条规矩来自仓库既有约定。`docs/backend-audit-handoff.md:90` 写着
"A failed query must not be converted to `NOT_FOUND`"。原因很直白：`NOT_FOUND` 本身
**是一个判定**（"源论文存在，但没有讲这件事"），把"查询失败"塞进 `NOT_FOUND` 就是在
**伪造结论**——用户会以为系统真的读过原文并且没找到支持。

所以响应模型刻意做成 `status` 判别符 + 嵌套 `judgement`，让"没判定"在类型层面
**不可能**被渲染成一个 verdict。

### 2.4 前端渲染规则（照抄即可）

```ts
if (body.status === "COMPARED") {
  // 显示 verdict 徽章 + confidence + rationale + evidence 列表
} else {
  // 显示"未能判定" + body.message，**不要**渲染任何 verdict 徽章
  // 如果有 cited_source，仍然显示"这条引用指向哪篇论文"
}
```

---

## 3. 八个 `status` 判定表

| `status` | HTTP | 含义 | 前端建议文案 |
|---|---|---|---|
| `COMPARED` | 200 | 判定完成，`judgement` 存在 | 正常展示判定 |
| `NO_BIBLIOGRAPHY` | 200 | 库里没有**唯一一份**已完成的 `.bib` | "请先上传这份手稿的参考文献（.bib）" |
| `MARKER_UNSUPPORTED` | 200 | 该标记形态无法定位（数字型 `[1]`） | "请改用 BibTeX key 指定引用" |
| `REFERENCE_NOT_FOUND` | 200 | 文献表里没有这个 key | "文献表中找不到这条引用" |
| `REFERENCE_AMBIGUOUS` | 200 | 命中多条，拒绝猜测 | "这条引用对应多篇文献，请消歧" |
| `SOURCE_NOT_AVAILABLE` | 200 | 找到了文献，但库里没有匹配的**已解析 PDF** | "请上传并解析被引论文的 PDF" |
| `SOURCE_EMPTY` | 200 | 定位成功，但源论文解析出零段落 | "被引论文没有可用正文" |
| `LLM_FAILED` | 200 | LLM 报错或返回了无法使用的标签 | "模型未能给出判定，请重试" |

> **`LLM_FAILED` 与 `SOURCE_EMPTY` 仍会返回 `evidence` 和 `source_document`**
> （只要它们已经拿到）。先例是 audit 把查询失败映射成报告内的 `LOOKUP_FAILED` 状态而不是
> 抛异常——我们确实拿到了源论文和证据，用 5xx 把它们丢掉是净损失。

### 3.1 状态优先级是固定的

同一个 marker 的答案**不随库里上传了什么而变**：

1. marker 形态无法解析（数字型）→ `MARKER_UNSUPPORTED`
2. 没有唯一 `.bib` → `NO_BIBLIOGRAPHY`
3. 文献表查不到 / 命中多条 → `REFERENCE_NOT_FOUND` / `REFERENCE_AMBIGUOUS`
4. 文献存在但无匹配 PDF → `SOURCE_NOT_AVAILABLE`

所以 `[1]` 在空库里和在满库里都返回 `MARKER_UNSUPPORTED`，行为可预测。

### 3.2 两个 HTTP 错误

| 情况 | HTTP | 响应体 |
|---|---|---|
| 请求校验失败（claim 空、k 越界、多余字段） | **422** | FastAPI 标准校验错误 |
| 没有配置任何 LLM API key | **503** | `{"detail": {"code": "LLM_NOT_CONFIGURED", "message": "..."}}` |
| 其他内部故障 | **500** | `{"detail": {"code": "COMPARISON_FAILED", "message": "..."}}` |

> ⚠️ **已知不一致**：空的 `claim` 返回 **422**（Pydantic 校验），而旧的 `/api/verify`
> 对手写检查返回 **400**。新端点选择让校验错误统一走 422（附带的 OpenAPI schema 也是这么写的）。
> 如果前端想统一处理，按 `status_code >= 400` 分支即可。

> **503 而不是降级**：如果放行并传 `client=None`，引擎的 `Verifier.verify` 会返回
> `NOT_FOUND, confidence=0.0, "Mock mode: no LLM client provided."` —— 一个**伪造的
> `NOT_FOUND` 冒充真实判定**。缺 key 是部署故障，应当响亮地拒绝。
> 另外 503 在**做任何 embedding 之前**就返回了（快速失败），不会白烧 4 秒 CPU。

---

## 4. 为什么收 marker 而不是 bib key

`docs/engine-source-resolver-handoff.md` §3 的方案 A 建议请求直接传干净的 bib key。
**这里有意偏离了**，理由：

`GET /api/papers/{id}/claims` 产出的 `ExtractedClaim.citation_marker` 有三种形态：

| 形态 | 例子 | 有干净的 key 吗 |
|---|---|---|
| LaTeX | `\cite{wei2022emergent}` | 有 |
| 数字 | `[1]`、`[1, 2]` | **没有**（是手稿自己参考文献表的序号） |
| 作者-年份 | `(Smith, 2020)` | **没有**（有损） |

对数字型 marker 根本不存在"干净的 key"，对作者-年份型也有损。所以契约上用**两个不同字段**
把两个概念分开：

- 请求 `citation_marker` —— **原始**标记，原样传入
- 响应 `citation_key` —— **归一化后**的 bib key，可能为 `null`

`locate_source(citation_key)` 保持规格 Task-1 的签名不变，但参数语义是 *marker-or-key*，
归一化发生在 `look_up_citation` 内部：

| marker | 走的路径 | 结果 |
|---|---|---|
| `\cite{key}` / 裸 key | `_find_bib_entry` 的直接匹配分支 | ✅ |
| `(Smith, 2020)` | 年份 + 首作者姓氏分支 | 唯一命中才算成功 |
| `[1]` | 数字正则 fullmatch | ❌ `MARKER_UNSUPPORTED` |

**歧义绝不猜。** `_find_bib_entry` 把"多个匹配"和"无匹配"都折叠成 `None`，所以歧义对它是
不可见的。做法是仍以 `_find_bib_entry` 为准（复用，不重写），**只在 `None` 路径**上跑一个
诊断用的 `_candidate_count()` 来区分文案。代码里明确标注它**仅用于诊断**——
规则漂移最坏只是提示不准，绝不会导致错误解析。

---

## 5. ⚠️ 四个引擎层的坑（必读）

引擎已冻结，本次全部在 backend 侧"吸收"。**如果你要改这条链路，先读完本节。**

### 坑 1：`Verdict(label)` 在 try 块外面 —— 会抛 `ValueError`

[engine/verifier.py:133](engine/engine/verifier.py#L133)

```python
try:
    parsed = json.loads(raw)
    label = parsed.get("label", "NOT_FOUND").upper()
    ...
except (json.JSONDecodeError, AttributeError):
    label = "NOT_FOUND"
    ...

return VerificationResult(verdict=Verdict(label), ...)   # ← 在 try 外面！
```

模型如果答 `"SUPPORTS"`（复数）而不是 `"SUPPORT"`，`Verdict("SUPPORTS")` 会抛
`ValueError` 直接穿透上来。

**吸收方式**：`citation_comparison_service` 用 `except Exception` 包住整个 verifier 调用，
映射为 `LLM_FAILED`（200）。捕获范围**故意宽**——provider SDK 也各有各的异常类型，
这些都不是本服务该泄漏的契约。

**建议的引擎修法**（留待引擎 owner，本次没做）：把 `Verdict(label)` 移进 try，
并在 except 里补一个 `ValueError`。

### 坑 2：空检索会伪造 `NOT_FOUND` —— 不调用 LLM

[engine/verifier.py:159-165](engine/engine/verifier.py#L159-L165)

```python
if not retrieval_results:
    return VerificationResult(verdict=Verdict.NOT_FOUND, confidence=0.0,
                              rationale="No passages retrieved from the source paper.")
```

**根本没调 LLM**，却返回了一个货真价实的 `NOT_FOUND`。

**吸收方式**：调用前断言 `resolved.retrieval` 非空，否则返回 `SOURCE_EMPTY`。
`citation_comparison_service.py` 的模块 docstring 和测试
`test_empty_retrieval_is_never_sent_to_the_llm` 都钉住了这一点
（该测试断言 `llm.calls == []`）。

### 坑 3：JSON 解析失败也变成 `NOT_FOUND`

同一段代码的 `except` 分支把 `label` 设成 `"NOT_FOUND"`，只在 `rationale` 里写
`"Failed to parse LLM response: ..."`。所以模型返回烂 JSON 时，用户会看到一个
`NOT_FOUND` 判定。

**本次不修**：探测它只能靠字符串匹配引擎自己的错误文案，太脆。`rationale` 是**原样**返回给
前端的，用户能看见真实原因，所以不算欺骗。测试
`test_unparseable_json_reply_becomes_a_not_found_verdict` 钉住了现状，**行为变了会是显式失败**。
建议引擎 owner 一起修：解析失败应该抛错或返回明确的失败标记。

### 坑 4：负余弦 —— 不做夹紧会直接 500

`Retriever` 用 `faiss.IndexFlatIP`，配合
[embedder.py:45](engine/engine/embedder.py#L45) 的 `normalize_embeddings=True`，
内积**恰好等于余弦相似度**，而余弦**可以为负**（实测不相关句子 −0.105）。

`ComparisonEvidence.similarity` 有 `ge=0.0` 约束（`MatchResult` 也一样，
[models.py:181](backend/src/models.py#L181)），直接塞进去就是 500。

**吸收方式**：`_clamp_similarity()` 夹到 `[0, 1]`。

> ⚠️ 这个耦合是隐式的：`score` 之所以是余弦，只因为 `encode()` 里写了
> `normalize_embeddings=True`。注释里已写明。**谁去掉了归一化，这里就静默变成内积。**

### 坑 5（额外）：`passage_index` 的 1:1 不变量

`RetrievalResult.passage_index` 是 `build_index(passages)` 那个列表的下标。
证据的页码完全靠这条链路：

```
evidence[].page     ← parsed.paragraphs[passage_index].page_start
evidence[].location ← view.paragraph_locations.get(passage_index)
```

只有当 `source_passages()` 返回的列表与 `parsed.paragraphs` **位置严格一一对应**
（不丢、不重排、不合并）时，页码才是对的。

> ⚠️ **将来谁在 `source_locator.source_passages()` 里加了过滤（比如"跳过空段落"或
> "跳过标题"），所有证据的页码会集体错位，而且不会报错。**
> 空段落被保留成 `""` 就是这个原因，测试 `test_blank_paragraphs_are_normalised_but_never_dropped`
> 钉住了它。

注意 `view.paragraph_locations` 是**稀疏**的（标题和空段落不入表），所以
`location` 可能是 `null`，但 `page` 始终有值。

---

## 6. LLM 配置

### 6.1 `load_dotenv()` —— 这次修好的一个隐形故障

`config.py` 以前**从不调用 `load_dotenv()`**。Docker 靠 `env_file` 注入环境变量所以没事，
但本地 `uvicorn src.main:app` 完全读不到 `.env`——启动日志永远是
`LLM NOT configured`，即使 `.env` 里 key 填得好好的。

现在 [config.py:130](backend/src/config.py#L130) 会加载：

```python
load_dotenv(os.getenv("CLAIMTRACE_ENV_FILE") or find_dotenv(), override=False)
```

- `find_dotenv()` 从 `config.py` 自身向上找，因此**与工作目录无关**，能找到 `claimtrace/.env`
- `override=False` 让**真实环境变量优先于文件**
- `CLAIMTRACE_ENV_FILE` 是逃生舱：指向任意文件即可改读它；**指向空文件（`os.devnull`）
  就是完全关掉 `.env` 加载**

启动后应当看到：

```
[ClaimTrace] LLM ready: deepseek/deepseek-chat
```

### 6.2 ⚠️ `lru_cache` 会把 `None` 也缓存住

`engine_adapter._get_llm_client()` 是 `@lru_cache(maxsize=1)`。
**如果进程启动时没有 key，它会缓存 `None`；之后即使补上 key，不重启也不生效。**
调试"为什么配了 key 还是 503"时先看这一条。

### 6.3 测试必须能脱离 `.env`

`main.py:10` 在**导入时**就执行 `settings = get_settings()` 并据此构建 CORS 中间件。
所以 `conftest.py` 在**模块级**、**导入 app 之前**设了 `CLAIMTRACE_ENV_FILE = os.devnull`。
放在 fixture 里**太晚了**——这是踩过的坑。

`conftest.py` 的 autouse fixture 另外会清掉四个 provider 的 key 并重置缓存，
保证测试**绝不发真实 API 调用**。

### 6.4 其他注意点

- **MiniLM 已在本机缓存**：`~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2`
  （87M），首次运行**不需要联网**。
- **`EMBEDDING_MODEL` 是死配置**：`engine/embedder.py` 把模型名硬编码成
  `all-MiniLM-L6-v2`，`settings.embedding_model` 传不进去。改模型得改引擎。
- **Embedder 缓存了，Retriever 没有**：`Retriever()` 构造要 **4.4 秒**（加载模型），
  而 `build_index(400 段)` 只要 **0.38 秒**。所以 `_get_embedder()` 是 `lru_cache`，
  每次请求 `Retriever(embedder=_get_embedder())`。
  **绝不能缓存 Retriever 本身**——`build_index` 会原地改它，两个线程共享就会出现
  A 请求搜到 B 的索引，**静默错答，不是崩溃**。
- **首个请求约 5 秒**（4.4s 模型加载 + 嵌入），之后每个请求约 1 秒。
  发生在 threadpool worker 内，不阻塞事件循环。Demo 可接受，**不靠启动预热解决**
  （那会给每次启动加 4.4 秒并常驻 90MB）。

---

## 7. 测试与运行

### 7.1 ⚠️ 必须从仓库根目录跑

```bash
cd /Users/owen/Desktop/SIS-2026S2/claimtrace
python -m pytest backend/tests
```

**不要** `cd claimtrace/backend && pytest`。`backend/tests/conftest.py` 第 14 行是
`from backend.src.config import get_settings`，而 `claimtrace-backend` **没有**以 editable
模式安装（只有 `claimtrace-engine` / `claimtrace-parser` 装了），从 `backend/` 里跑会直接
`ModuleNotFoundError: No module named 'backend'`。

> 📌 这一点**推翻了** `docs/engine-source-resolver-handoff.md:226` 里写的
> `cd claimtrace/backend && python -m pytest tests/ -v`。那份文档这一行是错的
> （本次没有改动那份文档，仅在此标注）。

当前结果：**137 passed**（原来 93 项 + 本次新增 44 项），全程离线、无网络。

### 7.2 新增测试

**`backend/tests/test_source_locator.py`**（23 项，纯单测，无 LLM、无 retriever）：
已知 key 命中 / `\cite{}` 与裸 key 等价 / `(Smith, 2024)` 命中 / 两条同年同姓 ⇒
`REFERENCE_AMBIGUOUS` / `[1]` ⇒ `MARKER_UNSUPPORTED` / 0 或非 1 份 `.bib` ⇒
`NO_BIBLIOGRAPHY` / 有文献无 PDF ⇒ `SOURCE_NOT_AVAILABLE` / **一份损坏的 parsed JSON
不影响其他论文** / 1:1 不变量 / 前向依赖的私有 helper 仍然存在。

**`backend/tests/test_citation_comparison_api.py`**（21 项，`client` fixture + `FakeRetriever`
+ `SimpleNamespace` 假 LLM）：happy path / 页码正确 / 假 retriever 收到的段落文本正确 /
claim 与原文真的进了 prompt / 无 key ⇒ **503 且 retriever 从未被构造** / LLM 抛错 ⇒
200 `LLM_FAILED` 且 `evidence` 仍在 / 枚举外标签 `"SUPPORTS"` ⇒ `LLM_FAILED` 不 500 /
**负数相似度 ⇒ 夹到 0.0 不 500** / 空检索 ⇒ `SOURCE_EMPTY` 且 LLM 未被调用 /
claim 空 ⇒ 422 / `extra="forbid"` 生效 / 旧 `/api/verify` 仍在 OpenAPI 里。

> 测试用 `SimpleNamespace` 冒充 `RetrievalResult`，是为了**避免 import torch**。
> 谁把它换成真的 `RetrievalResult`，整个 backend 测试会慢好几秒。

### 7.3 真实 LLM 验收（已跑通）

```bash
cd /Users/owen/Desktop/SIS-2026S2/claimtrace
python backend/scripts/acceptance_citation_comparison.py
```

脚本直接播种 paper library（绕过 PDF 解析——那条路 audit 已经验收过），
然后走**完整真实链路**：MiniLM 嵌入 → FAISS 检索 → 真实 DeepSeek 调用。

2026-09-11 实测（`deepseek/deepseek-chat`）：

| 主张 | 期望 | 实测 | 检索到的最佳段落相似度 |
|---|---|---|---|
| self-attention 关联单个序列的不同位置 | SUPPORT | ✅ SUPPORT (0.85) | 0.856 |
| self-attention 依赖循环连接 | CONTRADICT | ✅ CONTRADICT (0.85) | 0.696 |
| 方法减少 40% 碳排放 | NOT_FOUND | ✅ NOT_FOUND (0.3) | 0.088 |

三例全中，且 rationale 引用了原文的具体句子（不是套话），说明判定确实基于检索到的原文。

### 7.4 端到端手工验收（含真实 PDF 解析）

1. `POST /api/parse` 上传手稿 PDF、它的 `.bib`、以及被引论文的 PDF
2. 等三者都 `COMPLETED`
3. `GET /api/papers/{manuscript_id}/claims` 取一条 `citation_marker`
4. `POST /api/verify/citation`，body 传 `{"claim": <该条 text>, "citation_marker": <该 marker>,
   "manuscript_id": <manuscript_id>}`
5. 确认返回 `COMPARED` + 真实判定，且 `evidence[0].passage_text` 是**人会认同的那一段**

---

## 8. 前端对接

`frontend/src/types/api.ts:144` 已经声明了 `CitationAuditResult`，但**全项目没有任何地方引用它**
（`grep -rn "CitationAuditResult" frontend/src` 只命中类型定义本身）——是给这个功能预留的脚手架。

字段映射（新响应 → 那个旧类型）：

| `CitationAuditResult` | 新响应 | 说明 |
|---|---|---|
| `citation_key` | `citation_key` | 可能是 `null`（未定位成功时） |
| `claim` | `claim` | 直接对应 |
| `verdict` | `judgement.verdict` | ⚠️ `judgement` 可能为 `null`，见下 |
| `confidence` | `judgement.confidence` | 同上 |
| `comparison_rationale` | `judgement.rationale` | 同上 |
| `claim_id` | `claim_id` | 直接对应 |
| `cited_source` | `cited_source` | 直接对应（同 `IdentifiedSource`） |
| `source_document` | `source_document` | 直接对应（同 `SourceDocument`） |
| `source_passage` | `evidence[0].passage_text` | 取最佳证据 |
| `source_location.page` | `evidence[0].page` | |
| `source_location.quote` | `evidence[0].passage_text` | |
| `manuscript_location` | ❌ 新响应没有 | 需要前端自己从 `claims` 里带过来 |
| `risk_level` | ❌ 后端不产出 | 前端按 `confidence` 自行分档 |
| `similar_sources` | ❌ 新响应没有 | 预留字段，后端暂不产出 |
| — | `status` | **新增且必须处理**，见 §2.3 |
| — | `evidence[]` | **新增**：完整证据列表（含页码与相似度） |

**建议**：与其复用 `CitationAuditResult`（它假设 verdict 恒存在，与双轴语义冲突），
不如为这个端点新写一个类型，**把 `judgement` 声明为可空**：

```ts
type ComparisonStatus =
  | "COMPARED" | "NO_BIBLIOGRAPHY" | "MARKER_UNSUPPORTED"
  | "REFERENCE_NOT_FOUND" | "REFERENCE_AMBIGUOUS"
  | "SOURCE_NOT_AVAILABLE" | "SOURCE_EMPTY" | "LLM_FAILED";

interface CitationComparisonResponse {
  claim: string;
  citation_marker: string;
  citation_key: string | null;
  status: ComparisonStatus;
  message: string;
  claim_id?: string | null;
  cited_source?: IdentifiedSource | null;
  source_paper_id: string | null;
  source_document?: SourceDocument | null;
  evidence: ComparisonEvidence[];
  judgement: { verdict: Verdict; confidence: number; rationale: string } | null;  // ← 可空
}
```

前端已有的 `.confidence-ring` CSS 和 `demoClaimAudit` mock 数据都还没被引用，可以接上。

---

## 9. 后续可选项

按优先级排序：

1. **【P1】引擎修坑 1 与坑 3** —— `Verdict(label)` 移进 try（+ 捕 `ValueError`）；
   JSON 解析失败不要伪造 `NOT_FOUND`。这两处是**产品承诺层面的**问题：
   "展示证据而非只给结论"的前提是结论本身没被伪造。
2. **【P1】把 `analysis_service` 的私有 helper 提升为公开名** ——
   `source_locator.py` 现在跨模块 import 了 8 个 `_` 前缀的名字
   （`_find_bib_entry`、`_match_pdf_to_bib_entry`、`_load_completed_pdf_catalog` …）。
   同包内可用，但这是隐性耦合：重构 `analysis_service` 时容易忘记还有第二个调用方。
   建议改名去掉下划线，或抽出一个 `citation_resolution.py` 共享模块。
3. **【P2】`_match_pdf_to_bib_entry` 的平局加固** ——
   DOI 命中直接 return，标题相似度用严格 `>`，两篇 PDF 同时 ≥0.65 时会**静默选一个**。
   错源 = 错判定。建议平局时返回 `REFERENCE_AMBIGUOUS`。
4. **【P2】索引缓存** —— 同一篇源论文被多条 claim 引用时，现在每条都要重新
   `build_index`（0.38s / 400 段）。可以按 `paper_id` 缓存**索引与段落列表**，
   但仍然**每次请求新建 Retriever**（或改成无状态的检索函数）。
5. **【P2】批量端点** —— `POST /api/verify/citation/batch`，一次传多条 claim。
   需要先定并发上限和超时，否则会被 LLM 配额拖死。
6. **【P3】`SOURCE_NOT_PARSED` 单列一个状态** —— 现在"文献匹配上了但 PDF 没解析完"
   和"根本没上传 PDF"都折叠成 `SOURCE_NOT_AVAILABLE`。分成两个状态前端能给出更准的提示。
7. **【P3】`k` 的实际语义** —— `k` 只控制返回几段证据，送进 LLM 的永远是前 3 段
   （`top_n=3`，硬编码）。如果想让它可调，要把它也传进 `verify_with_retrieval`。

---

## 附：本次改动的文件清单

**新增**
- `backend/src/services/source_locator.py`
- `backend/src/services/citation_comparison_service.py`
- `backend/tests/test_source_locator.py`
- `backend/tests/test_citation_comparison_api.py`
- `backend/scripts/acceptance_citation_comparison.py`
- 本文档

**修改**
- `backend/src/models.py` —— 仅**追加**（§2 的 5 个模型 + 枚举），原内容未动
- `backend/src/routes/verify.py` —— 仅**追加**第二个 handler，原 `/api/verify` 一字未改
- `backend/src/services/engine_adapter.py` —— 新增 `_get_embedder()`，原有函数未动
- `backend/src/config.py` —— `_load_settings()` 增加 `load_dotenv()`
- `backend/pyproject.toml` —— 显式声明 `python-dotenv>=1.0.0`
- `backend/tests/conftest.py` —— ⚠️ **改了这个文件**：模块级关掉 `.env` 加载 +
  autouse fixture 清空 provider key。**这是安全前置**：没有它，`load_dotenv()` 会让
  现有测试发起**真实 API 调用**（联网、不确定、会计费）。
