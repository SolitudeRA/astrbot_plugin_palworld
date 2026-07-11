# Plugin Pages 设置与状态页 — 设计规格

日期：2026-07-12
状态：已对抗式复核（正确性/安全/平台兼容三视角），本版为修订版
关联：`docs/superpowers/specs/2026-07-10-palchronicle-v0.1.md`（主规格）、
`docs/superpowers/specs/2026-07-11-custom-headers-design.md`

## 0. 背景与决策记录

AstrBot v4.24.1（PR #5940）引入 Plugin Pages：插件在根目录 `pages/<page>/index.html`
声明页面，Dashboard 以受限 iframe 加载；v4.25.3（PR #8569）起启用了页面的插件
自动出现在侧栏「插件页面」可折叠分组。页面脚本经自动注入的
`window.AstrBotPluginPage` bridge 调用插件后端（`context.register_web_api` 注册的
端点），bridge 由父页面代持 Dashboard 登录态。

已确认决策（与用户逐项敲定）：

1. **范围**：设置编辑 + 只读状态面板，单页面两个 tab
2. **版本策略**：能力按版本降级（详见 §2.1）——`metadata.yaml` 保持
   `>=4.10.4`；后端用 Quart 兼容风格（`from quart import request, jsonify`，
   4.24.1–4.26+ 全区间可用），不用 v4.26.0 的 `astrbot.api.web` 新 API
3. **保存生效**：插件自重启容器（`save_config()` 只落盘、不触发 AstrBot
   热重载，故插件自己 stop→parse→start）
4. **前端**：原生 JS（ES Modules），零依赖零构建，完全自包含

### 0.1 平台事实（复核已核实，实现须据此）

- `register_web_api(route, view_handler, methods, desc)` 签名正确；路由必须以
  插件名前缀，本插件 `metadata.yaml` 的 `name` 为 `astrbot_plugin_palword`，
  与路由前缀一致
- **错误通道**：bridge 对非 2xx 只把一个字符串传回页面、丢弃状态码与响应体。
  故本设计所有**预期内**结果（成功与业务失败）一律 **HTTP 200**，用响应体
  `ok` 字段区分；非 2xx 只留给未预期异常。响应体顶层键不得用 `status` 或
  `data`（平台保留：`status:"error"` 判失败、`data` 会被解包）
- **鉴权为真**：`/plugins/extensions/*`（v4.26+）/ `/api/plug/*`（4.24–4.25）
  均过 Dashboard JWT 中间件，缺失/无效 401。但本设计不把单一假设当唯一防线
  （见 §5）
- **bridge 上下文**：`isDark`/`locale` 仅 ≥4.25.3 提供；SDK 自身会据 `isDark`
  维护 `<html data-theme>`，页面 CSS 直接吃该属性即可，JS 不重复设置
- **路由不随 terminate 注销**（Context 类属性、替换语义）：自重启容器方案不
  重新注册故无重复风险；但插件禁用后端点仍可达，handler 必须在容器为 None
  时安全返回

## 1. 文件布局

```
pages/settings/
  index.html        # 页面骨架；tab 结构；<script type="module" src="./app.js">
  app.js            # 入口：bridge.ready() → tab 路由 → 挂载两模块
  settings.js       # 设置表单：渲染/收集/提交
  status.js         # 状态面板：拉取/渲染/手动刷新
  style.css         # [data-theme="dark"] 选择器适配暗色（吃 SDK 行为）
palchronicle/presentation/web_api.py   # 全部 HTTP handler 编排（新模块）
palchronicle/presentation/config_view.py  # 脱敏读 / 校验 / 哨兵回填 纯函数（新模块）
main.py             # 注册路由；持有 web_api 所需回调；重启窗口守卫
```

- 页面脚本一律外部 `type="module"` 文件（内联脚本可能先于 bridge 注入执行）
- 静态资源相对路径引用，不手拼 content 路径，不用 `..` 逃逸页面根目录

## 2. 后端：注册与版本降级

### 2.1 能力降级（修正原「hasattr 版本探测」的失实设计）

`register_web_api` 自 v4.10.4 即存在，`hasattr` **不能**探测 Pages 能力。真实
分层：

- **注册**：`main.py.initialize()` 中，`hasattr(self.context, "register_web_api")`
  为真则注册三条路由。此 hasattr **仅作测试 stub 环境的防炸护栏**，不作版本
  判断（真实 AstrBot 恒为真）
- **能力**：<4.24.1 无 iframe/bridge/页面入口，`pages/` 目录被忽略，端点虽注册
  但无 UI 可达（无害）；≥4.24.1 详情页入口可用；≥4.25.3 侧栏入口 + `isDark`
  /`locale` 上下文可用。README 按此说明，不写「运行时探测版本」

`_register_web_api()` 注册三条路由（handler 见 §3）：

| 路由 | 方法 |
|---|---|
| `/astrbot_plugin_palword/config/get` | GET |
| `/astrbot_plugin_palword/config/save` | POST |
| `/astrbot_plugin_palword/status/overview` | GET |

- handler 采用 Quart 兼容风格；同一 handler 不混用 v4.26 新旧 request
- 在 `initialize()` 注册合法（dashboard 请求时才对共享列表做匹配，不要求
  `__init__`）

### 2.2 分层结构（修正「纯函数 (status_code,payload)」与 async 的矛盾）

- `config_view.py`：**同步纯函数**，无 IO、无锁、无 await。三个纯函数：
  `redact_config(raw) -> dict`、`validate_and_backfill(body, old_raw, env) ->
  (ok, candidate_or_error)`、`status_rows(dtos) -> list`。可脱离 AstrBot 单测
- `web_api.py`：**async 编排**，副作用（`save_config`、`container.stop/start`、
  锁）全部以参数/回调注入，返回 `(200, payload_dict)`。锁作为注入参数而非
  模块全局（避免测试间污染）
- Quart 薄壳（在 main.py 或 web_api 顶部）：只做 request 解包与 jsonify

## 3. API 契约（全部 HTTP 200；`ok` 字段区分成败）

### 3.1 `GET config/get` — 读取配置（脱敏）

响应：`{"ok": true, "config": {...}, "page_version": 1}`

**脱敏规则（红线）**：

- `servers[i].password` / `custom_headers[i].value`：明文**绝不回显**，字段置空
  串，附兄弟标记 `password_set` / `value_set`
- 标记语义（修正 env 场景误导）：`password_set = bool(password) or
  bool(password_env)`；`value_set = bool(value) or bool(value_env)`。页面据此
  显示「已设置（env 提供）」或「已设置」或「未设置」
- `password_env` / `value_env`：环境变量**名**可回显；环境变量**值**绝不出现
- **稳定回填键**：`redact_config` 为每个 servers/custom_headers/group_bindings
  条目注入服务端生成的不透明 `__row_id`（列表内唯一，如序号派生的字符串）。
  页面保存时原样带回，作为回填匹配键（见 §3.2），取代脆弱的 name/索引匹配
- `base_url` / `username` / `umo` 照常回显（设置页编辑所需）；这些非秘密但属
  内网拓扑/PII，其保护依赖 §5 的鉴权纵深，而非脱敏

### 3.2 `POST config/save` — 校验、落盘、重启

请求体：与 `config/get` 的 `config` 同构，每条列表项带回 `__row_id`。敏感字段
哨兵语义：`password`/`value` 传 `"__unchanged__"` = 保留旧值；传其它（含空串）
= 覆盖。

处理顺序（每步失败均 `200 {"ok": false, "error": <code>, "detail": <安全信息>}`）：

1. **并发锁**：注入的 `asyncio.Lock`，`locked()` 为真立即返回
   `error="save_in_progress"`。锁用 `async with` 确保 handler 内任何异常都释放锁
2. **频率限制（防重启风暴）**：距上次成功保存 < `MIN_SAVE_INTERVAL`（默认 5s）
   返回 `error="too_frequent"`。独立于并发锁
3. **体积上限**：body 序列化字节数 > 上限（默认 256 KiB）、或任一列表长度
   > 上限（servers/custom_headers/group_bindings 各 200）、或任一字符串
   > 8 KiB → `error="too_large"`
4. **形状/类型校验**（先于回填，防非 dict 项崩溃）：body 是 dict；顶层键 ⊆
   schema 顶层键；servers/custom_headers/group_bindings 为 list 且**每个元素
   是 dict**；其余节是 dict。逐项按 schema 模板**白名单键**，丢弃未知键（含
   回传的 `password_set`/`value_set`/`__row_id`/`__template_key`——它们绝不
   进入落盘配置）。不通过 → `error="invalid_shape"`
5. **路径化语义预校验**（修正「错误只含路径」不可实现 + 泄值）：在 web_api 层
   逐字段显式校验并生成**字段路径**（不含字段值）：enum 走白名单
   （access_mode ∈ {restricted,open}、privacy.mode ∈ {strict,balanced,advanced}
   等）、int/float 字段验可转性与范围。任一失败 →
   `error="invalid_field", detail={"path": "servers[2].timeout"}`（仅路径）
6. **哨兵回填**（按 `__row_id` 匹配旧条目）：
   - 命中：`"__unchanged__"` → 回填旧秘密；否则用新值
   - `__row_id` 无匹配（新增条目）而值为哨兵 → `error="invalid_field",
     detail.path` 指向该条目（绝不落哨兵字面量、绝不静默清空）
   - **凭证重定向防护（HIGH-1）**：命中旧条目但该条目 `base_url` 的 scheme 或
     host 相较旧值发生变化，且 password/value 为哨兵（要求复用旧秘密）→
     `error="credential_redirect", detail.path`。用户改目标地址必须重新输入
     秘密，杜绝「保留旧密码 + 改 base_url 到攻击者主机」的凭证外泄
7. **落盘**：候选配置（已剥离所有 schema 外键）逐键写回 `self._raw_config`
   （AstrBotConfig；测试为 dict stub），`save_config()`（`hasattr` 存在才调）。
   **落盘前深拷贝旧 raw config 留作回滚**（嵌套 list 深拷贝，避免原地覆写污染）
8. **容器重启**（窗口协议见 §3.4）：置重启标志 → `await old.stop()` →
   用新 AppConfig 构建新 Container → `await new.start()`。
   - 成功：清标志，记 `last_save_ts`，返回成功
   - 新容器 start 失败：**先 `await new.stop()`**（best-effort try/except，回收
     其已开的 DB 连接）→ 用深拷贝旧 raw 恢复 `self._raw_config` + `save_config()`
     → 用旧 AppConfig 重建容器 start → 清标志，返回
     `error="restart_failed_rolled_back"`
   - 回滚也失败：容器置 None、保持重启标志为「故障」态，返回
     `error="restart_failed"`
   - 所有失败分支：日志与响应**只含错误码/路径**，禁止 `str(exc)`；**禁止记录
     候选配置**（含明文秘密）

成功响应：`{"ok": true, "warnings": {"skipped_servers": [{raw_name,reason}...],
"skipped_headers": [...]}}`（parse 宽容语义产生的 skip 作为告警）。

### 3.3 `GET status/overview` — 只读状态

复用现有查询链路。**按 DTO 实名**（修正捏造字段）：每服务器返回
`{"name", "ready", "online", "smoothness_label", "degraded", "last_ok"}`，
字段取自 `QueryService.status(world)` 的 `StatusDTO`（`presentation/dtos.py`）。

- **不含** `last_poll_ok`（DTO 无此字段，删除该捏造项）；`world_name` 与 name
  同值（`query_service.py` 写死 `world_name=world.server_name`），不重复展示
- `repo.get_current_world` 返回 None（未 ready / 从未成功轮询）的服务器 →
  返回 `{"name", "ready": false}` 骨架行，其余字段省略
- 重启窗口期（§3.4 标志为真或容器 None）→ `{"ok": true, "servers": [],
  "restarting": true}`
- 字段白名单：**无** base_url/password/umo/玩家个体信息（不扩大现有
  `/pal status` 已公开的暴露面）。注：现有 QueryService 无 strict 专门裁剪逻辑，
  本端点靠白名单自限，不声称「复用 strict 裁剪」

### 3.4 重启窗口协议（修正矛盾 + 命令面崩溃）

- `main.py` 持有 `self._restarting: bool`（或等价单一状态源），`status/overview`
  与聊天命令共用它判断窗口
- 进入重启前置 `self._restarting = True`；成功/回滚完成后置 False
- **main.py 全部 `/pal` 命令处理器**（现无 None 检查，窗口期必崩）加统一前置
  守卫：`self._restarting or self._container is None` → 回「插件正在重载配置，
  请稍后重试」，不触达已 stop 的容器/已关 DB
- `status/overview` handler 同源判断，返回 `restarting: true`

## 4. 前端页面

- `app.js`：`await bridge.ready()`；主题由 SDK 据 `isDark` 自动维护
  `<html data-theme>`，CSS 挂 `[data-theme="dark"]` 即可；`isDark===undefined`
  （<4.25.3）时页面用亮色默认，不手动设 dataset。两个 tab 纯 DOM 切换
- **XSS 红线（HIGH-4）**：所有服务器名/世界名/skipped reason/任何配置派生或
  游戏服务器派生字符串一律经 `textContent` / `createTextNode` 写入 DOM，**严禁**
  `innerHTML` 拼接。`world_name` 来自游戏服务器 `/info`（verify_tls 可关，可被
  MITM 注入），属不可信外部输入
- `settings.js`：
  - `bridge.apiGet("config/get")` 渲染；servers/custom_headers/group_bindings
    为可增删卡片列表，每卡片持有其 `__row_id`（新增条目无 id，保存时视为新建）
  - 敏感输入框据 `password_set`/`value_set` 显示占位「已设置（留空保持不变）」，
    **绝不预填明文**；用户不输入 → 提交 `"__unchanged__"`，输入 → 提交新值；
    改了某服务器 `base_url` 时高亮提示「需重新输入该服务器密码」
  - 提交后按响应 `ok` 分支：成功展示 warnings；`error` 各码给对应文案
    （save_in_progress/too_frequent/too_large/invalid_shape/invalid_field(带
    `detail.path`)/credential_redirect/restart_failed*）
  - 数值字段前端粗校验，真校验以后端为准
- `status.js`：`bridge.apiGet("status/overview")` 渲染卡片 + 「刷新」按钮；
  `restarting:true` 显示重载提示并 3 秒后自动重试一次。不用 SSE

## 5. 安全与脱敏（红线汇总）

1. **秘密永不出站**：password/value 明文、env 值不进任何响应/错误/日志/DOM
2. **凭证重定向防护**：server `base_url` scheme/host 变更时拒绝复用哨兵保留的
   秘密（§3.2 步骤 6）
3. **鉴权纵深**（不押单一假设）：(a) 实现期第一个任务实测按版本正确的 URL
   （v4.26+ `/api/v1/plugins/extensions/...`、4.24–4.25 `/api/plug/...`；注意
   未匹配路由平台返回 200+`status:error` 而非 404，验证脚本以「JWT 缺失得 401」
   为判据）；(b) CI 加未鉴权访问三端点应 401 的回归测试；(c) handler 内兜底：
   拿不到 Dashboard 用户身份（`request.username` 缺失）时拒绝——禁用/卸载后
   端点仍可达，兜底防线必需
4. **CSRF**：实现期实测 AstrBot 是否对插件 POST 强制 same-origin/CSRF token；
   若不强制，handler 自加 state-changing 防护（校验来源）
5. **XSS**：所有外部/配置派生字符串 `textContent` 入 DOM（§4）
6. **输入不可信**：item 类型 + 逐项键白名单先于回填；schema 外键（含回传标记）
   落盘前剥离；体积/长度上限；路径化预校验后 parse_config 仅作最终防线、其
   `ValueError`（含非法值文本）一律折叠为无文本错误码，禁止 `str(exc)` 出站
7. **禁止记录候选配置**：回填后的候选含明文秘密，任何日志分支不得打印它
8. **重启滥用**：并发锁 + 频率限制（§3.2 步骤 1/2）；README 说明保存触发容器
   重启，重启窗口内轮询数据短暂中断（会话/在线时长计入有微小缺口）
9. **哨兵冲突**：真实密码等于 `__unchanged__` 会被误判保留——页面 hint 与
   README 声明保留字；若用户提交的**新值**等于哨兵，页面前端拦截并提示

## 6. 测试计划

| 层 | 用例 |
|---|---|
| config_view 脱敏 | password/value 明文绝不出现在 redact 输出（深度遍历断言）；`password_set`=bool(password)∨bool(password_env)（env-only 场景为 true）；env 值不出现；每条注入唯一 `__row_id` |
| config_view 回填 | `__row_id` 命中 + 哨兵→回填旧秘密；命中 + 新值→覆盖；新增条目(无 id)+哨兵→invalid_field(path)；删除/重排后 id 仍正确匹配（不错绑）；显式空串→清空 |
| config_view 凭证重定向 | 命中条目改 base_url host + 哨兵 → credential_redirect(path)；仅改非 base_url 字段 + 哨兵 → 正常回填 |
| config_view 校验 | 顶层未知键→invalid_shape；列表项非 dict→invalid_shape（不崩）；逐项 schema 外键被剥离（不落盘）；enum 非法值→invalid_field(path) 且 detail 不含该值；int/float 不可转→invalid_field(path)；体积/长度超限→too_large |
| web_api 编排 | 成功返回 warnings(skipped)；并发锁 409 语义(save_in_progress)且异常后锁释放（后续保存不被永久拒）；频率限制 too_frequent；重启失败→先 stop 失败容器→回滚旧配置→restart_failed_rolled_back；回滚失败→restart_failed；任一失败响应/日志不含异常文本与候选配置 |
| web_api status | 实名字段(name/ready/online/smoothness_label/degraded/last_ok)；无 base_url/password/umo 键；world=None→ready:false 骨架；restarting→空列表+restarting:true |
| main.py 注册/窗口 | stub 无 register_web_api→不炸（护栏，非版本探测）；有→三路由正确前缀注册；`_restarting` 为真时 `/pal` 命令处理器返回重载提示、不触达容器 |
| 静态结构 | `pages/settings/index.html` 存在；引用的每个 js/css 存在；script 均为 type=module 外部文件；js 源码不含明文秘密回显路径 |
| README | 关键词断言：插件页面、4.24.1、4.25.3、`__unchanged__`、保存触发重启 |

前端交互逻辑不引入 Node 测试链，由 config_view/web_api 契约测试兜底。

## 7. 文档同步

- README 新增「插件页面」小节：入口（侧栏 ≥4.25.3、详情页 ≥4.24.1、<4.24.1
  页面不可用但插件其余功能正常）、`__unchanged__` 保留字、改 base_url 需重填
  密码、保存即重启容器（轮询短暂中断）、鉴权依赖 Dashboard 登录
- `metadata.yaml` 版本声明不变（`>=4.10.4`）；可选补 `icon: mdi-*`（侧栏图标，
  从 CDN 拉取、离线退化）——本期不做，记为后续可选

## 8. 复核记录

2026-07-12 三视角对抗式复核，主要修订：

- **平台（高）**：错误通道从 409/400/500 改为全 HTTP 200 + `ok:false`（bridge
  丢弃非 2xx 的状态码与响应体）；删除「hasattr 版本探测」失实设计，改为能力
  按版本降级、hasattr 仅作 stub 护栏；URL 按版本区分并修正验证判据；
  isDark/locale 仅 ≥4.25.3、主题交给 SDK
- **安全（高）**：新增凭证重定向防护（base_url 变更拒复用秘密）；鉴权改三层
  纵深（版本正确 URL 实测 + CI 回归 + handler 身份兜底）；CSRF 实测+兜底；
  XSS textContent 红线（world_name 是可 MITM 外部输入）；item 类型/键白名单、
  体积上限、禁记候选配置
- **正确性**：重启窗口显式标志 + main.py 命令守卫（原设计窗口期命令必崩）；
  回填改稳定 `__row_id`（原按 name/索引会错绑凭证）；错误路径化预校验取代
  「只含字段路径」空头支票（parse_config 异常含值无路径）；status 字段按 DTO
  实名、删 last_poll_ok/strict 裁剪捏造、world=None 骨架行；回滚深拷贝+先 stop
  失败容器；纯函数拆为同步 config_view + async web_api 编排；`self.config`
  更正为 `self._raw_config`
