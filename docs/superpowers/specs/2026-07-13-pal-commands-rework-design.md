# `/pal` 命令组重构设计

> 状态:已批准,待写实施计划
> 日期:2026-07-13
> 范围:presentation / main 层的命令面重构,不触 domain / infrastructure / application 核心逻辑

## 目标

把 `/pal` 命令组里"服务器管理"与"玩家绑定"两条线的命名理顺:

1. 服务器的授权/撤销/列表全部收进 `/pal server` 组(裸命令=列表,`add`/`remove` 为子动作)。
2. 玩家侧新增 `/pal unbind`,与 `/pal bind` 成对对称,让用户能解除自己的玩家绑定。

旧的服务器命令(`/pal servers`、`/pal use`、管理员 `/pal unbind`)直接删除,不留过渡别名——当前用户基数小,靠 `/pal help` 与 README 引导即可。

## 命令面变化(before → after)

| 旧命令 | 新命令 | 权限 | 场景 |
|---|---|---|---|
| `/pal servers` | `/pal server`(裸) | 全员 | 私聊 / 群聊 |
| `/pal use <名>` | `/pal server add <名>` | 管理员 | 仅群聊 |
| `/pal unbind <名>`(管理员) | `/pal server remove <名>` | 管理员 | 仅群聊 |
| — | `/pal unbind`(新,玩家) | 全员 | 需已绑定 |
| `/pal bind <名>` | 不变 | 全员 | |

关键约束:旧的管理员 `/pal unbind` 删除后,`unbind` 命令名腾出,由新的玩家解绑接管。`bind`/`unbind` 在玩家侧成对。

## 实现方案:扁平命令 + 自解析(方案 B)

不采用 AstrBot 嵌套命令组(`@pal.group("server")`)。原因:

- 框架对"裸组"(`/pal server` 不带子命令)硬编码回一段"参数不足 + 子指令树"的 `ValueError`,**无法配置成返回业务列表**;而本设计要的正是"裸 `/pal server` = 列表"。
- 扁平命令 + 在 commands 层自解析首词,复刻仓库里已验证、已被测试覆盖的 `/pal me hide|show`、`/pal rank time|level` 模式,新人一眼看懂。
- 不新增任何 AstrBot 框架版本耦合(嵌套组行为随框架版本可能漂移)。

`/pal server` 由单个 `@pal.command("server")` handler 承接,commands 层 `server()` 方法用 `parse_arg` 拿到首词后分流 `add`/`remove`/裸=列表。权限门下沉到方法体(与旧 `use`/`unbind` 的方法体守卫完全同款)。

## 架构与组件

全部改动落在 presentation / main 层。`RoutingService.use/unbind` 底层零改动——`server add/remove` 仍调它们。

### main.py(handler 层)

- **删** `@pal.command("servers")` handler。
- **删** `@filter.permission_type(ADMIN) @pal.command("use")` handler。
- **删** `@filter.permission_type(ADMIN) @pal.command("unbind")` handler。
- **加** `@pal.command("server")`(**不带**框架权限门,权限下沉方法体),转调 `c.commands.server(umo, msg, is_group, is_admin)`。
- **加** `@pal.command("unbind")`(全员),转调 `c.commands.unbind_self(umo, msg, is_group, sender_id)`。

`pal` 命令组装饰器与其它 handler 不变。

### palworld_terminal/presentation/commands.py

- **删** `servers()`、`use()`、`unbind()` 三个方法(逻辑并入 `server()`)。
- **加** `async def server(self, umo, message_str, is_group, is_admin) -> str`:自解析分流。**不加** `@_gated`(与旧 `servers` 一致,core 命令始终可用)。
- **加** `@_gated async def unbind_self(self, umo, message_str, is_group, sender_id) -> str`:玩家解绑。**须带** `@_gated`(属 players 组,与 `bind` 一致)。

`server()` 逻辑契约:

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
            return await self._routing.use(umo, name)      # 底层不变
        return await self._routing.unbind(umo, name)        # 底层不变

    # 默认(含空首词、未知首词):列表,内联旧 servers() 逻辑,私聊也可
    ready_ids = {s.server_id for s in self._routing.ready_servers()}
    group = await self._repo.list_group_servers(umo) if is_group else {}
    rows = [...]  # 同旧 servers()
    return format_servers(rows, self._cfg.skipped if self._cfg else [], is_admin)
```

`unbind_self()` 逻辑契约(镜像 `me()`):

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

### palworld_terminal/adapters/sqlite_repository.py

- **加** `async def delete_binding(self, platform_hash: str, world_id: str) -> None`:纯 DELETE,照抄 `unset_hidden` 的写法。`player_bindings` 表主键 `(platform_hash, world_id)`,表已存在,**无需迁移**。

```python
async def delete_binding(self, platform_hash: str, world_id: str) -> None:
    await self._db.execute_write(
        "DELETE FROM player_bindings WHERE platform_hash=? AND world_id=?",
        (platform_hash, world_id),
    )
```

### palworld_terminal/presentation/command_registry.py

- `COMMANDS`:`("servers", "core")` → `("server", "core")`;在 players 组追加 `("unbind_self", "players")`。
- `HELP_LINE`:删 `"servers"` 键,加 `"server": "/pal server  服务器列表（管理员可 add/remove）"`;加 `"unbind_self": "/pal unbind  解除我的玩家绑定"`。

注:`COMMANDS` 的 name 是 commands.py 方法名(供 `_gated` 用 `fn.__name__` 查组,以及 `format_help` 迭代显示),与 astrbot 的 `@pal.command("X")` 字符串解耦。玩家解绑 commands 方法名 `unbind_self`,astrbot 命令字符串 `unbind`,HELP_LINE 显示文案写 `/pal unbind`。

### palworld_terminal/presentation/formatters.py

- `_HELP_ADMIN_EXTRA`:`/pal use <名称>` → `/pal server add <名称>`;`/pal unbind <名称>` → `/pal server remove <名称>`。
- `format_servers`、`format_help` 逻辑不变(server list 分支仍调 `format_servers`)。

### palworld_terminal/presentation/locale.py

**新增 key:**

- `server_usage`: `用法：/pal server add <名称> 或 /pal server remove <名称>`
- `unbind_self_ok`: `已解除你与玩家「{name}」的绑定。`
- `unbind_self_none`: `你还没有绑定玩家，无需解绑。`

**保留不改的 key**(内部标识,文案对新命令依然贴切):`use_ok`(server add 触发)、`unbind_ok`(server remove 触发)、`admin_required`、`use_only_group`。

**须改的用户可见提示串**(内嵌了旧命令名):

- `no_server_resolved`:`/pal use <名称>` → `/pal server add <名称>`;`/pal servers` → `/pal server`。
- `not_authorized`:`/pal use {server}` → `/pal server add {server}`。
- `active_server_stale`:`/pal use <名称>` → `/pal server add <名称>`。

## 数据流

```
/pal server add alpha
  → main.server → _guarded → commands.server()
  → parse_arg("server") → sub="add", name="alpha"
  → 守卫(管理员 → 群聊 → 名字非空) → routing.use(umo,"alpha") → L("use_ok")

/pal server（裸）
  → commands.server() → sub="" → 列表分支 → format_servers(...)

/pal unbind
  → main.unbind → commands.unbind_self()
  → resolve_world → hash_user_id → get_binding 检查
  → get_player 取名 → delete_binding → L("unbind_self_ok", name=…)
  （未绑定 → L("unbind_self_none")）
```

## 权限 / 守卫矩阵

| 命令 | 权限 | 群聊限制 | 其它 |
|---|---|---|---|
| `/pal server`(list) | 全员 | 无(私聊可列表,保留旧 `servers` 行为) | — |
| `/pal server add\|remove` | 管理员 | 仅群聊 | 名字空 → `server_usage` |
| `/pal unbind` | 全员 | 无(与 `bind` 一致) | 未绑定 → `unbind_self_none` |

## 边界情形

- **`/pal server add @alpha`**:`parse_arg` 会把 `@alpha` 剥成 `server_override`、`name` 变空。用 `name = arg.server_override or 拼词` 兜底(旧 `use`/`unbind` 即此写法,照抄)。
- **未知首词**(如 `/pal server foo`):只有 `add`/`remove` 是子命令,其余(含空)一律走列表。宽容,天然满足"裸=列表"。
- **名为 "add"/"remove" 的服务器**:`/pal server add add` 可正常工作(sub=add,name=add)。极端且无害,接受。

## 测试策略

### 需改的现有测试

- `tests/unit/commands_test.py`:重写 `test_use_*`、`test_unbind_*` 为 `server()` 分流 + 权限用例;`test_help_role_separation` 的锚点 `"use"` 改为新管理员命令关键词(如 `"server add"`)。`_FakeRouting.use/unbind` 保留(底层仍调)。
- `tests/unit/namespace_runtime_smoke_test.py`:`calls` 清单里 `(plugin.servers,"")` → `(plugin.server,"server")`;`(plugin.use,"use alpha")` → `(plugin.server,"server add alpha")`;`(plugin.unbind,"unbind alpha")` → `(plugin.server,"server remove alpha")`;追加 `(plugin.unbind,"unbind")`(玩家解绑,在 bind 之后,复现"绑定后解绑"深分支);更新头注释里写死的命令条数。
- `tests/integration/routing_e2e_test.py`:`c.commands.use(UMO,"/pal use alpha",...)` → `c.commands.server(UMO,"/pal server add alpha", is_group=True, is_admin=True)`;断言 `"alpha" in` 保留。
- `tests/unit/readme_test.py`:中文锚点(`/pal use`、`/pal unbind`、`/pal servers`、core 组矩阵)逐字同步为新命令名。**这是历史 CI 雷点(PR #13),命令改名后 docs 与 readme_test 锚点必须逐字对齐。**

### 需新增的测试

- `delete_binding` 仓储测试:upsert → get 命中 → delete → get 返回 None。
- `unbind_self` 命令测试:绑定后 `unbind` 返回 `unbind_self_ok` 且带玩家名;未绑定时返回 `unbind_self_none`;解绑后 `me` 显示未绑定。
- `server()` 分流测试:裸=列表;`add`/`remove` 的管理员门、群聊门、空名门;`add @alpha` 的 override 兜底。

### 需同步的文档

- `docs/commands.md`:指令详表(`servers`/`use`/`unbind` 行)、功能开关矩阵(core 组列出的命令名)、多服务器与群授权节。
- `docs/configuration.md`:`group_bindings` 注释"等价于管理员 `/pal use`" → `/pal server add`。
- `README.md`:含 `/pal use`、`/pal servers` 的引用同步(readme_test 从 README + docs 合集断言)。

## 版本

`v0.8.0` → `v0.9.0`(新增命令 + 命令面变更,minor bump)。需同步:`metadata.yaml`、`main.py` 的 `@register(...)` 版本参数、README 版本徽章,以及 grep `0.8.0` 的其余引用。

## 命名空间加载安全性

本设计不新增任何 import 语句,`server`/`unbind_self` 方法体如需包内模块须走既有顶层相对导入(绝不在函数体内绝对自导入)。历史 `/pal me` 崩溃根因是函数体内绝对自导入,与命令注册机制无关;既有静态防回归扫描 + 命名空间运行时冒烟对新方法同样生效。

## 非目标(YAGNI)

- 不做嵌套命令组。
- 不做旧命令的过渡别名 / 弃用提示。
- 不改 `RoutingService` 底层、不改 DB schema、不做迁移。
- 不改玩家 `bind` / `me` 的行为。
