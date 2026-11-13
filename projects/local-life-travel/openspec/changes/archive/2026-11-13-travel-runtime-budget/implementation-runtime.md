# T11阶段三DSH运行适配提案

状态：用户已在t11_dsh_implementation_adapter选择“批准DSH适配并继续（推荐）”；本change的阶段三宿主/派发形式例外已批准，角色、测试及门禁继续保留。实际决定见review/implementation-runtime-decision.json。不是ticket、不是已执行实现；不改变业务范围、deadline、取消或合并边界，也不自动扩展为其他change的例外。

## 已验证的现状

- 设计门：真人在t11_design_gate选择“按推荐方案继续（推荐）”；权威anchor_writeback已写design_approved=true和3项监视工件的内容锚，本地提交d382fd2。
- ship_gate在项目OpenSpec根返回RUN_PLAN，原因tickets.md尚未创建。嵌套项目使用项目根参数，实际Git仓仍是原隔离worktree。
- required resolver已清空旧HOST/tier/effort/voice，检查脚本可执行、捕获退出码、eval及变量合法性；返回host=unknown。CLAUDECODE与CODEX_THREAD_ID均未设置，不能伪造其中任何一个。
- sdflow-implement第零步明确要求unknown硬停，连出票也没有单session降级路径。这一点不同于已完成的设计审unknown路径。此前设计门确认的是行为及设计审能力，没有明确豁免实现入口的硬停。
- DSH实际子代理接口已在冷审及两轮复核成功执行；可用路由为magpie-responses/codex/gpt-6.1-sol，请求high。没有第二模型路由、实际effort/费用未采集。
- 默认Windows Temp导致yq front-matter文件Access denied；将本次工具进程TEMP/TMP设为工作区tmp/sdflow-yq-temp后，同一批准报告解析成功且ship_gate返回RUN_PLAN。未改Windows文件权限、系统环境或全局工具源码；默认Temp内部机制未进一步确诊。

## 推荐：仅对本change用真实DSH接口适配

请求豁免的只有宿主识别导致的硬停、以及Claude/Codex原生派发参数形式；不假装HOST=codex，不使用unknown输出的空档位/缺省Claude模型。每个实际角色的provider/model/requested effort在派发前明确记录为已验证DSH路由，返回时核验run_id/task_id、文件及通则首行回执。

- 出票仍由主助手inline完成。默认采用已批准的三张功能切片，并按skill强制追加唯一聚合验证票；若分票与草图的关系需要仲裁，按T10-choice交fresh强档对抗角色复核，不自行删除门。
- 每个ticket由独立fresh implementer执行；其后分别派fresh Standards和Spec评审者。角色不合并为作者自审，不继承聊天，不让实现者自己派重复评审。需要修复时由主助手派fix和复审角色，保持原熔断/台账规则。
- 串行执行，保持当前隔离worktree；没有并行写共享文件的假隔离。各角色只能读/写自己获分配的范围。
- 红→绿、系统边界MockTransport/假clock、隔离SQLite、每票测试/说明、引用机械核、完成标签与复选框双信号、聚合回归均照原管线。没有运行的测试或角色不记通过。
- 每步前后仍用权威ship_gate；完成信号/内容锚仍由原helper处理。不改gate、不手工制造native能力锚、不降需求或冒充跨模型。
- 阶段三后续冷代码审/verify同样通过真实DSH角色承载原要求的工作；原native outside-voice在无第二路由时如实标不可执行。用户已批准的单模型风险边界保留，不伪造多模型结果。
- 完成验证后提交本次PR，skip merge。GitHub CLI现有认证失效，提交阶段再处理有效认证；不提前索取token或发布私人规划内容。

## 代价与备选

系统镜：保留规格/角色/门禁，只替换本次派发传输；增加一份每change适配审计，需明确区分native和DSH事实。用户镜：可以在当前会话推进，不必迁移工作区；仍无硬90秒、跨模型或真实供应商保证。开发循环镜：保持每票三类角色与必要修复，调用次数不会因为只用一个模型而消失；真实用量未采集。主次：先维护审查与证据契约，适配当前可用的实际运行工具。

备选：在真正的Claude Code或Codex CLI中从此worktree接续原生管线，保持完全原样的宿主判定；代价是用户需要切换会话/运行入口。不能通过手设CLAUDECODE/CODEX_THREAD_ID把DSH冒充原生宿主。
