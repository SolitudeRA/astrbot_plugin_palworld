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

**目标**（2026-07-16 用户定稿修订）：① 这 5 条**纯 game-data、无交织**的命令后端恒禁用（配置写 on 也不生效）；② 设置页命令树显示禁用锁定行（「暂不可用」短标签，不带长原因）；③ **原因说明唯一载体 = 设置页顶部横幅**，可「不再提醒」永久关闭——聊天侧拦截保持既有泛化文案，不新增专属文案；④ 仍启用命令的输出中 game-data 派生部分**屏蔽**（today 据点变化分节、events 公会/据点类事件——采集恒关下自然缺席，验证之）；⑤ 手写启用的存量配置容忍 + 启动告警；⑥ 上游开放后**一步恢复**。

**非目标**：不删除任何数据结构 / 采集代码 / formatter / DTO / 据点推导（全部保留待恢复）；不改 `_VALID_COMMAND_KEYS`（存量 command_permissions 行仍可落盘保存——注意 enable_configurable 翻转后，unavailable 命令的 enabled 覆盖行**必须走 §3.5 的专属分流**，绝不能落进既有轴违规 invalid_command_keys 路径）；不动 LOCKABLE / admin_only 轴（锁存量无害，恢复后即生效）。

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

注（后端）：`effective_enabled` 首行 force-off 与「enable_configurable 排除 + default False」在当前取值下语义重叠——**刻意双保险**：即使将来有人改 FEATURE_DEFAULTS 或调整 enable_configurable 语义，force-off 仍独立成立，锁不静默失效。

⚠️ 注（前端，**方向相反，不是双保险**）：前端 `effEnabled` 现首行是 `if (!n.enableConfigurable) return true`（不可配 = core = **恒开**，fail-open，permissions.ts:47-48）。§4.1 把 guild×4 翻成 enableConfigurable=false 后，若 §4.2 的 `unavailable` 首判缺席或排在其后，guild 会**反转成恒开**——与本 spec 目标正面冲突。前端 unavailable 首判是**唯一承重护栏**：必须置于 `effEnabled`/`inheritEnabled` 函数第一行（先于 `!enableConfigurable` 判定），且由前端测试锁定（§5B）。

派生不变量：GAME_DATA 采集派生自 guild 组命令的 `effective_enabled` → force-off 使派生恒 False，**端点自然不轮询**（派生逻辑零改动，加测试锁定）。

### 3.4 聊天侧拦截（零改动——保持既有 feature_disabled）
**不新增 locale 键、不改任何拦截站点**（用户定稿：原因说明只在设置页横幅，聊天不重复）。force-off 后 5 条命令经既有 `effective_enabled` 判定自动收既有 `feature_disabled`（「该功能未开放：当前配置或服务器不支持。」）——真·生效拦截点是 `_dispatch_read`（commands.py:345-346 组分发功能门），零代码改动。门序不变量保持：功能门先于 admin 锁（:345 先于 :348）——对 unavailable 命令 admin 锁分支永不可达（§5A 的门序测试载体因此必须换组）。

### 3.5 存量配置容忍 + 启动告警（含轴违规分流——承重）
**冲突事实**：`config.py:355-358` 现有轴校验是 `if is_group or enable_configurable(cmd): 记录 else: invalid.append(f"{cmd}:enabled")`。enable_configurable 翻转后，叶子完整路径行（如 `{"command":"guild list","enabled":"on"}`）会落进 `invalid_command_keys`（轴违规，main.py:165 泛化告警）——违反 §2 非目标且与专属告警冲突；组名行则因 `is_group` 短路静默通过、漏收集。

**分流规则（必须在 :355 轴校验之前截获）**：
- 判定「命令级 unavailable」：`upstream_unavailable(cmd)`（完整路径）；「组级 unavailable」：组内全部叶子的 feat_group ∈ `UPSTREAM_UNAVAILABLE_FEATURES`（**由常量 + COMMAND_META 派生，不许硬编码组名 `guild`**——将来新增 unavailable feature 不漏）。
- 命中且 `enabled == "on"` → 记入 `upstream_ineffective_keys`（PermissionsConfig 新字段），行的 raw 数据照常保留落盘、**不进 invalid**；`enabled ∈ {off, inherit}` 不告警（用户预期即关闭）；admin_only 轴照旧走原逻辑（LOCKABLE 不变）。
- `main.py` 启动告警区（156-167 附近）追加：`以下命令依赖的 game-data 接口上游未开放，配置的启用未生效：%s`。

### 3.6 仍启用命令输出的 game-data 部分屏蔽
- **渲染面完整清单**（report/query 的 game-data 派生内容）：`world today` 的「据点变化」分节 + **「今日纪录」段的「新公会/新据点」行 + summary 的「N 处据点变化」**（report_service.py:135-138,190——三处都是，验收不能只看据点变化分节）；`world events` 的公会/据点类事件（NEW_GUILD/NEW_BASE/BASE_VANISHED/WORKER_DELTA 四枚举）。
- **缺席机制（措辞精确）**：**写侧不产**——该事件家族唯一产生于 ingest_game_data，force-off 双闸（active_endpoints 排除 + container 服务不装配）使新事件不再写入；且真服 /game-data 恒 404（snapshot_service 早退）是「从未落库」的硬保证。**读路径不过滤**（list_events 不按 event_type 过滤、formatter 对非空照常渲染）——「自然缺席」成立的依据是残留集为空，不是读侧屏蔽。若实机发现残留行渲染，加显式守卫（可选防御，非本期硬要求；届时须同时过滤 records 段的 new_guilds/new_bases，不能只过滤 base_events）。formatters 预期零改动。
- `world status` 不涉及（据点数来自官方 metrics）；help/裸组对禁用命令的隐藏是现有机制，自动生效。

## 4. 前端设计

### 4.1 PAL_TREE（`lib/schema.ts`，保持 JSON 可解析形态）
- `PalTreeNode` 接口加可选字段 `unavailable?: boolean`（注释：上游接口未开放，= 后端 upstream_unavailable(path)）。
- 5 个节点加 `"unavailable": true`；**guild×4 的 `enableConfigurable` true→false**；**overview 的 `defaultEnabled` true→false**；其余 24 节点不加字段（缺省 = false）。

### 4.2 `lib/permissions.ts`（复刻后端语义，防两端漂移）
- `effEnabled` / `inheritEnabled` **函数第一行**加 `if (n.unavailable) return false`——必须先于现有 `if (!n.enableConfigurable) return true`（该行是 core 恒开的 fail-open 分支，见 §3.3 前端注：这是唯一承重护栏，错位即 guild 反转恒开）。与 §4.1 的 enableConfigurable 翻转**同一提交**落地。
- `DEFAULT_ENABLED` 派生自动随 PAL_TREE 变化（overview → false）。
- `GROUP_DEFAULT_ENABLED`：guild 组变为「无可配叶子」→ 按 L2 已定语义不产键（与 link 同路径，现有派生代码零改动，加抽查断言）。

### 4.3 CommandTree.vue（功能页 enabled 轴）
- `lockedLabel`：enabled 轴 `n.unavailable` → **「暂不可用」**（优先于「恒开」判定）。短标签即止——**不加 title 长原因句、不加组头 caption**（原因说明唯一载体是 §4.5 横幅；原 caption 方案的 every/some 谓词陷阱随之消解）。
- 锁定行徽标：现模板对锁定标签硬接 `<small>内置</small>`（CommandTree.vue:151）——unavailable 行会渲染成「暂不可用 内置」语义错。unavailable 行徽标改「上游」（或不显示徽标，实现择一并在测试锁定）。
- guild 组头：`groupConfigurable` 因无可配叶子自然为 false → 无组头开关、显「—」（与 link 组现状同形，零新 markup）。
- **受管高亮抑制（承重）**：`groupManaged`（CommandTree.vue:79）现无 `groupConfigurable` 守卫——§3.5 容忍的存量 `{"command":"guild","enabled":"on"}` 组行会让不可配组头误亮「整组·受管」标（叶子层已有 `configurable(n) &&` 守卫，:141/:146；组头层缺）。规则：`!groupConfigurable(g)` 时不计 groupManaged、不亮整组标（统一覆盖 guild/link）。
- admin 轴零改动：这 5 条恒未启用 → 现有 `!effEnabled` 过滤自动不列。

### 4.4 其余前端
- SettingsPanel / collect / hydrate 零改动（存量 guild 覆盖行按「过滤不丢数据」不变量原样往返）。
- help（后端渲染）自动隐藏：overview 从恒列变不列（相关测试断言更新）。

### 4.5 设置页说明横幅（原因唯一载体，可永久关闭）
- SettingsPanel 章节内容顶部（所有配置章可见）显示说明横幅：
  「**公会/据点与世界概览功能暂不可用**：依赖的官方 game-data 接口（PalGameDataBridge）尚未对专用服务器开放，相关功能开关已禁用；待官方开放后随插件更新恢复。」＋ 按钮「不再提醒」。
- **横幅内联于 SettingsPanel 模板**（插点：`needsOnboarding` 的 `v-else` 内容顶部——该插点同时满足「6 个配置章可见 / 观测章不显示[SettingsPanel 被 v-show 隐藏] / onboarding 不显示[v-else 不渲染]」三条件，已核实 App.vue:64 + SettingsPanel.vue:221-222）；**勿抽独立子组件**——`.callout` 是 SettingsPanel scoped 样式（SettingsPanel.vue:351-355，全局无第二处），抽出去会失样式。
- 「不再提醒」→ localStorage 键 `palworld-terminal-gd-banner-dismissed` = '1'，永久关闭；受限 iframe localStorage 不可用时 try/catch 兜底（降级为本次会话关闭——复用主题 key 的容错**模式**：App.vue readStored/writeStored 是局部未导出函数，横幅自带一份同模式实现，非直接调用）。
- 样式复用现有 callout 原语，不新增全局 token；首次设置引导屏（onboarding）期间不显示（避免与引导叠加）；状态/审计观测章不显示（只在配置章——横幅关联的是功能开关）。

## 5. 跨端锚定与测试

### 5A. 既有测试改写清单（force-off 的语义反转波及面——**不是可选项，照单执行；严禁削弱 force-off 迎合旧断言**）

修法总原则：既有测试用 guild 当「可启用+可锁示范组」的，**示范载体迁到 player 组**（player 语义 = 改动前的 guild：可配/默认关/可锁/非 unavailable）；guild 的旧断言**反转为 force-off 护栏**（保留改写，不是删除）。反转时**同步改测试名/docstring**（`test_game_data_derived_from_guild_enable`/`test_guild_enabled_wires_game_data`/`test_world_overview_routes_to_world_impl` 三处名称会与新断言相反）；overview→world 实现的「非递归路由」护栏在 force-off 期间死于门后，接受该覆盖损失（恢复 PR 反转时自动回归）。

后端（12 处）：
1. `command_permissions_effective_test.py:15,18`：guild 组/叶 override on → True 断言反转为 False（:19 是空行，勿按旧引用漏改 :18）。
2. `command_permissions_endpoints_test.py:20-21`：GAME_DATA 入 active_endpoints 断言反转为不入集（与 §5B④ 是同一护栏的正反面）。
3. `config_command_permissions_test.py:25`：同 1 反转。
4. `container_features_test.py:63-65`（test_guild_enabled_wires_game_data）：guild on 装配 GAME_DATA/_guilds/_bases → 反转为不装配。
5. `feature_groups_off_test.py:49`：**零改动**（拦截文案保持 feature_disabled，断言继续绿）——自清单剔除。
6. `formatters_hierarchy_test.py:44-45`：visible_actions guilds_bases=True → 集合改恒空。
7. `formatters_hierarchy_test.py:54`：help（_all_on）含 `/pal guild info` → 改不含。
8. `formatters_test.py:127-128`：同 7 反转。
9. `commands_dispatch_test.py:141`：overview 触达实现（ROUTING_ERR）→ 改收 `feature_disabled` 文案。
10. `commands_dispatch_test.py:234`：裸组 help 含 overview → 改不含。
11. `commands_gating_test.py:58`：guilds_bases=True 放行 → 改收 `feature_disabled` 文案。
12. `commands_gating_test.py:82`（门序：admin 锁 denies guest）：功能门先短路致 admin_required 不可达 → **载体换 player 组**保门序覆盖不丢。
13. `namespace_runtime_smoke_test.py:112-114`（**绿但语义变——不红也要改**）：fixture `guilds_bases: True` 与注释「关掉的组命令直接回未开放…冒烟就白跑」对 5 条 game-data 命令失真（force-off 后它们恒短路 feature_disabled，深路径冒烟静默消失）——更新注释记录该设计变化（或从 fixture 删 guilds_bases 键），显式承认覆盖面变化。

前端（9 处）：
1. `CommandTree.test.ts:41-51`：enabled 轴组头开关点击示范 guild → player。
2. `CommandTree.test.ts:73`：admin 轴叶子计数 13→12，注释「world3」改「world2」、「恒开核心 11」改「10」。
3. `CommandTree.test.ts:92-97 / 113-118 / 119-134 / 135-141`：admin 轴 guild 载体四用例 → player。
4. `SettingsPanel.test.ts:155-170`：hydrate 用例的**渲染**断言载体换 player（第 164 行 state 数据层断言保留 guild 行——恰好锁「存量行往返不丢」）。
5. `permissions.test.ts:20`：兄弟随组示范 guild → player；guild 处改断言 false（force-off 护栏）。
6. `permissions.test.ts:65`：`GROUP_DEFAULT_ENABLED['guild']).toBe(false)` → `expect('guild' in GROUP_DEFAULT_ENABLED).toBe(false)`（键消失而非值 false）；同用例 it 描述（:63「guild 关」）改「guild 不产键」。

### 5B. 新增测试

- `tests/unit/frontend_pal_commands_test.py`：每节点断言 `n.get("unavailable", False) == upstream_unavailable(path)`（**须补 import** `upstream_unavailable`；现有 enableConfigurable/defaultEnabled 逐节点断言自动锚住两端翻转）。⚠️ 三向耦合：`command_registry.py`（归队）+ `command_permissions.py`（常量/enable_configurable）+ `schema.ts`（PAL_TREE 翻转）任一单独落地锚定测试即红——**三者同一提交**。
- 后端：① effective_enabled force-off（leaf on / 组 on 覆盖仍 False）；② 拦截回归锁（guild/overview 收**既有** feature_disabled——防实现时顺手加新文案）；③ 告警收集（leaf on 行与组 on 行都进 upstream_ineffective_keys 且**不进** invalid_command_keys；off/inherit 不告警）；④ 采集派生锁定（guild override on 时 GAME_DATA 不轮询）；⑤ help/裸组不含 overview 与 guild；⑥ 输出屏蔽验证——**锚定写侧/装配层，勿在 formatter 层测**（golden today.txt 保留「据点变化」渲染能力是有意的，直喂空 DTO 属同义反复）：驱动 ingest_game_data 在 force-off 下携带 GAME_DATA 载荷 → 断言 events 表无 NEW_GUILD/NEW_BASE 行落库；或装配层验证（snapshot 无 guilds/bases → today DTO 无 base_events/new_guilds/new_bases）。
- 前端：permissions.test（unavailable 首判 force-off——覆盖 guild 叶恒 false、防 §3.3 前端注的错位反转；guild 不产 GROUP_DEFAULT_ENABLED 键）；CommandTree.test（「暂不可用」锁定行 + 徽标非「内置」、存量 guild 组行不亮「整组」标）；SettingsPanel.test（横幅：默认显示、「不再提醒」后消失且 localStorage 置位、已置位时挂载即不显示、localStorage 抛错兜底不白屏、onboarding 态不显示）。**横幅用例自理 localStorage 卫生**：vitest.setup 的 in-memory Storage 是模块级共享 Map 不自动重置——beforeEach/afterEach 清 dismissed 键、抛错用例的 spy 用后恢复（防跨用例顺序依赖 flake）。横幅文案与既有 SettingsPanel `not.toContain` 锚点零冲突（已逐条核对）。
- README/docs 改动与 `tests/unit/readme_test.py` 中文锚点**同一提交**同步。
- golden 零改动（`format_world`/`format_guilds` 等 formatter 保留不删，golden 单测直调 formatter 不经功能门，继续绿）。

## 6. 文档同步（三处旧描述 + 矩阵）

1. `README.md:35`：「公会与据点 —— 依赖上游 `game-data`,默认关闭,开放后一键启用」→「公会与据点 —— 依赖上游 `game-data`（PalGameDataBridge），**官方暂未对专用服务器开放，暂不可用**；上游开放后随插件更新恢复」。
2. `README.md:108` 功能矩阵：`guilds_bases` 行「**默认关**」→「**暂不可用**（上游未开放）」，行示例补 `world overview`（归队后属本组）。
3. `_conf_schema.json:77`（polling.game_data_seconds）与 `:95`（bases）描述句尾追加「；上游暂未开放（PalGameDataBridge），guild 组与 world overview 暂不可用」。
4. **overview 归队的三处 core 行（易漏，逐处点名）**：`docs/commands.md:24`（world 组详表 overview 行「core」→「guilds_bases·暂不可用」）、`docs/commands.md:78`（可用性矩阵 core 行移除 `world overview`，移入 guilds_bases 行）、`docs/configuration.md:163`（features 表 core 行「world status/overview/rules」去掉 overview，guilds_bases 行补入）。
5. `docs/commands.md` guild 组段、`docs/configuration.md` 相应段同措辞更新（统一说法：「暂不可用」+「上游未开放（PalGameDataBridge）」）。

## 7. 恢复路径（上游开放后，一次 PR）

1. 后端：`UPSTREAM_UNAVAILABLE_FEATURES` 删 `"guilds_bases"`（3.2 常量注释即操作指南）。
2. 前端：PAL_TREE 5 节点删 `unavailable` 字段、guild×4 `enableConfigurable` 翻回 true、overview `defaultEnabled` 视产品决策定（默认关更稳）——**跨端锚定测试红→绿强制两端同步，即恢复护栏**。
3. 测试回收：§5A 反转过的断言翻回（示范载体可留 player 不必迁回）；§5B 新增的 force-off 专属测试（①②④⑤⑥与前端 force-off/横幅用例）删除或反转——恢复 PR 的测试面 = 本 PR 测试面的镜像。
4. 告警链路与横幅整体移除：config.py 分流收集器 + PermissionsConfig.upstream_ineffective_keys 字段 + main.py 告警块 + 前端横幅组件与 localStorage dismissed 键。
5. 文案/文档回收（本 spec §6 反向，含 commands.md:24/78、configuration.md:163 三处归位为 guilds_bases 可配组）。

## 8. 验收标准

1. 全套绿：后端 pytest / ruff / mypy、前端 vitest / typecheck、产物重建 no-drift。**基线净变**：§5A 列明的后端 12 处 + 前端 9 处既有断言按单改写/反转（不是「基线不动只加新测」），加 §5B 新增。
2. 语义验收：`/pal world overview`、`/pal guild list` 收既有 `feature_disabled` 文案（聊天无新说明）；`/pal world today` 无「据点变化」分节、「今日纪录」无新公会/新据点行、summary 无「N 处据点变化」（§3.6 渲染面三处都查）、`/pal world events` 无公会/据点类条目；配置手写 `{"command":"guild","enabled":"on"}` 后 effective 仍 False 且启动告警（专属 upstream 告警，非轴违规）；GAME_DATA 端点不轮询；help/权限页不见这 5 条。
3. UI 验收（dev demo 两主题）：功能页 guild 组灰锁「—」、overview 行「暂不可用」（徽标非「内置」）；说明横幅显示正常、「不再提醒」后刷新不再出现、onboarding 态不叠加。
4. 用词一致：「暂不可用」「上游未开放（PalGameDataBridge）」在设置页横幅与文档统一说法（聊天输出不引入新词）；readme_test 锚点绿。
