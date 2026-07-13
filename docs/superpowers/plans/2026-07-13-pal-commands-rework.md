# `/pal` 命令组重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把服务器授权/撤销/列表收进 `/pal server` 组(裸=列表、`add`/`remove` 子动作),并新增玩家侧 `/pal unbind` 与 `/pal bind` 对称。

**Architecture:** 纯 presentation / main 层重构。`/pal server` 由单个扁平 handler + commands 层自解析首词分流(复刻 `me hide|show` 模式);`RoutingService.use/unbind` 底层零改动,`server add/remove` 仍调它们。玩家解绑镜像 `me()`,新增仓储 `delete_binding`。

**Tech Stack:** Python 3.11+、AstrBot 插件框架、aiosqlite、pytest(pytest-asyncio)。

## Global Constraints

以下约束对每个 Task 隐式生效,值逐字取自 spec 与项目规则:

- **git 提交不得出现任何 Claude / AI / 🤖 署名**:无 `Co-Authored-By`,commit message 正文也不提及 Claude。
- **包内 import 一律相对**:`server`/`unbind_self` 方法体如需包内模块走既有顶层相对导入,**绝不在函数体内绝对自导入**(命名空间加载会炸;仓库有静态防回归扫描)。
- **Windows 上 `python` 被拦截**:一律用 `./.venv/Scripts/python.exe` 跑 pytest / ruff。
- **改中文文案必同步 grep** `tests/unit/readme_test.py` 中文锚点(历史 PR #13 因漏改锚点挂 CI)。
- **`RoutingService.use/unbind` 底层零改动**;**不改 DB schema、不做迁移**;**不改 `bind`/`me` 行为**。
- **严格档打错子命令**:`/pal server` 首词非空且非 `add`/`remove` → 返回 `server_usage`,不静默回落列表。
- **版本升 `v0.8.0` → `v0.8.5`**。
- **子代理 model 一律 opus**。

## 命令面变化速查(before → after)

| 旧 | 新 | 权限 | 场景 |
|---|---|---|---|
| `/pal servers` | `/pal server`(裸) | 全员 | 私聊 / 群聊 |
| `/pal use <名>` | `/pal server add <名>` | 管理员 | 仅群聊 |
| `/pal unbind <名>`(管理员) | `/pal server remove <名>` | 管理员 | 仅群聊 |
| — | `/pal unbind`(玩家) | 全员 | 需已绑定 |

## 文件结构总览

| 文件 | 职责 | 涉及 Task |
|---|---|---|
| `palworld_terminal/adapters/sqlite_repository.py` | 加 `delete_binding` | T1 |
| `palworld_terminal/presentation/locale.py` | 新 key + 提示串去旧命令名 | T2 |
| `palworld_terminal/presentation/commands.py` | 删 `servers/use/unbind`、加 `server`、加 `unbind_self` | T3, T4 |
| `palworld_terminal/presentation/command_registry.py` | `servers`→`server`;加 `unbind_self` | T3, T4 |
| `palworld_terminal/presentation/formatters.py` | `_HELP_ADMIN_EXTRA` 改 server add/remove | T3 |
| `main.py` | 删 `servers/use/unbind` handler、加 `server`、加玩家 `unbind`、升版本 | T3, T4, T6 |
| `_conf_schema.json` / `docs/*` / `README.md` | 文档与 schema 同步 | T5 |
| `metadata.yaml` / `palworld_terminal/__init__.py` | 版本号 | T6 |

---

## Task 1: 仓储 `delete_binding`(玩家解绑的底层)

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`(在 `unset_hidden` 后,约第 170 行)
- Test: `tests/unit/repository_players_binding_test.py`(追加)

**Interfaces:**
- Produces: `Repository.delete_binding(self, platform_hash: str, world_id: str) -> None`——按 `(platform_hash, world_id)` 双条件删一条绑定。T4 的 `unbind_self` 消费它。

- [ ] **Step 1: 写失败测试(两条隔离,单条测不出漏 world_id)**

在 `tests/unit/repository_players_binding_test.py` 末尾追加:

```python
async def test_delete_binding_isolates_by_world(repo):
    # 同一 phash 下两个 world 各有绑定;删 w1 不得误删 w2
    # (单条 upsert→delete→get None 无法区分"漏 AND world_id"的错误 SQL,故用两条隔离)
    await repo.upsert_binding("phash", "w1", "k1")
    await repo.upsert_binding("phash", "w2", "k2")
    await repo.delete_binding("phash", "w1")
    assert await repo.get_binding("phash", "w1") is None
    assert await repo.get_binding("phash", "w2") == "k2"
```

- [ ] **Step 2: 运行,确认因方法不存在而失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_players_binding_test.py::test_delete_binding_isolates_by_world -v`
Expected: FAIL —— `AttributeError: 'Repository' object has no attribute 'delete_binding'`

- [ ] **Step 3: 实现 `delete_binding`**

在 `sqlite_repository.py` 的 `unset_hidden` 方法之后插入(照抄 `unset_hidden` 的纯 DELETE 写法):

```python
    async def delete_binding(self, platform_hash: str, world_id: str) -> None:
        await self._db.execute_write(
            "DELETE FROM player_bindings WHERE platform_hash=? AND world_id=?",
            (platform_hash, world_id),
        )
```

- [ ] **Step 4: 运行,确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_players_binding_test.py -v`
Expected: PASS(含既有 `test_bind_and_get` 等全绿)

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/sqlite_repository.py tests/unit/repository_players_binding_test.py
git commit -m "feat(repo): 新增 delete_binding（玩家解绑底层，双条件隔离）"
```

---

## Task 2: locale —— 新增 key + 提示串去旧命令名

**Files:**
- Modify: `palworld_terminal/presentation/locale.py`
- Test: `tests/unit/locale_rework_test.py`(新建)

**Interfaces:**
- Produces: locale key `server_usage`、`unbind_self_ok`(占位符 `{name}`)、`unbind_self_none`。T3 消费 `server_usage`,T4 消费 `unbind_self_ok`/`unbind_self_none`。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/locale_rework_test.py`:

```python
from palworld_terminal.presentation.locale import MESSAGES, L


def test_new_keys_present():
    assert "server_usage" in MESSAGES
    assert L("unbind_self_ok", name="Alice") == "已解除你与玩家「Alice」的绑定。"
    assert MESSAGES["unbind_self_none"]


def test_hint_strings_drop_old_command_names():
    # 用户可见提示串不得残留已删除的 /pal use、/pal servers
    for key in ("no_server_resolved", "not_authorized", "active_server_stale"):
        assert "/pal use" not in MESSAGES[key], key
    assert "/pal servers" not in MESSAGES["no_server_resolved"]
    # 改后指向新命令
    assert "/pal server add" in MESSAGES["not_authorized"]
```

- [ ] **Step 2: 运行,确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/locale_rework_test.py -v`
Expected: FAIL —— `KeyError: 'server_usage'`(第一个测试),第二个因提示串仍含 `/pal use` 而失败

- [ ] **Step 3: 改 locale.py 提示串**

将 `MESSAGES` 里这三行(现含旧命令名)改为:

```python
    "no_server_resolved": "本会话未指定服务器。管理员可用 /pal server add <名称> 授权，或 /pal server 查看可用服务器。",
```
```python
    "not_authorized": "本会话未被授权使用服务器「{server}」。请管理员先执行 /pal server add {server}。",
```
```python
    "active_server_stale": "当前绑定的服务器已不可用，请管理员重新执行 /pal server add <名称>。",
```

- [ ] **Step 4: 加新 key**

在 `bind_usage` 那条之后(`MESSAGES` 闭合大括号前)追加:

```python
    "server_usage": "用法：/pal server add <名称> 或 /pal server remove <名称>",
    "unbind_self_ok": "已解除你与玩家「{name}」的绑定。",
    "unbind_self_none": "你还没有绑定玩家，无需解绑。",
```

- [ ] **Step 5: 运行,确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/locale_rework_test.py -v`
Expected: PASS

- [ ] **Step 6: 全库回归(确保没测试依赖旧提示串)**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS(全绿)

- [ ] **Step 7: 提交**

```bash
git add palworld_terminal/presentation/locale.py tests/unit/locale_rework_test.py
git commit -m "feat(i18n): 新增 server_usage/unbind_self 文案，提示串去旧命令名"
```

---

## Task 3: `/pal server` 命令(list/add/remove)+ 删除旧 servers/use/管理员 unbind

**Files:**
- Modify: `palworld_terminal/presentation/commands.py`(删 `servers`/`use`/`unbind` 三方法,加 `server`)
- Modify: `palworld_terminal/presentation/command_registry.py`(`servers`→`server`)
- Modify: `palworld_terminal/presentation/formatters.py`(`_HELP_ADMIN_EXTRA`)
- Modify: `main.py`(删 3 handler,加 `server` handler)
- Test: `tests/unit/commands_test.py`(重写 use/unbind 用例)
- Test: `tests/unit/formatters_test.py`(角色分离锚点)
- Test: `tests/integration/routing_e2e_test.py`(use→server)
- Test: `tests/unit/namespace_runtime_smoke_test.py`(calls 清单)

**Interfaces:**
- Consumes: `L("server_usage")`(T2);`RoutingService.use(umo,name)`/`unbind(umo,name)`(底层,不变);`format_servers(rows, skipped, is_admin)`;`ServerStatusRow`(commands.py 已导入)。
- Produces: `Commands.server(self, umo, message_str, is_group, is_admin) -> str`;main.py handler `PalWorldTerminal.server`。

> 说明:本 Task 删除旧管理员 `/pal unbind` 后,`/pal unbind` 命令暂时不存在——玩家版在 T4 补上。中间态是自洽且可测的。

- [ ] **Step 1: 重写 commands 层单元测试(先让它们红)**

在 `tests/unit/commands_test.py` 中,**删除** `test_use_requires_group`、`test_use_requires_admin`、`test_unbind_requires_admin`、`test_use_happy_path`、`test_unbind_happy_path` 五个函数,替换为:

```python
async def test_server_add_requires_group():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server add alpha", is_group=False, is_admin=True)
    assert "仅可在群聊" in out


async def test_server_add_requires_admin():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server add alpha", is_group=True, is_admin=False)
    assert out == L("admin_required")


async def test_server_add_happy_path():
    routing = _FakeRouting(Resolution(_server(), None))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server add alpha", is_group=True, is_admin=True)
    assert out == "USE_OK:alpha"
    assert routing.used == ("umo1", "alpha")


async def test_server_remove_happy_path():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server remove alpha", is_group=True, is_admin=True)
    assert out == "UNBIND_OK:alpha"


async def test_server_add_without_name_returns_usage():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server add", is_group=True, is_admin=True)
    assert out == L("server_usage")


async def test_server_typo_subcommand_returns_usage():
    # 严格档:非空非 add/remove 首词 → 用法提示,不静默列表
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server addd alpha", is_group=True, is_admin=True)
    assert out == L("server_usage")


async def test_server_bare_lists():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server", is_group=True, is_admin=False)
    assert "已配置服务器" in out and "alpha" in out


async def test_server_add_override_token():
    # /pal server add @alpha:@alpha 被剥成 server_override,首词 add 留在 arg.name;override 优先命中
    routing = _FakeRouting(Resolution(_server(), None))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.server("umo1", "/pal server add @alpha", is_group=True, is_admin=True)
    assert out == "USE_OK:alpha"
    assert routing.used == ("umo1", "alpha")
```

并把 `test_help_role_separation`(现断言 `"use"`)改为:

```python
def test_help_role_separation():
    cmds = Commands(
        _FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), _cfg_all_on(), None
    )
    assert "server add" in cmds.help("/pal help", is_admin=True)
    assert "server add" not in cmds.help("/pal help", is_admin=False)
```

- [ ] **Step 2: 运行,确认红(方法不存在)**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_test.py -v`
Expected: FAIL —— `AttributeError: 'Commands' object has no attribute 'server'`

- [ ] **Step 3: commands.py —— 删旧三方法、加 `server()`**

在 `palworld_terminal/presentation/commands.py` 中,**删除** `servers()`、`use()`、`unbind()` 三个方法(现约 220-249 行),替换为单个 `server()`:

```python
    async def server(self, umo, message_str, is_group, is_admin) -> str:
        arg = parse_arg(message_str, "server")
        tokens = arg.name.split()
        sub = tokens[0].lower() if tokens else ""
        name = arg.server_override or (" ".join(tokens[1:]) if len(tokens) > 1 else "")

        if sub in ("add", "remove"):
            if not is_admin:
                return L("admin_required")
            if not is_group:
                return L("use_only_group")
            if not name:
                return L("server_usage")
            if sub == "add":
                return await self._routing.use(umo, name)       # 底层不变
            return await self._routing.unbind(umo, name)         # 底层不变

        if sub:  # 非空非 add/remove:打错的子命令 → 用法提示,不静默回落列表
            return L("server_usage")

        # 裸命令（空首词）= 服务器列表（原 servers() 逻辑，私聊也可）
        ready_ids = {s.server_id for s in self._routing.ready_servers()}
        group = await self._repo.list_group_servers(umo) if is_group else {}
        rows = []
        for s in (self._cfg.servers if self._cfg else self._routing.ready_servers()):
            allowed, active = group.get(s.server_id, (False, False))
            rows.append(ServerStatusRow(
                name=s.name, ready=s.ready, online=s.server_id in ready_ids,
                allowed=allowed, active=active,
            ))
        skipped = self._cfg.skipped if self._cfg else []
        return format_servers(rows, skipped, is_admin)
```

- [ ] **Step 4: command_registry.py —— `servers`→`server`**

改 `COMMANDS`:把 `("servers", "core")` 改为 `("server", "core")`。
改 `HELP_LINE`:删 `"servers": ...` 这条,加(guest 只显示"服务器列表",add/remove 由 `_HELP_ADMIN_EXTRA` 仅对管理员展示):

```python
    "server": "/pal server  服务器列表",
```

- [ ] **Step 5: formatters.py —— `_HELP_ADMIN_EXTRA`**

把 `_HELP_ADMIN_EXTRA` 改为:

```python
_HELP_ADMIN_EXTRA = [
    "管理员命令：",
    "/pal server add <名称>  授权本群并设为活动服务器（仅群聊）",
    "/pal server remove <名称>  撤销本群授权",
]
```

- [ ] **Step 6: 运行 commands + formatters 单元测试**

先把 `formatters_test.py` 的角色分离测试对齐——把 `test_format_help_role_separation`(第 113 行起)里 `assert "use" in admin` 改为 `assert "server add" in admin`(第 119 行的 `"use" not in guest` 保留,新 guest server 行不含 `"use"` 也不含 `"server add"`):

```python
def test_format_help_role_separation():
    from palworld_terminal.config import FeaturesConfig
    feats = FeaturesConfig(report=True, events=True, guilds_bases=True)
    admin = format_help(None, is_admin=True, features=feats)
    assert "server add" in admin
    guest = format_help(None, is_admin=False, features=feats)
    assert "server add" not in guest and "status" in guest
```

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_test.py tests/unit/formatters_test.py -v`
Expected: PASS

- [ ] **Step 7: main.py —— 删 3 handler、加 `server` handler**

在 `main.py` 中**删除** `@pal.command("servers")` handler、`@filter.permission_type(...) @pal.command("use")` handler、`@filter.permission_type(...) @pal.command("unbind")` handler(现约 398-427 行)。在 `@pal.command("bind")` 之后、`@pal.command("help")` 之前插入:

```python
    @pal.command("server")
    async def server(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.server(
                self._umo(event), self._msg(event), self._is_group(event), self._is_admin(event)))
        )
```

- [ ] **Step 8: routing_e2e —— use→server**

在 `tests/integration/routing_e2e_test.py` 第 70-72 行,把注释与调用改为:

```python
        # 2) admin authorizes via /pal server add
        use_msg = await c.commands.server(UMO, "/pal server add alpha", is_group=True, is_admin=True)
        assert "alpha" in use_msg
```

- [ ] **Step 9: 冒烟 calls 清单 —— 旧命令换成 server(暂不加玩家 unbind)**

在 `tests/unit/namespace_runtime_smoke_test.py` 的 `calls` 列表里替换三处(**docstring 的命令条数留到 T4 一并改**):

```python
                (plugin.server, "server"), (plugin.help, ""),
                (plugin.server, "server add alpha"), (plugin.server, "server remove alpha"),
```
(即原 `(plugin.servers, "")`、`(plugin.use, "use alpha")`、`(plugin.unbind, "unbind alpha")` 三行的位置)

- [ ] **Step 10: 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS(全绿,ruff 0 error)

- [ ] **Step 11: 提交**

```bash
git add palworld_terminal/presentation/commands.py palworld_terminal/presentation/command_registry.py palworld_terminal/presentation/formatters.py main.py tests/unit/commands_test.py tests/unit/formatters_test.py tests/integration/routing_e2e_test.py tests/unit/namespace_runtime_smoke_test.py
git commit -m "feat(cmd): /pal server 组统一服务器列表/授权/撤销，删除 servers/use/管理员 unbind"
```

---

## Task 4: 玩家侧 `/pal unbind`(与 `/pal bind` 对称)

**Files:**
- Modify: `palworld_terminal/presentation/commands.py`(加 `unbind_self`)
- Modify: `palworld_terminal/presentation/command_registry.py`(加 `("unbind_self","players")` + HELP_LINE)
- Modify: `main.py`(加 `@pal.command("unbind")` 玩家 handler)
- Test: `tests/unit/commands_me_bind_test.py`(真 Repository:bind→unbind→me)
- Test: `tests/unit/players_group_off_test.py`(关组隐藏)
- Test: `tests/unit/namespace_runtime_smoke_test.py`(加玩家 unbind + docstring 计数)

**Interfaces:**
- Consumes: `Repository.delete_binding`(T1)、`L("unbind_self_ok"/"unbind_self_none")`(T2)、`hash_user_id`(commands.py 已导入)、`Repository.get_binding`/`get_player`。
- Produces: `Commands.unbind_self(self, umo, message_str, is_group, sender_id) -> str`(带 `@_gated`,属 players 组);main.py handler `PalWorldTerminal.unbind`。

- [ ] **Step 1: 写失败测试(真 Repository fixture,能抓 no-op 删除)**

在 `tests/unit/commands_me_bind_test.py` 末尾追加:

```python
async def test_bind_then_unbind_clears_binding(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.unbind_self("u", "unbind", True, "aiocqhttp:1")
    assert "Alice" in out and "解除" in out
    # 解绑后 me 显示未绑定(真 DB 验证 delete_binding 生效;no-op 删除会让此断言转红)
    assert "还没绑定" in await c.me("u", "me", True, "aiocqhttp:1")


async def test_unbind_when_not_bound(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).unbind_self("u", "unbind", True, "aiocqhttp:9")
    assert "还没有绑定" in out
```

- [ ] **Step 2: 运行,确认红**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_me_bind_test.py -v`
Expected: FAIL —— `AttributeError: 'Commands' object has no attribute 'unbind_self'`

- [ ] **Step 3: commands.py —— 加 `unbind_self()`**

在 `me()` 方法之后插入(带 `@_gated`,镜像 `me()` 的 world/hash 解析):

```python
    @_gated
    async def unbind_self(self, umo, message_str, is_group, sender_id) -> str:
        world, _arg, err = await self._resolve_world(umo, message_str, "unbind", is_group)
        if err is not None:
            return err
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        player_key = await self._repo.get_binding(phash, world.world_id)
        if player_key is None:
            return L("unbind_self_none")
        ident = await self._repo.get_player(world.world_id, player_key)
        name = ident.latest_name if ident is not None else player_key
        await self._repo.delete_binding(phash, world.world_id)
        return L("unbind_self_ok", name=name)
```

- [ ] **Step 4: command_registry.py —— 注册 players 组**

`COMMANDS`:在 `("bind", "players")` 之后加 `("unbind_self", "players")`。
`HELP_LINE`:在 `"bind": ...` 之后加:

```python
    "unbind_self": "/pal unbind  解除我的玩家绑定",
```

- [ ] **Step 5: 运行,确认绑定/解绑测试通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_me_bind_test.py -v`
Expected: PASS

- [ ] **Step 6: main.py —— 加玩家 `unbind` handler**

在 `@pal.command("bind")` handler 之后插入(全员,透传 `sender_id`,与 bind 对称):

```python
    @pal.command("unbind")
    async def unbind(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.unbind_self(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event)))
        )
```

- [ ] **Step 7: players_group_off —— 关组隐藏断言**

在 `tests/unit/players_group_off_test.py`:
`test_players_commands_gated_off` 的 for 元组里加 `c.unbind_self("u", "", True, "p:1")`:

```python
async def test_players_commands_gated_off():
    c = _cmds(players_on=False)
    for coro in (c.rank("u", "", True), c.player("u", "Alice", True),
                 c.me("u", "", True, "p:1"), c.bind("u", "Alice", True, "p:1"),
                 c.unbind_self("u", "", True, "p:1")):
        assert await coro == "该功能未开放：当前配置或服务器不支持。"
```

`test_help_hides_players_when_off` 加 `/pal unbind` 的开/关断言:

```python
def test_help_hides_players_when_off():
    off = format_help(None, False, FeaturesConfig(report=True, events=True, guilds_bases=False, players=False))
    on = format_help(None, False, FeaturesConfig(report=True, events=True, guilds_bases=False, players=True))
    assert "/pal rank" not in off and "/pal player" not in off and "/pal unbind" not in off
    assert "/pal rank" in on and "/pal bind" in on and "/pal unbind" in on
```

- [ ] **Step 8: 冒烟 —— 加玩家 unbind + 更新 docstring 计数**

在 `tests/unit/namespace_runtime_smoke_test.py`:在 `(plugin.me, "me")` 那行之后插入 `(plugin.unbind, "unbind")`(bind→me→unbind 连续,复现"绑定后解绑"深分支):

```python
                (plugin.me, "me"),            # ……me 才会走到档案(DTO)深分支
                (plugin.unbind, "unbind"),    # 绑定后解绑,走 delete_binding 深分支
```

把文件头 docstring 里写死的「18 条命令」改为:

```
把全部 17 条命令带参数走一遍(server 走裸/add/remove 三种参数,calls 共 19 项;
bind 成功后再走 unbind/me,复现当年实机 bug 的等价深分支)——任何仅在真实
```
> 注:冒烟仅验证命名空间加载下不炸,**不**验证 `delete_binding` 正确性(`unbind_self` 删完无条件返回 ok);删除正确性由 Step 1 的真 Repository 测试兜底。

- [ ] **Step 9: 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS(全绿)

- [ ] **Step 10: 提交**

```bash
git add palworld_terminal/presentation/commands.py palworld_terminal/presentation/command_registry.py main.py tests/unit/commands_me_bind_test.py tests/unit/players_group_off_test.py tests/unit/namespace_runtime_smoke_test.py
git commit -m "feat(cmd): 新增玩家 /pal unbind 解除自身绑定，与 /pal bind 对称"
```

---

## Task 5: 文档、schema 与 readme_test 锚点同步

**Files:**
- Modify: `docs/commands.md`、`README.md`、`docs/configuration.md`、`_conf_schema.json`、`docs/verification/real-server-checklist.md`
- Test: `tests/unit/readme_test.py`(锚点)

**Interfaces:** 无代码接口;本 Task 让 `readme_test.py` 与新命令面对齐,并清掉实机可见的旧命令名。

- [ ] **Step 1: 更新 readme_test 锚点(先红)**

在 `tests/unit/readme_test.py`:
`test_readme_requirements_and_usage`(第 27 行)把 `"/pal use"` 改为 `"/pal server add"`。
`test_readme_command_table_and_matrix`(第 89-90 行)把 `"/pal servers"` 改为 `"/pal server"`,并**删除** `"/pal use", "/pal unbind"`(玩家 unbind 锚点移到下方 players 测试):

```python
                      "/pal bases", "/pal base", "/pal server", "/pal help",
                      "@<服务器名>"):
```

`test_readme_documents_players_group`(第 98 行)加 `"/pal unbind"`:

```python
    for phrase in ("/pal rank", "/pal player", "/pal me", "/pal bind", "/pal unbind", "players"):
```

- [ ] **Step 2: 运行,确认红(docs 尚未同步)**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -v`
Expected: FAIL(`文档指令表缺少: /pal server` 等——docs 仍是旧命令名)

- [ ] **Step 3: 改 docs/commands.md**

指令详表:在 `/pal bind` 行之后加玩家 unbind 行:

```
| `/pal unbind` | — | `players` | 所有人 | 解除我的玩家绑定(与 `/pal bind` 对称) |
```

把 `/pal servers` 行(现第 23 行)改为:

```
| `/pal server` | `[add\|remove <名称>]` | `core` | 所有人（add/remove 管理员·仅群聊） | 裸命令=服务器列表+本群授权/活动；`add`/`remove` 授权/撤销本群 |
```

**删除**原 `/pal use`、管理员 `/pal unbind` 两行(现第 25-26 行)。

功能开关矩阵 `core` 组那行(现第 36 行)把指令列改为(去掉 servers/use/unbind,换 server):

```
| `core`（不可关闭） | 恒开 | `status` `online` `world` `rules` `server` `help` | ✅ 可用 | —（无法关闭） |
```

`players` 组那行(现第 40 行)加 `unbind`:

```
| `players` | **关** | `rank` `player` `me` `bind` `unbind` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
```

「多服务器与群授权」节(现第 48-50 行)改为:

```
- `/pal server`:列出所有服务器与本群授权/活动状态。
- `/pal server add <名称>`（管理员，仅群聊）：授权本群使用该服务器并设为活动服务器。
- `/pal server remove <名称>`（管理员，仅群聊）：撤销本群对该服务器的授权。
```

- [ ] **Step 4: 改 README.md**

- 第 55 行 `/pal use <服务器名>` → `/pal server add <服务器名>`。
- 第 71 行 `| \`/pal servers\` | 服务器列表与本群授权状态 |` → `| \`/pal server\` | 服务器列表与本群授权状态 |`。
- 第 72 行 `| \`/pal use <名称>\` | **管理员** · 授权本群使用某服务器 |` → `| \`/pal server add <名称>\` | **管理员** · 授权本群使用某服务器 |`。
- 第 107 行 `18 条指令详表` → `17 条指令详表`。

- [ ] **Step 5: 改 docs/configuration.md、_conf_schema.json、real-server-checklist.md**

`docs/configuration.md` 第 12 行:`等价于管理员执行 /pal use` → `等价于管理员执行 /pal server add`。

`_conf_schema.json` 第 35 行 `group_bindings` 的 `description`:`预设 群→服务器 授权（可选，等价于管理员 /pal use）` → `预设 群→服务器 授权（可选，等价于管理员 /pal server add）`。

`docs/verification/real-server-checklist.md` 第 235 行:`管理员 /pal use testsv 后同群可查` → `管理员 /pal server add testsv 后同群可查`(`use_ok` 文案 key 保留,只改命令名)。

- [ ] **Step 6: 运行 readme_test,确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -v`
Expected: PASS

- [ ] **Step 7: grep 确认无残留旧命令名(子串陷阱防护)**

Run: `./.venv/Scripts/python.exe -c "import pathlib,re,sys; files=['README.md','docs/commands.md','docs/configuration.md','_conf_schema.json','docs/verification/real-server-checklist.md']; bad=[(f,l) for f in files for l in pathlib.Path(f).read_text(encoding='utf-8').splitlines() if '/pal servers' in l or '/pal use' in l]; print(bad); sys.exit(1 if bad else 0)"`
Expected: `[]` 且退出码 0(无任何 `/pal servers`、`/pal use` 残留)

- [ ] **Step 8: 提交**

```bash
git add docs/commands.md README.md docs/configuration.md _conf_schema.json docs/verification/real-server-checklist.md tests/unit/readme_test.py
git commit -m "docs: 命令面文档与 schema 同步到 /pal server + 玩家 unbind（含实机可见 _conf_schema）"
```

---

## Task 6: 版本号 v0.8.0 → v0.8.5

**Files:**
- Modify: `metadata.yaml`、`main.py`、`palworld_terminal/__init__.py`、`README.md`
- Test: `tests/unit/phase1_smoke_test.py`、`tests/unit/skeleton_test.py`(版本断言)

**Interfaces:** 无。`main_test.py` 动态比对 `@register` 版本与 `metadata.yaml`,只要两者一致即通过。

- [ ] **Step 1: 更新版本断言测试(先红)**

`tests/unit/phase1_smoke_test.py` 第 19 行 `assert __version__ == "0.8.0"` → `assert __version__ == "0.8.5"`。
`tests/unit/skeleton_test.py` 第 11 行 `assert palworld_terminal.__version__ == "0.8.0"` → `assert palworld_terminal.__version__ == "0.8.5"`。

- [ ] **Step 2: 运行,确认红**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py tests/unit/main_test.py -v`
Expected: FAIL(`assert '0.8.0' == '0.8.5'`;`main_test` 亦因 `@register`≠metadata 而可能红)

- [ ] **Step 3: 改四处版本源**

`metadata.yaml` 第 4 行:`version: v0.8.0` → `version: v0.8.5`。
`main.py` 第 81 行 `@register(...)` 的版本参数:`"v0.8.0"` → `"v0.8.5"`。
`palworld_terminal/__init__.py` 第 3 行:`__version__ = "0.8.0"` → `__version__ = "0.8.5"`。
`README.md` 第 7 行徽章:`version-v0.8.0-007ec6` → `version-v0.8.5-007ec6`。

- [ ] **Step 4: 运行,确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py tests/unit/main_test.py -v`
Expected: PASS

- [ ] **Step 5: 全库回归 + ruff**

Run: `./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS(全绿,ruff 0 error)

- [ ] **Step 6: 提交**

```bash
git add metadata.yaml main.py palworld_terminal/__init__.py README.md tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py
git commit -m "chore: 版本升 v0.8.5（命令面重构）"
```

---

## 收尾:整体验证

- [ ] **全套测试 + lint + mypy**

Run:
```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
```
Expected: 全绿。

- [ ] **命名空间冒烟单独复核**(真实加载形态)

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/namespace_runtime_smoke_test.py tests/unit/no_absolute_self_import_test.py tests/unit/astrbot_namespace_load_test.py -v`
Expected: PASS —— 确认新 `server`/`unbind` handler 在命名空间加载下不炸、无绝对自导入。
