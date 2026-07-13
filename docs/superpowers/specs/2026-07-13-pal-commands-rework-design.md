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

    # 严格档:非空非 add/remove 的首词(打错的子命令,如 addd/remve)→ 用法提示,
    # 不静默回落列表。add/remove 是有副作用的管理操作,静默 no-op 危险,
    # 且用法提示能引导正确子命令。此处刻意偏离 me/rank 的宽容回落。
    if sub:
        return L("server_usage")

    # 仅裸命令(空首词)= 列表,内联旧 servers() 逻辑,私聊也可
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
- `HELP_LINE`:删 `"servers"` 键,加 `"server": "/pal server  服务器列表"`(**不含** add/remove——它们是管理员子动作,由 `_HELP_ADMIN_EXTRA` 仅对管理员展示,保持旧 use/unbind 的角色隔离,避免向全员泄露用不了的动作);加 `"unbind_self": "/pal unbind  解除我的玩家绑定"`。

注:`COMMANDS` 的 name 是 commands.py 方法名(供 `_gated` 用 `fn.__name__` 查组,以及 `format_help` 迭代显示),与 astrbot 的 `@pal.command("X")` 字符串解耦。玩家解绑 commands 方法名 `unbind_self`,astrbot 命令字符串 `unbind`,HELP_LINE 显示文案写 `/pal unbind`。

### palworld_terminal/presentation/formatters.py

- `_HELP_ADMIN_EXTRA`:`/pal use <名称>` → `/pal server add <名称>`;`/pal unbind <名称>` → `/pal server remove <名称>`。
- `format_servers`、`format_help` 逻辑不变(server list 分支仍调 `format_servers`)。

### palworld_terminal/presentation/locale.py

**新增 key:**

- `server_usage`: `用法：/pal server add <名称> 或 /pal server remove <名称>`（打错子命令或缺名字时返回;裸 /pal server 直接列表,不触发此提示）
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

/pal server addd alpha（打错子命令）
  → commands.server() → sub="addd" 非空且非 add/remove → L("server_usage")

/pal unbind
  → main.unbind → commands.unbind_self()
  → resolve_world → hash_user_id → get_binding 检查
  → get_player 取名 → delete_binding → L("unbind_self_ok", name=…)
  （未绑定 → L("unbind_self_none")）
```

## 权限 / 守卫矩阵

| 命令 | 权限 | 群聊限制 | 其它 |
|---|---|---|---|
| `/pal server`(裸=list) | 全员 | 无(私聊可列表,保留旧 `servers` 行为) | 非空非 add/remove 首词 → `server_usage` |
| `/pal server add\|remove` | 管理员 | 仅群聊 | 名字空 → `server_usage` |
| `/pal unbind` | 全员 | 无显式限制,但经 `_resolve_world`,restricted 模式私聊会被 `private_restricted` 拦(与 `bind`/`me` 同款,见边界情形) | 未绑定 → `unbind_self_none` |

## 边界情形

- **`/pal server add @alpha`**:`parse_arg` 把尾部 `@alpha` 剥成 `server_override="alpha"`,首词 `add` 仍留在 `arg.name`(即 `arg.name="add"`,**不是空**)。契约 `name = arg.server_override or 拼词` 让 override 优先命中,`name="alpha"`,正确授权 alpha。(旧 `use`/`unbind` 即此语义。)
- **`/pal server add alpha @beta`**(位置名与 `@override` 并存):尾部 `@beta` 剥成 `server_override="beta"`,`name = arg.server_override or ...` 令 override 优先 → 授权 **beta** 而非肉眼的 alpha。沿用旧 `use` 语义(`name = arg.server_override or arg.name`),不算回归。实现者与测试须明确此优先级,勿当 bug 反复排查。
- **未知/打错首词**(如 `/pal server addd alpha`、`/pal server foo`):严格档——首词非空且非 `add`/`remove` → 返回 `server_usage`,**不**静默回落列表。理由:`add`/`remove` 是有副作用的管理操作,静默 no-op 会让管理员误以为已授权/撤销;这里刻意偏离 `me`/`rank` 的宽容回落。只有**空首词**(纯裸 `/pal server`)才列表。
- **名为 "add"/"remove" 的服务器**:`/pal server add add` 可正常工作(sub=add,name=add)。极端且无害,接受。
- **restricted 模式 + 私聊下 `/pal unbind`**:`unbind_self` 经 `_resolve_world` → `RoutingService.resolve`,restricted+非群聊会先返回 `private_restricted`「私聊不可查询」。解绑是写操作,该文案用词不贴切,但这是 `bind`/`me` 的**既有同款行为**(底层 `RoutingService` 本设计零改动)。**记录为已知行为,本轮不修**——restricted 私聊本就无法定位 world,阻断合理,仅文案措辞欠佳;若日后要改,应在 `RoutingService` 层单独处理,超出本 spec 范围。

## 测试策略

### 需改的现有测试

- `tests/unit/commands_test.py`:重写 `test_use_*`、`test_unbind_*` 为 `server()` 分流 + 权限用例;`test_help_role_separation` 的锚点 `"use"` 改为新管理员命令关键词(如 `"server add"`)。`_FakeRouting.use/unbind` 保留(底层仍调)。
- **`tests/unit/formatters_test.py`::`test_format_help_role_separation`**(**与上一条不同文件、不同函数,必改否则挂 CI**):它直接测 `format_help`,断言 `"use" in admin`(admin help)。改 `_HELP_ADMIN_EXTRA` 后 admin help 不再含 `"use"` 子串,该断言 100% 失败。改为 `assert "server add" in admin`;guest 分支 `"use" not in guest` 保留(新 guest server 行文案「服务器列表」不含 `"use"` 也不含 `"server add"`,角色隔离锚点仍成立)。
- `tests/unit/namespace_runtime_smoke_test.py`:`calls` 清单里 `(plugin.servers,"")` → `(plugin.server,"server")`;`(plugin.use,"use alpha")` → `(plugin.server,"server add alpha")`;`(plugin.unbind,"unbind alpha")` → `(plugin.server,"server remove alpha")`;追加 `(plugin.unbind,"unbind")`(玩家解绑,在 bind 之后,复现"绑定后解绑"深分支)。头注释里写死的数字更新为:**astrbot 命令 17 条**(删 servers/use/管理员 unbind 三条、加 server/玩家 unbind 两条 = 18−3+2),但 `calls` 列表 **19 项**(server 出现 3 次:裸/add/remove;unbind 1 次)。注:冒烟仅验证"命名空间加载下不炸"(运行时环境差异),**不**验证 `delete_binding` 正确性——`unbind_self` 删完无条件返回 ok 文案,把 delete 改成 no-op 冒烟仍绿,故 delete 正确性由下方独立测试兜底。
- **`tests/unit/players_group_off_test.py`**:现有仅断言 players 组关闭时 `/pal rank`、`/pal player` 不出现。追加断言:关组时 `unbind_self` 返回 `feature_disabled` 且 `/pal unbind` 不在 help(与 `bind`/`me`/`rank`/`player` 的关组语义对齐;`unbind_self` 属 players 组的隐藏无回归覆盖)。
- `tests/integration/routing_e2e_test.py`:`c.commands.use(UMO,"/pal use alpha",...)` → `c.commands.server(UMO,"/pal server add alpha", is_group=True, is_admin=True)`;断言 `"alpha" in` 保留。
- `tests/unit/readme_test.py`:中文锚点须**分治**,不能一刀切"逐字同步为新命令名":
  - `/pal servers` → 改锚点为 `/pal server`(**注意子串陷阱**:`/pal server` 是 `/pal servers` 的子串,若 docs 半迁移仍残留 `/pal servers`,`"/pal server" in DOCS` 会假绿;迁移后须 grep 确认 docs 无残留 `/pal servers`、`/pal use` 旧串)。
  - `/pal use` → 删锚点或改为 `/pal server add`。
  - `/pal unbind` → **锚点保留不动**(命令名复用,语义变玩家解绑);但 docs 里该行须从 core 组挪到 players 组、参数由 `<名称>` 改为无参。
  - **这是历史 CI 雷点(PR #13),命令改名后 docs 与 readme_test 锚点必须逐字对齐。**

### 需新增的测试

- `delete_binding` 仓储测试(**须用两条隔离,单条测不出漏 `world_id` 条件**):种入两条绑定(同 `platform_hash` 不同 `world_id`)→ delete 目标一条 → 断言目标 `get` 为 `None` **且另一条 `get` 仍命中**。单条 upsert→delete→get None 的测法下,"漏 `AND world_id`" 的错误 SQL 与正确 SQL 效果相同、无法区分(已用 SQLite 突变体脚本证实)。对齐 `unset_hidden`/`test_bind_and_get` 现有的多键隔离测法。
- `unbind_self` 命令测试(**须用真 `Repository` + 真 SQLite fixture,非 `_FakeRepo`**):照 `commands_me_bind_test.py` 的 `apply_migrations` 模式,`bind` → `unbind` → `me`,断言 `me` 显示未绑定。用真 DB 才能让"delete 为 no-op"的变异转红;若用 `_FakeRepo`,production `delete_binding` 变 no-op 时"me 显示未绑定"会误绿。另断言:绑定后 `unbind` 返回 `unbind_self_ok` 且带玩家名;未绑定时返回 `unbind_self_none`。
- `server()` 分流测试:裸=列表;`add`/`remove` 的管理员门、群聊门、空名门;**打错首词(如 `server addd alpha`)→ `server_usage`**;`add @alpha` 的 override 兜底(`arg.name="add"`,override 优先命中 alpha)。

### 需同步的文档与 schema

- **`_conf_schema.json`(优先级最高——实机可见)**:第 35 行 `group_bindings` 的 `description`「预设 群→服务器 授权（可选，等价于管理员 `/pal use`）」→「`/pal server add`」。这不是普通文档:**AstrBot 原生设置页会把该 `description` 直接渲染给管理员**,而自研 Vue 页刻意不含 `group_bindings`(`frontend/src/lib/collect.ts` 注释「绝不含 group_bindings」),故原生 schema 编辑器是该字段唯一露出面。不改会让管理员在设置页看到一条已删除的命令。`conf_schema_test.py` 只断言结构不断言 `description`,故不挂 CI、会静默残留。
- `docs/commands.md`:指令详表(`servers`/`use`/`unbind` 行)、功能开关矩阵(core 组列出的命令名)、多服务器与群授权节。`/pal unbind` 行须从 core 挪到 players 组、参数由 `<名称>` 改无参。
- `docs/configuration.md`:`group_bindings` 注释"等价于管理员 `/pal use`" → `/pal server add`(与上面 `_conf_schema.json` 是孪生措辞,两处都要改)。
- `docs/verification/real-server-checklist.md`:第 235 行验收步「管理员 `/pal use testsv` 后同群可查」→「`/pal server add testsv`」(`use_ok` 文案 key 保留,仅命令名改)。无测试引用,漏改会让验收人执行不存在的命令。
- `README.md`:含 `/pal use`、`/pal servers` 的引用同步(readme_test 从 README + docs 合集断言);另「**18 条指令详表**」计数须按新详表重算——删 3 加 2、行数净减 1 → **17 条**(grep `18 条` 统一核对)。

## 版本

`v0.8.0` → `v0.8.5`(新增命令 + 命令面变更)。需同步:`metadata.yaml`、`main.py` 的 `@register(...)` 版本参数、README 版本徽章,以及 grep `0.8.0` 的其余引用。

## 命名空间加载安全性

本设计不新增任何 import 语句,`server`/`unbind_self` 方法体如需包内模块须走既有顶层相对导入(绝不在函数体内绝对自导入)。历史 `/pal me` 崩溃根因是函数体内绝对自导入,与命令注册机制无关;既有静态防回归扫描 + 命名空间运行时冒烟对新方法同样生效。

## 非目标(YAGNI)

- 不做嵌套命令组。
- 不做旧命令的过渡别名 / 弃用提示。
- 不改 `RoutingService` 底层、不改 DB schema、不做迁移。
- 不改玩家 `bind` / `me` 的行为。
