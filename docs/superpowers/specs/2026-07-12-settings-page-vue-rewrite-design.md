# 设计规格：设置页 Vue3 重写 + 白屏根因修复

- 状态：已按三视角对抗式复核修订（待用户复审）
- 日期：2026-07-12
- 分支：`feature/settings-page-refine`
- 交付方式：**一体交付**（白屏止血 + Vue3 重写在同一 plan 内完成、一次上线；实现顺序上止血相关任务优先，先堵死白屏路径再铺开重写）。
- 关联：取代 PR #4 交付的手写设置页前端实现；沿用其后端配置读写契约（`config_view.py`，本次冻结不改）。

---

## 1. 背景与问题

PalChronicle 的 AstrBot 插件设置页当前**整页白屏**（可打开、顶部两个 tab 能切换，但两个面板都空——即"形态 B"）。经对 AstrBot 官方源码（`AstrBotDevs/AstrBot`，跨 master 与 v4.25.6 核实）交叉验证，白屏是**前后端两个缺陷叠加**的确定结果。

### 1.1 根因 A（后端，白屏真正诱因）—— 鉴权取用户名的属性从来就取错了

**已认证的 Dashboard 用户名从来只绑定在 `g.username`（与传入 handler 的 `PluginRequest.username`）上，从不绑定在 `request` 上**——这一点在 AstrBot 的**纯 Quart 版（v4.24.x~v4.25.x）**与 **FastAPI+Quart 兼容层版（v4.26.x master）**上均成立：

- 纯 Quart 版（v4.25.6，`server.py:367/437`）：鉴权后 `g.username = ...`，插件 handler 跑在真实 Quart 请求上下文，`g.username` 可用；
- FastAPI+兼容层版（master，`plugins.py:189-226`）：`Depends(require_plugin_scope)` 鉴权后，用户名写入 `g_obj.username` 与 `PluginRequest.username`，经 `call_request_view` 在真实 Quart compat 上下文里 `setattr(g, "username", ...)`；`DashboardRequest` 代理**无 `username` 字段**（`asgi_runtime.py:139-148, 375`）；
- 官方测试 `tests/test_fastapi_v1_dashboard.py` 锁定的三种取法（`g.username` / `plugin_request.username` / Quart 兼容模式 `quart_g.username`）**没有一种是 `request.username`**。

而本插件 `main.py:179-184` 的 `_has_identity()` 读的是 `getattr(request, "username", None)`：

```python
@staticmethod
def _has_identity() -> bool:
    from quart import request
    return bool(getattr(request, "username", None))   # ← 在任何带插件页的版本上都恒 None
```

**因此这个 bug 从未在任何版本工作过**（不是"FastAPI 迁移后才坏"）。后果：`_has_identity()` **恒返回 `False`** → 三个端点 `config/get`、`config/save`、`status/overview` **全部**稳定返回 `{ok: false, error: "unauthorized"}`（`main.py:191-220` 每个 handler 均先查身份）。因静默返回而非抛异常，后端日志无任何报错线索。

参考源码：`plugins.py#L189-L226`、`auth.py#L145-L173`、`web.py#L165-L185`（`PluginRequest.username`）、`asgi_runtime.py#L139-L148/#L375-L377`、`server.py`(v4.25.6)`#L367/#L437`、`test_fastapi_v1_dashboard.py#L905-L911/#L2688-L2730`。

### 1.2 根因 B（前端，把 "unauthorized" 放大成 "白屏"）

`settings.js:122-126`：

```js
try { const r = await bridge.apiGet("config/get"); cfg = r.config; }  // ok:false 时 r.config = undefined
catch (e) { toast("读取配置失败"); return; }
(cfg.servers || []).forEach(...)   // ← try 之外：undefined.servers → TypeError，无人接住
```

bridge 在 HTTP 200 + body `{ok:false}` 时 **resolve 出完整 body**（父帧 `PluginPagePage.vue:386-389` 仅在 `response.data.status==="error"` 时 reject，本插件 payload 无 `status` 字段），`cfg` 为 `undefined`，`cfg.servers` 抛 `TypeError`；`app.js:27` 调 `mountSettings(...)` 既未 `await` 也无 `try/catch`，异常无人兜底 → 面板 `replaceChildren()` 清空后停在空白。`status.js:16` 写了 `if (!data.ok)` 检查，`settings.js` **漏了对应检查**——两模块不一致。

### 1.3 附带缺陷（本次一并处理）

1. **设置页只暴露 9 个配置节里的 2 个**（只渲染 `servers`/`custom_headers`，其余七节用户只能改配置文件）。
2. **无错误边界 / 四态**：成功路径外的一切都塌缩成一个 3 秒 toast。
3. **样式极简**（`style.css` 仅 11 行，与 Dashboard 观感不协调）。
4. **版本声明过低且矛盾**：`metadata.yaml:7` 与 `README.md:15` 写 `>=4.10.4`；插件页面能力（PR #5940）自 **v4.24.1** 引入（`README.md:100-102` 已有更准的"详情页 ≥4.24.1 / 左栏分组 ≥4.25.3"细分说明）。
5. **`main.py:100-103` 的 `hasattr` 护栏**在缺失方法时静默跳过注册，掩盖问题。

---

## 2. 目标 / 非目标

**目标**

- 修白屏：后端改正鉴权取用户名方式（根因 A）+ 前端纵深防御（根因 B）。
- 前端重写为 **Vue3 + Reka UI（headless）+ Vite + 自写 tokens**，补全全部 9 个配置节，加入错误边界与四态，美化到与 Dashboard 协调。
- **Quart 兼容层审计**：核实 `main.py` 所有 `quart` 用法在目标版本区间可靠。
- 前端 vitest + Vue Test Utils 完整组件测试；后端**新增**鉴权测试；清理失效的旧结构测试。
- 修正版本声明与 README。

**非目标（本次不做，YAGNI）**

- bridge 内建 i18n（保持 zh-CN 硬编码）。
- 状态页 SSE 推送（保留现有轮询）。
- `group_bindings` 在设置页编辑或展示（它是运行时群授权，归 `/pal use`、`/pal unbind` 命令；**保存时如实保留旧值，绝不清空**，见 §4.3/§6）。
- 改动后端 `config_view.py` 的配置读写安全契约（脱敏 / 校验 / 哨兵 / 白名单一律冻结）。

---

## 3. 架构：目录、构建与可复现性

前端源码与 AstrBot 实际 serve 的产物**分离**：

```
frontend/                    # 新增：前端源码
  package.json               # vue, reka-ui, vite, vitest, @vue/test-utils, jsdom, typescript
  package-lock.json          # 必须入 git（见下：可复现构建）
  .nvmrc                     # 钉 Node 版本（本地与 CI 一致）
  vite.config.ts             # base:'./' + 单 chunk 硬约束（见下）
  tsconfig.json
  index.html
  src/
    main.ts                  # 入口：bridge.ready() → 挂载 App；顶层 .catch 兜底
    bridge.ts                # 唯一碰 window.AstrBotPluginPage 的出口
    App.vue                  # 壳：tab + onErrorCaptured 错误边界 + 四态
    components/{SettingsPanel,StatusPanel}.vue, sections/*.vue, cards/*.vue, ui/*.vue
    lib/{collect.ts, schema.ts, errors.ts}
    styles/tokens.css
    __tests__/
pages/settings/              # AstrBot serve 这里：Vite 构建产物（入 git）
  index.html  assets/index.<hash>.js  assets/index.<hash>.css
```

### 3.1 构建正确性硬约束（阻断级，源自平台复核 F1/F5）

**AstrBot 的 JS import 重写正则 `_JS_MODULE_FROM_RE`（`plugin_page_service.py:43-46`）要求 `from` 两侧有空白，而 Vite 压缩产物是 `}from"./x.js"`（无空白）——不会被追加 asset_token，跨 chunk import 在 null-origin sandbox 里 401 → 白屏**；叠加 asset_token **60 秒 TTL**，任何延迟 `import()` 60s 后必 401。故以下是**正确性约束，不是优化**：

- `vite.config.ts`：`build.rollupOptions.output = { inlineDynamicImports: true, manualChunks: undefined }`、`build.cssCodeSplit: false`、`base: './'`。目标产物：**单个 `.js` + 单个 `.css`，零静态跨-chunk import、零动态 `import()`**。
- **CI 硬校验**（与"产物无 diff"并列为验收项）：build 后断言 `pages/settings/assets/` 只有 1 个 `.js` 文件；正则扫描该文件**不含** `}from"./`、`}from'./`、`*from"./`、` from"./`、`import(`（入口自身无外链 import）。

### 3.2 可复现构建与供应链（源自安全复核 SEC-2、正确性 F10）

- **`package-lock.json` 必须入 git**；CI 用 `npm ci`（依赖 lockfile），直接依赖钉到确切版本或锁 minor。
- CI 与本地统一 Node 版本（`.nvmrc` / `engines`）。
- `.gitattributes`：`pages/settings/**` 产物强制 `text eol=lf`，规避 win32 本地 / linux CI 的 CRLF 漂移。
- `frontend/node_modules` 进 `.gitignore`；`frontend/src` 源码与 `pages/settings/` 产物都入 git。
- CI 步骤：`cd frontend && npm ci && npm run build && npm test`，随后校验 `pages/settings/` 无未提交 diff + §3.1 的产物断言。

---

## 4. 前端设计

### 4.1 `bridge.ts`——单一出口 + 两层错误模型

所有与 `window.AstrBotPluginPage` 的交互只经此模块。**区分两层错误**（源自复核 F8）：

- **transport 层**：bridge `reject`（网络 / 非 2xx / bridge 缺失）→ `BridgeMissing`（缺失）或 `RequestFailed`（网络）。
- **业务层**：resolve 后 `r.ok === false` → 按 `error` 码分流：`unauthorized` → `Unauthorized`；其余 → `BusinessError(error, path?)`。

契约不变量（源自复核 SEC-3、平台 F7）：

- **只从 `detail` 白名单取 `path`（字符串）用于文案，绝不把 `detail` 整体或后端自由文本渲染进 DOM**；未知 `error` 码回退通用文案。
- `apiGet` 返回的是**完整业务包**（`{ok,error,config,...}`，非解包后的 data）；**后端一律用扁平 `{ok,error,...}` 约定，严禁引入顶层 `status` 字段**（否则父帧解包语义反转）。
- **杜绝 `r.config` 为 undefined 再解构**的路径（根因 B 回归锚点）。

### 4.2 `App.vue`——错误边界 + tab + 状态模型

- `onErrorCaptured` + `main.ts` 的 `.catch`：任何未处理异常渲染兜底错误页，**永不白屏**。
- **整页态**（仅这几类进整页 error/加载态）：`loading`（首屏骨架）/ `fatal-error`（bridge 缺失 / 首屏 `config/get` 失败 / `unauthorized`）/ `empty`（无服务器引导）/ `restarting`（保存重载中，轮询至就绪）。
- **保存动作的局部态**（不打整页 error，保留表单、就地提示）：`credential_redirect`、`too_frequent`、`save_in_progress`、`invalid_field`/`invalid_shape` 等业务码；**"保存中并发"为一等状态**（保存按钮 `disabled` + loading）。

### 4.3 9 个配置节表单 + `collect` 语义（消除 §4.3 原矛盾，源自复核 F1/F2/F3/F6）

后端契约**已支持** 9 节往返（`redact_config` 返回全部节、`validate_and_backfill._TOP_KEYS` 含全部 9 节），补全是纯前端工作。

| 节类型 | 节 | 控件 |
|---|---|---|
| 列表·可增删卡片 | `servers`、`custom_headers` | 卡片 + 字段；敏感字段（password/value）沿用哨兵 `__unchanged__` |
| object·分组表单 | `routing`、`polling`、`world`、`bases`、`privacy`、`history`、`features` | enum→Select、数值→NumberField、bool→Switch、字符串→Input |
| 布局 | 全 9 节 | Collapsible/Accordion 分区 |

**`collect.ts` 语义（明确、单一）**：由 `schema.ts` 元数据表**驱动逐字段收集用户输入**，产出与 `config/save` 契约一致的 body。**不再"原样透传"**。硬规则：

- **类型正确**：`NumberField → number`、`Switch → boolean`、字符串 → string；**绝不把数值/布尔收集成字符串**（否则 `bool('false')===true` 静默反转、`_conf_schema.json` 类型漂移）。
- **`schema.ts` 字段完整性**：必须覆盖每个 object 节在 `_conf_schema.json` 里的**全部**字段（漏字段 = 保存即回落默认值、静默丢配置）。以 `_conf_schema.json` 为真源做测试断言（见 §7）。
- **`group_bindings` 保护**：`collect` 产出的 body **完全不含 `group_bindings` 键**，依赖后端"缺键保留旧值"（`main.py:126` `for k,v in candidate.items()` 不覆盖缺失键）→ 预设群授权不被清空。以回归测试锁死。
- **顶层键纪律**：body 顶层键必须 ⊆ 后端 `_TOP_KEYS`；不得把 `page_version`/`__row_id`/`password_set`/`value_set` 抬到顶层。
- 敏感字段红线：password/value 明文不回显、不预填；拒绝字面量哨兵输入（沿用 `collectSecret` 语义）。

### 4.4 主题与样式（源自复核 F11）

- `tokens.css`：间距/字号/圆角/颜色/阴影/焦点环全变量化，亮暗双主题吃 `[data-theme]`。
- **首屏主题时序**：服务端在返回 HTML 时注入 `data-theme` 以减首屏闪烁；SDK 仅在收到 context 消息时更新 `data-theme`。故 **loading 骨架样式必须走 tokens 且不假设 `isDark` 已知**（用中性 / 跟随已注入的 `data-theme`），`main.ts` 在 `await bridge.ready()` 后再切实际主题。
- focus-visible 环、hover、`:disabled`、保存 loading、`prefers-reduced-motion` 降级。

### 4.5 前端安全

- **只用 SFC 预编译渲染函数**（Vite vue 插件默认），不引入 runtime template compiler、不用字符串 `template` 选项（规避潜在 eval 依赖 + 减体积）。
- Vue 模板默认转义，**全程禁 `v-html`**（等价原"绝不 innerHTML"红线）。

---

## 5. 后端设计

### 5.1 修正鉴权（根因 A）

`main.py:_has_identity` 改从 `g` 取用户名，并容忍无 app context 的边界（源自安全复核 SEC-4）：

```python
@staticmethod
def _has_identity() -> bool:
    try:
        from quart import g
        return bool(getattr(g, "username", None))
    except RuntimeError:            # 无 app context（正常 register_web_api 链路不可达）→ 拒绝
        return False
```

- **取值方式**：主用 `g.username`（经源码核实跨 v4.24.x 纯 Quart ~ v4.26.x 兼容层全区间可用，且 `g` 非 request 代理，不触犯官方"勿混用两个 request proxies"告诫）。
- **前向注记（非本次强制）**：官方推荐新代码用 `from astrbot.api.web import request/json_response`；若未来统一迁移可整体切换，但本次以最小、已验证的 `g.username` 为准。

### 5.2 Quart 兼容层审计

核实 `main.py` 每处 `quart` 用法在目标版本可靠：

- `from quart import g`：用于 `g.username`（§5.1）。
- `from quart import request`：仅用 `request.get_json(silent=True)` / `args` / `headers`（已确认兼容层提供）；**不再读 `request.username`**。
- `from quart import jsonify`：**已核实可靠**（`asgi_runtime.py:419-420` `jsonify→JSONResponse`，`dict/list` 亦自动转），保留，无需切 `json_response`。
- 产出"用法 → 结论"清单纳入实现记录。

### 5.3 后端测试（新增，此前零覆盖——源自三视角一致发现 F5/SEC-1/F3）

仓库**当前没有任何** `_has_identity`/三端点鉴权测试。本次**新增**（非"更新"）：

- 可测化：把取用户名下沉为可注入单点（如 `_current_username()`），单测 monkeypatch 该函数；或用 `quart` 的 `test_request_context` / 注入带/不带 `username` 的假 `g`。
- 必测三断言（经 `main.py` 的 `_web_config_*` 薄壳，而非只测纯 handler）：
  (a) `g.username` 存在 → 三端点正常；
  (b) `g` 无 `username`（`getattr→None`）→ 三端点回 `unauthorized`；
  (c) 无 app context（`RuntimeError`）→ 拒绝（不冒泡 500）。

---

## 6. 数据流与错误处理

- **读**：`App` 挂载 → `bridge.ready()` →（设置）`apiGet("config/get")` 渲染 9 节；（状态）`apiGet("status/overview")` 卡片；`restarting` 轮询至就绪。
- **写**：`collect` → `apiPost("config/save", body)`（**body 不含 group_bindings**）→ 成功 toast（含被跳过条数）；业务失败按 §4.2 落局部态、按 `error` 码映射文案（沿用 `errorText` 映射）→ 触发后端重载，期间状态区显示"正在重载"。
- 后端成败一律 HTTP 200 + `payload.ok`（契约不变）；前端据两层错误模型分流，无静默崩溃路径。

---

## 7. 测试与验收

**前端（vitest + Vue Test Utils，jsdom，mock `window.AstrBotPluginPage`）**

- 纯逻辑（`collect.ts`/`schema.ts`）：字段收集、哨兵回填/拒绝字面量哨兵、**类型正确性断言（数值节为 number、bool 节为 boolean，非字符串）**、**`schema.ts` 字段集 == `_conf_schema.json` 各 object 节键集**（缺一即失败）、body 顶层键 ⊆ `_TOP_KEYS`、**body 不含 `group_bindings`**。
- 组件：9 节渲染、增删卡片、敏感字段占位、状态机（loading/fatal-error/empty/restarting + 保存局部态/并发禁用）、错误类型→文案映射、错误边界兜底不白屏。
- 根因 B 回归锚点：mock 父帧对 `{ok:false,error:"unauthorized"}` 走 **resolve**，验证 `bridge.ts` 进 `Unauthorized` 分支、渲染可见提示而非崩溃。

**后端（Python）**

- §5.3 的身份门三断言。
- `config_view.py` 既有纯函数测试不变（契约未动）。
- **回归**：保存 `servers` 后 `group_bindings` 不被清空（锁死 §4.3 保护）。

**验收标准**

1. 真实 AstrBot（≥ 目标版本）Dashboard 打开设置页**能加载配置**（白屏消失）。
2. 9 节均可编辑保存；数值/布尔**落盘 round-trip 后类型不漂移**；保存触发重载，期间提示、就绪后恢复。
3. 断网 / 未登录 / bridge 缺失分别渲染**可见且不同**的态，**均不白屏**。
4. `npm ci && build` 产物与 `pages/settings/` 入库一致；**§3.1 产物断言通过**（单 js、无跨-chunk/动态 import）；vitest 与后端测试全绿。

---

## 8. 安全与隐私（红线，重写后必须全部保持）

- **凭证不外泄**：password/value 明文与 env 值绝不下发/回显/入产物；`redact_config` 脱敏契约不变。
- **哨兵回填 + 凭证重定向**：改 `base_url` 需重填密码等后端校验不变；前端如实呈现为局部态。
- **顶层键白名单 / `_strip_meta`**：后端落盘白名单不变；前端 body 顶层键 ⊆ `_TOP_KEYS`。
- **身份兜底仍在**：修正取值方式但保留 `_has_identity` 防线（读任何配置/secret 前判定）。
- **detail 不变量**：后端 `detail` 永远只含结构化 `path`，禁塞异常文本/配置值；前端只白名单取 `path`（测试锁定）。
- **XSS**：Vue 默认转义 + 禁 `v-html` + 仅 SFC 预编译。
- **沙箱 / CSP 合规**：相对路径（asset_token 重写）、无外部 CDN、不碰 `localStorage`/`cookie`/同源 `fetch`（一切走 bridge）。CSP 无 script-src/style-src，Reka/Vue scoped style 注入不被拦。
- **供应链**：`package-lock.json` 入库 + 钉版本，杜绝入库产物含未审计依赖代码。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| **Vite 压缩产物静态 import 不被 asset_token 重写 → 白屏** | §3.1 单 chunk 硬约束 + CI 产物断言（最高优先） |
| asset_token 60s TTL → 延迟 `import()` 必 401 | 同上：零动态 import（`inlineDynamicImports`） |
| null-origin 沙箱（无 `allow-same-origin`） | Reka headless 不碰持久化/CDN；状态只存内存；网络只走 bridge |
| `no-store` 每次全量重下 | headless 产物小（~60–95 KB gzip）+ 单文件 |
| 依赖漂移 → 入库产物含未审计代码 / CI diff | `package-lock.json` 入库 + 钉版本 + 统一 Node（§3.2） |
| 数值/布尔类型漂移污染落盘 | `collect` 按 schema 产出正确 JSON 类型 + 测试断言 |
| `schema.ts` 漏字段 → 保存即丢配置 | 以 `_conf_schema.json` 为真源的完整性断言 |
| `group_bindings` 保存即清空 | body 不含该键 + 回归测试 |
| 版本装到过低环境 | metadata/README 抬到 `>=4.24.1`；bridge 缺失渲染显式态 |

---

## 10. 迁移与清理

- `metadata.yaml:7` `astrbot_version` → **`>=4.24.1`**（插件详情页可用门槛）。
- `README.md`：修正 `:15` 的 `>=4.10.4` 过低声明；**保留** `:100-102` 已有的"详情页 ≥4.24.1 / 左栏分组 ≥4.25.3"细分（比单值更准）；更新设置页说明（9 节可视化编辑）。
- 删除旧手写 `pages/settings/{app.js, settings.js, status.js, style.css, index.html}`，由 Vite 产物取代。
- **删除或重写 `tests/unit/pages_static_test.py`**：它硬编码断言旧文件名 / grep 源码中文串 / `.innerHTML`，Vite 产物会让它全红。XSS"禁 innerHTML/v-html"红线转移到前端 vitest（断言不用 `v-html`）+ 对 `frontend/src` 源码（非压缩产物）的 grep。
- `main.py:100-103` `hasattr` 护栏：保留作 stub 护栏，注释更新（不再暗示版本判断）。

---

## 11. 开放问题（待用户复审确认）

- `group_bindings`：本次默认**设置页不展示不编辑**、保存时如实保留旧值（§4.3）。如需只读展示，另议。
- （原 `jsonify` 兼容层可靠性问题已在 §5.2 关闭：核实可靠，保留 `jsonify`。）
