# 设计规格：设置页 Vue3 重写 + 白屏根因修复

- 状态：待三视角对抗式复核
- 日期：2026-07-12
- 分支：`feature/settings-page-refine`
- 关联：取代 PR #4 交付的手写设置页（`2026-07-12-plugin-pages-settings-design.md`）的前端实现；沿用其后端配置读写契约（`config_view.py`）。

---

## 1. 背景与问题

PalChronicle 的 AstrBot 插件设置页当前**整页白屏**（可打开、顶部两个 tab 能切换，但两个面板都空——即"形态 B"）。经对 AstrBot 官方源码（`AstrBotDevs/AstrBot` master 分支）交叉核实，白屏是**前后端两个缺陷叠加**的确定结果：

### 1.1 根因 A（后端，白屏真正诱因）—— 鉴权取用户名的方式在新框架下失效

AstrBot 的 Dashboard 后端已从 **Quart 迁移到 FastAPI/Starlette**，插件 Web API 现由 FastAPI 路由承载。已认证的 Dashboard 用户名**不再挂在 `request` 上**：

- 插件扩展路由 `plugins.py:378` 用 `Depends(require_plugin_scope)` 鉴权，用户名取自 `AuthContext.username`；
- 转发进插件 handler 时，用户名写入 **`g.username`**（Quart 兼容 `g`）与 `PluginRequest.username`，**从不写 `request.username`**（`plugins.py:189-226`）；
- Quart 兼容代理绑定的 `DashboardRequest` 只有 `method/path/headers/cookies/args/get_json`，**无 `username` 字段**（`asgi_runtime.py:139-148, 375`）；
- 官方测试 `tests/test_fastapi_v1_dashboard.py` 锁定的三种取法（`g.username` / `plugin_request.username` / Quart 兼容模式下 `quart_g.username`）**没有一种是 `request.username`**。

而本插件 `main.py:179-184` 的 `_has_identity()` 用的正是 `getattr(request, "username", None)`：

```python
@staticmethod
def _has_identity() -> bool:
    from quart import request
    return bool(getattr(request, "username", None))   # ← 恒为 None
```

后果：`_has_identity()` **恒返回 `False`** → 三个端点 `config/get`、`config/save`、`status/overview` **全部**稳定返回 `{ok: false, error: "unauthorized"}`（`main.py:191-220` 每个 handler 均先查身份再办事）。因静默返回而非抛异常，后端日志无任何报错线索。

参考源码：
- `plugins.py`（路由 + `_call_plugin_extension`）：`.../astrbot/dashboard/api/plugins.py#L189-L226`、`#L378-L384`
- `auth.py`（`require_scope` / `_extract_dashboard_jwt`）：`.../astrbot/dashboard/api/auth.py#L72-L84`、`#L145-L173`
- `web.py`（`PluginRequest.username`）：`.../astrbot/api/web.py#L165-L185`
- `asgi_runtime.py`（Quart 兼容代理，`request` 无 username / `g` 有）：`#L139-L148`、`#L375-L377`、`#L567-L604`
- `test_fastapi_v1_dashboard.py`（官方取法）：`#L905-L911`、`#L2688-L2730`

### 1.2 根因 B（前端，把"unauthorized"放大成"白屏"）

`settings.js:122-126`：

```js
try { const r = await bridge.apiGet("config/get"); cfg = r.config; }  // ok:false 时 r.config = undefined
catch (e) { toast("读取配置失败"); return; }
(cfg.servers || []).forEach(...)   // ← try 之外：undefined.servers → TypeError，无人接住
```

后端返回 `{ok:false}`（无 `config` 字段）时，`cfg` 为 `undefined`，`cfg.servers` 抛 `TypeError`；`app.js:27` 调 `mountSettings(...)` 既未 `await` 也无 `try/catch`，异常无人兜底 → 面板 `replaceChildren()` 清空后停在空白。`status.js:16` 写了 `if (!data.ok)` 检查，`settings.js` **漏了对应检查**——两模块处理不一致。

### 1.3 附带缺陷（本次一并处理）

1. **设置页只暴露 9 个配置节里的 2 个**：`settings.js` 只渲染 `servers` 与 `custom_headers`，`routing / polling / world / bases / privacy / history / features` 七节在页面上不存在，用户只能改配置文件。
2. **无错误边界 / 四态**：成功路径之外的一切（加载中、bridge 缺失、后端错、空数据、重载中）都塌缩成一个 3 秒 toast。
3. **样式极简**：`style.css` 仅 11 行，无 focus/hover/disabled/loading 态，与 Dashboard 观感不协调。
4. **版本声明矛盾且过低**：`metadata.yaml:7` 与 `README.md:15` 写 `>=4.10.4`，而插件页面能力（Plugin Pages / bridge / `register_web_api`）自 **v4.24.2** 才引入；README 内部 `:15` 与 `:100` 自相矛盾。
5. **`main.py:100-103` 的 `hasattr` 护栏**在旧版会静默跳过注册，掩盖版本不匹配。

---

## 2. 目标 / 非目标

**目标**

- 修白屏：后端改正鉴权取用户名方式（根因 A）+ 前端纵深防御（根因 B）。
- 前端重写为 **Vue3 + Reka UI（headless）+ Vite + 自写 tokens**，补全全部 9 个配置节，加入错误边界与四态，美化到与 Dashboard 协调。
- **Quart 兼容层审计**：逐一核实 `main.py` 所有 `quart` 用法在 FastAPI+兼容层下可靠。
- 前端 vitest + Vue Test Utils 完整组件测试；后端 Python 测试更新/补齐。
- 修正版本声明与 README。

**非目标（本次不做，YAGNI）**

- bridge 内建 i18n（保持 zh-CN 硬编码）。
- 状态页 SSE 推送（保留现有轮询）。
- `group_bindings` 在设置页编辑（它是运行时群授权，归 `/pal use`、`/pal unbind` 命令管）。
- 改动后端 `config_view.py` 的配置读写安全契约（脱敏 / 校验 / 哨兵 / 白名单一律不动）。

---

## 3. 架构：目录与构建

前端源码与 AstrBot 实际 serve 的产物**分离**：

```
frontend/                    # 新增：前端源码（可脱离仓库独立构建）
  package.json               # vue, reka-ui, vite, vitest, @vue/test-utils, jsdom, typescript
  vite.config.ts             # base:'./' + build.cssCodeSplit:false + 单 chunk（关 code-split）
  tsconfig.json
  index.html                 # 构建入口（源）
  src/
    main.ts                  # 入口：await bridge.ready() → 挂载 App；顶层 .catch 兜底
    bridge.ts                # 唯一碰 window.AstrBotPluginPage 的出口：类型化 apiGet/apiPost + 缺失探测 + 统一 r.ok 检查
    App.vue                  # 壳：tab 路由 + onErrorCaptured 错误边界 + 四态
    components/
      SettingsPanel.vue      # 设置（9 节）
      StatusPanel.vue        # 状态
      sections/*.vue         # 每个配置节一个子组件
      cards/ServerCard.vue, HeaderCard.vue
      ui/*.vue               # 基于 Reka UI 封装的 Field/Select/Switch/NumberField/Card/Collapsible
    lib/
      collect.ts             # 纯逻辑：表单值收集 / 哨兵回填 / 字段映射（vitest 重点）
      schema.ts              # 配置节 → 字段控件元数据表
      errors.ts              # 错误类型（BridgeMissing / Unauthorized / RequestFailed）
    styles/tokens.css        # 设计变量（亮暗）
    __tests__/               # vitest：组件测试 + collect/schema 纯逻辑测试
pages/settings/              # AstrBot serve 这里：Vite 构建产物（入 git）
  index.html  assets/*.js  assets/*.css
```

**构建 & CI 约定**

- 构建：`cd frontend && npm run build` → 产物输出到 `../pages/settings/`（覆盖现有手写文件）。
- Vite：`base: './'`（相对路径，交由 AstrBot asset_token 重写）、`build.cssCodeSplit: false` + 单文件/少文件、**禁 code-splitting 动态外链 chunk**（否则 asset_token + CSP 白屏）。
- git：`frontend/node_modules` 进 `.gitignore`；**`frontend/src` 源码与 `pages/settings/` 产物都入 git**（`no-store` + asset_token 要求 serve 现成静态文件）。
- CI 新增一步：`cd frontend && npm ci && npm run build`，随后**校验 `pages/settings/` 无未提交 diff**（锁死"产物 = 源码构建结果"，防漂移）+ 跑 vitest。

---

## 4. 前端设计

### 4.1 `bridge.ts`——单一出口 + 可识别错误

所有与 `window.AstrBotPluginPage` 的交互只经此模块：

- 启动探测：`window.AstrBotPluginPage` 缺失 → 抛 `BridgeMissing`（App 渲染"需要 AstrBot ≥ v4.24.2 的插件页环境"）。
- `await bridge.ready()` 后暴露类型化 `apiGet<T>(endpoint, params?)` / `apiPost<T>(endpoint, body?)`。
- **统一查 `r.ok`**：`ok:false && error==="unauthorized"` → 抛 `Unauthorized`（"未登录或登录已过期，请重新登录 Dashboard"）；其余 `ok:false` → 抛 `RequestFailed(error, detail)`；网络/异常 → `RequestFailed`。**杜绝 `r.config` 为 undefined 再解构的路径。**

### 4.2 `App.vue`——错误边界 + tab + 四态

- `onErrorCaptured` + `main.ts` 的 `.catch`：任何未处理异常渲染兜底错误页，**永不白屏**。
- 两个 tab（设置 / 状态），各自独立四态。
- **四态**（每个数据区一等公民）：`loading`（骨架）/ `error`（按错误类型分文案 + 重试）/ `empty`（无服务器时引导）/ `restarting`（保存重载中，轮询状态至就绪）。

### 4.3 9 个配置节表单

后端契约**已支持** 9 节往返（`redact_config` 返回全部节、`validate_and_backfill` 的 `_TOP_KEYS` 含全部 9 节），补全是纯前端工作。

| 节类型 | 节 | 控件（Reka UI 封装） |
|---|---|---|
| 列表·可增删卡片 | `servers`、`custom_headers` | 卡片 + 字段；敏感字段（password / value）沿用**哨兵 `__unchanged__`**，占位"已设置（留空保持不变）" |
| object·分组表单 | `routing`、`polling`、`world`、`bases`、`privacy`、`history`、`features` | enum→Select、数值→NumberField、bool→Switch、字符串→Input |
| 布局 | 全 9 节 | Collapsible/Accordion 分区，避免超长表单 |

- 控件元数据集中在 `lib/schema.ts`（节→字段→类型→enum 选项→占位），驱动渲染，避免散落。
- 保存：`lib/collect.ts` 收集为与 `config/save` 契约一致的 body（列表节含 `__row_id`，哨兵处理同现状）；**其余 object 节原样透传**（与现 `settings.js:151` 行为一致）。
- **敏感字段红线**：password / value 明文不回显、不预填；哨兵字面量输入拒绝（沿用现 `collectSecret` 语义）。

### 4.4 主题与样式

- `tokens.css`：间距 / 字号 / 圆角 / 颜色 / 阴影 / 焦点环全变量化，亮暗双主题吃 `[data-theme]`。
- 主题跟随：`App` 订阅 `bridge.getContext()/onContext()` 的 `isDark`；SDK 已自动维护 `document.documentElement` 的 `data-theme`，前端只需让 tokens 响应它。
- focus-visible 环、hover、`:disabled`、保存中 loading、`prefers-reduced-motion` 降级。

### 4.5 XSS / 安全（前端）

- Vue 模板默认转义，**全程禁用 `v-html`**（等价于原实现"绝不 innerHTML"红线）。
- 服务器名、公会名等外部字符串一律走文本插值。

---

## 5. 后端设计

### 5.1 修正鉴权（根因 A）

`main.py:_has_identity` 改为从 Quart 兼容 `g` 取用户名：

```python
@staticmethod
def _has_identity() -> bool:
    from quart import g
    return bool(getattr(g, "username", None))
```

### 5.2 Quart 兼容层审计（全面）

逐一核实 `main.py` 中每处 `quart` 用法在 FastAPI + 兼容层下可靠，不可靠者替换：

- `from quart import request`：仅用其 `get_json` / `args` / `headers` 等已确认存在的字段（`_web_config_save` 的 `request.get_json(silent=True)`）；**不得再读 `request.username`**。
- `from quart import jsonify`：确认兼容层提供且返回 AstrBot 期望的响应类型；若不可靠，改用 AstrBot 原生 `json_response`（`astrbot.api.web`）。
- `from quart import g`：用于 `g.username`。
- 产出一份"用法 → 兼容层可用性 → 处置"清单，纳入实现与测试。

### 5.3 后端测试

- 更新身份兜底测试：现有若 mock `request.username`，改为 mock `g.username`；覆盖 `g` **有 / 无** username 两条路径（授权通过 vs `unauthorized`）。
- 保持 `config_view.py` 既有纯函数测试不变（契约未动）。

---

## 6. 数据流与错误处理

- **读**：`App` 挂载 → `bridge.ready()` →（设置 tab）`apiGet("config/get")` → 渲染 9 节表单；（状态 tab）`apiGet("status/overview")` → 卡片；`restarting` 时轮询至就绪。
- **写**：收集 → `apiPost("config/save", body)` → 成功 toast（含被跳过条数）/ 失败按 `error` 码映射文案（沿用现 `errorText` 映射：`save_in_progress` / `too_frequent` / `invalid_shape` / `credential_redirect` / `restart_failed_rolled_back` / `unauthorized` 等）→ 触发后端重载，期间状态区显示"正在重载"。
- **后端成败一律 HTTP 200 + `payload.ok`**（契约不变）；前端 `bridge.ts` 据 `ok` 与 `error` 分流到四态，不再有静默崩溃路径。

---

## 7. 测试与验收

**前端（vitest + Vue Test Utils，jsdom 环境，mock `window.AstrBotPluginPage`）**

- 纯逻辑（`collect.ts` / `schema.ts`）：字段收集、哨兵回填/拒绝字面量哨兵、9 节 → 控件映射、body 构造与契约一致。
- 组件：表单渲染全 9 节、增删卡片、敏感字段占位、四态切换（loading/error/empty/restarting）、错误类型 → 文案映射、错误边界兜底不白屏。
- bridge mock：`apiGet` 返回 `{ok:false,unauthorized}` 时渲染"未登录"错误态而非崩溃（根因 B 回归锁定）。

**后端（Python）**

- `_has_identity` 用 `g.username` 的有/无两路径；三端点在无身份时回 `unauthorized`、有身份时正常。
- Quart 兼容用法审计结论对应的断言。

**验收标准**

1. 真实 AstrBot ≥ v4.24.2 Dashboard 打开设置页**能加载配置**（白屏消失）。
2. 9 个配置节均可在页面编辑并保存；保存触发后端重载，期间状态区提示"正在重载"，就绪后恢复。
3. 断网 / 未登录 / bridge 缺失分别渲染**可见且不同**的错误态，**均不白屏**。
4. `npm run build` 产物与 `pages/settings/` 入库一致（CI 校验通过）；vitest 与后端测试全绿。

---

## 8. 安全与隐私（红线，重写后必须全部保持）

- **凭证不外泄**：password / value 明文与 env 值绝不下发、不回显、不入产物；`redact_config` 脱敏契约不变。
- **哨兵回填 + 凭证重定向**：改 `base_url` 需重填密码（`credential_redirect`）等后端校验不变；前端如实呈现该错误。
- **顶层键白名单 / `_strip_meta`**：后端落盘白名单不变；前端补全字段不得引入后端未知的顶层键。
- **身份兜底仍在**：`_has_identity` 是网关鉴权之外的最后防线，修正取值方式但**保留该防线**（读任何配置/secret 前判定）。
- **XSS**：Vue 默认转义 + 禁 `v-html`。
- **沙箱 / CSP 合规**：相对路径（asset_token 重写）、无外部 CDN、不碰 `localStorage`/`cookie`/同源 `fetch`（一切走 bridge）。
- **产物入库无敏感信息**：构建产物不含任何密钥/配置值。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| null-origin 沙箱（无 `allow-same-origin`）令库踩雷 | 选 Reka UI（headless，不碰持久化/CDN）；状态只存内存;网络只走 bridge |
| `no-store` 令产物每次全量重下 | headless 方案产物小（~60–95 KB gzip）；Vite 单文件内联、关 code-split |
| 构建产物与源码漂移 | CI `npm ci && build` 后校验 `pages/settings/` 无 diff |
| Vite 配置不当致产物白屏（绝对路径 / 外链 chunk / 字体 CDN） | `base:'./'` + 关 code-split + 图标内联 SVG + 无外部字体，实现阶段以 DevTools Network 逐资源核实 200 且返回 JS |
| Quart 兼容层其他用法在新框架失效 | §5.2 全面审计 + 后端测试 |
| 版本装到过低环境仍不可用 | metadata.yaml/README 抬到 `>=4.24.2`；bridge 缺失渲染显式错误态 |

---

## 10. 迁移与清理

- `metadata.yaml:7` `astrbot_version` → `>=4.24.2`。
- `README.md`：修正 `:15` 与 `:100` 的版本矛盾，统一"设置页需 AstrBot ≥ v4.24.2"；更新设置页说明（9 节可视化编辑）。
- 删除旧手写 `pages/settings/{app.js, settings.js, status.js, style.css, index.html}`，由 Vite 产物取代。
- `main.py:100-103` 的 `hasattr` 护栏：保留作为 stub 护栏，但注释更新——不再承担"版本判断"暗示（版本由 metadata 声明保证）。

---

## 11. 开放问题（待复核 / 用户确认）

- `group_bindings` 是否需要在设置页**只读展示**（当前默认：完全不纳入）。
- `jsonify` 兼容层可靠性需在实现首步以最小验证确认，若不可靠则统一切 `json_response`（影响三个 handler 的返回构造）。
