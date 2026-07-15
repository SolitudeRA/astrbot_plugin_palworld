# 首次强制模式选择：命令闸 + 设置页引导屏（Phase 1）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全新安装必须在设置页有意识地选一次运行模式并确认后，`/pal` 常规命令才正常服务（否则返回引导语），确认入口是设置页首次引导屏。

**Architecture:** 新增 `setup_confirmed`（bool，默认 false）**嵌进 `routing` 节**（与 `world_mode` 同处、随 routing 往返，避开首个顶层标量的平台不确定性、并让读侧 hydrate 天然可用）。后端在 `main.py` 的 `_guarded` / `_guarded_cmd` 两个包装器加**命令感知**的 setup 闸（逗口集 `{help,whoami,whereami}` 放行）。前端在 `SettingsPanel` 的 ready 相态里按 `routing.setup_confirmed !== true` 分叉到新组件 `ModeOnboarding.vue`。

**Tech Stack:** Python 3.10+（AstrBot 插件，相对导入红线）、pytest、Vue 3 + TS、Vitest；构建产物 `pages/settings/**` 入库须 no-drift + LF。

> **方案说明（决策 2 降级预案落地）**：spec §4.3 的"嵌进 routing"预案被采纳为实现方案（真实 AstrBot 不在本仓、无法验证顶层裸标量；嵌套是 `world_mode` 已验证的成熟模式，且 `collectBody` 逐字段重建 routing 的事实要求 setup_confirmed 必须进 schema fields）。spec §5/§6 的"顶层键"描述以本 plan 的 routing 嵌套版为准。

## Global Constraints

- **无迁移 / 无向后兼容**（插件尚无真实用户）：默认值/结构直接改，不写迁移护栏。
- **版本号不变（保持 v0.9.7）**：本 Phase 不发版，**不动**任何版本源/断言（`metadata.yaml`/`main.py @register`/`__init__.py`/`README` badge/`phase1_smoke_test.py`/`skeleton_test.py`）。
- **相对导入红线**：`palworld_terminal` 包内严禁绝对自导入。
- **Windows 测试**：`./.venv/Scripts/python.exe -m pytest`。lint：`./.venv/Scripts/python.exe -m ruff check .` + `./.venv/Scripts/python.exe -m mypy palworld_terminal`。
- **前端**：`cd frontend && npm test`（vitest）；改前端源后 `cd frontend && npm run build`（内置 normalize-eol）刷新 `pages/settings/**`，否则 CI no-drift 红。
- **git 提交不出现 Claude**（正文与尾行均不提及）。
- **命令锚定**：`_SETUP_EXEMPT ⊆ set(FLAT_ACTIONS)`（`command_registry.py:59-67`）。逗口集单一真相源在 `main.py`。
- **严格布尔**：`setup_confirmed` 只认 JSON `True`（后端 `is True`、前端 `=== true`），字符串/其它一律未确认。
- **门序铁律**：setup 闸放在 `_busy_msg()`（busy/container-None 守卫）**之后**、enable/admin/授权判定**之前**。闸只落聊天命令 handler 侧，绝不下沉到 web_api/scheduler。

---

### Task 1: 后端 `setup_confirmed` 配置字段（RoutingConfig + 严格解析 + schema）

只新增配置字段与解析，无消费方，任务结束绿（不改行为）。

**Files:**
- Modify: `palworld_terminal/config.py`（RoutingConfig 字段 + parse_config 接线）
- Modify: `_conf_schema.json`（routing.items 加 setup_confirmed）
- Create: `tests/unit/config_setup_confirmed_test.py`
- Test（回归）: `tests/unit/conf_schema_test.py`

**Interfaces:**
- Produces: `RoutingConfig.setup_confirmed: bool`（默认 `False`）；schema `routing.items.setup_confirmed`（type bool，default false）。

- [ ] **Step 1: 写失败测试**

Create `tests/unit/config_setup_confirmed_test.py`：

```python
from palworld_terminal.config import parse_config


def test_setup_confirmed_default_false():
    cfg = parse_config({}, {})
    assert cfg.routing.setup_confirmed is False


def test_setup_confirmed_parsed_true():
    cfg = parse_config({"routing": {"setup_confirmed": True}}, {})
    assert cfg.routing.setup_confirmed is True


def test_setup_confirmed_strict_bool_rejects_string():
    # 严格 is True：字符串一律未确认（避免 bool("false")==True 脚枪）
    assert parse_config({"routing": {"setup_confirmed": "true"}}, {}).routing.setup_confirmed is False
    assert parse_config({"routing": {"setup_confirmed": "false"}}, {}).routing.setup_confirmed is False
    assert parse_config({"routing": {"setup_confirmed": 1}}, {}).routing.setup_confirmed is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_setup_confirmed_test.py -v`
Expected: FAIL（`AttributeError: 'RoutingConfig' object has no attribute 'setup_confirmed'`）

- [ ] **Step 3: 加 dataclass 字段**

`palworld_terminal/config.py` 的 `RoutingConfig`（:63-68），在 `single_allowed_groups` 后加字段：

```python
@dataclass(slots=True)
class RoutingConfig:
    access_mode: AccessMode
    default_server: str
    world_mode: str = "single"  # "single" | "multi"
    single_allowed_groups: list[AllowedGroupEntry] = field(default_factory=list)
    setup_confirmed: bool = False  # 首次模式确认标志；随 routing 往返；靠 AstrBot 回填→新装恒 False
```

- [ ] **Step 4: parse_config 接线（严格布尔）**

`palworld_terminal/config.py` 的 `parse_config` 构造 `RoutingConfig(...)`（:443-451），加实参（`r = _obj(raw, "routing")` 已在 :435）：

```python
        routing=RoutingConfig(
            access_mode=AccessMode(str(r.get("access_mode", "restricted") or "restricted")),
            default_server=str(r.get("default_server", "") or ""),
            world_mode=_one_of(r.get("world_mode", "single"), frozenset({"single", "multi"}), "single"),
            single_allowed_groups=_parse_single_allowed_groups(raw),
            setup_confirmed=(r.get("setup_confirmed") is True),
        ),
```

- [ ] **Step 5: schema 加字段**

`_conf_schema.json` 的 `routing.items`（:29-32），在 `world_mode` 后加同级键：

```json
      "world_mode": { "type": "string", "options": ["multi", "single"], "default": "single", "description": "运行模式（主开关）：single 单世界（唯一服务器，群授权走插件设置页「连接」章的授权群名单 + /pal whereami）；multi 多世界（多台服务器，用 /pal link 绑定切换）。切换模式后请到插件设置页配置对应模式。" },
      "setup_confirmed": { "type": "bool", "default": false, "description": "首次设置确认标志：一般由插件设置页在你完成模式选择后自动写入，通常无需手动改动。" }
```

（注意 `world_mode` 行尾原无逗号——加了后续键须给它补逗号。）

- [ ] **Step 6: 跑测试确认通过 + schema 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_setup_confirmed_test.py tests/unit/conf_schema_test.py -v`
Expected: PASS（若 `conf_schema_test` 断言 routing.items 键集，就地把 `setup_confirmed` 加进其期望集）

- [ ] **Step 7: 提交**

```bash
git add palworld_terminal/config.py _conf_schema.json tests/unit/config_setup_confirmed_test.py
git commit -m "feat: routing.setup_confirmed 配置字段（严格布尔解析 + schema，暂无消费方）"
```

---

### Task 2: 后端命令闸（`_SETUP_EXEMPT` + `_setup_gate` + `_guarded`/`_guarded_cmd` 双插桩）

新增逗口集常量、闸方法、双包装器插桩、locale、锚定与穷举测试，并**同任务修 `namespace_runtime_smoke_test` fixture**（否则默认 false 会把该测试全部被闸命令短路、深支覆盖静默丢失）。

**Files:**
- Modify: `main.py`（`_SETUP_EXEMPT` 常量、`_setup_gate` 方法、`_guarded` 签名+插桩、`_guarded_cmd` 插桩、9 处 `_guarded` 调用点传首词）
- Modify: `palworld_terminal/presentation/locale.py`（`setup_required` 键）
- Modify: `tests/unit/namespace_runtime_smoke_test.py`（`_raw_config` routing 加 `setup_confirmed: True` + 新增未确认闸测试）
- Create: `tests/unit/setup_gate_test.py`（锚定 + 穷举单测）

**Interfaces:**
- Consumes: `RoutingConfig.setup_confirmed`（Task 1）；`FLAT_ACTIONS`、`PAL_REGISTERED`（`command_registry.py`）。
- Produces: `_SETUP_EXEMPT: frozenset[str]`；`PalWorldTerminal._setup_gate(command_str) -> str | None`；`_guarded(self, call, command_str)` 新签名；locale `setup_required`。

- [ ] **Step 1: 写锚定 + 穷举失败测试**

Create `tests/unit/setup_gate_test.py`：

```python
from types import SimpleNamespace

import main
from palworld_terminal.presentation.locale import L
from palworld_terminal.presentation.command_registry import FLAT_ACTIONS, PAL_REGISTERED


def _plugin(setup_confirmed: bool):
    # 绕过 __init__（其需 context）；只装 _setup_gate 依赖的 live 配置
    p = main.PalWorldTerminal.__new__(main.PalWorldTerminal)
    p._container = SimpleNamespace(
        config=SimpleNamespace(routing=SimpleNamespace(setup_confirmed=setup_confirmed)))
    return p


def test_setup_exempt_subset_of_flat_actions():
    assert main._SETUP_EXEMPT <= set(FLAT_ACTIONS)


def test_gate_allows_exempt_when_unconfirmed():
    p = _plugin(False)
    for w in main._SETUP_EXEMPT:
        assert p._setup_gate(w) is None


def test_gate_blocks_every_non_exempt_when_unconfirmed():
    p = _plugin(False)
    for w in set(PAL_REGISTERED) - main._SETUP_EXEMPT:
        assert p._setup_gate(w) == L("setup_required")


def test_gate_allows_all_when_confirmed():
    p = _plugin(True)
    for w in PAL_REGISTERED:
        assert p._setup_gate(w) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/setup_gate_test.py -v`
Expected: FAIL（`AttributeError: module 'main' has no attribute '_SETUP_EXEMPT'` / `_setup_gate`）

- [ ] **Step 3: 加 locale 键**

`palworld_terminal/presentation/locale.py` 的 `MESSAGES` dict，在 `single_not_authorized` 附近加：

```python
    "setup_required": (
        "🔧 帕鲁世界终端尚未完成首次设置。请打开插件设置页，"
        "选择运行模式（单服务器 / 多服务器）并确认后即可使用。"
    ),
```

- [ ] **Step 4: 加 `_SETUP_EXEMPT` 常量 + `_setup_gate` 方法**

`main.py`，在 `PalWorldTerminal` 类附近的模块级常量区加：

```python
_SETUP_EXEMPT = frozenset({"help", "whoami", "whereami"})
```

在类内（`_guarded` 附近）加方法：

```python
    def _setup_gate(self, command_str: str) -> str | None:
        """首次设置闸：未确认前，非逗口命令一律回引导语。读 live 配置。
        调用点已在 _busy_msg() 之后 → self._container 必非 None。"""
        if command_str in _SETUP_EXEMPT:
            return None
        if self._container.config.routing.setup_confirmed:
            return None
        return L("setup_required")
```

- [ ] **Step 5: `_guarded` 加 `command_str` 形参 + 插桩**

`main.py` 的 `_guarded`（:195-213）改签名与体：

```python
    async def _guarded(self, call, command_str):
        self._inflight += 1
        self._idle.clear()
        try:
            if (m := self._busy_msg()):
                return m
            if (g := self._setup_gate(command_str)):
                return g
            res = call(self._container)
            if inspect.isawaitable(res):
                res = await res
            return res
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
```

- [ ] **Step 6: `_guarded_cmd` 插桩（已带 command_str）**

`main.py` 的 `_guarded_cmd`（:215-232），在 `_busy_msg` 之后、`admin_denied` 之前插：

```python
            if (m := self._busy_msg()):
                return m
            if (g := self._setup_gate(command_str)):
                return g
            denied = self._container.commands.admin_denied(command_str, self._sender_id(event))
```

- [ ] **Step 7: 9 处 `_guarded` 调用点传首词**

`main.py` 各 handler，给 `self._guarded(...)` 补第二实参（首词字面量）：

- world（:426）：`await self._guarded(lambda c: c.commands.world_grp(...), "world")`
- guild（:430）：`..., "guild")`
- player（:436）：`..., "player")`
- server（:442）：`..., "server")`
- link（:452）：`await self._guarded(lambda c: self._link_dispatch(c, event), "link")`
- whoami（:487）：`await self._guarded(lambda c: c.commands.whoami(self._sender_id(event)), "whoami")`
- whereami（:492）：`..., "whereami")`
- help（:498）：`await self._guarded(lambda c: c.commands.help(self._msg(event), self._is_admin(event)), "help")`
- confirm（:504）：`await self._guarded(lambda c: c.commands.confirm(...), "confirm")`

（`rank`/`online`/`me` 走 `_guarded_cmd`、已带首词，无需改。）

- [ ] **Step 8: 跑单测确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/setup_gate_test.py -v`
Expected: PASS

- [ ] **Step 9: 修 `namespace_runtime_smoke_test` fixture（保深支覆盖）+ 加未确认闸集成测试**

`tests/unit/namespace_runtime_smoke_test.py`：

(a) `_raw_config`（:96）routing 加 `setup_confirmed: True`（已确认安装）：

```python
        "routing": {"access_mode": "open", "default_server": "alpha", "world_mode": world_mode, "setup_confirmed": True},
```

(b) 文件末尾加未确认闸集成测试（复用现有 `namespaced_main` / `_FakeContext` / `_FakeRest` / `_FakeSched` / `_Ev` 与 `calls` 结构，仿 `test_link_single_mode_short_circuits_under_namespaced_load`）：

```python
async def test_unconfirmed_gates_non_exempt_under_namespaced_load(tmp_path, monkeypatch):
    """未确认时：非逗口命令一律回 setup_required；逗口 help/whoami/whereami 放行。"""
    with namespaced_main() as mod:
        container_mod = sys.modules[f"{NS}.palworld_terminal.container"]
        Container = container_mod.Container
        orig_init = Container.__init__

        def patched_init(self, config, data_dir, clock, **kw):
            kw.setdefault("rest_factory", lambda s, c: _FakeRest())
            kw.setdefault("scheduler_factory", lambda **k: _FakeSched())
            orig_init(self, config, data_dir, clock, **kw)

        monkeypatch.setattr(Container, "__init__", patched_init)
        monkeypatch.setattr(mod, "_resolve_data_dir", lambda: tmp_path)

        raw = _raw_config()
        raw["routing"]["setup_confirmed"] = False  # 未确认
        plugin = mod.PalWorldTerminal(_FakeContext(), raw)
        await plugin.initialize()
        try:
            locale = sys.modules[f"{NS}.palworld_terminal.presentation.locale"]
            gate_msg = locale.L("setup_required")
            # 逗口放行（不等于闸文案）
            for msg in ("help", "whoami", "whereami"):
                outs = [o async for o in getattr(plugin, msg)(_Ev(msg))]
                assert outs and outs[0] != gate_msg, f"逗口 {msg} 不应被闸"
            # 非逗口被闸
            for handler, msg in ((plugin.world, "world status"), (plugin.rank, "rank"),
                                 (plugin.server, "server"), (plugin.link, "link list")):
                outs = [o async for o in handler(_Ev(msg))]
                assert outs == [gate_msg], f"未确认时 {msg!r} 应被闸: {outs!r}"
        finally:
            await plugin.terminate()
```

- [ ] **Step 10: 跑相关测试 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/setup_gate_test.py tests/unit/namespace_runtime_smoke_test.py -v`
Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（若有别的**经 handler 驱动命令**的用例因默认未确认而炸红，就地在其 config fixture 的 routing 里加 `setup_confirmed: True`——代表"已确认安装"，记录到账本）

- [ ] **Step 11: lint + 提交**

Run: `./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal`

```bash
git add main.py palworld_terminal/presentation/locale.py tests/unit/setup_gate_test.py tests/unit/namespace_runtime_smoke_test.py
git commit -m "feat: 首次设置命令闸（未确认时非逗口 /pal 命令回引导语，逗口 help/whoami/whereami 放行）"
```

---

### Task 3: 前端引导屏（schema field + 隐藏 + needsOnboarding + ModeOnboarding.vue + 分叉 + fixture 审计）

**Files:**
- Modify: `frontend/src/lib/schema.ts`（routing OBJECT_SECTION 加 setup_confirmed bool 字段）
- Modify: `frontend/src/components/SettingsPanel.vue`（visibleSections 隐藏、needsOnboarding、onboarding 分叉、确认写入）
- Create: `frontend/src/components/ModeOnboarding.vue`
- Create: `frontend/src/components/ModeOnboarding.test.ts`
- Modify: `frontend/src/components/SettingsPanel.test.ts`（cfg() + 所有 routing override 加 setup_confirmed）
- Modify: `frontend/src/components/SettingsPanel.test.ts`（新增 onboarding 用例）
- Build: `pages/settings/**`

**Interfaces:**
- Consumes: GET 下发的 `routing.setup_confirmed`（Task 1，`applyConfig` 整体展开 routing 自动 hydrate 进 `state.sections.routing`）。
- Produces: `ModeOnboarding.vue`（emit `confirm` 携所选 `'single'|'multi'`）；`needsOnboarding` computed。

- [ ] **Step 1: 写 ModeOnboarding 失败测试**

Create `frontend/src/components/ModeOnboarding.test.ts`：

```ts
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ModeOnboarding from './ModeOnboarding.vue'

describe('ModeOnboarding', () => {
  it('确认按钮在未点选前禁用', () => {
    const w = mount(ModeOnboarding)
    const btn = w.get('button.confirm')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('点选单服务器后启用并 emit confirm=single', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-mode="single"]').trigger('click')
    const btn = w.get('button.confirm')
    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
    await btn.trigger('click')
    expect(w.emitted('confirm')?.[0]).toEqual(['single'])
  })

  it('点选多服务器 emit confirm=multi', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-mode="multi"]').trigger('click')
    await w.get('button.confirm').trigger('click')
    expect(w.emitted('confirm')?.[0]).toEqual(['multi'])
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- ModeOnboarding`
Expected: FAIL（组件不存在）

- [ ] **Step 3: 写 ModeOnboarding.vue**

Create `frontend/src/components/ModeOnboarding.vue`（视觉复用现有卡片风格；内部选择态初值 null、与回填的 world_mode 解耦）：

```vue
<script setup lang="ts">
import { ref } from 'vue'
const emit = defineEmits<{ (e: 'confirm', mode: 'single' | 'multi'): void }>()
const selected = ref<'single' | 'multi' | null>(null)
</script>

<template>
  <div class="onboarding">
    <h2>欢迎使用 帕鲁世界终端</h2>
    <p class="lead">首次使用请先选择运行模式（之后可在 AstrBot 齿轮更改）：</p>
    <div class="cards">
      <button type="button" class="mode-card" data-mode="single"
        :class="{ picked: selected === 'single' }" @click="selected = 'single'">
        <span class="t">单服务器</span>
        <span class="d">唯一服务器；群授权走「授权群名单 + /pal whereami」。</span>
      </button>
      <button type="button" class="mode-card" data-mode="multi"
        :class="{ picked: selected === 'multi' }" @click="selected = 'multi'">
        <span class="t">多服务器</span>
        <span class="d">多台服务器；用 /pal link 绑定切换。</span>
      </button>
    </div>
    <button type="button" class="confirm" :disabled="!selected"
      @click="selected && emit('confirm', selected)">确认并开始</button>
  </div>
</template>

<style scoped>
.onboarding { display: flex; flex-direction: column; gap: 16px; max-width: 720px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.mode-card { flex: 1 1 260px; display: flex; flex-direction: column; gap: 6px; padding: 16px;
  text-align: left; border: 1px solid var(--pw-border, #3a3a3a); border-radius: 10px;
  background: transparent; cursor: pointer; }
.mode-card.picked { border-color: var(--pw-accent, #6ea8fe); box-shadow: 0 0 0 1px var(--pw-accent, #6ea8fe); }
.mode-card .t { font-weight: 600; }
.mode-card .d { opacity: .75; font-size: .9em; }
.confirm { align-self: flex-start; padding: 8px 18px; border-radius: 8px; cursor: pointer; }
.confirm:disabled { opacity: .5; cursor: not-allowed; }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npm test -- ModeOnboarding`
Expected: PASS

- [ ] **Step 5: schema.ts 加 routing 字段 + SettingsPanel 隐藏/分叉/确认**

(a) `frontend/src/lib/schema.ts`：routing 的 OBJECT_SECTION fields 里加 `setup_confirmed` bool 字段（**照 server_admin 里 `require_confirmation` 那种 bool 字段的写法**，type `'bool'`）——加进 fields 是为让 `collectBody` 的 `coerce('bool', …)` 回传它（否则被逐字段重建丢弃）。

(b) `frontend/src/components/SettingsPanel.vue`：

- `visibleSections`（:38-43）恒隐藏 setup_confirmed（与 world_mode 同型）：

```ts
  const hide = new Set<string>(['world_mode', 'setup_confirmed'])
```

- 加 computed（`worldMode` 附近 :33）：

```ts
const needsOnboarding = computed(() => (state.sections.routing?.setup_confirmed) !== true)
```

- 加确认处理（`save` 附近）：

```ts
function onConfirmMode(mode: 'single' | 'multi') {
  if (!state.sections.routing) state.sections.routing = {}
  state.sections.routing.world_mode = mode
  state.sections.routing.setup_confirmed = true
  save()
}
```

- import 组件（`<script setup>` 顶部）：`import ModeOnboarding from './ModeOnboarding.vue'`

- 模板 ready 分支（`<template v-else>` :151 内）分叉——在 `chapter-head` 之前包一层：

```html
    <template v-else>
      <ModeOnboarding v-if="needsOnboarding" @confirm="onConfirmMode" />
      <template v-else>
        <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
          <span class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }} · 切换请到插件齿轮配置</span>
        </div>
        <!-- …现有 isAccess / isPermissions / SectionForm / savebar 全部移进这层 v-else… -->
      </template>
    </template>
```

- [ ] **Step 6: 写 SettingsPanel onboarding 失败测试 + 审计既有 fixture**

(a) `frontend/src/components/SettingsPanel.test.ts` 的 `cfg()`（:17）routing 加 `setup_confirmed: true`（代表已确认安装）：

```ts
  routing: { access_mode: 'restricted', default_server: '', setup_confirmed: true },
```

(b) **审计所有 `mountAccess({ routing: {...} })` 的 override**（:167/:179/:197/:215/:222/:227/:232/:250 一带，override 整体替换 routing）：每个 routing override 补 `setup_confirmed: true`。

(c) 加 onboarding 用例：

```ts
it('未确认时显示引导屏、取代正常章节', async () => {
  const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', setup_confirmed: false } })
  expect(w.findComponent({ name: 'ModeOnboarding' }).exists()).toBe(true)
  expect(w.text()).not.toContain('保存设置')
})

it('已确认时不显引导屏、显示正常章节', async () => {
  const w = await mountAccess()  // cfg() 已 setup_confirmed:true
  expect(w.findComponent({ name: 'ModeOnboarding' }).exists()).toBe(false)
  expect(w.text()).toContain('保存设置')
})

it('确认写 world_mode + setup_confirmed 并保存', async () => {
  const post = (window.AstrBotPluginPage!.apiPost as any)
  const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', setup_confirmed: false } })
  await w.findComponent({ name: 'ModeOnboarding' }).vm.$emit('confirm', 'multi')
  await flushPromises()
  const body = post.mock.calls.at(-1)![1]
  expect(body.routing.world_mode).toBe('multi')
  expect(body.routing.setup_confirmed).toBe(true)
})
```

（`ModeOnboarding` 需 `name`：SFC 默认以文件名为 name，`findComponent({ name: 'ModeOnboarding' })` 可用；若不稳，改用 `findComponent(ModeOnboarding)` 并 import。）

- [ ] **Step 7: 跑前端全量 + 构建**

Run: `cd frontend && npm test`
Expected: PASS（含既有 SettingsPanel/collect 用例——确认 fixture 审计无遗漏）
Run: `cd frontend && npm run build`
Expected: `pages/settings/**` 刷新、无报错

- [ ] **Step 8: 提交**

```bash
git add frontend/src/ pages/settings/
git commit -m "feat(fe): 首次引导屏 ModeOnboarding——未确认取代正常章节，确认写 world_mode+setup_confirmed"
```

---

### Task 4: 文档 + 全库终检（版本号不变）

**Files:**
- Modify: `docs/commands.md`（首次设置闸说明）
- Modify: `docs/configuration.md`（setup_confirmed 说明）
- Test（回归）: `tests/unit/readme_test.py`

- [ ] **Step 1: 文档**

- `docs/commands.md`：加一段「首次使用」——全新安装须先在插件设置页选运行模式并确认，未确认时除 `/pal help`、`/pal whoami`、`/pal whereami` 外的命令返回引导语。
- `docs/configuration.md`：`routing.setup_confirmed`（bool，默认 false）说明——首次设置确认标志，一般由设置页自动写入；未确认时命令闸生效。

- [ ] **Step 2: 核 readme 中文锚点（若改了 README）**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -v`
Expected: PASS（本任务默认不改 README；若为叙述完整改了 README，须核锚点短语不缺失）

- [ ] **Step 3: 全库终检**

Run: `cd frontend && npm test && npm run build`
Run: `./.venv/Scripts/python.exe -m pytest -q`
Run: `./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal`
Run: `git status --porcelain pages/settings`（应为空 = 无 drift）
Expected: 全 PASS + pages/settings 无未提交漂移

- [ ] **Step 4: 确认版本未动**

Run: `git diff main -- metadata.yaml palworld_terminal/__init__.py`（应无版本号改动；本 Phase 版本不变）
Expected: 无 version 行改动

- [ ] **Step 5: 提交**

```bash
git add docs/
git commit -m "docs: 首次设置闸与 setup_confirmed 说明（版本号不变）"
```

---

## Self-Review

**Spec coverage：**
- §4.1 标志 → Task 1（RoutingConfig.setup_confirmed + 严格解析 + schema）。
- §4.2 命令闸 → Task 2（`_setup_gate` 双插桩、逗口集、门序、locale）。
- §4.3 配置管道 → Task 1（嵌 routing，config_view/`_TOP_KEYS` 免改，勘探已证）。
- §5/§6 读侧 hydrate + 写侧 → Task 3（读侧靠 applyConfig 整体展开 routing 天然可用；写侧靠 schema field + coerce bool；确认 onConfirmMode 写 world_mode+setup_confirmed 走 save）。
- §7 引导屏 UX → Task 3（ModeOnboarding，内部选择态初值 null、点选前禁用、needsOnboarding `!==true`）。
- §9 测试波及（跨端）→ Task 2（Python 冒烟 fixture + 未确认闸集成）+ Task 3（前端 cfg()/override 审计 + onboarding 用例）。
- §10 锚定 → Task 2（`_SETUP_EXEMPT ⊆ FLAT_ACTIONS` + 穷举 `PAL_REGISTERED\_SETUP_EXEMPT`）。
- §11 版本不变 → Task 4（终检确认版本未动）。

**Placeholder scan：** 无 TBD/TODO；schema.ts 字段与 SettingsPanel 模板分叉给了"照 X 写法"的明确参照（require_confirmation bool 范式 / world_mode 隐藏范式），因目标文件已存在、范式已在库中，非占位。

**Type consistency：** `RoutingConfig.setup_confirmed: bool`、`_setup_gate(command_str) -> str|None`、`_guarded(self, call, command_str)`、前端 `needsOnboarding`、`onConfirmMode(mode)`、ModeOnboarding emit `confirm:'single'|'multi'`——跨任务一致。严格布尔后端 `is True`/前端 coerce `=== true` 同向。

**依赖顺序：** Task 1（字段）→ Task 2（闸消费字段 + 冒烟 fixture）→ Task 3（前端读写，独立于 2 但逻辑在 1 之后）→ Task 4（文档+终检）。
