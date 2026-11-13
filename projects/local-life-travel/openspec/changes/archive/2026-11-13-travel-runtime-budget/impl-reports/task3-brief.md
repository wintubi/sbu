### Task 3: 异常收尾、脱敏与真实loopback验收

**Blocked-by:** 1,2
**R-ID:** LRC-01, LRC-02, LRC-03, LRC-04, LRC-05, LRC-06, LRC-07, LRC-08, LRC-09

补齐已取得资源的异常出口，确保主结果与安全诊断可读，并通过独立进程的真实本地HTTP组合验证前两票。对应原任务3.1/3.2/3.4/3.5；原3.3完整聚合回归由唯一票4承担，不能把本票自身失败覆盖推迟到票4。

- [ ] 自有资源成功/provider_error/call_limit/deadline/cancel/constructor_failure各有一次清理尝试；factory返回前未交资源由factory负责，借用关闭0且解绑后顺序复用；构造校验失败与close幂等有可观察断言。
- [ ] 解绑失败仍独立尝试其余清理/物理close；cleanup_failure保存原主类别/准确预算/证据及固定RESOURCE_CLEANUP_FAILED警告，不因finally跳过保存，不宣称释放成功；无更早主失败时清理后仍不能接受过期结果。
- [ ] 普通HTTPError、provider文本、顶层执行错误、取消探针与cleanup错误注入合成Key/query/私人标记；API、持久state和事件不含标记/带query URL/raw str(exc)，仅固定类别/安全异常类型或验证后的数字供应商码；原错误状态分类保持正确。
- [ ] [e2e] 独立隔离应用进程注入真实适配器与MockTransport合成供应商，经真实loopback HTTP对创建和LIVE修订并发POST/同键重放/cancel/GET；不能旁路写DB代替取消，核对运行/计数/清理动作/事件与SQLite一致；无论环境是否有Key都不得访问真实供应商，结束只停止自己启动的服务并保留可复现命令/退出码。
- [ ] LIVE文档、API约定和验收记录最终互链，逐条列9条需求的证据/未满足项，明确分支不等于main、未独立代码审不标T11完成，不更新私人讲义的main现状数字；记录实际命令/计数而非预写原88+新增总数。
- [ ] [Review Focus] close异常包含敏感文本且总deadline在清理期间到达：保留更早主失败、仅安全警告、持久化仍尝试，不把close一次尝试写成资源已释放。

