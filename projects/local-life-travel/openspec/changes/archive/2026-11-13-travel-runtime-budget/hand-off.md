# hand-off — travel-runtime-budget

> 生成于 2026-11-13。依据 `verify-report.md`（PASS）、`code-review-report.md`（pass）与各 ticket 报告；每条“完成”都复核过锚点存在性。

## ✅ 完成了什么

- **LRC-01 发送前准入**：`app/runtime.py` 的 `reserve_http` 在唯一 HTTP 发送点 `AmapClient.get` 前预占；`limit=0/1/2/40` 与“第 N+1 次不进传输层”有测试（`tests/test_live_admission.py`），`_record` 的 `max(1,差额)` 已移除。
- **LRC-02 单调 deadline**：可注入 clock、默认 90 秒，检查点覆盖发送前/返回后/阶段间/评估前后/终态与收尾；四类 HTTP timeout 取 `min(配置, 剩余)`；`tests/test_live_deadline_cancel.py` 用假时钟验证 0/90、UTC 跳变、0.25 秒配置。
- **LRC-03 可达取消与原子终态**：创建/修订走 `run_in_threadpool`，等待期间同键重放可拿 run_id 并调用原 cancel；取消确认与最终保存各一次短事务归一 `cancelled/cancelled/unverified/null` 并删除 `exhaustion_reason`；barrier 下独立 GET/重放无混合终态。
- **LRC-04 可解释耗尽**：耗尽保存 `failed/exhausted` + `exhaustion_reason=deadline|call_limit`，保留实际计数、elapsed 与已有证据；晚到结果不接受为 completed/verified。
- **LRC-05 幂等**：同键同载荷返回原 run、不建 runtime/factory、不新增 HTTP/事件；同键异载荷 409、缺 Key 503 保留。
- **LRC-06/07 运行控制与拥有权**：adapter 必须有 `bind_runtime`+`close`，activ​e 互斥；六类出口各 close 一次、借入只解绑、失败绑定不碰原 owner；默认 factory 显式 `owns_client`。
- **LRC-08 脱敏与清理失败**：HTTPError 只留类型、provider 只留数字 infocode；清理异常记固定 `RESOURCE_CLEANUP_FAILED`、不覆盖主失败、不宣称已释放；合成 Key/query/私人标记扫描覆盖 API/state/events/SQLite。
- **LRC-09 真实范围材料**：README/LIVE-AMAP/ACCEPTANCE/任务报告互链；明确未联调真实高德、未验硬中断/灾备/生产并发。
- **验证**：`159 passed`（39.14s）、独立进程 loopback `E2E_OK`；code-review 5 镜 + 6 项修复 + 复审 pass；`anchor_lint` CLEAN。
- **验收证据锚**：`verify-report.md` 的逐需求表；`code-review-report.md`；`impl-reports/task4-aggregate.md`；commit `74ab503`（代码审修复）、`e8aaf25`（verify 锚）。

## ⏳ 未完成 / 延后

按 summary 前缀「既有问题：」分组（本 change 的 issue 池扫描工具按 git 根解析，产品根下的 B1–B3 未被扫到，以下按文件实核列出）：

**本 change 延后项**

- `B3` LIVE finalize 失败时 run 可能停留 `queued`，幂等重放只回 queued；需 T12 原子保存处理。`app/live.py` 的 finalize 仍在 finally 内，属已知边界。
- `B1` 既有（base 6a78560）provider 列表元素非 dict 时 `AttributeError` 逸出，未归 `TOOL_FORMAT_ERROR`；`B2` 既有 adcode 失败统一报 `provider_error`、timeout 分类丢失。两条非本 change 引入，已入 bug 池。

**发现的既有问题（非本 change 引入）**

- 同 `B1`、`B2`（按 issue id 去重）。
- verify 的 Minor：`docs/ACCEPTANCE.md`/`LIVE-AMAP.md` 仍写旧分项（93/134+19+1），与 159 不一致；`docs/ACCEPTANCE.md`/`LIVE-AMAP.md`/`TECH-STACK.md`/`ARCHITECTURE.md` 仍有“未做独立代码审”的旧表述（保守低报，review 已 pass）。属文档一致性，未在 verify 后改（改产品文档会使审查锚失鲜），留给下一轮文档同步。
- 跨模型 code voice 未运行：本会话子代理限制在父级路由，`host-unknown` 如实记录，未用同族冒充。
- `ADR 同步：跳过（adr: openspec/adr 不存在或不是目录，refs 退出 2）`。
- `roadmap 回填草稿未生成：NO_ASSOCIATION（未声明关联且名前缀不符）`；若本 change 属某 roadmap，请手动回填。
- proposal 无「来源 issue：」行，未自动关单。

## ▶ 下一阶段建议

1. **T12**：阶段与事件原子保存；顺带处理 `B3`（finalize 失败留 queued）与 LIVE 两次提交非原子。
2. **T13/H11**：readiness 语义（worker 停止→degraded）。
3. **P17**：结构化脱敏日志（replay worker 的 `str(exc)` 也在范围内另评）。
4. **文档一致性清理**：把 `docs/` 里旧分项 93/134+19+1 与“未做独立代码审”统一到 159 + 已审，避免与 verify/code-review 报告矛盾。
5. **B1/B2 清理**：provider 非 dict 元素归 `TOOL_FORMAT_ERROR`；adcode 失败保留 timeout 分类。
6. 新方向（Python Agent—Java—Vue、动态 DAG）仍按独立 spec/评审推进，不在本 change 内。

`ADR 同步：跳过（adr: openspec/adr 不存在或不是目录，refs 退出 2）`
