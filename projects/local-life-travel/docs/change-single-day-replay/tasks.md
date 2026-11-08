# Tasks（变更产物索引）

本轮任务清单与验收状态统一维护在：

- `../../tasks/plan.md` — 实施计划、依赖图、风险、开放问题
- `../../tasks/todo.md` — 9 个任务的验收标准、验证方式、依赖、文件、检查点

本文件不重复清单，只记录产物映射：

| 产物 | 路径 | 对应任务 |
|---|---|---|
| Proposal | `docs/change-single-day-replay/proposal.md` | T0 范围收敛 |
| Design | `docs/change-single-day-replay/design.md` | T1–T6 设计决策 |
| Behavior specs | `docs/change-single-day-replay/specs.md` | S1–S6 |
| Tasks | `tasks/plan.md`, `tasks/todo.md` | T1–T9 |
| Decision memo | `docs/change-single-day-replay/decision-memo.md` | D1–D11 |
| Design review | `docs/change-single-day-replay/design-review.md` | 规格阶段评审 |
| Code review | `docs/change-single-day-replay/code-review.md` | 实现后自查 |
| Implementation | `docs/IMPLEMENTATION.md` | 运行与结构 |
| Acceptance | `docs/ACCEPTANCE.md` | 测试证据 |

> 说明：上游 `docs/SPEC-DRAFT.md` v0.2 明确「不是通过 OpenSpec CLI 生成、校验和评审的正式 change」，且本机未安装 sdflow/OpenSpec CLI。因此本轮产物是**人工编写、可审阅的规格与决策记录**，不宣称通过任何正式工具链门禁；范围批准来自用户 2026-11-07 的「按默认」。
