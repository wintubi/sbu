# 单日「行程判官」· REPLAY 本地回放切片

> **REPLAY / 本地回放演示**：不连接真实地图、天气或模型服务。POI、路线与天气全部来自 `fixtures/scenarios.json`，`provider=replay-fixture`，**结果不表示地点已核验**，也不可用于真实出行决策。
> 本目录属于 `wintubi/sbu` 的 `projects/local-life-travel/`，范围由用户 2026-11-07「按默认」「先通过吧 继续开始」批准。

## 快速开始

```bash
cd projects/local-life-travel
python run.py
# 打开 http://127.0.0.1:8765
```

Python 3.12；本次验证环境已具有所需依赖。新环境建议先建虚拟环境，再执行 `python -m pip install -r requirements-dev.txt`（只运行应用可用 `requirements.txt`）。文件固定了本次已验证的直接依赖版本，不是完整传递依赖锁文件。数据库默认写在 `data/replay.sqlite3`，可用 `TRAVEL_REPLAY_DB` 覆盖。

页面：从下拉框载入 20 个冻结回放场景 → 提交 → 自动轮询 → 查看状态/质量徽标、POI 匹配、时间线、路线依据、问题清单、调整说明、工具结果与事件日志。地点歧义时页面列出候选，选择后通过 `revisions` 创建新运行。

## 跑测试

```bash
set TRAVEL_REPLAY_NO_AUTOSTART=1
python -m pytest -q
# 期望：88 passed（回放 61 + 高德离线 14 + live API 13）
```

## 这个切片验证什么

在**固定回放数据**下，软件能否把「有效结果 / 部分结果 / 需要用户输入 / 失败」分开表达，并用确定性代码检查时空约束——而不是像第 13 章原型那样用占位景点和 `success=True` 让行程看起来成立。

- 同城、一天、一种交通方式、3–6 个已有候选地点；默认 `replay`，另有可选 `POST /api/v1/travel/live-runs`（无 `AMAP_API_KEY` 时 503，不伪造真实结果）。
- T-01 输入校验 → T-02 地点核验 → T-03 工具结果规范化 → T-04 确定性约束检查与一轮启发式重排 → T-05 持久化/预算/恢复/幂等/修订/取消 → T-06 结果与 UI。
- 20 个冻结场景：6 可行 / 4 时间冲突 / 3 地点歧义 / 2 天气覆盖不足 / 3 工具失败或格式错误 / 2 条件修改。

## 明确不做（不要误读）

真实外部 API 的已验证联调、LLM、真实 POI 核验、支付/订单/核销、多日规划、灵感发现、活动清单、公网多用户、认证与部署、LangGraph 迁移、Vue/TS 前端构建、效果阈值与模型对照实验、独立/跨模型评审、OpenSpec/sdflow 正式门禁。**不宣称原 `docs/SPEC-DRAFT.md` 全规格通过，也不宣称业务效果验收完成。**

可选的高德适配器、`live-runs` API 路径和假适配器测试已实现（14 项离线 + 9 项 live API），但历史 Key 已被回收（`USER_KEY_RECYCLED`/10013），**尚未用新 Key 成功联调**；无 Key 时返回 503，不会伪造真实结果。详见 `docs/LIVE-AMAP.md`。

真实浏览器：Chrome/CDP 已跑 F01 可行、F07 冲突、F11 歧义、F16 工具错误（`docs/evidence/ui-travel.png`）；Playwright 因临时目录 EPERM 未用。

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/IMPLEMENTATION.md` | 目录、启动、六阶段流水线、数据契约、API、fixture 格式、预算与并发、未运行项 |
| `docs/ACCEPTANCE.md` | 精确测试命令与结果、首次失败与修复、真实 HTTP 验证、20 场景矩阵、覆盖与缺口 |
| `docs/LIVE-AMAP.md` | 高德适配器、Key 现状、官方申请流程、限制与离线测试 |
| `docs/change-single-day-replay/proposal.md` | 范围、不做的事、窄化与局限 |
| `docs/change-single-day-replay/design.md` | 架构与 D1–D11 决策（含依据/代价/备选） |
| `docs/change-single-day-replay/specs.md` | S1–S6 行为规格、API 契约、issue code、验收门槛 |
| `docs/change-single-day-replay/tasks.md` | 产物索引 |
| `tasks/plan.md`, `tasks/todo.md` | 实施计划、9 个任务与检查点 |
| `docs/change-single-day-replay/decision-memo.md` | 决策记录与被否决方案 |
| `docs/change-single-day-replay/design-review.md` | **实现者自查**的设计评审（非独立评审） |
| `docs/change-single-day-replay/code-review.md` | 代码自查、父代理评审意见处置、残留风险 |

上游输入草案：`docs/SPEC-DRAFT.md`（v0.2，未被本轮修改）；仓库级交接包：`../AI-HANDOFF.md`、`../requirements-baseline.md`。

## 证据口径

计划与结果分开记录；失败、跳过、未运行分开；测试通过只代表**本机回放范围内的软件门槛**，不代表真实服务、领域效果或并发能力。详见 `docs/ACCEPTANCE.md`。
