# 权限管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给插件一套两层权限模型——超管(设置页访问者)在设置页维护受托名单,群里管理员权限严格只认该名单;新增 `/pal whoami`;命令门可把整条命令锁成管理员专用。

**Architecture:** 后端新增 `permissions` 配置(顶层 template_list `permission_admins` + 顶层 list `admin_only_commands`),`_is_admin` 改读名单,main.py 中央命令门 `_guarded_cmd` 拦锁定命令;前端设置页新增「权限」章(受托名单卡片 + 命令 chip 网格)。命令门词表统一为 astrbot 命令串,单一真相源 `LOCKABLE_COMMANDS` + 前后端锚定测试。

**Tech Stack:** Python 3.11+、AstrBot 插件框架、aiosqlite(不涉本轮);前端 Vue3 + reka-ui + Vite 单文件产物;pytest / vitest。

## Global Constraints

- **git 提交不得出现任何 Claude / AI / 🤖 署名**(无 Co-Authored-By,正文不提及 Claude)。
- **包内 import 一律相对**,函数体内**绝不绝对自导入**(命名空间加载会炸,有静态防回归测试)。
- **Windows 上 `python` 被拦截**,一律用 `./.venv/Scripts/python.exe` 跑 pytest / ruff / mypy。
- **命令门词表 = astrbot 命令串**(用户 `/pal <X>` 里的 `X`),不是 `command_registry` 方法名。`unbind`(串)≠ `unbind_self`(方法名)。`admin_only_commands`、`LOCKABLE_COMMANDS`、中央门传入串、前端 `PAL_COMMANDS` 全用命令串。
- **不可锁集** = `{server, whoami, help}`。`server` add/remove 内置需管理员(commands 层),裸 server 列表全员。
- **严格只认插件名单**:`_is_admin` 只查 `permission_admins`,**不认** AstrBot `admins_id` / `event.role`。
- **前端改后必须** `cd frontend && npm run build`(内置 normalize-eol)并提交 `pages/settings/`;`verify-bundle` 从仓库根跑;CI no-drift 强制。
- **改中文文案须同步 grep** `tests/unit/readme_test.py` 中文锚点。
- **版本升 `v0.8.5` → `v0.8.7`**。
- **子代理 model 一律 opus**。

## 文件结构总览

| 文件 | 职责 | Task |
|---|---|---|
| `palworld_terminal/config.py` | `PermissionsConfig`/`AdminEntry` + parse | T1 |
| `palworld_terminal/presentation/command_registry.py` | whoami 注册 + `LOCKABLE_COMMANDS`/`PAL_COMMAND_STRINGS` | T2 |
| `palworld_terminal/presentation/commands.py` | `whoami`/`is_plugin_admin`/`admin_denied` | T3 |
| `palworld_terminal/presentation/locale.py` | whoami 文案 | T3 |
| `main.py` | `_is_admin` 改写、`_guarded_cmd` 中央门、whoami handler、路由锁定命令 | T4 |
| `palworld_terminal/presentation/config_view.py` | `_TOP_KEYS` + permission_admins template_list + admin_only_commands 校验 | T5 |
| `_conf_schema.json` | permission_admins + admin_only_commands schema | T6 |
| `frontend/src/lib/schema.ts` | `PAL_COMMANDS` + 跨端锚定测试 | T7 |
| `frontend/src/components/AdminCard.vue`、`frontend/src/lib/collect.ts` | 名单卡片 + collect | T8 |
| `frontend/src/lib/chapters.ts`、`frontend/src/components/SettingsPanel.vue` | 权限章 + isPermissions + applyConfig | T9 |
| `pages/settings/` | 重建产物 | T10 |
| `docs/*`、`README.md`、`tests/unit/readme_test.py`、`metadata.yaml`、`palworld_terminal/__init__.py` | 文档 + 版本 | T11 |

---

## Task 1: config.py —— PermissionsConfig + parse

**Files:**
- Modify: `palworld_terminal/config.py`
- Test: `tests/unit/config_permissions_test.py`(新建)

**Interfaces:**
- Produces: `AdminEntry(id: str, note: str)`;`PermissionsConfig(admins: list[AdminEntry], admin_only_commands: list[str])`;`AppConfig.permissions: PermissionsConfig`;解析函数把 raw 的 `permission_admins`/`admin_only_commands` 解成上述结构。T3/T4/T5 消费。
- 注:`admin_only_commands` 过滤依赖 T2 的 `LOCKABLE_COMMANDS`,但为免循环依赖,parse 内联不可锁集 `{"server","whoami","help"}` 做剔除,合法命令名过滤放到运行时(T4 中央门只对 `∈ admin_only_commands` 判定,未知名不匹配任何 handler 自然无效)。**本任务 parse 不引用 command_registry**。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/config_permissions_test.py`:

```python
from palworld_terminal.config import parse_config


def _base(**over):
    raw = {"servers": [], "routing": {}, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    raw.update(over)
    return parse_config(raw, {})


def test_permission_admins_parsed_and_filtered():
    cfg = _base(permission_admins=[
        {"id": "aiocqhttp:12345", "note": "群主"},
        {"id": "", "note": "空 id 跳过"},
        {"id": "aiocqhttp:", "note": "空账号段跳过"},
        {"id": "aiocqhttp:12345", "note": "重复去掉"},
    ])
    ids = [a.id for a in cfg.permissions.admins]
    assert ids == ["aiocqhttp:12345"]
    assert cfg.permissions.admins[0].note == "群主"


def test_admin_only_commands_normalized():
    cfg = _base(admin_only_commands=["player", " rank ", "player", "server", "whoami", "help", 123])
    # 去空白/去重/剔除不可锁集{server,whoami,help}/丢非 str
    assert sorted(cfg.permissions.admin_only_commands) == ["player", "rank"]


def test_admin_only_commands_non_list_degrades_empty():
    cfg = _base(admin_only_commands="oops")
    assert cfg.permissions.admin_only_commands == []


def test_permissions_default_empty():
    cfg = _base()
    assert cfg.permissions.admins == []
    assert cfg.permissions.admin_only_commands == []
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_permissions_test.py -v`
Expected: FAIL —— `AttributeError: 'AppConfig' object has no attribute 'permissions'`

- [ ] **Step 3: 加 dataclass**

在 `config.py`(约 143 行,`AppConfig` 之前)加:

```python
@dataclass(slots=True)
class AdminEntry:
    id: str
    note: str


@dataclass(slots=True)
class PermissionsConfig:
    admins: list["AdminEntry"]
    admin_only_commands: list[str]


def _default_permissions() -> "PermissionsConfig":
    return PermissionsConfig(admins=[], admin_only_commands=[])


# 命令门不可锁集(astrbot 命令串);与 command_registry.LOCKABLE_COMMANDS 一致,
# 此处内联以免 config 依赖 presentation 层
_NON_LOCKABLE = frozenset({"server", "whoami", "help"})
```

- [ ] **Step 4: AppConfig 加字段**

在 `AppConfig`(146-158 行)`players` 之后加:

```python
    permissions: PermissionsConfig = field(default_factory=_default_permissions)
```

- [ ] **Step 5: 加 parse 辅助函数**

在 `_parse_bindings`(227 行)之后加:

```python
def _parse_permissions(raw: Mapping) -> PermissionsConfig:
    admins: list[AdminEntry] = []
    seen: set[str] = set()
    for item in raw.get("permission_admins", []) or []:
        if not isinstance(item, Mapping):
            continue
        pid = str(item.get("id", "") or "").strip()
        if not pid or pid.endswith(":") or pid in seen:  # 空 id / 空账号段 / 重复
            continue
        seen.add(pid)
        admins.append(AdminEntry(id=pid, note=str(item.get("note", "") or "").strip()))
    raw_cmds = raw.get("admin_only_commands", [])
    cmds: list[str] = []
    if isinstance(raw_cmds, list):
        cseen: set[str] = set()
        for c in raw_cmds:
            if not isinstance(c, str):
                continue
            name = c.strip()
            if not name or name in _NON_LOCKABLE or name in cseen:
                continue
            cseen.add(name)
            cmds.append(name)
    return PermissionsConfig(admins=admins, admin_only_commands=cmds)
```

- [ ] **Step 6: parse_config 接线**

在 `parse_config` 的 `return AppConfig(...)` 里,`players=PlayersConfig(...)` 之后加一行:

```python
        permissions=_parse_permissions(raw),
```

- [ ] **Step 7: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_permissions_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS(全绿,ruff 0 error)

- [ ] **Step 8: 提交**

```bash
git add palworld_terminal/config.py tests/unit/config_permissions_test.py
git commit -m "feat(config): PermissionsConfig + parse（受托名单/命令门，含归一化与去重）"
```

---

## Task 2: command_registry.py —— whoami 注册 + LOCKABLE_COMMANDS + 锚定

**Files:**
- Modify: `palworld_terminal/presentation/command_registry.py`
- Test: `tests/unit/command_names_test.py`(新建)

**Interfaces:**
- Consumes: 无。
- Produces: `PAL_COMMAND_STRINGS: list[str]`(**本任务 17 条,不含 whoami**——whoami 随 T4 的 handler 同步加入);`LOCKABLE_COMMANDS: frozenset[str]` = `PAL_COMMAND_STRINGS` − `{server,whoami,help}`(15 条,whoami 不在集合里、被减去无副作用)。T3/T7 消费 `LOCKABLE_COMMANDS`;锚定测试消费 `PAL_COMMAND_STRINGS`。
- **whoami 不在本任务**:whoami 的三处注册(COMMANDS/HELP_LINE/PAL_COMMAND_STRINGS)与 main.py handler 强耦合(锚定测试要求二者同步),统一放 T4。本任务的锚定断言 = 「当前 17 条 == main.py 现有 17 个注册」。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/command_names_test.py`:

```python
import re
from pathlib import Path

from palworld_terminal.presentation.command_registry import (
    LOCKABLE_COMMANDS, PAL_COMMAND_STRINGS,
)

_MAIN = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")


def test_pal_command_strings_match_main_registrations():
    # main.py 实际 @pal.command("X") 注册串 == PAL_COMMAND_STRINGS(防漏/防多)
    registered = set(re.findall(r'@pal\.command\("([^"]+)"\)', _MAIN))
    assert registered == set(PAL_COMMAND_STRINGS), (
        f"注册串与 PAL_COMMAND_STRINGS 不一致：仅注册 {registered - set(PAL_COMMAND_STRINGS)}，"
        f"仅表内 {set(PAL_COMMAND_STRINGS) - registered}"
    )


def test_lockable_excludes_non_lockable():
    assert LOCKABLE_COMMANDS == frozenset(PAL_COMMAND_STRINGS) - {"server", "whoami", "help"}
    assert "unbind" in LOCKABLE_COMMANDS    # 命令串是 unbind,不是 unbind_self
    assert "server" not in LOCKABLE_COMMANDS and "help" not in LOCKABLE_COMMANDS
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_names_test.py -v`
Expected: FAIL —— `ImportError: cannot import name 'LOCKABLE_COMMANDS'`

- [ ] **Step 3: 加命令串真相源 + LOCKABLE_COMMANDS(17 条,不含 whoami)**

在 `command_registry.py` 末尾(`HELP_LINE` 之后)加:

```python
# astrbot 命令串真相源(用户 /pal <X> 里的 X)。与 COMMANDS 的键(方法名)区分:
# unbind(串) vs unbind_self(方法名)。由 command_names_test 锚定到 main.py 注册。
# 注:whoami 随 T4 的 handler 一并加入本表。
PAL_COMMAND_STRINGS: list[str] = [
    "status", "online", "world", "rules", "guilds", "guild", "bases", "base",
    "events", "today", "rank", "player", "me", "bind", "unbind",
    "server", "help",
]

# 可被 admin_only_commands 锁定的命令串 = 全部 − 不可锁集{server,whoami,help}
LOCKABLE_COMMANDS: frozenset[str] = frozenset(PAL_COMMAND_STRINGS) - {"server", "whoami", "help"}
```

- [ ] **Step 4: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_names_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS(17 条 == main.py 现有 17 个 @pal.command)

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/command_registry.py tests/unit/command_names_test.py
git commit -m "feat(registry): LOCKABLE_COMMANDS 命令串真相源 + main.py 注册锚定测试"
```

---

## Task 3: commands.py + locale —— whoami / is_plugin_admin / admin_denied

**Files:**
- Modify: `palworld_terminal/presentation/commands.py`、`palworld_terminal/presentation/locale.py`
- Test: `tests/unit/commands_permissions_test.py`(新建)

**Interfaces:**
- Consumes: `self._cfg.permissions`(T1);`L`。
- Produces: `Commands.whoami(self, sender_id: str) -> str`;`Commands.is_plugin_admin(self, sender_id: str) -> bool`;`Commands.admin_denied(self, command_str: str, sender_id: str) -> str | None`。T4 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/commands_permissions_test.py`:

```python
from types import SimpleNamespace

from palworld_terminal.config import AdminEntry, PermissionsConfig
from palworld_terminal.presentation.commands import Commands


def _cmds(admins=(), locked=()):
    perms = PermissionsConfig(
        admins=[AdminEntry(id=a, note="") for a in admins],
        admin_only_commands=list(locked),
    )
    cfg = SimpleNamespace(permissions=perms)
    return Commands(routing=None, query=None, repo=None, cfg=cfg, clock=None, salt=b"")


async def test_whoami_returns_identity():
    out = await _cmds().whoami("aiocqhttp:12345")
    assert "aiocqhttp:12345" in out


async def test_whoami_empty_account():
    out = await _cmds().whoami("aiocqhttp:")
    assert "aiocqhttp:" not in out and "无法识别" in out


def test_is_plugin_admin():
    c = _cmds(admins=["aiocqhttp:1"])
    assert c.is_plugin_admin("aiocqhttp:1") is True
    assert c.is_plugin_admin("aiocqhttp:2") is False


def test_admin_denied_only_for_locked_non_admin():
    c = _cmds(admins=["aiocqhttp:1"], locked=["player"])
    assert c.admin_denied("player", "aiocqhttp:2") == "该命令需要管理员权限。"  # 锁定+非管理员
    assert c.admin_denied("player", "aiocqhttp:1") is None                    # 管理员放行
    assert c.admin_denied("rank", "aiocqhttp:2") is None                      # 未锁放行
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_permissions_test.py -v`
Expected: FAIL —— `AttributeError: 'Commands' object has no attribute 'whoami'`

- [ ] **Step 3: locale 加文案**

`locale.py` 的 `MESSAGES` 里 `bind_usage` 之后加:

```python
    "whoami": "你的账号标识：{id}（建议私聊 bot 执行本命令，再把标识报给管理员加入受托名单）",
    "whoami_no_sender": "当前场景无法识别你的账号，请在群聊里再试。",
```

- [ ] **Step 4: commands.py 加三方法**

在 `commands.py` 的 `Commands` 类里(如 `help` 方法之后)加:

```python
    async def whoami(self, sender_id: str) -> str:
        if sender_id.endswith(":"):  # 账号段为空(取不到 sender)
            return L("whoami_no_sender")
        return L("whoami", id=sender_id)

    def is_plugin_admin(self, sender_id: str) -> bool:
        return sender_id in {a.id for a in self._cfg.permissions.admins}

    def admin_denied(self, command_str: str, sender_id: str) -> str | None:
        if command_str in self._cfg.permissions.admin_only_commands and not self.is_plugin_admin(sender_id):
            return L("admin_required")
        return None
```

- [ ] **Step 5: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_permissions_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/presentation/commands.py palworld_terminal/presentation/locale.py tests/unit/commands_permissions_test.py
git commit -m "feat(cmd): whoami/is_plugin_admin/admin_denied（含空账号处理）"
```

---

## Task 4: main.py —— _is_admin 改写 + 中央命令门 + whoami handler + 路由锁定命令

**Files:**
- Modify: `main.py`、`palworld_terminal/presentation/command_registry.py`(补 whoami 进 3 处)
- Test: `tests/unit/main_permission_gate_test.py`(新建)、`tests/unit/namespace_runtime_smoke_test.py`(改)

**Interfaces:**
- Consumes: `Commands.is_plugin_admin`/`admin_denied`(T3);`command_registry` 的 whoami 注册(本任务补齐)。
- Produces: `PalWorldTerminal._guarded_cmd(event, command_str, call)`;`_is_admin(event)` 名单判定;`@pal.command("whoami")` handler。

- [ ] **Step 1: 先把 whoami 补进 command_registry 三处(与 handler 同任务,满足 T2 锚定测试)**

`command_registry.py`:`COMMANDS` 的 `("server","core")` 与 `("help","core")` 间加 `("whoami","core")`;`HELP_LINE` 加 `"whoami": "/pal whoami  查看我的账号标识（建议私聊使用）"`;`PAL_COMMAND_STRINGS` 加 `"whoami"`(放 `"server"` 与 `"help"` 之间,共 18 条)。

- [ ] **Step 2: 写失败测试(命令门 + whoami handler)**

新建 `tests/unit/main_permission_gate_test.py`:

```python
import sys

from tests.unit._ns_loader import NS, namespaced_main


class _Ev:
    def __init__(self, sender="u1"):
        self._sender = sender
    message_str = "whoami"
    unified_msg_origin = "test:GroupMessage:g1"
    role = "member"  # 关键:框架非管理员

    def is_private_chat(self): return False
    def get_group_id(self): return "g1"
    def get_platform_name(self): return "test"
    def get_sender_id(self): return self._sender
    def plain_result(self, s): return s


def _raw(admins, locked):
    return {
        "servers": [], "group_bindings": [],
        "routing": {"access_mode": "open", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {}, "history": {},
        "features": {"players": True},
        "permission_admins": [{"id": a, "note": ""} for a in admins],
        "admin_only_commands": list(locked),
    }


async def test_whoami_returns_composite_id(tmp_path, monkeypatch):
    with namespaced_main() as mod:
        monkeypatch.setattr(mod, "_resolve_data_dir", lambda: tmp_path)
        plugin = mod.PalWorldTerminal(object(), _raw([], []))
        await plugin.initialize()
        try:
            outs = [o async for o in plugin.whoami(_Ev(sender="12345"))]
            assert any("test:12345" in o for o in outs)
        finally:
            await plugin.terminate()


async def test_locked_command_blocks_non_admin(tmp_path, monkeypatch):
    with namespaced_main() as mod:
        monkeypatch.setattr(mod, "_resolve_data_dir", lambda: tmp_path)
        # 锁定 player,请求者非名单成员(role=member 也不放行)
        plugin = mod.PalWorldTerminal(object(), _raw([], ["player"]))
        await plugin.initialize()
        try:
            ev = _Ev(sender="12345"); ev.message_str = "player Alice"
            outs = [o async for o in plugin.player(ev)]
            assert any("需要管理员权限" in o for o in outs)
        finally:
            await plugin.terminate()
```

- [ ] **Step 3: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/main_permission_gate_test.py -v`
Expected: FAIL —— `AttributeError: 'PalWorldTerminal' object has no attribute 'whoami'`

- [ ] **Step 4: _is_admin 改写 + _guarded_cmd**

`main.py`:把 `_is_admin`(295-298)从 `@staticmethod` 改为实例方法、读名单:

```python
    def _is_admin(self, event) -> bool:
        c = self._container
        if c is None:
            return False
        return c.commands.is_plugin_admin(self._sender_id(event))
```

在 `_guarded`(132-150)之后加中央命令门:

```python
    async def _guarded_cmd(self, event, command_str, call):
        """可锁命令的门:先判 admin_only_commands 再走 _guarded。"""
        self._inflight += 1
        self._idle.clear()
        try:
            if (m := self._busy_msg()):
                return m
            denied = self._container.commands.admin_denied(command_str, self._sender_id(event))
            if denied is not None:
                return denied
            res = call(self._container)
            if inspect.isawaitable(res):
                res = await res
            return res
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
```

- [ ] **Step 5: 路由所有可锁命令 handler 过 _guarded_cmd**

把这 15 个 handler(`status/online/world/rules/guilds/guild/bases/base/events/today/rank/player/me/bind/unbind`)从 `await self._guarded(lambda c: c.commands.X(...))` 改为 `await self._guarded_cmd(event, "X", lambda c: c.commands.X(...))`,其中 `"X"` 是 astrbot 命令串(注意 unbind 的串是 `"unbind"`,方法仍是 `c.commands.unbind_self(...)`)。例:

```python
    @pal.command("player")
    async def player(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "player", lambda c: c.commands.player(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("unbind")
    async def unbind(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "unbind", lambda c: c.commands.unbind_self(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event)))
        )
```

`server`/`help` 保持用 `_guarded`(不可锁)。`server` handler 的 `is_admin` 实参改用名单判定:

```python
    @pal.command("server")
    async def server(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.server(
                self._umo(event), self._msg(event), self._is_group(event),
                c.commands.is_plugin_admin(self._sender_id(event))))
        )
```

- [ ] **Step 6: 加 whoami handler**

在 `server` handler 之后、`help` 之前加:

```python
    @pal.command("whoami")
    async def whoami(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.whoami(self._sender_id(event)))
        )
```

- [ ] **Step 7: 冒烟测试改 calls 清单**

`tests/unit/namespace_runtime_smoke_test.py`:`calls` 列表在 `(plugin.server, "server")` 附近加 `(plugin.whoami, "whoami")`;docstring 命令条数更新(现 17 → 18);种子数据的 raw config 加 `"permission_admins": []`、`"admin_only_commands": []`(避免缺键)。若 features 全开需确认新键不影响既有断言。

- [ ] **Step 8: 运行确认通过 + 全库回归 + ruff + mypy**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/main_permission_gate_test.py tests/unit/command_names_test.py tests/unit/namespace_runtime_smoke_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS(全绿)

> **注意兼容性回归**:`_is_admin` 从 event.role 改成名单判定后,现有依赖 role 的测试(如 `commands_test.py` 的 `server add/remove` happy-path 传 `is_admin=True`)不受影响(它们直接传布尔);但若有测试构造 `role="admin"` 期望 server 放行,会因名单空而变拒——按新模型修正这些测试(用 `permission_admins` 名单或直接传 is_admin)。

- [ ] **Step 9: 提交**

```bash
git add main.py palworld_terminal/presentation/command_registry.py tests/unit/main_permission_gate_test.py tests/unit/namespace_runtime_smoke_test.py
git commit -m "feat(main): _is_admin 改读名单 + 中央命令门 _guarded_cmd + whoami handler"
```

---

## Task 5: config_view.py —— _TOP_KEYS + permission_admins template_list + admin_only_commands 校验

**Files:**
- Modify: `palworld_terminal/presentation/config_view.py`
- Test: `tests/unit/config_view_permissions_test.py`(新建)

**Interfaces:**
- Consumes: 无(纯函数校验层)。
- Produces: `permission_admins` 纳入 template_list 机制;`admin_only_commands` 独立形状校验;`_TOP_KEYS` 含两键。T8/T9 前端 collect 往返依赖它。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/config_view_permissions_test.py`:

```python
from palworld_terminal.presentation.config_view import (
    redact_config, validate_and_backfill,
)


def _ok(body):
    return validate_and_backfill(body, {}, {})


def test_permission_admins_roundtrip_and_row_id():
    red = redact_config({"permission_admins": [{"id": "aiocqhttp:1", "note": "群主"}]})
    assert red["permission_admins"][0]["__row_id"] == "adm-0"


def test_admin_only_commands_valid():
    ok, res = _ok({"admin_only_commands": ["player", "rank"]})
    assert ok and res["admin_only_commands"] == ["player", "rank"]


def test_admin_only_commands_non_list_rejected():
    ok, err = _ok({"admin_only_commands": {"evil": 1}})
    assert not ok and err["error"] == "invalid_shape"


def test_admin_only_commands_non_str_element_rejected():
    ok, err = _ok({"admin_only_commands": ["player", 123]})
    assert not ok and err["error"] == "invalid_shape"


def test_permission_admins_strips_meta():
    ok, res = _ok({"permission_admins": [{"id": "aiocqhttp:1", "note": "x", "__row_id": "adm-0", "junk": 1}]})
    assert ok
    assert res["permission_admins"][0] == {"id": "aiocqhttp:1", "note": "x"}
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_view_permissions_test.py -v`
Expected: FAIL(`permission_admins` 不在 `_TOP_KEYS` → `invalid_shape`)

- [ ] **Step 3: 接线 permission_admins 到 template_list 机制**

`config_view.py`:
- `_LIST_SECTIONS`(13)加 `"permission_admins"`:`("servers", "custom_headers", "group_bindings", "permission_admins")`。
- `_ROW_ID_PREFIX`(14)加 `"permission_admins": "adm"`。
- `_SECTION_KEYS`(20)加 `"permission_admins": {"id", "note"}`。
- `_TOP_KEYS`(27)加 `"permission_admins"`、`"admin_only_commands"`。

（redact_config、_strip_meta、列表节形状校验会自动覆盖 permission_admins,因它们都遍历 `_LIST_SECTIONS`;id/note 非 secret 无需脱敏分支。）

- [ ] **Step 4: 加 admin_only_commands 独立校验**

在 `validate_and_backfill` 的"形状/类型"段(143 行 object 节循环之后)加:

```python
    # admin_only_commands:顶层字符串列表(仓库无此形态先例,独立校验)
    if "admin_only_commands" in body:
        aoc = body["admin_only_commands"]
        if not isinstance(aoc, list) or len(aoc) > _MAX_LIST:
            return _err("invalid_shape")
        for c in aoc:
            if not isinstance(c, str) or len(c) > _MAX_STR:
                return _err("invalid_shape")
```

- [ ] **Step 5: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_view_permissions_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS。若 `test_permission_admins_roundtrip_and_row_id` 因 __row_id 前缀断言不符,改断言为 `startswith("adm-")`。

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/presentation/config_view.py tests/unit/config_view_permissions_test.py
git commit -m "feat(config_view): permission_admins template_list + admin_only_commands 形状校验"
```

---

## Task 6: _conf_schema.json —— permission_admins + admin_only_commands

**Files:**
- Modify: `_conf_schema.json`
- Test: `tests/unit/conf_schema_test.py`(扩)

**Interfaces:** 无代码接口;AstrBot 原生设置页/schema 校验读它。

- [ ] **Step 1: 写失败测试**

`tests/unit/conf_schema_test.py` 加:

```python
def test_permission_schema_present():
    import json
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text(encoding="utf-8"))
    assert schema["permission_admins"]["type"] == "template_list"
    assert schema["admin_only_commands"]["type"] == "list"
    assert schema["admin_only_commands"]["default"] == []
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/conf_schema_test.py::test_permission_schema_present -v`
Expected: FAIL(`KeyError: 'permission_admins'`)

- [ ] **Step 3: 加 schema 块**

`_conf_schema.json` 顶层加(仿 `group_bindings` 结构):

```json
  "permission_admins": {
    "type": "template_list",
    "description": "受托群管理员：这些账号可在群里执行管理员命令（注意：名册全局，加入者在其所在每个群都有管理员权）",
    "default": [],
    "templates": {
      "admin": {
        "name": "管理员",
        "display_item": "id",
        "items": {
          "id": { "type": "string", "description": "账号标识 平台:账号（如 aiocqhttp:12345，群里发 /pal whoami 可查）" },
          "note": { "type": "string", "description": "备注（可选，明文存储于配置文件，勿填真实姓名/联系方式等敏感信息）", "default": "" }
        }
      }
    }
  },
  "admin_only_commands": {
    "type": "list",
    "description": "锁成仅管理员的命令（astrbot 命令串，如 player、rank；server/whoami/help 不可锁）",
    "default": []
  },
```

- [ ] **Step 4: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/conf_schema_test.py -v && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add _conf_schema.json tests/unit/conf_schema_test.py
git commit -m "feat(schema): permission_admins/admin_only_commands 配置项（含安全提示）"
```

---

## Task 7: frontend schema.ts —— PAL_COMMANDS + 跨端锚定测试

**Files:**
- Modify: `frontend/src/lib/schema.ts`
- Test: `tests/unit/frontend_pal_commands_test.py`(新建,Python 侧跨端锚定)

**Interfaces:**
- Consumes: 后端 `LOCKABLE_COMMANDS`(T2)。
- Produces: `PAL_COMMANDS`(astrbot 命令串 + 组,供 T9 chip 网格);跨端锚定测试。

- [ ] **Step 1: 写失败锚定测试**

新建 `tests/unit/frontend_pal_commands_test.py`:

```python
import re
from pathlib import Path

from palworld_terminal.presentation.command_registry import LOCKABLE_COMMANDS

_SCHEMA = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "schema.ts").read_text(encoding="utf-8")


def test_pal_commands_matches_lockable():
    # 从 schema.ts 的 PAL_COMMANDS 提命令串,断言 == 后端 LOCKABLE_COMMANDS
    m = re.search(r"export const PAL_COMMANDS[^=]*=\s*\[(.*?)\]", _SCHEMA, re.S)
    assert m, "schema.ts 缺 PAL_COMMANDS"
    cmds = set(re.findall(r"cmd:\s*'([^']+)'", m.group(1)))
    assert cmds == set(LOCKABLE_COMMANDS), (
        f"PAL_COMMANDS 与 LOCKABLE_COMMANDS 漂移：仅前端 {cmds - set(LOCKABLE_COMMANDS)}，"
        f"仅后端 {set(LOCKABLE_COMMANDS) - cmds}"
    )
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/frontend_pal_commands_test.py -v`
Expected: FAIL(schema.ts 无 PAL_COMMANDS)

- [ ] **Step 3: 加 PAL_COMMANDS**

`frontend/src/lib/schema.ts` 末尾加(命令串 = `LOCKABLE_COMMANDS` 的 15 条 = 全 18 − server/whoami/help;`g` 为所属组仅供分组展示):

```typescript
// 可锁命令(astrbot 命令串)+ 所属功能组。内容须 == 后端 LOCKABLE_COMMANDS,
// 由 tests/unit/frontend_pal_commands_test.py 跨端锚定。
export const PAL_COMMANDS: { cmd: string; g: string }[] = [
  { cmd: 'status', g: 'core' }, { cmd: 'online', g: 'core' },
  { cmd: 'world', g: 'core' }, { cmd: 'rules', g: 'core' },
  { cmd: 'guilds', g: 'guilds_bases' }, { cmd: 'guild', g: 'guilds_bases' },
  { cmd: 'bases', g: 'guilds_bases' }, { cmd: 'base', g: 'guilds_bases' },
  { cmd: 'events', g: 'events' }, { cmd: 'today', g: 'report' },
  { cmd: 'rank', g: 'players' }, { cmd: 'player', g: 'players' },
  { cmd: 'me', g: 'players' }, { cmd: 'bind', g: 'players' }, { cmd: 'unbind', g: 'players' },
]
```

- [ ] **Step 4: 运行确认通过(Python 锚定 + 前端 typecheck)**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/frontend_pal_commands_test.py -v`
Expected: PASS
Run: `cd frontend && npm run test:run` 之后 `cd ..`(确认前端单测不因新导出崩)
Expected: PASS

- [ ] **Step 5: 提交(仅源码,产物 T10 统一 build)**

```bash
git add frontend/src/lib/schema.ts tests/unit/frontend_pal_commands_test.py
git commit -m "feat(fe): PAL_COMMANDS 命令串常量 + 跨端锚定测试"
```

---

## Task 8: AdminCard.vue + collect.ts

**Files:**
- Create: `frontend/src/components/AdminCard.vue`
- Modify: `frontend/src/lib/collect.ts`
- Test: `frontend/src/components/AdminCard.test.ts`(新建)、`frontend/src/lib/collect.test.ts`(扩)

**Interfaces:**
- Consumes: 无。
- Produces: `AdminCard`(props `model-value`/`index-label`,emit `update:model-value`/`delete`,字段 id/note 两态);`collectAdmin(row)`;`collectBody` 加 `permission_admins`/`admin_only_commands`;`SettingsState` 加两字段;collect `TOP_KEYS` 常量加两键。

- [ ] **Step 1: 写失败测试(collect)**

`frontend/src/lib/collect.test.ts`:`TOP_KEYS` 常量(约 23 行)加 `'permission_admins'`、`'admin_only_commands'`;加用例:

```typescript
it('collectBody 含 permission_admins(剥 meta)与 admin_only_commands 数组', () => {
  const state: any = {
    servers: [], custom_headers: [], sections: {},
    permission_admins: [{ __row_id: 'adm-0', __local_key: 'local-1', id: 'aiocqhttp:1', note: 'x' }],
    admin_only_commands: ['player', 'rank'],
  }
  const body = collectBody(state)
  expect(body.permission_admins).toEqual([{ __row_id: 'adm-0', id: 'aiocqhttp:1', note: 'x' }])
  expect(body.admin_only_commands).toEqual(['player', 'rank'])
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm run test:run` 然后 `cd ..`
Expected: FAIL(collectBody 无 permission_admins)

- [ ] **Step 3: collect.ts 加 collectAdmin + collectBody + SettingsState**

`frontend/src/lib/collect.ts`:`SettingsState`(5-9)加:

```typescript
  permission_admins: Record<string, unknown>[]
  admin_only_commands: string[]
```

加 collector(仿 `collectHeader`):

```typescript
function collectAdmin(row: Record<string, unknown>): Record<string, unknown> {
  return { __row_id: (row.__row_id as string) || null, id: str(row.id), note: str(row.note) }
}
```

`collectBody`(55-67)在 `body.custom_headers = ...` 之后加:

```typescript
  body.permission_admins = state.permission_admins.map(collectAdmin)
  body.admin_only_commands = [...state.admin_only_commands]
```

- [ ] **Step 4: 写失败测试(AdminCard)**

新建 `frontend/src/components/AdminCard.test.ts`(仿 `HeaderCard.test.ts`):断言查看态显示 id、点「修改」进编辑态、编辑 id/note 后「完成」emit `update:model-value` 含新值、新行(无 __row_id)「取消」emit `delete`。

```typescript
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import AdminCard from './AdminCard.vue'

describe('AdminCard', () => {
  it('查看态显示 id，点修改进编辑态', async () => {
    const w = mount(AdminCard, { props: { modelValue: { __row_id: 'adm-0', id: 'aiocqhttp:1', note: '群主' }, indexLabel: '席 01' } })
    expect(w.text()).toContain('aiocqhttp:1')
    await w.get('[data-act="edit"]').trigger('click')
    expect(w.find('input').exists()).toBe(true)
  })

  it('新行取消 emit delete', async () => {
    const w = mount(AdminCard, { props: { modelValue: { __row_id: '', id: '', note: '' }, indexLabel: '席 01' } })
    // 新行初始即编辑态；取消
    await w.get('[data-act="cancel"]').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
})
```

- [ ] **Step 5: 建 AdminCard.vue**

新建 `frontend/src/components/AdminCard.vue`,照抄 `HeaderCard.vue` 结构但**去掉 secret 逻辑**(id/note 均非 secret,均走普通 input),字段 id(等宽,占位"如 aiocqhttp:12345")、note(占位"备注,可选")。保留 `freshNew`(新行未完成过→取消 emit delete)、`draft` 暂存、`saveCard` 浅比较只 emit 不落库。**关键:模板不得用 v-html/innerHTML**(frontend_source_test 红线)。

（完整组件代码照 `frontend/src/components/HeaderCard.vue` 逐行改写:把 `HEADER_FIELDS` 换成本地两字段 `[{key:'id'},{key:'note'}]`,删所有 `f.secret` 分支与 `-webkit-text-security`,view 态显示 `modelValue.id`/`modelValue.note`。)

- [ ] **Step 6: 运行确认通过**

Run: `cd frontend && npm run test:run && cd .. && ./.venv/Scripts/python.exe -m pytest tests/unit/frontend_source_test.py -v`
Expected: PASS(前端单测全绿;无 v-html/innerHTML)

- [ ] **Step 7: 提交(仅源码)**

```bash
git add frontend/src/components/AdminCard.vue frontend/src/components/AdminCard.test.ts frontend/src/lib/collect.ts frontend/src/lib/collect.test.ts
git commit -m "feat(fe): AdminCard 名单卡片 + collect 接入 permission 两键"
```

---

## Task 9: chapters.ts + SettingsPanel.vue —— 权限章 + isPermissions + applyConfig 缺键容错

**Files:**
- Modify: `frontend/src/lib/chapters.ts`、`frontend/src/components/SettingsPanel.vue`
- Test: `frontend/src/components/SettingsPanel.test.ts`(扩)、`frontend/src/lib/chapters.test.ts`(确认不破)、`frontend/src/App.test.ts`(确认空 config 不崩)

**Interfaces:**
- Consumes: `PAL_COMMANDS`(T7)、`AdminCard`(T8)、`collectBody` 两键(T8)。
- Produces: 权限章渲染;`applyConfig` 读入两键(缺键 `?? []` 容错)。

- [ ] **Step 1: 写失败测试(权限章渲染 + 缺键不崩)**

`frontend/src/components/SettingsPanel.test.ts`:cfg() mock 加 `permission_admins: []`、`admin_only_commands: []`;加用例:

```typescript
it('权限章渲染 callout + 名单 + 命令 chip', async () => {
  const w = await mountPanel('permissions')  // 复用现有 mount 辅助,传 chapter=permissions
  expect(w.text()).toContain('受托')
  expect(w.text()).toContain('/pal player')  // chip 网格含命令
})

it('config 缺 permission 两键不崩、collectBody 产出空数组', async () => {
  const w = await mountPanelWithConfig({})  // 空 config
  const body = collectBody((w.vm as any).state)
  expect(body.permission_admins).toEqual([])
  expect(body.admin_only_commands).toEqual([])
})
```

（若现有测试无 `mountPanel(chapter)`/`mountPanelWithConfig` 辅助,按 `SettingsPanel.test.ts` 现有 mount 方式内联构造。)

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm run test:run && cd ..`
Expected: FAIL(permissions 章未渲染 / state 无两字段)

- [ ] **Step 3: chapters.ts 加权限章**

`frontend/src/lib/chapters.ts` 的 `CHAPTERS` 末尾加:

```typescript
  { id: 'permissions', label: '权限', group: '配置', kind: 'settings', blocks: [] },
```

- [ ] **Step 4: SettingsPanel.vue —— applyConfig 两键 + isPermissions 块**

`applyConfig`(49-55)末尾加(**`?? []` 缺键容错**):

```typescript
  state.permission_admins = (c.permission_admins ?? []).map((a: Record<string, unknown>) => ({ ...a, __local_key: `local-${++localSeq}` }))
  state.admin_only_commands = [...(c.admin_only_commands ?? [])]
```

`state` 初值(19)加两字段:`permission_admins: [], admin_only_commands: []`。

import 加:`import AdminCard from './AdminCard.vue'`、`import { PAL_COMMANDS } from '../lib/schema'`。

加 `isPermissions` computed(仿 isAccess,25 行):`const isPermissions = computed(() => props.chapter === 'permissions')`。

模板在 `isAccess` 块之后加 `isPermissions` 块:两层模型 callout(含"名册全局:加入者在其所在每个群都有管理员权,含对任意群 server add/remove;多群共用同一 bot 请谨慎")+ AdminCard 列表(照抄 servers 容器,用 `state.permission_admins`、emptyRow 用 `[{key:'id',default:''},{key:'note',default:''}]` 形状)+ 命令 chip 网格(`v-for c in PAL_COMMANDS`,点击 toggle `state.admin_only_commands` 含否,`server/whoami/help` 不在 PAL_COMMANDS 故无需锁定态——它们根本不出现;dirty 跟踪)。空名单提示"名单为空 → 群里暂无人可执行管理员命令"。**不得用 v-html**。

- [ ] **Step 5: 运行确认通过 + 前端全测 + 源码红线**

Run: `cd frontend && npm run test:run && npm run typecheck && cd .. && ./.venv/Scripts/python.exe -m pytest tests/unit/frontend_source_test.py -v`
Expected: PASS(含 chapters.test/App.test 不破)

- [ ] **Step 6: 提交(仅源码)**

```bash
git add frontend/src/lib/chapters.ts frontend/src/components/SettingsPanel.vue frontend/src/components/SettingsPanel.test.ts
git commit -m "feat(fe): 设置页权限章（受托名单卡片 + 命令 chip 网格 + 缺键容错）"
```

---

## Task 10: 重建前端产物 + verify-bundle + no-drift

**Files:**
- Modify: `pages/settings/`(build 产物)

**Interfaces:** 无。收口 T7-T9 的源码改动为入库单文件产物。

- [ ] **Step 1: 构建**

Run: `cd frontend && npm run build && cd ..`
Expected: 成功,产物落 `pages/settings/`(build 内置 normalize-eol)

- [ ] **Step 2: verify-bundle(从仓库根)**

Run: `node frontend/scripts/verify-bundle.mjs`
Expected: 通过(恰 1 JS / ≤1 CSS / 无 import())

- [ ] **Step 3: 本地 no-drift 自检**

Run: `git add pages/settings && git status --short pages/settings`
Expected: 有产物变更(index.js/style.css/index.html)

- [ ] **Step 4: 全套回归**

Run: `cd frontend && npm run test:run && cd .. && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS

- [ ] **Step 5: 提交产物**

```bash
git add pages/settings
git commit -m "build(fe): 权限章设置页单文件产物"
```

---

## Task 11: 文档 + readme_test + 版本 v0.8.7

**Files:**
- Modify: `docs/commands.md`、`docs/configuration.md`、`README.md`、`tests/unit/readme_test.py`、`metadata.yaml`、`main.py`、`palworld_terminal/__init__.py`、`tests/unit/phase1_smoke_test.py`、`tests/unit/skeleton_test.py`

**Interfaces:** 无。

- [ ] **Step 1: readme_test 锚点 + 版本断言测试(先红)**

`tests/unit/readme_test.py`:`test_readme_command_table_and_matrix` 加 `"/pal whoami"` 锚点;`test_readme_documents_players_group` 或新增权限说明锚点(如 `"受托"`、`"permission_admins"`)。
`tests/unit/phase1_smoke_test.py`、`tests/unit/skeleton_test.py`:版本断言 `"0.8.5"` → `"0.8.7"`。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py -v`
Expected: FAIL

- [ ] **Step 3: 文档**

- `docs/commands.md`:指令详表加 `/pal whoami`(players 组外的 core 工具,注"建议私聊");新增"权限"节(两层模型、受托名单、命令门、内置 server 门);功能矩阵 core 组命令名加 whoami。
- `docs/configuration.md`:加 `permission_admins`/`admin_only_commands` 说明 + 三条安全告知(名册全局爆炸半径、多适配器实例共享命名空间、note/id 明文落盘勿填 PII)。
- `README.md`:功能特性加"细粒度授权";安全与隐私加"名册全局"提示;命令计数(如"N 条指令")+1 更新;版本徽章 `version-v0.8.5` → `version-v0.8.7`。

- [ ] **Step 4: 版本四源**

`metadata.yaml`:`version: v0.8.5` → `v0.8.7`。`main.py` `@register(...)` 版本参数 `"v0.8.5"` → `"v0.8.7"`。`palworld_terminal/__init__.py` `__version__ = "0.8.5"` → `"0.8.7"`。

- [ ] **Step 5: 运行确认通过 + grep 无旧命令名残留 + 全套**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py tests/unit/main_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS(全绿)

- [ ] **Step 6: 提交**

```bash
git add docs/commands.md docs/configuration.md README.md tests/unit/readme_test.py metadata.yaml main.py palworld_terminal/__init__.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py
git commit -m "docs+chore: 权限管理文档/命令表/安全告知 + 版本 v0.8.7"
```

---

## 收尾:整体验证

- [ ] **全套 + lint + mypy + 前端**

Run:
```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
cd frontend && npm run test:run && npm run build && cd ..
node frontend/scripts/verify-bundle.mjs
git diff --exit-code -- pages/settings
```
Expected: 全绿;no-drift 无差异(产物已在 T10 提交)。

- [ ] **命名空间冒烟 + 跨端锚定单独复核**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/namespace_runtime_smoke_test.py tests/unit/command_names_test.py tests/unit/frontend_pal_commands_test.py tests/unit/no_absolute_self_import_test.py -v`
Expected: PASS —— 权限门/whoami 在命名空间加载下不炸;命令串前后端锚定一致。
