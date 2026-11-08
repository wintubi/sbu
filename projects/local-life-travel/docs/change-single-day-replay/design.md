# Design: 单日「行程判官」本地回放切片

- 状态：实现者编写的设计说明；范围批准来自用户「按默认」（2026-11-07）。
- 对应：`docs/change-single-day-replay/proposal.md`、`specs.md`、`tasks.md`。

## 1. 架构

```
浏览器 (单文件 HTML, 原生 JS)
   │  GET /                     GET /fixtures
   │  POST /api/v1/travel/runs  GET /runs/{id}  POST /revisions  POST /cancel
   ▼
FastAPI (app/main.py)  ── Pydantic 请求校验 (T-01，先于任何 run 创建)
   │
   ├── Store (app/store.py)  SQLite：runs / events / idempotency
   │        ▲  每完成一个阶段就持久化一次（可恢复点）
   │
   ├── Worker (app/worker.py)  单后台线程，tick() 每次只推进一个 run 的一个阶段
   │        │                 测试可关闭自启动，显式 drain()
   │        ▼
   │   Engine (app/engine.py)  纯确定性阶段函数：validate → resolve_poi →
   │        │                  fetch_facts → check_constraints → adjust → finalize
   │        ▼
   └── ReplayAdapter (app/replay_tools.py)  从 fixtures/scenarios.json 读固定工具响应
            │                                ToolResult 显式状态：valid/empty/timeout/
            └──────────────────────────────── provider_error/format_error/unsupported/unavailable
```

**单一事实来源**：`runs.state`（JSON）保存阶段产物、工具结果、POI/Fact/RouteLeg、问题、变更、订单、预算、阶段日志。`runs` 表的 `status / current_stage / revision / result` 只是便于查询的派生列，写入时始终与 `state` 同步，避免双真相源。

## 2. 关键决策（含依据、代价、备选）

| ID | 决策 | 依据 | 代价 / 备选 |
|---|---|---|---|
| D1 | 纯 `replay`，`live` 在请求层被拒 | 无凭据、无付费授权；T-06 禁止把回放伪装成实时 | 无法验证真实供应商契约；备选 live 需另立规格与凭据 |
| D2 | 每阶段一持久化、worker 每次只推进一个阶段 | T-05 要求重启恢复且不伪称远程调用只执行一次 | 阶段数多、代码稍繁；备选整次运行一次性执行会丢失可恢复点 |
| D3 | 工具适配层返回显式 `ToolStatus`，空/错/超时分别传播 | T-03 明确禁止「查询成功 + 空列表」 | 需为每个工具写状态分支；备选统一成功会重演第 13 章缺陷 |
| D4 | 约束检查用纯函数 `evaluate_timeline`，不调用模型 | T-04 要求硬约束可检查，不能用提示词替代 | 不处理偏好/模糊语义；备选 LLM 规划不可判定、不可回放 |
| D5 | 只做一轮贪心顺序重排；不自动删除地点 | T-04 允许启发式；U4 把删除交给用户 revisions | 不保证找到可行解；备选全局搜索会被误读为最优 |
| D6 | 未知关键事实 → `partially_verified`，绝不 `verified_feasible` | T-04「关键约束未知 → 部分核验」 | 回放场景多为部分核验；备选冒充已验证违反规格 |
| D7 | 单文件 HTML + 原生 JS，无前端构建 | 本轮不修改第 13 章前端，避免 Vue/TS 构建链 | 无组件化/类型检查；备选 Vue 需引入锁文件与构建门禁 |
| D8 | 用标准库 `zoneinfo.ZoneInfo` 解析 IANA 时区，校验时间窗显式 UTC 偏移与该本地日期的区域规则一致，并拒绝 DST 重叠(歧义)/间隙(不存在)的本地时间 | 满足 SPEC §5 的 IANA 契约；本机 `tzdata` 已装、无需新增依赖；`Asia/Shanghai` 历史上有夏令时（1990-07 为 +09:00），固定偏移会算错 | 仅接受 `ZoneInfo` 可解析的 IANA 名，不支持 `CST` 之类缩写；备选固定偏移白名单被设计评审否决 |
| D9 | SQLite 单连接 + `RLock`，`check_same_thread=False` | 单进程本地演示；避免连接泄漏 | 不支持多进程；备选连接池超出首版 |
| D10 | 幂等键存表，请求哈希取规范化 JSON | T-05 同键同请求返回同一 run，同键异请求冲突 | 需规范化字段顺序；备选只按 key 返回会漏冲突 |
| D11 | 修订创建新 run（`parent_run_id`，revision+1），旧 run 不变 | U4 保留旧结果、重算受影响安排 | 存储增长；备选原地修改会丢历史 |

## 3. 数据契约（对应 SPEC §5，均为最小字段 + 本轮必要字段）

- `TravelRequest`：`mode, scenario_id, city, date, timezone, origin, time_window{start,end}, transport, candidates[{name|poi_id, stay_seconds, optional_time_window?}], preferences, manual_facts[], selected_poi_ids{}`
- `Run`：`run_id, request_id, parent_run_id?, request_hash, status, current_stage, revision, versions[], budget, created_at, updated_at, mode, scenario_id, state, result`
- `POIRecord`：`internal_id, provider("replay-fixture"), provider_poi_id, name, city, coordinates{lon,lat}, fetched_at, evidence_refs[], match_status`
- `Fact`：`fact_id, subject_id, field, value|null, source_type, source_ref, fetched_at, valid_for?, provider_status`
- `RouteLeg`：`from_poi_id, to_poi_id, transport, duration_seconds, distance_meters, source_ref, fetched_at`
- `ItineraryResult`：`run_id, revision, quality_status, visits[{poi_id,arrival,departure,stay_seconds}], legs, issues, changes, evidence_refs`
- 枚举：`status = queued|running|needs_input|completed|failed|cancelled`；`quality_status = verified_feasible|infeasible|partially_verified|unverified`；`ToolStatus = valid|empty|timeout|provider_error|format_error|unsupported|unavailable`；`match_status = matched|ambiguous|unmatched`。
- RFC3339 带偏移；另存 IANA `timezone`；距离米、时长秒；经纬度做合法范围检查。
- `completed` 仅表示处理结束；缺失事实用 `null` 而不是 0/空串/猜测值。

## 4. 状态机与阶段

```
POST (校验通过) → queued
  validate        → running
  resolve_poi     → running | needs_input(歧义) | failed(格式错误/跨城)
  fetch_facts     → running（工具错误记录为 issue，不伪成功）
  check_constraints → running（生成 result + quality_status）
  adjust          → running（最多一轮贪心重排，记录 changes，重算）
  finalize        → completed（若被取消则 cancelled；预算耗尽则 failed）
```
`cancel` 对 `queued/running` 生效；对终态返回 409。重启后 `current_stage` 指向下一个未执行阶段，`completed_stages` 用于去重；`events` 表记录每阶段实际执行次数，测试断言每阶段恰好一次。

## 5. 预算

默认上限：`max_tool_calls=10`、`max_adjustment_rounds=2`、`max_total_seconds=90`、`max_model_calls=0`（本轮不调用模型）。每次工具调用、每轮调整、每次阶段执行都记账。超限即停止后续调用、保留已得结果、置 `budget.status=exhausted`、写 `BUDGET_EXHAUSTED` issue 并置 `failed`。数值取自 SPEC §8 的候选起点，**未实测，不作为性能承诺**。

## 6. 错误与状态分层

- HTTP 层：`422 VALIDATION_ERROR`（T-01，`field_errors`）、`404 RUN_NOT_FOUND`、`409 IDEMPOTENCY_CONFLICT` / `RUN_NOT_CANCELLABLE`、`400 LIVE_MODE_DISABLED`。统一 `{code,message,retryable,run_id?,field_errors?}`。
- 任务层：`run.status`。
- 质量层：`result.quality_status`。
- 工具层：`ToolResult.status` 与 issue code。四层互不替代。

## 7. 回放声明（贯穿所有输出）

每个 API 响应带 `mode: "replay"` 与 `replay_notice`；页面顶部固定横幅「REPLAY / 本地回放演示 — 不连接真实地图、天气或模型服务，结果不表示地点已核验」；`POIRecord.provider` 恒为 `replay-fixture`；fixture 文件自带 `notice`。不出现「已核验真实 POI」类措辞。

## 8. 运行与部署边界

本地可信用户、单进程。`python run.py` 后访问 `http://127.0.0.1:8765`。数据库默认写在项目 `data/replay.sqlite3`，可用 `TRAVEL_REPLAY_DB` 覆盖。无认证、无限流、无公网部署；`thread_id` 之类客户端标识不作为授权依据。
