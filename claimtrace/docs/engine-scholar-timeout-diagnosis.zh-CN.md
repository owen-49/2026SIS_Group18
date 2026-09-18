# Google Scholar 30 秒超时：诊断与建议

> ## 🗄️ 本文已归档（superseded）— 2026-09-18
>
> 本文诊断的对象**已经不存在了**。Google Scholar 抓取路径（`scholarly`、Scholar worker
> 子进程、`BoundedScholarLookup`、`SCHOLAR_*`）已整体删除，检索来源换成 **OpenAlex（主）
> + Crossref（补）** 的 provider 链。§6/§7 里"换源"的建议**已经执行**，而且不是按本文设想的
> 形态执行的：链路的身份判定、provider 数量、超时语义都与本文的提议不同。
> 详见 [backend-audit-handoff- scholar- search.md](backend-audit-handoff-%20scholar-%20search.md) §8。
>
> **正文全部保留原样**，作为"当时如何定位一个被贴错标签的超时"的记录 —— 它的诊断结论
> （外部封锁是触发器、代码缺陷是放大器）在事后被证实是对的，这一点有独立的记录价值。
> 但**不要**再把本文当作当前系统的描述，也不要照着 §6/§7 的表去改代码：表里点名的文件
> 全部已被删除。
>
> 当前行为请看：[audit-live-acceptance/audit-integration-handoff.md](audit-live-acceptance/audit-integration-handoff.md)
> 与 [pdf-audit-integration-status.zh-CN.md](pdf-audit-integration-status.zh-CN.md)。

> **读者**：Audit 集成负责人（PR #27 的提问者）。
> **问题**：live Google Scholar 查询稳定 30 s 超时，返回 `LOOKUP_FAILED / SCHOLAR_TIMEOUT`。
> 这是"预期中的 Scholar/网络封锁"，还是"需要改代码"？
>
> **结论**：**两者都是，但不对称——外部封锁是触发器，代码缺陷是放大器。**
> 后者把一个"可诊断、有界"的封锁，变成了"永久、且被贴错标签"的 30 秒超时。
>
> **本诊断写于改动之前**，正文（§1–§5、§7）保留原样，作为当时的推理记录。
> §6 的两条 **P0 已于 2026-09-16 实施**，见下方"实施状态"。
>
> ⚠️ **本诊断是纯静态分析（阅读 scholarly 1.7.11 源码）+ 对已有 artifact 的推理，
> 没有做任何联网复现。** §7 列出了一个能一次性定性的一行实验。

---

## ✅ 实施状态（2026-09-16 更新）

§6 的两条 **P0 均已实施**：

| 条目 | 实现位置 | 关键机制 |
|---|---|---|
| worker 内硬 deadline | [scholar_worker.py](../backend/src/services/scholar_worker.py) | `run_with_deadline()`：搜索跑在 daemon 线程上，到点仍未返回则打印 `SCHOLAR_WORKER_TIMEOUT` 并 `os._exit(0)` |
| 捕获 worker stderr | [bounded_scholar_lookup.py](../backend/src/services/bounded_scholar_lookup.py) | 第三个临时文件 + `_worker_log_tail()`，失败时把 stderr 尾部追加进 `detail`，同时 `logger.warning` 落服务端日志 |

deadline 由父进程**从现有配置推导**并作为 `--deadline-seconds` 传给子进程：
`max(SCHOLAR_LOOKUP_TIMEOUT_SECONDS − 5, 一半)`（默认 30 → **25 s**）。
5 s 余量对应实测的 worker 启动开销 0.37–0.54 s，约 10× 余量。

### ⚠️ 实施中推翻的两条原建议

1. **"捕获 stderr 一行即可"不成立。** scholarly 在 **INFO** 级别打印判据，而它的 logger
   继承 root 的 **WARNING** 级别 —— 只改 `stderr=` 会得到一个**空字符串**。
   必须在 worker 里显式提级别并挂 handler，见 §4 修订说明。
   这与 §7 那张"完全无输出 ⇒ 网络黑洞"的判读表直接冲突：**空输出不再唯一指向黑洞**。
2. **改用线程而非 `signal.alarm`，改用临时文件而非 `subprocess.PIPE`**，理由见 §5、§6 修订说明。

### ⚠️ 实施后的 live 实测：**30 秒超时当前不复现**（2026-09-16）

在未改任何配置的前提下重跑 live acceptance，**没有一条查询超时**：

| case | 条目数 | 结果 | 单输入耗时 |
|---|---|---|---|
| `references.bib` | 1 | `METADATA_MISMATCH`（`found`，并检出 2020 vs 2017 的年份差） | 2.4 s |
| `manuscript.pdf` | 2 | `METADATA_MISMATCH`（`found`）+ `LOOKUP_FAILED / SCHOLAR_SEARCH_FAILED` | 5.7 s |

两次重跑结果一致（合计 14.7 s / 12.9 s），`SCHOLAR_TIMEOUT` 与 `SCHOLAR_WORKER_TIMEOUT` **均未出现**。

> ⚠️ **这不是本次改动带来的。** deadline 一次都没有触发——查询本身在 2–3 秒内就返回了。
> 本机对 Scholar 的封锁是**可变的**（403 / captcha 通常在数分钟到数小时内解除），
> 2026-09-14 观测到的"每条都烧满 30 s"**今天无法复现**。
> **封锁会不会回来，本文回答不了**——这正是 deadline + stderr 捕获仍然必要的原因：
> 它们不解除封锁，但让下一次封锁**有界、可诊断**，而不是又一次沉默的 30 秒。

同时，**deadline 机制在真实网络上单独验证过**（把 deadline 压到 0.5 s）：

| 观测 | 值 |
|---|---|
| 进程退出码 | `0` |
| 墙钟耗时 | **0.63 s**（deadline 0.5 s）—— 卡在网络调用里的线程**没能拖住进程** |
| stdout | 合法 JSON，`error_code=SCHOLAR_WORKER_TIMEOUT` |
| stderr | `INFO scholarly: Getting https://scholar.google.com/scholar?hl=en&q=%22Attention...` |

经完整父进程路径（`BoundedScholarLookup(timeout_seconds=1.0)`，推导 deadline 0.5 s）复核，
`attempts[0].detail` 同时含 deadline 说明与 `Worker log: ...`，并在服务端日志里留了一条 `WARNING`。
**即：封锁真的回来时，证据会直接出现在报告的 `detail` 里，不需要再加任何代码。**

---

## `SCHOLAR_*` error_code 现状

| code | 触发者 | 含义 | 用户该做什么 |
|---|---|---|---|
| `SCHOLAR_WORKER_TIMEOUT` | **worker 自己**（新增） | 搜索超出自己的内部 deadline，已主动放弃 | 重试；`detail` 里带 scholarly 原话 |
| `SCHOLAR_TIMEOUT` | 父进程 `TimeoutExpired` | **worker 连自己的 deadline 都没守住 ⇒ 这是 bug**，不再是"Scholar 慢" | 报 bug，附 `detail` |
| `SCHOLAR_WORKER_FAILED` | 父进程 `CalledProcessError` / `OSError` | worker 没起来或崩了；`detail` 里现在带 traceback | 查后端依赖与日志 |
| `SCHOLAR_SEARCH_FAILED` | worker 内 `google_scholar_lookup` | 搜索本身失败（如标题为空） | 修输入 |
| `SCHOLAR_RATE_LIMITED` | worker 内捕获 `DOSException` | **仍是死代码**（§3 缺陷二未修） | — |

> `SCHOLAR_TIMEOUT` 的语义**变了**：实施前它是"必然结果"，实施后它表示 deadline 本身失灵。
> 因此组员重跑 live acceptance 时：
> **出现 `SCHOLAR_WORKER_TIMEOUT` 是预期结果（封锁回来了，但已被有界处理），不是新故障；
> 不出现则说明当次网络通畅**（见上方实测，2026-09-16 即如此）。
> 两种情况都请看 `detail` 里的 `Worker log:`。

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

### 修订说明（2026-09-16，实施时实测）

上面这张表是**必要条件，不是充分条件**。scholarly 通过
`self.logger = logging.getLogger('scholarly')` 取日志器，而它发出的全部是 `.info(...)`。
在裸 worker 进程里实测：

| 量 | 值 |
|---|---|
| `scholarly` logger 自身级别 | `0`（NOTSET） |
| 有效级别 | `30`（WARNING，继承自 root） |
| handler 数 | `0` |
| `isEnabledFor(INFO)` | **`False`** |

⇒ **日志记录根本没被构造出来**，`stderr=` 改成什么都是空的（`stderr=subprocess.DEVNULL`
没有销毁任何东西）。修复必须在**跑搜索的那个进程**里同时做两件事：

```python
logger.setLevel(logging.INFO)                                  # 级别
logger.addHandler(logging.StreamHandler(sys.stderr))            # handler
```

实测前/后：

```
修复前 stderr: ''
修复后 stderr: 'INFO scholarly: Got an access denied error (403).\n'
                'INFO scholarly: Will retry after 74.31 seconds (with another session).\n'
                'INFO scholarly: Response code 429. Retrying...\n'
```

（**必须写 stderr，不能写 stdout** —— stdout 是 worker 的结果协议。）

**这条同时推翻了 §7 的判读表**：该表把"完全无输出"解释为网络黑洞。实施后，
"有结果但 `detail` 里没有 Worker log"才指向黑洞或未触发 scholarly 的路径。

---

## 5. 回答组员

**Q: 需要改代码吗？**
**需要**——但不是改 Scholar 的检索逻辑，是两处让失败**有界且可诊断**：

1. **让子进程内部预算在*所有*路径下严格小于父进程 30 s。**
   **不要**依赖 `scholarly.set_retries`（它在 403 / captcha / DOS 三条路径上无效）。
   可靠做法：在 worker 内设一个硬 deadline，到点即自杀并回一个明确的 error_code。
   **※ 2026-09-16 修订**：具体机制改为 **daemon 线程 + `join(deadline)` + `os._exit(0)`**。
   不用 `signal.alarm`：它在 Windows 上不存在，而本模块本来就带 Windows 适配
   （`creationflags=CREATE_NO_WINDOW`、ASCII-only stdout JSON）。
   机制已实测：`join(1.0)` 在 1.004 s 返回（线程仍 alive），随后打印 JSON、flush、
   `os._exit(0)` → 进程**立刻**以 0 退出；被 scholarly 的 60–120 s sleep 卡住的线程拖不住进程。
   另一条备选（把 `set_retries` 降到 1 并压低 `request_timeout_seconds`）**无效**——
   `set_retries` 约束不住 403 / captcha / DOS 三条路径（§2）。
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

## 6. 建议的修法（按性价比排序）

> **※ 2026-09-16：两条 P0 已实施**，见文首"实施状态"。下表保留原始排序，附实施后的修正。

| 优先级 | 改动 | 效果 |
|---|---|---|
| **P0** ✅ | `bounded_scholar_lookup.py:56`：`stderr=subprocess.DEVNULL` → **第三个临时文件**，并把 stderr 尾部写进 `detail` / 日志 | 把"30 秒超时"从不可诊断变成可诊断。~~一行~~ → 实测**不止一行**：还需在 worker 内提级别 + 挂 handler（§4 修订说明），否则捕获到的是空串。**另：刻意不用原建议的 `subprocess.PIPE`** —— 该类里 `:41-42` 已注明继承的管道句柄在 Windows 上超时后可能挂住，且 64 KB 管道缓冲写满会把卡住的线程彻底锁死；临时文件与既有 `source`/`stdout` 保持一致。 |
| **P0** ✅ | worker 内硬 deadline，使其上界在所有路径 `≪ 30 s` | `SCHOLAR_TIMEOUT` 从"必然"变成"异常"（新增 `SCHOLAR_WORKER_TIMEOUT` 承担常态） |
| **P1** | `scholar_search.py:147` 的 `DOSException` 分类：要么删掉（死代码），要么改成从 stderr 文本判定 | 消除误导性的分类 |
| **P2** | 修 `pdf-audit-integration-status.zh-CN.md:29` 的 "HTTP 429" 断言 | 文档与代码路径一致 |
| **P3** | 换文献源（见第 9 节） | 从根上绕开 Scholar 的封锁问题 |

---

## 7. ⚠️ 本诊断的边界

- **没有联网复现。** 第 2 节的 wall-clock 推理来自**阅读 scholarly 1.7.11 源码**，不是现场测量。
- **"本机是否真被封、封成什么码"是唯一缺失的事实。** 拿到它只需下面一次实验。

### 一行实验

> **※ 2026-09-16：本实验已实施**（用临时文件而非 `PIPE`，理由见 §6），
> 因此现在**不需要**改任何代码：跑一次 live acceptance，看失败条目
> `lookup_attempts[0].detail` 里的 `Worker log:` 即可。

四种输出对应四种结论：

| stderr 内容 | 结论 |
|---|---|
| `Got an access denied error (403).` + `Will retry after 6x.xx seconds` | **403 封锁**，确认第 2 节缺陷一 |
| `Response code 429. Retrying...` | 配额限流（那 `SCHOLAR_RATE_LIMITED` 的映射本身也有问题） |
| `Got a captcha request.` | captcha 拦截 |
| **完全无输出** | ⚠️ 见 §4 修订说明：只有在**已确认级别/handler 生效**的前提下，空输出才指向网络黑洞（DNS / 连接层静默丢包）。 |

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

1. ✅ **已完成（2026-09-16）**：§6 的两条 P0 —— 捕获 stderr + 收敛 deadline。
   这让当前链路**可诊断且不再必然超时**，不动任何用户可见行为。
   唯一新增的用户可见取值是 `SCHOLAR_WORKER_TIMEOUT`（`error_code` 本就是自由字符串，
   前端 `AuditPage.tsx` 按自由文本渲染，无枚举映射）。
2. **再单开一个 PR 换源**（Crossref + OpenAlex 双源，或先 OpenAlex），
   把 §8.4 的行为变化单独评审。
3. 缓存作为**独立优化**，在换源之后做——那时才有稳定的查询语义可以缓存。
