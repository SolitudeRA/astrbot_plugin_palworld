# 单 / 多服务器模式彻底分道 + 设置页模式感知呈现 设计（v0.9.7）

> 状态：设计已确认，待用户复核 → writing-plans。
> 前置：v0.9.6（PR #21）分级感知权限；v0.9.5 Phase 1（PR #20）引入 `routing.world_mode`（single/multi）模式基础。

## 1. 目标与背景

`world_mode`（single/multi）自 PR #20 起在**配置 / 路由解析 / 运行时守卫 / help 视觉 / 启动告警**五层贯通，但两处未了：

1. **UI 零差异化**——自定义设置页不因模式改变形态：single 下 `default_server` 仍显示、link 无提示、告警只藏在字段 hint。
2. **行为未彻底分道**——single + restricted 把访问控制**架空**并打启动告警（`routing_service.py:113-120`），是坏味道；两模式的授权语义纠缠在同一套 DB 记录里。

本期把两种模式**行为彻底分道**，并让自定义设置页**纯呈现对应模式**：

- **模式切换的唯一入口 = AstrBot 原生齿轮配置**（已安装插件页的齿轮图标渲染 `_conf_schema.json`）。`world_mode` 保持原生字段，做成醒目「主开关」。
- **自定义设置页无模式开关**，读当前 `world_mode` 后纯呈现该模式那一套配置形态，顶部只挂一个只读「当前模式」小标识。
- **单模式做成干净的单服务器体验**：单台服务器表单、访问控制真正生效（不再架空）、授权走设置页配置名单、命令面去掉 link。
- **多模式完全保持现状**，零行为改动。
- **默认值改 `single`**（多数用户只有一台服务器），并加迁移护栏保护存量安装不被静默切换。

架构风格沿用 v0.9.6 的**配置派生谓词**（functional，非策略类），后端新面最小。

## 2. 两模式行为契约

| 维度 | 单模式 single | 多模式 multi（现状不变） |
|---|---|---|
| 服务器数量 | 唯一（运行时取首台就绪 `_ready_servers()[0]`） | 多台，按群绑定 / `@override` / 默认选择 |
| 服务器配置 UI | 单台扁平表单 | 增删列表 |
| `@服务器名` override | 忽略 | 生效（`resolve` Step 1） |
| 群绑定 `group_bindings` / `default_server` | 忽略 | 生效 |
| 读授权（restricted） | 查**配置** `single_allowed_groups`：`umo ∈ 名单 → 放行`；`open → 全放` | 查 **DB allowed 记录**（link 授权），`resolve` 五步 |
| 授权入口 | 设置页配置名单（`single_allowed_groups`）+ `/pal whereami` 取 UMO | `/pal link add/remove`（群内命令，写 DB） |
| `link` 命令组 | 运行时拒 + help 省略 + 命令树隐藏（**彻底不可用**） | 完整可用 |
| 写命令（server 组 7 写） | 受管理员名单硬门（与模式无关，不变） | 同左 |
| single+restricted 告警 | **删除**（restricted 真正生效，不再架空） | N/A |

**私聊**：单模式下私聊 UMO 亦按 `single_allowed_groups` 判定（UMO 在名单才放行），open 下全放。语义统一，不再有 multi 的「私聊 restricted 恒拒」特例。

## 3. 配置模型变化

### 3.1 `world_mode` 默认 multi → single

改动三处默认（**运行时真相在 `parse_config`**，勘探证据：AstrBot 不回填 schema 默认到存量存储）：

- `config.py:67` dataclass 默认 `= "multi"` → `= "single"`。
- `config.py:428` `parse_config` 两处兜底 `_one_of(r.get("world_mode", "multi"), ..., "multi")` → 均改 `"single"`。**⚠️ 铁律：必须先上迁移护栏（§7）、再改此兜底**，否则 rollback 重解析路径（`main.py:284`）会读到 single。
- `_conf_schema.json:31` `"default": "multi"` → `"single"`（只影响新装展示 / 前端表单初值）。
- 镜像默认（宽容兜底，非真相源，为一致性同改）：`commands.py:306`、`formatters.py:158,180`、`frontend/src/lib/schema.ts:36` + 构建产物。

### 3.2 新增 `single_allowed_groups`（顶层 template_list，挂 RoutingConfig）

**schema 约束**：`template_list` 不可嵌进 `routing`（object 节仅容标量项），故实现为**顶层键**（与 `group_bindings` 同范式），语义上归 routing。

- `_conf_schema.json`：新增顶层 `single_allowed_groups`，`type: "template_list"`，`default: []`，`display_item: "umo"`，items `{umo: string, note: string}`（镜像 `permission_admins:143-157`）。描述点明：仅 single + restricted 生效、UMO 可用 `/pal whereami` 获取。
- `config.py`：新增 `@dataclass(slots=True) AllowedGroupEntry(umo: str, note: str)`；新增 `_parse_single_allowed_groups(raw)`（镜像 `_parse_permissions` 的 admin 循环 `:293-303`：读顶层键、行键 `umo`、strip、空 / 重复去重；不套用 admin 专属的 `endswith(":")`）；`RoutingConfig`（`:63-68`）加字段 `single_allowed_groups: list[AllowedGroupEntry] = field(default_factory=list)`，在 `parse_config` routing 构造处（`:425-429`）填入。
- `config_view.py`：四常量各加一项——`_LIST_SECTIONS` 加 `"single_allowed_groups"`、`_ROW_ID_PREFIX` 加 `{"single_allowed_groups": "sag"}`、`_SECTION_KEYS` 加 `{"single_allowed_groups": {"umo", "note"}}`、`_TOP_KEYS` 加 `"single_allowed_groups"`。其余 redact/validate/strip 循环通用，自动覆盖。

## 4. 单模式路由 / 访问（配置派生谓词）

`RoutingService`（`routing_service.py`）single 分支（`:42-57`）改造：

- 保持 short-circuit 到 `_ready_servers()[0]`、忽略 override / 群绑定。
- **restricted 时不再放宽**：新增私有判定，`umo ∈ {e.umo for e in cfg.routing.single_allowed_groups}` 或 `access_mode is OPEN` → 放行；否则返回未授权提示（复用 `L("not_authorized"...)` 或新文案 `single_not_authorized`）。
- 多台就绪告警（`:50-56`）保留（single 下多台仍取首台）。
- **删除** `single_restricted_warning()`（`:113-120`）及其在 `main.py:149-151` 的调用与 `_log_startup_warnings` 相关分支；对应 locale `single_restricted_warning`、测试 `main_link_single_test.py` 的告警用例一并删/改。

`link` 单模式守卫（`main.py:451-452`）**保留**（唯一运行时防线）。help 省略（`formatters.py:166-167`）保留。

多模式 `resolve` 五步（`:59-98`）**零改动**。

## 5. 多模式（保持现状）

多服务器、link 绑定、`group_bindings`、`default_server`、restricted per-server（DB allowed）全部不变。本期不触碰多模式任何行为路径与测试。

## 6. `/pal whereami` 元命令

新增扁平元命令，镜像 `whoami`（`feat_group=core`、`gate=read`、入 `_NON_LOCKABLE`、**非** `@_gated`、经 `_guarded` 注册绕过功能门），差异仅：handler 传 `self._umo(event)`（非 `_sender_id`）、locale 文案。恒可用（含未授权群，正是取 UMO 去申请授权的引导路径）。

**锚定改动点**（勘探清单）：

- `command_registry.py`：`FLAT_ACTIONS`（`:59-66`）加 `"whereami": ("whereami","core","read")`；`_NON_LOCKABLE`（`:94-98`）加 `"whereami"`；`HELP_TEXT`（`:105-134`）加 `"whereami": "查看当前群标识（UMO）"`。（METHOD_PATH / PAL_REGISTERED / PAL_COMMAND_STRINGS / LOCKABLE_COMMANDS 派生自动含。）
- `config.py:150-155` 内联 `_NON_LOCKABLE` 加 `"whereami"`（与 registry 保持集相等）。
- `main.py`：加 `@pal.command("whereami")` handler（`_guarded` + `self._umo(event)`），更新注释「7 扁平 / 12 注册」（`:412-415`）。
- `commands.py`：加 `async def whereami(self, umo: str) -> str`（无 `@_gated`，镜像 `whoami:448-451`），空 UMO 兜底。
- `locale.py`：加 `"whereami"`（含 `{umo}`）+ 可选 `whereami_no_umo`。
- `frontend/src/lib/schema.ts` `PAL_TREE`（`:114-143`）：加 `{"group": null, "path": "whereami", "label": "本群标识", "enableConfigurable": false, "adminConfigurable": false, "adminForced": false, "danger": false}`（JSON 可解析形态）。
- `COMMAND_META`（`command_permissions.py:42-43`）派生自动含，谓词与 whoami 同档，无手工。

`format_help` 自动把 whereami 渲入「其他」段（`formatters.py:188-192`），对所有角色可见（gate=read）。

## 7. 迁移护栏（default single 的存量保护）

**风险**：存量安装（多服务器，或单服务器 + restricted 经 link 授权过群）若从未显式设 `world_mode`，升级后默认翻 single → 只认首台 / link 被拦 / DB 授权群丢读权。

**护栏**（仿 `_migrate_permissions_config:84-113`，`initialize()` 里置于其后、`parse_config` 之前）：

```
def _migrate_world_mode_default(config) -> None:
    routing = config.get("routing")
    if isinstance(routing, Mapping) and "world_mode" in routing:   # 用户已显式选过 → 幂等跳过、不 save
        return
    servers = config.get("servers") or []
    bindings = config.get("group_bindings") or []
    if not servers and not bindings:                               # 真·全新装 → 留给 single 新默认
        return
    # 存量缺键：任何已配置过 servers / group_bindings 的安装 → 冻结历史 multi 语义
    r = dict(routing) if isinstance(routing, Mapping) else {}
    r["world_mode"] = "multi"
    config["routing"] = r
    save = getattr(config, "save_config", None)
    if callable(save): save()
```

**最保守判据**：`servers` 或 `group_bindings` 非空即回写 `multi`（宁可多锁存量）；只有真正无 servers 的全新装享受 single。DB allowed 信号（需 await，晚于 parse）本期不作回写依据——`servers` 非空已覆盖「单服务器 + 授权」存量。护栏把 world_mode 写实后，`parse_config` 兜底不再触发，故兜底改 single 只服务护栏放行的新装。

## 8. 自定义设置页（纯呈现、模式感知、无模式开关）

数据源：`worldMode = computed(() => state.sections.routing?.world_mode ?? 'multi')`（`SettingsPanel.vue:21,57`；GET 响应带 routing.world_mode，无需改 API）。**注意兜底用 `'multi'` 保证旧 mock 不炸，single 分支测试须显式 mock**。

分叉缝（均在 SettingsPanel 层，尽量不动 schema.ts 以免 `schema.test.ts` 字段集断言炸）：

1. **顶部只读小标识**：`SettingsPanel.vue:126` chapter-head 的 h2 旁加 chip「当前模式：单服务器 / 多服务器 · 切换请到插件齿轮配置」（该组件已有 worldMode 值，无需状态上提）。
2. **服务器区**：`SettingsPanel.vue:131-133` 外包 `v-if="worldMode==='multi'"` 增删列表 / `v-else` 单台表单。单台表单复用 `ServerCard`（隐藏移除按钮 + 强制 edit 态），维持 `state.servers` 为**长度 1 数组** → `collectServer` / `body.servers`（`collect.ts:69`）契约不变；single 下 `state.servers` 空时自动 `emptyRow(SERVER_FIELDS)` 占位。
3. **routing 字段可见性**：页面无模式开关 → 恒隐藏 routing 表单里的 `world_mode` 字段；single 再隐藏 `default_server`。走 **SettingsPanel 层 section clone + `fields.filter(...)`**（不改 schema.ts）传给 SectionForm。
4. **命令树去 link**：`CommandTree.vue` 加 `hideGroups` prop，`:22` 循环 `if (hideGroups.includes(n.group ?? '')) continue`；SettingsPanel 调用点（`:160-161`）single 传 `['link']`。已存的 link command_permissions 行 hydrate 后原样回吐（不静默清空）。
5. **授权群名单区**（新建，镜像 `permission_admins`/AdminCard）：single + restricted 下呈现。新组件 `GroupCard.vue`（clone `AdminCard.vue`，`id`→`umo`）；`collect.ts` 加 `collectGroup`（`{__row_id, umo, note}`）+ `body.single_allowed_groups`；`SettingsPanel.vue` 加 state 初始化 / applyConfig hydrate（`:59` 镜像）/ `emptyGroup()`；区块归**连接章**（`isAccess:128`，与访问控制同章，符合 routing 语义）。

> 澄清：`single_allowed_groups` 是**全新顶层字段**，与前端零 UI 的 `group_bindings` 无关，**不触碰 group_bindings 采集契约**（`collect.ts:87` 保持不发 group_bindings）。

## 9. 原生齿轮侧优化

`_conf_schema.json` `world_mode` 描述重写成「主开关」：讲清 single=单服务器（一台机、群授权走插件设置页名单 + `/pal whereami`）、multi=多服务器（多台、`/pal link` 绑定切换），并指引「切到某模式后，请到插件设置页配置该模式」。移除旧描述里的 single+restricted 架空警告（该行为已消失）。

## 10. 锚定 & 测试

**新增**：single restricted 名单授权（放行 / 拒绝 / open 全放 / 私聊）、迁移护栏四态（存量 servers→multi+saved / 全新装→不动+single / 已显式→幂等 / 端到端 initialize）、whereami 单测、前端 single 分支渲染（单台表单 / link 隐藏 / default_server 隐藏 / 授权群名单出现）、CommandTree hideGroups、GroupCard、schema `single_allowed_groups` 存在性、config/config_view 往返。

**必改**（断言旧默认 / 旧告警）：`config_world_mode_test.py:10-27`（默认 → single）、`main_link_single_test.py` 告警用例（删/改）、注册数 `11→12`（`command_registry_hierarchy_test.py:24`、`command_names_test.py:33`）、`_NON_LOCKABLE` 三处 literal 加 whereami（`command_names_test.py:21`、`config_server_admin_test.py:35`）、HELP_TEXT 双等 / 前端跨端锚定（加 whereami 节点）、`collect.test.ts` TOP_KEYS 加 `single_allowed_groups`、`namespace_runtime_smoke_test.py` calls 加 whereami。

**文档同步**（readme 中文锚点铁律）：`README.md`、`docs/commands.md`（whereami + 模式差异）、`docs/configuration.md`（默认 single + single_allowed_groups + 迁移说明），并核 `readme_test.py:93,109-113,125` 锚点短语（"multi"/"single"/"单世界"/"多世界"/"whoami" 相关）。

**产物**：`npm run build`（内置 normalize-eol，避免 Windows CRLF 幻影脏）刷新 `pages/settings/`，no-drift 校验。

## 11. 版本

v0.9.7，四源同步：`metadata.yaml`、`main.py` `@register`、`palworld_terminal/__init__.py` `__version__`、`README.md` badge；核对版本断言测试。

## 12. 范围外 / 风险

- 不改多模式任何行为。不改 DB schema（single 授权走配置，不建新表）。
- 不做「多台已存在时切 single 的降级引导」——护栏只保证不静默翻转；用户显式选 single 后自负其责（首台生效 + 多台告警已在）。
- 单模式单台表单编辑 `servers[0]`；用户在多模式配过多台后切 single，表单只呈现 / 编辑首台，其余保留在配置中但不生效（不静默删除）。
- `worldMode` 前端兜底 `'multi'`：新装 schema 默认 single，但若 GET 响应 routing 缺 world_mode（极端旧 raw），前端会呈现 multi 形态——与后端护栏「存量→multi」方向一致，无矛盾。
