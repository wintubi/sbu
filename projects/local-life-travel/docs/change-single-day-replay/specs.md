# Behavior Specs: 单日「行程判官」回放切片 v1.0

- 状态：本轮实现的行为规格（范围已由用户「按默认」批准）。上游 `docs/SPEC-DRAFT.md` v0.2 为输入草案，本文件只覆盖本轮收窄后的 replay 切片。
- 约定：`应` = 必须实现且有测试；`不` = 明确禁止；测试 ID 对应 `tests/` 下的用例名。
- 所有结果均带 `mode: replay` 与 replay_notice；下述「核验」一律指**回放 fixture 内的记录**，不指真实供应商核验。

## T-01 输入与时间一致性

- **S1.1** 系统**应**校验 `date`（YYYY-MM-DD 可解析）、`time_window.start/end`（RFC3339 带偏移）、`end > start`、窗口 ≤ 24h、且与 `date` 为同一本地日。
- **S1.2** 系统**应**用标准库 `zoneinfo` 解析 IANA `timezone`，校验时间窗的显式 UTC 偏移与该本地日期的区域规则一致，并拒绝 DST 重叠（ambiguous）/间隙（nonexistent）的本地时间；未知 IANA 名返回字段错误。测试：`test_domain.py::test_t01_iana_offset_and_dst_validation`。
- **S1.3** 系统**应**校验 `city/origin` 非空、`transport` 在白名单、候选数 3–6、每个 `stay_seconds > 0`、候选键唯一、`name` 与 `poi_id` 恰有其一。
- **S1.4** WHEN 上述任一不成立 THEN 返回 `422 VALIDATION_ERROR` 且 `field_errors` 指明字段，**不创建 run、不调用任何工具/模型**。测试：`test_domain.py::test_t01_*`、`test_api.py::test_invalid_request_returns_422_and_no_run`。
- **S1.5** WHEN `mode != "replay"` THEN 返回 `400 LIVE_MODE_DISABLED`，不产生任何外部调用。测试：`test_api.py::test_live_mode_rejected`。
- **S1.6** 系统**不**为缺失的可选事实伪造值；影响可行性的必填信息缺失归入 S1.4。

## T-02 地点核验

- **S2.1** 每个确认地点**应**产生 `POIRecord`，含 `provider="replay-fixture"`、`provider_poi_id`、`name`、`city`、`coordinates{lon,lat}`、`fetched_at`、`evidence_refs`、`match_status`。坐标做合法范围检查。
- **S2.2** WHEN 同名出现两个及以上合理候选 THEN `run.status = needs_input`，`state.candidates_for_input` 列出候选（含 id/name/坐标），**不静默选择**、不产生 itinerary。测试：`test_worker.py::test_ambiguity_*`、`test_api.py::test_ambiguity_run_exposes_candidates`。
- **S2.3** WHEN 无匹配 THEN 写 `POI_UNMATCHED` issue，`match_status=unmatched`，**不生成坐标**、不补占位景点。测试：`test_domain.py::test_unmatched_poi_has_no_coordinates`。
- **S2.4** WHEN 匹配 POI 的 `city != request.city` THEN 写 `CROSS_CITY_POI` issue 并置 `failed`。测试：`test_domain.py::test_cross_city_poi_rejected`。
- **S2.5** 用户通过 revisions 提交 `selected_poi_ids` 后，新 run **应**据此确定唯一 POI 并重新执行后续阶段。测试：`test_worker.py::test_revision_resolves_ambiguity`。

## T-03 工具结果规范化

- **S3.1** 适配层**应**区分 `valid / empty / timeout / provider_error / format_error / unsupported / unavailable`，每个 `ToolResult` 带 `status / source_ref / fetched_at / payload / error_code? / message?`。
- **S3.2** WHEN 工具「成功」但响应无法解析 THEN 记 `TOOL_FORMAT_ERROR`，**不**返回「查询成功 + 空列表」。测试：`test_worker.py::test_format_error_not_masked_as_success`。
- **S3.3** WHEN 天气 `forecast_date != request.date` THEN 置 `unavailable` + `WEATHER_DATE_NOT_COVERED` issue，**不**把当前天气当目标日预报。测试：`test_worker.py::test_weather_out_of_coverage`、`test_fixtures.py::test_weather_scenarios`。
- **S3.4** WHEN 供应商不提供营业/预约时段 THEN `Fact.value = null`、`provider_status = unknown`，写 `HOURS_UNKNOWN`；用户 `manual_facts` 以 `source_type="manual_input"` 记录来源。测试：`test_domain.py::test_unknown_hours_not_fabricated`。
- **S3.5** 工具错误**应**在 `state.tool_results` 与 `result.issues` 中可查，且 run 不因此变成 `success=True` 语义。

## T-04 行程可行性与调整

- **S4.1** 系统**应**用 `time_window`、路线 `duration_seconds`、`stay_seconds`、已知开放时段计算 `visits[{arrival,departure}]`；未知时长时 `arrival/departure = null`，不用 0 或猜测值。
- **S4.2** WHEN 总耗时超窗 / 到达离开越界 THEN `quality_status = infeasible`，写 `TIME_WINDOW_EXCEEDED` 或 `OPENING_WINDOW_VIOLATION`，保留未满足约束，并给出可选调整建议（缩短停留、延长时间窗、通过 revisions 删除地点）。测试：`test_worker.py::test_time_conflict_scenarios`。
- **S4.3** WHEN 关键约束未知（路线缺失/超时、营业未知、天气不可用） THEN `quality_status = partially_verified`，**不**宣布已证实可行。测试：`test_worker.py::test_unknown_constraints_partial`。
- **S4.4** 仅当所有硬约束已知且满足、无工具错误、无未知事实 THEN `quality_status = verified_feasible`。
- **S4.5** 系统**应**提供一轮贪心顺序重排（非全局最优），记录 `changes`（含依据）后重新执行 S4.1–S4.4；调整轮次受预算限制。测试：`test_domain.py::test_greedy_reorder_records_change`、`test_worker.py::test_reorder_fixture`。
- **S4.6** 系统**不**自动删除地点；删除由用户通过 revisions 显式提交。
- **S4.7** `completed` 只表示处理结束，不代表行程可行。

## T-05 执行状态、预算与恢复

- **S5.1** 每次运行**应**持久化 request、阶段、规范化工具结果、版本、预算、问题、事件日志；每个阶段完成后立即落盘。
- **S5.2** WHEN 工具调用/调整轮次/总时限超上限 THEN 停止后续调用、保留已得结果、`budget.status=exhausted`、写 `BUDGET_EXHAUSTED`、置 `failed`。测试：`test_worker.py::test_budget_exhaustion_stops_and_keeps_partial`。
- **S5.3** WHEN 在已保存阶段后重启（新 Store/Worker 指向同一 DB） THEN 从 `current_stage` 继续，`events` 中每阶段恰好执行一次，**不**声称所有工具调用只执行一次。测试：`test_worker.py::test_restart_resumes_without_duplicate_stage`。
- **S5.4** WHEN 同一 `Idempotency-Key` + 相同请求重复提交 THEN 返回同一 `run_id`（`replayed=true`）；同键 + 不同请求 THEN `409 IDEMPOTENCY_CONFLICT`。测试：`test_api.py::test_idempotency_same_and_conflict`。
- **S5.5** `cancel` 对 `queued/running` 生效并返回已执行阶段数；对终态返回 409；消息**不**声称撤销远端操作。测试：`test_api.py::test_cancel_queued_run`、`test_api.py::test_cancel_terminal_conflict`。
- **S5.6** revisions **应**创建带 `parent_run_id` 的新 run，`revision = parent+1`，旧 run 与旧 result 不变。测试：`test_api.py::test_revision_keeps_parent`。

## T-06 结果与界面

- **S6.1** API `GET /runs/{id}` **应**返回输入、地点匹配、时间线、路线依据、问题清单、调整说明、工具结果、事件、预算、replay 声明；**不**暴露凭据。
- **S6.2** HTML 页面**应**展示 replay 顶部横幅、状态徽标、阶段、预算、POI 匹配、时间线、问题、证据引用与修订入口；地图为可选增强，本轮用列表/时间线代替。
- **S6.3** WHEN `needs_input / failed / partially_verified / infeasible` THEN UI 用不同徽标与文案明显区分，**不**用占位景点构造有效方案。测试：`test_api.py::test_ui_has_replay_banner_and_status_pills`。
- **S6.4** 回放完成页面**应**标明 REPLAY，不伪装为实时查询。

## API 契约（SPEC §6 落地）

| 方法与路径 | 成功 | 说明 |
|---|---|---|
| `POST /api/v1/travel/runs` | 202 | body=`TravelRequest`；header `Idempotency-Key` 可选；返回 `run_id,status,request_id,revision,mode,replayed` |
| `GET /api/v1/travel/runs/{run_id}` | 200 | 完整 `RunView`；404 `RUN_NOT_FOUND` |
| `POST /api/v1/travel/runs/{run_id}/revisions` | 202 | body=`RevisionRequest`；返回新 run |
| `POST /api/v1/travel/runs/{run_id}/cancel` | 200 | 返回 status、executed_stages、message |
| `GET /health/live` | 200 | 进程存活，不执行任何收费/外部请求 |
| `GET /health/ready` | 200 | 报告 database/worker/mode/fixtures 数；`live_mode_enabled=false` |
| `GET /fixtures` | 200 | 场景 id/category/label/request（供 UI 载入） |
| `GET /` | 200 | 单文件 HTML |

统一错误体：`{code, message, retryable, run_id?, field_errors?}`。

## Issue code 表

`VALIDATION_ERROR, LIVE_MODE_DISABLED, RUN_NOT_FOUND, IDEMPOTENCY_CONFLICT, RUN_NOT_CANCELLABLE, AMBIGUOUS_POI, POI_UNMATCHED, CROSS_CITY_POI, TOOL_FORMAT_ERROR, TOOL_TIMEOUT, TOOL_PROVIDER_ERROR, TOOL_EMPTY, TOOL_UNSUPPORTED, WEATHER_DATE_NOT_COVERED, HOURS_UNKNOWN, ROUTE_UNKNOWN, TIME_WINDOW_EXCEEDED, OPENING_WINDOW_VIOLATION, BUDGET_EXHAUSTED`。

## 回放场景冻结（SPEC §9）

20 个：6 `feasible`、4 `time_conflict`、3 `ambiguity`、2 `weather_coverage`、3 `tool_error`、2 `condition_modification`。分组与数量在本轮冻结；**它们是演示级回放，不是已有真实数据，不支持统计结论**（SPEC §9）。

## 验收门槛

- 软件门槛：全部 pytest 通过；20 个场景期望全部命中；无占位伪成功；状态可区分；重启恢复与幂等通过；服务与页面可启动。
- 未运行（明确单列）：真实服务联调、模型对照、前端标准构建（本轮无前端构建链）、p95/成本/业务效果阈值。
- 不宣称：真实 POI 核验、领域/业务效果验收、并发容量、多用户安全。
