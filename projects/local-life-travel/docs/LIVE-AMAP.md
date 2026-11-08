# 高德真实数据适配器（LIVE / 未联调）

状态：适配器、`POST /api/v1/travel/live-runs` 路径与离线/假适配器测试已完成；**没有用真实 Key 成功调用过**，因此不能声称真实数据/真实行程验收通过。默认运行仍是 replay。

## 1. 为什么先做适配器而不是直接接页面

现有 `ReplayAdapter` 已经把 POI/天气/营业/路线统一成 `ToolResult(status, source_ref, payload, error_code)`。真实供应商的风险不在“能不能发 HTTP”，而在：空结果、限流、超时、字段缺失、日期不覆盖、营业时间没有返回。先把这些映射做实，再用一个 Key 做小样本探测，才能避免把供应商错误伪装成成功行程。

## 2. Key 的现状（实测证据）

- 原 chapter13 前端 `Result.vue` 里有一个历史硬编码 Key（注释写“Web 服务 API Key”）。
- 2026-11-08 用该 Key 调用高德 Web 服务 `geocode/geo` 与 `place/text`，两次均返回 HTTP 200、`status=0`、`info=USER_KEY_RECYCLED`、`infocode=10013`。
- 结论：该 Key 已被回收，不能继续使用。代码里不应保留硬编码 Key；新 Key 只放环境变量。
- 仓库内的 `backend/.env.example`、`frontend/.env.example` 只有占位符，没有可用 Key。

## 3. 官方申请流程（已核对高德官方“创建应用和 Key”页）

1. 打开高德开放平台控制台，登录或注册开发者账号：<https://console.amap.com/>。
2. 进入【应用管理】→【创建新应用】，填写应用名称与类型。
3. 在应用下【添加 Key】，服务平台选择【Web 服务】。
4. 创建成功后复制 Key，配置到本机环境变量 `AMAP_API_KEY`（不要提交到 Git）。

账号注册/实名要求以控制台实际页面为准。个人开发者通常需要手机号验证，部分能力还涉及实名认证；我没有代替你完成手机短信、实名或验证码，也不会伪造身份。若注册页面要求邮箱验证码，可以使用你已有的邮箱；自动注册新邮箱并不是可靠路径（主流邮箱同样要手机号/人机验证，且代注册涉及服务条款与账号归属问题）。

## 4. 使用

```powershell
$env:AMAP_API_KEY = "<你的 Web 服务 Key>"
python scripts/amap_probe.py --city 北京
```

探测只做少量真实请求：3 次 POI 搜索、1 次天气、两两 POI 之间的路线（3 个点最多 3 条）。脚本只打印状态、匹配结果、质量状态和 issue code，不打印 Key。若 Key 无效/被回收，会输出 `provider_error`/`10013`，不会继续生成行程。

预期输出示例（真实成功时）：

```text
poi 故宫博物院: status=valid match=matched
weather 2026-11-09: status=valid
hours: status=valid windows=1
leg 故宫博物院 -> 景山公园: status=valid
quality_status=verified_feasible
issue_codes=
```

若天气日期不在预报窗口、营业时间缺失、路线超时，会分别出现 `WEATHER_DATE_NOT_COVERED`、`HOURS_UNKNOWN`、`TOOL_TIMEOUT` 等 issue，质量会降为 `partially_verified`，而不是硬说可行。

## 5. 适配器边界

| 能力 | 实现 | 限制 |
|---|---|---|
| POI 搜索 | `/v3/place/text`，`citylimit=true` | 同名多结果返回 ambiguous，不静默选第一个 |
| POI 详情 | `/v3/place/detail` | 用户选定候选后使用 |
| 天气 | `/v3/weather/weatherInfo`，按日期匹配 | 高德没有“按日期查询”的参数；目标日不在预报窗口就标 unavailable，不用当前天气代替 |
| 营业时间 | POI `biz_ext.open_time` | 很多 POI 不返回；缺失就保持 unknown，不编造 |
| 路线 | 步行 `/v3/direction/walking`、驾车 `/v3/direction/driving` | 公交/骑行未接入，返回 unsupported；每条腿一次请求，受预算限制 |
| 路线矩阵 | `matrix(pairs)` 显式传腿 | 不使用 `leg_key` 的对称假设做真实双向路线；当前矩阵按无向 key 存，真实单向道路是已知局限 |
| 错误 | 超时/HTTP/JSON/业务错误 | 分别映射 timeout/provider_error/format_error，不吞成空成功 |

## 6. Live API

`POST /api/v1/travel/live-runs` 接收与 replay 相同的城市/日期/时间窗/3–6 候选，但走 `app.live`：同步调用适配器、规范化 ToolResult、用同一 `evaluate_timeline` 判定质量并落库。测试用可注入假适配器覆盖：成功、歧义 needs_input、供应商错误 failed、跨城 blocker、无 Key 503、幂等重放与冲突；歧义运行可通过 `POST /api/v1/travel/runs/{run_id}/revisions` 选点生成新的 live run，旧运行保留。真实 Key 未提供，所以这条路径仍是“代码可运行、真实未联调”。live 预算按 `AmapClient` 的真实 HTTP 调用计数（含 matrix 逐腿、hours 逐 POI detail），默认上限 40 次；超限置 `failed`/`budget.status=exhausted` 并记 `BUDGET_EXHAUSTED`。

## 7. 测试

```powershell
$env:TRAVEL_REPLAY_NO_AUTOSTART='1'
python -m pytest -q tests/test_amap_tools.py
# 14 passed
python -m pytest -q
# 88 passed（回放 61 + 高德离线 14 + live API 13）
```

离线测试用 `httpx.MockTransport`，覆盖：唯一匹配、同名歧义、空结果、Key 回收、超时、坏坐标、天气日期覆盖/不覆盖、路线时长距离、营业时间有/无。**没有真实网络请求**。

## 8. 下一步

1. 你完成高德账号注册并创建 Web 服务 Key（手机/实名校验由你本人完成）。
2. 设置 `AMAP_API_KEY`，运行 `scripts/amap_probe.py`。
3. 把探测结果（成功/错误码/质量状态）写入验收记录；`POST /api/v1/travel/live-runs` 已实现，设置 Key 后可直接调用。4. 无 Key 时端点返回 503 `LIVE_NOT_CONFIGURED`，不会创建假成功运行。
4. 在控制台核对配额与 QPS；不要用循环压测。
