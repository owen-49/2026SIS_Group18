# Engine Verify 输入/输出契约

> **读者**：任何调用 `engine.verifier.Verifier` 的人——后端服务的作者、审计流水线的
> 维护者、以及将来写新消费者的人。
>
> **一句话**：`JUDGED` 是唯一带 verdict 的状态。**其余状态一律表示"这条主张没有被判定"，
> 绝不表示"这条主张不成立"。**
>
> **本次改动**：只加固 engine 的失败路径与调用方的状态映射。**没有**新增 `Verdict` 成员，
> **没有**改 `/api/verify` 的响应形状或状态码，**没有**动网页或浏览器插件。

---

## 1. 范围与读者

本文档描述 [engine/verifier.py](../engine/engine/verifier.py) 中两个公开方法的
**输入契约**与**输出契约**，以及后端当前对它的映射方式。

它存在的理由是一个产品诚信缺陷：加固之前，`Verifier` 在 **7 条路径**上把
"我没能判断" 呈现成 "我判断了"，其中两条**完全不调用 LLM** 就返回一个货真价实的
`NOT_FOUND`。`NOT_FOUND` 是一个**判定**（"源论文存在，但没谈到这件事"），所以那不是降级，
是**伪造发现**。仓库早有明文禁令：

> A failed query must not be converted to `NOT_FOUND`.
> —— [docs/backend-audit-handoff.md:90](backend-audit-handoff.md#L90)

---

## 2. 输入契约

### 2.1 两个方法

```python
Verifier(model: str = "deepseek-chat")

verify(claim: str, source_passage: str, client=None) -> VerificationResult

verify_with_retrieval(
    claim: str,
    retrieval_results: list[RetrievalResult],
    client=None,
    top_n: int = 3,
) -> VerificationResult
```

`verify_with_retrieval` 把检索结果渲染成 SOURCE TEXT 后转交 `verify`，是**后端应当使用的入口**
（它多做了证据过滤与 `best_match` 归因）。`verify` 是底层原语，供已有明文原文的调用方使用。

### 2.2 空白输入

`_has_text()`（[:77](../engine/engine/verifier.py#L77)）的定义是
"是 `str` 且 `.strip()` 后非空"。空白视为**没有输入**，不是"空内容的输入"：

| 输入 | 结果 |
|---|---|
| `claim` 空白 | `NO_EVIDENCE`，不调模型 |
| `source_passage` 空白 | `NO_EVIDENCE`，不调模型 |
| 某条检索结果的 `passage` 空白 | 该条**被丢弃**，且**不占 `top_n` 名额** |
| 所有检索结果的 `passage` 都空白 | `NO_EVIDENCE`，不调模型 |

> ⚠️ 输入校验**先于** client 检查。`verify("", "", client=None)` 报 `NO_EVIDENCE`
> 而不是 `NO_CLIENT`——先报更根本的那个错。

### 2.3 `top_n` 的语义

"**至多** N 段**有文本的**段落"。`top_n <= 0` 或非 `int` 一律按 `0` 处理 → `NO_EVIDENCE`，
**不调模型**（加固前会拿一个空 context 去问模型，然后把它答的 `NOT_FOUND` 当成判定）。

### 2.4 渲染格式

[`_format_passages`](../engine/engine/verifier.py#L82) 逐字节未变：

```
[Passage {rank}, similarity={score:.3f}]
{passage}

---

[Passage {rank}, similarity={score:.3f}]
{passage}
```

顺序即传入顺序（检索排名），**不做重排**。

### 2.5 ⚠️ 继承自 SDK 的超时预算（尚未收紧，见 §7）

`create()` 不带 `timeout=`，因此继承 openai SDK 2.8.1 的默认值：

```
Timeout(connect=5.0, read=600, write=600, pool=600)     # read 预算 600 s
DEFAULT_MAX_RETRIES = 2                                  # 即最多 3 次尝试
```

**在同步 FastAPI handler 里，最坏情况是 30 分钟。** 这不是本次引入的，本次也没修
（见 §7 已知限制 R3）。任何把 `Verifier` 放进请求路径的人都要知道这个数字。

---

## 3. 输出契约与 `VerificationStatus`

### 🔴 `JUDGED` 是唯一带 verdict 的状态

> **其余五个状态一律表示"没有被判定"。它们绝不表示"该主张不成立"，
> 也绝不能被渲染成任何 `Verdict` 成员。**
>
> 换句话说：看到 `MODEL_ERROR` 时，你**不知道**主张是否被支持——你只知道模型没答上来。
> 把这种情况显示成 `NOT_FOUND`，等于告诉用户"我们查过了，源论文没提这件事"，
> 而事实是"我们没查成"。

```python
class VerificationStatus(str, Enum):     # engine/verifier.py:49
    JUDGED           = "JUDGED"            # 唯一带 verdict 的成员
    NO_EVIDENCE      = "NO_EVIDENCE"       # 没有可用证据可判
    NO_CLIENT        = "NO_CLIENT"         # 未配置 LLM
    MODEL_ERROR      = "MODEL_ERROR"       # 调用本身失败
    INVALID_LABEL    = "INVALID_LABEL"     # 回复可解析，但标签缺失/空白/越界
    INVALID_RESPONSE = "INVALID_RESPONSE"  # 回复不是 JSON 对象
```

**六个成员刻意与需求原话一一对应**（"the model fails" / "returns an invalid label" /
"no usable evidence"），因为**每一个对应不同的运维处置**：

| 状态 | 含义 | 该去修什么 |
|---|---|---|
| `JUDGED` | 模型给出了可用标签 | —— |
| `NO_EVIDENCE` | 没有可判的原文 | 检索 / PDF 解析 |
| `NO_CLIENT` | 没给 client | 配置（API key / `.env`） |
| `MODEL_ERROR` | 调用失败（传输 / provider / 超时） | 重试，或查上游 |
| `INVALID_LABEL` | 标签非法 | 提示词 / 模型质量 |
| `INVALID_RESPONSE` | 回复不是 JSON 对象 | provider 未遵守 `response_format`，或传输被截断 |

`INVALID_LABEL` 与 `INVALID_RESPONSE` **分开是有意的**：二者的上游原因与处置完全不同。
命名沿用仓库既有的 SCREAMING_SNAKE 约定（`SCHOLAR_TIMEOUT` / `LOOKUP_FAILED` /
`LLM_FAILED` / `SOURCE_EMPTY`）。

### 3.1 🚫 绝不新增 `Verdict` 成员

`Verdict` 是**闭集**，有三个包外消费者，加成员会四处**静默**出错：

| 消费者 | 加成员后会发生什么 |
|---|---|
| [frontend/src/components/VerdictBadge.tsx:3-11](../frontend/src/components/VerdictBadge.tsx#L3-L11) | `Record<Verdict, string>` 后 `labels[verdict]` **无运行时守卫** → 渲染 `undefined`，且 CSS 类 `verdict-${verdict.toLowerCase()}` 也是错的 |
| [frontend/src/types/api.ts:1](../frontend/src/types/api.ts#L1) | 字面量联合不匹配 |
| [backend/src/models.py:10-14](../backend/src/models.py#L10-L14) | `VerdictEnum` 是镜像；两处 `VerdictEnum(result.verdict.value)` 会抛 `ValueError` |

**失败必须由判别符（`status`）表达，不能由 verdict 表达。** 这条由测试
`TestVerdictEnumContract.test_verdict_is_still_a_closed_four_member_set` 钉住。

---

## 4. 字段表与不变量

```python
@dataclass
class VerificationResult:                # engine/verifier.py:89
    claim: str
    status: VerificationStatus
    verdict: Verdict | None = None
    confidence: float = 0.0
    rationale: str = ""
    best_match: RetrievalResult | None = None
    source_text_used: str = ""
```

| 字段 | 契约 |
|---|---|
| `claim` | 原样回显传入的 claim |
| `status` | **必填**。不是 `VerificationStatus` 实例 → `TypeError` |
| `verdict` | **仅当 `status is JUDGED` 时非 `None`**。其余状态必须是 `None`，否则 `ValueError` |
| `confidence` | **粗档位，不是模型自报的概率**（见下）。失败态**强制 `0.0`** |
| `rationale` | 人类可读解释；失败态写的是**失败原因** |
| `best_match` | "判定所依据的那一段"。**仅 `JUDGED` 时非 `None`** |
| `source_text_used` | **模型实际看到的原文**，逐字节相同。失败态可能为空 |

### 4.1 `confidence` 不是概率

取值只有两档，**硬编码**：`0.85`（`SUPPORT` / `PARTIAL` / `CONTRADICT`）、
`0.3`（`NOT_FOUND`）。提示词**从未**向模型索要置信度。

> 请把它当作"粗档位"渲染，**不要**当成校准过的概率，也不要在 UI 上写成百分比精确值。
> 改进它（让模型自报并按标签校准）会改变验收结果，本次有意不做（§7 R4）。

### 4.2 三层结构性防护

1. **只有两个 classmethod 是正规构造口**：[`judged()`](../engine/engine/verifier.py#L133) 与
   [`failed()`](../engine/engine/verifier.py#L155)。**`failed()` 根本没有 `verdict` 或
   `best_match` 参数**——它**无法**表达一个判定。
2. [`__post_init__`](../engine/engine/verifier.py#L116) 拒绝任何非法组合（手搓也一样）。
3. `verdict` **不再是第二个位置字段**，且 `isinstance(self.status, VerificationStatus)`
   把经典误用 `VerificationResult(claim, Verdict.SUPPORT)` 从"静默的错误答案"
   变成响亮的 `TypeError`。

```python
VerificationResult("c", Verdict.SUPPORT)        # TypeError
VerificationResult(claim="c", status=VerificationStatus.JUDGED)   # ValueError
VerificationResult(claim="c", status=VerificationStatus.MODEL_ERROR,
                   verdict=Verdict.SUPPORT)      # ValueError
VerificationResult.failed(claim="c", status=VerificationStatus.JUDGED, rationale="r")  # ValueError
```

---

## 5. 十一条路径对照表

| # | 路径 | 加固前 | 加固后 | 状态 |
|---|---|---|---|---|
| 1 | `client is None` | `NOT_FOUND` / conf 0.0 / "Mock mode" | 不调模型 | `NO_CLIENT` |
| 2 | `not retrieval_results` | `NOT_FOUND`，**不调模型** | 不调模型 | `NO_EVIDENCE` |
| 3 | `json.JSONDecodeError` | `NOT_FOUND` + rationale | 保留原文于 rationale | `INVALID_RESPONSE` |
| 4 | 缺 `label` 键（`parsed.get("label", "NOT_FOUND")`） | 静默 `NOT_FOUND` | 点名缺字段 | `INVALID_LABEL` |
| 5 | `Verdict(label)` 枚举外（**在 try 之外**） | **未捕获 `ValueError` 穿透** | 回显非法标签 | `INVALID_LABEL` |
| 6 | `raw is None` → `json.loads(None)` → `TypeError` | **穿透** | 守卫 `choices[0].message.content` 的 `AttributeError`/`IndexError` | `INVALID_RESPONSE` |
| 7 | `create(...)` 抛错 | **任何异常直接穿透** | 包 `try/except Exception` | `MODEL_ERROR` |
| 8 | 硬编码 confidence | `0.85` / `0.3` | **取值不变**；失败态强制 `0.0` | —— |
| 9 | `top_n <= 0` | 空 context，**仍调模型** | 不调模型 | `NO_EVIDENCE` |
| 10 | 纯空白段落 | context 只剩 `[Passage 1, similarity=0.000]` 表头 → 模型答 `NOT_FOUND` | 先滤空白再切 `top_n`；空白段不占名额 | `NO_EVIDENCE` |
| 11 | 空白 `claim` / 空白 `source_passage` | 照建 prompt 并调模型 | `_has_text()` 前置守卫 | `NO_EVIDENCE` |

**唯一一处放宽而非收紧**：标签做 `strip().upper()` 归一
（[:353](../engine/engine/verifier.py#L353)）。`"  support "` / `"SUPPORT\n"` 会被接受为
`SUPPORT`。这是**有意的**——尾随空白不是模型失败，不该让整条链路报错。
`"SUPPORTS"` 仍然正确地是 `INVALID_LABEL`。

---

## 6. 后端映射

### 6.1 `POST /api/verify/citation`（claim 对照，新端点）

[citation_comparison_service.py:214-252](../backend/src/services/citation_comparison_service.py#L214-L252)

| Engine 状态 | `ComparisonStatus` | HTTP |
|---|---|---|
| `JUDGED` | `COMPARED` + `judgement` | 200 |
| `NO_EVIDENCE` | `SOURCE_EMPTY` | 200 |
| `NO_CLIENT` / `MODEL_ERROR` / `INVALID_LABEL` / `INVALID_RESPONSE` | `LLM_FAILED` | 200 |

`message=result.rationale` 是**承重的**：它让引擎的具体原因（比如非法标签的字面值）
可见，而不是被折叠成一个 code。这是新端点**唯一**消费者，映射干净。

### 6.2 `POST /api/verify`（既有端点）—— 诚实的注脚

**这个端点的响应契约里没有表达"未判定"的位置。** `VerifyResponse.verdict` 是必填的
`VerdictEnum`，去掉它需要前端可见的失败表示——而那些约束（"不要改网页或插件接口"）
不允许。所以：

> ⚠️ **在 `/api/verify` 上，模型调用失败仍然表现为一个正常的 `SUPPORT` / `NOT_FOUND`。
> 只有 `rationale` 泄露了失败**（`"LLM verification failed (...); mock fallback used."`）。
>
> **不要靠给 `Verdict` 加成员来"修"这件事**——那会同时打破 §3.1 里的三个消费者。
> 真正的修法是给这个端点一个前端可见的失败表示，而那是一次前端改动。

加固后的行为：显式分支到端点**既有的、有文档的**词重叠降级路径
（[engine_adapter.py:124-137](../backend/src/services/engine_adapter.py#L124-L137)），
`rationale` 文案**逐字保留**以免前端字符串失配。

**逐行等价性**（响应形状 / 状态码 / 枚举取值均不变）：

| Engine 路径 | 加固前 adapter 输出 | 加固后 | 等价？ |
|---|---|---|---|
| 合法标签 | 模型判定 | 相同 | ✅ |
| 枚举外标签 | 词重叠降级（经 `ValueError`） | 词重叠降级（显式分支） | ✅ 同 verdict 同 confidence，仅 rationale 文本更具体 |
| `json.loads(None)` → `TypeError` | 词重叠降级 | 词重叠降级 | ✅ |
| `create()` 抛错 | 词重叠降级 | 词重叠降级 | ✅ |
| **坏 JSON 回复** | 模型派生的 `NOT_FOUND` | 词重叠降级 | ❌ **有意变化** |
| **空白原文** | 拿空 source 去问模型 | 词重叠降级，不调模型 | ❌ **有意变化** |

两处变化都是拿"从未被证成的判定"换成端点**已有的、有文档的**降级路径。
**方向性风险**：坏 JSON 回复在词重叠 ≥ 0.2 时可能从伪 `NOT_FOUND` 变成伪 `SUPPORT`。
这与该端点对网络错误、非法标签的既有降级行为一致，但值得知情。

`NO_CLIENT` 在 `/api/verify` 上**不可达**（adapter 只在 `_get_llm_client()` 非 `None`
时才调 verifier），其分支纯属防御。

---

## 7. 有意不做 / 已知限制

| # | 项 | 为什么不做 |
|---|---|---|
| R3 | **engine 的超时与重试**。SDK 默认 `read=600s` × 3 次尝试，同步 handler 里最坏 30 分钟 | 改进方式已明确（`Verifier.__init__(timeout=...)` 透传给 `create(timeout=...)`，默认 `None` 不影响现有调用），但它会改变真实链路的行为特征，应与可观测性一起做，不混进本次 |
| R4 | **`confidence` 仍是硬编码档位** | 改了会动验收结果（§4.1） |
| —— | **`/api/verify` 没有可见的失败表示** | 需要前端改动，超出本次范围（§6.2） |
| —— | **不给 `Verdict` 加成员** | 会打破三个包外消费者（§3.1） |
| —— | **不动网页 / 浏览器插件** | 需求明文约束 |

---

## 8. 测试与验收

```bash
# engine 套件 —— 必须从仓库根跑（从 engine/ 跑会 collection error：
# tests/test_google_scholar_lookup.py 要 import backend.src.audit_models）
cd /Users/owen/Desktop/SIS-2026S2/claimtrace && python -m pytest engine/tests -q
#   基线 95 passed → 加固后 141 passed

# 后端套件 —— 同样必须从仓库根（conftest 里是 from backend.src.main import app）
cd /Users/owen/Desktop/SIS-2026S2/claimtrace && python -m pytest backend/tests -q
#   基线 137 passed → 加固后 150 passed

# 离线保证：无网络、无 key 也必须全绿
cd /Users/owen/Desktop/SIS-2026S2/claimtrace && \
  env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY -u GEMINI_API_KEY -u ANTHROPIC_API_KEY \
  python -m pytest backend/tests engine/tests -q

# 被加固文件的 lint
cd /Users/owen/Desktop/SIS-2026S2/claimtrace/engine && \
  ruff check engine/verifier.py tests/test_verifier.py

# 真实 LLM 验收（不进 CI；需要 claimtrace/.env 里有 key）
cd /Users/owen/Desktop/SIS-2026S2/claimtrace && python scripts/llm_smoke_test.py
cd /Users/owen/Desktop/SIS-2026S2/claimtrace && python backend/scripts/acceptance_citation_comparison.py
```

后者（`llm_smoke_test.py`）的通过标准**不只是"没崩"**：每条 `JUDGED` 结果都打印
**非空**的 `source_text_used`——这是"检索到的原文确实传入模型"在人类可见层面的形式。
任一条没到达 `JUDGED`，脚本 `exit(1)`。

### 8.1 关键测试

| 测试 | 钉住什么 |
|---|---|
| `TestPromptPlumbing::test_passages_land_in_the_source_slot_not_the_claim_slot` | **原文确实进了模型**：用哨兵串断言段落落在 prompt 的 SOURCE 槽**内**，而不只是"出现在 prompt 某处" |
| `TestVerdictEnumContract::test_verdict_is_still_a_closed_four_member_set` | `Verdict` 是闭集 |
| `TestVerificationResultInvariant`（6 项） | 三层结构性防护 |
| `TestFailurePathsNeverFabricate`（14 项） | 每条失败路径各自的状态 |
| `TestNoFailurePathProducesAVerdict`（3 项） | **字面编码需求**：12 个失败场景全部 `status is not JUDGED`、`verdict is None`、`confidence == 0.0`、`best_match is None` |
| `test_unusable_model_replies_are_never_reported_as_compared`（参数化 6 例） | 任何不可用的模型回复都不得看起来像判定 |
| `test_blank_source_never_reaches_the_model` | 空白原文永不抵达模型（`calls == []`） |

---

## 9. 变更文件清单

| 文件 | 改动 |
|---|---|
| [engine/engine/verifier.py](../engine/engine/verifier.py) | `VerificationStatus`、`VerificationResult` 重构、两个方法重写、模块 docstring。**`ENTAILMENT_PROMPT` 渲染结果逐字节不变**（sha256 `bfdc28a9…`，895 bytes） |
| [engine/tests/test_verifier.py](../engine/tests/test_verifier.py) | 全量重写，50 项 |
| [backend/src/services/engine_adapter.py](../backend/src/services/engine_adapter.py) | 显式状态分支；`rationale` 文案逐字保留 |
| [backend/src/services/citation_comparison_service.py](../backend/src/services/citation_comparison_service.py) | 状态映射；模块 docstring 与内联注释更新（原注释称"`Verdict(label)` 在 try 外"，已不成立） |
| [backend/tests/test_citation_comparison_api.py](../backend/tests/test_citation_comparison_api.py) | 1 项改写 + 5 项新增 + 2 处 docstring |
| [backend/tests/test_engine_adapter.py](../backend/tests/test_engine_adapter.py) | 新增 4 项 |
| [scripts/llm_smoke_test.py](../scripts/llm_smoke_test.py) | 状态优先输出；打印 `source_text_used`；未判定则 `exit(1)` |
| [docs/citation-comparison-backend-handoff.zh-CN.md](citation-comparison-backend-handoff.zh-CN.md) | §5 坑 1/2/3 由"后端绕过"改为"引擎已修"；§7.2/§7.3 同步 |
| 本文档 | 新建 |

**前端与浏览器插件：一字未动。**
