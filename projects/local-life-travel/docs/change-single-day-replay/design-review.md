# Design Review: 单日「行程判官」回放切片

> **评审性质：实现者自查（self-review）。** 由编写本轮代码的同一 delegated 代理执行。
> 它**不是**独立评审、**不是**跨模型评审、**不是**用户批准记录，也**不宣称**通过任何 OpenSpec/sdflow 正式门禁。
> 上游 `collaboration.md` 要求「自查、独立评审和跨模型评审必须如实区分」；本文件只代表自查。
> 范围批准来自用户 2026-11-07 的「按默认」，见 `decision-memo.md` A0；父代理将做独立评审与验证。
>
> 日期：2026-11-07（Asia/Shanghai）。评审对象：`proposal.md` / `design.md` / `specs.md` / `tasks/plan.md` / `tasks/todo.md`。
>
> **状态说明（父代理评审意见已纳入）**：本文中的测试用例名称为**计划用例**，在 `tests/` 实际落地并通过之前不标记为「已加/已验证」。实际结果由实现后的 `docs/ACCEPTANCE.md` 与 `docs/change-single-day-replay/code-review.md` 单独记录。

## 1. 评审问题与逐项处置

| # | 问题 | 自查结论 | 处置 |
|---|---|---|---|
| R1 | 领域语义：T-01～T-06 是否都被行为规格覆盖？ | 是，S1–S6 与 T-01–T-06 一一对应，每条带测试 ID | 保留；`specs.md` 末尾列未运行项 |
| R2 | 数据链路：工具原始返回 → POIRecord/Fact/RouteLeg 是否可追溯？ | 是，每个 `ToolResult` 有 `source_ref`，POI/Fact/Leg 带 `evidence_refs` | 保留；计划用例 `test_fixtures.py::test_provider_is_replay_fixture` |
| R3 | 失败模式：工具失败会不会被当成成功？ | 设计上不会：`ToolStatus` 七态 + issue code + `failed` 或 `partially_verified` | 计划用例 `test_worker.py::test_format_error_not_masked_as_success`；**待实装验证** |
| R4 | 工程可行性：依赖是否都已安装、是否引入大安装？ | 已实测：Python 3.12.9 + fastapi 0.115.12 / pydantic 2.11.2 / pytest 9.0.3 / httpx 0.28.1 / starlette 0.46.1 均在；只用标准库 `sqlite3` 与 `zoneinfo`（`tzdata` 已随环境安装） | 无新增安装；版本记录于 `ACCEPTANCE.md` |
| R5 | 验收覆盖：20 场景分组与 SPEC §9 一致？ | 是，6/4/3/2/3/2 | 计划用例 `test_fixtures.py::test_scenario_groups`；**待实装验证** |
| R6 | 是否把 replay 说成真实核验？ | 设计上未发现：API/UI/fixture/文档四处 replay 声明，POI `provider` 固定 `replay-fixture` | 计划用例 `test_api.py::test_ui_has_replay_banner`；**待实装验证** |
| R7 | 是否存在双真相源？ | `runs.state` 为主，其余列为派生，写入时同步 | 保留；集中在 `Store.save_run()` |
| R8 | 重启后阶段是否会重复执行？ | 设计上用 `completed_stages` + `events` 去重，新 Store 可恢复 | 计划用例 `test_worker.py::test_restart_resumes_without_duplicate_stage`；**待实装验证** |
| R9 | 幂等冲突是否可能漏判？ | 设计上用规范化 JSON 哈希，非仅 key | 计划用例 `test_api.py::test_idempotency_same_and_conflict`；**待实装验证** |
| R10 | 是否越权修改？ | **修正（父代理指出）**：本子代理被沙箱拒绝写入 `D:\git\sbu\projects\local-life-travel`，且 escalation 被用户拒绝；因此**实际写入路径是会话工作区镜像 `D:\workspace-dsh\local-life-travel\**`**，需父代理复制到仓库。本轮不写 `projects/RESEARCH-AND-SCOPE-v0.1.md`、不改第 13 章代码、不改 9 份交接文档、不合并 PR、不提交/push、不改凭据 | 已在 `decision-memo.md` D16 与 `tasks/plan.md` 风险表记录；移交时给出精确复制命令 |
| R11 | 效果指标是否被冒充已完成？ | 未冒充；「真实服务联调 / 模型对照 / 效果阈值 / 前端标准构建」列为未运行 | 保留在 `ACCEPTANCE.md` |
| R12 | 规格是否自相矛盾？ | 发现 4 处需澄清，见 §2 | 已在 design/specs/domain 中修正 |
| R13 | 时区实现是否满足 SPEC §5 的 IANA 要求？ | **修正（父代理指出）**：初稿用固定 +08:00 白名单是对原规格的无理由降级；`zoneinfo` 与 `tzdata` 在本机可用，且 `Asia/Shanghai` 1990-07 曾为 +09:00 | 改为 `ZoneInfo` 真实解析 + 偏移校验 + DST 歧义/不存在本地时间拒绝；见 §2 P4 |

## 2. 发现并已处置的设计问题

- **P1（已修）**：初稿把「天气不可用」直接判 `infeasible`，与 T-03「标 unavailable、不把当前天气当目标日预报」和 T-04「关键约束未知 → 部分核验」冲突。处置：天气/营业为**事实层**，缺失时写 issue 并把 `quality_status` 降为 `partially_verified`，不直接判不可行，也绝不判 `verified_feasible`。见 `decision-memo.md` D13。
- **P2（已修）**：初稿允许引擎自动删除地点以满足时间窗，会绕过 U4「用户删除地点后创建新版本」并可能掩盖冲突。处置：只做一轮贪心顺序重排，删除改由 `POST /revisions` 显式提交；冲突场景保留 `infeasible` 与调整建议。见 D5。
- **P3（已修）**：初稿用 `0`/空串表示缺失路线时长，违反 SPEC §5「missing fact 不以 0、空字符串或猜测事实代替」。处置：`arrival/departure = null`，`Fact.value = null`。
- **P4（已修，父代理评审）**：初稿以「避免 tzdata 依赖」为由把时区降级为固定 +08:00 白名单。实测 `tzdata` 已安装、`ZoneInfo("Asia/Shanghai")` 可用，且该时区历史上有夏令时，固定偏移会算错历史日期。处置：`domain.resolve_zone()` / `validate_local_datetime()` 用标准库做真实 IANA 解析，校验显式偏移与区域规则一致，并拒绝 DST 重叠（fold=0/fold=1 偏移不同）与 DST 间隙（UTC 往返不一致）的本地时间；`evaluate_timeline` 在 IANA 时区下换算 HH:MM。同步修正 `proposal.md` 局限表、`design.md` D8、`decision-memo.md` D8、`specs.md` S1.2、`tasks/plan.md` 风险表。

## 3. 仍未解决 / 明确接受的风险

| 风险 | 严重度 | 说明 | 缓解 |
|---|---|---|---|
| 无真实供应商契约验证 | 高 | 无法证明 POI/路线/天气真实返回格式、配额、时效 | 明列为未运行；live 另立规格 |
| 路线时长未按交通方式换算 | 低 | fixture 只有一套对称矩阵，`transport` 只被记录 | 文档局限写明；不推断真实步行/驾车差异 |
| 单进程 SQLite | 中 | 无并发容量、多实例恢复能力 | SPEC §7 已限定首版单进程 |
| 自查非独立评审 | 中 | 可能遗漏实现者盲点 | 明确标注；父代理将做独立评审与验证 |
| 20 场景为演示级回放 | 中 | 不能推断业务效果 | SPEC §9 口径，文档写明 |
| 无前端构建链 | 低 | 单文件 HTML 无类型检查/组件化 | 本轮不修改第 13 章前端；后续 Vue 需另立构建门禁 |
| 目标目录写入受限 | 中 | 实现落在工作区镜像，需父代理复制 | 位置无关代码 + 精确复制命令 + 文件清单 |

## 4. 门禁结论

- **设计评审（自查）结论：可以进入实现**，条件是 §2 四个问题修掉（P1–P4 已修）并把 §3 风险如实写入交付文档。
- 本结论**不等于**用户新增批准，**不等于**独立/跨模型设计评审通过，**不宣称** OpenSpec/sdflow 正式门禁已通过。
- §1 中标注「计划用例」的条目在测试实装前不算验证通过；实际结果见 `docs/ACCEPTANCE.md` 与 `docs/change-single-day-replay/code-review.md`。
- 实现后的代码自评审与验收证据单独成文，计划与结果分开记录。

## 5. 实现后复核（补记，2026-11-07）

本文 §1 中标注「计划用例」的条目现已全部实装并运行。复核结论基于 `docs/ACCEPTANCE.md` 的实测结果：

- `python -m pytest -q` → **60 passed, 0 failed, 0 skipped**（首次 2 failed 已修复并复测通过）；`tests/` 四组共 60 个用例。
- 真实 uvicorn 服务：`/health/live`、`/health/ready`（worker=running、fixtures=20）、`/fixtures`、`/` 均 200；`POST → 202 queued → 轮询 completed/verified_feasible`；lifespan 关闭后 worker 已停止。
- 20 个冻结场景期望矩阵全部命中；父代理代码评审 C1–C5 与自查 S1–S7 均已处置，见 `code-review.md`。
- 用户于 2026-11-07「先通过吧 继续开始」确认该 replay 首版设计获准进入实现（见 `decision-memo.md` A0）。

**本次复核仍是实现者自查，不是独立/跨模型评审，也不是原 SPEC-DRAFT 全规格通过或业务效果验收。** 未运行项、失败/跳过与残留风险见 `docs/ACCEPTANCE.md`；父代理将独立评审与验证。
