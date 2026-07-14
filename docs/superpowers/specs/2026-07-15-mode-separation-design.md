# 单/多服务器模式彻底分道 + 设置页模式感知呈现（v0.9.7）

> 状态：设计定稿，待三视角对抗复核。承接 v0.9.6（Phase 2 分级感知权限）。

## 0. 目标与背景

`world_mode`（single/multi）自 v0.9.5（PR #20）引入后，只在**配置解析 / 路由解析 / 运行时守卫 / help 视觉省略 / 启动告警**五层贯通，但：

- **UI 零差异化**：自定义设置页把 `world_mode` 当普通 enum 字段渲染，选 single 不隐藏任何多服务器配置；`default_server` 仍显示、link 无提示、告警只藏在字段 hint 里。
- **single + restricted「架空」**：单模式 resolve 短路时不跑授权判定，restricted 访问控制被架空，只打一条启动 warning——这是个待消除的坏味道。
- **两模式在共享方法里交缠**，「单服务器」体验并不干净。

本期把两种模式**行为彻底分道**并让设置页**模式感知呈现**：

- **模式主开关下沉到 AstrBot 原生齿轮配置**（`world_mode` 保持 `_conf_schema.json` 原生字段），自定义设置页**不含模式开关**，纯粹按当前模式渲染对应形态。
- **单模式**：一台服务器；`restricted` 时**真正生效**，改查一份新的**配置授权群名单** `single_allowed_groups`（不再依赖 link/DB 绑定，不再架空）；link 组彻底移除；`group_bindings`/`default_server` 忽略；写命令仍受管理员名单硬门。
- **多模式**：**完全保持现状**（多服务器、link 绑定、group_bindings、default_server、restricted per-server DB 授权）。
- 默认从 `multi` 改成 `single`，配一道**最保守迁移护栏**保护存量安装不被静默切换。
- 新增元命令 `/pal whereami` 回显当前群 UMO，供管理员填授权群名单。

**设计原则**：沿用 Phase 2 的**配置派生谓词**风格；单模式授权走**配置名单**而非 DB（两模式授权机制真正分家）；锚定闭环防漂移；先护栏后改默认（铁律时序）。

---

## 1. 模式主开关（AstrBot 原生齿轮）

- `routing.world_mode`（enum `single|multi`）保持 `_conf_schema.json` 原生字段，**默认改 `single`**。
- 描述重写成「主开关」措辞，讲清两模式差异并指引「切模式后请到插件设置页配置对应模式」。
- 原生齿轮是**唯一**切模式入口；自定义设置页**不提供**模式切换（见 §5）。

---

## 2. 配置模型

### 2.1 `world_mode` 默认翻转（两层真相 + 镜像）

运行时真相是 `config.py` 的 **`parse_config` 兜底**，非 schema 默认（AstrBot 不回填新键默认值——见 §6 证据）。需同步改：

| 层 | 位置 | 改动 |
|---|---|---|
| **运行时真相** | `config.py:428` `world_mode=_one_of(r.get("world_mode","multi"),…,"multi")` | 两处 `"multi"`→`"single"`（键缺失兜底 + 非法值兜底）**（务必先上 §6 护栏）** |
| dataclass 默认 | `config.py:67` `world_mode: str = "multi"` | → `"single"` |
| AstrBot/前端默认 | `_conf_schema.json:31` `"default":"multi"` | → `"single"`（只影响新装展示） |
| 前端 schema | `frontend/src/lib/schema.ts:36` `default:'multi'` + 构建产物 `pages/settings/assets/index.js` | → `'single'`（需 rebuild） |
| 宽容默认（保留 multi） | `commands.py:306`、`formatters.py:158,180` 的 `world_mode="multi"` 测试替身兜底 | **不改**（非真相源，仅兼容不完整测试替身） |

### 2.2 新增 `single_allowed_groups`（单模式授权群名单）

**硬约束**：AstrBot `template_list` **不能嵌进 `routing`（object 节仅容标量项）**，故 schema 里必为**顶层键**（与 `group_bindings` 同列），但解析后挂到 `RoutingConfig.single_allowed_groups`，语义仍属 routing。

- **`_conf_schema.json`**：仿 `permission_admins`（`:143-157`）新增顶层 `single_allowed_groups`：`type:"template_list"`、`default:[]`、`display_item:"umo"`、items `umo`（string）+ `note`（string）。
- **`config.py`**：新增 `@dataclass(slots=True) AllowedGroupEntry(umo: str, note: str)`；`RoutingConfig`（`:63-68`）加 `single_allowed_groups: list[AllowedGroupEntry] = field(default_factory=list)`；新增 `_parse_single_allowed_groups(raw)`（仿 `_parse_permissions` admin 环 `:293-303`：读 `raw.get("single_allowed_groups")`，行键 `umo`，去空、去重；**不套 admin-id 专属的 `endswith(":")` 校验**）；在 `parse_config` routing 构造处（`:425-429`）接线。
- 语义：仅 `world_mode=="single"` 且 `access_mode==RESTRICTED` 时消费（§3.1）。`open` 或 multi 下该名单**不生效**（惰性字段）。

### 2.3 授权机制分家（不碰 group_bindings）

- **单模式授权 = 配置 `single_allowed_groups`**（本期新增，纯配置，无 DB）。
- **多模式授权 = link/DB `group_servers` allowed 记录**（现状零改动）。
- `single_allowed_groups` 是**全新独立字段**，**不复用、不改动** `group_bindings` 及其前端「故意不发」的既有契约。

---

## 3. 单模式行为（配置派生谓词）

### 3.1 RoutingService.resolve — restricted 真正生效

`routing_service.py:42-57` 单分支现状：短路到首台就绪服务器，**不跑 `_authorized`**（架空 restricted）。改为：

```
if world_mode == "single":
    ready = _ready_servers()
    if not ready: return Resolution(None, L("no_server_configured"))
    if len(ready) > 1: 一次性 warning（保留现有 _single_multi_warned 机制）
    srv = ready[0]
    if access_mode == RESTRICTED:
        if umo not in {e.umo for e in cfg.routing.single_allowed_groups}:
            return Resolution(None, L("single_not_authorized"))   # 新文案
    # OPEN：直接放行
    return Resolution(srv, None)
```

- 授权判定**统一**作用于读与「写命令的路由步」（与多模式一致：群先被授权，写再过管理员硬门）。私聊 UMO 同理——在名单则放、否则拒（uniform membership，无多模式的「私聊 restricted 一律拒」特例）。
- `@override`、群绑定、`default_server` 单模式**仍忽略**（本就忽略）。

### 3.2 删除 single_restricted「架空」告警

- 删 `routing_service.py:113-120` `single_restricted_warning()` 及 `main.py:149-151` 其调用点、`locale.py` 的 `single_restricted_warning` 文案、`tests/unit/main_link_single_test.py` 相关断言。restricted 现已真正生效，告警无存在意义。

### 3.3 link 组移除 + 写命令门不变

- link 组运行时守卫保留强化（`main.py:448-455` `_link_dispatch` 单模式拒）+ help 省略（`formatters.py:166-167` 现状）。
- 写命令仍受 `commands.admin_write` 管理员名单硬门（`permission_admins`），与本期无关、不变。

---

## 4. 多模式行为

**完全保持现状，零行为改动**：多服务器、link 绑定、`group_bindings`、`default_server`、restricted per-server（DB allowed 记录）。仅设置页呈现层新增「按 world_mode 分叉」（§5），不改多模式契约。

---

## 5. 自定义设置页（纯呈现、模式感知、无模式开关）

数据流：读 `state.sections.routing.world_mode` 派生 `worldMode` computed（`SettingsPanel.vue:21,57`），驱动分叉。**页面不含模式切换控件**。

### 5.1 只读模式标识

- `SettingsPanel.vue:126` chapter-head 的 `<h2>` 旁加只读 chip：「当前模式：单服务器 / 多服务器」+ 提示「切换模式请到插件齿轮配置」。（此处已能读到 `worldMode`，无需把 config 上提到 App.vue。）

### 5.2 单模式呈现

- **服务器**：`SettingsPanel.vue:131-133` 增删列表外包 `v-if="worldMode==='multi'"`；`v-else` 渲染**单台扁平表单**——复用 `ServerCard.vue`（隐藏「移除」按钮、强制 edit 态），维护 `state.servers` 为**长度 1 数组**（空则 `emptyRow(SERVER_FIELDS)` 占位），使 `collect.ts:69 body.servers` 契约**零改动**。
- **routing 字段可见性**：因页面无模式开关，需**隐藏 routing 节里的 `world_mode` 字段**；single 还要隐藏 `default_server`。缝：在 SettingsPanel 层给 SectionForm 传**过滤后的 section clone**（`fields.filter(...)`），**不动 `schema.ts`**（避免 `schema.test.ts` 字段集断言炸）。
- **授权群名单**：single + restricted 下新增区块，新组件 `GroupCard.vue`（克隆 `AdminCard.vue`，`id`→`umo`），采集/hydrate 见 §5.4。`open` 下该区块隐藏（不生效）。
- **命令树**：`CommandTree.vue` 加 `hideGroups` prop，single 传 `['link']`，在 `:22` 循环过滤 `PAL_TREE`。已存的 link command_permissions 行仍原样 hydrate/回吐（不静默清空）。
- 采集/世界/隐私/权限其余照常。

### 5.3 多模式呈现

- 服务器增删列表 + `default_server` + link/群绑定概念 + `access_mode`；**完整命令树（含 link，`hideGroups` 缺省不隐藏）**。与现状一致。

### 5.4 `single_allowed_groups` 前端接线（仿 `permission_admins`）

- 新组件 `GroupCard.vue`（克隆 `AdminCard.vue`，`id`→`umo`，placeholder 示例改 UMO 形态如 `aiocqhttp:GroupMessage:123456`）。
- `collect.ts`：`SettingsState` 加 `single_allowed_groups`；新增 `collectGroup`→`{__row_id,umo,note}`；`collectBody` 加 `body.single_allowed_groups = (state.single_allowed_groups ?? []).map(collectGroup)`。
- `SettingsPanel.vue`：import 新卡片；state 初始化 `single_allowed_groups:[]`；`applyConfig` hydrate（仿 `:59` permission_admins）；`emptyGroup()`；克隆受托名单 `<section>`（`:150-156`）——放**连接章**（`isAccess`，routing 语义），single + restricted 下显示。

### 5.5 后端 config_view 往返闭合

- `config_view.py` 四常量加 `single_allowed_groups`：`_LIST_SECTIONS`（`:17`）、`_ROW_ID_PREFIX`（`:19`，前缀 `"sag"`）、`_SECTION_KEYS`（`:31`，`{"umo","note"}`）、`_TOP_KEYS`（`:40`）。redact/validate/strip 泛化环自动覆盖，无 secret 字段（同 permission_admins）。

---

## 6. 迁移护栏（default single 的存量保护）

**证据**：AstrBot **不**把新增 schema 键默认值回填进存量存储（`hierarchical-permissions-design.md:192-196` 明述 + `_migrate_permissions_config` 存在即反证 + `world_mode` 仅 v0.9.5 才入 schema）。故存量缺键用户走 `parse_config` 兜底，改兜底即静默影响存量。

**破坏面**：存量**多服务器**用户翻 single → 只认首台、忽略群绑定/override、restricted 架空；存量**单服务器 + restricted** 用户翻 single → 授权改读空的 `single_allowed_groups`、不认 DB → 已授权群**丢读权**。

**护栏（仿 `_migrate_permissions_config`，`main.py:84-113`）**：新增 `_migrate_world_mode_default(config)`，`initialize()` 里置于 `_migrate_permissions_config` 之后、`parse_config` 之前（`main.py:135-136` 之间）。**同步判据（信号 A，raw 层，无需 DB/await）**：

```
routing = config.get("routing") or {}
if "world_mode" in routing:                 # 用户已显式选过 → 幂等跳过、不 save
    return
servers = config.get("servers") or []
group_bindings = config.get("group_bindings") or []
if not servers and not group_bindings:      # 真·全新装 → 留给 single 新默认、不动、不 save
    return
routing["world_mode"] = "multi"             # 任何已配置痕迹的存量 → 冻结历史 multi 语义
config["routing"] = routing
config.save_config()                        # 落盘（AstrBotConfig.save_config）
```

- **最保守**：`servers` 非空（**或** `group_bindings` 非空）的任何安装一律回写 `multi`；只有真·全新装（无 servers、无 bindings）享 single。宁可多锁存量，保多服务器 + 单服务器带授权两类存量都不被打断。
- **铁律：先上护栏、后改 `parse_config` 兜底**——否则 rollback 重解析路径（`main.py:284`）读到 single。护栏把存量 world_mode 显式写死后，`parse_config` 兜底只服务护栏放行的新装。

---

## 7. 新增元命令 `/pal whereami`（镜像 `whoami`）

**语义**：扁平元命令（`group=null`、`feat_group="core"`、`gate="read"`、在 `_NON_LOCKABLE`、**非 `@_gated`**、经 `_guarded` 注册绕过功能门），回显当前群 UMO，供管理员复制进 `single_allowed_groups`。恒可用（不受读授权门管、不可锁），两模式都出。

**锚定点（每处派生的免手改，手改集中在三对真相源）**：

- `command_registry.py`：`FLAT_ACTIONS`（`:59`）加 `"whereami": ("whereami","core","read")`；`_NON_LOCKABLE`（`:94`）加 `"whereami"`；`HELP_TEXT`（`:105`）加 `"whereami": "查看当前群标识（UMO）"`。（`METHOD_PATH`/`PAL_REGISTERED`/`PAL_COMMAND_STRINGS`/`LOCKABLE` 派生自动。）
- `main.py`：加 `@pal.command("whereami")` handler，经 `_guarded`（**非** `_guarded_cmd`）调 `c.commands.whereami(self._umo(event))`（`_umo` at `:379`）；更新 `:412` handler 计数注释 11→12。
- `commands.py`：加 `async def whereami(self, umo: str) -> str`（**无 `@_gated`**，仿 `whoami` `:448`），空 UMO 兜底后 `return L("whereami", umo=umo)`。
- `locale.py`：加 `"whereami"`（+ 可选 `whereami_no_umo` 兜底）。
- `config.py`：内联 `_NON_LOCKABLE`（`:150-155`）加 `"whereami"`（与 registry 集全等）。
- `formatters.py`：**无需改**（扁平命令自动进「其他」段，`gate=="read"` 对所有人可见）。
- `command_permissions.py`：`COMMAND_META` 派生自动含（enable/admin/danger 谓词全 False，同 whoami）。
- `schema.ts`：`PAL_TREE`（`:114`）加 `{"group":null,"path":"whereami","label":"本群标识",...}` 四标志全 `false`（保 JSON 可解析）。

---

## 8. 锚定闭环 & 测试

### 8.1 whereami 锚定测试（must update）

- `command_registry_hierarchy_test.py:24`、`command_names_test.py:33`：注册数 `11`→`12`。
- `command_names_test.py:17-22` `_NON_LOCKABLE_PATHS` 字面量加 `"whereami"`；`config_server_admin_test.py:31-36` non_lockable frozenset 加 `"whereami"`。
- `formatters_hierarchy_test.py:95-98` `set(HELP_TEXT)==set(PAL_COMMAND_STRINGS)` 双向全等：需 `FLAT_ACTIONS`+`HELP_TEXT` 都加 whereami。
- `frontend_pal_commands_test.py:25-34` `{PAL_TREE.path}==set(COMMAND_META)` + 逐节标志：需 `schema.ts` PAL_TREE 节。
- `namespace_runtime_smoke_test.py:142-164` calls 列表加 `(plugin.whereami, "whereami")`。
- 新增 `whereami` 单测（仿 `commands_permissions_test.py` whoami）：回显 UMO / 空 UMO 兜底。

### 8.2 single_allowed_groups 锚定测试（mirror permission_admins）

- `conf_schema_test.py:85-97`：加 `single_allowed_groups` schema 断言（type/default/items/display_item）。
- `config_permissions_test.py:11-20`：仿 parse + 去重 + 去空。
- `config_view_permissions_test.py:11-13,42-45`：仿 `sag-0` row_id 往返 + strip_meta。
- `collect.test.ts:35-37` TOP_KEYS 加 `'single_allowed_groups'` + collectBody 用例；`AdminCard.test.ts` 克隆为 `GroupCard.test.ts`；`SettingsPanel.test.ts`/`schema.test.ts` 确认其**不入** OBJECT_SECTIONS。

### 8.3 模式行为 & 前端分叉测试

- `config_world_mode_test.py:10,18,22-27`：默认/非法兜底/schema 默认 `multi`→`single`；`_base()` helper 缺键路径语义翻转复核。
- 迁移护栏单测（仿 `main_migration_test.py` `_FakeAstrBotConfig`）：(a) 存量有 servers/bindings 无 world_mode→回写 `multi` 且 `saved`；(b) 全新装无 servers→不动、`saved=False`、享 single；(c) 已显式 world_mode→幂等跳过不 save；(d) 端到端 `initialize()` 后 `container.config.routing.world_mode` 正确。
- `routing_world_mode_test.py`：新增 single+restricted **名单命中放行 / 未命中拒 / open 全放** 用例；删 `single_restricted_warning` 相关。
- `main_link_single_test.py`：删架空告警断言；显式 `world_mode="multi"` 传参用例复核不回归。
- 前端 vitest：SettingsPanel single 分支（单台表单 / link 隐藏 / default_server 隐藏 / 授权群名单出现）；CommandTree `hideGroups` 用例。

### 8.4 文档 & 版本

- `README.md:91,119`、`docs/commands.md:83-92`、`docs/configuration.md:11-16`：默认语义 multi→single 同步；`docs/commands.md` 记 `/pal whereami`；`single_allowed_groups` 配置说明；迁移 flat→保护对照。
- **readme 中文锚点**：改文案须同步 `tests/unit/readme_test.py` 中文短语锚点（含 `:93,:125` 的 `/pal whoami` 邻近段、`:109-113` 的 multi/single/多世界/单世界）。
- **版本四源** v0.9.7：`metadata.yaml`、`main.py @register`、`__init__.py __version__`、`README` badge + 2 处测试断言（同 Phase 1/2 先例）。

### 8.5 构建产物

- `frontend` 改动后 `npm run build`（已内置 normalize-eol），产物 `pages/settings/**` 入库，保 no-drift 与 LF（`.gitattributes` 强制）。

---

## 9. 安全考量

- **单模式 restricted 现真正生效**：授权群名单未命中即拒读，消除 v0.9.5 起的「架空」窗口。
- **门序不变**：写命令 admin 硬门（`permission_admins`）独立于路由授权；单模式路由授权（名单）先解析、写再过 admin，语义与多模式一致，不泄漏管理员身份。
- **迁移最保守**：存量一律冻结 multi，杜绝升级静默丢读权/丢多服务器路由。
- **whereami 只回显本会话 UMO**（非敏感、非他人信息），恒可用不构成信息泄漏；建议私聊/管理员使用的提示进文案。
- **note-id/PII**：`single_allowed_groups` 的 `umo`/`note` 与现有名单同为明文落盘，沿用既有告知（勿填 PII）。

---

## 10. 非目标（YAGNI）

- 不做单模式的群内授权命令（授权走设置页名单，已定）。
- 不改多模式任何行为/契约。
- 不动 `group_bindings` 及其前端契约。
- 不引入路由策略类（选配置派生谓词）。
- 不把 config 状态上提到 App.vue（模式标识落 chapter-head 即可）。
- whereami 不改 `whoami`。
