# game-data 上游不可用锁定 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将依赖 `/game-data`（PalGameDataBridge，上游 404 未开放）的 5 条命令（`world overview` + `guild list/info/bases/base`）锁定为「上游不可用」：后端 force-off、UI 锁定行 + 可永久关闭的说明横幅、存量配置容忍 + 启动告警、一步恢复路径。

**Architecture:** 后端单一真相源常量 `UPSTREAM_UNAVAILABLE_FEATURES` 驱动 `enable_configurable`/`effective_enabled` 双闸；前端 PAL_TREE `unavailable` 字段 + `effEnabled` 首行护栏（唯一承重，防 fail-open 反转）；聊天侧零改动（拦截走既有 feature_disabled、输出靠写侧不产自然缺席）；原因说明唯一载体 = 设置页横幅（localStorage 永久关闭）。

**Tech Stack:** Python（AstrBot 插件，相对导入）+ Vue3/reka-ui + Vitest/pytest。

**Spec（需求真源，两轮对抗复核定稿）:** `docs/superpowers/specs/2026-07-16-gamedata-unavailable-lock-design.md`

## Global Constraints

- 包内 Python 一律**相对导入**（绝对自导入运行时炸，有静态防回归测试）。
- **三向同 commit 耦合**：`command_registry.py`（归队）+ `command_permissions.py`（常量/函数）+ `frontend/src/lib/schema.ts`（PAL_TREE 翻转）任一单独落地，`frontend_pal_commands_test.py` 逐节点锚定即红——T1 一次提交内完成。
- **严禁削弱 force-off 迎合旧断言**——既有测试按 spec §5A 清单改写/反转，示范载体迁 player。
- 前端 `effEnabled`/`inheritEnabled` 的 `unavailable` 首判**必须在 `!enableConfigurable` 恒开分支之前**（spec §3.3 前端注：唯一承重护栏）。
- PAL_TREE 保持 JSON 可解析形态（双引号、true/false、数组内无注释）。
- 聊天侧文案零改动：不新增 locale 键；拦截 = 既有 `L("feature_disabled")`。
- 横幅**内联于 SettingsPanel 模板**（`.callout` 是 scoped 样式，勿抽子组件）；localStorage 键 `palworld-terminal-gd-banner-dismissed`，try/catch 容错。
- README/docs 中文用词改动与 `tests/unit/readme_test.py` 锚点**同一提交**。
- 版本号不变（v0.9.8，定版留 finishing）；提交信息**不得出现 Claude**（正文与尾行均不提，无 Co-Authored-By）。
- 产物 `pages/settings` 只经 `cd frontend && npm run build`（内置 normalize-eol）重建，T7 统一做。
- 测试命令：后端 `./.venv/Scripts/python.exe -m pytest -q`（基线 927 passed + 1 skipped；repository_sessions_test 偶发 3 个 teardown ERROR 是 Windows flake，复跑即消）、`ruff check .`、`./.venv/Scripts/python.exe -m mypy palworld_terminal`；前端 `cd frontend && npx vitest run`（基线 261）、`npm run typecheck`。

---

### Task 1: force-off 原子切换 + 跨端锚定 + 既有测试改写（大原子任务）

**Files:**
- Modify: `palworld_terminal/presentation/command_registry.py:26`
- Modify: `palworld_terminal/application/command_permissions.py`（常量 + `upstream_unavailable` + `enable_configurable` + `effective_enabled`）
- Modify: `frontend/src/lib/schema.ts`（PalTreeNode 接口 + 5 节点）
- Modify: `frontend/src/lib/permissions.ts`（effEnabled/inheritEnabled 首判）
- Test: `tests/unit/frontend_pal_commands_test.py`（+unavailable 断言与 import）
- Test（改写，spec §5A 后端 1-13 / 前端 5-6）：`command_permissions_effective_test.py` / `command_permissions_endpoints_test.py` / `config_command_permissions_test.py` / `container_features_test.py` / `feature_groups_off_test.py`（零改动核验） / `formatters_hierarchy_test.py` / `formatters_test.py` / `commands_dispatch_test.py` / `commands_gating_test.py` / `namespace_runtime_smoke_test.py` / `frontend/src/lib/permissions.test.ts`
- Test（改写，spec §5A 前端 1-4）：`frontend/src/components/CommandTree.test.ts` / `frontend/src/components/SettingsPanel.test.ts`

**Interfaces:**
- Produces: `upstream_unavailable(path: str) -> bool`、`UPSTREAM_UNAVAILABLE_FEATURES: frozenset[str]`（T2/T5 消费）；PAL_TREE 节点可选字段 `unavailable?: boolean`（T3 消费）。

- [ ] **Step 1（TDD 红）**：`frontend_pal_commands_test.py` 扩：`from palworld_terminal.application.command_permissions import upstream_unavailable`（与既有 import 并列），逐节点循环内加 `assert n.get("unavailable", False) == upstream_unavailable(p), p`。跑该文件 → 红（后端无此函数）。
- [ ] **Step 2（后端核心）**：
  - `command_registry.py:26`：`"overview": ("world", "core", "read")` → `"overview": ("world", "guilds_bases", "read")`（保留行尾注释并追加 `；2026-07-16 归队 game-data 家族`）。
  - `command_permissions.py` 新增（FEATURE_DEFAULTS 附近）：
```python
# 上游不可用 feature 集：/game-data（PalGameDataBridge）对专用服务器未开放
# （2026-07-12 实测定论：404 "GameData API is not enabled"，无任何参数可开启）。
# 集内 feature 的命令恒禁用且不可配置；上游开放后的恢复操作：从本集合删除该
# feature + 同步前端 PAL_TREE（schema.ts 的 unavailable/enableConfigurable/
# defaultEnabled）——跨端锚定测试红→绿即恢复护栏。详见 spec §7。
UPSTREAM_UNAVAILABLE_FEATURES: frozenset[str] = frozenset({"guilds_bases"})


def upstream_unavailable(path: str) -> bool:
    m = COMMAND_META.get(path)
    return m is not None and m.feat_group in UPSTREAM_UNAVAILABLE_FEATURES
```
  - `enable_configurable`：`return m is not None and m.feat_group != "core" and m.feat_group not in UPSTREAM_UNAVAILABLE_FEATURES`
  - `effective_enabled` 函数首行插入：`if upstream_unavailable(path):`↵`    return False  # 上游不可用硬锁：先于一切覆盖（与 enable_configurable 排除构成双保险）`
- [ ] **Step 3（前端核心，同一提交）**：
  - `schema.ts`：`PalTreeNode` 接口加 `unavailable?: boolean`（注释：上游接口未开放，= 后端 upstream_unavailable(path)；缺省 false）。5 节点改动：`world overview` 行 `"defaultEnabled": true`→`false` 且行尾加 `, "unavailable": true`；`guild list/info/bases/base` 四行 `"enableConfigurable": true`→`false` 且各加 `, "unavailable": true`。
  - `permissions.ts`：`effEnabled` 与 `inheritEnabled` **函数第一行**加 `if (n.unavailable) return false // 上游不可用硬锁——必须先于 !enableConfigurable 的恒开(fail-open)分支`。
- [ ] **Step 4（既有测试改写——照 spec §5A 清单逐条，方向与载体迁移按单执行）**：后端 13 条（含 namespace 冒烟「绿但语义变」的注释/fixture 更新、门序测试换 player 载体、三处测试名/docstring 同步改名）；前端 6 条（CommandTree 载体迁 player、计数 13→12 与注释 11→10、SettingsPanel 渲染断言载体换 player 而 state 断言保留 guild、permissions.test 兄弟随组换 player + guild 键消失断言）。
- [ ] **Step 5（新增护栏测试）**：后端——5 条路径 leaf on/组 on 覆盖下 `effective_enabled` 恒 False；`/pal guild list` 与 `/pal world overview` 经 commands 层收 `L("feature_disabled")`（拦截回归锁）；前端 `permissions.test.ts`——guild 叶 `effEnabled` 恒 false（首判护栏，错位即红）。
- [ ] **Step 6**：全套绿（后端 pytest+ruff+mypy、前端 vitest+typecheck），单一提交（`feat: game-data 依赖功能上游不可用锁定——force-off 核心 + 跨端锚定`）。

### Task 2: config 轴违规分流 + 启动告警

**Files:**
- Modify: `palworld_terminal/config.py`（`_parse_permissions` 轴校验前分流 + `PermissionsConfig` 加字段）
- Modify: `palworld_terminal/application/command_permissions.py`（组级判定 helper）
- Modify: `main.py`（启动告警区 156-167 附近）
- Test: `tests/unit/config_command_permissions_test.py`（或同族新文件）

**Interfaces:**
- Consumes: T1 的 `upstream_unavailable` / `UPSTREAM_UNAVAILABLE_FEATURES`。
- Produces: `PermissionsConfig.upstream_ineffective_keys: tuple[str, ...]`；`upstream_unavailable_group(group: str) -> bool`。

- [ ] **Step 1（TDD 红）**：新测试——`{"command":"guild list","enabled":"on"}` 与 `{"command":"guild","enabled":"on"}` 解析后：均入 `upstream_ineffective_keys`、均**不在** `invalid_command_keys`、raw 行保留（生效值仍 False）；`enabled∈{off,inherit}` 两者皆不入；admin_only 轴不受影响。跑 → 红。
- [ ] **Step 2**：`command_permissions.py` 加：
```python
def upstream_unavailable_group(group: str) -> bool:
    metas = [m for m in COMMAND_META.values() if m.group == group]
    return bool(metas) and all(m.feat_group in UPSTREAM_UNAVAILABLE_FEATURES for m in metas)
```
- [ ] **Step 3**：`config.py` `_parse_permissions`：在 `config.py:355-358` 轴校验分支**之前**插入分流——`enabled == "on"` 且（`upstream_unavailable(cmd)` 或 `is_group and upstream_unavailable_group(cmd)`）→ 记 `f"{cmd}:enabled"` 入 `upstream_ineffective` 列表，行照常记录（raw 保留）、**不进** invalid；`PermissionsConfig` 加 `upstream_ineffective_keys` 字段（沿 `invalid_command_keys` 同形）。
- [ ] **Step 4**：`main.py` 启动告警区追加：`以下命令依赖的 game-data 接口上游未开放，配置的启用未生效：%s`（仅列表非空时）。
- [ ] **Step 5**：测试绿 + 全套绿，提交（`feat: 上游不可用命令的配置分流告警——不入轴违规、raw 保留`）。

### Task 3: CommandTree「暂不可用」视觉 + 受管高亮抑制

**Files:**
- Modify: `frontend/src/components/CommandTree.vue`（lockedLabel / 徽标 / groupManaged）
- Test: `frontend/src/components/CommandTree.test.ts`

**Interfaces:** Consumes T1 的 `n.unavailable`。

- [ ] **Step 1（TDD 红）**：新用例——enabled 轴 guild 叶行含「暂不可用」且徽标文本非「内置」（为「上游」）；state 含 `{"guild":{enabled:'on'}}` 时公会组头**无** `managed` 类且无「整组」标；player 组头受管高亮回归不变。跑 → 红。
- [ ] **Step 2**：`lockedLabel` 首行加 `if (props.axis === 'enabled' && n.unavailable) return '暂不可用'`；模板 `:151` 的 `<small>内置</small>` 改 `<small>{{ n.unavailable ? '上游' : '内置' }}</small>`；`groupManaged` 加守卫：`!g.isFlat && groupConfigurable(g) && hasAxisOverride(g.key)`。
- [ ] **Step 3**：vitest 全绿 + typecheck，提交（`feat(fe): 命令树上游不可用锁定行视觉 + 不可配组受管高亮抑制`）。

### Task 4: 设置页说明横幅（可永久关闭）

**Files:**
- Modify: `frontend/src/components/SettingsPanel.vue`（模板内联横幅 + script）
- Test: `frontend/src/components/SettingsPanel.test.ts`

- [ ] **Step 1（TDD 红）**：五用例（默认显示横幅文案「暂不可用」「PalGameDataBridge」/ 点「不再提醒」后消失且 `localStorage.getItem('palworld-terminal-gd-banner-dismissed')==='1'` / 预置 '1' 挂载即不显示 / `getItem` 抛错时不白屏且横幅显示 / `needsOnboarding` 态不渲染横幅）+ **beforeEach 清 dismissed 键、抛错 spy 用后恢复**（vitest.setup 的 Storage 是模块级共享 Map）。跑 → 红。
- [ ] **Step 2**：script 加：
```ts
const GD_BANNER_KEY = 'palworld-terminal-gd-banner-dismissed'
const gdBannerDismissed = ref(false)
try { gdBannerDismissed.value = localStorage.getItem(GD_BANNER_KEY) === '1' } catch { /* 受限 iframe：本次会话内显示 */ }
function dismissGdBanner() {
  gdBannerDismissed.value = true
  try { localStorage.setItem(GD_BANNER_KEY, '1') } catch { /* 降级：会话内关闭 */ }
}
```
  模板：`needsOnboarding` 的 `v-else` 内容顶部（chapter-head 前）内联：
```html
<div v-if="!gdBannerDismissed" class="callout gd-banner">
  <p><b>公会/据点与世界概览功能暂不可用</b>：依赖的官方 game-data 接口（PalGameDataBridge）尚未对专用服务器开放，相关功能开关已禁用；待官方开放后随插件更新恢复。</p>
  <button class="ghost" @click="dismissGdBanner">不再提醒</button>
</div>
```
  （markup 按现有 `.callout` 结构微调；`gd-banner` 补充 scoped 布局样式按需，不新增全局 token。）
- [ ] **Step 3**：vitest 全绿 + typecheck，提交（`feat(fe): game-data 不可用说明横幅——设置页唯一原因载体，可永久关闭`）。

### Task 5: 输出屏蔽写侧/装配层验证测试

**Files:**
- Test: `tests/unit/`（新文件或并入 `container_features_test.py`/snapshot ingest 同族）

- [ ] **Step 1**：写侧测试——构造 guild override on（force-off 生效）的 container/服务装配，喂含 game-data 载荷的假客户端跑一次采集 tick → 断言 events 表无 `NEW_GUILD`/`NEW_BASE`/`BASE_VANISHED`/`WORKER_DELTA` 行（参照 spec §5B⑥；勿在 formatter 层直喂 DTO——golden 保留渲染能力是有意的）。
- [ ] **Step 2**：装配层测试——snapshot 无 guilds/bases 时 daily 报告 DTO 的 `base_events`/`new_guilds`/`new_bases` 为空、events 查询无公会/据点类条目。
- [ ] **Step 3**：全套绿，提交（`test: game-data 输出屏蔽链路锁定——写侧不产 + 装配层缺席`）。

### Task 6: 文档同步（与锚点同提交）

**Files:**
- Modify: `README.md:35,108`、`_conf_schema.json:77,95`、`docs/commands.md:24,78,81 与 guild 组段`、`docs/configuration.md:163 与相应段`
- Test: `tests/unit/readme_test.py`（锚点核验，预期零改动——「默认关」经 players 行存活）

- [ ] **Step 1**：照 spec §6 五项逐处改（统一说法「暂不可用」+「上游未开放（PalGameDataBridge）」；overview 从三处 core 行移入 guilds_bases 行；README:108 行示例补 world overview）。
- [ ] **Step 2**：`./.venv/Scripts/python.exe -m pytest -q tests/unit/readme_test.py tests/unit/conf_schema_test.py` 绿 + 全套绿，提交（`docs: game-data 依赖功能标注暂不可用（上游未开放）+ overview 归队三处 core 行`）。

### Task 7: 产物重建 + 全套验证收尾

- [ ] **Step 1**：`cd frontend && npm run build`（normalize-eol LF）→ 产物单独提交（`build: 重建 pages/settings 产物`）。
- [ ] **Step 2**：全套终验——后端 pytest（含 no-drift）+ ruff + mypy、前端 vitest + typecheck 全绿；`git status` 干净。
- [ ] **Step 3**：报告基线净变数字（§5A 改写 + §5B 新增后的最终计数），供全分支终审。

## Self-Review

- Spec 覆盖：§3.1-3.6 → T1/T2/T5；§4.1-4.5 → T1/T3/T4；§5A/§5B → T1-T5 各步；§6 → T6；§7 恢复路径为文档性（常量注释 + spec，无任务）；§8 验收 → T7 + 终审。无缺口。
- 占位符扫描：核心代码全给出；§5A 清单在 spec 中带 file:line 与方向，plan 引用其执行（brief 会同时携带 spec 路径）。
- 类型一致：`upstream_unavailable(path)->bool`、`upstream_unavailable_group(group)->bool`、`unavailable?: boolean` 前后一致。
