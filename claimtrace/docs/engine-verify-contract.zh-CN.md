# Engine Verify 输入/输出契约

> **读者**：任何调用 `engine.verifier.Verifier` 的人——后端服务的作者、审计流水线的
> 维护者、以及将来写新消费者的人。
>
> **一句话**：`JUDGED` 是唯一带 verdict 的状态。**其余状态一律表示"这条主张没有被判定"，
> 绝不表示"这条主张不成立"。**
>
> **本次改动**：只加固 engine 的失败路径与调用方的状态映射。**没有**新增 `Verdict` 成员，
> **没有**改 `/api/verify` 的响应形状或状态码，**没有**动网页或浏览器插件。
>
> **更新（2026-09-19）**：§6.2 里那条"`/api/verify` 上失败仍表现为正常判定"的注脚
> **已经不再成立**。该端点的模型失败现在以 **HTTP 503 + 结构化 code** 上报，**响应形状仍然没改**
> （失败走的是标准错误信封，不是 `VerifyResponse`），前端与插件仍然一字未动。
> §6.2 已按当前行为重写，§7 表格同步。

---

## 1. 范围与读者

本文档描述 [engine/verifier.py](../engine/engine/verifier.py) 中两个公开方法的
**输入契约**与**输出契约**，以及后端当前对它的映射方式。

它存在的理由是一个产品诚信缺陷：加固之前，`Verifier` 在 **7 条路径**上把
"我没能判断" 呈现成 "我判断了"，其中两条**完全不调用 LLM** 就返回一个货真价实的
`NOT_FOUND`。`NOT_FOUND` 是一个**判定**（"源论文存在，但没谈到这件事"），所以那不是降级，
是**伪造发现**。仓库早有明文禁令：

> A failed query must not be converted to `NOT_FOUND`.
> —— [audit-contract.md](audit-contract.md) §2「The rule the rest of the repository quotes」

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
命名沿用仓库既有的 SCREAMING_SNAKE 约定（`LOOKUP_FAILED` / `LLM_FAILED` /
`SOURCE_EMPTY`）。

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

### 6.2 `POST /api/verify`（既有端点，已无客户端）—— 未判定以失败上报

**这个端点的响应契约里没有表达"未判定"的位置。** `VerifyResponse.verdict` 是必填的
`VerdictEnum`，而 `NOT_FOUND` **本身就是一个判定**（"源文献存在，但没谈到这件事"），
所以往这个字段里塞任何值都是伪造发现。

**因此未判定不走响应体，改走 HTTP 状态码**——响应**形状**一个字节都没改：

```http
503 Service Unavailable
{"detail": {"code": "<VerificationStatus>", "message": "<Engine 的 rationale>"}}
```

[engine_adapter.py](../backend/src/services/engine_adapter.py) 在
`result.status is not VerificationStatus.JUDGED` 时抛 `ClaimNotJudgedError`，
[routes/verify.py](../backend/src/routes/verify.py) 把它映射成上面的响应。

| Engine 路径 | 从前的 adapter 输出 | 现在 | HTTP |
|---|---|---|---|
| `JUDGED` | 模型判定 | 相同 | 200 |
| `NO_EVIDENCE` | 伪 `SUPPORT` / `NOT_FOUND` + conf 0.2 | `ClaimNotJudgedError` | 503 `NO_EVIDENCE` |
| `MODEL_ERROR` | 同上 | 同上 | 503 `MODEL_ERROR` |
| `INVALID_LABEL` | 同上 | 同上 | 503 `INVALID_LABEL` |
| `INVALID_RESPONSE` | 同上 | 同上 | 503 `INVALID_RESPONSE` |
| **未配置 client** | 词法基线（有文档的降级模式） | **不变** | 200 |

`code` **直接用 Engine 的 `VerificationStatus` 取值**，而不是折叠成一个笼统的码：
§3 的表里每种状态对应不同的修法，丢掉这个区别就等于丢掉可操作性。
`message` 放 rationale 原文，理由与 §6.1 相同。这两个字段也正好是前端
`readResponse`（[client.ts:11-29](../frontend/src/api/client.ts#L11-L29)）已经认识的形状。

> **仍然不要靠给 `Verdict` 加成员来"修"这件事**——那会同时打破 §3.1 里的三个消费者。
> **失败由判别符表达，不由 verdict 表达**；这个端点没有判别符字段，所以用状态码。

三个实现上的要点（都很容易写错，写错了测试仍可能通过）：

1. **`ClaimNotJudgedError` 刻意不继承 `EngineAdapterError`。** 后者会被
   `verification_service` 规范化成通用的 500 `"Unable to verify the claim."`，
   把 code 与 rationale 一起丢掉。它也因此**故意缺席** service 里那个 except 元组。
2. **抛出点在 `try` 之外。** 那个 `except Exception` 是给"Engine 抛了它自己没有建模成状态的
   东西"用的安全网；抛出点若在 `try` 内，会被自己的安全网捕获并重新包装成 adapter 故障。
3. **`VerdictEnum(result.verdict.value)` 也移到了安全网之外。** 从前枚举镜像不一致会被吞成
   一个伪造判定；现在它会响亮地失败。这条闭集契约在两个包里都有测试钉着
   （`test_verdict_is_still_a_closed_four_member_set`），不一致属于代码缺陷。

**无 client 时的词法基线不在这次改动内。** 它是端点**被公告的**降级模式（启动横幅
`"Single Verify uses a lexical baseline"`，rationale 写 `"Local evidence analysis:"`），
也是 CI 与无 key 本地开发的路径。但要注意：它输出的 `NOT_FOUND` 同样是一个判定，
只是这个模式是公开声明过的，且不掩盖任何模型失败。要改它是另一件事。

**这个端点已无客户端。** 前端的 `verifyClaim` 全仓无调用者（`VerifyPage` 用的是 §6.1 的
`/api/verify/citation`），浏览器插件从不调它，`frontend/tests/verify-citation.spec.mjs` 里
还有一句 `'Legacy Verify must not be called'`。**新集成请用 §6.1 的端点。**

`NO_CLIENT` 在 `/api/verify` 上**不可达**（adapter 只在 `_get_llm_client()` 非 `None`
时才调 verifier），防御分支而已。

---

## 7. 有意不做 / 已知限制

| # | 项 | 为什么不做 |
|---|---|---|
| R3 | **engine 的超时与重试**。SDK 默认 `read=600s` × 3 次尝试，同步 handler 里最坏 30 分钟 | 改进方式已明确（`Verifier.__init__(timeout=...)` 透传给 `create(timeout=...)`，默认 `None` 不影响现有调用），但它会改变真实链路的行为特征，应与可观测性一起做，不混进本次 |
| R4 | **`confidence` 仍是硬编码档位** | 改了会动验收结果（§4.1） |
| —— | **`/api/verify` 无 client 时的词法基线仍会产出判定** | 它是被公告的降级模式，且 CI 与无 key 本地开发依赖它；改它要同时动启动横幅、模块 docstring 与测试（§6.2） |
| —— | **`/api/verify` 的 503 是客户端没见过的状态码** | 该端点目前零消费者；且失败信封与 `/api/verify/citation` 的 503 同形（§6.2） |
| —— | **不给 `Verdict` 加成员** | 会打破三个包外消费者（§3.1） |
| —— | **不动网页 / 浏览器插件** | 需求明文约束 |

---

## 8. 测试与验收

```bash
# engine 套件 —— engine/ 目录内外都可以（engine 以 editable 安装，测试只 import engine.*）
cd /Users/owen/Desktop/SIS-2026S2/claimtrace/engine && python -m pytest tests -q
# 也可：cd claimtrace && python -m pytest engine/tests -q
# （早期本文说必须从根跑，且因 test_google_scholar_lookup.py 的 backend import 会
#   collection error —— 那个文件已删除，这条限制不复存在）

# 后端套件 —— 必须从 claimtrace/ 跑（conftest 里是 from backend.src.main import app）
cd /Users/owen/Desktop/SIS-2026S2/claimtrace && python -m pytest backend/tests -q

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
| [backend/src/services/engine_adapter.py](../backend/src/services/engine_adapter.py) | 显式状态分支（2026-09-19 起改为抛 `ClaimNotJudgedError`，见 §6.2） |
| [backend/src/services/citation_comparison_service.py](../backend/src/services/citation_comparison_service.py) | 状态映射；模块 docstring 与内联注释更新（原注释称"`Verdict(label)` 在 try 外"，已不成立） |
| [backend/tests/test_citation_comparison_api.py](../backend/tests/test_citation_comparison_api.py) | 1 项改写 + 5 项新增 + 2 处 docstring |
| [backend/tests/test_engine_adapter.py](../backend/tests/test_engine_adapter.py) | 新增 4 项 |
| [scripts/llm_smoke_test.py](../scripts/llm_smoke_test.py) | 状态优先输出；打印 `source_text_used`；未判定则 `exit(1)` |
| [docs/citation-comparison.zh-CN.md](citation-comparison.zh-CN.md) | §5 坑 1/2/3 由"后端绕过"改为"引擎已修"；§7.2/§7.3 同步 |
| 本文档 | 新建 |

**前端与浏览器插件：一字未动。**
