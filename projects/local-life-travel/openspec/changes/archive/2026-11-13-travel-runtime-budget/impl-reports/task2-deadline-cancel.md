<!-- prefix-version: principles-b9a054bafa9c -->
DONE — 票2（单调deadline、可达API取消、原子终态）已按 2.1–2.7 与 Review Focus 交付；全量 `134 passed`（exit 0），改动未提交、未打标签、未勾票。

# Task 2 实现报告：单调deadline、可达的API取消与原子终态

## 0. 回执与身份

前缀文件：`openspec/changes/travel-runtime-budget/.outside-voice/20261110T182434Z-impl-N2Sw5e/prefix-principles.md`

```text
<!-- prefix-version: principles-b9a054bafa9c -->
```

- run_id：`20261110T182434Z-impl-N2Sw5e`
- task_id：`task2-implementer`
- role：fresh implementer（非编排器）；**未派子代理**，未使用 `subagent`/`subagent_fork`/`workflow`
- native HOST：unknown（未伪造宿主；按真人已批准的 DSH 阶段三运行适配执行，未重问批准）
- 本票 R-ID：LRC-02、LRC-03、LRC-04、LRC-05、LRC-06、LRC-09
- 起点：`3bed847`（`checkpoint(travel-runtime-budget:task1-http-admission)`，Ticket 1 已验收）
- 未触碰：design.md / specs / tasks.md / tickets.md / 票复选框 / 真人门记录；未 push / merge / reset；未打 `checkpoint(travel-runtime-budget:task2-...)` 标签；未 `git add -A`；未访问真实供应商（仅 `httpx.MockTransport` + 合成 Key `synthetic-example` + 进程内 127.0.0.1 loopback）；本报告不含真实 Key、带 query 的供应商 URL 或完整私人请求
- 权限边界：本会话为 delegated subagent，无法扩权；未请求 sandbox 升级

## 1. 起点、授权与范围

- 工作树起点 `3bed847`，干净（仅编排器派发的 3 个 untracked context 文件）。
- 设计/口径权威：`design.md` 的 Admission and Deadline / Ownership and Finalization、`specs/live-runtime-control/spec.md` LRC-02/03/04/05/06/09、`docs/LIVE-AMAP.md`、`review/task2-shared-context.md`（Global Constraints 与代码审查清单）。
- 本票只做 2.1–2.5 与测试/文档；**不改票 1 已验收行为**（`app/amap_tools.py` 未改，`tests/test_live.py` / `tests/test_live_admission.py` 未改，111 项旧测试全绿）。
- 不引入 worker、202 提前返回、SQL 列迁移；`run_in_threadpool` 只包同步核心，原 POST 仍等待终态。

## 2. 起点复现（先复现再改）

起点全量：`C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider` → `111 passed in 9.16s`，exit `0`。

派发提示的 5 个现状均已逐条复现（行号为 `3bed847`）：

| 现状 | 复现 |
|---|---|
| `LiveRuntime.check()` 占位 | `app/runtime.py:24-27` 方法体只有注释 + `pass`；deadline/取消完全不生效 |
| `reserve_http` 不裁剪 timeout | `app/runtime.py:28-35` 直接 `return base_timeout`；剩余时间再短也把配置值交给 httpx |
| 创建在 async 路由里同步调用 | `app/main.py:228`（创建）与 `app/main.py:304`（LIVE 修订）直接 `create_live_run(...)`；执行期间阻塞事件循环 |
| `cancel_travel_run` 对所有 run 返回 replay | `app/main.py:360-377` 固定 `mode="replay"` + `REPLAY_NOTICE` + “本地回放无远端操作需要撤销”，对 LIVE 不准确 |
| `Store.save_run` 只在 status 上保护 cancelled | `app/store.py:211-228` 的 `CASE WHEN status='cancelled'` 只保 status；budget/state 仍可写入与 cancelled 不一致的快照 |

## 3. 改动文件

| 文件 | 改动 |
|---|---|
| `app/runtime.py`（改） | 新增 `RunCancelled`、`RuntimeControlError`、`DEFAULT_MAX_TOTAL_SECONDS`；`LiveRuntime` 增加可注入 `clock`（默认 `time.monotonic`）与 `cancel_probe`，构造时取单调开始值；`check()` 固定“先探取消、再判 `elapsed >= max_total_seconds`”；`reserve_http` 重新采样剩余时间并返回 `min(配置, 剩余)` 的**正** timeout（不放大短配置、不关闭超时）；探针异常只报固定类别+安全异常类型 |
| `app/store.py`（改） | 新增 `_normalize_cancelled`（status/budget.status=cancelled、quality=unverified、result=null、删 exhaustion_reason，保留计数/elapsed/证据/issues）；`cancel_run` 对 LIVE 在同一 `BEGIN IMMEDIATE` 短事务内写 status+budget+state；新增 `probe_run_status`（单行短读）与 `finalize_run`（单次短事务重新判定取消、归一后一次提交并返回 canonical）；`save_run` 仅保留 replay/worker 用途并注明 LIVE 不得使用 |
| `app/live.py`（改） | `execute_live` 在 needs_input 接受前、评估前/后、completed/needs_input 终态接受前加 `runtime.check()`（`invoke` 前后已有检查改为真实生效）；新增 `_mark_exhausted` / `_mark_execution_failure` / `_classify_control`（已有主失败不被清理/时间检查覆盖）；`create_live_run` 接受 `clock`，在 factory 前建 runtime 并绑定 `store.probe_run_status` 探针；收尾 close 后做最后一次 check、写实际 `elapsed_seconds`、走 `store.finalize_run` 返回 canonical，事件理由取 canonical 状态 |
| `app/main.py`（改） | `from starlette.concurrency import run_in_threadpool`；创建与 LIVE 修订的 `create_live_run` 改为 `await run_in_threadpool(...)`；`create_app(live_clock=...)` 作为时钟注入 seam；抽出 `LIVE_NOTICE`；`cancel_travel_run` 按 `run.mode` 分支：LIVE 返回 `mode=live`、LIVE notice、归一后的 budget/quality/result、LIVE 专属事件与“尽力停止/不撤回在途/不保证立即返回”文案，replay 分支逐字保持原样；terminal 冲突用重读状态报 409 |
| `tests/test_live_deadline_cancel.py`（新增） | 23 项：假时钟/取消优先/timeout 四操作/UTC 跳变/探针失败/0预算/Late 响应与评估/清理超时/普通 timeout·provider·format 分类/主失败保留/幂等不建 runtime/已提交失败取消 409；真实 loopback 并发创建与修订、最终 check 后取消胜出、耗尽后取消删 reason |
| `docs/LIVE-AMAP.md`（改） | 状态行更新；新增 6.5（默认90/操作5、单调 elapsed、检查点、timeout=min、晚到分类、新耗尽必填/历史可缺、不保证90秒强制返回、清理可超时、deadline JSON 示例）与 6.6（run_in_threadpool 可达取消、短事务归一、canonical 最终保存、取消响应 JSON、检查后竞争、replay 不变）；测试计数更新为真实值 |

`git diff --stat`（tracked）：4 个 app 文件 + docs，293 insertions / 50 deletions；另有新增未跟踪 `tests/test_live_deadline_cancel.py`（875 行）。工作树保持未提交，便于 review diff。

## 4. 逐条验收证据

### 2.1 单调时间与 timeout

| 要求 | 证据 |
|---|---|
| 幂等命中不建 runtime | `create_live_run` 在 `existing` 分支直接返回（`app/live.py:319`）；`test_idempotent_replay_does_not_build_runtime` 用计数 `LiveRuntime` 断言首次=1、重放后仍=1 |
| 新 run 在 factory 前取单调开始值 | `LiveRuntime.__init__` 采样 `self.started_at`（`runtime.py:55`），构造位于 `store` 创建之后、`adapter_factory` 之前（`live.py:323`）；`test_deadline_zero_before_factory_starts_no_http` 证明 0 预算时 factory 调用 0 次 |
| 发送前/返回后/阶段间/评估前后/终态接受/收尾检查 | 发送前：`reserve_http` 内 `check()`（`runtime.py:88`）；返回后：`invoke` 前后（`live.py:95,97`）；needs_input 接受前（`live.py:171`）；评估前/后（`live.py:246,253`）；completed 接受前（`live.py:263`）；收尾 close 后（`live.py:353`） |
| 0/90 边界 | `test_check_boundary_zero_and_ninety_uses_monotonic_clock`：0 与 89.999 通过，90 抛 `BudgetExhausted("deadline")` |
| 取消先于时间 | `test_check_observes_cancel_before_deadline`：时钟已到 91 且探针返回 cancelled，仍抛 `RunCancelled`（若先判时间会抛 BudgetExhausted，测试红） |
| UTC 跳变不影响 | `test_utc_wall_clock_jump_does_not_change_monotonic_elapsed`：`time.time` +3600、`datetime.now` +1h，`elapsed()` 仍 0，预算边界仍按假单调时钟 |
| 剩余 1 秒 / 0.25 秒配置 / 四操作 timeout | `test_reserve_http_timeout_is_min_of_config_and_remaining`（5.0→5.0、剩余1→1.0、配置0.25→0.25、剩余0.25→0.25且为正）；`test_amap_client_applies_bounded_timeout_to_all_four_operations` 经 `httpx.MockTransport` 读 `request.extensions["timeout"]`，断言 `{connect,read,write,pool}` 全等于期望且不漏放大短配置 |
| 不得关闭超时 | 所有返回 timeout 断言 `0 < t < inf`；`reserve_http` 对非正 timeout 抛 deadline 而非把非正值交给 httpx |
| 不用真实 sleep 等 90 秒 | 全部用 `FakeClock`/`OffsetClock`/事件 barrier；唯一 `time.sleep` 是 loopback 启动轮询 5ms |

### 2.2 晚到分类与主失败保护

| 要求 | 证据 |
|---|---|
| 已准入响应晚到（无更早主失败）→ deadline 耗尽 + 实际 elapsed，不接受 completed | `test_late_tool_result_after_deadline_is_not_completed`：origin 发送后时钟 +91，响应晚到；结果 `failed/exhausted/deadline`，`elapsed_seconds>=90`、`tool_calls=1`、`tool_results=[]`、`result=null`、`quality=unverified` |
| 评估/收尾晚到 → 拒绝 needs_input/verified | `test_late_needs_input_after_deadline_is_rejected`（已在内存置 needs_input 后 deadline 到达仍变 failed/exhausted）；`test_cleanup_past_deadline_rejects_completed_terminal`（close 越过 deadline，completed/verified 被拒绝，实际计数与证据保留） |
| 普通单操作 timeout/provider/format 且总 deadline 未到 → 原分类 | `test_ordinary_tool_failure_keeps_classification` 参数化 timeout/provider_error/format_error：`budget.status=failed`、无 `exhaustion_reason`、issue 分别为 TOOL_TIMEOUT/TOOL_PROVIDER_ERROR/TOOL_FORMAT_ERROR、计数=1 |
| 已有主失败不被清理/时间检查覆盖 | `test_primary_failure_survives_later_deadline_check`：origin provider error 后 close 推过 90 秒，最终仍 `failed`+`budget.status=failed`、无 exhaustion_reason、保留 TOOL_PROVIDER_ERROR 且无 BUDGET_EXHAUSTED |
| 新耗尽 run 必填 reason | deadline 测试断言 `exhaustion_reason="deadline"`；call_limit 由票1 `test_api_interrupted_batch_keeps_normalized_evidence` 保持断言 `call_limit`；取消胜出时该键被删除（race 2/3） |

### 2.3 取消探针

| 要求 | 证据 |
|---|---|
| 每次 check 用短 DB 读，不包 HTTP、不持长事务 | `Store.probe_run_status` 单行 `SELECT status` + 既有 RLock（`store.py:228`），无显式事务、无网络；`LiveRuntime._observe_cancel` 只调用该函数 |
| run 缺失/读取异常必须失败并停止发送 | `test_probe_failure_is_fixed_category_without_raw_exception_text`：探针抛含 “secret /v3/geocode/geo?key=SECRET-TOKEN” 的异常 → `RuntimeControlError`，`str()` 不含原文/Key、`safe_exception_type=RuntimeError`、`tool_calls=0`；返回 None → `RUN_STATE_MISSING`、`tool_calls=0`；`reserve_http` 在分配前抛出 |
| 检查后竞争如实记录、不承诺撤回 | loopback race 1：取消提交后释放被阻塞的第二次发送，传输层只命中 `/v3/geocode/geo`（下一 handler 0 次）；文档 6.6 明写“已提交在途请求可能仍返回，不承诺严格线性化或撤回” |

### 2.4 事件循环与可达取消

| 要求 | 证据 |
|---|---|
| 创建与 LIVE 修订用 `run_in_threadpool` | `main.py:18` 导入；创建 `main.py:240`、修订 `main.py:318`；`live_clock` 从 `app.state` 注入 |
| 原 POST 仍等待终态 | `await run_in_threadpool(...)` 返回后才构造响应；无 202/worker/提前返回 |
| 等待期间同键同载荷重放拿 run_id 再取消 | `test_api_create_replay_then_cancel_stops_next_handler`：首次 POST 阻塞在第二次发送前，控制连接同键重放 202/`replayed=True` 取 `run_id`，随后原 cancel 入口 200；`test_api_revision_replay_then_cancel_stops_child_http` 对 LIVE 修订同样成立 |
| 重放不新建 factory/HTTP/完成事件 | 两测试断言等待期间 `factory_calls`/`boundary.sent`/events 计数不增；race 1 在最终保存后再次重放，断言 `events` 与 canonical 响应逐项相等 |
| 下一 handler 不命中 | race 1 用真实 `AmapAdapter` + `MockTransport`：阻塞在 `/v3/place/text` 之前，取消后释放；`boundary.sent == ["/v3/geocode/geo"]`；修订用例 `child_adapter.sent == []` |

### 2.5 取消语义与原子终态

| 要求 | 证据 |
|---|---|
| LIVE 取消响应/事件正确 mode、尽力停止文案、不含 replay/REPLAY_NOTICE/无远端声明 | `assert_live_cancel_wording`：`mode=live`、`replay_notice==LIVE_NOTICE`（不含 REPLAY_NOTICE）、message 不含“回放/无远端”、含“尽力/可能仍完成”；`CANCELLED` 事件 reason 含 `LIVE`、不含“回放”；replay 取消分支与文案未改（旧 `test_api` 断言仍绿） |
| 取消确认一次短事务归一四字段 + 删 reason | `Store.cancel_run` LIVE 分支在 `BEGIN IMMEDIATE` 内 `_normalize_cancelled` 后一条 UPDATE 写 status+budget+state（`store.py:189`）；race 1/2/3 在取消返回后立即断言四字段一致且无 `exhaustion_reason` |
| 最终保存一次短事务重新判定、归一后一次提交、返回 canonical | `Store.finalize_run`（`store.py:236`）在同一事务内读 status→必要时归一→写整行→读回 canonical；`live.py:358` 使用返回的 canonical 构造响应与 LIVE_FINISHED 事件 |
| 已提交主失败先于取消 → terminal 409 | `test_cancel_rejects_committed_live_failure`：provider error 已落盘，cancel 409 `RUN_NOT_CANCELLABLE`，重读仍 failed/failed |
| 禁止先写 cancelled+verified 再修补；GET/重放无混合终态 | race 2：最后 check 被 barrier 挡住期间取消提交，独立 loopback 连接连续 5 次 GET + 同键重放，每次都是 `cancelled/cancelled/unverified/null` 且无 exhaustion_reason；最终保存后再次 GET/重放一致。红证：临时只写 status 不归一时，同一断言立刻报 `budget.status` `'ok' == 'cancelled'` |
| 保存实际次数/elapsed/证据/原诊断 | race 1：最终 `tool_calls=1`、`tool_results=["origin"]`；race 2：`tool_calls=15`、工具证据保留、`elapsed>0`；race 3：cancel 胜出后 `BUDGET_EXHAUSTED` 留在 issues、budget 无 exhaustion_reason |

### 2.6 测试要求

- 假时钟：`FakeClock` / `OffsetClock` / `BlockingFinalClock`（无真实 sleep 等 90 秒）。
- 普通 timeout 保持分类：timeout/provider/format 三参数。
- barrier：`BlockingFinalClock.block_next` 由收尾 `close()` 置位，取消在“最后一次 check 之后、最终保存之前”提交（`test_cancel_after_final_check_normalizes_atomic_terminal`）。
- 独立连接 GET 与同键重放：真实 loopback 上 `control` 连接在窗口内 5 次 GET + 重放（不是只测最终一次 GET）。
- API 并发集成：创建与修订、原键原载荷、factory/HTTP/完成事件增量 0、下一 handler 不命中。
- 取消响应/事件 mode 断言：`assert_live_cancel_wording` + 事件 reason 断言。
- 未用真实 sleep 制造 90 秒；`time.sleep(0.005)` 只用于 loopback 启动轮询。

### 2.7 文档与诊断

- `docs/LIVE-AMAP.md` 6.5/6.6 覆盖：默认 90 秒 / 操作 5 秒、单调 elapsed、检查点、`timeout=min`、晚到拒绝、新耗尽必填/历史可缺、不能强制 90 秒返回、清理可能超时且过期终态被拒、deadline 与 cancel 两段 JSON 示例、检查后竞争、replay 取消保持原样、真实测试计数 134。
- 新增诊断只含固定类别与安全异常类型：`CANCEL_PROBE_READ_FAILED: <ExcType>`、`RUN_STATE_MISSING`、固定 `BUDGET_EXHAUSTED` 文案、`STAGE_EXECUTION_ERROR：真实渠道执行异常：<ExcType>`；测试断言 `str()` 不含伪造 secret/Key。

### [Review Focus]

“最后一次 check 之后、最终保存之前取消提交胜出；竞争中的独立连接 GET 与同键重放须始终读到归一快照，不能只检查最终一次 GET。”

由 `test_cancel_after_final_check_normalizes_atomic_terminal` 覆盖：真实 `AmapAdapter`/`MockTransport`（15 次发送）完成业务后，`close()` 之后、最终 `check()` 的时钟采样被 barrier 挡住；取消经 loopback `control` 连接提交并归一；窗口内 5 次 GET + 同键重放均读到归一快照；释放 barrier 后 `finalize_run` 在同一事务内重新判定取消、对含实际 15 次计数/证据的快照归一后一次提交，原等待 POST 返回 canonical cancelled。

## 5. 每个 seam 能抓住 / 漏掉什么

| Seam | 能抓住 | 漏掉 |
|---|---|---|
| 可注入单调时钟（`LiveRuntime(clock)`, `create_app(live_clock)`） | 0/90 边界、剩余 1s/0.25s、UTC 墙钟跳变、收尾超时、barrier 最终 check；若实现改用 UTC 会立即红 | 不证明生产 `time.monotonic` 自身（标准库语义）；不能模拟真实 socket 挂起（无真实网络） |
| `check()` 的 DB 探针 | run 缺失/读取异常阻止 reserve、取消优先于时间、取消后下一发送不命中 | 不能抓住“check 返回后到实际发送”的微窗口本身（race 测试用阻塞点显式制造该窗口）；单进程 Store，不覆盖跨进程取消 |
| `reserve_http` timeout + httpx `extensions["timeout"]` | 四操作 timeout 值、正数、不放大短配置、不关闭超时、第 N+1 次不命中 handler | 不证明 httpx read 分块/连接挂起的真实耗时；不覆盖重试/重定向（本来就没有） |
| `run_in_threadpool` | 原 POST 等待期间 loop 可受理重放/取消/GET；去掉后 replay ReadTimeout 红 | 不证明线程池容量/生产并发；单 loop、单进程；不覆盖多 worker 部署 |
| 取消确认短事务（`Store.cancel_run`） | 一次事务写 status+budget+state；只写 status 的旧行为立即红（budget.status='ok'） | 不能把内存最新计数写进确认快照（设计由最终保存写实际值）；不覆盖跨进程写者 |
| 最终保存短事务（`Store.finalize_run`） | 最后 check 后取消胜出时一次提交归一、canonical 返回、窗口内 GET/重放无混合态、已提交失败取消 409 | 两次提交之间进程崩溃的窗口（T12 已知边界）；不覆盖外部非 cancel 终态 writer（当前不存在） |
| 真实 loopback + barrier | 同进程真实 ASGI/HTTP 并发、独立连接、取消入口可达、响应/事件 mode、下一 handler 不命中 | 不是独立 OS 进程/真实网络（票3.4 owns）；`trust_env=False` 绕过本机代理；事件控制顺序而非随机调度压力 |

## 6. 红→绿记录（真实输出）

1) 起点（3bed847）：`111 passed in 9.16s`，exit 0。
2) **去掉 threadpool**（创建路由临时改回直接同步调用）→ `test_api_create_replay_then_cancel_stops_next_handler`：`1 failed ... in 21.79s`，失败为等待期间重放 `httpx.ReadTimeout: timed out`（事件循环被同步核心阻塞，重放/取消不可达）。
3) **`check()` 临时改回占位 no-op** → 5 项 deadline 测试：`4 failed, 1 passed in 1.10s`，典型断言 `assert 'completed' == 'failed'`、`assert 'needs_input' == 'failed'`（晚到结果被当正常终态接受；`test_primary_failure_survives_later_deadline_check` 是恒真的“不覆盖主失败”守卫，故在红态也通过）。
4) **取消确认临时只写 status、不归一 budget/state** → `test_cancel_after_final_check_normalizes_atomic_terminal`：`1 failed`，断言 `assert payload["budget"]["status"] == "cancelled"` → `AssertionError: assert 'ok' == 'cancelled'`（正是“混合终态”）。
5) 恢复后当前全量：见 §9（`134 passed`，exit 0）。loopback 4 项连续跑 3 轮均稳定通过。

## 7. Concerns / 已知边界

1. **两次提交非原子**：取消确认与最终保存是两个短事务（与 design 一致，T12 另处理）；本票保证各自内部一致、GET/重放不见混合终态，但不宣称跨两次提交的 exactly-once。
2. **取消确认时的计数以已持久化为准**：本次 run 的最新计数在内存中，确认事务写的是当时已持久化的计数/elapsed/证据；实际计数/elapsed/证据由原等待 POST 的最终保存写入（文档 6.6 已明说；race 1/2 断言最终值）。
3. **“更早主失败”的判据是内存 `run["status"]=="failed"`**：若取消在最终提交前胜出，内存主失败只保留为 issues 诊断、不混入 budget 主分类（符合 COLD-002）；若最终提交先完成，取消看到 terminal 返回 409。
4. **探针成本**：每次 check 一次 SQLite 单行读（每次发送约 3 次 check）；本地单进程下开销可忽略，但不做生产吞吐宣称。
5. **本机环境问题（票外）**：宿主 `NO_PROXY` 含 `[::1]`，httpx 在 `trust_env=True` 且 `transport=None` 时解析 env proxy 会抛 `InvalidURL: Invalid port ':1]'`；因此本机**无 transport 的默认 `AmapClient()` 构造失败**。测试均注入 `MockTransport`，loopback 显式 `trust_env=False`，故本票不受影响；但生产默认 LIVE factory 在本机不可用。属既有代码/环境交互，未在本票修改（避免加宽范围），见 §8。
6. **loopback 为进程内**：单 uvicorn 线程 + 127.0.0.1，不是独立进程 e2e（票3.4 负责）；不据此宣称生产并发/硬中断。
7. **`finalize_run` 直接写整行**：当前 LIVE 只有一个最终 writer + 取消 writer，靠 `BEGIN IMMEDIATE` + 状态重读实现；若未来出现第二个非 cancel 终态 writer，需要 CAS 语义（现在不存在）。

## 8. 票外发现

1. **默认 `AmapClient()` 在本机受 `NO_PROXY=[::1]` 影响构造失败**（上面 §7.5）。建议票3真实 loopback/默认 factory 或独立脚本前处理（如 provider client 显式 `trust_env=False`，或修正宿主 `NO_PROXY` 写法）；未在本票改。
2. **既有脱敏缺口仍在**：`AmapClient.get` 的 HTTPError 分支仍把 `f"{type(exc).__name__}: {exc}"` 写入 ToolResult message；provider 错误仍回显 `info` 原文而只保留 infocode 数字校验未做。属 LRC-08 / 票3.3 范围，本票新增诊断已脱敏；未顺手改。
3. **LIVE 非幂等创建仍写“回放运行创建” intake 事件**（`Store.create_run`，票1遗留文案）；本票未改，避免触碰票1已验收行为。
4. **前端未展示 `exhaustion_reason`/取消归一后的 budget**；`web/` 未改（不在本票范围）。
5. **测试环境注意**：`tests/test_live_deadline_cancel.py` 的 loopback 客户端必须 `trust_env=False`，否则在本机因 §7.5 直接构造失败；这不是测试规避产品路径，而是绕过宿主代理。

## 9. 全量验证（真实命令 / exit / 计数）

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
134 passed, 2 warnings in 19.44s
exit code 0
```

四文件子集（供 LIVE 文档复现）：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py tests/test_live_deadline_cancel.py
73 passed, 2 warnings in 8.62s
exit code 0
```

构成：旧 111（回放 61 + 高德离线 14 + live API 13 + 发送前准入/资源闭环 23）+ 本票新增 23（运行时/API deadline 19 + loopback 并发 4）= 134。2 条 warning 为 uvicorn 依赖的 websockets legacy DeprecationWarning，与本票改动无关。

## 10. 交付状态

- 改动**未提交**，位于 `3bed847` 之上；无 checkpoint 标签；票复选框未勾；design/specs/tasks/tickets 未改。
- 建议 review 重点：`app/store.py` 的 `cancel_run`/`finalize_run` 事务边界、`app/live.py` 的 `_classify_control` 主失败优先级、`app/main.py` 的 threadpool 与 LIVE cancel 分支。

### 10.6 复审记录（票2 r1）

- Standards 轴（task2-standards-r1）：**pass**，无 Critical/Important；4 条 Minor：STD-01 非正配置 timeout 被归为 deadline、STD-02 `cancel_run` 的 `missing` 分支未处理、STD-03 成功路径 finalize 在 finally 内（存储异常时可能停留 queued）、STD-04 耗尽文案两份字面量。均不阻塞本票；STD-03 关联 T12 的原子保存，其余为边界/一致性问题。
- Spec 轴（task2-spec-r1）：**pass**，8 项验收（2.1–2.6、Review Focus、R-ID）全通过；2 条 low：F1 needs_input 晚到用例未真正压住 171 行检查点、F2 UTC 跳变用例只证注入时钟（未覆盖默认 time.monotonic）。均属测试强度缺口，无行为缺陷。
- 全量回归：`134 passed in 19.83s`（exit 0，2026-11-13 由编排层独立复跑）。
- 延后处置：STD-01..04、F1、F2 均按 Minor/low 记账，不在本票扩修；若后续测试整理或 T12 触及相关路径再处理。无未处置 Critical/Important。

