# Implementation Plan: 单日「行程判官」本地回放切片

## Overview

在 `projects/local-life-travel/` 内交付一个不联网的 replay 最小闭环：FastAPI + SQLite 持久 worker + 固定 fixture 工具适配层 + 纯确定性约束引擎 + 单文件 HTML 页面，配 20 个回放场景与 pytest 回归，并留下 proposal/design/specs/tasks/评审/验收证据。依据 `docs/change-single-day-replay/specs.md` 的 S1–S6。

## Architecture Decisions

- 自底向上：`domain.py`（契约+纯函数）→ `store.py`（SQLite）→ `replay_tools.py`（fixture 适配）→ `engine.py`（阶段）→ `worker.py` → `main.py`（API+UI）。
- 每阶段一持久化；`runs.state` 为唯一事实来源。
- 只做 replay；工具状态显式；未知事实降级为 `partially_verified`；不自动删除地点。
- 全部路径相对 `__file__`，便于整体复制到仓库后原样运行。

## Dependency Graph

```
fixtures/scenarios.json (数据契约样例)
        │
   domain.py (TravelRequest / ToolResult / evaluate_timeline)
        │
   store.py (runs / events / idempotency)
        │
   replay_tools.py (ReplayAdapter)
        │
   engine.py (6 阶段) ── worker.py (tick/drain/线程)
        │
   main.py (API + 静态 HTML) ── web/index.html
        │
   tests/* ── docs/ACCEPTANCE.md
```

## Task List（垂直切片，顺序即依赖顺序）

### Phase 1: Foundation
- [ ] T1 领域契约与纯函数（domain.py）：request 校验、时间计算、ToolStatus、evaluate_timeline、贪心重排。验收 S1.1–S1.3、S4.1–S4.5。
- [ ] T2 持久化（store.py）：建表、create/get/save、事件、幂等键、线程锁。验收 S5.1、S5.3、S5.4 存储基础。
- [ ] T3 回放 fixtures（fixtures/scenarios.json）与适配层（replay_tools.py）：20 场景、6 类状态、天气日期覆盖检查、路线矩阵。验收 S3.1–S3.4。

**Checkpoint A**：T1–T3 单元测试通过，20 个 fixture 能加载且 request 全部通过校验。

### Phase 2: Core
- [ ] T4 阶段引擎（engine.py）：6 阶段状态机、歧义/错误/未知分支、预算记账、result 生成。验收 S2、S3.5、S4、S5.2。
- [ ] T5 Worker（worker.py）：tick/drain、自启动线程、restart 可恢复。验收 S5.3。
- [ ] T6 API + UI（main.py / web/index.html）：7 个端点、统一错误体、replay 声明、状态徽标。验收 S6、S5.4–S5.6。

**Checkpoint B**：API 端到端「创建→轮询→结果」可跑；歧义→修订、取消、幂等、重启恢复有测试。

### Phase 3: Verify & Deliver
- [ ] T7 pytest 全量：domain / api / worker / fixtures 四组，含 20 场景期望断言。
- [ ] T8 文档：plan/todo、自设计评审、决策记录、代码自评审、IMPLEMENTATION、ACCEPTANCE、README。
- [ ] T9 最终核对：精确测试结果、文件清单、局限与未运行项。

**Checkpoint C**：全部测试通过；文档记录失败/跳过/未运行；无 git 提交/push/凭据改动。

## Risks and Mitigations

| 风险 | 影响 | 缓解 |
|---|---|---|
| 目标目录写入被沙箱拒绝 | 无法直接落在 `D:\git\sbu\projects\local-life-travel` | 在会话工作区构建位置无关镜像，交给父代理一条命令复制；本文件随实现一起交付 |
| pytest 9 / httpx 0.28 与 FastAPI TestClient 兼容 | 测试跑不起来 | 先做最小导入探针，失败则改用 `httpx.ASGITransport` 手写异步客户端 |
| Windows 无系统时区库 | ZoneInfo 可能失败 | 已实测 `tzdata` 已安装、`ZoneInfo("Asia/Shanghai")` 可用；改用标准库真实 IANA 校验，不采用固定偏移 |
| fixture 与实现互相迁就 | 测试只验证自己的假设 | fixture 期望独立于实现硬编码；测试断言期望值而非实现输出 |
| 把 replay 说成真实核验 | 违反 T-06 | 所有响应/页面/文档带回放声明；POI provider 固定 `replay-fixture` |
| 单线程 worker 与 TestClient 竞争 | 测试不稳定 | 测试用 `TRAVEL_REPLAY_NO_AUTOSTART=1` 显式 drain |

## Open Questions（不阻塞本轮，记录待用户/后续规格处理）

- 真实供应商渠道、配额、凭据与预算（SPEC P2）。
- 营业/预约信息拿不到时的产品策略是否长期保持「两者并存」（SPEC P3）。
- 效果阈值（POI 匹配、有效完成率、p95、成本）与独立验收集（SPEC §9）。
- 是否引入 LangGraph 状态图 / Vue 前端构建（SPEC P4、§7）。
- 编排框架、模型对照实验的设计与预算。
