# 单 / 多服务器模式彻底分道 + 设置页模式感知 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `world_mode`（single/multi）行为彻底分道——单模式做成干净单服务器体验（restricted 真正生效、授权走配置名单、写命令不受名单约束），并让自定义设置页按模式纯呈现；默认改 single。

**Architecture:** 沿用 v0.9.6 配置派生谓词风格。后端：`RoutingService.resolve` single 分支查新配置字段 `single_allowed_groups`（顶层 template_list，挂 `RoutingConfig`），写路径经 `for_write=True` 绕过读名单；新增元命令 `/pal whereami`。前端：`worldMode` computed 驱动分叉渲染（单台表单 / 命令树去 link / 授权群名单区），无模式开关。**无用户 → 无迁移**（见 memory `no-existing-users-no-migration`），默认直接改。

**Tech Stack:** Python 3.10+（AstrBot 插件，相对导入红线）、pytest、Vue 3 + TS、Vitest；构建产物 `pages/settings/**` 入库须 no-drift + LF。

## Global Constraints

- **无迁移 / 无向后兼容**（插件尚无真实用户）：默认值/结构直接改，不写迁移护栏。
- **相对导入红线**：`palworld_terminal` 包内严禁绝对自导入（`from palworld_terminal…`），用相对导入；config 层跨 application/presentation 用函数体内相对 import。
- **Windows 测试命令**：`./.venv/Scripts/python.exe -m pytest`（裸 `python` 被拦）。lint：`./.venv/Scripts/python.exe -m ruff check .` + `./.venv/Scripts/python.exe -m mypy palworld_terminal`。
- **前端**：`cd frontend && npm test`（vitest）；改前端源后 `cd frontend && npm run build`（内置 normalize-eol 统一 LF）刷新 `pages/settings/**`，否则 CI no-drift 红。
- **git 提交不出现 Claude**（正文与尾行均不提及）。
- **命令锚定三真相源全等**：`command_registry._NON_LOCKABLE` ↔ `config._NON_LOCKABLE` ↔ 测试 literal；`FLAT_ACTIONS`↔`HELP_TEXT`↔前端 `PAL_TREE`↔`COMMAND_META` 全等；注册数硬编码测试须同步。
- **readme 中文锚点**：改 README/docs 中文用词须核 `tests/unit/readme_test.py` 锚点短语，勿漏。
- **版本四源** v0.9.7：`metadata.yaml`、`main.py @register`、`palworld_terminal/__init__.py __version__`、`README` badge + `tests/unit/phase1_smoke_test.py:19` 断言。
- **门序铁律**：写命令 `permission_admins` admin 硬门独立于 resolve；本期只让单模式写**绕过读名单**，不改 admin 硬门与多模式行为。
- **拒绝文案红线**：`single_not_authorized` 文案不得含 `/pal link add`（`locale_rework_test.py:16`）或 `/pal use`（`:12-13`）。

---

### Task 1: 新增元命令 `/pal whereami`（后端 + 前端锚定 + 构建）

新增扁平元命令，镜像 `whoami`：`feat_group=core`、`gate=read`、入 `_NON_LOCKABLE`、非 `@_gated`、经 `_guarded` 注册。回显当前群 UMO，恒可用，两模式都出。跨端锚定强制后端 + `schema.ts` PAL_TREE 同任务落地。

**Files:**
- Modify: `palworld_terminal/presentation/command_registry.py`（FLAT_ACTIONS/_NON_LOCKABLE/HELP_TEXT）
- Modify: `palworld_terminal/presentation/commands.py`（whereami 方法）
- Modify: `main.py`（handler + 注释计数）
- Modify: `palworld_terminal/presentation/locale.py`（whereami / whereami_no_umo）
- Modify: `palworld_terminal/config.py:150-155`（内联 _NON_LOCKABLE）
- Modify: `frontend/src/lib/schema.ts`（PAL_TREE 加 whereami 节点）
- Build: `pages/settings/**`
- Test: `tests/unit/commands_permissions_test.py`、`command_registry_hierarchy_test.py`、`command_names_test.py`、`config_server_admin_test.py`、`namespace_runtime_smoke_test.py`、`frontend/src/lib/schema.test.ts`

**Interfaces:**
- Produces: `Commands.whereami(umo: str) -> str`（async）；`plugin.whereami(event)` handler；locale 键 `whereami`（含 `{umo}`）、`whereami_no_umo`。

- [ ] **Step 1: 写失败测试（whereami 回显 UMO / 空兜底）**

`tests/unit/commands_permissions_test.py` 追加（仿其 whoami 用例）：

```python
async def test_whereami_returns_umo():
    c = _commands()  # 复用本文件已有的 Commands 构造 helper
    assert "aiocqhttp:GroupMessage:42" in await c.whereami("aiocqhttp:GroupMessage:42")

async def test_whereami_empty_umo_falls_back():
    c = _commands()
    out = await c.whereami("")
    assert "aiocqhttp" not in out  # 空 UMO 走兜底、不回显空串
```

（若该文件无 `_commands()` helper，就近仿 `test_whoami_*` 的构造方式；whereami 无依赖 routing/repo，构造可最简。）

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_permissions_test.py -k whereami -v`
Expected: FAIL（`AttributeError: 'Commands' object has no attribute 'whereami'`）

- [ ] **Step 3: 加 locale 键**

`palworld_terminal/presentation/locale.py`，在 `whoami_no_sender`（:42）后加：

```python
    "whereami": "本群标识（UMO）：{umo}（把它交给管理员，在设置页「连接」章的授权群名单中添加即可授权本群查询）",
    "whereami_no_umo": "当前场景无法识别群标识，请在目标群聊里再试。",
```

- [ ] **Step 4: 加 Commands.whereami**

`palworld_terminal/presentation/commands.py`，在 `whoami`（:448-451）后加（**无 `@_gated`**）：

```python
    async def whereami(self, umo: str) -> str:
        if not umo:
            return L("whereami_no_umo")
        return L("whereami", umo=umo)
```

- [ ] **Step 5: 注册表三处（FLAT_ACTIONS / _NON_LOCKABLE / HELP_TEXT）**

`palworld_terminal/presentation/command_registry.py`：
- FLAT_ACTIONS（:64 whoami 行后）加：`    "whereami": ("whereami", "core", "read"),`
- _NON_LOCKABLE（:97）`+ ["help", "whoami", "confirm"]` → `+ ["help", "whoami", "whereami", "confirm"]`
- HELP_TEXT（:132 whoami 行后）加：`    "whereami": "查看当前群标识（UMO）",`

- [ ] **Step 6: config 内联 _NON_LOCKABLE 同步**

`palworld_terminal/config.py:154`：`"help", "whoami", "confirm",` → `"help", "whoami", "whereami", "confirm",`

- [ ] **Step 7: main.py handler + 计数注释**

`main.py`，在 `whoami` handler（:478-482）后加：

```python
    @pal.command("whereami")
    async def whereami(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.whereami(self._umo(event)))
        )
```

并把 :412-413 注释「6 扁平（rank/online/me/whoami/help/confirm）= 11 注册」改为「7 扁平（rank/online/me/whoami/whereami/help/confirm）= 12 注册」。

- [ ] **Step 8: 前端 PAL_TREE 节点**

`frontend/src/lib/schema.ts`，PAL_TREE 里 whoami 节点（约 :141）后加：

```ts
  {"group": null, "path": "whereami", "label": "本群标识", "enableConfigurable": false, "adminConfigurable": false, "adminForced": false, "danger": false},
```

- [ ] **Step 9: 更新锚定测试计数 / literal**

- `tests/unit/command_registry_hierarchy_test.py:18-24`：11 首词集加 `"whereami"`、`assert len(...) == 11` → `12`。
- `tests/unit/command_names_test.py:17-22`：`_NON_LOCKABLE_PATHS` literal 加 `"whereami"`；`:33` 注册数断言 `11` → `12`。
- `tests/unit/config_server_admin_test.py:31-36`：`_non_lockable` frozenset 加 `"whereami"`。
- `tests/unit/namespace_runtime_smoke_test.py`：calls 列表加 `(plugin.whereami, "whereami")`（仿 :152 whoami 行）。
- `frontend/src/lib/schema.test.ts`：若断言 PAL_TREE 长度/路径集，同步加 whereami。

- [ ] **Step 10: 后端全绿 + 前端全绿 + 构建**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_permissions_test.py tests/unit/command_registry_hierarchy_test.py tests/unit/command_names_test.py tests/unit/config_server_admin_test.py tests/unit/formatters_hierarchy_test.py tests/unit/command_permissions_meta_test.py tests/unit/frontend_pal_commands_test.py tests/unit/namespace_runtime_smoke_test.py -v`
Expected: PASS（HELP_TEXT↔PAL_COMMAND_STRINGS 双等、COMMAND_META 派生、前端跨端锚定均自动含 whereami）
Run: `cd frontend && npm test`
Expected: PASS
Run: `cd frontend && npm run build`
Expected: `pages/settings/**` 刷新，无报错

- [ ] **Step 11: 提交**

```bash
git add palworld_terminal/ main.py frontend/src/ tests/ pages/settings/
git commit -m "feat: 新增元命令 /pal whereami 回显当前群 UMO（供单模式授权名单）"
```

---

### Task 2: `single_allowed_groups` 配置解析（config.py）

新增顶层 template_list `single_allowed_groups`（行 `{umo, note}`）的解析，挂 `RoutingConfig.single_allowed_groups`。仅解析，无消费方，任务结束绿。

**Files:**
- Modify: `palworld_terminal/config.py`（AllowedGroupEntry / _parse_single_allowed_groups / RoutingConfig 字段 / parse_config 接线）
- Test: `tests/unit/config_permissions_test.py`（新增用例）

**Interfaces:**
- Produces: `AllowedGroupEntry(umo: str, note: str)`；`RoutingConfig.single_allowed_groups: list[AllowedGroupEntry]`（默认 `[]`）。

- [ ] **Step 1: 写失败测试**

`tests/unit/config_permissions_test.py` 追加：

```python
def test_single_allowed_groups_parsed_and_deduped():
    raw = {"single_allowed_groups": [
        {"umo": "aiocqhttp:GroupMessage:1", "note": "主群"},
        {"umo": "  aiocqhttp:GroupMessage:2  ", "note": ""},
        {"umo": "aiocqhttp:GroupMessage:1", "note": "重复"},  # 去重
        {"umo": "", "note": "空"},                              # 去空
    ]}
    cfg = parse_config(raw, {})
    umos = [e.umo for e in cfg.routing.single_allowed_groups]
    assert umos == ["aiocqhttp:GroupMessage:1", "aiocqhttp:GroupMessage:2"]

def test_single_allowed_groups_default_empty():
    cfg = parse_config({}, {})
    assert cfg.routing.single_allowed_groups == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_permissions_test.py -k single_allowed_groups -v`
Expected: FAIL（`AttributeError: 'RoutingConfig' object has no attribute 'single_allowed_groups'`）

- [ ] **Step 3: dataclass + 解析函数 + 字段 + 接线**

`palworld_terminal/config.py`：
- `AdminEntry`（:128-131）后加：

```python
@dataclass(slots=True)
class AllowedGroupEntry:
    umo: str
    note: str
```

- `RoutingConfig`（:63-67）加字段：

```python
@dataclass(slots=True)
class RoutingConfig:
    access_mode: AccessMode
    default_server: str
    world_mode: str = "multi"  # "single" | "multi"
    single_allowed_groups: list[AllowedGroupEntry] = field(default_factory=list)
```

- 新增解析函数（放 `_parse_permissions` 附近）：

```python
def _parse_single_allowed_groups(raw: Mapping) -> list[AllowedGroupEntry]:
    out: list[AllowedGroupEntry] = []
    seen: set[str] = set()
    for item in raw.get("single_allowed_groups", []) or []:
        if not isinstance(item, Mapping):
            continue
        umo = str(item.get("umo", "") or "").strip()
        if not umo or umo in seen:
            continue
        seen.add(umo)
        out.append(AllowedGroupEntry(umo=umo, note=str(item.get("note", "") or "").strip()))
    return out
```

- `parse_config` 的 `RoutingConfig(...)` 构造（:425-429）加实参：

```python
        routing=RoutingConfig(
            access_mode=AccessMode(str(r.get("access_mode", "restricted") or "restricted")),
            default_server=str(r.get("default_server", "") or ""),
            world_mode=_one_of(r.get("world_mode", "multi"), frozenset({"single", "multi"}), "multi"),
            single_allowed_groups=_parse_single_allowed_groups(raw),
        ),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_permissions_test.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/config.py tests/unit/config_permissions_test.py
git commit -m "feat: 解析 single_allowed_groups 配置（挂 RoutingConfig）"
```

---

### Task 3: `single_allowed_groups` schema + config_view 往返

`_conf_schema.json` 新增顶层 template_list（AstrBot 原生页可渲染），`config_view.py` 四常量接线（含 `_TOP_KEYS`，否则含该键的保存被判 invalid_shape 拒绝）。

**Files:**
- Modify: `_conf_schema.json`（顶层 single_allowed_groups）
- Modify: `palworld_terminal/presentation/config_view.py:17-44`（四常量）
- Test: `tests/unit/conf_schema_test.py`、`tests/unit/config_view_permissions_test.py`

**Interfaces:**
- Consumes: `AllowedGroupEntry`（Task 2）。
- Produces: schema 键 `single_allowed_groups`；config_view row_id 前缀 `sag`。

- [ ] **Step 1: 写失败测试（schema 存在 + 顶层非嵌 routing + 往返 row_id）**

`tests/unit/conf_schema_test.py` 追加（仿 :31-33 group_bindings 顶层断言 + :85-97 permission_admins 形态）：

```python
def test_single_allowed_groups_is_top_level_template_list():
    s = _schema()  # 复用本文件读取 _conf_schema.json 的 helper
    assert "single_allowed_groups" not in s["routing"]["items"]  # 不可嵌 routing
    sag = s["single_allowed_groups"]
    assert sag["type"] == "template_list"
    assert sag["default"] == []
    items = sag["templates"]["group"]["items"]
    assert set(items) == {"umo", "note"}
    assert sag["templates"]["group"]["display_item"] == "umo"
```

`tests/unit/config_view_permissions_test.py` 追加（仿 permission_admins 往返 :11-13 + strip :42-45）：

```python
def test_single_allowed_groups_roundtrip_row_id():
    cfg = {"single_allowed_groups": [{"umo": "aiocqhttp:GroupMessage:1", "note": "x"}]}
    out = redact_config(cfg)
    assert out["single_allowed_groups"][0]["__row_id"] == "sag-0"
    assert out["single_allowed_groups"][0]["umo"] == "aiocqhttp:GroupMessage:1"

def test_single_allowed_groups_strips_meta():
    body = {"single_allowed_groups": [{"__row_id": "sag-0", "umo": "u", "note": "n", "junk": "x"}]}
    cleaned = _strip_meta(body)  # 复用本文件 import 的 strip 入口
    assert set(cleaned["single_allowed_groups"][0]) == {"umo", "note"}
```

（helper 名以本文件实际为准；redact/strip 入口与现有 permission_admins 用例一致。）

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/conf_schema_test.py tests/unit/config_view_permissions_test.py -k single_allowed_groups -v`
Expected: FAIL

- [ ] **Step 3: schema 顶层新增**

`_conf_schema.json`，在 `permission_admins`（:143-157）后加同级键：

```json
  "single_allowed_groups": {
    "type": "template_list",
    "description": "单世界模式授权群名单：仅 world_mode=single 且 access_mode=restricted 时生效，列出的会话（群/私聊）才能查询唯一服务器。UMO 可在群里发 /pal whereami 获取。（多世界模式忽略本表）",
    "default": [],
    "templates": {
      "group": {
        "name": "授权群",
        "display_item": "umo",
        "items": {
          "umo": { "type": "string", "description": "会话标识 unified_msg_origin，如 aiocqhttp:GroupMessage:123456（群里发 /pal whereami 可查）", "default": "" },
          "note": { "type": "string", "description": "备注（可选，明文存储于配置文件，勿填真实姓名/联系方式等敏感信息）", "default": "" }
        }
      }
    }
  },
```

- [ ] **Step 4: config_view 四常量**

`palworld_terminal/presentation/config_view.py`：
- `_LIST_SECTIONS`（:17-18）加 `"single_allowed_groups"`。
- `_ROW_ID_PREFIX`（:19-20）加 `"single_allowed_groups": "sag"`。
- `_SECTION_KEYS`（:31-38）加 `"single_allowed_groups": {"umo", "note"},`。
- `_TOP_KEYS`（:40-44）加 `"single_allowed_groups"`。

- [ ] **Step 5: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/conf_schema_test.py tests/unit/config_view_permissions_test.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add _conf_schema.json palworld_terminal/presentation/config_view.py tests/
git commit -m "feat: single_allowed_groups schema（顶层）+ config_view 往返闭合"
```

---

### Task 4: 单模式 restricted 真正生效（RoutingService + for_write 形参 + 文案 + 删架空告警）

single 分支 restricted 改查 `single_allowed_groups`；`resolve` 加 `for_write` 形参（仅 single 分支消费，读默认受控）；新增 `single_not_authorized` 文案；删 `single_restricted_warning` 方法/键/调用，改成空名单运维告警。**写路径 for_write 穿线在 Task 5。**

**Files:**
- Modify: `palworld_terminal/application/routing_service.py`（resolve single 分支 + for_write + 删 single_restricted_warning）
- Modify: `palworld_terminal/presentation/locale.py`（加 single_not_authorized、删 single_restricted_warning）
- Modify: `main.py:143-157`（_log_startup_warnings：删架空告警调用、加空名单告警）
- Test: `tests/unit/routing_world_mode_test.py`（主测，反转 + 删 + `_cfg` 增参 + 新增名单用例）、`tests/unit/main_link_single_test.py`（删告警断言）

**Interfaces:**
- Consumes: `RoutingConfig.single_allowed_groups`（Task 2）、`AccessMode`。
- Produces: `RoutingService.resolve(umo, override, is_group, *, for_write: bool = False)`；locale `single_not_authorized`。

- [ ] **Step 1: 改主测 `routing_world_mode_test.py`（先让它表达新契约）**

`tests/unit/routing_world_mode_test.py`：
- `_cfg` helper（:32）增形参 `single_allowed_groups=None`，构造 `RoutingConfig(..., single_allowed_groups=single_allowed_groups or [])`（import `AllowedGroupEntry`）。
- `:69-76` 私聊放宽用例：改为「single+restricted+私聊 umo 不在名单 → error 非空（拒）」。
- `:79/:87/:104` 三用例：`_cfg` 传 `access=OPEN`（保持「忽略 override/binding/多台」语义不被授权门干扰），断言不变。
- `:117-133` 三 `single_restricted_warning` 用例：整段删除。
- 新增四用例：

```python
async def test_single_restricted_umo_in_allowlist_resolves():
    svc = _svc(_cfg(world_mode="single", access=RESTRICTED,
                    single_allowed_groups=[AllowedGroupEntry("g1", "")]))
    res = await svc.resolve("g1", None, True)
    assert res.server is not None and res.error is None

async def test_single_restricted_umo_not_in_allowlist_denied():
    svc = _svc(_cfg(world_mode="single", access=RESTRICTED,
                    single_allowed_groups=[AllowedGroupEntry("g1", "")]))
    res = await svc.resolve("g2", None, True)
    assert res.server is None and res.error  # single_not_authorized

async def test_single_restricted_empty_allowlist_denies_all():
    svc = _svc(_cfg(world_mode="single", access=RESTRICTED, single_allowed_groups=[]))
    res = await svc.resolve("g1", None, True)
    assert res.server is None  # fail-closed

async def test_single_open_ignores_allowlist():
    svc = _svc(_cfg(world_mode="single", access=OPEN, single_allowed_groups=[]))
    res = await svc.resolve("g1", None, True)
    assert res.server is not None
```

（`_svc`/`RESTRICTED`/`OPEN` 以本文件既有 helper 为准；`_svc` 需 ≥1 就绪服务器。）

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/routing_world_mode_test.py -v`
Expected: FAIL（新用例红 + `single_restricted_warning` AttributeError 之前的用例已删）

- [ ] **Step 3: 改 resolve single 分支 + for_write**

`palworld_terminal/application/routing_service.py`，`resolve`（:42）签名与 single 分支（:46-57）改为：

```python
    async def resolve(
        self, umo: str, override: str | None, is_group: bool, *, for_write: bool = False
    ) -> Resolution:
        # 单世界模式：恒解析到唯一就绪服务器。restricted 读授权查 single_allowed_groups；
        # 写命令(for_write)绕过读名单（admin 硬门独立把守）。忽略 @override 与群绑定。
        if self._cfg.routing.world_mode == "single":
            ready = self._ready_servers()
            if not ready:
                return Resolution(None, L("no_server_configured"))
            srv = ready[0]
            if self._cfg.routing.access_mode is AccessMode.RESTRICTED and not for_write:
                allowed = {e.umo for e in self._cfg.routing.single_allowed_groups}
                if umo not in allowed:
                    return Resolution(None, L("single_not_authorized"))
            if len(ready) > 1 and not self._single_multi_warned:
                self._single_multi_warned = True
                _log.warning(
                    "world_mode=single 但检测到 %d 台就绪服务器，仅使用首台「%s」；"
                    "其余将被忽略。若需多服务器请改用 world_mode=multi。",
                    len(ready), ready[0].server_id,
                )
            return Resolution(srv, None)
        # ...multi 五步不变...
```

删除 `single_restricted_warning()` 方法（:113-120）。

- [ ] **Step 4: locale 增删**

`palworld_terminal/presentation/locale.py`：
- 删 `single_restricted_warning` 键（:11-14）。
- 加：

```python
    "single_not_authorized": "本群未被授权查询本服务器。请在群里发 /pal whereami 获取本群标识，交管理员在插件设置页「连接」章的授权群名单中添加。",
```

- [ ] **Step 5: main.py 启动告警替换**

`main.py`，确认顶部已 import `AccessMode`（若无，加 `from palworld_terminal.domain.enums import AccessMode`——与现有 `from palworld_terminal...` 顶层入口导入风格一致）。`_log_startup_warnings`（:149-151）把：

```python
        warn = c.routing.single_restricted_warning()
        if warn is not None:
            _log.warning(warn)
```

替换为：

```python
        r = c.config.routing
        if (r.world_mode == "single" and r.access_mode is AccessMode.RESTRICTED
                and not r.single_allowed_groups):
            _log.warning(
                "单世界模式 + restricted 但授权群名单为空：当前所有群/私聊都无法查询。"
                "请在群里发 /pal whereami 获取群标识，在设置页「连接」章的授权群名单中添加。"
            )
```

同步更新 :144-145 docstring（删「single+restricted 架空」表述）。

- [ ] **Step 6: 改 main_link_single_test.py**

`tests/unit/main_link_single_test.py`：删「single+restricted 启动告警」相关断言（:132 一带）；保留 link 单模式守卫、multi 无告警等用例；显式 `world_mode="multi"` 传参用例复核不受影响。

- [ ] **Step 7: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/routing_world_mode_test.py tests/unit/main_link_single_test.py tests/integration/routing_test.py -v`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add palworld_terminal/application/routing_service.py palworld_terminal/presentation/locale.py main.py tests/
git commit -m "feat: 单模式 restricted 真正生效（查 single_allowed_groups）+ 删架空告警 + resolve for_write 形参"
```

---

### Task 5: 写路径 `for_write=True` 穿线（6 处）

让单模式写命令绕过读名单。写路径 6 处 resolve 调用传 `for_write=True`。漏一处=fail-closed（管理员被过度限制），有测试兜底。

**Files:**
- Modify: `palworld_terminal/application/admin_service.py:69,219`
- Modify: `palworld_terminal/presentation/commands.py:485,536,549,588`
- Test: `tests/unit/admin_service_test.py`（或新增：单模式非授权群写命令仍放行）

**Interfaces:**
- Consumes: `resolve(..., for_write=True)`（Task 4）。

- [ ] **Step 1: 写失败测试（单模式非授权群管理员写命令仍放行）**

`tests/unit/admin_service_test.py` 追加（构造 world_mode=single + restricted + 空名单 + 就绪服务器）：

```python
async def test_single_restricted_write_bypasses_allowlist():
    svc = _admin_service(world_mode="single", access="restricted", single_allowed_groups=[])
    # 非授权群（空名单）里管理员写命令仍能解析到服务器并执行（不被读名单拒）
    res = await svc.announce("admin:1", "unlisted_group", True, "hello")
    assert res.message_key != "admin_resolve_failed"
```

（`_admin_service` helper 以本文件既有构造为准；关键是 routing 为 single+restricted+空名单。若 helper 不便加参，可直接构造 RoutingService + AdminService。）

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/admin_service_test.py -k bypass -v`
Expected: FAIL（`admin_resolve_failed`——for_write 未穿线，被读名单拒）

- [ ] **Step 3: 穿线 6 处**

- `admin_service.py:69`：`resolution = await self._routing.resolve(umo, None, is_group, for_write=True)`
- `admin_service.py:219`：同上。
- `commands.py:485`：`resolution = await self._routing.resolve(umo, None, is_group, for_write=True)`
- `commands.py:536`：同上。
- `commands.py:549`：同上。
- `commands.py:588`：`resolution = await self._routing.resolve(p.umo, None, is_group, for_write=True)`

- [ ] **Step 4: 跑测试确认通过 + 写命令回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/admin_service_test.py tests/unit/commands_permissions_test.py tests/unit/confirmation_store_test.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/admin_service.py palworld_terminal/presentation/commands.py tests/
git commit -m "feat: 单模式写命令 for_write=True 绕过读名单（6 处 resolve）"
```

---

### Task 6: `world_mode` 默认 multi → single（三源 + 文案清理）

无用户，直接改三处默认；清理已成假的「架空」文案。

**Files:**
- Modify: `palworld_terminal/config.py:67,428`
- Modify: `_conf_schema.json:31`（default + description 重写）
- Modify: `frontend/src/lib/schema.ts:36`（default + hint 清理）+ build
- Test: `tests/unit/config_world_mode_test.py`

- [ ] **Step 1: 改测试断言（默认 single）**

`tests/unit/config_world_mode_test.py`：
- `:10-11` `test_world_mode_default_multi` → 断言默认 `"single"`（改名 `_default_single`）。
- `:18-19` 非法值兜底 → `"single"`。
- `:22-27` schema 默认断言 `wm["default"] == "single"`。

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_world_mode_test.py -v`
Expected: FAIL

- [ ] **Step 3: 改三源默认 + 文案**

- `config.py:67`：`world_mode: str = "single"`。
- `config.py:428`：`world_mode=_one_of(r.get("world_mode", "single"), frozenset({"single", "multi"}), "single"),`
- `_conf_schema.json:31`：`"default": "single"`，description 重写为：`"运行模式（主开关）：single 单世界（唯一服务器，群授权走插件设置页「连接」章的授权群名单 + /pal whereami）；multi 多世界（多台服务器，用 /pal link 绑定切换）。切换模式后请到插件设置页配置对应模式。"`（删除旧「⚠️ single + restricted…架空」句）。
- `frontend/src/lib/schema.ts:36`：`default: 'single'`，hint 删除「⚠️ single + restricted 并存时访问控制不生效」子句（保留 multi/single 说明）。

- [ ] **Step 4: 跑测试 + 全库回归（抓默认翻转的连带）**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（若有未显式设 world_mode 而依赖 multi 行为的用例翻红，就地给它显式 `world_mode="multi"` 或修正断言——记录到 SDD 账本）

- [ ] **Step 5: 前端构建**

Run: `cd frontend && npm test && npm run build`
Expected: PASS + `pages/settings/**` 刷新

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/config.py _conf_schema.json frontend/src/ pages/settings/ tests/
git commit -m "feat: world_mode 默认改 single（无用户免迁移）+ 清理架空文案"
```

---

### Task 7: 前端 —— worldMode + 模式标识 + routing 字段隐藏 + 兜底 seed

**Files:**
- Modify: `frontend/src/components/SettingsPanel.vue`（worldMode computed / mode badge / 字段过滤 / seed）
- Build: `pages/settings/**`
- Test: `frontend/src/components/SettingsPanel.test.ts`

**Interfaces:**
- Produces: `worldMode` computed；隐藏 world_mode（恒）/ default_server（single）字段但保留其值回传。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/SettingsPanel.test.ts` 追加（mock config routing 带 `world_mode`）：

```ts
it('single 模式隐藏 world_mode/default_server 字段但 collect 仍回传 world_mode', async () => {
  const wrapper = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', world_mode: 'single' } })
  // routing 表单不渲染 world_mode / default_server 标签
  expect(wrapper.text()).not.toContain('默认服务器')
  // 顶部模式标识
  expect(wrapper.text()).toContain('单服务器')
})
```

并对 `collectBody` 加断言（`frontend/src/lib/collect.test.ts` 或本文件）：`collectBody(state).routing` 恒含 `world_mode`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- SettingsPanel`
Expected: FAIL

- [ ] **Step 3: 实现**

`frontend/src/components/SettingsPanel.vue`：
- `<script>` 加：

```ts
const worldMode = computed(() => (state.sections.routing?.world_mode as string) ?? 'multi')
const singleRestricted = computed(() =>
  worldMode.value === 'single' && ((state.sections.routing?.access_mode as string) ?? 'restricted') === 'restricted')
const visibleSections = computed(() => currentSections.value.map((s) => {
  if (s.key !== 'routing') return s
  const hide = new Set<string>(['world_mode'])           // 页面无模式开关：恒隐藏 world_mode
  if (worldMode.value === 'single') hide.add('default_server')
  return { ...s, fields: s.fields.filter((f) => !hide.has(f.key)) }
}))
```

- `applyConfig`（:57 后）加 seed（防空值 coerce 成 '' 撞枚举校验）：

```ts
  if (!state.sections.routing) state.sections.routing = {}
  if (!state.sections.routing.world_mode) state.sections.routing.world_mode = 'multi'
```

- 模板 chapter-head（:126）改：

```html
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
        <span class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }} · 切换请到插件齿轮配置</span>
      </div>
```

- 模板 SectionForm 循环（:165）`v-for="sec in currentSections"` → `v-for="sec in visibleSections"`。
- 加 `.mode-badge` 样式（scoped，仿现有 muted chip 风格）。

- [ ] **Step 4: 跑测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: PASS + 产物刷新

- [ ] **Step 5: 提交**

```bash
git add frontend/src/ pages/settings/
git commit -m "feat(fe): 模式感知——worldMode + 只读模式标识 + 隐藏 world_mode/default_server 字段"
```

---

### Task 8: 前端 —— 单模式单台服务器表单（不截断）

**Files:**
- Modify: `frontend/src/components/ServerCard.vue`（可选 `hideDelete` prop）
- Modify: `frontend/src/components/SettingsPanel.vue`（服务器区 v-if 分叉 + single 占位）
- Build + Test: `SettingsPanel.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
it('single 模式渲染单台服务器表单、不显示增删、不截断 state.servers', async () => {
  const wrapper = await mountAccess(
    { routing: { access_mode: 'restricted', default_server: '', world_mode: 'single' } },
    { servers: [{ __row_id: 'srv-0', name: 'A' }, { __row_id: 'srv-1', name: 'B' }] })
  expect(wrapper.text()).not.toContain('添加服务器')  // 无「＋ 添加服务器」
  // 保存不丢第二台：collect 仍含 2 台
  expect(collectBody(wrapper.vm.$.setupState.state).servers).toHaveLength(2)
})
```

（断言 collect 保留全部服务器——不截断。具体取 state 的方式以本测试工具为准。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- SettingsPanel`
Expected: FAIL

- [ ] **Step 3: 实现**

`frontend/src/components/ServerCard.vue`：`defineProps` 加 `hideDelete?: boolean`；查看态移除按钮（:48）加 `v-if="!hideDelete"`。

`frontend/src/components/SettingsPanel.vue` 服务器 `<section>`（:129-134）改：

```html
        <section>
          <div class="group-head"><span class="t">服务器</span><span class="c">要监测的 Palworld 服务器</span></div>
          <template v-if="worldMode === 'multi'">
            <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || (s.__local_key as string)" :model-value="s" :index-label="'服务器 ' + pad(i + 1)"
              @update:model-value="(v) => { state.servers[i] = v; dirty = true }" @delete="state.servers.splice(i, 1); dirty = true" />
            <button class="add" @click="state.servers.push(emptyRow(SERVER_FIELDS)); dirty = true">＋ 添加服务器</button>
          </template>
          <ServerCard v-else :key="(state.servers[0].__row_id as string) || (state.servers[0].__local_key as string)"
            :model-value="state.servers[0]" :index-label="'服务器'" :hide-delete="true"
            @update:model-value="(v) => { state.servers[0] = v; dirty = true }" @delete="() => {}" />
        </section>
```

`applyConfig`（seed 之后）确保 single 有一台占位（不截断已有）：

```ts
  if (worldMode.value === 'single' && state.servers.length === 0) {
    state.servers = [emptyRow(SERVER_FIELDS)]
  }
```

- [ ] **Step 4: 跑测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: PASS + 产物刷新

- [ ] **Step 5: 提交**

```bash
git add frontend/src/ pages/settings/
git commit -m "feat(fe): 单模式单台服务器表单（编辑 servers[0]，绝不截断）"
```

---

### Task 9: 前端 —— 命令树单模式隐藏 link 组

**Files:**
- Modify: `frontend/src/components/CommandTree.vue`（hideGroups prop）
- Modify: `frontend/src/components/SettingsPanel.vue`（传 hideGroups）
- Build + Test: `frontend/src/components/CommandTree.test.ts`

- [ ] **Step 1: 写失败测试**

`frontend/src/components/CommandTree.test.ts` 追加：

```ts
it('hideGroups=[link] 时不渲染 link 组', () => {
  const wrapper = mount(CommandTree, { props: { modelValue: {}, hideGroups: ['link'] } })
  expect(wrapper.text()).not.toContain('服务器授权')  // GROUP_LABELS.link
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- CommandTree`
Expected: FAIL

- [ ] **Step 3: 实现**

`frontend/src/components/CommandTree.vue`：
- props（:6）改：`const props = defineProps<{ modelValue: Record<string, CmdPerm>; hideGroups?: string[] }>()`
- groups computed（:22 循环）过滤：

```ts
  for (const n of PAL_TREE) {
    if ((props.hideGroups ?? []).includes(n.group ?? '')) continue
    const k = n.group ?? '__flat__'
    ...
  }
```

`frontend/src/components/SettingsPanel.vue` CommandTree 调用（:160）加 prop：

```html
          <CommandTree :model-value="state.command_perms ?? {}" :hide-groups="worldMode === 'single' ? ['link'] : []"
            @update:model-value="(v) => { state.command_perms = v }" @change="dirty = true" />
```

- [ ] **Step 4: 跑测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: PASS + 产物刷新

- [ ] **Step 5: 提交**

```bash
git add frontend/src/ pages/settings/
git commit -m "feat(fe): 命令树 hideGroups——单模式隐藏 link 组"
```

---

### Task 10: 前端 —— 授权群名单区（GroupCard + collect + hydrate）

single+restricted 下于连接章呈现 `single_allowed_groups` 名单。镜像 permission_admins/AdminCard。

**Files:**
- Create: `frontend/src/components/GroupCard.vue`（clone AdminCard，id→umo）
- Modify: `frontend/src/lib/collect.ts`（SettingsState + collectGroup + body）
- Modify: `frontend/src/components/SettingsPanel.vue`（state/hydrate/emptyGroup/section）
- Create: `frontend/src/components/GroupCard.test.ts`（clone AdminCard.test）
- Build + Test: `collect.test.ts`、`SettingsPanel.test.ts`

- [ ] **Step 1: 写失败测试**

`frontend/src/lib/collect.test.ts`：TOP_KEYS 断言加 `'single_allowed_groups'`（:35）；加：

```ts
it('collectBody 恒回传 single_allowed_groups（含 multi，防抹除）', () => {
  const state = { servers: [], custom_headers: [], sections: {}, single_allowed_groups: [{ __row_id: 'sag-0', umo: 'g1', note: 'x' }] } as any
  expect(collectBody(state).single_allowed_groups).toEqual([{ __row_id: 'sag-0', umo: 'g1', note: 'x' }])
})
```

`SettingsPanel.test.ts`：加「single+restricted 显示授权群名单区、single+open 不显示」用例。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- collect SettingsPanel`
Expected: FAIL

- [ ] **Step 3: GroupCard 组件**

`frontend/src/components/GroupCard.vue`：整体克隆 `AdminCard.vue`，把 `modelValue.id`→`modelValue.umo`、`draft.id`→`draft.umo`、`setDraft('id',…)`→`setDraft('umo',…)`、查看态标签「标识」保留、placeholder「如 aiocqhttp:12345」→「如 aiocqhttp:GroupMessage:123456」。备注字段不变。

- [ ] **Step 4: collect.ts**

`frontend/src/lib/collect.ts`：
- `SettingsState`（:9-17）加：`single_allowed_groups?: Record<string, unknown>[]`
- `collectAdmin`（:63-65）后加：

```ts
function collectGroup(row: Record<string, unknown>): Record<string, unknown> {
  return { __row_id: (row.__row_id as string) || null, umo: str(row.umo), note: str(row.note) }
}
```

- `collectBody`（:72 后）加：`body.single_allowed_groups = (state.single_allowed_groups ?? []).map(collectGroup)`

- [ ] **Step 5: SettingsPanel 接线**

`frontend/src/components/SettingsPanel.vue`：
- import GroupCard；state 初始化（:21）加 `single_allowed_groups: []`。
- `applyConfig`（:59 后）**无条件** hydrate：`state.single_allowed_groups = (c.single_allowed_groups ?? []).map((g: Record<string, unknown>) => ({ ...g, __local_key: \`local-${++localSeq}\` }))`
- `emptyAdmin`（:73-75）旁加 `emptyGroup()`：`return { __row_id: '', __local_key: \`local-${++localSeq}\`, umo: '', note: '' }`
- 连接章（`isAccess`）末尾加区块（`singleRestricted` 时显示）：

```html
        <section v-if="singleRestricted">
          <div class="group-head"><span class="t">授权群名单</span><span class="c">单世界受限模式下，仅这些会话可查询服务器</span></div>
          <p class="grouphint">群里发 /pal whereami 获取群标识后填入。名单为空 = 当前无人可查询。</p>
          <GroupCard v-for="(g, i) in state.single_allowed_groups" :key="(g.__row_id as string) || (g.__local_key as string)" :model-value="g" :index-label="'授权群 ' + pad(i + 1)"
            @update:model-value="(v) => { state.single_allowed_groups![i] = v; dirty = true }" @delete="state.single_allowed_groups!.splice(i, 1); dirty = true" />
          <button class="add" @click="state.single_allowed_groups!.push(emptyGroup()); dirty = true">＋ 添加授权群</button>
        </section>
```

- [ ] **Step 6: GroupCard.test.ts**

克隆 `AdminCard.test.ts`，断言字段换成 umo。

- [ ] **Step 7: 跑测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: PASS + 产物刷新

- [ ] **Step 8: 提交**

```bash
git add frontend/src/ pages/settings/
git commit -m "feat(fe): 单模式授权群名单区（GroupCard + collect + 无条件 hydrate）"
```

---

### Task 11: 版本 v0.9.7 + 文档 + 终检

**Files:**
- Modify: `metadata.yaml`、`main.py`（@register 版本）、`palworld_terminal/__init__.py`、`README.md`（badge + 功能 + 模式说明）、`docs/commands.md`（whereami + 模式差异）、`docs/configuration.md`（默认 single + single_allowed_groups + 无迁移）
- Modify: `tests/unit/phase1_smoke_test.py:19`
- Build: `pages/settings/**`

- [ ] **Step 1: 版本四源 + 断言**

改 `metadata.yaml` version、`main.py:116` `@register(... "v0.9.7" ...)`、`palworld_terminal/__init__.py` `__version__ = "0.9.7"`、`README.md` badge；`tests/unit/phase1_smoke_test.py:19` `"0.9.6"` → `"0.9.7"`。

- [ ] **Step 2: 文档**

- `docs/commands.md`：加 `/pal whereami`；更新 single/multi 模式差异（single restricted 查授权群名单、link 单模式不可用、写命令不受名单约束）。
- `docs/configuration.md`：`world_mode` 默认 single；新增 `single_allowed_groups` 说明；注明「无迁移（默认直改）」。
- `README.md`：功能特性/模式说明同步。

- [ ] **Step 3: 核 readme 中文锚点**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -v`
Expected: PASS（若锚点短语因文案改动缺失，补回或调锚点）

- [ ] **Step 4: 前端构建 + 全库终检**

Run: `cd frontend && npm test && npm run build`
Run: `./.venv/Scripts/python.exe -m pytest -q`
Run: `./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal`
Run: `git status --porcelain pages/settings`（应为空 = 无 drift）
Expected: 全 PASS + pages/settings 无未提交漂移

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "chore: v0.9.7 版本四源 + 文档（whereami/模式差异/single_allowed_groups）"
```

---

## Self-Review

**Spec coverage：**
- §1 目标 / §2 契约 → Task 4/5（读授权+写绕过）、Task 7-10（前端呈现）、Task 6（默认）。
- §3.1 默认 → Task 6；§3.2 single_allowed_groups → Task 2/3。
- §4.1 restricted 生效 / §4.2 for_write / §4.3 告警 / §4.4 文案 → Task 4/5。
- §5 多模式不变 → 未触碰多模式路径（Task 4 只改 single 分支）。
- §6 whereami → Task 1。
- §7 前端五缝 → Task 7（badge/字段/seed）、8（servers）、9（link 树）、10（名单）。
- §8 锚定测试 → 各任务内 + Task 11。§9 版本 → Task 11。

**Placeholder scan：** 无 TBD/TODO；每步给实码或实测命令。helper 名（`_svc`/`_admin_service`/`_commands`/`mountAccess`）标注「以本文件既有为准」——因测试文件已存在、helper 已在，非占位。

**Type consistency：** `AllowedGroupEntry(umo,note)`、`RoutingConfig.single_allowed_groups`、`resolve(...,*,for_write=False)`、`worldMode`/`singleRestricted`/`visibleSections`、`collectGroup`/`emptyGroup`、row_id 前缀 `sag`——跨任务一致。for_write 6 处调用点在 Task 5 显式枚举。

**依赖顺序：** Task 2→3（config 先于 view）；Task 2→4（字段先于消费）；Task 4→5（形参先于穿线）；Task 4/5→6（single 行为正确后再翻默认，避免默认翻转期行为不一致）；前端 7-10 独立，各自 build 保 no-drift。
