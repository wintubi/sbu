### Task 2: 单调deadline、可达的API取消与原子终态

**Blocked-by:** 1
**R-ID:** LRC-02, LRC-03, LRC-04, LRC-05, LRC-06, LRC-09

从创建前到最终保存建立运行级时间/取消边界；原创建与修订POST仍等待终态，但同进程可并发重放取标识并取消。取消确认和最终快照分别短事务一致归一，不引入worker、提前202平台或SQL列迁移。对应原任务2.1–2.5。

- [ ] 幂等命中不建立runtime；新run在factory前取单调开始时间；发送前后、阶段间、评估前后、终态接受和收尾检查；假clock验证0/90边界、UTC跳变、剩余1秒及更短0.25秒配置，四操作timeout不大于配置与剩余时间较小值，不用真实sleep等90秒。
- [ ] 响应、评估或收尾迟到且无更早主失败时保存deadline耗尽与实际elapsed，不接受completed/needs_input/verified晚结果；普通操作timeout但总deadline未到仍保持原工具分类；已有主失败不被后续清理或时间检查覆盖。
- [ ] 取消/缺失/读取异常探针不得放行新发送，短探针不包HTTP；创建与LIVE修订的同步核心在线程执行，同一应用同一事件循环在等待期间可并发API同键重放拿到run_id，再调用原cancel入口，原等待请求最终返回已提交取消态。
- [ ] API并发集成覆盖创建和修订、原键/原载荷、重放factory/HTTP增量0及下一handler不命中；LIVE取消响应/事件标正确mode与尽力停止提示，不含replay或无远端调用声明，承认in-flight检查后竞争。
- [ ] 取消确认与最终保存各自一次短事务重新判定并归一status=cancelled、budget.status=cancelled、quality_status=unverified、result=null、删除耗尽原因；保存实际次数/elapsed/证据与原诊断。barrier竞争中的GET/重放不可看到混合终态，不先提交后修补；已提交主失败先于取消则terminal拒绝。
- [ ] 时间/取消说明与JSON示例随票更新，明确默认90/操作5、单调elapsed、新耗尽必填原因/历史可缺、不能强制90秒返回、清理可超时；新增诊断只含固定类别/安全类型，不拷原始异常字符串。
- [ ] [Review Focus] 最后一次check之后、最终保存之前取消提交胜出；竞争中的独立连接GET与同键重放须始终读到归一快照，不能只检查最终一次GET。

