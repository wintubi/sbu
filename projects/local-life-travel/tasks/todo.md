# Task List: 单日「行程判官」回放切片

> 计划正文见 `tasks/plan.md`；行为规格见 `docs/change-single-day-replay/specs.md`。
> 状态：全部已完成并验证（精确结果见 `docs/ACCEPTANCE.md`）。

## Task 1: 领域契约与纯函数

**Description:** `app/domain.py`：Pydantic 请求/工具结果/结果模型、RFC3339 与固定偏移校验、`evaluate_timeline` 纯函数、贪心重排。

**Acceptance criteria:**
- [x] 非法日期/时间窗/停留时长/候选数/时区/live 模式被拒，且给出字段名
- [x] 时间线计算使用路线秒数、停留秒数、时间窗、开放时段
- [x] 未知时长产生 `null` 而非 0/猜测值
- [x] 重排记录 changes 且只做一轮

**Verification:** `test_domain.py` 全通过；`pytest -q` 无失败。
**Dependencies:** None
**Files:** `app/domain.py`, `tests/test_domain.py`
**Estimated scope:** M

## Task 2: SQLite 持久化

**Description:** `app/store.py`：runs/events/idempotency 三表、JSON state、线程锁、WAL、每阶段保存。

**Acceptance criteria:**
- [x] 新建/读取/保存 run 往返一致
- [x] events 可查询且带阶段名
- [x] 幂等键可查可写，含 request_hash

**Verification:** `test_worker.py::test_restart_resumes_without_duplicate_stage` 用新 Store 指向同一 DB。
**Dependencies:** T1
**Files:** `app/store.py`
**Estimated scope:** S

## Task 3: 20 个回放 fixtures 与适配层

**Description:** `fixtures/scenarios.json`（6/4/3/2/3/2 分组）与 `app/replay_tools.py` 的 `ReplayAdapter`、场景解析、天气日期覆盖检查、路线矩阵。

**Acceptance criteria:**
- [x] 恰好 20 个场景，分组数量 6/4/3/2/3/2
- [x] 每个场景 request 通过 T-01 校验
- [x] 工具状态覆盖 valid/format_error/timeout/provider_error/empty/unsupported/unavailable
- [x] 天气日期不匹配返回 unavailable

**Verification:** `test_fixtures.py` 全通过。
**Dependencies:** T1
**Files:** `fixtures/scenarios.json`, `app/replay_tools.py`, `tests/test_fixtures.py`
**Estimated scope:** M

## Checkpoint A
- [x] T1–T3 单元测试通过
- [x] 20 个 fixture 可加载且 request 全部合法

## Task 4: 六阶段引擎

**Description:** `app/engine.py`：validate/resolve_poi/fetch_facts/check_constraints/adjust/finalize，状态机、issue、result、预算。

**Acceptance criteria:**
- [x] 歧义 → needs_input + candidates_for_input
- [x] 格式错误 → failed + TOOL_FORMAT_ERROR，不伪成功
- [x] 未知约束 → partially_verified
- [x] 预算超限停止且保留部分结果

**Verification:** `test_worker.py` 对应用例 + 20 场景期望。
**Dependencies:** T1, T2, T3
**Files:** `app/engine.py`
**Estimated scope:** L→拆为 3 个阶段函数组实现

## Task 5: Worker

**Description:** `app/worker.py`：tick/drain、自启动后台线程、可关闭、重启恢复。

**Acceptance criteria:**
- [x] 测试关闭自启动后可显式 drain
- [x] 新 Worker 指向同一 DB 能从 saved stage 继续
- [x] 每阶段 events 恰好一次

**Verification:** `test_worker.py::test_restart_resumes_without_duplicate_stage`。
**Dependencies:** T4
**Files:** `app/worker.py`
**Estimated scope:** S

## Task 6: API 与单文件 UI

**Description:** `app/main.py` + `web/index.html`：7 端点、统一错误体、replay 声明、状态徽标、修订/取消入口。

**Acceptance criteria:**
- [x] POST 202、GET 200、404/409/400/422 错误体一致
- [x] 幂等同键同请求/异请求行为正确
- [x] revisions 保留父 run、cancel 对终态 409
- [x] 页面含 REPLAY 横幅与状态徽标，无实时查询措辞

**Verification:** `test_api.py` 全通过。
**Dependencies:** T5
**Files:** `app/main.py`, `web/index.html`, `run.py`
**Estimated scope:** M

## Checkpoint B
- [x] 创建→轮询→结果 端到端可跑
- [x] 歧义→修订、取消、幂等、重启恢复均有测试

## Task 7: pytest 全量

**Description:** `tests/conftest.py` 提供 temp DB / 关闭自启动 / TestClient；四组测试文件。

**Acceptance criteria:**
- [x] `python -m pytest -q` 全绿
- [x] 20 场景期望全部命中
- [x] 无跳过项伪装为通过

**Verification:** 精确输出记录于 `docs/ACCEPTANCE.md`。
**Dependencies:** T1–T6
**Files:** `tests/conftest.py`, `tests/test_*.py`
**Estimated scope:** M

## Task 8: 文档与自评审

**Description:** proposal/design/specs/tasks/plan/todo、decision-memo、design-review、code-review、IMPLEMENTATION、ACCEPTANCE、README。

**Acceptance criteria:**
- [x] 明确标注自查非独立评审
- [x] 窄化范围与未运行项单列
- [x] 启动命令与验收证据可复现

**Verification:** 文件存在且内容与实现一致。
**Dependencies:** T7
**Files:** `docs/**`, `README.md`
**Estimated scope:** M

## Task 9: 最终核对与移交

**Description:** 核对精确测试结果、变更文件清单、无 git/凭据改动，并把结果发回父代理。

**Acceptance criteria:**
- [x] 报告精确 pass 数与失败数
- [x] 列出全部新增文件
- [x] 给出父代理复制命令

**Verification:** 本文件 + `docs/ACCEPTANCE.md` + 发送给父代理的消息。
**Dependencies:** T8
**Files:** —
**Estimated scope:** S

## Checkpoint C
- [x] 全部测试通过
- [x] 失败/跳过/未运行分开记录
- [x] 无 git commit/push、无凭据改动
