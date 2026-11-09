# LIVE运行控制实现任务

状态：全部待实施。前置：独立设计评审和真人设计门；本文件存在/CLI valid不授权跳过门禁。实施票由sdflow-ship按既有ticket管线生成，下面是3张垂直切片建议而非已经出票或执行。当前只完成规格与旧行为复现。

## 1. HTTP准入、真实计数与正常资源闭环

Blocked-by：设计门。建议ticket 1，先交付真实适配器经API创建/限额失败的完整链路。

- [ ] 1.1 [LRC-01,LRC-04] 新增每run控制器和发送前预占，移除工具后max(1,差额)记账；验证limit=0/1/2/40及恰好用完，真实MockTransport第N+1次handler命中0，保存数与准入数一致。
- [ ] 1.2 [LRC-01,LRC-04] 把POI、adcode/weather、hours、matrix所有HTTP纳入同一准入；验证各内部批次中途耗尽、网络失败尝试仍计数、本地缓存工具计0，保存已有证据但无不完整可行结果。
- [ ] 1.3 [LRC-06,LRC-07] 加入adapter运行绑定/正常close、client active绑定互斥与身份匹配解绑，默认factory显式拥有client；更新FakeAdapter/CountingAdapter为逐次准入；验证缺协议工具调用0、并发绑定至多一赢、失败绑定清理不影响原run、借入client不被误关。
- [ ] 1.4 [LRC-05,LRC-07] 用真实AmapAdapter+MockTransport经TestClient覆盖正常和额度耗尽的创建/重放；验证同键run_id相同、新factory/HTTP/完成事件0、耗尽后关闭尝试1且数据库可读，不只验证status。
- [ ] 1.5 [LRC-09] 同票更新LIVE-AMAP的发送尝试/默认40/内部绑定协议说明及复现前后数据；验证文中命令在隔离库能执行，并明确脚本独立调用不自动拥有run预算、真实供应商未验。

## 2. Deadline、取消与终态持久一致性

Blocked-by：ticket 1。建议ticket 2；不引入worker或硬中断平台。

- [ ] 2.1 [LRC-02,LRC-04] 在factory之前建立单调开始值并注入可控clock；发送前、返回后、阶段间和终态检查deadline，传入min(操作配置,剩余时间)的四类timeout；验证90秒边界、0秒、不放大0.25秒配置、UTC跳变不影响，使用假时钟而非真实sleep。
- [ ] 2.2 [LRC-02,LRC-04] 对迟到响应、评估和收尾分类耗尽并保留准确计数/elapsed/已有证据；验证不接受completed/needs_input/verified晚结果，普通工具timeout且总deadline未到时仍保持原工具错误语义。
- [ ] 2.3 [LRC-03,LRC-06] 用短持久状态探针观察取消/缺失/读取异常，HTTP不持DB事务；验证另一连接在两次发送间取消后下一handler不命中，探针失败不绕过控制，in-flight竞争局限如实记录。
- [ ] 2.4 [LRC-03,LRC-04,LRC-05] 保存后以canonical run返回并处理被SQL取消保护截获的晚结果；验证最后检查与保存之间的取消竞争仍返回cancelled及非verified未完成结果，同键重放保留旧消耗而不重执行。
- [ ] 2.5 [LRC-02,LRC-03,LRC-09] 同票更新LIVE时限/取消契约与JSON示例；验证默认90/操作5、单调elapsed、exhaustion_reason、检查后竞争与不能强制90秒返回均有明确说明，清理超过时间不被隐瞒。

## 3. 异常资源收尾与跨切片验收

Blocked-by：ticket 1、ticket 2。建议ticket 3，已有功能的必要异常路径补齐，不把前票本应拥有的测试推迟到这里。

- [ ] 3.1 [LRC-07] 完成拥有权转移后的构造验证失败/factory部分失败处理与close幂等；验证成功/provider_error/budget/deadline/cancel/constructor_failure共6类已取得自有资源路径有清理尝试，借用为0次关闭且解绑后可顺序复用。
- [ ] 3.2 [LRC-07,LRC-08] 注入解绑与关闭异常，独立尝试其余清理，记录固定类别/异常类型警告；验证第7类cleanup_failure仍保存原主失败/准确预算及警告，不声称释放成功、不因finally异常跳过save，不泄漏测试凭据/带query URL。
- [ ] 3.3 [LRC-01,LRC-02,LRC-03,LRC-04,LRC-05,LRC-06,LRC-07,LRC-08,LRC-09] 运行跨切片完整pytest回归并记录真实命令/exit/count；验证原replay、Amap离线和LIVE业务案例无未说明回退，不预写“原88+新增=N通过”。
- [ ] 3.4 [LRC-01,LRC-04,LRC-05,LRC-07,LRC-08,LRC-09] 新增隔离进程loopback HTTP烟测，应用注入真实适配器+MockTransport合成供应商；验证POST/GET/同键重放的run/计数/清理事件与SQLite一致，脚本只访问本地、结束时停止自己创建的服务，不能因默认环境有Key而访问真实渠道。
- [ ] 3.5 [LRC-09] 同票完成README/LIVE-AMAP/API契约与验收记录的最终互链，标明分支与main；验证规格9条需求全部有运行证据或明确未满足项，独立代码审查前不记T11完成，未合并时不改私人面试稿的main现状数字。

## Requirement Traceability

| Requirement | 实现/验证任务 |
|---|---|
| LRC-01 | 1.1、1.2、3.3、3.4 |
| LRC-02 | 2.1、2.2、2.5、3.3 |
| LRC-03 | 2.3、2.4、2.5、3.3 |
| LRC-04 | 1.1、1.2、2.1、2.2、2.4、3.3、3.4 |
| LRC-05 | 1.4、2.4、3.3、3.4 |
| LRC-06 | 1.3、2.3、3.3 |
| LRC-07 | 1.3、1.4、3.1、3.2、3.3、3.4 |
| LRC-08 | 3.2、3.3、3.4 |
| LRC-09 | 1.5、2.5、3.3、3.4、3.5 |

## Test Coverage Map

以下新文件为计划，不是现有已通过测试。

| 代码路径/风险 | 单元 | 集成 | E2E/流程 |
|---|---|---|---|
| runtime准入/时钟/次数边界 | 新tests/test_live_runtime.py：假clock、预占、零额度/恰好额度 | 新tests/test_live_runtime_integration.py：AmapAdapter+MockTransport+Store | loopback POST耗尽，GET重读计数 |
| adcode/weather/hours/matrix内部循环 | client reserve spy | MockTransport handler路径/次数与保存预算对账 | 同合成应用一次API链路 |
| 取消/晚到/保存竞争 | 探针与终态分类 | 独立Store连接/确定性barrier、保存前注入取消 | loopback保存后GET不复活；不声称全浏览器 |
| 幂等重放/修订 | 既有规范hash规则 | 扩展tests/test_live.py，factory/HTTP/event增量0 | 真实HTTP同键两次同run |
| bind/owns/close/constructor/cleanup失败 | 绑定竞争/所有权/close计数 | 真适配器+MockTransport、故障注入后重开Store读结果 | HTTP失败响应可读且服务/临时资源结束 |
| 原功能不回退 | tests/test_domain.py等既有测试 | tests/test_amap_tools.py与tests/test_live.py | 不重做与此次后端契约无关的浏览器全交互 |

```text
ticket1: HTTP准入+正常close+API离线闭环
      |
      v
ticket2: deadline/取消/终态
      |                       ticket1也为ticket3前置
      v
ticket3: 异常清理+全回归+loopback验收
```

计划命令沿用项目Python与pytest：`python -m pytest -q -p no:cacheprovider`；局部选择实际新测试文件后执行。loopback命令在3.4实现脚本后填入真实入口，不先捏造可运行脚本名。日志记录环境、提交、命令、退出码及真实计数，不记录凭据；每票测试与说明随该票落地。

## Workflow follow-up

- 按sdflow-spec-review完成独立设计审查和真人设计门，再由sdflow-ship出票/实现；未过门不走裸实现。
- 实现后执行sdflow-code-review并处置发现，完成证据核验再考虑归档；保持未满足需求可见。
- 新PR推送/合并按用户明确授权执行；本次没有未来PR的无限合并授权，不能把本地checkpoint当发布。
- 只有实际合并版本变更后同步统一任务和私人面试文档；原始大数据/私人planning不随公开代码发布。
