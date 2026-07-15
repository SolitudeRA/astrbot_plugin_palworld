# 有条件模式互转 + 转移引导（Phase 2）设计

> 关联：本功能是「让运行模式选择变成有意识、被引导的动作」的 **Phase 2**，叠在 Phase 1 之上。
> Phase 1 已交付（同分支 feat/mode-separation）：`routing.setup_confirmed` + 命令闸 + 设置页首次引导屏
> （`docs/superpowers/specs/2026-07-15-mode-onboarding-gate-design.md`）。
> 前置更早：模式分道 v0.9.7（`world_mode`、`single_allowed_groups`、DB `group_servers` 绑定、`admin_audit`）。

## 1. 背景与目标

**痛点（用户确认）**：Phase 1 让用户首次有意识选模式，但**之后改模式**仍只能走 AstrBot 齿轮裸切——裸切 single↔multi 会**静默改变授权介质**、丢配置对应关系，用户无引导、无二次确认、无数据迁移。

**平台/数据现实（勘探结论，命门）**：
- 多世界群授权的**运行时真相在 DB `group_servers`（allowed=1）**，config `group_bindings` 只是启动一次性种子；单世界授权在 **config `single_allowed_groups`**。两者**跨介质**。
- Repository **无**"列全表绑定 / 列某 server 绑定"方法（全是 `WHERE umo=?`），前端也拿不到 DB 绑定（4 个 web 端点无一列绑定）——迁移**必须新增后端**。
- 服务器运行时数据几乎全以 `world_id` 为键（十余表），`server_id` 仅在 `servers`/`group_servers`/`worlds`；**无任何 server 级清数据方法**，删 config server 行只留 DB 孤儿——真删须新写 server 级 purge。
- 聊天二次确认 `ConfirmationStore`（sender_id 单槽、绑 `/pal confirm`、server 语义）**不宜复用**于 Web 页面的全局 config 变更——确认走前端自持对话框（Phase 1 `onConfirmMode` 先例）。

**目标**：在自定义设置页提供**有条件、带引导、带二次确认**的模式互转，保留原有授权（可选迁移）、可选真删其余服务器数据，全程审计。

**成功标准**：
- 用户可在设置页切换 single↔multi，经二次确认；restricted 下可选迁移授权保留原群访问、不静默锁人。
- 多台切单：告警 + 转移向导（选保留台 / 可选迁移 / 保留或真删其余）+ 强确认。
- 破坏性 purge 单点原子编排 + 审计；任何路径失败不留前后端半态。
- 齿轮裸切仍容忍（后端安全网不变）；未触碰多模式常规授权路径。

## 2. 非目标

- 不改 Phase 1 的首次设置闸 / 引导屏机制（转移不重置 `setup_confirmed`，恒保持 true）。
- 不引入聊天版模式切换命令；确认统一在 Web 设置页。
- 不拦截齿轮裸切（裸切仍是无引导的兜底，后端已有安全网：单模式多台就绪→告警+只用首台）。
- 不改多世界常规授权判定（`resolve` multi 分支查 DB `group_servers` 不变）。
- **版本号不变（保持 v0.9.7）**：Phase 2 不单独发版，随后续统一发版。

## 3. 术语

- **转移端点** `mode/transfer`：唯一后端入口，原子编排模式切换 + 可选迁移 + 可选 purge + 审计。
- **迁移授权**：跨介质搬运授权——multi→single 读 DB 绑定 umo 并入 config 名单；single→multi 读 config 名单写 DB 绑定。
- **保留台**：multi→single 时用户选中、成为单模式唯一服务器的那台（归位 `servers[0]`）。
- **server 级 purge**：解析某 server 的 world_id 集 → 逐表 DELETE 运行时数据 + 删 server/worlds/group_servers 行。
- **转移向导**：multi→single 多台时的前端多步向导（选台/迁移/保留删除/摘要+强确认）。

## 4. 架构

### 4.1 唯一后端入口：原子端点 `mode/transfer`

- 注册：`main.py._register_web_api` 加 `{p}/mode/transfer` POST → `_web_mode_transfer` → `web_api.handle_mode_transfer`。鉴权同 `config/save`（Dashboard 登录 `_has_identity`，未鉴权拒）。**不受 Phase 1 首次设置闸约束**（web 端点始终可达）。
- 载荷：`{ target_mode: "single"|"multi", surviving_server_id?: str, migrate_auth: bool, purge_others: bool }`。
- 破坏性操作**全程审计**（复用 `admin_audit` migration_0004）：kind `mode_transfer`，记 from/to 模式、保留台、迁移 umo 数、purge 的 server 及各表计数（userid 只 hash、沿现有审计规范；note-id 明文规范不变）。

**编排（单次后端操作，非 2PC——见 §4.4）**：
1. 校验载荷 + 鉴权；读当前 config（`self._raw_config` / parse）。
2. **迁移读在前**（purge 会删绑定，须先读）：
   - multi→single 且 `migrate_auth`：`umos = repo.list_bound_umos()` → 并入 config `single_allowed_groups`（去重，note「从多世界绑定迁移」）。
   - single→multi 且 `migrate_auth`：读 config `single_allowed_groups` 的 umo 集，**暂存**待步 5 写 DB。
3. 改 config：`world_mode = target_mode`；multi→single 把 `surviving_server_id` 对应行归位 `servers[0]`；`purge_others` 则从 config `servers` 移除其余行。`setup_confirmed` 保持 true。
4. 落库 + reload：复用 `_apply_and_restart`（`validate_and_backfill` + 重建 container）；失败走既有 `_rollback`、模式不变。
5. single→multi 迁移：`repo.bind_umos_to_server(umos, servers[0].server_id)`（reload 后新容器 repo）。
6. `purge_others`：对每个被移除 server `repo.purge_server_data(server_id)`。
7. 审计（记实际完成的迁移/purge 结果）。
8. 返回脱敏新 config（供前端 `applyConfig`）+ 回执摘要（迁移 N 群 / purge M 台及计数）。

### 4.2 互转矩阵

| 从→到 | 前端 UI | 后端 `mode/transfer` |
|---|---|---|
| single→multi | 二次确认框（restricted 含「迁移授权」勾选默认勾）| target=multi；migrate→config 名单 umo 写 DB 绑定（绑 servers[0]，allowed=1）|
| multi→single（1 台）| 二次确认框（同上迁移勾选）| target=single；migrate→DB 绑定 umo 集并入 config 名单；该台归位 servers[0] |
| multi→single（多台）| **告警 + 转移向导** + 强确认 | target=single；选保留台归位 servers[0]；migrate→DB umo 并入名单；purge_others→移除其余 config 行 + server 级 DB purge |

**迁移语义**：多世界"哪些群有权访问"= DB `group_servers.allowed=1` 全部 distinct umo（不分绑到哪台——单模式只剩一台，全并入名单保留访问）；反向把名单 umo 绑到 servers[0]。均去重、幂等。

**关键不变量**：切到 single 后**保留台必是生效单模式服务器**（后端 single 取 `_ready_servers()[0]`）——转移把保留台**归位 servers[0]**（删其余则它自然唯一）。就绪服务器为 0 时阻止切 single。

### 4.3 新增 Repository 方法（`sqlite_repository.py` + `Repository` 抽象）

- `list_bound_umos() -> list[str]`：`SELECT DISTINCT umo FROM group_servers WHERE allowed=1`。
- `bind_umos_to_server(umos, server_id) -> None`：批量置 `allowed=1`（复用/仿 `set_active` 的 upsert 语义；是否同时 active 由实现定，保底 allowed=1）。
- `purge_server_data(server_id) -> dict[str, int]`：`SELECT world_id FROM worlds WHERE server_id=?` → 对 world_id 键表（players/player_sessions/player_observations/guilds/palboxes/bases/base_observations/world_metrics/world_events/daily_aggregates/player_bindings/hidden_players）逐表 `DELETE WHERE world_id IN (…)` + 删 `group_servers`/`worlds`/`servers` 的 server_id 行；返回各表删除计数。空 world_id 集时只删 server/worlds/group_servers 行、不碰 world_id 表。

### 4.4 原子性诚实说明（用户已接受）

config 文件与 SQLite 是两个存储，无真 2PC。策略：**config 改动为主**（失败即 `_rollback`、模式不变、前端不改 state 无半态）；**purge 是 config 落库后的清理**（失败则审计记「部分完成」、回执告警"服务器已切换但 N 台数据清理失败，可稍后重试"，不回滚已切模式）。破坏性 purge 因此放最后、且前端**强确认在先**（§5）。

## 5. 前端组件（access 连接章）

- **模式切换控件**：把现只读 mode-badge（"切换请到齿轮"）升级为带切换入口——显示当前模式 + 「切换到 单/多 服务器」按钮，点击按当前模式 + 就绪服务器数派发下列 UI。齿轮仍留裸切兜底。
- **确认对话框组件**（single↔multi、multi→single 1 台）：显示目标模式；restricted 时列「迁移授权」勾选（默认勾，附"保留原有群访问"）；未迁移时告警"restricted 下切后需重新授权否则群无法查询"。确认→POST `mode/transfer`→`applyConfig(res.config)`+回执摘要 toast。
- **转移向导组件**（multi→single 多台）：步 ① 单选保留哪台（**仅就绪服务器**）；步 ② 「迁移授权」勾选；步 ③ 其余「保留 / 删除（含历史数据，破坏性）」二选一；末尾**摘要页**（保留台/迁移 N 群/删除 M 台及数据）+ 最终确认。
  - **删除侧额外强确认**（用户已定）：摘要页删除项**标红**列"将永久删除以下服务器及其全部历史数据，**不可恢复**" + **勾选闸**「我了解此操作不可恢复」——勾选前「确认删除并切换」按钮**禁用**（仿 Phase 1 点选前禁用范式）。保留数据侧无此额外闸。
- **失败不留半态**（复用 Phase 1 教训）：模式只在后端成功后经 `applyConfig(res.config)` 改变；端点失败→错误 toast、模式与页面不变（不乐观改 state）。

## 6. 错误处理 / 边界

- 非 2PC 失败处理见 §4.4。
- multi→single 保留台须就绪（向导只列就绪）；就绪服务器为 0 → 阻止切 single。
- 迁移源为空（无绑定/名单空）→ no-op 正常。`purge_server_data` world_id 集为空 → 只删 server/worlds/group_servers 行、零计数。
- 迁移幂等去重（集合语义）；purge 只作用被移除 server、不误伤保留台数据（测试须坐实隔离）。
- 并发：转移复用既有 busy/在途门闩（`_apply_and_restart`/`_guarded`），重载中回 busy。
- `setup_confirmed` 贯穿转移保持 true；`mode/transfer` 不受首次设置闸约束。
- restricted 切 single 未迁移 → 确认框告警 + 既有空名单启动告警兜底。

## 7. 测试策略

- **后端 Repository**：`list_bound_umos`（distinct + 排除 allowed=0）；`bind_umos_to_server`（批量 allowed=1）；`purge_server_data`（跨表 seed→purge 后 world_id 行/server/worlds/group_servers 全清 + 计数正确 + 空 world_id 集 + **保留台数据隔离不受损**）。
- **端点编排** `handle_mode_transfer`：三类互转 × 迁移开关 × 保留/删除，断言 config（world_mode/保留台归位 servers[0]/名单并入/servers 增删）+ DB（绑定写入/purge 生效）+ 审计写入（kind mode_transfer）+ `_has_identity` 鉴权（未鉴权拒）+ 失败回滚（模式不变）。
- **前端**：模式切换控件按模式渲染并开对应流；确认框（restricted 迁移勾选默认勾、未迁移告警、POST 载荷、错误→模式不变）；转移向导（选台/迁移/保留删除、**删除侧勾选闸禁用逻辑**、摘要、POST 载荷、错误→模式不变）。
- 无新命令锚定（`mode/transfer` 是 web 端点、非 `/pal` 命令）。前端改源后 `npm run build` 保 no-drift。

## 8. 锚定 / 约束（沿用项目铁律）

- 相对导入红线；提交不出现 Claude；前端 build no-drift + LF。
- README/docs 改中文用词须核 `readme_test.py` 锚点。
- **版本号不变（v0.9.7）**——不动任何版本源/断言。
- 审计沿 `admin_audit` 规范（userid hash、留存 `audit_retention_days` 折进现有 prune）。

## 9. 依赖顺序 / 风险

- 依赖顺序：Repository 三方法（含 purge，先测透）→ `mode/transfer` 端点编排（含审计/鉴权/回滚）→ 前端模式切换控件 + 确认框 + 转移向导 → 文档 + 终检。
- **头号风险（purge 正确性 + 隔离）**：server 级 purge 跨十余表全新写，须充分测（漏表=孤儿滞留；误删=打到保留台数据）。world_id 解析须精确按 `worlds.server_id`。
- **次风险（非 2PC 部分失败）**：purge 失败但模式已切 → 审计+回执必须如实告警，不假装成功。
- **迁移方向易错**：multi→single 读 DB 写 config、single→multi 读 config 写 DB，两向别写反。
- **保留台归位**：切 single 后 `_ready_servers()[0]` 必须是保留台，否则用错服务器——归位 servers[0] 是硬约束、须测。
