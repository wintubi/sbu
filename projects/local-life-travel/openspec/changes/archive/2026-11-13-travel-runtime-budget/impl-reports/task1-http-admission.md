# Task 1 实现报告：HTTP发送前准入、真实计数与正常资源闭环

## 0. 回执与身份

前缀文件：`openspec/changes/travel-runtime-budget/.outside-voice/20261110T182434Z-impl-N2Sw5e/prefix-principles.md`

```text
<!-- prefix-version: principles-b9a054bafa9c -->
```

- run_id：`20261110T182434Z-impl-N2Sw5e`
- task_id：`task1-implementer-attempt2`
- role：fresh implementer（非编排器）；未派子代理，未使用 `subagent`/`workflow`
- native HOST：unknown（未伪造原生宿主；按真人已批准的 DSH 阶段三运行适配记录 `review/implementation-runtime-decision.json` 执行）
- 本票 R-ID：LRC-01、LRC-04、LRC-05、LRC-06、LRC-07、LRC-09
- 未触碰：design.md / specs / tasks.md / tickets.md / 票复选框 / 真人门记录；未 push / merge / reset；未使用任何 `checkpoint(travel-runtime-budget:task1-...)` 标签；未 `git add -A`；未访问真实供应商（仅 `httpx.MockTransport` 与合成占位 Key，无真实 Key/query 写入本报告或证据）

## 1. 起点与授权

- 代码起点：`00c5502`（`checkpoint(travel-runtime-budget:plan)`，派发记录 before_sha）；`5886487` 只增加 docs，未改 app/tests。
- 工作区继承上一实现者的未验收 WIP（从 stash 恢复）：`app/runtime.py` 新增，`app/amap_tools.py` / `app/live.py` / `app/main.py` / `tests/test_live_admission.py` 已改，`tests/test_live.py` 未迁移。
- 设计批准：`review/design-decision.json`（90秒协作式 deadline、真实API取消推荐候选、三票顺序；不合并）；运行适配批准：`review/implementation-runtime-decision.json`。本票只做票1，不提前实现票2/票3。
- 权限边界：本会话为 delegated subagent，无法扩权；未请求 sandbox 升级。

## 2. 起点复现（红）

命令（项目固定解释器，未加 `-x`，未预热）：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
```

结果（真实输出）：`10 failed, 97 passed in 15.47s`，exit code `1`。

失败构成与根因（与派发诊断一致，已逐条复现）：

| 失败 | 根因 |
|---|---|
| `tests/test_live.py` 9 项（success/ambiguous×2/manual/budget×2/provider/cross-city/origin-cross-city） | `FakeAdapter`/`CountingAdapter` 仍是旧协议（无 `bind_runtime`/`close`，无逐HTTP预占），被新契约判为 `STAGE_EXECUTION_ERROR`。属本 change 已声明的内部破坏性变更 |
| `tests/test_live_admission.py::test_reentrant_factory_object_failure_does_not_clean_active_owner` | factory 返回一个已绑定另一 run 的 `AmapAdapter`；本 run 在 adapter 层被拒后，`finally` 仍调用 `close()`，把别的 run 的 client 物理关闭（`close_attempts` 1，期望 0） |

红证据原文（该失败断言）：`assert len(boundary.sent) == boundary.close_attempts == 0` → `assert 0 == 1`（`close_attempts=1`）。

## 3. 改动文件

工作区改动（未提交，保持 review diff 可见；均属本票路径）：

| 文件 | 改动 |
|---|---|
| `app/runtime.py`（新增，继承WIP） | `LiveRuntime`：`reserve_http` 在发送前预占并返回 timeout，`check()`/`deliver_evidence()` 占位（deadline/取消留给票2）；`BudgetExhausted.reason` |
| `app/amap_tools.py`（改） | `AmapClient` 绑定/解绑/`release`（短锁、closing/closed、身份核对、锁外物理关闭）；`AmapAdapter.bind_runtime/close`（自有/借用、close 幂等）；hours/route_leg 子证据回调。**修复轮**：删除一次性的 `_binding_failed` 让位逻辑，改为由 `create_live_run` 记录本次 bind 是否成功、失败则不调用该对象 `close()`；`close()` 只按自身绑定身份清理（见 §10） |
| `app/live.py`（改） | 删除 `_record` 的 `max(1,差额)` 事后记账；`invoke` 只做 `check`；`create_live_run` 建立 per-run runtime、校验 `bind_runtime`+`close` 协议、耗尽/异常终态、`finally` 清理并记录 `RESOURCE_CLEANUP_FAILED` |
| `app/main.py`（改） | 默认 factory 用 `owns_client=True` 显式移交独立 client（缺 Key 仍 503） |
| `tests/test_live.py`（改） | `FakeAdapter` 迁移到新协议：`bind_runtime` 保存 runtime、`close` 解绑、每个模拟 HTTP 发送前 `runtime.reserve_http(5.0)`（origin 1 / poi 每个 1 / weather 1 / hours 2 / matrix 每对 1）；删除已无区分度的 `CountingAdapter`（其口径并入 base fake）；`tool_calls` 期望 7→13（旧 7 是“每工具至少计1”的旧口径）。**修复轮**：fake 改为真实口径（weather 2、hours 逐候选 3，正常路径 15），期望 7→15；`test_live_budget_counts_internal_http_requests` 改为 limit=14 边界（见 §10） |
| `tests/test_live_admission.py`（新增，继承WIP + 本次补 2 组） | 真实适配器经 API 的正常/耗尽/重放、发送点边界、失败尝试计数、本地0消耗、bind-v-bind、bind-v-close、借用/自有清理、失败绑定不碰原 owner；**新增**：缺协议 0 工具/0 HTTP、默认 factory 自有 client 物理关闭一次 |
| `docs/LIVE-AMAP.md`（改） | 6.1 发送尝试与默认40、6.2 内部绑定协议、6.3 独立脚本不拥有 run 预算、6.4 修前/修后复现数据、6.5 本票未交付声明；7 测试命令与真实计数 |
| `openspec/changes/travel-runtime-budget/impl-reports/task1-http-admission.md`（本文件） | 证据与限制 |

`git diff --stat`（tracked）：5 files changed, 223 insertions(+), 62 deletions(-)；另有 2 个本票新增文件（`app/runtime.py`、`tests/test_live_admission.py`）。派发方自己的 `impl-reports/task1-brief.md`、`review/task1-dispatch.json`、`review/task1-shared-context.md` 保持未被我改动的未跟踪状态。

## 4. 修复 1：测试 fake 迁移到新协议（不靠放宽断言）

契约（design.md「内部注入协议」+ shared-context Global Constraints）：factory 返回对象必须有 `bind_runtime` 和 `close`；测试 fake 必须显式模拟逐 HTTP 准入；缺协议/绑定失败为 `STAGE_EXECUTION_ERROR`。

迁移方式（`tests/test_live.py`）：

- `FakeAdapter.__init__`：`self.client = SimpleNamespace(calls=0)` 作为“实际发送”观测点；`_runtime`/`_closed` 保存绑定状态。
- `bind_runtime`：已绑定或已关闭则拒绝，否则保存 runtime。
- `close`：解绑并置 closed（幂等）。
- `_send(n)`：**每次模拟发送前**调用 `self._runtime.reserve_http(5.0)` 再 `client.calls += 1`；未绑定直接拒绝（不允许静默绕过 guard）。
- 各工具按真实适配器同一口径模拟发送：origin 1、poi 每个 1、weather 2（首次 adcode geocode + 预报）、hours 按已解析的非 origin 候选逐个 1、matrix 每对 1。**修复轮更正**：原文写作“weather 1、hours 2（合计13）”，与真实适配器不符（见 §10 / STD-02 / F2）。
- 原断言全部保留并**加强**：`test_live_run_success` 断言 `budget.tool_calls == 15`（原文为 13，修复轮按真实口径更正）、`adapter.client.calls == budget.tool_calls` 且 `len(adapter.sent) == 15`；`sent` 的逐项序列断言在 `test_live_budget_counts_internal_http_requests` 的 limit=14 边界用例中（见 §10），后者也不再与 success 重复。

7→15 的换算（不是放宽）：origin1 + poi3 + weather2 + hours3 + matrix6 = 15；旧值 7 = origin1 + poi3 + weather1 + hours1 + matrix1，即“工具方法数”。新口径是本 change 声明的目标语义（`tool_calls` = 获准的 HTTP 尝试数），与真实适配器路径 15 一致（原文“13 与 15 不冲突”的算式 `13+adcode` 是错的：差 2 = weather adcode 1 + hours 逐 POI 1）。

结果：`tests/test_live.py` → `13 passed`。

## 5. 修复 2：失败绑定清理不得触碰原 owner

> **修复轮说明（2026-11-13）**：本节记录修复轮前的一次性 `_binding_failed` 让位方案，已被 §10 的修复取代——该标志及其消费逻辑已删除，改由 `create_live_run` 记录本次 bind 是否成功。原文保留为历史记录。

根因：`AmapAdapter.bind_runtime` 在“本 adapter 已 active”分支直接抛错、未做任何标记；随后本次运行的 `finally` 调 `adapter.close()`，按该 adapter 的旧绑定身份解绑并物理关闭了**另一个 run** 的 client。

修复（`app/amap_tools.py`）：

1. `bind_runtime` 的**任何**失败路径都标记 `_binding_failed = True`：
   - adapter 已 active（属于别的 run）：只标记，不改变该 adapter 的 `_runtime`/`_closed`；
   - adapter 已 closed：`close()` 本就幂等返回；
   - `client.bind_runtime` 抛错（client 已绑别的 run / closing / closed / runtime 非法）：标记并置 `self._closed = True`（本 adapter 永不取得控制权，也不物理关闭共享 client）。
2. `close()`：若存在 `_binding_failed`，**消费该标记并直接返回**——不触碰 client、不把对象标记为 closed，因此原 owner 的绑定与对象仍可正常使用，原 owner 自己的 `close()` 仍会物理关闭一次。
3. 正常自有路径不变：短锁内标 `closing` + 按身份解绑 → 锁外 `client.close()` 一次；借用路径只解绑；解绑身份核对仍在同一短锁内。

红→绿：该测试在修复前 `close_attempts=1`（期望0）；修复后 `test_reentrant_factory_object_failure_does_not_clean_active_owner` 通过，`tests/test_live_admission.py` → `22 passed`。

## 6. 逐条验收证据

以下命令均在 2026-11-13 实跑；测试只用合成占位 Key 与 `MockTransport`，不出网。

### 6.1 票 1.1（LRC-01/LRC-04：发送前预占、真实计数、移除事后记账）

| 验收点 | 测试 | 实测断言 |
|---|---|---|
| limit=0/1/2/40 在真实发送点 | `test_http_boundaries_at_transport[0/1/2/40]` | 恰好 N 次后 `budget.tool_calls == client.calls == len(boundary.sent) == N`；第 N+1 次抛 `BudgetExhausted`，handler 命中数仍为 N |
| 恰好用满仍可完成 | `test_real_adapter_api_exact_budget_and_replay`（limit 15） | `status=completed`、`budget.status=ok`、`tool_calls == sent == 15` |
| 已准入但失败仍计 1 | `test_failed_admitted_attempts_still_count[connect/timeout/provider/format]` | 每种分类下 `budget.tool_calls == client.calls == len(sent) == 1`（limit=1） |
| 本地缓存/空矩阵/缺 POI 计 0 | `test_local_empty_matrix_and_hours_consume_zero`（limit 0） | `matrix([])`、`hours()`（无缓存POI）、`leg("missing","also missing")` 成功后计数仍为 0，传输层 0 |
| adcode 缓存但预报不缓存 | `test_weather_adcode_is_cached_but_http_forecast_is_not` | 两次 `weather()` 共 3 次发送（geocode 1 + forecast 2），计数 3 |
| 预占在传输前（单元） | `test_http_limit_is_reserved_before_transport` | 第 3 次 `get("/rejected")` 抛错，`sent == ["/first","/second"]` |
| 移除 `max(1,差额)` | `git diff app/live.py` | `_record` 不再接收 `calls`，`tool_calls` 只在 `LiveRuntime.reserve_http` 成功时 +1（grep 全仓 `max(1,` 在 app 下已无匹配） |
| API 端到端计数一致 | `test_real_adapter_api_exact_budget_and_replay` / `test_live_run_success` | 持久化 `budget.tool_calls` == 实际发送数（15 / 15；修复轮前 fake 为 13，见 §10） |

### 6.2 票 1.2（批内子证据保留、部分批次不成为完整成功）

| 验收点 | 测试 |
|---|---|
| 批内已规范化 hours_detail 保留来源/时间/最小 payload | `test_api_interrupted_batch_keeps_normalized_evidence[7-hours_detail-payload0]`：limit=7，`sent == tool_calls == 7`，`failed/exhausted/call_limit`，`result=None`、`quality_status=unverified`；DB 重读有且仅 1 条 `hours_detail`，`payload == {"windows":{"合成甲":["09:00","18:00"]}}`、`source_ref` 以 `amap:` 开头、`fetched_at` 非空；不存在聚合 `hours` 结果 |
| 批内已成功 route_leg 保留 | 同测试 `[10-route_leg-payload1]`：1 条 `route_leg`（`__origin__ -> 合成甲`），无聚合 `routes` |
| 计数与准入对账 | 两参数均断言 `budget.tool_calls == len(boundary.sent) == limit` |
| 自有资源仍清理一次 | 两参数均断言 `boundary.close_attempts == 1` |
| 同键重放不重执行 | 两参数均断言 `run_id` 相同、`events`/`tool_results` 不变、`sent` 与 `close_attempts` 不增长 |

### 6.3 票 1.3（LRC-06/LRC-07：绑定/清理协议与并发）

| 验收点 | 测试 | 实测 |
|---|---|---|
| bind-v-bind 至多一赢（不靠 GIL） | `test_bind_race_serializes_on_client_lock_and_one_winner`（修复轮改名） | `Barrier(2)` 两线程绑定同一 client，`sum(won) == 1`；探针锁 `enters == 2`（去锁突变 → `enters == 0`，见 §10） |
| 失败绑定清理不触碰原 owner（cleanup 不调用 close） | `test_reentrant_factory_object_failure_does_not_clean_active_owner` + `test_two_failed_binds_then_cleanups_leave_owner_client_open`（修复轮新增） | 失败方 0 发送 0 关闭；原 adapter 仍可 `resolve_origin`，原 run 预算 1、失败 run 预算 0；同一对象两次失败 bind 后 `close` 从未被调用，client 仍 `open` |
| 借入 close 次数 0、可顺序复用 | `test_borrowed_client_unbinds_for_sequential_runs_without_close` | 两次顺序借用各 1 次发送，`close_attempts == 0`；`client.calls == 2`；原拥有者 `close()` 后 `close_attempts == 1` |
| 自有 close 幂等（物理关闭最多一次） | `test_bind_race_serializes_on_client_lock_and_one_winner` / `test_owned_close...` | 连续两次 `close()` 后 `close_attempts == 1` |
| bind-v-close：物理关闭未完成时新绑定必须失败 | `test_owned_close_rejects_bind_while_physical_close_waits[False/True]` | transport 的 `close()` 在 barrier 处停住时，新 adapter `bind_runtime` 抛 `RuntimeError`；结束后 `client.bind_runtime` 仍拒绝 |
| 关闭失败不得恢复可复用 | 同上 `[True]` | close 抛 `OSError` 后重新绑定仍 `RuntimeError`，`close_attempts == 1` |
| 缺协议 → 工具/HTTP 均 0，取得对象仍尝试清理 | `test_missing_binding_protocol_invokes_no_tool[bind_runtime-1]` / `[close-0]` | `failed` + `issues[0]=STAGE_EXECUTION_ERROR`、`tool_calls == 0`、`{"bind":0,"tools":0,"close":1|0}`、`result=None`、`unverified` |
| 默认 factory 显式拥有独立 client | `test_default_factory_owns_independent_client` | 默认路径（注入仅替换 `AmapClient` 的 transport 与合成 Key）完成 15 次发送，物理 `close` 1 次；**突变验证**：把 `owns_client=True` 改成 `False` 后该测试失败（`close_attempts` 0≠1），已恢复 |
| 测试 fake 显式逐 HTTP 准入 | `tests/test_live.py` 全 13 项 | 全部经 `bind_runtime`；每个模拟发送前 `reserve_http`；正常路径 15 次发送、与 `client.calls` 对账（修复轮口径，见 §10） |

### 6.4 票 1.4（LRC-05/LRC-07：真实 AmapAdapter+MockTransport 经 API）

| 验收点 | 测试 |
|---|---|
| 正常闭环 | `test_real_adapter_api_exact_budget_and_replay`：经 `TestClient` POST，真实 `AmapAdapter(AmapClient(..., transport=MockTransport), owns_client=True)`；`completed`、`verified_feasible`、15 次发送、关闭尝试 1 |
| 数据库重读对账 | 同上：`GET /api/v1/travel/runs/{id}`（走 Store 重读）返回的 `budget` 与 `tool_results` 与创建响应逐项相等 |
| 同键重放不重执行 | 同上：`run_id` 相同、`replayed=true`、`events` 不变、`len(transports) == 1`、发送仍 15、关闭仍 1 |
| 额度耗尽 | `test_api_interrupted_batch_keeps_normalized_evidence[7/10]`：`failed/exhausted/call_limit`，`result=None`、`unverified`，关闭尝试 1，DB 可读证据 |
| 同键改载荷 409 / 缺 Key 503 保留 | `test_live_idempotency_conflict`（409 `IDEMPOTENCY_CONFLICT`）、`test_live_requires_key`（503 `LIVE_NOT_CONFIGURED`） |

### 6.5 票 1.5（LRC-09：说明真实范围）

`docs/LIVE-AMAP.md` 已更新，逐项覆盖：

- 发送尝试语义：发送前预占、第 N+1 次不进传输、失败尝试仍计、本地 0 消耗、“不是供应商计费凭证”（6.1）。
- 默认 40（`LIVE_MAX_TOOL_CALLS`）与各内部循环口径（6.1）。
- 内部绑定协议变更：`bind_runtime`+`close`、缺协议/绑定失败 = `STAGE_EXECUTION_ERROR` 且 0 发送、per-run runtime、active 互斥、自有/借用、失败绑定不碰原 owner、fake 必须逐HTTP准入（6.2）。
- 独立脚本不自动拥有 run 预算（4、6.3）。
- 真实供应商未验（标题状态行、6.5）。
- 复现前后数据（6.4，见 §7）。
- 明确未交付 deadline/取消（6.5），没有把协作式 deadline 说成已实现或硬中断。

文中命令按原文执行通过：`49 passed` / `110 passed`（历史值；修复轮后为 `50 passed` / `111 passed`，见 §7 与 §10）。

### 6.6 Review Focus

> 第二个 adapter 绑定同一 active client 失败后，其 cleanup 不得解绑或关闭第一个 run 的 client；原 run 仍能执行且预算独立。

证据：`test_reentrant_factory_object_failure_does_not_clean_active_owner`（0 发送、0 关闭、原 run 仍可执行、预算独立、最终原 owner 关闭 1 次）+ `test_two_failed_binds_then_cleanups_leave_owner_client_open`（两次失败 bind 的清理都不调用 close，原 owner client 仍 open）+ `test_bind_race_serializes_on_client_lock_and_one_winner`（绑定竞争一赢一败、client 锁被进入 2 次）。

## 7. 红→绿命令与真实计数

起点（修复前，同一会话）：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 10 failed, 97 passed in 15.47s   (exit 1)
```

修复 fake 后局部：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live.py
→ 13 passed                        (exit 0)
```

修复绑定清理后局部：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live_admission.py
→ 22 passed                        (exit 0)   # 修复轮前；修复轮后 23 passed
```

文档命令（按 `docs/LIVE-AMAP.md` 原文，`python` 解析到 `C:\Miniconda3\python.exe`，3.12.9）：

```text
$env:TRAVEL_REPLAY_NO_AUTOSTART='1'
python -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py
→ 49 passed                        (exit 0)   # 14 + 13 + 22（修复轮前）
→ 50 passed                        (exit 0)   # 14 + 13 + 23（修复轮后）

python -m pytest -q -p no:cacheprovider
→ 110 passed                       (exit 0)   # 修复轮前：回放61 + 高德离线14 + live API13 + 准入/资源闭环22
→ 111 passed                       (exit 0)   # 修复轮后：回放61 + 高德离线14 + live API13 + 准入/资源闭环23
```

最终权威全量（所有代码/文档改动完成后的最后一次）：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 110 passed in 16.21s             (exit 0)   # 修复轮前
→ 111 passed in 16.75s             (exit 0)   # 修复轮后最终复跑（2026-11-13，见 §10）
```

计数说明：107（起点总数）→ 110 = 新增 3 个用例（`test_default_factory_owns_independent_client` 1 个 + `test_missing_binding_protocol_invokes_no_tool` 2 参数）；修复轮再新增 1 个用例（`test_two_failed_binds_then_cleanups_leave_owner_client_open`）→ 111。无测试被删除或跳过；`CountingAdapter` 删除属实现内同类替换（口径并入 base fake，原测试断言由 7 收紧到 13，修复轮再更正为 15 并新增发送数对账）。

隔离复现（`openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py`，临时目录 SQLite + MockTransport）：

| 观察项 | 修前（基线 `6a78560`，2026-11-09 记录于 `evidence/baseline-overshoot.json`） | 本分支修后（2026-11-13 实跑） |
|---|---|---|
| limit | 2 | 2 |
| transport attempts | 3 | 2 |
| client.calls | 3 | 2 |
| 持久化 tool_calls | 2 | 2 |
| oversent | true | false |
| 终态 | failed / exhausted | failed / exhausted |
| `budget.exhaustion_reason` | 缺失（该键本次新增，历史 run 可缺；修复轮补入输出） | `call_limit` |

修后实跑输出关键字段（修复轮后，`scope` 文案为 `post-fix behavior`）：`{"scope": "offline MockTransport; synthetic data; post-fix behavior", "limit": 2, "transport_attempts": 2, "client_calls": 2, "persisted_count": 2, "exhaustion_reason": "call_limit", "run_status": "failed", "budget_status": "exhausted", "oversent": false}`（exit 0；`path_categories` 只是本地请求路径，不含 query/Key）。

## 8. 每个 seam：能抓住什么 / 漏掉什么

| Seam | 能抓住 | 漏掉 |
|---|---|---|
| **S1 发送点**：`AmapClient.get` 的 `reserve → httpx`（唯一集中发送点） | 超发在第 N+1 次预占处被拒、handler 命中 0；matrix 逐腿 / hours 逐 detail / weather 两段都在同一 guard；失败尝试照计；本地缓存/空矩阵 0 消耗；limit=0/1/2/40 边界 | 进程崩溃前未落库的尝试（不宣称逐 HTTP 崩溃账本）；reserve 成功但请求在途时无法撤回；httpx 传输内部行为（无重试、`follow_redirects=False`，但未做供应商侧验证）；`reserve_http` 目前不裁剪 timeout（票2 deadline） |
| **S2 所有权/生命周期**：`AmapAdapter.bind_runtime/close` + `AmapClient` 短锁 | active 互斥、closing/closed 拒绑、身份核对解绑、借入不关闭、自有关闭一次、关闭失败不可复用、失败绑定清理不碰原 owner（修复轮：失败 bind 不调用 close，由 `create_live_run` 判定） | `close()` 协议没有身份参数；失败绑定的清理责任在编排层（`create_live_run` 记录 bind 是否成功），若调用方绕过该路径直接 close 未取得所有权的对象，行为不再受契约保护（见 §9、§10）；同一对象多线程并发 bind/close 的极端交错未覆盖；factory 在返回前抛错时其资源由 factory 自己负责，顶层无法关闭未知对象 |
| **S3 编排/持久化**：`create_live_run` 的 finally→`save_run`→`LIVE_FINISHED`→API/DB 重读 | 缺协议 0 工具 0 发送、耗尽/异常终态与 `exhaustion_reason`、清理异常降级为 warning、同键重放不建 runtime/factory、DB 重读计数与证据一致 | run 与事件两次提交非原子（T12 另跟踪）；取消/晚到响应（票2）；进程崩溃/断电恢复不保证 |
| **S4 测试契约**：fake 逐 HTTP 准入 + 真实 adapter/MockTransport 交叉 | 防止“事后按工具计 1”回归；fake 与真实适配器计数口径对账（修复轮后同为 15：origin1+poi3+weather2+hours3+matrix6） | fake 只模拟固定路径与固定失败模式，不模拟真实延迟/QPS/供应商语义；真实供应商效果与计费仍未验 |

## 9. 必要限制 / concerns

1. **deadline 与取消未交付**（按票范围）：`LiveRuntime.check()` 目前是占位；`reserve_http` 返回原始操作 timeout，未做 `min(配置, 剩余时间)`；未实现取消探针、晚到结果拒绝、终态一致化。本票不声称 90 秒硬中断。
2. **`close()` 无身份参数（修复轮后的清理边界）**：`create_live_run` 记录本次 bind 是否成功；失败时该对象仍归原 owner，本次 run **不调用**它的 `close()`（修复轮前靠 adapter 上一次性 `_binding_failed` 标记，该标记已删除，见 §10）。因此“失败绑定不清理原 owner”由编排层保证，而不是由 `close()` 的身份判定保证；直接对未取得所有权的对象调用 `close()` 不再是契约路径。若后续要求在 adapter 层做身份判定，需要给 `close()` 增加 runtime 身份参数（会再次改动内部注入契约，超出本票范围）。
3. **Path C 永久作废**：`client.bind_runtime` 抛错时 adapter 置 `closed`，不允许重试绑定——与“closing/closed 拒绝新绑定”一致，但意味着“瞬时失败后重试同一对象”不受支持（设计未要求）。
4. **计数不是计费凭证**：`budget.tool_calls` 是获准的 HTTP 尝试数；连接失败也计 1；供应商是否收到/扣费未验证。
5. **API 层并发**：本票只在测试内用真实 `TestClient` 与线程 barrier 验证绑定/关闭竞争；真实 loopback 并发 POST/重放/cancel 属票3。
6. **真实 HOST / 真实供应商**：HOST=unknown，未伪造原生宿主调度；未使用真实高德 Key，真实数据未联调。
7. **未提交**：改动留在工作区（不 add/push/merge），便于 Standards/Spec 两个 fresh reviewer 直接看 diff；未创建 checkpoint 标签。

## 票外发现

[has-off-ticket-finding] 共 2 项（均属后续票范围，本票未提前实现，仅登记）：
1. **LIVE 取消响应/事件仍使用 replay 文案**：`app/main.py` 的 `cancel_travel_run` 无论 run 模式都返回 `"mode": "replay"` + `REPLAY_NOTICE`，事件理由写“本地回放无远端操作需要撤销”。对 LIVE run 这不准确（spec LRC-03 与 AMEND-002 要求按实际模式描述、不含回放声明）。该行为属票2.3（LRC-03）范围，本票未改，以免提前侵入票2的行为面。建议票2实现时把取消响应的 mode/文案与 LIVE 事件理由一并归一。
2. **错误文本仍可能带原始异常串/供应商 info**：`app/amap_tools.py` 的 `AmapClient.get` 在 `httpx.HTTPError` 分支返回 `f"{type(exc).__name__}: {exc}"`，`_map_client_error` 把它透传进 `ToolResult.message`；provider 分支也回显 `data.get("info")`。LRC-08 的脱敏（只保留固定类别/异常类型/校验后的数字码）属票3.2，本票未改；现有测试不写入真实凭据，故未泄漏真实 Key，但脱敏覆盖仍待票3补齐。

## 10. 修复轮

### 10.0 身份与边界

- run_id：`20261110T182434Z-impl-N2Sw5e`；task_id：`task1-fix-r1`；role：fresh fix 子代理（只按评审发现修复，不重新设计、不扩票）。
- 评审前快照：`795f1de`；修复改动保持**未提交**，便于 fix 轮 diff。工作树在本轮开始前已有一处非本轮的改动（`review/task1-dispatch.json`，派发方写入），本轮未触碰。
- 未改 `design.md` / `specs/` / `tasks.md` / `tickets.md` / 票复选框 / 设计门记录；未派子代理；未 push / merge / reset；未打 checkpoint 标签；未 `git add`；未访问真实供应商（仅合成 Key `synthetic-example` + `httpx.MockTransport`）。
- 内部注入协议语义未变：`bind_runtime(runtime)` / `close()` 签名与调用方式均未改，只是把“失败 bind 后是否清理”的判断从 adapter 私有布尔搬到 `create_live_run`。

### 10.1 发现 → 修复

| 发现 | 修复 |
|---|---|
| **STD-01（Important）** 失败绑定靠与身份无关的一次性 `_binding_failed`；两次失败 bind 后两次 close 时，第二次会按原 owner 的 `_runtime` 物理关闭仍在执行的 run 的 client | `app/live.py`：`create_live_run` 记录本次 `bind_runtime` 是否成功（`cleanup_acquired`）；失败则不调用该 adapter 的 `close()`（对象归原 owner）。`app/amap_tools.py`：删除 `_binding_failed` 及其消费逻辑；`bind_runtime` 失败路径不再改原 owner 状态；`close()` 回到“只按自身绑定身份清理自有/借用资源”。保留：缺协议（有 close 无 bind_runtime）时已取得对象仍尝试 close 一次；借用只解绑；自有 close 一次且幂等；bind-v-close 仍拒绝新绑定 |
| **STD-02 / F2** FakeAdapter 口径与真实适配器不一致（hours 固定 2、weather 固定 1 → 13） | `tests/test_live.py`：weather 改 2（adcode geocode + 预报），hours 按已解析的非 origin 候选逐个发（3 候选 = 3 次）；正常路径 13→15，并新增 `sent` 标签序列断言；`budget.tool_calls == len(sent) == client.calls` 对账保留。同步修正本报告 §4/§6.1/§8 的“13 + adcode = 15”错误算式 |
| **STD-03** `test_live_budget_counts_internal_http_requests` 与 success 重复（limit=20 > 13 永不触发） | 改成 limit=14 的边界用例：断言 `failed` / `exhausted` / `call_limit`、`tool_calls == len(sent) == client.calls == 14`、`sent` 恰好是前 14 次（第 15 次最后一条腿未到达 handler）、`result=None`、`unverified`；未删除该测试 |
| **STD-04** `RESOURCE_CLEANUP_FAILED` 未登记进 `ISSUE_CODES` | `app/domain.py`：加入 `ISSUE_CODES`；**不加入** `DEGRADING_ISSUES`（spec 只要求 warning；`engine.py` 用 `DEGRADING_ISSUES` 判定降级，加入会改变 replay 语义，代码无此要求）。实测 `'RESOURCE_CLEANUP_FAILED' in ISSUE_CODES` 为真、不在 `DEGRADING_ISSUES` |
| **STD-05** `unbind_runtime` 与 `release(runtime, owns_client=False)` 两条解绑实现 | `app/amap_tools.py`：`unbind_runtime` 委托 `self.release(runtime, owns_client=False)`；测试补身份不符抛 `RuntimeError` 与解绑后 `_runtime is None` |
| **F1** bind-v-bind 测试只证明“本次结果”，去掉 client 锁仍会通过 | `tests/test_live_admission.py`：`test_bind_race_serializes_on_client_lock_and_one_winner` 用探针锁 `CountingLock`（委托真实 `RLock`、记录进入临界区次数）；保留 `sum(won) == 1`，新增 `probe.enters == 2`。去锁突变实测 `enters == 0`（确定性红）；局限见 §10.4 |
| **F3** `evidence/reproduce_budget.py` 的 scope 自称 “current baseline behavior, not a fix”，且缺 `exhaustion_reason` | 脚本：`scope` 改为 `post-fix behavior`，输出 `exhaustion_reason`；`docs/LIVE-AMAP.md` 6.4 表新增 `budget.exhaustion_reason` 行并注明修后一列可由该命令输出逐项复现，两处口径一致 |

### 10.2 红 / 绿证据（真实输出）

**红（STD-01，修复前代码 + 新测试）**：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live.py tests/test_live_admission.py
→ 1 failed, 35 passed in 5.48s      (exit 1)

E   AssertionError: assert ['close', 'close'] == []
E     Left contains 2 more items, first extra item: 'close'
tests\test_live_admission.py::test_two_failed_binds_then_cleanups_leave_owner_client_open
```

即旧实现会对“本次没有取得所有权”的对象调用两次 `close()`；新实现中 `create_live_run` 对失败 bind 直接跳过清理。

**红（STD-02，旧 fake 口径探针）**：用 `git show HEAD:tests/test_live.py` 的旧 `FakeAdapter` 走同一 API，实测 `old_fake_status=completed tool_calls=13 client_calls=13`；新期望 15 对旧口径必红（差 2 = weather adcode 1 + hours 逐 POI 1）。

**红/绿（STD-04）**：`git show 795f1de:.../app/domain.py` 的 `ISSUE_CODES` 不含 `RESOURCE_CLEANUP_FAILED`（修复前登记断言不成立）；修复后通过：

```text
ISSUE_CODES ok; not degrading      (exit 0)
```

**F1 突变验证**：仅把 `AmapClient.bind_runtime` 换成无锁版本（不改文件，进程内打补丁）后跑同一竞争场景：

```text
mutation(no client lock) winners= 1 probe.enters= 0
```

`winners` 仍常为 1（印证评审“旧测试抓不到去锁回归”的判断），但 `probe.enters == 0` 会让新断言确定性变红；恢复真实锁后 `enters == 2` 且一赢一败。

**绿（修复后）**：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 111 passed in 16.75s             (exit 0)

$env:TRAVEL_REPLAY_NO_AUTOSTART='1'
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py
→ 50 passed in 3.97s               (exit 0)   # 14 + 13 + 23

C:/Miniconda3/python.exe openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py
→ {"scope": "offline MockTransport; synthetic data; post-fix behavior", "limit": 2,
   "transport_attempts": 2, "client_calls": 2, "persisted_count": 2,
   "exhaustion_reason": "call_limit", "run_status": "failed",
   "budget_status": "exhausted", "path_categories": ["/v3/geocode/geo", "/v3/place/text"],
   "issue_codes": ["BUDGET_EXHAUSTED"], "oversent": false}      (exit 0)
```

### 10.3 新计数

| 指标 | 修复轮前 | 修复轮后 |
|---|---|---|
| `tests/test_live.py` | 13 passed | 13 passed（期望 13→15） |
| `tests/test_live_admission.py` | 22 passed | 23 passed（+1：两次失败 bind 清理测试） |
| 三文件命令 | 49 passed | 50 passed |
| 全量 | 110 passed | 111 passed |
| `reproduce_budget.py` | exit 0，无 `exhaustion_reason` | exit 0，`exhaustion_reason=call_limit` |

无测试被删除或 skip；新增 1 个用例；`test_bind_race_...` 为改名不改数。

### 10.4 局限（如实）

1. **F1 探针锁是白盒**：`enters == 2` 证明 client 短锁被进入，去锁会确定性变红；但它不证明“任意调度交错下仍然互斥”，也不覆盖“锁换了对象/锁语义被改坏”的变异。行为侧仍靠 `sum(won) == 1` 与所有权/预算断言。
2. **STD-01 的物理关闭交错无法再经契约路径复现**：修复后 `create_live_run` 对失败 bind 根本不调用 `close()`，所以“两次 bind 后才两次 close”的旧交错在 API 路径上不可达；新测试用 `attempted == []` 直接钉住“cleanup 不调用 close”，并断言 client 仍 `open`、`close_attempts == 0`、原 run 仍能发送。直接对未取得所有权的对象调用 `close()` 已不是契约路径（旧 review 探针的调用形状不再受支持）。
3. **未给 `close()` 加身份参数**：那会改变已批准内部注入协议语义，按任务要求不自行为之；当前把判定放在 `create_live_run`。
4. `test_owned_close_rejects_bind_while_physical_close_waits` 不再调用被拒对象的 `close()`（非契约路径），bind-v-close 拒绝语义由 `client.bind_runtime` 仍拒绝与 `close_attempts == 1` 守住。
5. 仍未验证：真实供应商、真实 Key、真实 loopback 并发、deadline/取消（票2）、脱敏（票3）。

### 10.5 复审记录（r2）

- Standards 轴（task1-standards-r2）：**pass**，7 项全部 fixed，无新 Critical/Important；新增 1 条 Minor（STD-06：并发探针断言偏机制、对合法重构过敏，建议改 `max_active` 语义），按 Minor 记账、不阻塞本票。
- Spec 轴（task1-spec-r2）：**pass**，Review Focus 与票 1.1–1.5、六条 R-ID 仍满足；3 条 low：R2-F1 fix 评审包文件清单漏 2 个（报告 143 行改写与 dispatch）、R2-F2 报告 §4 的 `sent` 序列断言归属已在本轮更正到 limit=14 用例、R2-F3 `close()` 无身份参数的残余边界（已披露，票3 处理）。
- 全量回归（修复后）：`111 passed in 8.03s`（exit 0，2026-11-13 由编排层独立复跑）；修复轮三文件命令 `50 passed`、`reproduce_budget.py` 输出与 docs 6.4 修后列一致。
- 未做：真实供应商、真实 Key、loopback 并发（票3）、deadline/取消（票2）。

