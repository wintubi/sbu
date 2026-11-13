### Task 1: HTTP发送前准入、真实计数与正常资源闭环

**Blocked-by:** none
**R-ID:** LRC-01, LRC-04, LRC-05, LRC-06, LRC-07, LRC-09

交付真实适配器通过API创建、查询、耗尽和幂等重放的离线闭环。本票落实HTTP准入、次数耗尽、协议和正常拥有权；deadline/实际API取消在票2交付，异常资源矩阵与最终材料在票3完成，不把本票通过当全部需求完成。对应原实现任务1.1–1.5。

- [ ] 每run独立控制，POI、adcode/weather、营业详情和路线内部循环逐HTTP发送前预占；limit=0/1/2/40及恰好用完均在真实MockTransport发送点验证，第N+1次不命中handler；连接、timeout、provider或格式错误的已准入尝试计数，本地缓存/解析/空矩阵计0，移除事后max(1,差额)替代记账。
- [ ] 批次中断仍保存此前已规范化的成功leg/营业详情及来源、时间和最小payload；计数与准入对账，部分批次不成为完整成功，不返回未完成可行方案；call_limit耗尽保存failed/exhausted、必填原因、空result与unverified。
- [ ] 所有LIVE工具调用前必须有显式绑定/清理协议；缺协议或绑定失败时工具发送0；每client短锁保护active身份及open/closing/closed，借入只按身份解绑且可顺序复用，自有close先标closing再锁外关闭；重复清理物理close最多一次，关闭失败也不允许重新绑定。
- [ ] 默认factory显式拥有独立client，内部fake显式逐HTTP准入；测试并发bind至多一赢、失败绑定清理不改变原run、借入close次数0、自有close过程中新bind失败，不靠GIL或真实sleep建立竞争顺序。
- [ ] 真实AmapAdapter与MockTransport经API集成覆盖正常/额度耗尽/同键重放；重放同run且新增factory/HTTP/完成事件为0，正常与耗尽已取得自有资源均关闭尝试一次，数据库重读可核对证据和实际计数；保留同键改载荷409与默认缺Key503。
- [ ] 同票说明默认40、HTTP尝试非计费、绑定协议变更、独立脚本不自动拥有run预算以及真实供应商未验；给出隔离库复现前后观察，不提前宣称deadline/取消已交付。
- [ ] [Review Focus] 第二个adapter绑定同一active client失败后，其cleanup不得解绑或关闭第一个run的client；原run仍能执行且预算独立。

