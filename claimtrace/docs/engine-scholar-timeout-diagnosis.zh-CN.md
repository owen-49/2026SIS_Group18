# Google Scholar 30 秒超时：诊断与建议

> **读者**：Audit 集成负责人（PR #27 的提问者）。
> **问题**：live Google Scholar 查询稳定 30 s 超时，返回 `LOOKUP_FAILED / SCHOLAR_TIMEOUT`。
> 这是"预期中的 Scholar/网络封锁"，还是"需要改代码"？
>
> **结论**：**两者都是，但不对称——外部封锁是触发器，代码缺陷是放大器。**
> 后者把一个"可诊断、有界"的封锁，变成了"永久、且被贴错标签"的 30 秒超时。
>
> **本次只诊断，未改任何代码。** 第 7 节是建议的修法，留给决策。
>
> ⚠️ **本诊断是纯静态分析（阅读 scholarly 1.7.11 源码）+ 对已有 artifact 的推理，
> 没有做任何联网复现。** 第 8 节列出了一个能一次性定性的一行实验。

---

## 1. 证据：`SCHOLAR_TIMEOUT` 是必然结果，不是偶发

`live/live-evidence.json`（2026-09-14T05:50:41Z）：

| case | entries | status | error_code | elapsed |
|---|---|---|---|---|
| `references.bib` | 1 | `LOOKUP_FAILED` ×1 | `SCHOLAR_TIMEOUT` ×1 | **30.25 s** |
| `manuscript.pdf` | 2 | `LOOKUP_FAILED` ×2 | `SCHOLAR_TIMEOUT` ×2 | **61.55 s** |

两条推理：

1. `61.55 ≈ 2 × 30 + 2 s 节流` ⇒ **每一次查询都烧满整个 deadline**，不是"偶尔慢"。
   （那 2 s 对应 scholarly `_navigator.py:112-113` 每次请求前 `random.uniform(1,2)` 的固定节流。）
2. 现场**只有** `SCHOLAR_TIMEOUT`，**从未出现** `SCHOLAR_WORKER_FAILED`。
   `SCHOLAR_WORKER_FAILED` 由 `subprocess.CalledProcessError` / `OSError` / `ValueError` 触发
   （[bounded_scholar_lookup.py:71-75](../backend/src/services/bounded_scholar_lookup.py#L71-L75)），
   即"worker 没起来或崩了"。它没出现 ⇒ **worker 成功启动，并成功 import 了 scholarly 与 engine**，
   从而排除了"模块路径 / cwd 错"那一整类 bug。

---

## 2. 缺陷一：`set_retries(2)` 约束不住 scholarly（源码层证实）

[engine/engine/scholar_search.py:139-142](../engine/engine/scholar_search.py#L139-L142) 的注释声称：

> Bound scholarly's own retry loop so a rate-limited (HTTP 429) or captcha block fails fast
> instead of hanging the worker until the parent timeout.

**这个 bound 不存在。** `scholarly.set_retries(max_tries)` 只设置 `_navigator` 单例的
`self._max_retries`，而 `_get_page` 的循环（`_navigator.py:110`）里：

```python
tries = 0                                    # :98   每次调用都从 0 开始（局部变量，非参数）
while tries < self._max_retries:             # :110
    w = random.uniform(1, 2); time.sleep(w)  # :112-113  每次请求前的固定节流
    ...
```

`tries` **只在三处自增**，而三条重试分支**在 `continue` 之前从不让它前进**：

| 分支 | 行 | 行为 | 是否自增 `tries` |
|---|---|---|---|
| **403**（本机无 proxy） | `:134-148` | 第 1 次立即换 session；**第 2 次起** `time.sleep(random.uniform(60, 120))` → `continue` | ❌ **永不自增 ⇒ 无限循环** |
| **DOSException**（captcha 判定） | `:158-164` | `time.sleep(random.uniform(60, 120))` → `continue` | ❌ **永不自增 ⇒ 无限循环** |
| **captcha 页面** | `:130-133` | `_handle_captcha2(...)` → `continue` | ❌ 永不自增 |
| 404 | `:122-129` | `tries += 1` | ✅ |
| 302 | `:151-153` | 落到 `:178` | ✅ |
| **其他状态码（含 429）** | `:154-156` | 落到 `:178` | ✅ **有界** |
| read/connect timeout | `:165-171` | `set_timeout(10)` 下按 10→20→30 s 逐级升，约 **60 s** 后才 `tries += 1` | ⚠️ 有界但极慢 |

**三者最小惩罚都是 60 s，恰为父进程 30 s 死线的 2 倍。** 与证据的 30.25 / 61.55 特征吻合。

### 还有一层：`premium` 递归

```python
if not premium:
    return self._get_page(pagerequest, True)   # :187-188  用 premium=True 重来一遍！
else:
    raise MaxTriesExceededException(...)       # :190
```

`tries` 是**函数内局部变量**（`:98`），所以这次递归**重新从 0 开始**一个新的完整预算。
`MaxTriesExceededException` 只有在 `premium` 为真时才会抛——也就是说
`scholar_search.py:147` 里等它的那个 `except`，**在非 premium 路径上根本等不到**。

---

## 3. 缺陷二：`SCHOLAR_RATE_LIMITED` 在真实环境下不可达

[scholar_search.py:147](../engine/engine/scholar_search.py#L147) 捕获 `DOSException`
来映射 `rate_limited`，但 `_navigator.py:158` **早已把它吞掉**并去 sleep 了
（正是上表第 2 行）。它根本传不到 `scholar_search` 那一层。**这条分类是死代码。**

### ⚠️ 连带纠正一处文档错误

[docs/pdf-audit-integration-status.zh-CN.md:29](pdf-audit-integration-status.zh-CN.md#L29)
断言"当前机器直连 Scholar 返回 HTTP 429（限流）"。**这与代码路径矛盾**：

裸 429 走 `_navigator.py:154-156` 的 `else` 分支，**会**自增 `tries` 并被正确约束，
应表现为 `SCHOLAR_RATE_LIMITED`，**而不是** `SCHOLAR_TIMEOUT`。

观测到的 code 更符合 **403** 或 **DOS/captcha 页**，或**网络静默黑洞**。
**仓库内没有任何 artifact 记录过真实的 HTTP 状态码。**

---

## 4. 缺陷三：`stderr=subprocess.DEVNULL` 销毁了唯一能定性的证据

[bounded_scholar_lookup.py:56](../backend/src/services/bounded_scholar_lookup.py#L56)
丢弃子进程 stderr。而 scholarly 恰在 **INFO 级别**打印唯一判据：

| 源码位置 | 日志 |
|---|---|
| `_navigator.py:135` | `Got an access denied error (403).` |
| `_navigator.py:143` | `Will retry after %.2f seconds (with another session).` |
| `_navigator.py:155` | `Response code %d. Retrying...` |
| `_navigator.py:131` | `Got a captcha request.` |

`:71-75` 的 `except` 又把崩溃折叠成一句泛化文案。**这是本 blocker 无法从仓库内定位的根本原因。**

---

## 5. 回答组员

**Q: 需要改代码吗？**
**需要**——但不是改 Scholar 的检索逻辑，是两处让失败**有界且可诊断**：

1. **让子进程内部预算在*所有*路径下严格小于父进程 30 s。**
   **不要**依赖 `scholarly.set_retries`（它在 403 / captcha / DOS 三条路径上无效）。
   可靠做法：在 worker 内设一个硬 deadline（`signal.alarm`，或把 `set_retries` 降到 1
   并把 `request_timeout_seconds` 压到使其上界 `≪ 30 s`），到点即自杀并回一个明确的 error_code。
2. **捕获 worker stderr 放进 `LookupResult` detail。**
   这一条几乎零成本，且是唯一能把"被封成什么码"变成事实的手段。

**Q: 当前能否继续走完流程？**
**能。** `LOOKUP_FAILED` 是**有界、诚实**的失败态：报告正常持久化并读回，
不存在"把失败伪装成 `NOT_FOUND`"的问题（这正是 Audit 侧那条禁令要求的）。
**你证明的 "bounded failure handling" 是真的**——
**只是它掩盖的那个缺陷本身，从来没被当成缺陷报出来。**

**Q: 阻塞吗？**
**不阻塞交付；阻塞的是"能否诊断"。** 见第 8 节。

---

## 6. 建议的修法（按性价比排序，本次均未实施）

| 优先级 | 改动 | 效果 |
|---|---|---|
| **P0** | `bounded_scholar_lookup.py:56`：`stderr=subprocess.DEVNULL` → `subprocess.PIPE`，并在 `TimeoutExpired` 时把 stderr 尾部写进 `detail` / 日志 | 把"30 秒超时"从不可诊断变成可诊断。**一行。** |
| **P0** | worker 内硬 deadline，使其上界在所有路径 `≪ 30 s` | `SCHOLAR_TIMEOUT` 从"必然"变成"异常" |
| **P1** | `scholar_search.py:147` 的 `DOSException` 分类：要么删掉（死代码），要么改成从 stderr 文本判定 | 消除误导性的分类 |
| **P2** | 修 `pdf-audit-integration-status.zh-CN.md:29` 的 "HTTP 429" 断言 | 文档与代码路径一致 |
| **P3** | 换文献源（见第 9 节） | 从根上绕开 Scholar 的封锁问题 |

---

## 7. ⚠️ 本诊断的边界

- **没有联网复现。** 第 2 节的 wall-clock 推理来自**阅读 scholarly 1.7.11 源码**，不是现场测量。
- **"本机是否真被封、封成什么码"是唯一缺失的事实。** 拿到它只需下面一次实验。

### 一行实验

把 `bounded_scholar_lookup.py:56` 的 `stderr=subprocess.DEVNULL` 改成 `subprocess.PIPE`，
在 `TimeoutExpired` 分支打印它，然后跑一次 live lookup。四种结果对应四种结论：

| stderr 内容 | 结论 |
|---|---|
| `Got an access denied error (403).` + `Will retry after 6x.xx seconds` | **403 封锁**，确认第 2 节缺陷一 |
| `Response code 429. Retrying...` | 配额限流（那 `SCHOLAR_RATE_LIMITED` 的映射本身也有问题） |
| `Got a captcha request.` | captcha 拦截 |
| **完全无输出** | 网络被黑洞（DNS / 连接层静默丢包），与 scholarly 无关 |

---

## 8. 【另附】文献源迁移建议

> 这一节回应"能否用本地文献数据库解决搜索超时"的提问。**结论：不应该用本地库，
> 但应该换源。** 下面给出可换的源、换的位置、以及换的代价。

### 8.1 为什么不是"本地库"

三个意义上的"本地库"，逐个排除：

| 方案 | 为什么不行 |
|---|---|
| 用我们**自己上传的**文献库 | **结构上不成立。** Audit 存在的理由恰恰是核验**我们没有的**参考文献。把 Audit 改成只查本地库，会让每一条不在库里的引用都变成 `NOT_FOUND`——**正是禁令禁止的那种伪造发现**。（Verify 已经只做本地解析，两者分工不同。） |
| 一份**离线全量 dump** | OpenAlex 全量是**数百 GB**；且对"存在性核验"这个用途，**过期快照比实时 API 更糟**——它会斩钉截铁地说"不存在"。 |
| 一个**本地缓存** | 值得做，但那是**优化**（省重复查询），不是**修复**。第一次查询照样超时。 |

**真正的修法是换源**，不是换存储。

### 8.2 两个候选源（2026-09-14 实测）

| | **Crossref** | **OpenAlex** |
|---|---|---|
| 端点 | `api.crossref.org/works` | `api.openalex.org/works` |
| 实测状态 | `200`，JSON | `200`，JSON |
| 实测延迟 | 2.16 s（另一次 0.78 s） | 3.75 s（冷） |
| 认证 | 无（`User-Agent` 带 mailto 进 polite pool） | 无（mailto 同上） |
| 限速 | polite pool ~3 req/s | 明确 10 req/s 上限 |
| 覆盖 | 有 DOI 的出版物 | **更广**，含无 DOI 的预印本 |
| 语义 | **存在性 + 元数据**核验 | 同左，另带引用图 |

两者都**没有** Scholar 的封锁问题，都是**结构化 JSON**（不用解析 HTML），
都有**可预期的限速**而不是随机 60–120 s 惩罚性 sleep。

### 8.3 ⚠️ 换源的真实代价：rank-1 会答错

**这是本次调研最重要的发现，比超时本身更值得警惕。**

用 `"Attention is all you need"` 做标题查询，2026-09-14 实测：

**Crossref**（top 3）：

1. `[book-chapter]` **Is Attention All You Need?** (2025) — Springer 书章
2. `[posted-content]` Attention Is All You Need: An Analysis Of The Valuation... (2024) — SSRN
3. `[posted-content]` Attention is All You Need... Unless You Are a CISO (2026) — SSRN

**OpenAlex**（top 3）：

1. `[preprint]` **Attention Is All You Need** (2025)
2. `[conference-paper]` Attention Is All You Need In Speech Separation (2021)
3. `[conference-paper]` Channel Attention Is All You Need for Video Frame Interpolation (2020)

**两个源 rank-1 都不是 Vaswani 2017。** 原因有二：

- "Attention is all you need" 已经成了**被大量套用的句式**，标题查询天然被后来的仿写淹没；
- **NeurIPS 等 ML 会议论文常常没有 Crossref DOI**——而这类论文恰恰是本工具的目标用户引用的东西。
  这是换到 Crossref 的一个**真实覆盖缺口**。

**已有的护栏会救回来，但代价是 `ambiguous` 变多：**
[google_scholar_lookup.py:93-97](../backend/src/services/google_scholar_lookup.py#L93-L97) 的
标题匹配守卫会在"返回标题 ≠ 请求标题"时把 `found` 降级为 `ambiguous`。
它按设计工作——上面前两条都会被降级——但**`ambiguous` 会从罕见变成常态**，
而 `ambiguous` 对用户是"我们找到了几条候选，请人工确认"，体验上明显差于"找到了"。

> ⚠️ 换句话说：**换源解决了超时，没解决"找得准"。** 标题模糊匹配这件事，
> 无论 Scholar / Crossref / OpenAlex 都一样难。若要把"找得准"也做掉，
> 需要的是**结构化查询**（用 DOI / arXiv ID 精确查）而不是把标题查询换个后端。

### 8.4 迁移是**受控的**：只有一个接缝

好消息是换源不需要动架构。整个 Scholar 依赖被收在一个方法后面：

```python
GoogleScholarLookup.lookup(entry: ReferenceEntry) -> LookupResult
#   backend/src/services/google_scholar_lookup.py
```

而 `provider="google_scholar"` 是 `ExternalRecord`（`:50`）与
`LookupAttempt`（`:70`）上的**字段值**，不是硬编码假设——
所以一个 `CrossrefLookup` / `OpenAlexLookup` 实现同一协议即可接入，
`provider` 字段换成新值，其余流水线不动。

**需要同步改的地方**：

| 位置 | 改什么 |
|---|---|
| `backend/src/services/google_scholar_lookup.py` | 新增 `CrossrefLookup` / `OpenAlexLookup`（同一 `lookup()` 签名） |
| `bounded_scholar_lookup.py` | 子进程边界可以**完全去掉**——换源之后没有"会无限 sleep 的库"了，一次 HTTP 调用即可 |
| `backend/src/services/scholar_worker.py` | 同上，可退役（连带 §4 的 stderr 问题一起消失） |
| `backend/tests/test_google_scholar_lookup.py` | 换 fake 的 HTTP seam |
| `backend/tests/test_bounded_scholar_lookup.py`（如存在） | 边界测试的对象消失；`SCHOLAR_TIMEOUT` / `SCHOLAR_WORKER_FAILED` 两个 code 一起退役 |
| `controlled/*` 夹具 | 若里面有 Scholar 特有的 fixture，需同步 |

**行为变化（必须写进 PR 描述）**：`ambiguous` 会显著变多（§8.3），
`SCHOLAR_TIMEOUT` / `SCHOLAR_WORKER_FAILED` / `SCHOLAR_RATE_LIMITED` 三个 error_code
会退役或换名。**这是一次用户可见的行为改变，不该混进"修超时"的 PR。**

### 8.5 建议的顺序

1. **先做 §6 的 P0**（两行：捕获 stderr + 收敛 deadline）。这让当前链路**可诊断且不再必然超时**，
   不动任何用户可见行为。
2. **再单开一个 PR 换源**（Crossref + OpenAlex 双源，或先 OpenAlex），
   把 §8.4 的行为变化单独评审。
3. 缓存作为**独立优化**，在换源之后做——那时才有稳定的查询语义可以缓存。
