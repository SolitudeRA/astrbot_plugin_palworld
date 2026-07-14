# 分级感知权限：统一层级权限模型 + 设置页权限章重做（v0.9.5 Phase 2）

## 背景

Phase 1（PR #20）把 26 个扁平命令重构为分级 `/pal <组> <动作>`，并把门控下沉进
Commands 分发（功能门 per-子动作 + admin_only 锁按完整路径 + server 写 admin 硬门）。
但**权限/采集的配置模型仍停在 Phase 0 的「6 个功能组布尔」**：

- `FeaturesConfig`（6 bool：report/events/guilds_bases/players/server_admin_basic/danger）
  按**数据域**开关命令可用性，与命令树的**语义分组**不对齐——`players` 功能横跨
  `player` 组 + 扁平 `rank` + 扁平 `me` 两处；`report`=仅 `world today`；`events`=仅
  `world events`。用户无法「只关 world today 保留 world events」，也无法「按分级整组调」。
- admin_only 锁是一条**扁平字符串列表** `admin_only_commands`，与 enable 轴各走各的
  配置面；设置页有独立「功能开关」章 + 权限章平铺 chip 网格，两套心智。
- 采集（`active_endpoints`）从 `FeaturesConfig` 派生，是**第二根杠杆**，与命令 enable
  概念重叠却分开配置。

Phase 2 把这些统一到**一个以命令树为唯一控制面的层级权限模型**。

## 目标

1. **统一层级模型**：命令树的每个节点承载两个属性——`enabled`（是否可用）与
   `admin_only`（是否仅管理员）——取代 `FeaturesConfig` 与扁平 `admin_only_commands`
   的双轴分立。支持「1 级整组调」与「子级逐个调」（三级继承）。
2. **采集派生自 enable**：命令树是唯一控制面，采集自动算出（不再单独配置功能组）。
3. **门控复用生效值**：现有下沉门控（`_dispatch_read`/`admin_write`/`link`/
   `visible_actions` + 方法级 `_gated`）从查 `features.enabled(组)` 改为查命令的
   **生效 enabled**；admin 锁从查 `admin_only_commands` 改为查命令的**生效 admin_only**。
   门序铁律不变（写命令 admin 硬门先于 enable；写/绑定命令 admin_only 恒真不可关）。
4. **设置页权限章 = 命令树 UI**：删掉「功能开关」章 + 平铺 chip 网格，重做成
   可展开的命令树（组级批量 + 叶子逐个，两轴各一列开关，生效值/继承可视区分）。
5. **无痛迁移**：老 `features`(6 bool) + `admin_only_commands`(平铺) → 新
   `command_permissions`，启动迁移一次。
6. **权限名单保持全局**：`permission_admins`（谁是管理员）仍是全局名单；Phase 2
   **不**做「某人对某组有权」的按人分级。「调整权限分配」= 哪些命令要管理员
   （admin_only 轴，组/叶子），不是谁管哪。

## 非目标（YAGNI）

- 按人分级授权（某管理员只对某组有权）——名单仍全局。
- 让 web 状态页可被命令 enable 关掉——观测地板恒轮询（见 §6）。
- 改 DB schema / 审计表 / 二次确认 / routing 世界模式——纯配置模型 + 门控输入替换。
- 改命令树本身（组/动作不动）——Phase 2 只改「每个节点的权限属性怎么配」。

---

## §1 核心模型：命令节点的权限属性

命令树在 Phase 1 已有单一真相源：`DISPATCH`（5 组 × 子动作）+ `FLAT_ACTIONS`（6 扁平），
每项是 `ActionSpec = (方法名, feat_group, gate)`。Phase 2 **不新增手工元数据**——每个命令
节点的权限语义**全部从现有 ActionSpec + `_NON_LOCKABLE` + 现 feature 默认派生**：

| 派生属性 | 定义（从现有数据算） | 含义 |
|---|---|---|
| `enable_configurable(path)` | `feat_group != "core"` | enable 可否被用户配置。core 命令恒开、不可关。 |
| `admin_configurable(path)` | `path ∈ LOCKABLE_COMMANDS`（= gate==read 且 ∉ `_NON_LOCKABLE`） | admin_only 可否被用户配置。 |
| `admin_forced_true(path)` | `gate ∈ {admin_write, admin}` | admin_only 结构性恒真（server 7 写 + link add/remove + confirm），不可配。 |
| `default_enabled(path)` | 现 `FeaturesConfig` 默认按 feat_group 取（core=True、report=True、events=True、guilds_bases/players/server_admin_*=False） | enable 内置默认。 |
| `default_admin_only(path)` | `admin_forced_true` → True，否则 False | admin_only 内置默认（默认无锁）。 |

由此每个命令落入三类可配置组合（**这张表是模型的心脏**，实现须锚定）：

| 类别 | 命令 | enable | admin_only |
|---|---|---|---|
| **核心读**（core, read, ∉ NON_LOCKABLE） | world status/overview/rules、online | 恒开·不可配 | **可配**·默认关 |
| **域读**（≠core, read, ∈ LOCKABLE） | world today、world events、guild list/info/bases/base、player info/bind/unbind、rank、me | **可配**·默认见下 | **可配**·默认关 |
| **固定开放**（core, read, ∈ NON_LOCKABLE） | link list、help、whoami | 恒开·不可配 | 恒开放·不可配 |
| **写/绑定**（admin_write / admin） | server announce/save/kick/unban/ban/shutdown/stop、link add/remove、confirm | announce…stop **可配**·默认关；link add/remove、confirm 恒开·不可配 | **恒仅管理员·不可配** |

域读默认 enabled：`world today`/`world events`=开（report/events 默认 True）；
`guild.*`/`player.*`/`rank`/`me`=关（guilds_bases/players 默认 False）。
写命令 `server.*` 默认关（server_admin_* 默认 False）。

> `danger` 分类（ban/shutdown/stop）在 Phase 1 是 `server_admin_danger` 功能组，Phase 2
> **保留为固定命令分类**（驱动二次确认 + 审计归类），但**不再是 enable 配置杠杆**——
> 7 个写命令各自独立 enable（比旧 basic/danger 两档更细，且各默认关，安全性不降）。

**生效值计算**（三级继承，只存覆盖=稀疏）：

```
effective_enabled(path):
    if not enable_configurable(path): return default_enabled(path)   # 核心/固定开放/link·confirm 恒开
    return leaf_override(path).enabled  ??  group_override(group_of path).enabled  ??  default_enabled(path)

effective_admin_only(path):
    if admin_forced_true(path):        return True                   # 写/绑定/confirm 恒真
    if not admin_configurable(path):   return False                  # link list/help/whoami 恒开放
    return leaf_override(path).admin_only  ??  group_override(...).admin_only  ??  False
```

扁平命令（rank/online/me/…）无组层 → 跳过 group_override 一级。

---

## §2 配置形状：`command_permissions`（稀疏覆盖 + 三级继承）

新增配置节 `command_permissions`：**dict，键 = 组名或完整路径，值 = 覆盖对象**
`{enabled?: bool, admin_only?: bool}`。只存偏离默认的覆盖；空 dict = 全用内置默认。

```jsonc
{
  "command_permissions": {
    "player":       { "enabled": true },        // 组级：整组开（player info/bind/unbind）
    "world today":  { "enabled": false },        // 叶子级：单条关（即使 world 组开）
    "guild list":   { "admin_only": true },      // 叶子级：单条锁为仅管理员
    "rank":         { "enabled": true }          // 扁平命令（无组层）
  }
}
```

- 键类型：**组名** ∈ {world, guild, player, server, link}（覆盖该组全部叶子）
  或**完整路径**（`world today` / 扁平 `rank`）。
- 生效 = 叶子覆盖 ?? 组覆盖 ?? 内置默认（§1）。
- 「1 级整组调」= 写组键；「子级逐个调」= 写叶子键。
- **解析期清洗**（照 `_parse_permissions` 现有 `unknown_locks` 先例，绝不静默吞）：
  - 未知键（非组名、非已知路径）→ 丢弃 + 登记 `invalid_command_keys` 供启动告警。
  - 在**不可配轴**上设覆盖（如给 `link list` 设 `admin_only`、给核心命令设 `enabled`、
    给写命令设 `admin_only`）→ 该字段忽略（生效仍走恒定值）+ 登记告警。
  - 非 bool 值 → 忽略该字段。

`PermissionsConfig` 增字段 `command_overrides: dict[str, CommandOverride]` +
`invalid_command_keys: list[str]`（告警）。旧 `admin_only_commands`/`unknown_locks`
字段**移除**（迁移到新模型，见 §5）；`FeaturesConfig` 整个**移除**。

---

## §3 生效值查询 API

在 `application/` 新增纯函数模块 `command_permissions.py`（无 IO、可单测），作为门控 +
采集 + 前端往返的唯一生效值真相源：

```python
def enable_configurable(path: str) -> bool: ...
def admin_configurable(path: str) -> bool: ...
def effective_enabled(overrides: Mapping[str, CommandOverride], path: str) -> bool: ...
def effective_admin_only(overrides: Mapping[str, CommandOverride], path: str) -> bool: ...
def active_endpoints(overrides) -> frozenset[EndpointName]: ...   # §6
```

派生元数据（configurable/forced/default）从 `command_registry` 的 `DISPATCH`/
`FLAT_ACTIONS`/`_NON_LOCKABLE` + 一张 `FEATURE_DEFAULTS: dict[str,bool]`（承接现
`_default_features` 语义）算出，集中一处、有防漂移测试锚定到 registry。

---

## §4 门控改造（复用生效值，门序不变）

所有现查 `self._cfg.features.enabled(组)` 的落点改查 `effective_enabled(overrides, 完整路径)`；
所有 admin 锁落点改查 `effective_admin_only(overrides, 完整路径)`。逐点：

| 落点 | 现状 | 改为 |
|---|---|---|
| `commands.py:_gated`（方法级装饰器，L75） | `features.enabled(组)` | 按该方法对应完整路径查 `effective_enabled`；**收口 Phase 1 遗留**：`_gated` 只服务扁平 rank/online/me 等，改为按路径判定，`COMMANDS`/`COMMAND_GROUP` 双真相源删除。 |
| `_dispatch_read`（L337） | `features.enabled(feat_group)` | `effective_enabled(ov, f"{group} {sub}")` |
| `_dispatch_read`（L340） | `_admin_locked(path)` 查 `admin_only_commands` | `effective_admin_only(ov, path)` |
| `admin_write`（L453） | `features.enabled(组)` | `effective_enabled(ov, 写路径)`；**admin 硬门（L448）仍先于 enable**，不变 |
| `link`（L389） | `features.enabled(core)` 恒真 | `link list` 恒开、add/remove 恒开（core 不可配），逻辑等价；admin 门不变 |
| `formatters._action_visible`（L148） | `features.enabled(feat_group)` + gate 角色 | `effective_enabled(ov, path)` + gate 角色（不变） |

**门序铁律（不变）**：写命令 `admin_write` 内 admin 硬门先于 enable 门；写/绑定/confirm
的 admin_only 恒真、结构不可绕；裸组角色隔离复用 `visible_actions` 单一谓词（guest 不
泄漏 kick/ban/stop）。

**可见性语义保持不变（明确非目标）**：`_action_visible` 只换 enable 数据源
（`features.enabled` → `effective_enabled`），**不**引入「admin_only 锁读命令对非管理员
不可见」。锁定读命令仍是「help/裸组可见但执行拒」——与现状一致，避免把正交的可见性
收紧塞进本期，降低风险。执行期 `effective_admin_only` 拒绝（直呼路径也挡）保持。
（gate=admin_write/admin 的写/绑定命令对非管理员不可见，是 Phase 1 既有行为，不变。）

---

## §5 迁移：旧模型 → `command_permissions`

启动解析期一次性迁移（照 DB/localStorage 迁移先例，读完旧键即弃）：

1. **features（6 bool）→ 组/命令 enable 覆盖**：对每个旧 feature 布尔，若其值 ≠ 该
   feature 的内置默认，则为其覆盖的命令写 enable 覆盖。映射：
   - `report` → `world today`；`events` → `world events`；
   - `guilds_bases` → `guild`（组键）；
   - `players` → `player`（组键）+ `rank` + `me`（扁平，各写叶子键）；
   - `server_admin_basic` → announce/save/kick/unban（各叶子）；
     `server_admin_danger` → ban/shutdown/stop（各叶子）。
   仅当旧值偏离默认才写覆盖（保持稀疏 + 幂等）。
2. **admin_only_commands（平铺完整路径）→ admin_only 覆盖**：每条若 ∈ LOCKABLE，写
   `{path: {admin_only: true}}`；非 LOCKABLE 条目 → `invalid_command_keys` 告警（承接
   现 `unknown_locks` 语义）。
3. 迁移在 `parse_config` 内完成，输出统一的 `command_overrides`；旧 `features`/
   `admin_only_commands` 顶层键读完不再回写（下次保存时 config_view 只吐新键）。

**兼容窗口**：迁移是「读旧→算新」，旧配置文件无需用户手改即生效；新写入只含
`command_permissions`。文档给出旧→新对照表。

---

## §6 采集派生自 enable

**关键约束（安全）**：web 状态页（观测章 `kind:'status'`）与核心读命令共用 INFO/METRICS/
PLAYERS/SETTINGS 四端点。这四个是**观测地板**，恒轮询——采集**不**纯随聊天命令 enable
派生，否则关掉命令会让网页仪表盘熄火。真正派生的只有 `GAME_DATA`。

```
OBSERVATION_FLOOR = {INFO, METRICS, PLAYERS, SETTINGS}   # web 仪表盘 + 核心读，恒轮询
COMMAND_ENDPOINTS: 命令 → 其所需非地板端点   # 目前仅 guilds_bases 命令 → GAME_DATA

active_endpoints(overrides) =
    OBSERVATION_FLOOR
    ∪ { ep  for 某命令 path 若 effective_enabled(ov, path) 且 ep ∈ COMMAND_ENDPOINTS[path] }
```

- 结果与今日等价（GAME_DATA ⟺ guild 命令 enabled；默认关），但**输入从
  `features.guilds_bases` 换成「命令生效 enable」**——达成「命令树唯一控制面」。
- `container.py:154` 从 `active_endpoints(cfg.features)` 改为
  `active_endpoints(cfg.permissions.command_overrides)`。
- `feature_groups.py` 的 `ENDPOINT_GROUP`/`active_endpoints(features)` 由新
  `command_permissions.active_endpoints` 取代（旧模块删除或改写）。

---

## §7 设置页权限章 = 命令树 UI

删掉「功能开关」章（`chapters.ts` 的 `feature` 项，blocks features/players/server_admin）
——其内容并入权限章。权限章（`kind:'settings'`，特例块）重做为：

1. **管理员名单**：沿用现 AdminCard（`permission_admins`），不变。
2. **命令树**：可展开的分级表。
   - 一行一命令，按组分组（组头行可折叠）；扁平命令归入「其他」段（复用 formatters
     `_FLAT_LABEL`「其他」）。
   - 每行两列开关：**启用**（enable）+ **仅管理员**（admin_only）。不可配的格显示为
     锁定/置灰并展示恒定生效值（core 恒开、写/绑定恒仅管理员、link list/help/whoami
     恒开放）。
   - **组头行**有「整组启用 / 整组仅管理员」批量开关，写组级覆盖；展开后叶子行覆盖
     组级（视觉区分「继承自组/默认」vs「本行覆盖」）。
   - 危险写命令（ban/shutdown/stop）行加危险标记。
- 前端 `PAL_COMMANDS`（现 15 可锁）扩为**完整命令树描述**（含 configurable 标志），
  跨端锚定后端 `command_permissions` 派生元数据（现 `frontend_pal_commands_test` 升级）。
- `collectBody` 从命令树 UI 收敛为 `command_permissions` 稀疏 dict 回写。

> 前端树 UI 是本期视觉重点，可能启用 artifact-design / 可视化协作（实现期定）。

---

## §8 `_conf_schema.json` / config_view 往返

- `_conf_schema.json`：**移除** `features`（6 bool）与旧 `admin_only_commands` 项；
  `permission_admins` 不变。新增 `command_permissions`（object 型；AstrBot 原生设置页
  渲染为高级/JSON 编辑，描述指向插件自带设置页为主编辑面）。
- `config_view.py`：`_TOP_KEYS` 去 `features`/`admin_only_commands`、加
  `command_permissions`；新增 `command_permissions` 形状校验（dict，值为
  `{enabled?/admin_only?: bool}`，键/轴合法性照 §2 清洗，非法项拒绝或告警——与
  `admin_only_commands` 现有独立校验同规格）。往返闭合（collectBody 键 ↔ `_TOP_KEYS`）。
- `server_admin`（require_confirmation/timeout/retention）**保留不变**（它是管控行为
  配置，非命令 enable）。其 schema subtitle「任一组启用时生效」文案随命令化调整。

---

## §9 锚定与测试

- **模型派生锚定**：`command_permissions` 的 configurable/forced/default 派生 ↔
  `command_registry`（DISPATCH/FLAT/`_NON_LOCKABLE`/FEATURE_DEFAULTS）交叉全等测试。
- **门控回归**：现有 gating/dispatch/admin_write/formatters 测试改用 `command_permissions`
  覆盖驱动；补继承（叶子覆盖组、组覆盖默认）+ 恒定轴（不可配格）用例。
- **迁移测试**：旧 features + admin_only_commands 各形态 → 生效值等价 + 稀疏性 + 幂等。
- **采集派生测试**：地板恒在；guild enabled ⟺ GAME_DATA；关光聊天命令地板仍在。
- **可见性不回归**（§4）：锁定读命令仍「可见但执行拒」；写/绑定命令仍对 guest 不可见。
- **跨端锚定**：前端命令树描述 ↔ 后端派生元数据全等（升级 `frontend_pal_commands_test`）。
- **_conf_schema 防漂移**：schema 键 ↔ `_TOP_KEYS` ↔ 迁移映射一致（承接现有防漂移测试）。
- 全库 pytest + ruff + mypy + 前端 vitest + `pages/settings` no-drift 全绿。

---

## §10 版本与文档

- 版本四源默认 **v0.9.6**（Phase 1 已作为 v0.9.5 合并发布；Phase 2 是独立 PR，按序
  进位到 v0.9.6，避免两个已发布 PR 同号）。终审前与用户确认可回退同号 v0.9.5。
- README / 设置页文案：更新权限章说明（命令树控制面）、旧「功能开关」表述迁移、
  旧→新配置对照表；改中文用词须同步 `tests/unit/readme_test.py` 中文锚点短语。
- 三条安全告知（名册全局爆炸半径 / 多群共享命名空间 / note-id 明文）保留。

---

## 分期与交付顺序（供 writing-plans 参考）

1. **后端地基**：`command_permissions.py`（生效值 API + 派生元数据 + 锚定）→ config
   模型（`PermissionsConfig` 新字段 + 解析清洗）→ 迁移。可独立跑绿。
2. **门控 + 采集切换**：各门控落点改查生效值 + `active_endpoints` 派生 + `container`
   接线 + 删 `FeaturesConfig`/`feature_groups`/`COMMANDS` 双真相源。全库绿。
3. **往返闭合**：`_conf_schema` + `config_view`（_TOP_KEYS + 形状校验）。
4. **前端权限章树 UI**：schema.ts 命令树描述 + SettingsPanel 树组件 + chapters 去
   feature 章 + collectBody 回写 + 跨端锚定。
5. **文档 + 版本 + 终审**。
