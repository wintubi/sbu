# Proposal: 单日「行程判官」本地回放切片

- 日期：2026-11-07（Asia/Shanghai）
- 状态：**已批准范围的实现提案**。用户于 2026-11-07 以「按默认」明确确认 `projects/RESEARCH-AND-SCOPE-v0.1.md` §5.1 的 9 项默认值，并授权继续开发。
- 依据：`projects/local-life-travel/docs/SPEC-DRAFT.md` v0.2（T-01～T-06、§5 数据契约、§6 API 草案、§8 边界、§9 测试计划）、`projects/AI-HANDOFF.md`、`projects/requirements-baseline.md`、`projects/woodblock-heritage/docs/collaboration.md` 的推进顺序。
- 实施代理：delegated subagent（单一实现者）。本文件与同目录 design/specs/tasks/design-review 均由该代理编写，**未经独立评审或跨模型评审**。

## 1. 问题与目标

用户已有一份同城、单日、3–6 个候选地点的清单，需要判断「这份安排能否执行、依据是什么、哪里还不知道」。SPEC-DRAFT 指出现有第 13 章原型的失败兜底会生成占位景点、接口仍标成功，工具结果解析未完成，主链没有显式路线/时间约束检查。

本切片只验证一件事：**在固定回放数据下，软件能否把「有效结果 / 部分结果 / 需要用户输入 / 失败」分开表达，并用确定性代码检查时空约束，而不是靠提示词或占位数据让行程看起来成立。**

## 2. 本轮范围（IN）

- 同城、一天、一种交通方式、3–6 个**已有**候选地点；`replay` 单一运行模式。
- 固定回放 fixture 驱动的地点核验、天气/营业时段事实、路线时长；所有工具结果显式带状态。
- 确定性时间窗 / 停留时长 / 路线耗时 / 开放时段约束检查；简单启发式顺序重排（非全局最优）。
- SQLite 持久化：request、阶段、规范化工具结果、版本、预算、问题清单、事件日志。
- API：`POST /runs`、`GET /runs/{id}`、`POST /runs/{id}/revisions`、`POST /runs/{id}/cancel`、`/health/live`、`/health/ready`、`GET /`（简单 HTML UI）、`GET /fixtures`。
- 幂等键、修订、取消、重启恢复、预算耗尽停止。
- 20 个固定回放场景（6 可行 / 4 时间冲突 / 3 地点歧义 / 2 天气覆盖不足 / 3 工具失败或格式错误 / 2 条件修改）。
- pytest 单元测试、契约/集成/E2E 测试；实现、验收、局限文档。

## 3. 本轮不做（OUT，明确记录）

- **不连接任何真实外部服务**：无高德/MCP、无 LLM、无 OCR/VLM、无真实天气、无支付/订单/核销/平台跳转。所有 POI/天气/路线来自仓库内 JSON fixture。
- **不声称地点已核验**：所有 `POIRecord.provider = "replay-fixture"`，所有响应与页面带 `mode: replay` 和醒目回放声明。
- 不做多日、灵感发现、活动清单、购票、交易、主动触达、订阅、公网多用户、认证、限流、部署。
- 不做 LangGraph/HelloAgents 编排迁移、大小模型路由、向量库、消息队列、K8s。
- 不修改 `projects/RESEARCH-AND-SCOPE-v0.1.md`，不修改第 13 章前端/后端，不改 9 份交接文档，不合并 PR，不提交/push，不改凭据。
- 不做真实服务联调与模型对照实验；`SPEC-DRAFT` §9 的「真实服务」「模型对照」两行明确记为**未运行**。

## 4. 成功标准（软件门槛，非业务效果）

1. `pytest` 全量通过，覆盖 T-01～T-06 的确定性回归、20 个 fixture、幂等、修订、重启恢复、取消、预算、歧义、错误状态。
2. 无占位结果伪成功：任何 `matched` 之外的地点不产生坐标；任何工具失败不产生 `success=True` 语义。
3. `needs_input` / `failed` / `partially_verified` / `verified_feasible` / `infeasible` 在 API 与 UI 中可区分。
4. 重启后从已保存阶段继续，已完成阶段不重复执行；同一幂等键同请求返回同一 run，同键不同请求返回冲突。
5. 服务可用 `uvicorn` 启动，`/health/live`、`/health/ready` 与 HTML 页面可用；页面标明 replay。

## 5. 明确的窄化与局限（必须随交付一起读）

| 局限 | 原因 | 影响 |
|---|---|---|
| 只有 `replay`，`live` 请求被拒绝 | 无凭据、无付费调用授权、避免伪造真实接入 | 不能证明供应商返回契约、配额、时效、真实 POI 正确性 |
| 路线时长直接取自 fixture，未按 `transport` 重新换算 | 回放数据不含分交通方式的真实矩阵 | 交通方式字段被记录但不影响耗时；不能推断真实步行/驾车差异 |
| 顺序重排为贪心启发式，只做一轮；不自动删除地点 | T-04 允许启发式；删除地点应由用户通过 revisions 显式提交（U4） | 不保证全局最优，也不保证一定找到可行解 |
| 天气/营业时段为「事实」而非硬可行性约束；缺失时结果降为 `partially_verified` | T-03/T-04 要求未知不伪装已知 | 不会因此直接判 `infeasible`，但绝不声称已证实可行 |
| 单进程 SQLite + 线程 worker，无多实例/并发容量承诺 | SPEC §7 明确首版单进程本地 | 不能推断 p95、吞吐、多用户行为 |
| 20 个场景是演示级回放，不是统计样本 | SPEC §9 | 不能推断用户满意度、业务转化或 POI 匹配准确率 |
| 设计评审为**实现者自查** | 交接包要求区分自查/独立/跨模型评审 | 不构成独立设计批准；范围批准来自用户「按默认」 |

## 6. 证据计划

- 实现文档 `docs/IMPLEMENTATION.md`：目录、启动命令、数据契约、状态机、如何新增 fixture。
- 验收文档 `docs/ACCEPTANCE.md`：精确 pytest 命令、逐项结果、失败/跳过/未运行分开、已知问题。
- 自评审 `docs/change-single-day-replay/design-review.md` 与 `docs/change-single-day-replay/code-review.md`。
- 所有测试在本地现有依赖（Python 3.12.9 / fastapi 0.115.12 / pydantic 2.11.2 / pytest 9.0.3 / httpx 0.28.1）下运行，无新增安装。
