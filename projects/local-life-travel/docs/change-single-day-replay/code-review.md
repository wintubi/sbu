# Code Review: 单日「行程判官」回放切片

> **评审性质：实现者自查（self-review）**，由编写本轮代码的同一 delegated 代理执行。
> **不是**独立评审、**不是**跨模型评审、**不是**用户批准记录。父代理将独立评审与验证。
> 日期：2026-11-07（Asia/Shanghai）。范围：`app/*.py`、`run.py`、`web/index.html`、`fixtures/scenarios.json`、`tests/*`。

## 1. 父代理初步评审的处置（全部已修）

| # | 问题 | 处置 | 验证 |
|---|---|---|---|
| C1 | `await request.json()` 未处理 `JSONDecodeError` → 非法 JSON 500 | 新增 `read_json()`，捕获 `json.JSONDecodeError/UnicodeDecodeError/ValueError` 并统一 422 `VALIDATION_ERROR`；create 与 revisions 都使用 | `test_malformed_json_returns_422_not_500`、`test_malformed_json_on_revisions_returns_422` |
| C2 | `/health/ready` 在后台 worker 已死时仍报 ready；缺少生命周期关闭 | `create_app(manual_drain=...)` 区分显式测试模式；非测试模式 worker 不存活即 `degraded`；增加 `asynccontextmanager` lifespan 启动建 store/worker、关闭时 `worker.stop()`；`owns_resources=True` 时关闭 store | `test_health_live_and_ready`；真实服务器验证 shutdown 后 `is_alive=False` |
| C3 | worker 静默捕获异常、假设 engine 已持久化失败 → 可能无限重试 | `tick()` 捕获异常后写 `logger.exception`，落 `STAGE_EXECUTION_ERROR` issue、置 `failed`、写 `STAGE_ERROR` 事件；`drain()` 不再重复拾取 | `test_worker_logs_unexpected_error_and_marks_terminal` |
| C4 | 取消存在丢失更新；幂等非原子 | `Store.cancel_run()` 用 `BEGIN IMMEDIATE` + 条件 `UPDATE ... WHERE status IN ('queued','running')`；`save_run` 用 `CASE WHEN status='cancelled'` 防止在途写复活；`create_run_atomic()` 把 run + idempotency + intake event 放同一事务 | `test_cancel_cannot_be_resurrected_by_late_save`、`test_cancel_queued_run`、`test_idempotency_same_and_conflict` |
| C5 | 固定 +08:00 白名单是对 IANA 契约的无理由降级 | 改用 `zoneinfo.ZoneInfo` 真实解析 + 偏移校验 + DST 歧义/间隙拒绝；同步修正 5 份文档 | `test_t01_iana_offset_and_dst_validation`；实测 1990-07 Asia/Shanghai 为 +09:00 |

## 2. 自查发现并修复的问题

| # | 严重度 | 问题 | 修复 |
|---|---|---|---|
| S1 | 高 | `evaluate_timeline` 中前序路线未知后 `current=None`，后续已知路线仍做 `None + timedelta` 抛 `TypeError` | 条件改为 `if not leg_ok or current is None`，统一走 null 分支并写 `ROUTE_UNKNOWN`；`test_t04_unknown_duration_uses_null_not_zero` |
| S2 | 中 | DST 间隙被误判为歧义（fold 偏移先比较） | 先做 UTC 往返判间隙，再比较 fold 偏移判歧义 |
| S3 | 中 | `resolve_scenario` 未把 `defaults.candidates` 放进 request，导致 13 个场景请求缺字段 | `request["candidates"] = deepcopy(defaults["candidates"])` 后再合并 overrides；`test_all_fixture_requests_are_valid` |
| S4 | 中 | `max_total_seconds` 只声明未执行 | `_Context.call()` 按 `created_at` 计算 elapsed，超限抛 `BudgetExhausted`；新增 `test_budget_total_time_limit_is_enforced` |
| S5 | 低 | `adjust` 对 `partially_verified` 也做重排（未知事实无法靠排序修复） | 仅 `infeasible` 时重排 |
| S6 | 低 | `TOOL_UNAVAILABLE` / `STAGE_EXECUTION_ERROR` 不在 issue code 表 | 补入 `ISSUE_CODES` |
| S7 | 低 | 项目根 `.pytest_cache` 写入被沙箱拒绝产生告警 | 项目内 `pytest.ini` 加 `-p no:cacheprovider`（未添加仓库根配置） |

其中 S1/S2 是**首次 pytest 运行实际发现的 2 个失败**（`2 failed, 57 passed`），修复后全绿；其余为自查/父代理评审发现。

## 3. 规格符合性抽查

| 条款 | 实现 | 证据 |
|---|---|---|
| T-01 | 非法请求 422 + `field_errors`，不创建 run、不调工具；`live` 400 | `test_invalid_request_returns_422_and_no_run`、`test_live_mode_rejected` |
| T-02 | 歧义→`needs_input`+候选；未匹配无坐标；跨城 `failed`；修订选候选 | `test_ambiguity_needs_input_with_candidates`、`test_unmatched_poi_has_no_coordinates`、`test_cross_city_poi_rejected`、`test_revision_resolves_ambiguity` |
| T-03 | 七态 `ToolStatus`；格式错/超时/供应商错/unsupported/unavailable 分别落 issue；天气日期不覆盖标 unavailable；人工补充标 `manual_input` | `test_format_error_not_masked_as_success`、`test_weather_scenarios_do_not_use_current_weather`、`test_unknown_constraints_partial` |
| T-04 | 纯函数约束检查；未知→null；硬违规→`infeasible`；未知→`partially_verified`；一轮贪心重排并复算 | `test_t04_*`、`test_time_conflict_scenarios_are_infeasible`、`test_reorder_fixture_records_change` |
| T-05 | 每阶段落盘；预算三上限；重启恢复；幂等；修订保留父；取消 | `test_restart_resumes_without_duplicate_stage`、`test_budget_*`、`test_idempotency_*`、`test_revision_keeps_parent_result`、`test_cancel_*` |
| T-06 | RunView 全字段 + replay 声明；UI 状态/质量徽标与 REPLAY 横幅；无占位方案 | `test_ui_has_replay_banner_and_status_pills`、`test_every_response_carries_replay_declaration`、`test_create_and_poll_run` |

## 4. 未解决 / 接受的风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 无真实供应商验证 | 无法证明真实返回契约/配额/时效 | 明列为未运行；live 另立规格 |
| 路线矩阵不按交通方式换算 | `transport` 只被记录 | 文档局限写明 |
| 单进程 SQLite | 无并发容量/多实例恢复 | SPEC §7 首版限定 |
| 每阶段重新读取 fixtures JSON | `advance()` 在无注入 adapter 时调用 `get_scenario()` 重新解析文件 | 20 场景本机无性能问题；后续可缓存 |
| 自查非独立评审 | 可能遗漏实现者盲点 | 明确标注；父代理独立验证 |
| 目标目录写入受限 | 实现位于工作区镜像 | 位置无关代码 + 精确复制命令 |

## 5. 结论

- 实现与 `docs/change-single-day-replay/specs.md` S1–S6 的自查一致；`python -m pytest -q` → **60 passed**；真实 uvicorn HTTP 端到端通过。
- **本结论不是独立/跨模型评审通过，也不是原 SPEC-DRAFT 全规格通过，更不是业务效果验收。**
- 未运行项与失败/跳过分开记录在 `docs/ACCEPTANCE.md`。
