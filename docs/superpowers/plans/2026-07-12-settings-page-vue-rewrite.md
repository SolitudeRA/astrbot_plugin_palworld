# 设置页 Vue3 重写 + 白屏根因修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复设置页整页白屏(后端取用户名方式错误 + 前端漏查 `r.ok`),并把前端重写为 Vue3 + Reka UI,补全全部 9 个配置节、加错误边界与四态、美化到与 Dashboard 协调。

**Architecture:** 后端一处鉴权修复即可消白屏(实现顺序最先做);前端在独立 `frontend/` 工程用 Vite 构建单文件产物入 `pages/settings/`,经 AstrBot bridge 与后端通信。逻辑(bridge/schema/collect)与 UI(组件)分层,数据驱动渲染 9 节配置。

**Tech Stack:** Python(后端,冻结 `config_view.py` 契约)；Vue 3.5 + reka-ui 2.10(headless)+ Vite 8 + vitest 4 + @vue/test-utils + TypeScript + jsdom。

**关联 spec:** `docs/superpowers/specs/2026-07-12-settings-page-vue-rewrite-design.md`

## Global Constraints

每个任务的要求都隐含包含本节（值逐字取自 spec）：

- **平台版本**：AstrBot `>=4.24.1`（插件详情页可用门槛）。`metadata.yaml`/README 据此。
- **产物硬约束（CI 红线）**：`pages/settings/assets/` 只有 **1 个 `.js` + 1 个 `.css`**，产物内**无静态跨-chunk import、无动态 `import()`**（AstrBot 的 import 重写正则要求 `from` 两侧有空白，压缩产物 `}from"./` 不被追加 asset_token → 401 白屏；asset_token TTL=60s，延迟 `import()` 必 401）。
- **资源引用**：一律相对路径（交 asset_token 重写），无外部 CDN、无外部字体。
- **沙箱**：iframe 无 `allow-same-origin` → 不碰 `localStorage`/`cookie`/同源 `fetch`，**一切网络走 bridge**。
- **后端契约冻结**：`palchronicle/config.py`、`palchronicle/presentation/config_view.py` 的脱敏/校验/哨兵/白名单/`_strip_meta` 一律不改。
- **安全红线**：password/value 明文不回显不预填、拒绝字面量哨兵 `__unchanged__`；`detail` 只白名单取 `path`；禁 `v-html`；仅 SFC 预编译渲染函数。
- **collect 纪律**：产出 body **完全不含 `group_bindings` 键**；顶层键 ⊆ 后端 `_TOP_KEYS`（9 节）；数值字段产出 `number`、布尔字段产出 `boolean`（禁字符串）。
- **可复现构建**：`frontend/package-lock.json` 入 git、依赖钉版本、`.nvmrc` 统一 Node；`pages/settings/**` 产物 `.gitattributes` 强制 LF。
- **git 提交**：不出现任何 AI 署名 / "Claude" / 🤖（正文与尾行均不得）。
- **Python 工具**：`ruff`（py311, line 120）+ `mypy`（`files=["palchronicle"]`，前端与 `main.py` 外的脚本不纳入）；测试 `*_test.py`、`asyncio_mode=auto`。

## 跨任务共享接口（锁定命名与类型，实现时严格一致）

```ts
// bridge.ts —— 唯一碰 window.AstrBotPluginPage 的出口
export async function ready(): Promise<void>
export async function apiGet<T = unknown>(endpoint: string): Promise<T>          // GET；内部查 r.ok
export async function apiPost<T = unknown>(endpoint: string, body?: unknown): Promise<T>
// errors.ts
export class BridgeMissing extends Error {}      // window.AstrBotPluginPage 不存在
export class Unauthorized extends Error {}        // 业务 ok:false && error==='unauthorized'
export class BusinessError extends Error { code: string; path?: string }  // 其余业务 ok:false
export class RequestFailed extends Error {}       // transport reject（网络/非2xx/bridge 缺失调用）

// schema.ts —— 9 节字段元数据（真源对齐 _conf_schema.json）
export type FieldType = 'enum' | 'int' | 'float' | 'bool' | 'string'
export interface FieldSpec { key: string; type: FieldType; label: string; options?: string[]; default: unknown }
export interface ObjectSection { key: string; title: string; fields: FieldSpec[] }   // 7 个 object 节
export const OBJECT_SECTIONS: ObjectSection[]        // routing/polling/world/bases/privacy/history/features
export const SERVER_FIELDS: FieldSpec[]              // servers 卡片字段
export const HEADER_FIELDS: FieldSpec[]              // custom_headers 卡片字段

// collect.ts
export const SENTINEL = '__unchanged__'
export interface RedactedConfig { [section: string]: unknown }   // config/get 返回的 config
export function collectBody(state: SettingsState): Record<string, unknown>   // 产出 config/save 的 body
```

---

## 阶段 0 —— 后端止血（最先做；单独完成即消白屏）

### Task 1: 后端鉴权修复（`_has_identity` 改用 `g.username`）+ 身份测试

**Files:**
- Modify: `main.py`（`_has_identity` 于 `main.py:178-184`，新增 `_current_username`）
- Test: `tests/unit/main_identity_test.py`（新建；此前零覆盖）

**Interfaces:**
- Produces: `PalChronicle._current_username() -> str | None`（可注入/可 monkeypatch 的取用户名单点）；`PalChronicle._has_identity() -> bool`（三端点 handler 沿用）。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/main_identity_test.py`。用一个假的 `quart` 模块注入 `g`（测试环境未装 quart，`main.py` 内延迟 `from quart import ...`），避免真依赖：

```python
"""根因 A 回归：用户名只在 quart g 上；_has_identity 据此，三端点无身份回 unauthorized。"""
import sys
import types


def _install_fake_quart(username):
    """装一个最小 quart 假模块：g（可选 username）、jsonify（透传 payload）、request（有 get_json，无 username）。"""
    q = types.ModuleType("quart")

    class _G:
        pass

    g = _G()
    if username is not None:
        g.username = username
    q.g = g
    q.jsonify = lambda payload: payload  # 薄壳测试只关心 payload 内容

    class _Req:
        # 关键：request 上没有 username（印证根因 A：读 request.username 恒 None）
        async def get_json(self, silent=False):
            return {}

    q.request = _Req()
    sys.modules["quart"] = q
    return q


def _raw():
    return {
        "servers": [], "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {}, "features": {},
    }


class _FakeContext:
    def register_web_api(self, *a, **k):
        pass


def test_current_username_reads_g_not_request():
    _install_fake_quart("admin")
    import main as main_mod
    assert main_mod.PalChronicle._current_username() == "admin"


def test_has_identity_true_when_g_has_username():
    _install_fake_quart("admin")
    import main as main_mod
    assert main_mod.PalChronicle._has_identity() is True


def test_has_identity_false_when_g_missing_username():
    _install_fake_quart(None)
    import main as main_mod
    assert main_mod.PalChronicle._has_identity() is False


async def test_config_get_returns_unauthorized_without_identity():
    _install_fake_quart(None)
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    payload = await plugin._web_config_get()
    assert payload == {"ok": False, "error": "unauthorized", "detail": {}}


async def test_config_get_ok_with_identity():
    _install_fake_quart("admin")
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    payload = await plugin._web_config_get()
    assert payload.get("ok") is True and "config" in payload
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/unit/main_identity_test.py -v`
Expected: FAIL —— `test_current_username_reads_g_not_request` 报 `AttributeError: type object 'PalChronicle' has no attribute '_current_username'`；`test_config_get_returns_unauthorized_without_identity` 会因当前 `_has_identity` 读 `request.username`（假 request 无该属性→None→已 False）可能"意外通过"，但 `_current_username` 相关用例必失败。

- [ ] **Step 3: 实现——`main.py` 新增 `_current_username`，改 `_has_identity`**

把 `main.py:178-184`：

```python
    @staticmethod
    def _has_identity() -> bool:
        # 身份兜底（规格 §5.3c）：网关鉴权之外的最后防线。禁用/卸载后端点仍可达，
        # 拿不到 Dashboard 登录用户即拒。在读取任何配置/secret 之前判定，
        # 绝不记录、绝不 str(exc)、绝不回显 request 内容。
        from quart import request
        return bool(getattr(request, "username", None))
```

改为：

```python
    @staticmethod
    def _current_username() -> str | None:
        # 用户名只绑在 Quart g 上（跨 v4.24.x 纯 Quart ~ v4.26.x 兼容层全区间），
        # 从不在 request 上（根因 A）。下沉为单点便于单测注入。
        from quart import g
        try:
            return getattr(g, "username", None)
        except RuntimeError:  # 无 app context（正常 register_web_api 链路不可达）
            return None

    @staticmethod
    def _has_identity() -> bool:
        # 身份兜底（规格 §5.3c）：网关鉴权之外的最后防线。禁用/卸载后端点仍可达，
        # 拿不到 Dashboard 登录用户即拒。在读取任何配置/secret 之前判定，
        # 绝不记录、绝不 str(exc)、绝不回显 request 内容。
        return bool(PalChronicle._current_username())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/unit/main_identity_test.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 回归 + lint + 提交**

Run: `python -m pytest tests/ -q && ruff check . && mypy`
Expected: 全绿。

```bash
git add main.py tests/unit/main_identity_test.py
git commit -m "fix(web): _has_identity 改用 g.username 修复设置页白屏根因 + 新增身份门测试"
```

> 完成本任务后，即使前端仍是旧手写页，`config/get` 恢复 `ok:true`，**白屏消失**。后续前端重写是增强，不阻塞止血。

---

## 阶段 1 —— 前端脚手架

### Task 2: `frontend/` 工程与可复现构建 + CI 产物断言

**Files:**
- Create: `frontend/package.json`、`frontend/package-lock.json`（`npm install` 生成后入库）、`frontend/.nvmrc`、`frontend/vite.config.ts`、`frontend/vitest.config.ts`、`frontend/vitest.setup.ts`、`frontend/tsconfig.json`、`frontend/index.html`、`frontend/src/main.ts`（临时 hello）、`frontend/src/global.d.ts`、`frontend/scripts/verify-bundle.mjs`
- Modify: `.gitignore`（加 `frontend/node_modules`）、新建 `.gitattributes`

**Interfaces:**
- Produces: `npm run build`（→ `../pages/settings/` 单文件产物）、`npm run test:run`、`npm run verify:bundle` 三个可被 CI 调用的脚本。

- [ ] **Step 1: 写工程骨架文件**

`frontend/package.json`（版本钉死，取自工具链核实 2026-07-12 latest）：

```json
{
  "name": "palworld-settings-page",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "typecheck": "vue-tsc --noEmit",
    "test": "vitest",
    "test:run": "vitest run",
    "verify:bundle": "node scripts/verify-bundle.mjs"
  },
  "dependencies": {
    "vue": "3.5.39",
    "reka-ui": "2.10.1"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "6.0.7",
    "@vue/test-utils": "2.4.11",
    "jsdom": "29.1.1",
    "typescript": "5.9.2",
    "vite": "8.1.4",
    "vitest": "4.1.10",
    "vue-tsc": "2.2.10"
  }
}
```

> 版本注记：`vue`/`reka-ui`/`vite`/`vitest` 用当前 latest；**`typescript` 保守钉 `5.9.2` + `vue-tsc 2.2.10`**（TS7.0 是 tsgo 原生移植大版本，与 vue-tsc 组合成熟度未验证；5.9 线稳）。若 Step 5 冒烟发现 vite8/vitest4 与 vue-tsc 2.2 有冲突，回退 `vite ~7.1` + `vitest ~3.2`。`build` 不串 `vue-tsc`（类型检查独立 `npm run typecheck`，避免 tsgo 边缘错阻塞构建）。

`frontend/.nvmrc`：
```
22
```

`frontend/vite.config.ts`：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 产物硬约束：单 JS + 单 CSS，零跨-chunk import、零 import()
export default defineConfig({
  plugins: [vue()],
  base: './', // asset_token 重写要求相对路径
  build: {
    outDir: fileURLToPath(new URL('../pages/settings', import.meta.url)),
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true, // 内联动态 import → 零 import()/零异步 chunk
        manualChunks: undefined,
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/index.js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
})
```

`frontend/vitest.config.ts`：

```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.ts'],
    setupFiles: ['./vitest.setup.ts'],
    restoreMocks: true,
  },
})
```

`frontend/vitest.setup.ts`：

```ts
import { vi } from 'vitest'

// 全局兜底 bridge；单测可在 beforeEach 覆盖 window.AstrBotPluginPage
vi.stubGlobal('AstrBotPluginPage', {
  ready: () => Promise.resolve(),
  apiGet: vi.fn().mockResolvedValue({}),
  apiPost: vi.fn().mockResolvedValue({ ok: true }),
})
```

`frontend/tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "jsx": "preserve",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vitest/globals", "@vue/test-utils"],
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts", "vitest.config.ts"]
}
```

`frontend/src/global.d.ts`：

```ts
export {}
declare global {
  interface AstrBotBridge {
    ready(): Promise<void>
    apiGet(path: string): Promise<any>
    apiPost(path: string, body?: unknown): Promise<any>
  }
  interface Window { AstrBotPluginPage?: AstrBotBridge }
}
```

`frontend/index.html`：

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PalChronicle 设置</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="./src/main.ts"></script>
  </body>
</html>
```

`frontend/src/main.ts`（临时 hello，T11 再替换为真入口）：

```ts
import { createApp, h } from 'vue'
createApp({ render: () => h('div', 'PalChronicle 设置') }).mount('#app')
```

`frontend/scripts/verify-bundle.mjs`（跨平台，Windows CI 友好）：

```js
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const dir = 'pages/settings/assets' // 相对仓库根运行
const files = readdirSync(dir)
const js = files.filter((f) => f.endsWith('.js'))
const css = files.filter((f) => f.endsWith('.css'))
const fail = (m) => { console.error('FAIL:', m); process.exit(1) }

if (js.length !== 1) fail(`expected exactly 1 .js, found ${js.length}: ${js.join(', ')}`)
if (css.length > 1) fail(`expected at most 1 .css, found ${css.length}: ${css.join(', ')}`)

const src = readFileSync(join(dir, js[0]), 'utf8')
const banned = ['}from"./', "}from'./", '*from"./', ' from"./', 'import(']
for (const needle of banned) {
  if (src.includes(needle)) fail(`bundle ${js[0]} contains banned token: ${JSON.stringify(needle)}`)
}
console.log(`OK: single-file bundle verified -> ${join(dir, js[0])}`)
```

> `verify-bundle.mjs` 从仓库根运行（`node frontend/scripts/verify-bundle.mjs` 时 `dir` 用 `pages/settings/assets`）。CI 里在仓库根执行；本地在 `frontend/` 内跑则改用 `npm run verify:bundle` 前 `cd ..`，或在脚本里用相对 `../pages/...`——统一约定：**CI/脚本从仓库根调用**，见 Task 15。

新建 `.gitattributes`（追加，不覆盖已有行）：

```
pages/settings/** text eol=lf
```

`.gitignore` 追加：

```
frontend/node_modules/
```

- [ ] **Step 2: 安装依赖并生成 lockfile**

Run: `cd frontend && npm install`
Expected: 生成 `node_modules/` 与 `package-lock.json`；无 peer 冲突致命错。

- [ ] **Step 3: 冒烟——构建 + 产物断言**

Run（在仓库根）：`cd frontend && npm run build && cd .. && node frontend/scripts/verify-bundle.mjs`
Expected: `pages/settings/assets/` 生成 `index.js`（hello 阶段无样式，css 为 0 个）。`verify-bundle.mjs` 的 js 断言严格为 1、css 断言为"至多 1 个"（`> 1` 才失败），故此步 0 css 通过。真实样式在 T12 引入后产物为 1 js + 1 css。Expected 输出：`OK: single-file bundle verified`。

- [ ] **Step 4: 冒烟——vitest 与 typecheck**

Run: `cd frontend && npm run test:run && npm run typecheck`
Expected: vitest 无测试文件时报 "no test files"（正常）；`vue-tsc --noEmit` 无类型错。若 `vue-tsc 2.2.10` 与 vite8/vitest4 冲突，按 Step 1 版本注记回退并重跑。

- [ ] **Step 5: 提交**

```bash
git add frontend/ .gitattributes .gitignore
git commit -m "chore(frontend): Vite+Vue3+vitest 脚手架与单文件产物硬约束 + CI 产物断言脚本"
```

---

## 阶段 2 —— 前端纯 TS 逻辑（bridge / schema / collect）

### Task 3: `errors.ts` + `bridge.ts`（两层错误模型 + 根因 B 回归锚点）

**Files:**
- Create: `frontend/src/lib/errors.ts`、`frontend/src/lib/bridge.ts`
- Test: `frontend/src/lib/bridge.test.ts`

**Interfaces:**
- Produces: 见"跨任务共享接口"的 bridge.ts / errors.ts 块。

- [ ] **Step 1: 写失败测试**

`frontend/src/lib/bridge.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiGet, apiPost } from './bridge'
import { BridgeMissing, Unauthorized, BusinessError, RequestFailed } from './errors'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve(),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    ...impl,
  }
}

describe('bridge', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('apiGet 正常返回业务包', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, config: { servers: [] } }) })
    const r = await apiGet<{ ok: boolean; config: unknown }>('config/get')
    expect(r.config).toEqual({ servers: [] })
  })

  it('apiGet ok:false unauthorized → Unauthorized（根因 B 回归锚点）', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: false, error: 'unauthorized', detail: {} }) })
    await expect(apiGet('config/get')).rejects.toBeInstanceOf(Unauthorized)
  })

  it('apiPost ok:false 其他 → BusinessError 携带 code/path', async () => {
    setBridge({ apiPost: vi.fn().mockResolvedValue({ ok: false, error: 'credential_redirect', detail: { path: 'servers[0].password' } }) })
    await expect(apiPost('config/save', {})).rejects.toMatchObject({ code: 'credential_redirect', path: 'servers[0].password' })
  })

  it('transport reject → RequestFailed', async () => {
    setBridge({ apiGet: vi.fn().mockRejectedValue(new Error('network')) })
    await expect(apiGet('status/overview')).rejects.toBeInstanceOf(RequestFailed)
  })

  it('bridge 缺失 → BridgeMissing', async () => {
    await expect(apiGet('config/get')).rejects.toBeInstanceOf(BridgeMissing)
  })

  it('detail 非对象/无 path → BusinessError.path 为 undefined（detail 白名单）', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: false, error: 'invalid_shape', detail: null }) })
    await expect(apiGet('config/get')).rejects.toMatchObject({ code: 'invalid_shape', path: undefined })
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/lib/bridge.test.ts`
Expected: FAIL（`Cannot find module './bridge'`）。

- [ ] **Step 3: 实现**

`frontend/src/lib/errors.ts`：

```ts
export class BridgeMissing extends Error {
  constructor() { super('AstrBotPluginPage bridge 不存在'); this.name = 'BridgeMissing' }
}
export class Unauthorized extends Error {
  constructor() { super('未登录或登录已过期'); this.name = 'Unauthorized' }
}
export class BusinessError extends Error {
  code: string; path?: string
  constructor(code: string, path?: string) {
    super(`业务错误: ${code}`); this.name = 'BusinessError'; this.code = code; this.path = path
  }
}
export class RequestFailed extends Error {
  constructor(message = '请求失败') { super(message); this.name = 'RequestFailed' }
}
```

`frontend/src/lib/bridge.ts`：

```ts
import { BridgeMissing, Unauthorized, BusinessError, RequestFailed } from './errors'

function getBridge(): AstrBotBridge {
  const b = window.AstrBotPluginPage
  if (!b || typeof b.apiGet !== 'function') throw new BridgeMissing()
  return b
}

// 业务包统一解包：只白名单取 detail.path；ok:false 分流为 Unauthorized/BusinessError。
function unwrap<T>(r: any): T {
  if (r && typeof r === 'object' && r.ok === false) {
    const code = String(r.error ?? 'unknown')
    if (code === 'unauthorized') throw new Unauthorized()
    const path = r.detail && typeof r.detail === 'object' && typeof r.detail.path === 'string'
      ? r.detail.path : undefined
    throw new BusinessError(code, path)
  }
  return r as T
}

export async function ready(): Promise<void> {
  const b = getBridge()
  if (typeof b.ready === 'function') await b.ready()
}

export async function apiGet<T = unknown>(endpoint: string): Promise<T> {
  const b = getBridge()
  let r: any
  try { r = await b.apiGet(endpoint) } catch (e) { throw new RequestFailed((e as Error)?.message) }
  return unwrap<T>(r)
}

export async function apiPost<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
  const b = getBridge()
  let r: any
  try { r = await b.apiPost(endpoint, body) } catch (e) { throw new RequestFailed((e as Error)?.message) }
  return unwrap<T>(r)
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/lib/bridge.test.ts`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/lib/errors.ts frontend/src/lib/bridge.ts frontend/src/lib/bridge.test.ts
git commit -m "feat(frontend): bridge 单一出口 + 两层错误模型（r.ok 分流治根因 B）"
```

---

### Task 4: `schema.ts`（9 节字段元数据）+ 完整性断言（治 F6）

**Files:**
- Create: `frontend/src/lib/schema.ts`
- Test: `frontend/src/lib/schema.test.ts`

**Interfaces:**
- Produces: `FieldType`、`FieldSpec`（含可选 `secret?: boolean`）、`ObjectSection`、`OBJECT_SECTIONS`、`SERVER_FIELDS`、`HEADER_FIELDS`（见共享接口块）。

- [ ] **Step 1: 写失败测试（以 `_conf_schema.json` 为真源）**

`frontend/src/lib/schema.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS } from './schema'

// vitest root = frontend/；仓库根的 _conf_schema.json 在上一层
const schemaPath = fileURLToPath(new URL('../../../_conf_schema.json', import.meta.url))
const RAW = JSON.parse(readFileSync(schemaPath, 'utf8'))

function keysOfObject(section: string): string[] {
  return Object.keys(RAW[section].items).sort()
}
function keysOfTemplateList(section: string, tpl: string): string[] {
  return Object.keys(RAW[section].templates[tpl].items).sort()
}

describe('schema 完整性（对齐 _conf_schema.json，缺一即失败）', () => {
  it('7 个 object 节字段集完全一致', () => {
    for (const sec of OBJECT_SECTIONS) {
      const declared = sec.fields.map((f) => f.key).sort()
      expect(declared, `节 ${sec.key} 字段不齐`).toEqual(keysOfObject(sec.key))
    }
  })
  it('SERVER_FIELDS 覆盖 servers 模板全字段', () => {
    expect(SERVER_FIELDS.map((f) => f.key).sort()).toEqual(keysOfTemplateList('servers', 'server'))
  })
  it('HEADER_FIELDS 覆盖 custom_headers 模板全字段', () => {
    expect(HEADER_FIELDS.map((f) => f.key).sort()).toEqual(keysOfTemplateList('custom_headers', 'header'))
  })
  it('OBJECT_SECTIONS 恰为 7 个 object 节（不含 servers/custom_headers/group_bindings）', () => {
    expect(OBJECT_SECTIONS.map((s) => s.key)).toEqual(
      ['routing', 'polling', 'world', 'bases', 'privacy', 'history', 'features'])
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/lib/schema.test.ts`
Expected: FAIL（`Cannot find module './schema'`）。

- [ ] **Step 3: 实现——完整字段表（逐字段对齐 `_conf_schema.json`）**

`frontend/src/lib/schema.ts`：

```ts
export type FieldType = 'enum' | 'int' | 'float' | 'bool' | 'string'

export interface FieldSpec {
  key: string
  type: FieldType
  label: string
  default: unknown
  options?: string[]
  secret?: boolean // password / value：不预填、走哨兵
}
export interface ObjectSection { key: string; title: string; fields: FieldSpec[] }

export const SERVER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '' },
  { key: 'enabled', type: 'bool', label: '启用', default: true },
  { key: 'base_url', type: 'string', label: 'REST 地址', default: 'http://127.0.0.1:8212' },
  { key: 'username', type: 'string', label: 'Basic 用户名', default: 'admin' },
  { key: 'password', type: 'string', label: '密码', default: '', secret: true },
  { key: 'password_env', type: 'string', label: '密码环境变量名', default: '' },
  { key: 'timeout', type: 'int', label: '超时(秒)', default: 10 },
  { key: 'verify_tls', type: 'bool', label: '校验 TLS', default: true },
  { key: 'timezone', type: 'string', label: '时区(留空用全局)', default: '' },
]

export const HEADER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: 'Header 名', default: '' },
  { key: 'value', type: 'string', label: 'Header 值', default: '', secret: true },
  { key: 'value_env', type: 'string', label: '值环境变量名', default: '' },
  { key: 'servers', type: 'string', label: '限定服务器(逗号分隔;留空=全部)', default: '' },
]

export const OBJECT_SECTIONS: ObjectSection[] = [
  { key: 'routing', title: '路由与访问控制', fields: [
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'] },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '' },
  ]},
  { key: 'polling', title: '轮询间隔', fields: [
    { key: 'metrics_seconds', type: 'int', label: 'metrics(秒)', default: 30 },
    { key: 'players_seconds', type: 'int', label: 'players(秒)', default: 30 },
    { key: 'info_seconds', type: 'int', label: 'info(秒)', default: 600 },
    { key: 'settings_seconds', type: 'int', label: 'settings(秒)', default: 1800 },
    { key: 'game_data_seconds', type: 'int', label: 'game-data(秒)', default: 120 },
    { key: 'jitter_ratio', type: 'float', label: '抖动比例', default: 0.10 },
    { key: 'max_concurrency', type: 'int', label: '并发上限', default: 6 },
  ]},
  { key: 'world', title: '世界与展示', fields: [
    { key: 'timezone', type: 'string', label: '全局时区', default: 'Asia/Tokyo' },
    { key: 'locale', type: 'enum', label: '文案语言', default: 'zh-CN', options: ['zh-CN'] },
    { key: 'fps_smooth', type: 'int', label: 'FPS 流畅阈值', default: 50 },
    { key: 'fps_moderate', type: 'int', label: 'FPS 一般阈值', default: 35 },
    { key: 'fps_laggy', type: 'int', label: 'FPS 卡顿阈值', default: 20 },
  ]},
  { key: 'bases', title: '据点推导', fields: [
    { key: 'enabled', type: 'bool', label: '启用据点推导', default: true },
    { key: 'assignment_radius', type: 'int', label: '归属半径', default: 5000 },
    { key: 'ambiguity_ratio', type: 'float', label: '模糊比阈值', default: 0.20 },
    { key: 'confirmation_samples', type: 'int', label: '确认次数', default: 3 },
    { key: 'position_grid_size', type: 'int', label: '坐标网格', default: 2000 },
    { key: 'z_weight', type: 'float', label: 'Z 轴权重', default: 0.5 },
  ]},
  { key: 'privacy', title: '隐私与脱敏', fields: [
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'] },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60 },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120 },
    { key: 'uncertain_timeout', type: 'int', label: 'uncertain 超时(秒)', default: 900 },
  ]},
  { key: 'history', title: '保留清理天数', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标天数', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合天数', default: 90 },
    { key: 'session_days', type: 'int', label: '会话天数', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察天数', default: 180 },
  ]},
  { key: 'features', title: '功能分组开关', fields: [
    { key: 'report', type: 'bool', label: '日报/在线统计', default: true },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false },
  ]},
]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/lib/schema.test.ts`
Expected: PASS（4 passed）。若失败说明某节字段与 `_conf_schema.json` 不一致——按报错补齐/更正 schema.ts（这正是本测试的价值：防手抄漏字段导致保存丢配置）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/lib/schema.ts frontend/src/lib/schema.test.ts
git commit -m "feat(frontend): 9 节字段元数据表 + 以 _conf_schema.json 为真源的完整性断言"
```

---

### Task 5: `collect.ts`（逐字段收集 + 类型正确 + 哨兵 + 不含 group_bindings，治 F1/F3）

**Files:**
- Create: `frontend/src/lib/collect.ts`
- Test: `frontend/src/lib/collect.test.ts`

**Interfaces:**
- Consumes: `OBJECT_SECTIONS`（schema.ts）。
- Produces: `SENTINEL`、`SettingsState`、`collectSecret(value, isNew)`、`collectBody(state)`。

```ts
export interface SettingsState {
  servers: Record<string, unknown>[]         // 每行含 __row_id 与 SERVER_FIELDS 各值（password 为用户输入串）
  custom_headers: Record<string, unknown>[]  // 每行含 __row_id 与 HEADER_FIELDS 各值
  sections: Record<string, Record<string, unknown>>  // objectSection.key -> { fieldKey: value }
}
```

- [ ] **Step 1: 写失败测试**

`frontend/src/lib/collect.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { collectBody, collectSecret, SENTINEL, type SettingsState } from './collect'

const baseState = (): SettingsState => ({
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
  sections: {
    routing: { access_mode: 'restricted', default_server: '' },
    polling: { metrics_seconds: 30, players_seconds: 30, info_seconds: 600, settings_seconds: 1800,
      game_data_seconds: 120, jitter_ratio: 0.1, max_concurrency: 6 },
    world: { timezone: 'Asia/Tokyo', locale: 'zh-CN', fps_smooth: 50, fps_moderate: 35, fps_laggy: 20 },
    bases: { enabled: true, assignment_radius: 5000, ambiguity_ratio: 0.2, confirmation_samples: 3,
      position_grid_size: 2000, z_weight: 0.5 },
    privacy: { mode: 'balanced', public_exact_ping: false, public_positions: false,
      ping_good_ms: 60, ping_ok_ms: 120, uncertain_timeout: 900 },
    history: { raw_metrics_days: 7, aggregate_days: 90, session_days: 365, observation_days: 180 },
    features: { report: true, events: true, guilds_bases: false },
  },
})

const TOP_KEYS = ['servers', 'routing', 'group_bindings', 'custom_headers',
  'polling', 'world', 'bases', 'privacy', 'history', 'features']

describe('collectBody', () => {
  it('数值字段产出 number（非字符串）', () => {
    const st = baseState(); st.sections.polling.metrics_seconds = '45' // 模拟原生 input 给了字符串
    const body = collectBody(st) as any
    expect(typeof body.polling.metrics_seconds).toBe('number')
    expect(body.polling.metrics_seconds).toBe(45)
    expect(typeof body.polling.jitter_ratio).toBe('number')
  })
  it('布尔字段产出 boolean（治 bool("false")===true 陷阱）', () => {
    const body = collectBody(baseState()) as any
    expect(typeof body.features.report).toBe('boolean')
    expect(body.features.guilds_bases).toBe(false)
  })
  it('body 完全不含 group_bindings 键（后端缺键保留旧值）', () => {
    expect('group_bindings' in (collectBody(baseState()) as any)).toBe(false)
  })
  it('顶层键 ⊆ 后端 _TOP_KEYS', () => {
    for (const k of Object.keys(collectBody(baseState()))) expect(TOP_KEYS).toContain(k)
  })
  it('server 行保留 __row_id；新建行(无 id)不注入哨兵到空密码', () => {
    const st = baseState(); st.servers.push({ __row_id: '', name: 'b', enabled: true, base_url: '',
      username: 'admin', password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' })
    const body = collectBody(st) as any
    expect(body.servers[0].__row_id).toBe('srv-0')
    expect(body.servers[1].__row_id).toBe(null)
    expect(body.servers[1].password).toBe('') // 新建行空密码 = 无明文
  })
})

describe('collectSecret', () => {
  it('新建行留空 = 空串', () => { expect(collectSecret('', true)).toBe('') })
  it('既有行留空 = 哨兵', () => { expect(collectSecret('', false)).toBe(SENTINEL) })
  it('有值 = 原值', () => { expect(collectSecret('pw', false)).toBe('pw') })
  it('字面量哨兵输入被拒绝', () => { expect(() => collectSecret(SENTINEL, false)).toThrow() })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/lib/collect.test.ts`
Expected: FAIL（`Cannot find module './collect'`）。

- [ ] **Step 3: 实现**

`frontend/src/lib/collect.ts`：

```ts
import { OBJECT_SECTIONS, type FieldType } from './schema'

export const SENTINEL = '__unchanged__'

export interface SettingsState {
  servers: Record<string, unknown>[]
  custom_headers: Record<string, unknown>[]
  sections: Record<string, Record<string, unknown>>
}

const str = (v: unknown): string => (v == null ? '' : String(v))

export function collectSecret(value: unknown, isNew: boolean): string {
  const v = str(value)
  if (v === SENTINEL) throw new Error('不能使用保留字 __unchanged__')
  if (v !== '') return v
  return isNew ? '' : SENTINEL
}

function coerce(type: FieldType, v: unknown): unknown {
  if (type === 'int' || type === 'float') return typeof v === 'number' ? v : Number(v)
  if (type === 'bool') return v === true // 严格：只有 boolean true 为真，杜绝 'false'→true
  return str(v) // string / enum
}

function collectServer(row: Record<string, unknown>): Record<string, unknown> {
  const rowId = (row.__row_id as string) || null
  const isNew = !rowId
  return {
    __row_id: rowId,
    name: str(row.name),
    enabled: row.enabled === true,
    base_url: str(row.base_url),
    username: str(row.username),
    password: collectSecret(row.password, isNew),
    password_env: str(row.password_env),
    timeout: typeof row.timeout === 'number' ? row.timeout : Number(row.timeout),
    verify_tls: row.verify_tls === true,
    timezone: str(row.timezone),
  }
}

function collectHeader(row: Record<string, unknown>): Record<string, unknown> {
  const rowId = (row.__row_id as string) || null
  const isNew = !rowId
  return {
    __row_id: rowId,
    name: str(row.name),
    value: collectSecret(row.value, isNew),
    value_env: str(row.value_env),
    servers: str(row.servers),
  }
}

export function collectBody(state: SettingsState): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  body.servers = state.servers.map(collectServer)
  body.custom_headers = state.custom_headers.map(collectHeader)
  for (const section of OBJECT_SECTIONS) {
    const vals = state.sections[section.key] ?? {}
    const out: Record<string, unknown> = {}
    for (const f of section.fields) out[f.key] = coerce(f.type, vals[f.key])
    body[section.key] = out
  }
  // 绝不含 group_bindings：后端缺键保留旧值，避免清空预设群授权（spec §4.3）
  return body
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/lib/collect.test.ts`
Expected: PASS（9 passed）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/lib/collect.ts frontend/src/lib/collect.test.ts
git commit -m "feat(frontend): collect 逐字段收集（类型正确/哨兵/不含 group_bindings，治 F1/F3）"
```

---

## 阶段 3 —— 前端组件

> **reka-ui DOM 注记（贯穿 T6–T11）**：以下测试选择器基于 ARIA 规范（Switch→`role="switch"`+`aria-checked`）。reka-ui 2.10.1 的确切渲染属性以实测为准；若选择器不命中，用 `wrapper.html()` 快照核对后调整选择器，**不改被测行为**。Select 在 jsdom 下打开下拉依赖 pointer 事件，交互测试降级为"渲染出 options / modelValue 正确反映"即可。

### Task 6: `Field.vue`（数据驱动字段组件，分派 enum/int/float/bool/string）

**Files:**
- Create: `frontend/src/components/Field.vue`
- Test: `frontend/src/components/Field.test.ts`

**Interfaces:**
- Consumes: `FieldSpec`（schema.ts）。
- Produces: `Field`（props `spec: FieldSpec`、`modelValue: unknown`；emit `update:modelValue`）。供 T7 SectionForm 与 T8 cards 复用。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/Field.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Field from './Field.vue'
import type { FieldSpec } from '../lib/schema'

const mountField = (spec: FieldSpec, modelValue: unknown) =>
  mount(Field, { props: { spec, modelValue } })

describe('Field', () => {
  it('string：输入 emit 字符串', async () => {
    const w = mountField({ key: 'name', type: 'string', label: '名称', default: '' }, '')
    await w.get('input[type="text"]').setValue('alpha')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['alpha'])
  })
  it('bool：切换 emit boolean', async () => {
    const w = mountField({ key: 'enabled', type: 'bool', label: '启用', default: true }, false)
    await w.get('[role="switch"]').trigger('click')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([true])
  })
  it('int：输入 emit number', async () => {
    const w = mountField({ key: 'timeout', type: 'int', label: '超时', default: 10 }, 10)
    await w.get('input').setValue('25')
    const last = w.emitted('update:modelValue')?.at(-1)?.[0]
    expect(typeof last).toBe('number')
  })
  it('enum：渲染全部 options', () => {
    const w = mountField({ key: 'mode', type: 'enum', label: '模式', default: 'a', options: ['a', 'b', 'c'] }, 'a')
    expect(w.text()).toContain('模式')
    // 渲染断言：三个 option 值出现在 DOM（不测下拉打开交互）
    for (const opt of ['a', 'b', 'c']) expect(w.html()).toContain(opt)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/Field.test.ts`
Expected: FAIL（`Cannot find module './Field.vue'`）。

- [ ] **Step 3: 实现**

`frontend/src/components/Field.vue`：

```vue
<script setup lang="ts">
import { computed } from 'vue'
import {
  SelectRoot, SelectTrigger, SelectValue, SelectContent, SelectViewport, SelectItem, SelectItemText,
  SwitchRoot, SwitchThumb,
  NumberFieldRoot, NumberFieldInput, NumberFieldDecrement, NumberFieldIncrement,
} from 'reka-ui'
import type { FieldSpec } from '../lib/schema'

const props = defineProps<{ spec: FieldSpec; modelValue: unknown }>()
const emit = defineEmits<{ 'update:modelValue': [v: unknown] }>()
const set = (v: unknown) => emit('update:modelValue', v)

const strVal = computed<string>({ get: () => String(props.modelValue ?? ''), set })
const boolVal = computed<boolean>({ get: () => props.modelValue === true, set })
const numVal = computed<number>({ get: () => Number(props.modelValue ?? 0), set })
</script>

<template>
  <div class="pw-field">
    <label class="pw-field-label">{{ spec.label }}</label>

    <SelectRoot v-if="spec.type === 'enum'" v-model="strVal">
      <SelectTrigger class="pw-select-trigger" :aria-label="spec.key"><SelectValue /></SelectTrigger>
      <SelectContent class="pw-select-content">
        <SelectViewport>
          <SelectItem v-for="opt in spec.options" :key="opt" :value="opt" class="pw-select-item">
            <SelectItemText>{{ opt }}</SelectItemText>
          </SelectItem>
        </SelectViewport>
      </SelectContent>
    </SelectRoot>

    <SwitchRoot v-else-if="spec.type === 'bool'" v-model="boolVal" class="pw-switch">
      <SwitchThumb class="pw-switch-thumb" />
    </SwitchRoot>

    <NumberFieldRoot v-else-if="spec.type === 'int' || spec.type === 'float'" v-model="numVal"
      :step="spec.type === 'float' ? 0.01 : 1" class="pw-number">
      <NumberFieldDecrement class="pw-number-btn">−</NumberFieldDecrement>
      <NumberFieldInput class="pw-number-input" />
      <NumberFieldIncrement class="pw-number-btn">+</NumberFieldIncrement>
    </NumberFieldRoot>

    <input v-else class="pw-input" type="text" v-model.trim="strVal" />
  </div>
</template>
```

> 注记：`SelectRoot` 用无 Portal 版（直接 `SelectContent`），规避 sandbox teleport 落点问题（工具链核实建议）。若 `numVal`/`strVal` 的 `v-model` 在 reka 2.10.1 上需 `defaultValue`/事件名微调，以文档核对。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/Field.test.ts`
Expected: PASS（4 passed；如 reka DOM 属性差异致某断言不命中，按顶部注记调选择器）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/Field.vue frontend/src/components/Field.test.ts
git commit -m "feat(frontend): Field 数据驱动字段组件（enum/int/float/bool/string 分派）"
```

---

### Task 7: `SectionForm.vue`（schema 驱动渲染一个 object 节）

**Files:**
- Create: `frontend/src/components/SectionForm.vue`
- Test: `frontend/src/components/SectionForm.test.ts`

**Interfaces:**
- Consumes: `Field`（T6）、`ObjectSection`（schema.ts）。
- Produces: `SectionForm`（props `section: ObjectSection`、`modelValue: Record<string,unknown>`；emit `update:modelValue` 返回合并后的整节值）。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/SectionForm.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SectionForm from './SectionForm.vue'
import { OBJECT_SECTIONS } from '../lib/schema'

const features = OBJECT_SECTIONS.find((s) => s.key === 'features')!

describe('SectionForm', () => {
  it('渲染节标题与全部字段', () => {
    const w = mount(SectionForm, { props: { section: features, modelValue: { report: true, events: true, guilds_bases: false } } })
    expect(w.text()).toContain('功能分组开关')
    for (const f of features.fields) expect(w.text()).toContain(f.label)
  })
  it('改一个字段 emit 合并后的整节值', async () => {
    const w = mount(SectionForm, { props: { section: features, modelValue: { report: true, events: true, guilds_bases: false } } })
    await w.findAll('[role="switch"]')[2].trigger('click') // guilds_bases
    const emitted = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(emitted).toMatchObject({ report: true, events: true, guilds_bases: true })
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/SectionForm.test.ts`
Expected: FAIL（模块缺失）。

- [ ] **Step 3: 实现**

`frontend/src/components/SectionForm.vue`：

```vue
<script setup lang="ts">
import Field from './Field.vue'
import type { ObjectSection } from '../lib/schema'

const props = defineProps<{ section: ObjectSection; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <section class="pw-section">
    <h3 class="pw-section-title">{{ section.title }}</h3>
    <Field v-for="f in section.fields" :key="f.key" :spec="f"
      :model-value="modelValue[f.key]"
      @update:model-value="(v) => update(f.key, v)" />
  </section>
</template>
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/SectionForm.test.ts`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SectionForm.vue frontend/src/components/SectionForm.test.ts
git commit -m "feat(frontend): SectionForm schema 驱动渲染 object 节"
```

---

### Task 8: `ServerCard.vue` + `HeaderCard.vue`（列表节可增删卡片 + 哨兵敏感字段）

**Files:**
- Create: `frontend/src/components/ServerCard.vue`、`frontend/src/components/HeaderCard.vue`
- Test: `frontend/src/components/ServerCard.test.ts`

**Interfaces:**
- Consumes: `Field`（T6）、`SERVER_FIELDS`/`HEADER_FIELDS`（schema.ts）。
- Produces: `ServerCard` / `HeaderCard`（props `modelValue: Record<string,unknown>`；emit `update:modelValue`、`delete`）。secret 字段（password/value）不预填、占位据 `password_set`/`value_set`。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/ServerCard.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ServerCard from './ServerCard.vue'

const row = () => ({ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
  password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' })

describe('ServerCard', () => {
  it('password 不预填明文，占位显示已设置', () => {
    const w = mount(ServerCard, { props: { modelValue: row() } })
    const pw = w.get('input[type="password"]')
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('删除按钮 emit delete', async () => {
    const w = mount(ServerCard, { props: { modelValue: row() } })
    await w.get('button.pw-danger').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('改名字 emit 合并后的行', async () => {
    const w = mount(ServerCard, { props: { modelValue: row() } })
    await w.get('input[type="text"]').setValue('beta')
    const emitted = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(emitted.name).toBe('beta')
    expect(emitted.__row_id).toBe('srv-0') // __row_id 保留
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/ServerCard.test.ts`
Expected: FAIL（模块缺失）。

- [ ] **Step 3: 实现**

`frontend/src/components/ServerCard.vue`：

```vue
<script setup lang="ts">
import Field from './Field.vue'
import { SERVER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>]; delete: [] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <div class="pw-card">
    <template v-for="f in SERVER_FIELDS" :key="f.key">
      <div v-if="f.secret" class="pw-field">
        <label class="pw-field-label">{{ f.label }}</label>
        <input class="pw-input" type="password"
          :placeholder="modelValue.password_set ? '已设置（留空保持不变）' : '未设置'"
          :value="String(modelValue[f.key] ?? '')"
          @input="update(f.key, ($event.target as HTMLInputElement).value)" />
      </div>
      <Field v-else :spec="f" :model-value="modelValue[f.key]"
        @update:model-value="(v) => update(f.key, v)" />
    </template>
    <button class="pw-danger" @click="emit('delete')">删除</button>
  </div>
</template>
```

`frontend/src/components/HeaderCard.vue`（同构，用 `HEADER_FIELDS` 与 `value_set`）：

```vue
<script setup lang="ts">
import Field from './Field.vue'
import { HEADER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>]; delete: [] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <div class="pw-card">
    <template v-for="f in HEADER_FIELDS" :key="f.key">
      <div v-if="f.secret" class="pw-field">
        <label class="pw-field-label">{{ f.label }}</label>
        <input class="pw-input" type="password"
          :placeholder="modelValue.value_set ? '已设置（留空保持不变）' : '未设置'"
          :value="String(modelValue[f.key] ?? '')"
          @input="update(f.key, ($event.target as HTMLInputElement).value)" />
      </div>
      <Field v-else :spec="f" :model-value="modelValue[f.key]"
        @update:model-value="(v) => update(f.key, v)" />
    </template>
    <button class="pw-danger" @click="emit('delete')">删除</button>
  </div>
</template>
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/ServerCard.test.ts`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/ServerCard.vue frontend/src/components/HeaderCard.vue frontend/src/components/ServerCard.test.ts
git commit -m "feat(frontend): ServerCard/HeaderCard 可增删卡片 + 哨兵敏感字段不预填"
```

---

### Task 9: `StatusPanel.vue`（状态面板 + restarting 轮询 + 四态）

**Files:**
- Create: `frontend/src/components/StatusPanel.vue`
- Test: `frontend/src/components/StatusPanel.test.ts`

**Interfaces:**
- Consumes: `apiGet`（bridge.ts）。
- Produces: `StatusPanel`（无 props；自管 loading/error/ready 与 restarting 轮询）。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/StatusPanel.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StatusPanel from './StatusPanel.vue'

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

describe('StatusPanel', () => {
  it('渲染服务器状态卡片', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockResolvedValue({
      ok: true, servers: [{ name: 'alpha', ready: true, online: 3, smoothness_label: '流畅', degraded: false }] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('alpha')
    expect(w.text()).toContain('在线 3')
    expect(w.text()).toContain('流畅')
  })
  it('restarting 显示重载中', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockResolvedValue({ ok: true, servers: [], restarting: true })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('正在重载')
  })
  it('读取失败进 error 态,不白屏', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockRejectedValue(new Error('net'))
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('读取状态失败')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/StatusPanel.test.ts`
Expected: FAIL（模块缺失）。

- [ ] **Step 3: 实现**

`frontend/src/components/StatusPanel.vue`：

```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet } from '../lib/bridge'

interface StatusRow { name: string; ready: boolean; online?: number; smoothness_label?: string; degraded?: boolean }
interface StatusResp { ok: boolean; servers: StatusRow[]; restarting?: boolean }

const state = ref<'loading' | 'error' | 'ready'>('loading')
const rows = ref<StatusRow[]>([])
const restarting = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

async function load() {
  try {
    const data = await apiGet<StatusResp>('status/overview')
    restarting.value = !!data.restarting
    rows.value = data.servers ?? []
    state.value = 'ready'
    if (restarting.value) { if (timer) clearTimeout(timer); timer = setTimeout(load, 3000) }
  } catch {
    state.value = 'error'
  }
}
onMounted(load)
onUnmounted(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <div class="pw-status">
    <button class="pw-primary" @click="load">刷新</button>
    <p v-if="state === 'loading'" class="pw-muted">加载中…</p>
    <p v-else-if="state === 'error'" class="pw-error">读取状态失败，请重试</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">插件正在重载配置…</p>
      <div v-for="row in rows" :key="row.name" class="pw-card">
        <strong>{{ row.name }}</strong>
        <div v-if="!row.ready" class="pw-muted">未就绪</div>
        <div v-else>在线 {{ row.online }} · {{ row.smoothness_label }}<span v-if="row.degraded"> · 数据缺失</span></div>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/StatusPanel.test.ts`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/StatusPanel.vue frontend/src/components/StatusPanel.test.ts
git commit -m "feat(frontend): StatusPanel 状态面板 + restarting 轮询 + 四态"
```

---

### Task 10: `SettingsPanel.vue`（装配 9 节 + 保存 + 四态 + 局部错误分层 + 并发禁用）

**Files:**
- Create: `frontend/src/components/SettingsPanel.vue`
- Test: `frontend/src/components/SettingsPanel.test.ts`

**Interfaces:**
- Consumes: `apiGet`/`apiPost`（bridge.ts）、`collectBody`（collect.ts）、`OBJECT_SECTIONS`/`SERVER_FIELDS`/`HEADER_FIELDS`（schema.ts）、`ServerCard`/`HeaderCard`/`SectionForm`。
- Produces: `SettingsPanel`（无 props；自管 loading/fatal-error/ready；unauthorized/bridge 缺失→整块 error 态；保存业务错误→就地局部提示；保存中→按钮禁用）。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/SettingsPanel.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsPanel from './SettingsPanel.vue'

const cfg = () => ({ ok: true, config: {
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
  routing: { access_mode: 'restricted', default_server: '' },
  polling: { metrics_seconds: 30, players_seconds: 30, info_seconds: 600, settings_seconds: 1800,
    game_data_seconds: 120, jitter_ratio: 0.1, max_concurrency: 6 },
  world: { timezone: 'Asia/Tokyo', locale: 'zh-CN', fps_smooth: 50, fps_moderate: 35, fps_laggy: 20 },
  bases: { enabled: true, assignment_radius: 5000, ambiguity_ratio: 0.2, confirmation_samples: 3,
    position_grid_size: 2000, z_weight: 0.5 },
  privacy: { mode: 'balanced', public_exact_ping: false, public_positions: false,
    ping_good_ms: 60, ping_ok_ms: 120, uncertain_timeout: 900 },
  history: { raw_metrics_days: 7, aggregate_days: 90, session_days: 365, observation_days: 180 },
  features: { report: true, events: true, guilds_bases: false },
}, page_version: 1 })

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

describe('SettingsPanel', () => {
  it('加载后渲染 9 节（含 features 分组标题）', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockResolvedValue(cfg())
    const w = mount(SettingsPanel); await flushPromises()
    expect(w.text()).toContain('功能分组开关')
    expect(w.text()).toContain('路由与访问控制')
    expect(w.text()).toContain('保存并重载')
  })
  it('config/get unauthorized → 整块错误态，不白屏', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockResolvedValue({ ok: false, error: 'unauthorized', detail: {} })
    const w = mount(SettingsPanel); await flushPromises()
    expect(w.text()).toContain('未登录')
  })
  it('保存调用 apiPost，body 不含 group_bindings 且类型正确', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage.apiPost as any).mockResolvedValue({ ok: true, warnings: {} })
    const w = mount(SettingsPanel); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    const [, body] = (window.AstrBotPluginPage.apiPost as any).mock.calls[0]
    expect('group_bindings' in body).toBe(false)
    expect(typeof body.polling.metrics_seconds).toBe('number')
    expect(typeof body.features.report).toBe('boolean')
  })
  it('保存业务错误 credential_redirect → 就地提示，不打整页错误态', async () => {
    (window.AstrBotPluginPage.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage.apiPost as any).mockResolvedValue({ ok: false, error: 'credential_redirect', detail: { path: 'servers[0].password' } })
    const w = mount(SettingsPanel); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    expect(w.text()).toContain('请重新输入该服务器密码')
    expect(w.text()).toContain('功能分组开关') // 表单仍在（未塌成整页错误）
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/SettingsPanel.test.ts`
Expected: FAIL（模块缺失）。

- [ ] **Step 3: 实现**

`frontend/src/components/SettingsPanel.vue`：

```vue
<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { apiGet, apiPost } from '../lib/bridge'
import { Unauthorized, BusinessError } from '../lib/errors'
import { collectBody, type SettingsState } from '../lib/collect'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS } from '../lib/schema'
import ServerCard from './ServerCard.vue'
import HeaderCard from './HeaderCard.vue'
import SectionForm from './SectionForm.vue'

const phase = ref<'loading' | 'error' | 'ready'>('loading')
const fatalMsg = ref('')
const saving = ref(false)
const notice = ref('')

const state = reactive<SettingsState>({ servers: [], custom_headers: [], sections: {} })

const ERR: Record<string, string> = {
  save_in_progress: '保存进行中，请稍候', too_frequent: '保存过于频繁，请稍候再试',
  too_large: '配置过大', invalid_shape: '配置结构不合法', invalid_field: '字段不合法',
  credential_redirect: '修改了服务器地址，请重新输入该服务器密码',
  restart_failed_rolled_back: '重载失败，已回滚到旧配置',
  restart_failed: '重载失败且回滚失败，请检查后台', unauthorized: '未登录或登录已过期',
}
const mapError = (e: BusinessError) => (ERR[e.code] ?? '保存失败') + (e.path ? `：${e.path}` : '')

function emptyRow(fields: typeof SERVER_FIELDS): Record<string, unknown> {
  const row: Record<string, unknown> = { __row_id: '' }
  for (const f of fields) row[f.key] = f.default
  return row
}

async function load() {
  phase.value = 'loading'
  try {
    const r = await apiGet<{ config: Record<string, any> }>('config/get')
    const c = r.config
    state.servers = (c.servers ?? []).map((s: Record<string, unknown>) => ({ ...s }))
    state.custom_headers = (c.custom_headers ?? []).map((h: Record<string, unknown>) => ({ ...h }))
    state.sections = {}
    for (const sec of OBJECT_SECTIONS) state.sections[sec.key] = { ...(c[sec.key] ?? {}) }
    phase.value = 'ready'
  } catch (e) {
    fatalMsg.value = e instanceof Unauthorized ? '未登录或登录已过期，请重新登录 Dashboard' : '读取配置失败，请重试'
    phase.value = 'error'
  }
}
onMounted(load)

function toast(msg: string) { notice.value = msg; setTimeout(() => { if (notice.value === msg) notice.value = '' }, 3000) }

async function save() {
  if (saving.value) return
  saving.value = true; notice.value = ''
  try {
    const res = await apiPost<{ ok: boolean; warnings?: Record<string, unknown[]> }>('config/save', collectBody(state))
    const w = res.warnings ?? {}
    const skips = [...((w.skipped_servers as unknown[]) ?? []), ...((w.skipped_headers as unknown[]) ?? [])]
    toast(skips.length ? `已保存（${skips.length} 条被跳过）` : '已保存并重载')
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e))
    else if (e instanceof Unauthorized) toast('未登录或登录已过期')
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败')
    else toast('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="pw-settings">
    <p v-if="phase === 'loading'" class="pw-muted">加载中…</p>
    <div v-else-if="phase === 'error'" class="pw-fatal">{{ fatalMsg }}<button class="pw-primary" @click="load">重试</button></div>
    <template v-else>
      <h3 class="pw-section-title">服务器</h3>
      <ServerCard v-for="(s, i) in state.servers" :key="s.__row_id || i" :model-value="s"
        @update:model-value="(v) => state.servers[i] = v" @delete="state.servers.splice(i, 1)" />
      <button class="pw-add" @click="state.servers.push(emptyRow(SERVER_FIELDS))">+ 添加服务器</button>

      <h3 class="pw-section-title">自定义请求头</h3>
      <HeaderCard v-for="(h, i) in state.custom_headers" :key="h.__row_id || i" :model-value="h"
        @update:model-value="(v) => state.custom_headers[i] = v" @delete="state.custom_headers.splice(i, 1)" />
      <button class="pw-add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS))">+ 添加请求头</button>

      <SectionForm v-for="sec in OBJECT_SECTIONS" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => state.sections[sec.key] = v" />

      <div class="pw-save-bar">
        <button class="pw-save pw-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存并重载' }}</button>
        <span v-if="notice" class="pw-notice">{{ notice }}</span>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/SettingsPanel.test.ts`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SettingsPanel.vue frontend/src/components/SettingsPanel.test.ts
git commit -m "feat(frontend): SettingsPanel 装配 9 节 + 保存 + 四态 + 局部错误分层 + 并发禁用"
```

---

### Task 11: `App.vue` + `main.ts`（tab + 错误边界 + bridge 缺失态 + 首屏主题）

**Files:**
- Create: `frontend/src/App.vue`、`frontend/src/lib/boot.ts`、`frontend/src/App.test.ts`、`frontend/src/lib/boot.test.ts`
- Modify: `frontend/src/main.ts`（替换 T2 的 hello 入口）

**Interfaces:**
- Consumes: `SettingsPanel`/`StatusPanel`、`ready`（bridge.ts）、`BridgeMissing`（errors.ts）。
- Produces: `App`（tab + onErrorCaptured 兜底）、`bootMessage(err) -> string`。

- [ ] **Step 1: 写失败测试**

`frontend/src/lib/boot.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { bootMessage } from './boot'
import { BridgeMissing } from './errors'

describe('bootMessage', () => {
  it('bridge 缺失 → 提示需要插件页环境', () => {
    expect(bootMessage(new BridgeMissing())).toContain('AstrBot ≥ v4.24.1')
  })
  it('其他错误 → 通用刷新提示（不泄露原文）', () => {
    expect(bootMessage(new Error('secret internal detail'))).toBe('初始化失败，请刷新')
  })
})
```

`frontend/src/App.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from './App.vue'

beforeEach(() => {
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve(),
    apiGet: vi.fn().mockResolvedValue({ ok: true, config: {}, servers: [] }),
    apiPost: vi.fn().mockResolvedValue({ ok: true }),
  }
})

describe('App', () => {
  it('默认设置 tab，可切到状态', async () => {
    const w = mount(App); await flushPromises()
    const tabs = w.findAll('.pw-tabs button')
    expect(tabs[0].text()).toBe('设置')
    await tabs[1].trigger('click'); await flushPromises()
    expect(w.text()).toContain('刷新') // StatusPanel 的刷新按钮
  })
  it('子组件抛错 → 错误边界兜底，不白屏', async () => {
    const Boom = { setup() { throw new Error('boom-child') }, template: '<div/>' }
    const w = mount(App, { global: { stubs: { SettingsPanel: Boom } } })
    await flushPromises()
    expect(w.text()).toContain('boom-child')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/lib/boot.test.ts src/App.test.ts`
Expected: FAIL（模块缺失）。

- [ ] **Step 3: 实现**

`frontend/src/lib/boot.ts`：

```ts
import { BridgeMissing } from './errors'

// 不回显原始错误文本（避免泄露内部信息）
export function bootMessage(err: unknown): string {
  return err instanceof BridgeMissing ? '需要 AstrBot ≥ v4.24.1 的插件页面环境' : '初始化失败，请刷新'
}
```

`frontend/src/App.vue`：

```vue
<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import SettingsPanel from './components/SettingsPanel.vue'
import StatusPanel from './components/StatusPanel.vue'

const tab = ref<'settings' | 'status'>('settings')
const fatal = ref('')
onErrorCaptured((err) => { fatal.value = (err as Error)?.message || '页面发生错误'; return false })
</script>

<template>
  <div v-if="fatal" class="pw-fatal">{{ fatal }}<button class="pw-primary" @click="fatal = ''">重试</button></div>
  <div v-else class="pw-app">
    <nav class="pw-tabs">
      <button :class="{ active: tab === 'settings' }" @click="tab = 'settings'">设置</button>
      <button :class="{ active: tab === 'status' }" @click="tab = 'status'">状态</button>
    </nav>
    <main class="pw-main">
      <SettingsPanel v-if="tab === 'settings'" />
      <StatusPanel v-else />
    </main>
  </div>
</template>
```

`frontend/src/main.ts`（替换 T2 的 hello）：

```ts
import { createApp, h } from 'vue'
import App from './App.vue'
import { ready } from './lib/bridge'
import { bootMessage } from './lib/boot'
import './styles/tokens.css'

async function boot() {
  try {
    await ready()
  } catch (e) {
    createApp({ render: () => h('div', { class: 'pw-fatal' }, bootMessage(e)) }).mount('#app')
    return
  }
  createApp(App).mount('#app')
}
boot()
```

> `main.ts` 是 bootstrap，不单测（顶层 `boot()` 副作用）；其唯一逻辑分支 `bootMessage` 已在 `boot.test.ts` 覆盖，整体 mount 在 T13 真机验收。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/lib/boot.test.ts src/App.test.ts`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.vue frontend/src/main.ts frontend/src/lib/boot.ts frontend/src/App.test.ts frontend/src/lib/boot.test.ts
git commit -m "feat(frontend): App tab+错误边界 + main bridge 缺失显式态"
```

---

### Task 12: `tokens.css` 设计变量与组件样式（亮暗双主题）

**Files:**
- Create: `frontend/src/styles/tokens.css`

**Interfaces:**
- Consumes: `main.ts` 已 `import './styles/tokens.css'`（T11）。
- Produces: 全部 `pw-*` 类样式；产物出 1 个 `.css`。

> 本任务无单元测试（纯样式），验收 = build 出单 css + `verify:bundle` 通过 + T13 真机观感。骨架/首屏样式**不假设 `isDark`**：默认（无 `data-theme`）用亮色令牌，`[data-theme="dark"]` 覆盖为暗色，服务端注入 `data-theme` 即生效，无闪烁依赖。

- [ ] **Step 1: 写样式**

`frontend/src/styles/tokens.css`：

```css
:root {
  --pw-sp-1: 4px; --pw-sp-2: 8px; --pw-sp-3: 12px; --pw-sp-4: 16px; --pw-sp-6: 24px;
  --pw-radius: 8px;
  --pw-bg: #ffffff; --pw-surface: #f7f8fa; --pw-border: #e3e6ea;
  --pw-text: #1f2430; --pw-muted: #6b7280;
  --pw-accent: #3b82f6; --pw-accent-contrast: #ffffff;
  --pw-danger: #dc2626; --pw-error: #b91c1c;
  --pw-focus: 0 0 0 2px rgba(59, 130, 246, 0.45);
}
[data-theme="dark"] {
  --pw-bg: #14171c; --pw-surface: #1c2029; --pw-border: #2b313c;
  --pw-text: #e6e9ef; --pw-muted: #9aa3b2;
  --pw-accent: #60a5fa; --pw-accent-contrast: #0b0d10;
  --pw-danger: #f87171; --pw-error: #f87171;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--pw-bg); color: var(--pw-text);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }

.pw-app { max-width: 880px; margin: 0 auto; padding: var(--pw-sp-4); }
.pw-tabs { display: flex; gap: var(--pw-sp-2); border-bottom: 1px solid var(--pw-border); margin-bottom: var(--pw-sp-4); }
.pw-tabs button { background: none; border: none; padding: var(--pw-sp-2) var(--pw-sp-3); color: var(--pw-muted);
  cursor: pointer; border-bottom: 2px solid transparent; font-size: 14px; }
.pw-tabs button.active { color: var(--pw-text); border-bottom-color: var(--pw-accent); }

.pw-section { margin: var(--pw-sp-4) 0; }
.pw-section-title { font-size: 15px; margin: var(--pw-sp-4) 0 var(--pw-sp-2); color: var(--pw-text); }
.pw-field { display: flex; align-items: center; gap: var(--pw-sp-3); margin: var(--pw-sp-2) 0; }
.pw-field-label { flex: 0 0 160px; color: var(--pw-muted); font-size: 13px; }

.pw-input, .pw-select-trigger, .pw-number-input {
  flex: 1; min-width: 0; padding: var(--pw-sp-2) var(--pw-sp-3); border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius); background: var(--pw-surface); color: var(--pw-text); font-size: 14px; }
.pw-input:focus-visible, .pw-select-trigger:focus-visible, .pw-number-input:focus-visible { outline: none; box-shadow: var(--pw-focus); }

.pw-select-trigger { display: inline-flex; justify-content: space-between; align-items: center; cursor: pointer; }
.pw-select-content { background: var(--pw-surface); border: 1px solid var(--pw-border); border-radius: var(--pw-radius); padding: var(--pw-sp-1); }
.pw-select-item { padding: var(--pw-sp-2) var(--pw-sp-3); border-radius: var(--pw-radius); cursor: pointer; }
.pw-select-item[data-highlighted] { background: var(--pw-accent); color: var(--pw-accent-contrast); }

.pw-switch { width: 40px; height: 22px; border-radius: 999px; background: var(--pw-border); position: relative; cursor: pointer; border: none; }
.pw-switch[data-state="checked"] { background: var(--pw-accent); }
.pw-switch-thumb { display: block; width: 18px; height: 18px; border-radius: 50%; background: #fff; transform: translateX(2px); transition: transform .15s; }
.pw-switch[data-state="checked"] .pw-switch-thumb { transform: translateX(20px); }

.pw-number { display: inline-flex; align-items: center; gap: var(--pw-sp-1); }
.pw-number-btn { width: 28px; height: 30px; border: 1px solid var(--pw-border); background: var(--pw-surface); color: var(--pw-text); border-radius: var(--pw-radius); cursor: pointer; }
.pw-number-input { text-align: center; }

.pw-card { border: 1px solid var(--pw-border); border-radius: var(--pw-radius); padding: var(--pw-sp-3); margin: var(--pw-sp-2) 0; background: var(--pw-surface); }
.pw-add { background: none; border: 1px dashed var(--pw-border); color: var(--pw-accent); padding: var(--pw-sp-2) var(--pw-sp-3); border-radius: var(--pw-radius); cursor: pointer; }

.pw-primary, .pw-save { background: var(--pw-accent); color: var(--pw-accent-contrast); border: none; padding: var(--pw-sp-2) var(--pw-sp-4); border-radius: var(--pw-radius); cursor: pointer; font-size: 14px; }
.pw-primary:disabled, .pw-save:disabled { opacity: .55; cursor: not-allowed; }
.pw-danger { background: none; border: 1px solid var(--pw-danger); color: var(--pw-danger); padding: var(--pw-sp-1) var(--pw-sp-3); border-radius: var(--pw-radius); cursor: pointer; }

.pw-save-bar { display: flex; align-items: center; gap: var(--pw-sp-3); margin-top: var(--pw-sp-6); }
.pw-notice { color: var(--pw-muted); font-size: 13px; }
.pw-muted { color: var(--pw-muted); }
.pw-error { color: var(--pw-error); }
.pw-fatal { padding: var(--pw-sp-6); text-align: center; color: var(--pw-error); display: flex; flex-direction: column; align-items: center; gap: var(--pw-sp-3); }

@media (prefers-reduced-motion: reduce) { .pw-switch-thumb { transition: none; } }
```

> reka-ui 的 `data-state`/`data-highlighted` 属性名以 2.10.1 实测核对；若不同，按实测调 selector（不影响功能，仅视觉）。

- [ ] **Step 2: 构建并验证单文件产物**

Run（仓库根）：`cd frontend && npm run build && cd .. && node frontend/scripts/verify-bundle.mjs`
Expected: `pages/settings/assets/` = `index.js` + `index.css`；输出 `OK: single-file bundle verified`。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/styles/tokens.css
git commit -m "feat(frontend): tokens.css 设计变量与组件样式（亮暗双主题）"
```

---

## 阶段 4 —— 集成、迁移与 CI

### Task 13: 产物入库 + 清理旧前端与失效测试

**Files:**
- Delete: `pages/settings/app.js`、`settings.js`、`status.js`、`style.css`（旧手写；`index.html` 被 Vite 产物替换）
- Delete: `tests/unit/pages_static_test.py`（硬编码旧文件名/grep，Vite 产物后全红）
- Create: `tests/unit/frontend_source_test.py`（XSS 红线转移到前端源码）

- [ ] **Step 1: 新增前端源码 XSS 红线守卫**

`tests/unit/frontend_source_test.py`：

```python
"""XSS 红线转移到前端源码：Vue 组件禁 v-html / innerHTML（对源码而非压缩产物）。"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_no_v_html_in_vue_sources():
    for f in SRC.rglob("*.vue"):
        assert "v-html" not in f.read_text(encoding="utf-8"), f"{f.name} 不得用 v-html"


def test_no_innerhtml_in_frontend_sources():
    for f in list(SRC.rglob("*.vue")) + list(SRC.rglob("*.ts")):
        assert ".innerHTML" not in f.read_text(encoding="utf-8"), f"{f.name} 不得用 innerHTML"
```

- [ ] **Step 2: 运行新守卫（迁移任务，非 red-first）**

Run: `python -m pytest tests/unit/frontend_source_test.py -v`
Expected: PASS（前端源码本就无 v-html/innerHTML）。

- [ ] **Step 3: 删旧手写文件 + 失效测试，确认产物**

T12 的 `npm run build`（`emptyOutDir:true`）已把 `pages/settings/` 清为纯 Vite 产物。用 git 记录删除：

```bash
git rm tests/unit/pages_static_test.py
git add -A pages/settings
```

确认：`pages/settings/` 应为 `index.html` + `assets/`；`pages/settings/assets/` 为 `index.js` + `index.css`（旧 `app.js`/`settings.js`/`status.js`/`style.css` 已不存在）。

- [ ] **Step 4: 后端全量回归**

Run: `python -m pytest -q && ruff check . && mypy`
Expected: 全绿（`pages_static_test` 已删、`frontend_source_test` 通过、其余不受影响）。

- [ ] **Step 5: 提交**

```bash
git add -A pages/settings frontend tests/unit/frontend_source_test.py
git commit -m "chore(pages): Vite 产物替换手写设置页 + XSS 红线转移到前端源码 + 删失效静态测试"
```

---

### Task 14: 版本声明迁移到 `>=4.24.1` + 同步测试与 README

**Files:**
- Modify: `metadata.yaml:7`、`tests/unit/skeleton_test.py:21`、`tests/unit/readme_test.py:12`、`README.md:15` 及插件页面说明段

**Interfaces:** 无下游代码依赖。

- [ ] **Step 1: 先改测试断言到新期望（red）**

`tests/unit/skeleton_test.py:21`：
```python
    assert data["astrbot_version"] == ">=4.24.1"
```

`tests/unit/readme_test.py:12`：
```python
    assert "AstrBot ≥ 4.24.1" in README or "AstrBot >= 4.24.1" in README
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/unit/skeleton_test.py::test_metadata_yaml_has_all_top_keys tests/unit/readme_test.py::test_readme_requirements_and_usage -v`
Expected: FAIL（`metadata.yaml` 仍 `>=4.10.4`；README 仍写 `≥ 4.10.4`）。

- [ ] **Step 3: 改 `metadata.yaml` 与 README**

`metadata.yaml:7`：
```yaml
astrbot_version: ">=4.24.1"
```

`README.md:15`（把 `- AstrBot ≥ 4.10.4（建议最新 4.26.x）` 改为）：
```markdown
- AstrBot ≥ 4.24.1（插件设置页需此版本；建议最新 4.26.x）
```

README 插件页面说明段（现 `:98` 起）：**保留** `readme_test.py` 要求的所有短语（`插件页面`、`4.24.1`、`4.25.3`、`__unchanged__`、`重载`），仅补一句说明"设置页现以 Vue 页面提供，可视化编辑全部 9 个配置节（服务器/请求头/路由/轮询/世界/据点/隐私/保留/特性）"。**不得删除** `readme_test.py` 其它断言覆盖的段落（安全声明、只读端点、polling/world/bases/history/custom_headers/feature_groups 各节文档）。

> 约束提醒：`readme_test.py` 有 11 组短语断言，改 README 前先通读该测试，确保新文案仍含全部被断言短语。

- [ ] **Step 4: 运行确认通过（含 README 全量断言）**

Run: `python -m pytest tests/unit/skeleton_test.py tests/unit/readme_test.py tests/unit/main_test.py -q`
Expected: PASS（版本断言更新、README 短语齐全、`main_test` 的 `@register` version=v0.1.0 与 metadata `version` 一致——未动 `version` 字段）。

- [ ] **Step 5: 提交**

```bash
git add metadata.yaml README.md tests/unit/skeleton_test.py tests/unit/readme_test.py
git commit -m "docs: 插件页面版本门槛统一为 AstrBot >=4.24.1（metadata/README/测试同步）"
```

---

### Task 15: CI 增加前端 job（构建 + 测试 + 产物断言 + 无漂移校验）

**Files:**
- Modify: `.github/workflows/ci.yml`（在 `jobs:` 下新增 `frontend` job）

- [ ] **Step 1: 新增 frontend job**

在 `.github/workflows/ci.yml` 的 `jobs:` 下追加：

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: frontend/.nvmrc
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install
        working-directory: frontend
        run: npm ci
      - name: Unit tests
        working-directory: frontend
        run: npm run test:run
      - name: Build
        working-directory: frontend
        run: npm run build
      - name: Verify single-file bundle
        run: node frontend/scripts/verify-bundle.mjs
      - name: Assert built assets committed (no drift)
        run: |
          git diff --exit-code -- pages/settings \
            || (echo "产物与源码构建结果漂移：请本地 npm run build 后提交 pages/settings" && exit 1)
```

> 漂移校验注记（对应 spec §3.2 / 复核 F10）：`.nvmrc` 钉 Node + `.gitattributes` 强制 `pages/settings/**` LF 是跨平台可复现的前提。若 CI（linux）与本地（win32）仍出现字节级漂移致该步误红，**回退方案**：删除最后一步"no drift"，只保留 `build + verify-bundle`（产物仍由开发者本地构建入库，CI 只保证可构建与单文件约束）。实现时先在 CI 实跑一次确认无漂移，再决定是否保留该门禁。

- [ ] **Step 2: 本地静态校验 YAML + 逐步手验**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml',encoding='utf-8')); print('yaml ok')"`
Expected: `yaml ok`。并本地依次跑通 `cd frontend && npm ci && npm run test:run && npm run build && cd .. && node frontend/scripts/verify-bundle.mjs && git diff --exit-code -- pages/settings`。

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: 增加前端 job（npm ci + vitest + build + 单文件产物断言 + 无漂移校验）"
```

---

## 实现顺序与依赖

- **T1 先行**（止血）：完成即消白屏，独立于前端。
- **T2 → T3/T4/T5**（脚手架 → 纯 TS 逻辑，可并行三者但都依赖 T2）。
- **T6 → T7/T8 → T9/T10 → T11 → T12**（组件自底向上；T10 依赖 T6/T7/T8，T11 依赖 T9/T10）。
- **T13 依赖 T12**（build 产物）；**T14/T15 可在 T13 后任意序**。

## Quart 兼容审计结论（落地 spec §5.2）

本 plan 的后端改动**仅** T1 一处（`_has_identity` 改读 `g.username`）。审计结论（复核已核实源码）：`from quart import jsonify`→真实 Quart `jsonify`（`asgi_runtime.py:419`）可靠**保留**；`request.get_json(silent=True)` 兼容层提供**保留**；唯一需改的是**不再读 `request.username`**（T1 完成）。故无额外后端任务。

## Self-Review：spec 覆盖对照

| spec 要点 | 落地任务 |
|---|---|
| 根因 A（`g.username`）+ 身份测试新增 | T1 |
| 根因 B（`r.ok` 分流） | T3 |
| 单文件硬约束 + CI 断言（治平台 F1/F5） | T2 / T12 / T15 |
| 供应链钉版 + lockfile 入库（治 SEC-2） | T2 |
| 9 节补全 + collect 逐字段语义（治 F1） | T4 / T5 / T7 / T10 |
| 类型正确（治 F3） | T5（+断言） |
| schema 完整性（治 F6） | T4（vs `_conf_schema.json`） |
| `group_bindings` 不清空（治 F2） | T5（body 不含该键） |
| 四态 + transport/业务两层错误（治 F8） | T3 / T9 / T10 / T11 |
| detail 白名单（治 SEC-3） | T3 |
| bridge 无 status 契约（治平台 F7） | T3（基于 `ok` 解包） |
| 预编译渲染（治平台 F9） | Vite `@vitejs/plugin-vue` 默认 SFC 预编译（无 runtime compiler） |
| 首屏主题不假设 isDark（治 F11） | T12（默认亮 + `[data-theme=dark]`） |
| 禁 v-html（XSS） | T13（源码守卫） |
| 删失效 `pages_static_test`（治平台 F4） | T13 |
| 版本 4.24.1 + README 修正（治 F7/F8） | T14 |
| Quart 兼容审计（jsonify 保留） | T1 + 上节结论 |

**验收总门（全 15 任务后）**：`python -m pytest -q && ruff check . && mypy` 全绿；`cd frontend && npm run test:run && npm run build` 全绿 + `verify-bundle` 通过；真实 AstrBot ≥ 4.24.1 Dashboard 打开设置页能加载、9 节可编辑保存、各错误态可见不白屏。

