---
title: verify 报告 — travel-runtime-budget
date: 2026-11-13
---

# verify 报告 — `travel-runtime-budget`

> 验证者：fresh verify 子代理（**不信任**既有报告措辞与 `tasks.md` 复选框；逐条读码、重跑命令、以可机验锚点为唯一判据）。
> 日期：2026-11-13（Asia/Shanghai）。
> 基线：分支 `feat/travel-runtime-budget`；本次验证时 **HEAD `7e025afe502f36b5e8d5c40d34be55f5c2ea6bff`**，base `6a785607e4bdb52e6c1af95e7b7b585d1b5d035b`（= `main`）。
> **结论：PASS** —— LRC-01..09 九条需求全部有可跑通的可机验锚点（测试名 / 命令 / 文件:行），无核心功能缺口；3 项 Minor（文档计数自相矛盾、代码审状态陈旧、既有分类缺陷已入池）如实列于 §6，不构成 FAIL。

## 回执：`prefix-principles.md` 首行原样回显

```text
<!-- prefix-version: principles-b9a054bafa9c -->
```

（正文未内联；本报告只按该文件要求做回执。）

## 0. 本次验证的证据纪律

- 每条 ✅ 都附**可机验锚点**：pytest 用例名（含文件:行）、真实命令 + exit + 计数、或产品代码 `文件:行`。**无锚点即判 gap**，不凭 `tasks.md` 复选框。
- `tasks.md` 的勾选在本会话开始时是**工作树未提交改动**（`git status` 唯一 `M` 项），本报告不把它当证据；勾选状态随本报告一并提交，便于后续门禁读取干净树。
- 未修改任何产品代码 / 测试 / design / specs；未 push / merge；未访问真实供应商（全部 `httpx.MockTransport` + 合成 Key `synthetic-example`）。
- 报告自有的 `verify=PASS` 结论锚由 `anchor_writeback.py` 权威写入 frontmatter，正文不手写该字段。

## 1. 逐需求核对表（需求 | 代码出处 | 状态）

| 需求 | 代码出处（含测试/命令锚点） | 状态 |
|---|---|---|
| **LRC-01** 每次 HTTP 尝试发送前受预算准入（默认 40；工具内部批次同受限；被拒不到传输层；本地工具 0；已准入失败不退） | `app/runtime.py:83-102` `reserve_http`（`check()` → 锁内比 `tool_calls >= max_tool_calls` → `min(base, remaining)` → 计数 +1）；`app/amap_tools.py:139-149`（`get` 在 `httpx.Client.get` **之前** reserve，`calls += 1` 在 reserve 之后）；默认 40：`app/live.py:30`、`:48-49`；工具/子证据记录不消费预算：`app/live.py:70-74`；POI/adcode/weather/hours/matrix 全走 `AmapClient.get`（`amap_tools.py:275-289, 291-311, 365-383, 407-432, 435-480`） | ✅ `tests/test_live_admission.py:139`（limit 0/1/2/40：第 N+1 次 transport 命中 0）、`:431`（预占先于 transport，`sent == ["/first","/second"]`）、`:159`（connect/timeout/provider/format 四类失败仍计 1）、`:183`（本地空 matrix/hours 计 0）、`:198`（adcode 缓存、预报不缓存）；`tests/test_live.py:217`（limit=14 时第 15 次被拒且 `tool_calls == sent == 14`，工具方法数≠HTTP 数）、`:243`（limit=2 耗尽）；`tests/test_live_admission.py:58`（15/15 恰好用完仍 `completed`） |
| **LRC-02** 新建 run、factory 之前的单调 90s 预算；发送/返回/阶段间/终态/收尾检查；`min(config,remaining)` 四类 timeout；不保证硬中断 | `app/runtime.py:14`（90.0）、`:44-57`（`started_at` 在构造时取一次单调值）、`:59-61`（`elapsed` 只用单调差）、`:77-81`（先取消后 deadline）、`:83-102`（`timeout=min(config, remaining)`，非正配置不当成 deadline）；`app/live.py:326-329`（落盘后、factory 前建 runtime）、`:94-99`（`invoke` 前后各 check）、`:171`、`:246`、`:253`、`:263`、`:356-360`（终态/收尾再 check） | ✅ `tests/test_live_deadline_cancel.py:314`（0/89.999/90 边界，check 不消费次数）、`:327`（时间已到仍先观察取消）、`:343`（5→1/1→0.25 不放大）、`:374`（0/-1 配置 → `INVALID_OPERATION_TIMEOUT`，不写耗尽）、`:464`（httpx `connect/read/write/pool` 四键 timeout = min 值）、`:436`（UTC 墙钟跳变不影响单调 elapsed）、`:497`（factory 前 0 预算：`factory_calls == []`、`tool_calls == 0`）、`:522`/`:543`（晚到响应/评估拒绝为 completed/needs_input）、`:561`（收尾越过 deadline 拒绝过期 completed）、`:593`（更早主失败不被时间检查覆盖）、`:580`（普通 timeout 保持原分类） |
| **LRC-03** 工作边界与每次发送前观察持久取消；取消确认与最终提交各自**一个短事务**归一 `cancelled/cancelled/unverified/null`、删耗尽键、留诊断；返回/GET/重放无混合终态；同进程 API 可取消 + 同键重放取 run_id | `app/runtime.py:63-81`（短探针 `probe`，取消优先于 deadline，失败给固定分类）、`:88`（每次 reserve 前 check）；`app/store.py:17-26`（`_normalize_cancelled`：status/budget/quality/result，pop `exhaustion_reason`，不动计数/elapsed/issues）、`:189-226`（取消：`BEGIN IMMEDIATE` 内读+归一+UPDATE，LIVE 同事务写 budget/state）、`:228-234`（探针单行短读、不开显式事务、不包 HTTP）、`:236-274`（最终提交：事务内重读 status，若已 cancelled 则对含实际计数/elapsed/证据的内存快照同归一后一次写入）；`app/main.py:40-45`（LIVE 取消文案/事件理由，无“回放/无远端”）、`:240-241`（同步核心进 threadpool，原 POST 仍等待）、`:375-407`（cancel：404/409、LIVE 分支回 canonical 快照） | ✅ `tests/test_live_deadline_cancel.py:648`（真实 loopback：等待期间同键重放取 run_id、factory/发送/事件增量 0；cancel 可达；下一 handler 未命中 `sent == ["/v3/geocode/geo"]`；最终返回 cancelled 且计数保留）、`:732`（修订同路径）、`:801`（收尾 check 被 barrier 挡住时取消：独立连接多次 GET/重放都是归一快照，`tool_calls == 15` 保留）、`:867`（取消胜过内存耗尽、删原因、保留 BUDGET_EXHAUSTED 诊断）、`:415`（探针异常 → 固定分类 + 安全异常类型）、`:327`（探针先于 deadline）；`tests/test_live_cleanup_redaction.py:246`（首发送返回后取消 → 下一次不发送） |
| **LRC-04** 保存准入数与单调 elapsed；耗尽 → `failed/exhausted` + `BUDGET_EXHAUSTED` + 新 run 必填 `exhaustion_reason`（历史可缺）；`result=null`、`quality=unverified`、保留工具证据 | `app/live.py:270-278`（`_mark_exhausted`：failed/exhausted/reason/result=null/unverified+BUDGET_EXHAUSTED）、`:281-286`（执行失败分类）、`:347-361`（finally 里 cleanup→末次 check→`elapsed_seconds` 必写）、`:363`（`finalize_run` 一次提交）；`app/store.py:104-107,120`（旧 budget JSON 原样 `json.loads` 返回，无补写/无补造） | ✅ `tests/test_live_admission.py:98`（limit 7/10 中途断批：`failed/exhausted/call_limit`、`tool_calls == sent == limit`、`result is None`、已规范化的 `hours_detail`/`route_leg` 子证据含 `source_ref`/`fetched_at`/payload，完整工具未入账，重放不变）、`tests/test_live.py:217`（14 次发送后 `result=None`、`quality=unverified`、证据保留）；`tests/test_live_deadline_cancel.py:522`/`:561`（deadline 耗尽 + 已得证据数 = `tool_calls`）；另以**本次临时探针**（不入仓，见 §5 第 6 行）实测：全本地零 HTTP run → `completed / budget.status=ok / tool_calls=0 / 无 exhaustion_reason / result 存在`；手工插入的旧形态 budget `{"max_tool_calls":40,"tool_calls":7}` 经 GET **原样返回**（无 `elapsed_seconds`、无 `exhaustion_reason`）——覆盖 spec「无HTTP及历史run」两个分支 |
| **LRC-05** 幂等重放不重执行（同键同请求返回已保存 run，不建 runtime/factory、不重发、不重算 elapsed）；同键异请求 409；缺 Key 默认入口 503 | `app/live.py:313-325`（`create_run_atomic` 命中即 `return existing, False`，**在** runtime/factory 之前；冲突抛 `IDEMPOTENCY_CONFLICT`）、`:48-49`（每 run 独立 budget 深拷贝，计数不串 run）；`app/main.py:243-245`（409 映射）、`:166-169`（无 `AMAP_API_KEY` → 503 `LIVE_NOT_CONFIGURED`）、`:327-334`（修订重放校验父/修订号） | ✅ `tests/test_live_admission.py:58`（同键重放：同 run_id、`factory` 一次、`sent == 15` 不变、`close_attempts == 1`、事件相等）、`:98`（耗尽 run 重放同 run_id 且事件/证据不变）；`tests/test_live_deadline_cancel.py:608`（monkeypatch 计数 `LiveRuntime`：重放不建 runtime）；`tests/test_live.py:305`（重放）、`:292`（同键改载荷 409）、`:285`（无 Key 503）；`tests/test_live_admission.py:327`（借入 client 两个顺序 run 各自独立计数 1/2） |
| **LRC-06** LIVE 工具调用前必须有显式运行绑定/清理协议；缺失或绑定失败即停、0 调用；同 client 第二个 active run 被拒且不覆盖前者；非 LIVE 调用者不被误称拥有保证 | `app/amap_tools.py:70-76`（`bind_runtime`：非 open 或已绑定 → `RuntimeError`）、`:117-131`（`_detach_locked` 按身份匹配，不符即抛且不转 closing）、`:247-262`（adapter bind：client 已被别的 run 占用时只作废自身、**不关闭**共享 client）、`:139-142`（closing/closed 拒发）；`app/live.py:331-342`（缺协议 `TypeError` → 执行错误；bind 失败 `cleanup_acquired=False`，不 close 属他人的对象）；默认 factory 显式拥有 client：`app/main.py:170-171`；脚本独立调用不自动拥有 run 预算：`docs/LIVE-AMAP.md:32,82` | ✅ `tests/test_live_admission.py:417`（缺 `bind_runtime`/缺 `close`：`bind/tools` 均 0，close 0/1 符合预期）、`:234`（双线程 bind 至多一赢，`probe.enters == 2`，输家预算 0）、`:270`（已绑定 owner 时新 run 失败且不动原 run：`sent == close_attempts == 0`，原 run 仍可发送）、`:291`（同对象两次失败 bind 后两次清理都不 close，client 仍 open）、`:345`（物理 close 阻塞时新 bind 必须失败；close 失败也不恢复可借用）、`:381`（默认 factory `owns_client=True`，结束物理关闭 1 次）、`:327`（借入 client 顺序复用不 close） |
| **LRC-07** 区分自有/借入；拥有权转移后成功/供应商失败/耗尽/deadline/取消/构造失败 6 类出口均有关闭尝试；重复清理不重复关闭；借入只解绑；factory 返回前失败由 factory 负责 | `app/amap_tools.py:231-236`（构造校验失败且自有 → 先 `client.close()`）、`:264-272`（adapter `close` 幂等：`_closed` 短路，再按 `owns_client` 交 `release`）、`:82-115`（`release`：短锁内标记 closing、锁外物理 close、失败也落 `closed`）、`:78-80`（`unbind_runtime` = `release(owns_client=False)`）；`app/live.py:347-355`（finally 一次 close、失败仅记警告） | ✅ `tests/test_live_cleanup_redaction.py:191`（成功）、`:201`（provider 失败）、`:219`（call_limit）、`:232`（deadline）、`:246`（cancel）、`:265`（constructor 校验失败 + close 幂等：`close_attempts == 1`）、`:286`（factory 返回前失败：factory 自己关 1 次、顶层无二次关闭）、`:311`（借入：`close_attempts == 0`、仍 open、可顺序复用）、`:599`（不依赖 HTTP 层的直接创建路径也保存成功） |
| **LRC-08** 解绑/关闭抛错后继续其余清理；保存主结果 + 脱敏 `RESOURCE_CLEANUP_FAILED`；不覆盖更早主失败；close 尝试≠释放成功；无更早失败时收尾仍拒绝过期终态；诊断不含 Key/带 query URL/私人请求 | `app/amap_tools.py:85-115`（解绑失败仍尝试物理 close；只留固定类别与异常类型名）、`:150-155`（HTTPError → `type(exc).__name__`，不回显 str/URL）、`:162-170`（provider `info` 一律不回显，仅保留通过数字校验的 `infocode`；`_safe_infocode` L40-45）；`app/live.py:345-360`（分类不覆盖已 failed；cleanup 失败只记类型名 + “资源是否释放未知”）、`:289-305`（顶层异常只留类型名，探针失败只留固定类别）；`app/runtime.py:31-41`（`RuntimeControlError` 只携 category + 安全类型名） | ✅ `tests/test_live_cleanup_redaction.py:332`（解绑失败仍物理 close 1 次、主结果 completed 保留、警告只含 `RuntimeError`）、`:350`（provider 失败 + close 失败：原 `failed`/无 exhaustion 键/计数 1 保留，警告 `OSError`+“未知”，且 finally 未跳过保存——DB 重读与 LIVE_FINISHED 事件一致）、`:383`（call_limit 类别 + 精确计数）、`:399`（close 期间越过 deadline：更早失败保留、无 BUDGET_EXHAUSTED、`elapsed_seconds ≥ 90`）、`:435`（无更早失败但收尾越界 → 拒绝过期 completed）、`:478`/`:500`/`:537`/`:552`/`:574`（HTTPError / provider info & 非法 infocode / 顶层异常 / 探针异常 / cleanup 异常五路合成 Key+query+私人标记扫描 API、持久 state、`events` 表、SQLite 全文）；`tests/test_live_deadline_cancel.py:415`（探针异常文本不含 secret） |
| **LRC-09** 交付材料区分 HTTP 尝试 vs 收费、deadline vs 硬中断、离线契约 vs 真实渠道；默认 40/90/5 来源、内部协议变化、耗尽原因必填/历史可缺可查；验收须观察发送点/持久终态/资源动作 | 默认值与边界：`docs/LIVE-AMAP.md:63-102`（6.1-6.4，含修前/修后复现表与 `exhaustion_reason` 行）、`:104-131`（6.5-6.7：单调 90s、四类 timeout、晚到拒绝、取消原子终态、JSON 示例）、`:140-173`（6.8 独立进程 loopback + 覆盖清单）、`:32,82`（`amap_probe.py` 独立调用不享 run 预算）、`:3`（分支≠main、真实 Key 未验）；交叉链：`README.md:23,27,41`、`docs/ACCEPTANCE.md:145-201`（§10 分支状态、实测命令、LRC-01..09 逐条证据/未满足、§10.4 未运行清单）、`docs/TECH-STACK.md:20`（159 分项）；离线复现脚本：`openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py` + `evidence/baseline-overshoot.json` | ✅ 本次实跑 `reproduce_budget.py`：exit 0，隔离临时 SQLite，输出 `transport_attempts=2 / client_calls=2 / persisted_count=2 / exhaustion_reason=call_limit / failed+exhausted / oversent=false`，与 `docs/LIVE-AMAP.md:102` 的修后列一致（修前 3 次已发出、仅入账 2 次 = `baseline-overshoot.json`）；`docs/ACCEPTANCE.md:184-194` 九行均给到具体测试名；文档明确 MockTransport/假时钟为离线、不声称真实高德/费用/硬中断/断电恢复/已合并 main。**2 项文档 Minor 见 §6（计数残行、代码审状态陈旧），不改判** |

## 2. 场景级复核（spec 全部 Scenario → 锚点）

| Requirement / Scenario | 锚点 |
|---|---|
| LRC-01 第N+1次被拒绝 | `test_live_admission.py:139`、`:431`、`test_live.py:243` |
| LRC-01 批次中途耗尽 | `test_live_admission.py:98[7-hours_detail]`、`[10-route_leg]` |
| LRC-01 失败尝试与无HTTP工具 | `test_live_admission.py:159`、`:183` |
| LRC-01 零额度和恰好用完 | `test_live_admission.py:139[0]`、`:58`（15/15） |
| LRC-02 开始前和批内达到deadline | `test_live_deadline_cancel.py:497`、`:522`（`sent == ["origin"]`） |
| LRC-02 响应或评估迟到 | `:522`、`:543`、`:561` |
| LRC-02 剩余时间与短配置 | `:343`、`:464`（三组参数） |
| LRC-02 普通工具timeout和系统时钟跳变 | `:580`（timeout 参数）、`:436` |
| LRC-03 两次发送之间被取消 | `test_live_cleanup_redaction.py:246`、`test_live_deadline_cancel.py:648`（下一 handler 未命中） |
| LRC-03 保存竞争中取消被保护 | `test_live_deadline_cancel.py:801` |
| LRC-03 取消探针读取失败 | `:415`、`test_live_cleanup_redaction.py:552` |
| LRC-03 运行中从实际API取得标识并取消 | `test_live_deadline_cancel.py:648`、`:732`；`scripts/live_loopback_e2e.py` 两场景（独立进程） |
| LRC-04 耗尽前已有有效证据 | `test_live_admission.py:98`、`test_live_deadline_cancel.py:561` |
| LRC-04 无HTTP及历史run | 本次临时探针实测（§5 第 6 行）+ `app/store.py:104-107,120` + `test_live_admission.py:183`（本地工具 0 消耗） |
| LRC-04 批内成功子证据不随中断丢失 | `test_live_admission.py:98`（子证据 payload/source_ref/fetched_at） |
| LRC-05 已成功或耗尽run的同键重放 | `test_live_admission.py:58`、`:98` |
| LRC-05 改请求和缺Key | `test_live.py:292`、`:285` |
| LRC-06 缺少协议 | `test_live_admission.py:417` |
| LRC-06 重叠绑定及顺序借用 | `:234`、`:327`、`:291` |
| LRC-06 自有client关闭与新绑定竞争 | `:345[False]`、`:345[True]` |
| LRC-07 已取得自有资源后的多种终态 | `test_live_cleanup_redaction.py:191/201/219/232/246/265` |
| LRC-07 构造失败和借入资源 | `:265`、`:286`、`:311` |
| LRC-08 原失败与关闭失败同时出现 | `:350`、`:383` |
| LRC-08 解绑失败不跳过自有client关闭 | `:332` |
| LRC-08 普通网络及执行异常中的敏感文本 | `:478`、`:500`、`:537`、`:552`、`:574` |
| LRC-09 开发者验收材料 | `docs/LIVE-AMAP.md:63-173`、`docs/ACCEPTANCE.md:145-201`、`README.md:23-41`、`evidence/reproduce_budget.py` 实跑 |

## 3. 聚合覆盖复核（收尾票，独立重跑，不采信报告措辞）

### 3.1 报告 §0 的 suite-scope JSON vs 本会话重跑（逐字比对）

重跑命令（逐字）：

```text
C:/Miniconda3/python.exe C:/Users/Lenovo/.agents/skills/sdflow-implement/scripts/impl_route.py suite-scope --root D:/workspace-dsh/tmp/sbu-travel-runtime-budget --base 6a785607e4bdb52e6c1af95e7b7b585d1b5d035b --head 1aee907de9f6245877fe03ce77fc24afb7e3f767
```

exit `0`。输出（本次规范化后逐字）：

```json
{"base": "6a785607e4bdb52e6c1af95e7b7b585d1b5d035b", "domains_configured": false, "head": "1aee907de9f6245877fe03ce77fc24afb7e3f767", "hit_domains": [], "layers": {}, "mapping": [ ...87 项... ], "skipped_layers": {}}
```

报告 §0（工作树模式，同一 base/head）头字段完全一致，`mapping` 90 项。规范化（`json.dumps(..., sort_keys=True)`）逐字比对结果：

- **头字段 `base/head/domains_configured/hit_domains/layers/skipped_layers`：逐字相等。**
- `mapping` 差集**恰为 3 项**，全部是**报告那次运行时刻已存在、尚未提交**的未跟踪输入文件（工作树模式 `git ls-files --others` 收录，提交范围模式不收录；它们在 `111f274` 才入库，晚于 `head=1aee907`）：
  - `projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task4-brief.md`
  - `projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task4-dispatch.json`
  - `projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task4-shared-context.md`
- 排除上述 3 项后，`mapping` 的 `(path, domain, prefix)` 三元组集合与顺序**完全相等**（87 == 87），规范化 JSON 整体逐字相等。
- **关于「报告自身可能多一项」**：实测报告 `task4-aggregate.md` **不在**其自身 §0 的 `mapping` 里——报告正文的落盘晚于该次 suite-scope 运行（§0 的 JSON 由管道先写入，报告随后成型），故该文件未进工作树模式的 `ls-files --others`。多出的 3 项属同一「落盘时序」理由，方向一致。

**判定：报告 §0 是真实工具输出，非手写伪造。** 差异可被「工作树模式 vs 提交范围模式」+「落盘时序」完全解释，且修正后逐字相等。

### 3.2 修复后重跑（step 4）

```text
C:/Miniconda3/python.exe C:/Users/Lenovo/.agents/skills/sdflow-implement/scripts/impl_route.py suite-scope --root D:/workspace-dsh/tmp/sbu-travel-runtime-budget --base 1aee907de9f6245877fe03ce77fc24afb7e3f767 --head HEAD
```

exit `0`，`head = 7e025afe502f36b5e8d5c40d34be55f5c2ea6bff`，`domains_configured=false`、`hit_domains=[]`、`layers={}`、`skipped_layers={}`，`mapping` **31 项（非空）**：`README.md`、`app/live.py`、`app/main.py`、`app/runtime.py`、`scripts/live_loopback_e2e.py`、`tests/test_api.py`、`tests/test_live_deadline_cancel.py`、`tests/test_live_loopback_e2e.py`、`docs/{ACCEPTANCE,ARCHITECTURE,LIVE-AMAP,TECH-STACK}.md`、`openspec/changes/travel-runtime-budget/**`（含 `code-review-report.md`、`impl-reports/cr-*.json`、`impl-reports/task4-*`、`tickets.md`）、`openspec/issues/open/bug/B1..B3.md`。

**mapping 非空、`layers` 为空 ⇒ 命中域无自动测试层，未触发重跑（依派单口径，不判缺口）。** 根因同时复核：`openspec/config.yaml` 无活动的 `test-suites:` 键（`Select-String -Pattern '^test-suites:'` 无命中；`-SimpleMatch` 的 4 处命中全为注释 L100/106/113/127）；仅项目根 `pytest.ini`（`testpaths = tests`、`addopts = -p no:cacheprovider`），无 unit/integration/e2e 分层 runner。

> 附加（合同外、非缺口判定依据）：修复面（`app/live.py`、`app/main.py`、`app/runtime.py`、两个测试文件）仍被本会话全量 pytest 覆盖，见 §4 —— exit 0 / 159 passed。

### 3.3 报告 §2 证据行复核（只核**通过行** + SHA 一致性）

| 行 | 报告值 | 本次复核 |
|---|---|---|
| 聚合离线回归（全仓 pytest） | exit 0 / **154** / HEAD `1aee907` | 在 `1aee907` 的**干净 git worktree** 重跑：`154 passed, 2 warnings in 18.90s`，exit 0 —— 计数与 SHA 均一致，非预写 |
| 独立进程 loopback（脚本） | exit 0 / **2 场景** / HEAD `1aee907` / `E2E_OK` | HEAD（`7e025af`）重跑：`E2E_OK`，exit 0；`create`、`revision` 两场景字段结构一致（`transport_sends` 3 与 [11,3]、`close_attempts` 1 与 2、`tool_calls` 3/3、`parent_status=needs_input`）；`run_id` 为本次新建值（非预写常量） |
| 独立进程 loopback（pytest 包装） | exit 0 / **1** / HEAD `1aee907` | `1aee907` 的 154 中包含该文件当时唯一的用例（收集数 1，随全量通过）；HEAD 该文件已增至 2 个用例（修复期新增握手超时用例），实跑 `2 passed` —— 与 SHA 时点自洽 |
| unit/integration/e2e 三行「未覆盖」 | — | 与 `layers={}`、config 无 `test-suites` 一致，理由成立 |

`--collect-only` 交叉核（HEAD）：`24+7+13+18+13+14+23+26+19+2 = 159`；报告时点（`1aee907`）为 `24+7+13+17+13+14+23+23+19+1 = 154`。差额 +1（`test_api`）、+3（`test_live_deadline_cancel`）、+1（`test_live_loopback_e2e`）恰等于代码审修复期新增用例数，与 `cr-fix-r1.md`/`code-review-report.md` 一致。

## 4. 本会话真实重跑记录（命令 / exit / 计数 / HEAD）

| # | 命令（逐字） | exit | 结果 | 运行 HEAD |
|---|---|---|---|---|
| 1 | `C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider`（项目根，`TRAVEL_REPLAY_NO_AUTOSTART=1`，`SDFLOW_DIFF_BASE=6a78560…`） | 0 | **159 passed**, 2 warnings in 26.15s | `7e025af` |
| 2 | 同 #1，在 `git worktree`（`1aee907`，干净树） | 0 | **154 passed**, 2 warnings in 18.90s | `1aee907` |
| 3 | `python -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py tests/test_live_deadline_cancel.py tests/test_live_cleanup_redaction.py tests/test_live_loopback_e2e.py`（文档 §10.2 记录的 6 文件命令） | 0 | **97 passed**（14+13+23+**26**+19+**2**）；文档仍写 93 → 见 §6 M1 | `7e025af` |
| 4 | `C:/Miniconda3/python.exe scripts/live_loopback_e2e.py` | 0 | `E2E_OK`；`{"create":{...tool_calls:3, transport_sends:3, close_attempts:1, status:"cancelled"}, "revision":{...transport_sends:[11,3], close_attempts:2, parent_status:"needs_input"}}` | `7e025af` |
| 5 | `python -m pytest -q -p no:cacheprovider tests/test_live_loopback_e2e.py` | 0 | **2 passed** in 7.52s | `7e025af` |
| 6 | `python openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py`（隔离临时 SQLite） | 0 | `transport_attempts=2, client_calls=2, persisted_count=2, exhaustion_reason=call_limit, failed/exhausted, oversent=false` —— 与 `docs/LIVE-AMAP.md:102` 修后列一致 | `7e025af` |
| 7 | 临时探针（`%TEMP%\verify-ttrb\lrc04_zero_http_legacy.py`，**不入仓**，只读调用 app） | 0 | 零 HTTP LIVE run：`completed / budget.status=ok / tool_calls=0 / 无 exhaustion_reason / result 存在 / close 1`；旧形态 budget 经 GET 原样返回（无 el/无 reason，无补造） | `7e025af` |
| 8 | `impl_route.py suite-scope --base 6a78560… --head 1aee907…` / `--base 1aee907… --head HEAD` | 0 / 0 | 见 §3.1 / §3.2 | — |

## 5. `tasks.md` 逐条锚点核对（复选框不作为证据，逐条给锚点）

| 任务 | 锚点 | 判定 |
|---|---|---|
| 1.1 预占与真实计数、移除事后差额记账 | `app/runtime.py:83-102`；`test_live_admission.py:139/431`、`test_live.py:217` | ✅ |
| 1.2 POI/adcode/weather/hours/matrix 同准入 + 子证据回调 + 断批可定位 | `app/amap_tools.py:139-149,422-425,470`；`app/live.py:70-74,104-107`；`test_live_admission.py:98,159,183,198` | ✅ |
| 1.3 adapter 运行绑定/正常 close、client 互斥与身份解绑、默认 factory 拥有 client | `app/amap_tools.py:70-131,247-272`；`app/main.py:170-171`；`test_live_admission.py:234,270,291,327,345,381,417` | ✅ |
| 1.4 真 AmapAdapter+MockTransport 经 TestClient 覆盖创建/重放/耗尽 | `test_live_admission.py:58`、`test_live_cleanup_redaction.py:219`；`test_live.py:305` | ✅ |
| 1.5 LIVE-AMAP 默认40/内部协议/复现数据 + 脚本不享 run 预算 | `docs/LIVE-AMAP.md:63-102,32,82`；`evidence/reproduce_budget.py` 实跑（§4 #6） | ✅ |
| 2.1 factory 前单调起点 + 四类 timeout 取 min + 假时钟 | `app/runtime.py:44-57,83-102`；`test_live_deadline_cancel.py:314,343,436,464,497` | ✅ |
| 2.2 晚到分类/保留计数与证据/不 str(exc)/新耗尽必填 | `app/live.py:270-305,347-361`；`test_live_deadline_cancel.py:522,543,561,580,593`；`test_live_cleanup_redaction.py:537,552` | ✅ |
| 2.3 短探针、HTTP 不持 DB 事务、同步核心搬 threadpool、API 取消可达 | `app/store.py:228-234`；`app/main.py:240-241,318-321,375-407`；`test_live_deadline_cancel.py:648,732` | ✅ |
| 2.4 取消确认/最终保存各自短事务归一 + barrier 并发 GET/重放 | `app/store.py:17-26,189-226,236-274`；`test_live_deadline_cancel.py:801,867` | ✅ |
| 2.5 LIVE 时限/取消契约与 JSON 示例 | `docs/LIVE-AMAP.md:104-131` | ✅ |
| 3.1 六类出口 + 借入 0 关闭 + close 幂等 | `test_live_cleanup_redaction.py:191,201,219,232,246,265,286,311`；`app/amap_tools.py:264-272` | ✅ |
| 3.2 解绑/关闭异常继续其余清理 + 第7类 cleanup_failure + 敏感文本扫描 | `app/amap_tools.py:85-115,150-170`；`test_live_cleanup_redaction.py:332,350,383,399,435,478,500,537,552,574,599` | ✅ |
| 3.3 跨切片全量回归真实命令/exit/count | §4 #1、#2（159 / 154，均 exit 0） | ✅ |
| 3.4 隔离进程 loopback 烟测（真实适配器+MockTransport、不直写 DB、只连本地） | `scripts/live_loopback_e2e.py`；§4 #4、#5；`tests/test_live_loopback_e2e.py:18,69` | ✅ |
| 3.5 README/LIVE-AMAP/验收记录互链 + 9 条需求证据/未满足 | `README.md:23-41`；`docs/LIVE-AMAP.md:3`；`docs/ACCEPTANCE.md:145-201`；`docs/TECH-STACK.md:20` | ✅（文档计数残行见 M1） |

## 6. 缺口清单

**核心功能缺口：无。** 以下 3 项如实登记；按派单口径均为 Minor（文档 / 可观测），不构成 FAIL。

- **M1（Minor，文档计数自相矛盾）** `docs/ACCEPTANCE.md:168` 仍写「`93 passed … (14+13+23+23+19+1)`」、`:180` 仍写「计数构成：134 + 19 + 1」（=154），与同文件 `:147`/`:165` 已更新的 **159** 互斥；`docs/LIVE-AMAP.md:168` 同写 93（23/1 旧分项）。实测该 6 文件命令在 HEAD 为 **97 passed**（14+13+23+**26**+19+**2**，§4 #3），159 的正确分项见 `docs/TECH-STACK.md:20` 与 `docs/LIVE-AMAP.md:170`（134+19+1+5）。属代码审修复期只改了总数、漏改两处分项行。
- **M2（Minor，文档状态陈旧，方向为保守低报）** `docs/ACCEPTANCE.md:155`（「独立代码审 **未做**」）、`:200`（未运行清单含「独立代码审」）、`docs/LIVE-AMAP.md:3`、`docs/TECH-STACK.md:5`、`docs/ARCHITECTURE.md:4` 均写「未做独立代码审」，但 `openspec/changes/travel-runtime-budget/code-review-report.md` 已落盘并通过（frontmatter `code_review: pass`，评审范围 `6a78560..74ab503`；对应提交 `74ab503`/`8ea871d`/`0b5ce45`/`2c1367b`）。未验证范围里的「真实高德/硬中断/断电恢复/未合并 main」仍为真，故只是状态字段过时，不构成虚假高报。
- **M3（Minor，既有分类缺陷，已入 bug 池，非本 change 引入）**
  - `B2`（OPEN/P2，`openspec/issues/open/bug/B2.md`）：`app/amap_tools.py:365-375` 的 `_city_adcode()` 把网络失败（含 timeout）折叠为 `None`，`weather()` `:379-381` 统一报 `provider_error`，该子请求的 timeout 分类丢失——与 LRC-02「普通单操作 timeout 仍保持原分类」在该子路径上不完全一致（尝试数仍正确计 1、不外呼）。属可观测分类精度，不阻塞 PASS。
  - `B1`（provider 列表元素非 dict 时 `AttributeError` 逸出、未归 `TOOL_FORMAT_ERROR`）与 `B3`（`finalize` 写库异常时 run 可能停留 `queued`，幂等重放只回 queued）：均在代码审中判定为**既有/递延**（`code-review-report.md:54-56`），且 LRC-04 明文把保证限定在「正常可写数据库」、不扩展到崩溃/断电逐 HTTP 账本，故不计本 change 缺口。

> 说明：`tasks.md` 在本会话开始时是工作树未提交改动（16 处复选框 + 1 行状态）。本报告不以它作证据；随本报告提交，使锚写入时监视域无脏树。

## 7. 未验证范围（如实保留，不因全绿外推）

- **真实高德供应商**：未提供 Key、未联调；全部为 `httpx.MockTransport` + 合成 Key。真实 POI/天气/路线数据、配额/QPS、计费与效果未验证。
- **硬中断 / 90 秒强制返回**：未验证。deadline 是协作式的（只在可观察边界停止新请求并拒绝晚结果），不撤回挂起的同步调用。
- **断电 / 崩溃恢复 / 逐 HTTP 账本**：未验证（`B3` 另跟踪）。
- **生产并发**：仅单进程 + Starlette 线程池 + 独立进程 loopback（`127.0.0.1`），不构成容量承诺。
- **跨模型 outside-voice**：`code-review-report.md:65-71` 如实记为 `host-unknown`、未运行；本 verify 亦未运行跨模型复核（宿主限制）。
- **分支状态**：`feat/travel-runtime-budget`，未 push、未 merge、未 archive；`main` 仍为 `6a78560`。

## 8. 结论

- LRC-01..09 九条需求全部有**可机验锚点**（pytest 用例名 + 实跑命令 exit/计数 + 代码 `文件:行`），覆盖 spec 全部 Scenario；核心功能无缺口。
- 聚合收尾票复核：报告 §0 的 suite-scope JSON 与本次重跑规范化后**逐字相等**（差异仅为 3 项运行时刻未跟踪输入文件，属工作树/提交范围模式 + 落盘时序）；§2 通过行（154 / 2 场景 / 1 包装）与 SHA 一致，重跑可复现；修复后 `--base 1aee907 --head HEAD` 为 `mapping=31` 非空、`layers={}` ⇒ **命中域无自动测试层，未触发重跑**（不判缺口）。
- 全量回归在当前 HEAD **159 passed / exit 0**；`1aee907` 干净 worktree **154 passed / exit 0**；独立进程 loopback `E2E_OK`。
- 3 项 Minor（M1 文档计数残行、M2 代码审状态陈旧、M3 既有分类缺陷已入池）已列明，均不阻塞归档。
- **判定：PASS。**
