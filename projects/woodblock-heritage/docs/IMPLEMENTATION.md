# 实现说明（本地审核切片）

## 1. 模块

| 模块 | 职责 | 不做什么 |
|---|---|---|
| `app/models.py` | Pydantic 请求契约、冻结谓词、字段长度 | 不写数据库 |
| `app/images.py` | base64 严格解码、PNG/JPEG `verify` + 重新 `load`、8MiB/20MP 限额 | 不做 OCR/VLM |
| `app/store.py` | SQLite/WAL/`BEGIN IMMEDIATE`、表结构、幂等读写 | 不写业务判断 |
| `app/service.py` | 三状态轴、结构校验、审核裁决、发布门禁、快照 | 不做 HTTP |
| `app/main.py` | FastAPI 路由、统一错误、CSP、Origin 检查 | 不写业务规则 |
| `web/` | 同源页面（外部 JS/CSS、canvas 区域覆盖） | 不内联脚本 |

## 2. 请求生命周期

1. `POST /sources`：解码图片 → 计算 SHA256 → 查同哈希来源；元数据一致返回 200，不一致 409；否则存 BLOB + 元数据 201。
2. `POST /works`（幂等键）：校验 schema/来源 → 区域坐标换算（像素按实际宽高归一化）→ 断言重置为 `insufficient/unreviewed` 并重算结构 → 未知谓词/缺证据保留为 invalid + blocking issue → 保存不可变 v1（含 `raw_import`）201。
3. `POST /works/{id}/reviews`（幂等键）：先查幂等键 → 校验 `expected_version` → 逐条 approve/reject/revise → 问题处置 → 原子写事件、v+1、当前版本。
4. `POST /publications`（幂等键）：校验当前版本 → 门禁 → 已有同版本快照复用 → 否则写不可变快照。
5. `GET /knowledge`：只取 `publication.version == works.current_version` 的快照。

## 3. 三个状态轴

- `validation_status`：谓词是否在冻结集合、证据引用是否存在、值是否非空；结构问题产生 blocking issue。
- `support_status`：导入强制 `insufficient`；只有人工 approve 且明确 `supported` 才变 supported。
- `review_status`：导入强制 `unreviewed`；approve/reject 改变；revise 回到 unreviewed。

发布只收 `approved + supported + valid + 值非空 + 证据非空` 的断言。

## 4. 事务与幂等

- 每个写操作 `BEGIN IMMEDIATE`；`PRAGMA journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`。
- 幂等表主键 `(scope,key)`，保存规范 JSON 的 SHA256 与原响应；同键同载荷返回原响应，同键异载荷 409。
- 审核在同一个事务里完成：幂等检查、版本检查、事件、新版本、当前版本指针、幂等响应。并发同版本只有一个能提交。
- 发布在同一个事务里完成：门禁、快照唯一性、幂等响应。
- 取消/后台 worker 不在本切片；没有可撤销的外部调用。

## 5. 表

| 表 | 关键列/约束 |
|---|---|
| `sources` | `id` PK、`content_hash` UNIQUE、`media_type`、`width/height`、`content` BLOB、`metadata_json` |
| `works` | `id` PK、`current_version` |
| `work_versions` | `(work_id,version)` PK、`payload_json`（不可变） |
| `review_events` | `id` PK、`(work_id,to_version)` UNIQUE、`reviewer/reason/payload_json` |
| `publications` | `id` PK、`(work_id,version)` UNIQUE、`payload_json`、FK 到版本 |
| `idempotency` | `(scope,key)` PK、`request_hash`、`response_json` |
| `meta` | `schema_version=1` |

## 6. 发布门禁

1. 期望版本 == 当前版本；
2. 所有断言已裁决（无 unreviewed）；
3. 所有仍 blocking 的 open issue 已解决；若 issue 关联的断言已被 reject，则该结构问题不再阻断其他合格知识；
4. 至少一条合格 approved+supported+valid 断言。

不满足返回 409 `PUBLICATION_BLOCKED`，附 `unreviewed_claim_ids` 与 `blocking_issue_ids`，不生成空快照。

## 7. 安全与限制

- CSP：`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`；页面无内联脚本/样式。
- 写请求若带非本地 Origin 返回 403；不提供 CORS。服务默认只绑定 `127.0.0.1`。
- 文件名只作显示，不拼路径；来源图片只按服务生成的 ID 取；不接收外部 URL。
- 审核者标签是自述，不是认证；不能部署公网多用户。
- 当前没有后台 worker、真实抽取、Neo4j；这些不因本切片通过而完成。

## 8. 已知缺口

- 页面已用 Chrome CDP 跑过选候选/批准/发布；文件上传、canvas、冲突重载仍未覆盖，Playwright 临时目录 EPERM 未解决。
- `get_work` 读路径也开了 `BEGIN IMMEDIATE`，串行化偏重；数据量上来应改为只读连接/快照读。
- `work:create` 幂等作用域是全局；同一键跨不同作品会重放旧作品（这是幂等语义，但调用方需按作品维度生成键）。
- 没有来源元数据修订/删除流程；没有自由实体关系；没有分页。
