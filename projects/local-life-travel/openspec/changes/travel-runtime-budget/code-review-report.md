---
ship-gate:
  code_review: pass
  reviewed_sha: a75cf20b74ae6f1f910bf4fe16cd6028766a439b1071735c9f423b08a11535e8
  reviewed_manifest: MTAwNjQ0IGJsb2IgYmYzNjg3ZWIwZGYzYjE1MjgzMDc5YWViOWE4ZWM2ZGY4NzE3MjEyYQkuZW52LmV4YW1wbGUAMTAwNjQ0IGJsb2IgYTc1YWMxOGQ5NzFjZjZkZDhjNzE5Y2NjOWY0MGJmYzMyNDg5N2RmMgkuZ2l0aWdub3JlADEwMDY0NCBibG9iIGE4ZWJkYTlhNjliMTkwMTJjZjU4ZDg5ZjVlMWQzM2U4MGViNTg2OTQJQUdFTlRTLm1kADEwMDY0NCBibG9iIGVlNzk2OWNiMmE2NTQ3OTE4ZDU4NTVhMTQzYzUyOWU2ZWU5N2E0MmQJQ0xBVURFLm1kADEwMDY0NCBibG9iIGVhYjNkYzg5OTM2M2EyMGQ0YjRhMGFhZTExY2U5ZTcwMzNkOTNiNTIJUkVBRE1FLm1kADA0MDAwMCB0cmVlIDRjNTQwNTg1NGFhZGVlZTFjNGIzZTE2NmJiMDI0M2E4ZjFiNzRkNWUJYXBwADA0MDAwMCB0cmVlIDEyNmYyNDkyMWVkYzJkYjRkOGZlMGU1Y2RjODlkN2FiODI0NWZjM2UJZG9jcwAwNDAwMDAgdHJlZSA4ZTQ3OWU2Yjc2NjA3M2MwNGQwYTA0ZDY0MGMxYjhkYzhjM2VkMzNhCWZpeHR1cmVzADEwMDY0NCBibG9iIDMzMjUzZTk3MTBkMTM0Y2M5OTE3MmE3YmU5MDAxNjE4YmFkYWVhNGYJcHl0ZXN0LmluaQAxMDA2NDQgYmxvYiA4MzRiZTY5YTUxMTExOTEyNTRjMDIxNzM1ZmZiZDkwMGRmNzQ4NWVjCXJlcXVpcmVtZW50cy1kZXYudHh0ADEwMDY0NCBibG9iIGM0M2Y3YzNjYWNlYjg4MjZjMzQ0NzM5NGJjZTA2YTk4NDVmN2M1ZDgJcmVxdWlyZW1lbnRzLnR4dAAxMDA2NDQgYmxvYiBiZTlmNWVmNmVkZmMxYWQwZDk3YTliNzMwNmQyODdjMjhhMTg0ZGYxCXJ1bi5weQAwNDAwMDAgdHJlZSA4YWQzNzNjNWExYzI1NjViNDJiZmZiMDQzYTdmNTk1MDhjZGJlM2YxCXNjcmlwdHMAMDQwMDAwIHRyZWUgNTQ1ZDYwMjI5MWExMmIzMTJkMDI4NTUyYjZlNjdjMjg0Y2IxN2IxYgl0YXNrcwAwNDAwMDAgdHJlZSAwNWY4NjRmMmEyNzM4N2U4ZWJkMWU5NGRlYzg1ZGEzYThiNDE5YWMzCXRlc3RzADA0MDAwMCB0cmVlIGRkNzRlMDg4ZTY0MzNiYjZkYTk4MDgzNDJjYTY5OTU2NDQ2ODNkN2QJd2Vi
---
# code-review 报告 — travel-runtime-budget

> 调用方：ship（gate RUN_CODE_REVIEW）。评审范围 `6a785607e4bdb52e6c1af95e7b7b585d1b5d035b..74ab503`（含代码审自动修复）。
> 本报告正文手写；头部 frontmatter 由 `anchor_writeback.py` 权威写入。

## 命中范围

- 栈：Python 3.12 / FastAPI / SQLite；清单：`code-review-base.md` 全部 CR-01..CR-12 + backend delta。
- Step1 自持 scope 审计（`impl-reports/cr-scope.json`）：15 项任务 **14 DONE / 1 CHANGED**（1.3 的 CountingAdapter 被删除、fake 改为逐 HTTP reserve，契约意图满足），无 NOT DONE、无 UNVERIFIABLE 阻塞项；切片偏离与 `planning-decisions.md` 一致，无静默偏离。
- 镜集合：领域镜 1、对抗镜 3（并发/资源/错误路径）、历史镜按条件跳过（无 rename、无 ≥200 行既有文件改动）、Step1 scope 审计 1。
- `trivial_shape`：NOT_EXEMPT（有逻辑面），故全量 fan-out。

### 子代理能力锚

<!-- sdflow:fanout-capability v1 host="unknown" subagents="available" mirrors="domain,adversarial,broad" -->

host 仍为 `unknown`（resolver 判不出原生宿主）；本轮按**真人已批准的 T11-only DSH 阶段三适配**用 DSH 子代理完成上述镜，未伪造原生 claude/codex 信号。`mirrors` 只列实际独立完成的镜；历史镜未派（条件未命中）。

## Findings（已采纳）

- [已修] SCOPE-DOC-01 文档事实 | `docs/TECH-STACK.md:5`、`docs/ARCHITECTURE.md:4` | 仍写“T11 半成品在 git stash”，与已提交的 T11 票 1–4 矛盾 | 置信 95 | 已改为票级双轴通过、未独立代码审、未合并。
- [已修] CRD-02 CR-01/CR-02 | `app/main.py:382` | `Store.cancel_run` 的 `missing` 未处理，会 200 + 旧快照 + 写 CANCELLED 事件 | 置信 90 | 改为 404 `RUN_NOT_FOUND`，写事件前抛出；补测试。
- [已修] CRD-03 CR-11/CR-01 | `app/runtime.py:98` | 配置 operation timeout ≤0 被持久化成 deadline 耗尽 | 置信 72 | 改抛 `RuntimeControlError("INVALID_OPERATION_TIMEOUT")`，不计数、不发送、不写 exhaustion_reason；补 0/-1 与 API 测试。
- [已修] CRD-04 CR-04/CR-09 | `scripts/live_loopback_e2e.py:198` | 握手 deadline 只在阻塞 `readline` 之后判断，子进程卡住会永久挂起；stderr 管道未 drain | 置信 88 | 改读线程 + queue 超时、stderr daemon drain、失败 kill；补确定性测试。
- [已修] CRD-05 CR-09/CR-04 | `scripts/live_loopback_e2e.py:456` | `data/` 不存在时 `mkdtemp` 抛裸 `FileNotFoundError`，绕过 `E2E_FAILED` | 置信 92 | 先 `mkdir`，失败统一 `E2E_FAILED` + exit 1；新副本实测 E2E_OK。
- [已修] CRF2-01 文档计数 | 项目 README/TECH-STACK/LIVE-AMAP/ACCEPTANCE | 修复后实际 159，文档仍写 154 | 置信 95 | 已同步为 159（62 replay + 14 + 13 + 23 + 26 + 19 + 2 loopback）。
- [递延] CRD-01 CR-01/CR-02 | `app/live.py:359` | finalize 写在 finally 内，存储异常时 run 可能停留 `queued`，幂等重放只回 queued | 置信 90 | 归 T12 原子保存；入池 B3，不在本 change 临时改事务边界。

## 已裁掉

- X1 资源镜 5 条 dismissed：基类不可达的 owned_binding 分支、绑定态 `AmapClient.close()` 无仓内调用、失败 bind 不 close 属 adapter 语义、close 抛 BaseException 与 lifespan 未关 store 均超本 change 范围；主审同意不构成本 change 缺陷。
- X2 并发镜 5 条 dismissed：threadpool 40 容量已声明不承诺、cancel/finalize 串行化、bind/close/dispatch、探针与写事务、两次短读偏斜；主审同意均已在设计/文档声明或不可证伪。
- X3 领域镜 5 条 dismissed：未绑定 runtime 的脚本回退、test_live 预算口径重写非削弱、`_record` 不计预算、取消响应字段、残留 BUDGET_EXHAUSTED issue；主审同意。
- X4 错误路径镜 5 条 dismissed：探针异常、HTTPError 脱敏、provider.info、finalize 写库失败、取消确认快照；主审同意。

## 需人工复核

无（未出现无法接地的拒判项）。

## 修复 / defer 台账

自动修 6 项（SCOPE-DOC-01、CRD-02..05、CRF2-01）[impl-review-fix]；自动选推荐 0 项；本轮新增待处理 3 项（B1/B2 既有、B3 递延），均已由 recorder 确认 `source_change=travel-runtime-budget`。

| id | 池 | 摘要 | critique（裁决理由） |
|---|---|---|---|
| B1 | bug | 既有问题：provider 列表元素非 dict 时 AttributeError 逸出，未归 TOOL_FORMAT_ERROR | base 6a78560 已存在，不在本 change diff；入池不在本票扩修 |
| B2 | bug | 既有问题：adcode 查询失败统一报 provider_error，timeout 分类丢失 | 同上；poi_lookup 已保留 TOOL_TIMEOUT，本 change 未改该路径 |
| B3 | bug | LIVE finalize 失败时 run 可能停留 queued，需 T12 原子保存处理 | 修复需改事务边界，超出本 change；如实递延不在本票硬塞 |

## 既有问题

| id | 池 | 摘要 | 说明 |
|---|---|---|---|
| B1 | bug | 既有问题：provider 列表元素非 dict 时 AttributeError 逸出，未归 TOOL_FORMAT_ERROR | 所在行不在本 change 改动行内；错误路径镜以 TEMP 副本复现 |
| B2 | bug | 既有问题：adcode 查询失败统一报 provider_error，timeout 分类丢失 | 同上；本 change 脱敏只改文案，不改分类 |

## outside-voice

<!-- sdflow:hr-tg v1 hit="none" declared="" -->
<!-- sdflow:declared-sites v1 declared="code-voice" -->
<!-- sdflow:outside-voice v1 site="code-voice" guard="none" host="unknown" runner="none" reason_code="host-unknown" findings="0" truncated="false" -->

跨模型第二意见未运行：本会话的子代理被限制在父级路由，无法显式选择独立模型；同族子代理不构成跨模型 voice，故如实记 `host-unknown`，不以同族冒充。该缺口由领域镜 + 3 个对抗镜 + Step1 覆盖；不代表已获得跨模型复核。

## 结论

☑ 建议进 `/sdflow-done`（代码审通过；B1/B2 既有、B3 递延已入池；真实高德/生产并发/硬中断/灾备仍未验）。
