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
| `app/amap_tools.py`（改） | `AmapClient` 绑定/解绑/`release`（短锁、closing/closed、身份核对、锁外物理关闭）；`AmapAdapter.bind_runtime/close`（自有/借用、close 幂等）；**本次修复：任何 bind 失败路径标记“本次运行未取得该对象”，`close()` 让位一次且不触碰原 owner**；hours/route_leg 子证据回调 |
| `app/live.py`（改） | 删除 `_record` 的 `max(1,差额)` 事后记账；`invoke` 只做 `check`；`create_live_run` 建立 per-run runtime、校验 `bind_runtime`+`close` 协议、耗尽/异常终态、`finally` 清理并记录 `RESOURCE_CLEANUP_FAILED` |
| `app/main.py`（改） | 默认 factory 用 `owns_client=True` 显式移交独立 client（缺 Key 仍 503） |
| `tests/test_live.py`（改） | `FakeAdapter` 迁移到新协议：`bind_runtime` 保存 runtime、`close` 解绑、每个模拟 HTTP 发送前 `runtime.reserve_http(5.0)`（origin 1 / poi 每个 1 / weather 1 / hours 2 / matrix 每对 1）；删除已无区分度的 `CountingAdapter`（其口径并入 base fake）；`tool_calls` 期望 7→13（旧 7 是“每工具至少计1”的旧口径） |
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
- 各工具按真实适配器同一口径模拟发送：origin 1、poi 1、weather 1、hours 2、matrix 每对 1。
- 原断言全部保留并**加强**：`test_live_run_success` 断言 `budget.tool_calls == 13` 且 `adapter.client.calls == budget.tool_calls`（保存计数与实际发送一致）；`test_live_budget_counts_internal_http_requests` 仍守“hours 2 次 + matrix 逐对”不被当成每工具 1 次。

7→13 的换算（不是放宽）：origin1 + poi3 + weather1 + hours2 + matrix6 = 13；旧值 7 = origin1 + poi3 + weather1 + hours1 + matrix1，即“工具方法数”。新口径是本 change 声明的目标语义（`tool_calls` = 获准的 HTTP 尝试数），与真实适配器路径 15（weather 首调含 adcode 1 次）不冲突。

结果：`tests/test_live.py` → `13 passed`。

## 5. 修复 2：失败绑定清理不得触碰原 owner

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
| API 端到端计数一致 | `test_real_adapter_api_exact_budget_and_replay` / `test_live_run_success` | 持久化 `budget.tool_calls` == 实际发送数（13 / 15） |

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
| bind-v-bind 至多一赢（不靠 GIL） | `test_bind_race_one_winner_and_failed_cleanup_preserves_owner` | `Barrier(2)` 两线程绑定同一 client，`sum(won) == 1` |
| 失败绑定清理不改变原 run | 同上 + `test_reentrant_factory_object_failure_does_not_clean_active_owner` | 失败方 `close()` 后 `close_attempts == 0`；原 adapter 仍可 `resolve_origin`，原 run 预算 1，失败 run 预算 0 |
| 借入 close 次数 0、可顺序复用 | `test_borrowed_client_unbinds_for_sequential_runs_without_close` | 两次顺序借用各 1 次发送，`close_attempts == 0`；`client.calls == 2`；原拥有者 `close()` 后 `close_attempts == 1` |
| 自有 close 幂等（物理关闭最多一次） | `test_bind_race...` / `test_owned_close...` | 连续两次 `close()` 后 `close_attempts == 1` |
| bind-v-close：物理关闭未完成时新绑定必须失败 | `test_owned_close_rejects_bind_while_physical_close_waits[False/True]` | transport 的 `close()` 在 barrier 处停住时，新 adapter `bind_runtime` 抛 `RuntimeError`、其 `close()` 不触碰 client；结束后 `client.bind_runtime` 仍拒绝 |
| 关闭失败不得恢复可复用 | 同上 `[True]` | close 抛 `OSError` 后重新绑定仍 `RuntimeError`，`close_attempts == 1` |
| 缺协议 → 工具/HTTP 均 0，取得对象仍尝试清理 | `test_missing_binding_protocol_invokes_no_tool[bind_runtime-1]` / `[close-0]` | `failed` + `issues[0]=STAGE_EXECUTION_ERROR`、`tool_calls == 0`、`{"bind":0,"tools":0,"close":1|0}`、`result=None`、`unverified` |
| 默认 factory 显式拥有独立 client | `test_default_factory_owns_independent_client` | 默认路径（注入仅替换 `AmapClient` 的 transport 与合成 Key）完成 15 次发送，物理 `close` 1 次；**突变验证**：把 `owns_client=True` 改成 `False` 后该测试失败（`close_attempts` 0≠1），已恢复 |
| 测试 fake 显式逐 HTTP 准入 | `tests/test_live.py` 全 13 项 | 全部经 `bind_runtime`；每个模拟发送前 `reserve_http`；预算断言与 `client.calls` 对账 |

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

文中命令按原文执行通过：`49 passed` / `110 passed`（见 §7）。

### 6.6 Review Focus

> 第二个 adapter 绑定同一 active client 失败后，其 cleanup 不得解绑或关闭第一个 run 的 client；原 run 仍能执行且预算独立。

证据：`test_reentrant_factory_object_failure_does_not_clean_active_owner`（0 发送、0 关闭、原 run 仍可执行、预算独立、最终原 owner 关闭 1 次）+ `test_bind_race_one_winner_and_failed_cleanup_preserves_owner`（败者 close 后物理关闭仍 0）。

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
→ 22 passed                        (exit 0)
```

文档命令（按 `docs/LIVE-AMAP.md` 原文，`python` 解析到 `C:\Miniconda3\python.exe`，3.12.9）：

```text
$env:TRAVEL_REPLAY_NO_AUTOSTART='1'
python -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py
→ 49 passed                        (exit 0)   # 14 + 13 + 22

python -m pytest -q -p no:cacheprovider
→ 110 passed                       (exit 0)   # 回放61 + 高德离线14 + live API13 + 准入/资源闭环22
```

最终权威全量（所有代码/文档改动完成后的最后一次）：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 110 passed in 16.21s             (exit 0)
```

计数说明：107（起点总数）→ 110 = 新增 3 个用例（`test_default_factory_owns_independent_client` 1 个 + `test_missing_binding_protocol_invokes_no_tool` 2 参数）；无测试被删除或跳过；`CountingAdapter` 删除属实现内同类替换（口径并入 base fake，原测试断言由 7 收紧到 13 并新增发送数对账）。

隔离复现（`openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py`，临时目录 SQLite + MockTransport）：

| 观察项 | 修前（基线 `6a78560`，2026-11-09 记录于 `evidence/baseline-overshoot.json`） | 本分支修后（2026-11-13 实跑） |
|---|---|---|
| limit | 2 | 2 |
| transport attempts | 3 | 2 |
| client.calls | 3 | 2 |
| 持久化 tool_calls | 2 | 2 |
| oversent | true | false |
| 终态 | failed / exhausted | failed / exhausted（`call_limit`） |

修后实跑输出关键字段：`{"limit": 2, "transport_attempts": 2, "client_calls": 2, "persisted_count": 2, "run_status": "failed", "budget_status": "exhausted", "oversent": false}`（exit 0；`path_categories` 只是本地请求路径，不含 query/Key）。

## 8. 每个 seam：能抓住什么 / 漏掉什么

| Seam | 能抓住 | 漏掉 |
|---|---|---|
| **S1 发送点**：`AmapClient.get` 的 `reserve → httpx`（唯一集中发送点） | 超发在第 N+1 次预占处被拒、handler 命中 0；matrix 逐腿 / hours 逐 detail / weather 两段都在同一 guard；失败尝试照计；本地缓存/空矩阵 0 消耗；limit=0/1/2/40 边界 | 进程崩溃前未落库的尝试（不宣称逐 HTTP 崩溃账本）；reserve 成功但请求在途时无法撤回；httpx 传输内部行为（无重试、`follow_redirects=False`，但未做供应商侧验证）；`reserve_http` 目前不裁剪 timeout（票2 deadline） |
| **S2 所有权/生命周期**：`AmapAdapter.bind_runtime/close` + `AmapClient` 短锁 | active 互斥、closing/closed 拒绑、身份核对解绑、借入不关闭、自有关闭一次、关闭失败不可复用、失败绑定清理不碰原 owner | `close()` 协议没有身份参数，失败绑定的“让位”靠一次性标记（见 §9）；同一对象多线程并发 bind/close 的极端交错未覆盖；factory 在返回前抛错时其资源由 factory 自己负责，顶层无法关闭未知对象 |
| **S3 编排/持久化**：`create_live_run` 的 finally→`save_run`→`LIVE_FINISHED`→API/DB 重读 | 缺协议 0 工具 0 发送、耗尽/异常终态与 `exhaustion_reason`、清理异常降级为 warning、同键重放不建 runtime/factory、DB 重读计数与证据一致 | run 与事件两次提交非原子（T12 另跟踪）；取消/晚到响应（票2）；进程崩溃/断电恢复不保证 |
| **S4 测试契约**：fake 逐 HTTP 准入 + 真实 adapter/MockTransport 交叉 | 防止“事后按工具计 1”回归；fake 与真实适配器计数口径可对账（13 vs 15 的差异来自 weather adcode） | fake 只模拟固定路径与固定失败模式，不模拟真实延迟/QPS/供应商语义；真实供应商效果与计费仍未验 |

## 9. 必要限制 / concerns

1. **deadline 与取消未交付**（按票范围）：`LiveRuntime.check()` 目前是占位；`reserve_http` 返回原始操作 timeout，未做 `min(配置, 剩余时间)`；未实现取消探针、晚到结果拒绝、终态一致化。本票不声称 90 秒硬中断。
2. **`close()` 无身份参数**：失败绑定要让位给原 owner，只能靠 adapter 上“最近一次 bind 未取得所有权”的一次性标记；要求“一次失败绑定之后恰好一次 close”。当前 `create_live_run` 的 `finally` 保证这一点。若调用方跳过该次 close，或同一对象连续失败两次后才 close，让位可能错位一次（对象仍归原 owner，但清理时机被推迟）。若后续要求更强的可判定性，需要在协议里引入 runtime 身份（会再次改动内部注入契约，超出本票范围）。
3. **Path C 永久作废**：`client.bind_runtime` 抛错时 adapter 置 `closed`，不允许重试绑定——与“closing/closed 拒绝新绑定”一致，但意味着“瞬时失败后重试同一对象”不受支持（设计未要求）。
4. **计数不是计费凭证**：`budget.tool_calls` 是获准的 HTTP 尝试数；连接失败也计 1；供应商是否收到/扣费未验证。
5. **API 层并发**：本票只在测试内用真实 `TestClient` 与线程 barrier 验证绑定/关闭竞争；真实 loopback 并发 POST/重放/cancel 属票3。
6. **真实 HOST / 真实供应商**：HOST=unknown，未伪造原生宿主调度；未使用真实高德 Key，真实数据未联调。
7. **未提交**：改动留在工作区（不 add/push/merge），便于 Standards/Spec 两个 fresh reviewer 直接看 diff；未创建 checkpoint 标签。

## 票外发现

[has-off-ticket-finding] 共 2 项（均属后续票范围，本票未提前实现，仅登记）：
1. **LIVE 取消响应/事件仍使用 replay 文案**：`app/main.py` 的 `cancel_travel_run` 无论 run 模式都返回 `"mode": "replay"` + `REPLAY_NOTICE`，事件理由写“本地回放无远端操作需要撤销”。对 LIVE run 这不准确（spec LRC-03 与 AMEND-002 要求按实际模式描述、不含回放声明）。该行为属票2.3（LRC-03）范围，本票未改，以免提前侵入票2的行为面。建议票2实现时把取消响应的 mode/文案与 LIVE 事件理由一并归一。
2. **错误文本仍可能带原始异常串/供应商 info**：`app/amap_tools.py` 的 `AmapClient.get` 在 `httpx.HTTPError` 分支返回 `f"{type(exc).__name__}: {exc}"`，`_map_client_error` 把它透传进 `ToolResult.message`；provider 分支也回显 `data.get("info")`。LRC-08 的脱敏（只保留固定类别/异常类型/校验后的数字码）属票3.2，本票未改；现有测试不写入真实凭据，故未泄漏真实 Key，但脱敏覆盖仍待票3补齐。
