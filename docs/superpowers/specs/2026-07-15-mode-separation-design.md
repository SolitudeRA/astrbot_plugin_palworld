# 单 / 多服务器模式彻底分道 + 设置页模式感知呈现 设计（v0.9.7）

> 状态：设计定稿（已过三视角对抗复核 + 决策收口），待 writing-plans。
> 前置：v0.9.6（PR #21）分级感知权限；v0.9.5（PR #20）引入 `routing.world_mode` 模式基础。
> **前提**：截至本设计，插件**尚无真实用户**，故**不做任何配置迁移 / 向后兼容**（见 memory `no-existing-users-no-migration`）。默认值/结构直接改。

## 1. 目标

把 `world_mode`（single/multi）**行为彻底分道**，并让自定义设置页**纯呈现对应模式**：

- **模式切换唯一入口 = AstrBot 原生齿轮配置**（`world_mode` 为 `_conf_schema.json` 原生字段，做成醒目「主开关」）。自定义设置页**无模式开关**，读当前模式后纯呈现该模式那套配置形态 + 顶部只读「当前模式」小标识。
- **单模式**：一台服务器、单台扁平表单；restricted **真正生效**（不再架空），读授权改查新配置字段 `single_allowed_groups`（群 UMO 名单，不依赖 link/DB）；link 组彻底不可用；`group_bindings`/`default_server` 忽略。
- **写命令（server 组 7 写）不受读名单约束**：管理员硬门（`permission_admins`）已独立把守，单模式只一台服务器、读名单只管读。管理员可从任意群管理。
- **多模式**：完全保持现状，零行为改动。
- **默认值改 `single`**（多数用户单台服务器）。因无存量用户，直接改三处默认、无迁移护栏。
- 新增元命令 `/pal whereami` 回显当前群 UMO，供管理员填授权名单。

风格沿用 v0.9.6 的**配置派生谓词**（functional，非策略类）。

## 2. 两模式行为契约

| 维度 | 单模式 single | 多模式 multi（现状不变） |
|---|---|---|
| 服务器数量 | 唯一（`_ready_servers()[0]`） | 多台，按绑定/override/默认选择 |
| 服务器配置 UI | 单台扁平表单（编辑 `servers[0]`） | 增删列表 |
| `@服务器名` / 群绑定 / `default_server` | 忽略 | 生效 |
| **读授权**（restricted） | 查**配置** `single_allowed_groups`：`umo ∈ 名单` 或 `open` → 放行 | 查 **DB allowed**（link 授权），resolve 五步 |
| 授权入口 | 设置页 `single_allowed_groups` 名单 + `/pal whereami` 取 UMO | `/pal link add/remove`（群内命令写 DB） |
| **写命令**（server 7 写） | **不受读名单约束**；仅 `permission_admins` 硬门（与模式无关，不变） | 同左（另经 resolve 的 DB 授权定位服务器，现状不变） |
| `link` 命令组 | 运行时拒 + help 省略 + 命令树隐藏 | 完整可用 |
| single+restricted「架空」告警 | 删除；改为「空名单」运维告警（§4.3） | N/A |

**私聊**：单模式私聊 UMO 亦按 `single_allowed_groups` 判定（在名单才放，open 全放）。

## 3. 配置模型

### 3.1 `world_mode` 默认 multi → single（直接改，无迁移）

三处默认同步改（运行时真相在 `parse_config`；AstrBot 会递归回填 schema 默认到已存配置并落盘——无用户故无害，回填只会写 single，正是所需）：

- `config.py:67` dataclass `world_mode: str = "multi"` → `"single"`。
- `config.py:428` `parse_config` 两处兜底 `_one_of(r.get("world_mode","multi"),…,"multi")` → 均 `"single"`。
- `_conf_schema.json:31` `"default":"multi"` → `"single"`；**description 重写成「主开关」**（讲清 single/multi 差异 + 指引「切模式后到插件设置页配置」）+ **删除旧「single+restricted 访问控制不生效」表述**（该行为已消失）。
- `frontend/src/lib/schema.ts:36` `default:'multi'` → `'single'`，且 **hint 删除「⚠️ single + restricted 并存时访问控制不生效」**（已成假陈述）；构建产物随 rebuild 刷新。
- 宽容兜底 `commands.py:306`、`formatters.py:158,180` 的 `world_mode="multi"`（测试替身用，非真相源）：**不改**。

### 3.2 新增 `single_allowed_groups`（顶层 template_list，挂 RoutingConfig）

**硬约束**：`template_list` 不可嵌 `routing`（object 节仅容标量，且 AstrBot 对非 object 类型不做子项合并——见 PR #21 教训）。故 schema 里必为**顶层键**（与 `group_bindings` 同范式），解析后挂 `RoutingConfig`。

- `_conf_schema.json`：新增顶层 `single_allowed_groups`，`type:"template_list"`、`default:[]`、`display_item:"umo"`、items `{umo:string, note:string}`（镜像 `permission_admins:143-157`）。description 点明：**仅 single+restricted 生效**、UMO 可用 `/pal whereami` 获取、**note/umo 明文落盘勿填 PII**（镜像 permission_admins 安全告知）。接受「原生齿轮页对 multi 用户也恒显此名单」（同 group_bindings 先例，无害）。
- `config.py`：新增 `@dataclass(slots=True) AllowedGroupEntry(umo:str, note:str)`；新增 `_parse_single_allowed_groups(raw)`（镜像 `_parse_permissions` admin 环 `:293-303`：读顶层键、行键 `umo`、strip、去空去重；**不套 admin 专属 `endswith(":")`**）；`RoutingConfig`（`:63-68`）加 `single_allowed_groups: list[AllowedGroupEntry] = field(default_factory=list)`，`parse_config` routing 构造处（`:425-429`）填入。
- `config_view.py` 四常量各加 `single_allowed_groups`（**必须全加，尤其 `_TOP_KEYS`，否则含该键的保存被 `validate_and_backfill` 判 invalid_shape 拒绝**）：`_LIST_SECTIONS`（`:17`）、`_ROW_ID_PREFIX`（`:19`，前缀 `"sag"`）、`_SECTION_KEYS`（`:31`，`{"umo","note"}`）、`_TOP_KEYS`（`:40`）。redact/validate/strip 泛化环自动覆盖，无 secret/sentinel 特殊逻辑（对照 permission_admins 确认）。

## 4. 单模式路由 / 访问（配置派生谓词）

### 4.1 读授权：restricted 真正生效

`RoutingService.resolve`（`routing_service.py:42-57`）single 分支改造，**顺序钉死**（防 fail-open）：

```
if world_mode == "single":
    ready = _ready_servers()
    if not ready: return Resolution(None, L("no_server_configured"))
    srv = ready[0]
    if access_mode is RESTRICTED and not for_write:          # ← 先判、early-return
        allowed = {e.umo for e in cfg.routing.single_allowed_groups}
        if umo not in allowed:
            return Resolution(None, L("single_not_authorized"))
    if len(ready) > 1 and not self._single_multi_warned:      # 多台告警（保留）
        ...warn...
    return Resolution(srv, None)
```

- `@override`/群绑定/`default_server` 单模式仍忽略。私聊同群判定（umo ∈ 名单）。
- **空名单 fail-closed**：`umo ∈ {}` 恒 False 且非 OPEN → 全拒读（安全方向）。

### 4.2 写命令绕过读名单（决策：写与模式无关）

- `RoutingService.resolve` 新增形参 `for_write: bool = False`；**仅 single 分支消费**（multi 分支忽略，行为不变）。`for_write=True` 时跳过 §4.1 的名单判定，直接返回 `ready[0]`。
- 写路径两处 resolve 调用传 `for_write=True`：`admin_service.py:69`（`_execute`）、`:219`（`_target_write`）。这两处覆盖全部 7 写（announce/save/shutdown/stop/unban/execute_target 走 `_execute`；kick/ban 走 `_target_write`）。
- 写命令仍受 `commands.admin_write` 的 `permission_admins` 硬门（门序不变，独立于 resolve）。读命令（`_resolve_world` 等）用 `for_write` 默认 False，受名单约束。

### 4.3 删架空告警 + 补空名单运维告警

- **删除** `single_restricted_warning()`（`routing_service.py:113-120`）及 `main.py:149-151` 调用、locale `single_restricted_warning` 键、`main_link_single_test.py` 相关断言。
- **新增**运维启动告警（补上被删告警的可见性、非迁移）：`_log_startup_warnings` 中，若 `world_mode=="single" and access_mode is RESTRICTED and not single_allowed_groups` → warn「单模式受限但授权群名单为空 = 当前全群不可读，请用 /pal whereami 取 UMO 后在设置页『连接』章配置」。

### 4.4 拒绝文案专用（不复用 not_authorized）

- **必须**新增 locale `single_not_authorized`，文案指向 `/pal whereami` + 设置页名单。**不得**复用 `not_authorized`（其硬编码 `/pal link add`，单模式已禁用；且 `locale_rework_test.py:16` 钉死其含 `/pal link add`）；**不得**含 `/pal use`（`locale_rework_test.py:12-13` 红线）。

`link` 单模式守卫（`main.py:451-452`）保留。多模式 resolve 五步（`:59-98`）零改动。

## 5. 多模式（保持现状）

多服务器、link 绑定、`group_bindings`、`default_server`、restricted per-server（DB allowed）全不变。本期不触碰多模式任何行为路径与测试。

## 6. `/pal whereami` 元命令（镜像 whoami）

扁平元命令，镜像 `whoami`（`feat_group=core`、`gate=read`、入 `_NON_LOCKABLE`、**非 `@_gated`**、经 `_guarded` 注册绕过功能门），差异仅 handler 传 `self._umo(event)`、locale 文案。恒可用（含未授权群——正是取 UMO 去申请授权的引导路径），两模式都出。

**不变量**：只回显 `event` 自身 UMO，**不接受任何目标参数**（防日后被加 `@群` 参数变成他群探测器）——固化到单测。

**锚定改动点**：

- `command_registry.py`：`FLAT_ACTIONS`（`:59`）加 `"whereami":("whereami","core","read")`；`_NON_LOCKABLE`（`:94`）加 `"whereami"`；`HELP_TEXT`（`:105`）加 `"whereami":"查看当前群标识（UMO）"`。（METHOD_PATH/PAL_REGISTERED/PAL_COMMAND_STRINGS/LOCKABLE 派生自动。）
- `config.py:150-155` 内联 `_NON_LOCKABLE` 加 `"whereami"`。
- `main.py`：加 `@pal.command("whereami")` handler（`_guarded` + `self._umo(event)`），更新 `:412` 注释 11→12。
- `commands.py`：加 `async def whereami(self, umo:str)->str`（无 `@_gated`，镜像 `whoami:448`），空 UMO 兜底。
- `locale.py`：加 `"whereami"`（含 `{umo}`）+ `whereami_no_umo` 兜底。
- `frontend/src/lib/schema.ts` `PAL_TREE`（`:114`）加 `{"group":null,"path":"whereami","label":"本群标识","enableConfigurable":false,"adminConfigurable":false,"adminForced":false,"danger":false}`。
- `COMMAND_META` 派生自动含（谓词同 whoami）。`format_help` 自动渲入「其他」段，对所有角色可见。

## 7. 自定义设置页（纯呈现、模式感知、无模式开关）

`worldMode = computed(() => state.sections.routing?.world_mode ?? 'multi')`（`SettingsPanel.vue:21,57`；GET 带 routing.world_mode，无需改 API）。

1. **只读模式标识**：`SettingsPanel.vue:126` chapter-head 的 h2 旁加只读 chip「当前模式：单服务器/多服务器 · 切换请到插件齿轮配置」（此处已有 worldMode，无需状态上提）。
2. **服务器区**：`SettingsPanel.vue:131-133` 增删列表外包 `v-if="worldMode==='multi'"`；`v-else` 渲染**单台扁平表单**——复用 `ServerCard`（隐藏移除按钮 + 强制 edit 态），**只渲染/编辑 `state.servers[0]`，绝不截断 `state.servers`**（多台并存时其余保留、随 SENTINEL 由后端 backfill 完好，不静默删除）；`servers` 空时 `emptyRow(SERVER_FIELDS)` 占位。`collect.ts:69 body.servers` 契约不变。
3. **routing 字段可见性 —— 红线**：`world_mode` **必须**保留在 `schema.ts` OBJECT_SECTIONS.routing.fields（`collectBody` 遍历它才能原样回传 world_mode；否则整对象 merge 会丢 world_mode → parse 回落 single → multi 用户一保存即翻 single）。隐藏**只允许**在 SettingsPanel 展示层传**过滤后的 section clone**（`fields.filter` 掉 world_mode；single 再滤 default_server），**严禁改 schema.ts 删字段**。补前端测试断言 `collectBody().routing` 恒含 `world_mode`。
4. **命令树去 link**：`CommandTree.vue` 加 `hideGroups` prop，`:22` 循环 `if (hideGroups.includes(n.group ?? '')) continue`；调用点（`:160`）single 传 `['link']`。已存 link command_permissions 行 hydrate 后原样回吐（不静默清空）。
5. **授权群名单区**（新建，镜像 permission_admins/AdminCard）：single+restricted 下呈现于**连接章**（`isAccess:128`）。新组件 `GroupCard.vue`（clone `AdminCard.vue`，`id`→`umo`，placeholder 示例改 UMO 形态）；`collect.ts` 加 `collectGroup`→`{__row_id,umo,note}` + `body.single_allowed_groups`；`SettingsPanel.vue` 加 state 初始化 / **无条件 hydrate**（所有模式，`applyConfig:59` 镜像——否则 single→multi→保存会把名单抹成 `[]`）/ `emptyGroup()`。
6. **world_mode 兜底 seed**（防拒存）：`applyConfig` hydrate 时把 `state.sections.routing.world_mode` 用 `worldMode`（兜底 `'multi'`）seed 成合法枚举，避免空值 coerce 成 `''` 撞 `config_view._ENUMS` 校验致整体保存被拒。

> `single_allowed_groups` 是**全新顶层字段**，与前端零 UI 的 `group_bindings` 无关，**不触碰 group_bindings 采集契约**。

## 8. 锚定 & 测试

**新增**：single+restricted 名单授权（命中放行/未命中拒/**空名单全拒**/open 全放/私聊按名单）；**单模式写命令绕过名单**（未列名群里管理员写命令仍放行、非管理员仍拒）；whereami 单测（回显 UMO/空兜底/**无目标参数不变量**）；空名单运维告警；前端 single 分支渲染（单台表单不截断/link 隐藏/default_server 隐藏/授权群名单出现）；CommandTree hideGroups；`collectBody().routing` 恒含 world_mode；GroupCard；schema single_allowed_groups 存在 + **顶层非嵌 routing** 断言（镜像 `conf_schema_test.py:31-33` group_bindings 范式）；config/config_view 往返（`sag-0` row_id + strip_meta）；multi 保存不丢 single_allowed_groups 名单。

**必改**：
- `config_world_mode_test.py:10,18,22-27`：默认/非法兜底/schema 默认 → single。
- **`routing_world_mode_test.py`（主测，勿漏）**：`:69-76` 私聊放宽用例反转为「umo 不在名单→拒」；`:79/:87/:104` 三用例 `_cfg` 默认 RESTRICTED 需喂名单或改 OPEN；`:117-133` 三 `single_restricted_warning` 用例整段删；`_cfg`（`:32`）增 `single_allowed_groups` 形参。
- `main_link_single_test.py`：删架空告警断言；显式 `world_mode="multi"` 传参用例复核不回归。
- 注册数 `11→12`（`command_registry_hierarchy_test.py:24`、`command_names_test.py:33`）；`_NON_LOCKABLE` 三处 literal 加 whereami（`command_names_test.py:21`、`config_server_admin_test.py:35`）；HELP_TEXT 双等 + 前端跨端锚定加 whereami 节点；`namespace_runtime_smoke_test.py` calls 加 whereami；`collect.test.ts:35` TOP_KEYS 加 `single_allowed_groups`。
- 版本断言：`phase1_smoke_test.py:19` `"0.9.6"→"0.9.7"`（`main_test.py:75` 动态读 metadata 自动过）。
- 核 locale 完整性测试不因删 `single_restricted_warning` 键翻红。

**文档**（readme 中文锚点铁律）：`README.md`、`docs/commands.md`（whereami + 模式差异）、`docs/configuration.md`（默认 single + single_allowed_groups + 无迁移说明）；核 `readme_test.py:93,109-113,125` 锚点短语。

**产物**：`npm run build`（内置 normalize-eol）刷新 `pages/settings/**`，no-drift + LF。

## 9. 版本

v0.9.7 四源：`metadata.yaml`、`main.py @register`、`palworld_terminal/__init__.py __version__`、`README` badge；改 `phase1_smoke_test.py:19`。

## 10. 范围外 / 风险

- **无迁移 / 无向后兼容**（无用户）。不改 DB schema（single 授权走配置）。
- 不改多模式任何行为。不动 `group_bindings` 及其前端契约。不引入路由策略类。
- 单模式单台表单编辑 `servers[0]`；多模式配过多台后切 single，表单只呈现首台，其余保留在配置中不生效（不删除）。
- fresh 装机默认 single + access_mode 默认 restricted + 空名单 = 初始全群不可读；由 §4.3 运维告警 + §4.4 清晰拒绝文案（指向 whereami）引导管理员完成 bootstrap。
