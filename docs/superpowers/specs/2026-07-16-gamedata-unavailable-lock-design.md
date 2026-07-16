# game-data 依赖功能「上游不可用」锁定 设计（spec）

> 日期：2026-07-16　分支：`fix/gamedata-unavailable-lock`（base main `8ecb941`，v0.9.8）
> 起因：命令输出重设计迭代中确认——`/game-data`（PalGameDataBridge）上游至今未对专用服务器开放，依赖它的命令在实机恒输出全零/空，其中 `world overview` 还挂在 core 组恒开不可关。本 spec 将这些功能锁定为「上游不可用」，UI 写明原因，并保留一步恢复路径。

## 1. 背景事实（已定论，勿重查）

- 官方文档存在 `GET /v1/api/game-data`（PalGameDataBridge），但 Palworld 1.0 专用服务器实测返回 **404 + `PalGameDataBridge GameData API is not enabled`**（2026-07-12 三视角调查 + 实服 v1.0.0.100427 复核定论）。无任何 INI/启动参数可开启。
- 依赖该端点的数据：GameDataSnapshot 全家（角色/随行/工作帕鲁/野生/NPC/PalBox/公会/据点推导）。
- 受影响命令共 **5 条**：`world overview`（feat=core——**归类错位**，数据实为 game-data 家族）+ `guild list / info / bases / base`（feat=guilds_bases，默认关但可配）。
- 采集派生现状（PR #21）：GAME_DATA 端点仅当「有 guild 组命令生效启用」才轮询（`_DERIVED_ENDPOINT_FEATURE`，command_permissions.py:118-120）。
- 无真实用户（2026-07-15 记忆），不需迁移护栏；本 spec 不改任何 config 键结构。

## 2. 目标 / 非目标

**目标**：① 这 5 条命令后端恒禁用（配置写 on 也不生效）；② 设置页命令树显示禁用锁定行 + 原因；③ 聊天侧拦截给专属原因文案；④ 手写启用的存量配置容忍 + 启动告警；⑤ 上游开放后**一步恢复**。

**非目标**：不删除任何数据结构 / 采集代码 / formatter / DTO / 据点推导（全部保留待恢复）；不改 `_VALID_COMMAND_KEYS`（存量 command_permissions 行仍合法可存）；不动 LOCKABLE / admin_only 轴（锁存量无害，恢复后即生效）。

## 3. 后端设计

### 3.1 归队：`world overview` → guilds_bases
`presentation/command_registry.py:26`：`"overview": ("world", "core", "read")` → `("world", "guilds_bases", "read")`。它本来就是 game-data 家族；恢复上游后 overview 应与 guild 组同为可配功能，不回 core。

### 3.2 单一真相源常量
`application/command_permissions.py` 新增：
```python
# 上游不可用 feature 集：/game-data（PalGameDataBridge）对专用服务器未开放（2026-07-12 实测定论，
# 404 "GameData API is not enabled"）。集内 feature 的命令恒禁用且不可配置；
# 上游开放后：从本集合删除该 feature + 前端 PAL_TREE 同步（跨端锚定测试强制两端一致）即恢复。
UPSTREAM_UNAVAILABLE_FEATURES: frozenset[str] = frozenset({"guilds_bases"})

def upstream_unavailable(path: str) -> bool:
    m = COMMAND_META.get(path)
    return m is not None and m.feat_group in UPSTREAM_UNAVAILABLE_FEATURES
```

### 3.3 语义变化（承重面，逐函数）

| 函数 | 变化 | 5 条命令的结果 |
|---|---|---|
| `enable_configurable(path)` | `feat != "core" and feat not in UPSTREAM_UNAVAILABLE_FEATURES` | guild×4：True→**False**；overview：False→False（原因从 core 变 upstream） |
| `default_enabled(path)` | 不变（读 FEATURE_DEFAULTS） | overview：True→**False**（随归队），guild×4 不变 False |
| `effective_enabled(overrides, path)` | **函数首行**插入 `if upstream_unavailable(path): return False`——先于叶子/组覆盖/默认的一切分支 | 5 条恒 False，任何 override（含存量 on 行、组头 on 行）不生效 |
| `admin_configurable` / `admin_forced_true` | 不变 | 不变 |

注：`effective_enabled` 首行 force-off 与「enable_configurable 排除 + default False」在当前取值下语义重叠——**刻意双保险**：即使将来有人改 FEATURE_DEFAULTS 或调整 enable_configurable 语义，force-off 仍独立成立，锁不静默失效。前端 `effEnabled` 首判同理。

派生不变量：GAME_DATA 采集派生自 guild 组命令的 `effective_enabled` → force-off 使派生恒 False，**端点自然不轮询**（派生逻辑零改动，加测试锁定）。

### 3.4 拦截文案（专属，替代泛化 feature_disabled）
`presentation/locale.py` 新键：
```python
"feature_upstream_unavailable": "该功能依赖官方 game-data 接口（PalGameDataBridge），Palworld 专用服务器暂未开放；待上游开放后可在设置页启用。",
```
`presentation/commands.py` 现有 5 个 `L("feature_disabled")` 站点（71-78 `_gated`、346、398、472、567）改走共用 helper：
```python
def _feature_denied(self, path: str) -> str:
    return L("feature_upstream_unavailable") if upstream_unavailable(path) else L("feature_disabled")
```
（567 行「未知写命令」站点无具体 path，保持 `feature_disabled` 不变。）

### 3.5 存量配置容忍 + 启动告警
config 解析（`config.py` permissions 解析处，与既有 `invalid_command_keys` 同族）新增收集：对 unavailable 命令（完整路径）或组名 `guild` 写了 `enabled ∈ {on}` 的覆盖行 → `upstream_ineffective_keys` 列表（行保留、不删、不报错）。`main.py` 启动告警区（156-167 附近）追加：
```
以下命令依赖的 game-data 接口上游未开放，配置的启用未生效：%s
```

## 4. 前端设计

### 4.1 PAL_TREE（`lib/schema.ts`，保持 JSON 可解析形态）
- `PalTreeNode` 接口加可选字段 `unavailable?: boolean`（注释：上游接口未开放，= 后端 upstream_unavailable(path)）。
- 5 个节点加 `"unavailable": true`；**guild×4 的 `enableConfigurable` true→false**；**overview 的 `defaultEnabled` true→false**；其余 24 节点不加字段（缺省 = false）。

### 4.2 `lib/permissions.ts`（复刻后端语义，防两端漂移）
- `effEnabled` / `inheritEnabled` 首判 `if (n.unavailable) return false`。
- `DEFAULT_ENABLED` 派生自动随 PAL_TREE 变化（overview → false）。
- `GROUP_DEFAULT_ENABLED`：guild 组变为「无可配叶子」→ 按 L2 已定语义不产键（与 link 同路径，现有派生代码零改动，加抽查断言）。

### 4.3 CommandTree.vue（功能页 enabled 轴）
- `lockedLabel`：enabled 轴 `n.unavailable` → **「暂不可用」**（优先于「恒开」判定）；锁定行 `title` 属性 = 完整原因句「上游 game-data 接口（PalGameDataBridge）未开放，暂不可用」。
- guild 组头：`groupConfigurable` 因无可配叶子自然为 false（无组头开关）；组头右侧 caption 位显示「上游接口未开放，暂不可用」。
- admin 轴零改动：这 5 条恒未启用 → 现有 `!effEnabled` 过滤自动不列。

### 4.4 其余前端
- SettingsPanel / collect / hydrate 零改动（存量 guild 覆盖行按「过滤不丢数据」不变量原样往返）。
- help（后端渲染）自动隐藏：overview 从恒列变不列（相关测试断言更新）。

## 5. 跨端锚定与测试

- `tests/unit/frontend_pal_commands_test.py`：每节点新增断言 `n.get("unavailable", False) == upstream_unavailable(path)`（现有 enableConfigurable/defaultEnabled 逐节点断言自动锚住两端翻转）。
- 后端新增：① `effective_enabled` force-off（含 leaf on / 组 on 覆盖仍 False）；② 门控文案分叉（guild 命令与 overview 收 upstream 文案；players 等其他关闭功能仍收 feature_disabled）；③ 启动告警收集（手写 on → upstream_ineffective_keys）；④ 采集派生锁定（guild 组 override on 时 GAME_DATA 仍不轮询）；⑤ help 不含 overview / guild（hierarchy 测试更新）。
- 前端：permissions.test（unavailable force-off、guild 组不产 GROUP_DEFAULT_ENABLED 键）、CommandTree.test（「暂不可用」锁定行、guild 组头原因 caption、title 原因句）。
- README/docs 改动与 `tests/unit/readme_test.py` 中文锚点**同一提交**同步。
- golden 零改动（format_status 等不涉及；`format_world`/`format_guilds` 等 formatter 保留不删，其 golden `world.txt` 对应单测继续跑——formatter 单测不经过功能门）。

## 6. 文档同步（三处旧描述 + 矩阵）

1. `README.md:35`：「公会与据点 —— 依赖上游 `game-data`,默认关闭,开放后一键启用」→「公会与据点 —— 依赖上游 `game-data`（PalGameDataBridge），**官方暂未对专用服务器开放，暂不可用**；上游开放后一键恢复」。
2. `README.md:108` 功能矩阵：`guilds_bases` 行「**默认关**」→「**暂不可用**（上游未开放）」；同表若列 `world overview` 归属 core 处同步归队。
3. `_conf_schema.json:77`（polling.game_data_seconds）与 `:95`（bases）描述句尾追加「；上游暂未开放（PalGameDataBridge），guild 组与 world overview 暂不可用」。
4. `docs/commands.md` 可用性矩阵与 guild 组段、`docs/configuration.md` 相应段同措辞更新（以「暂不可用·上游未开放」为统一说法）。

## 7. 恢复路径（上游开放后，一次 PR）

1. 后端：`UPSTREAM_UNAVAILABLE_FEATURES` 删 `"guilds_bases"`（3.2 常量注释即操作指南）。
2. 前端：PAL_TREE 5 节点删 `unavailable` 字段、guild×4 `enableConfigurable` 翻回 true、overview `defaultEnabled` 视产品决策定（默认关更稳）——**跨端锚定测试红→绿强制两端同步，即恢复护栏**。
3. 文案/文档回收（本 spec §6 反向）；`feature_upstream_unavailable` locale 键与告警按需保留或删。

## 8. 验收标准

1. 全套绿：后端 pytest（927+1 基线 + 新增）/ruff/mypy、前端 vitest（261 基线 + 新增）/typecheck、产物重建 no-drift。
2. 语义验收：`/pal world overview`、`/pal guild list` 收 upstream 专属文案；配置手写 `{"command":"guild","enabled":"on"}` 后 effective 仍 False 且启动告警；GAME_DATA 端点不轮询；help/权限页不见这 5 条。
3. UI 验收（dev demo 两主题）：功能页 guild 组灰锁 + 组头原因、overview 行「暂不可用」+ title 原因句。
4. 用词一致：「暂不可用」「上游未开放（PalGameDataBridge）」全库统一说法；readme_test 锚点绿。
