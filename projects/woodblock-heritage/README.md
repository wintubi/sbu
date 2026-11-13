# 木版年画证据审核 · 本地切片

状态：**可运行后端 + 同源审核页面**；47 项 pytest 通过，真实 HTTP 合成链路跑通，真实 Chrome CDP 已完成完整页面流程（上传→导入→409冲突重载→修订→处置→发布→历史只读），并验证 canvas 命中、恶意文本不执行、双标签页并发冲突。**本仓库是脱敏公开子集：不含原始扫描页、历史数据、本地数据库或密钥。** 没有真实 OCR/VLM/Neo4j 调用；canvas 拖拽/缩放未覆盖。边界见 [PUBLIC-SUBSET.md](PUBLIC-SUBSET.md)。

## 这是什么

在历史年画工程（本体、词表、抽取、自动校验）之上，补一条可审计的“候选 → 人工裁决 → 版本 → 本地发布”链路：

```text
来源登记（PNG/JPEG、哈希去重、实际解码）
  → 候选导入（Region/Claim/Issue，坐标归一化，结构校验）
  → 人工审核（approve/reject/revise，expected_version）
  → 发布门禁（当前版本、全部裁决、阻断问题解决、至少一条合格断言）
  → 不可变本地快照 → 当前知识 / 历史快照
```

三个状态轴分开：`validation_status`（结构）、`support_status`（来源支持）、`review_status`（人工结论）。**有引用不等于支持，结构通过不等于人批准。**

## 快速开始

```powershell
cd woodblock-heritage
python -m pip install -r requirements-dev.txt
python run.py
# 打开 http://127.0.0.1:8770
```

`access_policy` 只允许 `synthetic-only` / `local-unverified-no-publication` / `cleared-for-publication`；未知策略在登记时 422，`local-*` 即使断言全批准也禁止发布。

页面步骤：选一张合成 PNG（或自己生成）→ 登记来源 → “用当前来源生成示例候选” → 导入 → 逐条批准/驳回 → 填写理由 → 发布 → 查看当前知识。默认数据库 `data/heritage.sqlite3`，可用 `HERITAGE_DB` 覆盖；服务只绑定 `127.0.0.1`。

无页面演示也可用 API；`scripts/demo_e2e.py` 是真实 HTTP 冒烟脚本。

## 公开子集边界（不含原始数据）

本公开子集只保留合成演示、架构/规格、测试和可复用流程代码；**不包含**历史扫描页、原始候选、审核工作表、本地 SQLite 或任何密钥。真实历史页的导入/核对在私有工作区进行，不随仓库发布。

如果要评测，金标准格式与结构校验见 [GOLD-SCHEMA](docs/GOLD-SCHEMA.md) 和 `scripts/validate_gold.py`。当前**没有真实金标准**，不能报领域准确率或 P/R/F1。

## 真实浏览器

`scripts/ui_full_e2e_cdp.py` 用本机 Chrome 的 DevTools Protocol（不是 Playwright）完成完整页面流程：真实文件上传 → 生成/导入候选 → 两条断言批准 v2 → 另一客户端推进 v3 → 页面旧提交 409 后重载 v3 → 修订 → 批准 v5 → 处置问题 v6 → 发布 → 当前知识。截图见[完整界面证据](docs/evidence/ui-full-e2e.png)，输出见[CDP 记录](docs/evidence/chrome-cdp-full.txt)。

## 测试

```powershell
python -m pytest
# 47 passed
```

覆盖：来源去重/元数据冲突、坏 base64/截断图片、坐标归一化、非法断言保留、重复 ID、客户端伪造批准被重置、审核幂等/版本冲突/并发只赢一个、结构问题不能靠理由关闭、发布门禁、驳回坏断言不阻断好断言、当前/历史快照、重启恢复、CSP/无内联脚本。

真实 HTTP（先启动服务）：

```powershell
python scripts/demo_e2e.py http://127.0.0.1:8770
# publication=... version=2 claims=2
# knowledge_count=1 title=合成门神示例
```

## API

| 方法/路径 | 作用 |
|---|---|
| `POST /api/v1/heritage/sources` | 登记来源（base64 PNG/JPEG） |
| `GET /api/v1/heritage/sources/{id}` / `/image` | 来源元数据 / 同源原图 |
| `POST /api/v1/heritage/works` | 导入候选（`Idempotency-Key`） |
| `GET /api/v1/heritage/works` / `/{id}?version=` | 列表 / 当前或历史版本 |
| `GET /api/v1/heritage/works/{id}/publications` | 该作品的发布历史快照 |
| `POST /api/v1/heritage/works/{id}/reviews` | 审核（`Idempotency-Key`、`expected_version`） |
| `POST /api/v1/heritage/publications` | 发布当前审核版本 |
| `GET /api/v1/heritage/publications/{id}` | 历史快照 |
| `GET /api/v1/heritage/knowledge` | 当前知识（只含发布版本==当前版本） |
| `GET /health/live` / `/health/ready` | 存活 / 就绪 |

## 目录

- `docs/TECH-STACK.md`：技术栈总结（组件/技术/作用/状态）、现状与目标态、选型理由与代价。
- `docs/ARCHITECTURE.md`：整体架构：分层、审核事务、发布门禁、目标态受控动态 DAG。
- `app/models.py`：请求契约与冻结谓词；`app/images.py`：Pillow 完整解码与限额。
- `app/service.py`：三状态轴、审核裁决、发布门禁；`app/store.py`：SQLite/WAL/事务/幂等。
- `app/main.py`：FastAPI 边界、CSP、Origin 检查。
- `web/`：同源页面（无内联脚本/样式，CSP 允许外部 JS/CSS）。
- `tests/`：47 项离线测试；`scripts/demo_e2e.py`：真实 HTTP 冒烟。

## 明确没做

- 真实 OCR/VLM 抽取、Neo4j 发布、公网认证与多用户；真实原件只在本地审核且许可未核，未发布。
- Playwright E2E 仍未跑（临时目录 EPERM）；Chrome CDP 已覆盖上传/导入/409冲突重载/修订/处置/发布/历史只读、canvas 命中、恶意文本不执行、双标签页冲突；未覆盖 canvas 拖拽/缩放、触摸手势。
- 自由实体关系/自动本体演化、全量 11 卷、领域准确率或 92% 命中率复验。

历史工程的本体/词表/抽取/校验在本地私有工作区另行保存；本公开子集不重写它们，也不包含其原始数据。论文的 23/19、Cypher 92% 与当前代码 27/31、远端 15/19 是不同版本，不能混用。
