# 有条件模式互转 + 转移引导（Phase 2）设计

> 关联：本功能是「让运行模式选择变成有意识、被引导的动作」的 **Phase 2**，叠在 Phase 1 之上。
> Phase 1 已交付（同分支 feat/mode-separation）：`routing.setup_confirmed` + 命令闸 + 设置页首次引导屏
> （`docs/superpowers/specs/2026-07-15-mode-onboarding-gate-design.md`）。
> 前置更早：模式分道 v0.9.7（`world_mode`、`single_allowed_groups`、DB `group_servers` 绑定、`admin_audit`）。
>
> 本稿是**重写版**：折入一轮对抗复核（verdict=needs-rework，26 确认发现）+ 3 个用户决策。
> 破坏性核心（§4/§5/§6/§7）全部重写，§1-3/§8/§9 保留骨架并订正。本功能是**破坏性、不可逆**
> 操作（server 级 DB purge + 跨介质授权迁移），设计准确性优先于篇幅。

## 1. 背景与目标

**痛点（用户确认）**：Phase 1 让用户首次有意识选模式，但**之后改模式**仍只能走 AstrBot 齿轮裸切——裸切 single↔multi 会**静默改变授权介质**、丢配置对应关系，用户无引导、无二次确认、无数据迁移。

**平台/数据现实（勘探结论 + 复核确证的代码事实，命门）**：
- 多世界群授权的**运行时真相在 DB `group_servers`（allowed=1）**（`sqlite_repository.py:106` `get_allowed`：`SELECT server_id FROM group_servers WHERE umo=? AND allowed=1`）；config `group_bindings` 只是**启动一次性种子**（`container.py:102` `seed_bindings`，seed-only：`sqlite_repository.py:58-86` 已存在行绝不覆盖 allowed/active）；单世界授权在**顶层** config `single_allowed_groups`。两者**跨介质**。
- `single_allowed_groups` 是**顶层 config 键、非 routing 子键**：`config.py:451` 的 `_parse_single_allowed_groups(raw)` 读 `raw['single_allowed_groups']`（`config.py:304`），而 `world_mode` 读 `raw['routing']['world_mode']`（`config.py:450`）。`config_view.py:42-47` 的 `_TOP_KEYS` 也把 `single_allowed_groups` 与 `routing` 并列为顶层。运行时经 `RoutingConfig.single_allowed_groups` 字段读，但**存储真相是顶层**。
- Repository **无**「列全表绑定 / 列某 server 绑定 / 清全表绑定 / 列孤儿 server」方法（现有绑定读全是 `WHERE umo=?`：`get_allowed`/`get_binding_active`/`list_group_servers`），前端也拿不到 DB 绑定（4 个 web 端点无一列绑定）——迁移**必须新增后端**（§4.3）。
- 服务器运行时数据几乎全以 `world_id` 为键（12 张表，见 §4.3 purge 表清单）；`server_id` 仅在 `servers`/`group_servers`/`worlds`；**无任何 server 级清数据方法**，删 config server 行只留 DB 孤儿——真删须新写 server 级 purge。
- `_apply_and_restart`（`main.py:259-294`）**不持任何锁**、只置 `_restarting` 标志（对读路径 advisory）；真写锁是 `_save_lock`（`main.py:131`），目前仅 `config/save` 用它串行化（`web_api.py:41-45`）。`_apply_and_restart` 用**整键替换** `self._raw_config[k]=v`（`main.py:263-264`）、并在改动**之前**深拷贝 `old_raw` 作回滚快照（`main.py:260`）；它调 `parse_config`、**不调** `validate_and_backfill`（后者只在 `handle_config_save` 里，`web_api.py:46`）。
- 聊天二次确认 `ConfirmationStore`（sender_id 单槽、绑 `/pal confirm`、server 语义）**不宜复用**于 Web 页面的全局 config 变更——确认走前端自持对话框（Phase 1 `onConfirmMode` 先例）。

**目标**：在自定义设置页提供**有条件、带引导、带二次确认**的模式互转；授权**按管理员显式选择迁移**（不静默扩权）；转移采用 **move 语义**（迁移后清空源介质，切回不复活）；可选真删其余服务器数据（server 级 purge）；全程审计；孤儿数据有清理入口。

**成功标准**：
- 用户可在设置页切换 single↔multi，经二次确认；restricted 下可按预览列表显式勾选迁移哪些群、默认只保留既有权限（最小权限）、不静默锁人也不静默扩权。
- 多台切单：告警 + 转移向导（选保留台 / 显式勾选迁移群 / 保留或真删其余）+ 强确认。
- 破坏性 purge 单点原子编排（全程持 `_save_lock`）+ 全路径审计；任何失败都不留前后端半态、不留静默失锁。
- 齿轮裸切仍容忍（后端安全网不变）；未触碰多模式常规授权路径。

## 2. 非目标

- 不改 Phase 1 的首次设置闸 / 引导屏机制（转移不重置 `setup_confirmed`，恒保持 true；此恒真不构成安全绕过，复核已确认，不作为缺陷处理）。
- 不引入聊天版模式切换命令；确认统一在 Web 设置页。
- 不拦截齿轮裸切（裸切仍是无引导的兜底，后端已有安全网：单模式多台就绪→告警+只用首台，`routing_service.py:55-61`）。
- 不改多世界常规授权判定（`resolve` multi 分支查 DB `group_servers` 不变，`routing_service.py:64-103`）。
- **鉴权不加严**：转移/预览/孤儿清理端点鉴权与 `config/save` **同级**（Dashboard 登录 `_has_identity`，`main.py:328-333`）。复核已驳回「破坏性操作须 `permission_admins` 更严鉴权」的主张（2 验证者：同级足够，config/save 本身已能改整份配置）。
- **版本号不变（保持 v0.9.7）**：Phase 2 不单独发版，随后续统一发版。

## 3. 术语

- **预览端点** `mode/transfer/preview`（GET，只读）：转移前拉取真实源集，供向导渲染可迁移群列表与就绪台候选（决策 1）。不改任何状态。
- **转移端点** `mode/transfer`（POST，写）：原子编排模式切换 + 显式授权迁移 + move 清源 + 可选 purge + 审计。全程持 `_save_lock`。
- **孤儿清理端点** `mode/orphans`（GET 列 / `mode/orphans/purge` POST 清）：清理 config 已无对应但 DB 仍残留的 server 数据（决策 3），让「purge 失败可稍后重试」成真。
- **move 迁移语义**（决策 2，非「copy/搬运」）：授权从源介质**迁到**目标介质后，**源被消费（清空）**。
  - multi→single：读 DB `group_servers` 的选中 umo → 写入顶层 config `single_allowed_groups`，随后**清空全部 DB `group_servers`**。
  - single→multi：读 config `single_allowed_groups` 的选中 umo → 写入 DB `group_servers`（绑生效就绪台），随后**清空全部 config `single_allowed_groups`**。
  - move 保证：切回原模式不会从残留的源介质**复活**旧授权（fail-open 防线）。
- **保留台**：multi→single 时管理员选中、成为单模式唯一就绪服务器的那台（候选**仅限当前就绪服务器**；转移把它**归位** `servers[0]`）。
- **生效就绪台**：单模式下 `resolve` 恒取的服务器 = `routing._ready_servers()[0]`（`routing_service.py:47-62`）。single→multi 迁移的 DB 绑定目标就是**reload 前**捕获的这台（§4.1，B2）。
- **server 级 purge**：解析某 server 的 `world_id` 集 → 逐表 DELETE 运行时数据 + 删 `servers`/`worlds`/`group_servers` 的 server_id 行。单台一个 `write_tx`。
- **转移向导**：multi→single 多台时的前端多步向导（选台 / 显式勾选迁移群 / 保留删除 / 摘要+强确认）。

## 4. 架构

### 4.1 两个后端端点：只读预览 + 原子转移

注册（`main.py._register_web_api`，与现有 4 端点并列）：
- `{p}/mode/transfer/preview` GET → `_web_mode_transfer_preview` → `web_api.handle_mode_transfer_preview`。
- `{p}/mode/transfer` POST → `_web_mode_transfer` → `web_api.handle_mode_transfer`。
- `{p}/mode/orphans` GET → `_web_orphans_list` → `web_api.handle_orphans_list`（§4.4）。
- `{p}/mode/orphans/purge` POST → `_web_orphans_purge` → `web_api.handle_orphans_purge`（§4.4）。

四端点鉴权同 `config/save`（`_has_identity`，`main.py:328-333`；未鉴权→`_deny_unauthorized`）。**不受 Phase 1 首次设置闸约束**（web 端点始终可达）。业务成败一律 HTTP 200、用 `payload['ok']` 区分（沿 `web_api.py` 范式）。

#### 4.1.1 预览端点 `mode/transfer/preview`（GET，只读，决策 1）

只读、走既有在途门闩（`_inflight`/`_idle`，镜像 `_web_status`/`_web_audit`）；`container is None` 或 `_restarting` → `{ok:True, restarting:True}` 空载。返回**当前真实源集**，供向导据以渲染、不信客户端凭空构造：

- **multi→single**（`?target=single`）：
  - `ready_servers`: `[{server_id, name}]` = 当前就绪服务器（保留台候选**权威源**，前端**不得**从脱敏 config 推断 ready——密码已抹）。来源 `container.config.servers` 中 `s.ready` 者。
  - `bindings`: `[{umo, server_ids:[...]}]` = 由 `repo.list_allowed_bindings()`（`allowed=1` 的 `(umo, server_id)` 对）按 umo 聚合。向导据此：管理员选定保留台后，对每个 umo 标注**已有权**（保留台 ∈ 其 `server_ids`）或**将获新权**（保留台 ∉ 其 `server_ids`）；默认勾**最小权限集**=「已有权」的 umo（保留既有访问、不默认扩权，M1），「将获新权」默认不勾、管理员可手动勾选扩权。
- **single→multi**（`?target=multi`）：源群来自顶层 config `single_allowed_groups`，**前端 state 已持有**（`collect.ts:14-16,81` 无条件往返，含 multi 模式），故**可不走预览端点**；`ready_servers` 仍可复用本端点或 `status/overview`（供确认框判断是否有可绑目标）。

#### 4.1.2 转移端点 `mode/transfer`（POST，写）—— 原子编排

**载荷**（决策 1：迁移范围改为显式子集 `migrate_umos: string[]`，取代旧 `migrate_auth: bool`）：

```
{ target_mode: "single" | "multi",
  surviving_server_id?: str,     // 仅 multi→single 必填
  migrate_umos: string[],        // 管理员显式勾选的迁移群（可空=不迁移）
  purge_others: bool }           // 仅 multi→single 多台有意义
```

**编排（单次后端操作，非 2PC——见 §4.4；全程持 `_save_lock`，B4）**。步序**不可重排**，尤其「迁移读必须先于 reload」「reload 失败即中止」「审计做最外层」：

0. **入口串行门（B4，显式点名 `self._save_lock`）**：
   - `if self._save_lock.locked(): return 200, {"ok":False,"error":"transfer_in_progress"}`（拒 busy，不排队）。
   - `async with self._save_lock:` **包裹整个编排**（迁移读 + 候选构造 + `_apply_and_restart` + post-reload DB 写 + purge + 审计），使 purge 落在锁内 / 容器就绪窗口，不与并发 `config/save` 或另一转移竞争。
   - 读 `container.repo`/`container.routing` 前先查 `_busy_msg()`（`main.py:191-194`）与 `container is None`：重载中 → `{"ok":False,"error":"busy"}`，零状态变更。
   - `_apply_and_restart` 本身不再夺锁、只置 `_restarting`，故在持锁上下文里调它安全、无死锁（它是 `config/save` 持锁时的既有调用姿势）。

1. **校验载荷 + 鉴权**（鉴权已在 Star 层 `_has_identity`）。`target_mode ∈ {single,multi}`，与当前模式不同（同模式→`no_change`）。

2. **校验保留台与就绪台（B1 / B2）——在任何 config 改动 / DB 写 / purge 之前**：
   - **multi→single**：`surviving_server_id` 必须经 `routing._ready_by_name(surviving_server_id)`（`routing_service.py:29-33`，只在就绪集内匹配）解析到一台当前**就绪**服务器；否则拒 `{"ok":False,"error":"invalid_surviving"}`（审计 rejected、success=0、**零状态变更**）。就绪台数 `== 0` → 拒 `{"error":"no_ready_server"}`（不得切 single）。
   - **single→multi**：若 `migrate_umos` 非空，须 `len(routing._ready_servers()) >= 1`，否则拒 `{"error":"no_ready_target"}`（无台可绑）。捕获 `target_server_id = routing._ready_servers()[0].server_id`——**reload 前的生效单模式服务器**（B2：不是 reload 后的 `servers[0]`；非就绪台排在前时二者背离=迁移做反，`servers` 空时 `[0]` IndexError 半态）。

3. **迁移读（必须先于第 4 步 reload，硬约束）**：reload 中 `cleanup_orphan_bindings(ready_ids)`（`container.py:104`）会删掉被移除 server 的 `group_servers` 行，purge 的 `group_servers` DELETE 只是幂等兜底（count 可能已为 0）。故所有源读取在 reload 前完成、结果**捕获进内存**：
   - **multi→single**：`pairs = repo.list_allowed_bindings()` → `source_umos = {umo for umo,_ in pairs}`。**校验 `set(migrate_umos) ⊆ source_umos`**（决策 1，不信客户端）；不满足（客户端篡改 / 预览后源变化）→ 拒 `{"error":"invalid_migrate_umos"}`（对破坏性不可逆操作 fail-closed，令管理员重取预览后重试）。捕获保留台 `name`（供审计 `server_name`）。计算 **purge 删除集（显式，B1）**：`purge_set = {s.server_id for s in ready_servers} − {surviving_server_id}`（不靠「移除其余」泛指）。
   - **single→multi**：源 = 当前 config `single_allowed_groups` 的 umo 集（`{e.umo for e in container.config.routing.single_allowed_groups}`）。**校验 `set(migrate_umos) ⊆ source_umos`**，不满足→拒 `invalid_migrate_umos`。`migrate_umos` 已在内存，无需 DB 读。

4. **候选构造（M8：深拷贝原地改，绝不预改 `self._raw_config`、绝不经 redact/parse 重建）**：
   - `candidate = copy.deepcopy(dict(get_raw()))`——**完整**顶层快照（所有键在场），逐字保留 `routing`（`access_mode`/`default_server`/`setup_confirmed`）与 `servers` 行**逐字**（含明文 `password`/`password_env`）。**理由（M8）**：`_apply_and_restart` 整键替换 `self._raw_config[k]=v`——若给最小候选（仅 `routing={world_mode}`）会**静默重置** `access_mode→restricted`（`config.py:448`）、`default_server→''`（`config.py:449`）；若从 `redact_config` 视图重建 servers 会**丢明文密码**（`config_view.py:100-103` 抹密码），保留台变不就绪→0 就绪 single。给**完整深拷贝**故所有未改键原样回写、无静默漂移。
   - 原地改字段：
     - `candidate['routing']['world_mode'] = target_mode`（`world_mode` 在 routing 子键，`config.py:450`）。`setup_confirmed` 保持 true（不动）。
     - **multi→single**：把 `surviving_server_id` 对应行**归位** `candidate['servers'][0]`（按 `name==surviving_server_id` 定位后移到索引 0）。`migrate_umos` 并入**顶层** `candidate['single_allowed_groups']`（M7：**不是** `candidate['routing']['single_allowed_groups']`——写进 routing 会过 schema 校验但 `parse_config` 永不读→迁移静默丢失→restricted single 空名单锁全群）：按 umo **去重合并**（已存在 umo 保留原 note；新 umo 加 note「从多世界绑定迁移」），并**自校** 行形 `{umo, note}` 与总量 `≤ 200`（`_MAX_LIST`，`config_view.py:55`；本端点绕过 `validate_and_backfill` 的形/量校验，须自守）。`purge_others=True` 时：`candidate['servers']` 仅留保留台行；并删 `candidate['group_bindings']` 中 `server ∈ purge_set` 的种子行（否则切回 multi 时 `seed_bindings` 复活=第二复活向量，Minor）。
     - **single→multi**：`candidate['single_allowed_groups'] = []`（决策 2 move 清源：写 DB 前先在候选里清空 config 名单；随 reload 落库，切回 single 不复活）。
   - **绝不预改 `self._raw_config`**（M8c）：`_apply_and_restart` 在改动前深拷贝 `old_raw`（`main.py:260`），预改会污染其回滚快照。只改 `candidate`。

5. **落库 + reload**：`outcome = await self._apply_and_restart(candidate)`（`validate_and_backfill` **不在**此步——那是 `config/save` 的事，M8a）。`_apply_and_restart` 内部：整键替换→`save_config()`→`parse_config`→重建 container；失败走既有 `_rollback` 并返回 `{"ok":False,...}`、**不抛异常**。
   - **reload 失败即中止（M5）**：`if not outcome.get("ok"):` → **立即中止**：不做 post-reload DB 写、不 purge、不 clear 源；审计 success=0（config 已回滚、DB 完全未动）；`return 200, outcome`（把 `restart_failed_rolled_back` 透传前端，模式不变）。**否则** config 已回滚却仍 purge=删了数据但模式没切。

6. **post-reload DB 写（reload ok 后，用新容器 `self._container.repo`）**：
   - **single→multi 绑定**：`try: repo.bind_umos_to_server(migrate_umos, target_server_id)`（绑到**第 2 步捕获的生效就绪台**，B2）。`bind_umos_to_server` 语义见 §4.3/M3（`allowed=1`；仅当该 umo 无既有 active 行时才置 `active=1`）。
     - **绑定失败处理（B3，禁止静默逃逸）**：`except Exception:` → 保持已切换的模式（不回滚——reload 已成功、回滚成本/风险高），审计 success=0、migrated=0、记 error；回执带**可执行**告知「模式已切到 multi，但授权迁移失败，restricted 群可能失访，请重新迁移或用 `/pal link` 手动绑定」；返回 `{"ok":True, "config":…, "warnings":{"migration_failed":True,…}}`（`ok:True` 使前端 `applyConfig` 与后端已切模式对齐、避免半态，Phase 1 教训；`warnings` 让前端弹告警）。
   - **multi→single move 清源（决策 2）**：`repo.clear_all_group_servers()`（清空全部 DB `group_servers`——含保留台的行；单模式读走 `single_allowed_groups`、`group_servers` 不再参与，清空防切回 multi 复活）。
   - **multi→single purge（`purge_others=True`）**：对 `purge_set` 每个 `server_id` 调 `repo.purge_server_data(server_id)`（§4.3，单台一个 `write_tx`）；单台失败**记该 server_id + 异常**、继续下一台（不中断、不回滚已切模式）。累加各表计数入回执/审计。

7. **审计（最外层，M6）——包在 `finally` / 覆盖全部退出分支**：现有实现把审计列在 purge 之后（若 purge 抛异常 / reload 早返回则**完全无审计**，违 §4.4 承诺）。改为：编排入口设 `success`/`migrated`/`purge_counts`/`failed_server_ids`/`error` 累加变量，退出时（`finally` 或每个 `return` 前统一）写一条审计，覆盖**拒绝 / reload 回滚 / bind 失败 / purge 部分失败 / 全成功**五类。**字段定义（M6，复核确证）**：
   - `admin_id = self._current_username()`（Dashboard 登录用户名，`main.py:319-326`）——**明文存**（`admin_audit.admin_id` 列现有语义即明文，`admin_service.py:98` 直传不 hash；`config_view.py:329` 审计视图直接回显 `admin`）。spec 早稿照搬的「userid 只 hash」样板对本 web 场景**错误**，已删。
   - `action = "mode_transfer"`。
   - `server_name`（列 `NOT NULL`，`migrations.py:248`；`None` 会 IntegrityError）= 保留台名（multi→single）/ 绑定目标台名（single→multi）/ 非空哨兵 `"mode_transfer"`（皆无时）。
   - `target_name = None` / `target_hash = None`（本操作无单个玩家目标）。
   - `detail`（JSON 文本）：`from`/`to`/`surviving`/`migrated`(数)/`purged`(server→各表计数)/`failed_server_ids`/`cleared_group_servers`/`cleared_single_allowed`。**注**：`audit_rows`（`config_view.py:316-334`）不下发 `detail`，故这些结构化计数**仅 DB 留存**（供事后核查 / 重建），前端审计页只见 action/server/admin/success/error（记账已明确）。
   - `success = 1` 当且仅当 reload ok **且**（single→multi 时）bind 未抛。purge 部分失败 → `success=1`、`error` 摘要失败台、`failed_server_ids` 落 detail（cleanup「可稍后重试」，走 §4.4 孤儿清理）。
   - `error`：拒绝原因 / reload 失败码 / bind 异常 / purge 失败摘要（非成功分支非空）。
   - **审计所用 repo**：取当前活容器 `self._container.repo`（reload ok 后=新容器；回滚后=旧容器；`_rollback` 二次失败 `container=None` 的灾难分支无 repo 可写、审计写不成，此时响应 `restart_failed` 已如实示警——记账为已知边界）。

8. **返回**：脱敏新 config（`redact_config(get_raw())`，供前端 `applyConfig`）+ 回执摘要（`from→to`/保留台/迁移 N 群/purge M 台及各表计数/purge 失败台/迁移失败标志）。

### 4.2 互转矩阵

| 从→到 | 前端 UI | 后端 `mode/transfer`（要点） |
|---|---|---|
| single→multi | 二次确认框（restricted 时列 `single_allowed_groups` 群、默认全勾迁移，可取消）| target=multi；校验 `migrate_umos ⊆ 名单`；候选清空顶层 `single_allowed_groups`（move 清源）+ world_mode=multi；reload ok 后 `bind_umos_to_server(migrate_umos, 生效就绪台)`；无 purge |
| multi→single（1 台）| 二次确认框（拉 preview 列绑定群、默认勾「已有保留台权限」的、可改）| target=single；校验 surviving 就绪 + `migrate_umos ⊆ DB 绑定 umo`；候选把该台归位 `servers[0]` + `migrate_umos` 并入顶层 `single_allowed_groups`；reload ok 后 `clear_all_group_servers()`；无 purge（未删台）|
| multi→single（多台）| **告警 + 转移向导**（步①选就绪保留台→步② preview 勾迁移群[已有权默认勾/将获新权默认不勾]→步③其余保留/删除→摘要+强确认）| 同上 + `purge_others=True`：候选仅留保留台 servers 行 + 删指向 purge_set 的 group_bindings 种子行；reload ok 后 `clear_all_group_servers()` + 对 `purge_set={就绪台}−{surviving}` 每台 `purge_server_data`（单台 write_tx、失败记录续跑）|

**迁移语义（决策 1 + 决策 2，M1/M2）**：迁移范围=**管理员显式勾选**的 `migrate_umos`（非自动全并入、非自动最小），后端校验 ⊆ 真实源；向导对 multi→single 默认只勾「已有保留台权限」的群（保留、不扩权），对将获新权的群显式标注、默认不勾。迁移是 **move**：写目标介质后清空源介质（multi→single 清 DB `group_servers`；single→multi 清 config `single_allowed_groups`），切回原模式不复活。均按集合去重、幂等。

**关键不变量**：切到 single 后**保留台必是生效单模式服务器**（`routing._ready_servers()[0]`）——转移把保留台**归位 `servers[0]`**（删其余则它自然唯一；不删其余则它排首台）。就绪服务器 `==0` 时阻止切 single（B1）。single→multi 绑定目标恒为 **reload 前**捕获的 `_ready_servers()[0]`（B2）。

### 4.3 新增 Repository 方法（`sqlite_repository.py` + `Repository` 抽象）

- `list_allowed_bindings() -> list[tuple[str, str]]`：`SELECT umo, server_id FROM group_servers WHERE allowed=1`。供预览端点聚合（每 umo 绑到哪些 server_id）+ multi→single 迁移的**真实源集**（distinct umo）与 `migrate_umos ⊆ 源` 校验。
- `bind_umos_to_server(umos: list[str], server_id: str) -> None`（M3，镜像 `seed_bindings` seed-only-active + `set_active` clear-then-set 的 one-active-per-umo 不变量）：单 `write_tx` 内对每个 umo：`INSERT … (umo, server_id, allowed=1, active=?) ON CONFLICT(umo,server_id) DO UPDATE SET allowed=1`（**保底 `allowed=1`**）；`active` 置法——**仅当该 umo 尚无任何 `active=1` 行**时（`SELECT 1 FROM group_servers WHERE umo=? AND active=1 LIMIT 1`）才对本行置 `active=1`，否则 `active` 不动。保 `get_binding_active`（`LIMIT 1`，`sqlite_repository.py:99-104`）依赖的每 umo ≤1 active。单台目标经 resolve unique-ready 路径（`routing_service.py:97-100`）本可不靠 active，但 pin 使 >1 就绪台时也能命中 step2 active 绑定或提示 `/pal link`。
- `purge_server_data(server_id: str) -> dict[str, int]`：`SELECT world_id FROM worlds WHERE server_id=?` → 对 **12 张 world_id 键表**逐表 `DELETE WHERE world_id IN (…)`：`players` / `player_sessions` / `player_observations` / `guilds` / `palboxes` / `bases` / `base_observations` / `world_metrics` / `world_events` / `daily_aggregates` / `player_bindings` / `hidden_players`（对照 `migrations.py` 建表：这 12 张是全部 world_id 键表；`unknown_classes` 是全局类字典、非 per-server、**不碰**）→ 再删 `group_servers`/`worlds`/`servers` 的 `server_id` 行。**单台一个 `write_tx`**（`database.py:64-73`：SELECT→逐表 DELETE→删三张 server 行，一并 commit；任何 DELETE 抛错整台回滚）。返回各表删除计数。空 world_id 集时只删三张 server 行、world_id 表零计数（非就绪 / 从未轮询台）。
- `clear_all_group_servers() -> int`（决策 2，multi→single move 清源）：`DELETE FROM group_servers` 全表，返回删除行数。
- `list_orphan_server_ids(valid_server_ids: set[str]) -> list[str]`（决策 3）：DB 中出现但不在 `valid_server_ids` 的 server_id——`SELECT DISTINCT server_id FROM servers`（并集 `worlds`/`group_servers` 的 distinct server_id，兜全介质残留）`WHERE server_id NOT IN valid`。供孤儿清理端点列待清台。

### 4.4 原子性诚实说明 + 失败处理矩阵（用户已接受）

config 文件与 SQLite 是两个存储、无真 2PC。策略：**config 改动为主**（`_apply_and_restart` 失败即 `_rollback`、模式不变、DB 完全未动、前端不改 state 无半态）；**post-reload 的 DB 写（bind / clear / purge）是切换成功后的清理**，其失败**不回滚已切模式**，改为如实审计 + 可执行回执。破坏性 purge 因此放最后、全程持 `_save_lock`、且前端**强确认在先**（§5）。

失败处理矩阵（每格都写审计、见 §4.1 步 7）：

| 失败点 | 已发生的状态变更 | 处理 | 审计 | 前端回执 |
|---|---|---|---|---|
| 校验 surviving（B1）| 无 | 拒 `invalid_surviving`，零变更 | success=0，error=invalid_surviving | 错误 toast，模式/页面不变 |
| 校验 `migrate_umos⊄源` | 无 | 拒 `invalid_migrate_umos`，零变更 | success=0 | 提示重取预览后重试 |
| 就绪台=0 / 无绑定目标 | 无 | 拒 `no_ready_server` / `no_ready_target` | success=0 | 错误 toast |
| reload 失败（M5）| config 已回滚、DB 未动 | 立即中止，不 bind/clear/purge | success=0，error=restart_failed_rolled_back | 透传错误，模式不变 |
| bind 失败（B3）| 模式已切、DB 未绑 | 保持切换，不静默逃逸 | success=0，migrated=0，记 error | `ok:True`+applyConfig+告警「迁移失败，请重迁移或 /pal link」 |
| purge 部分失败 | 模式已切、授权已迁、部分台残留 | 记失败台，续跑，不回滚 | success=1，error=失败台摘要，failed_server_ids 入 detail | `ok:True`+applyConfig+「N 台数据清理失败，可到孤儿清理稍后重试」|
| 全成功 | 全部完成 | — | success=1 | `ok:True`+applyConfig+回执摘要 |

**孤儿清理端点（决策 3，让「可稍后重试」成真）**：
- `mode/orphans` GET（`handle_orphans_list`）：`valid = {s.server_id for s in container.config.servers}`；返回 `repo.list_orphan_server_ids(valid)`（DB 残留但 config 已无的台）。只读、走在途门闩。
- `mode/orphans/purge` POST（`handle_orphans_purge`）：持 `_save_lock`（写）；对每个当前孤儿 `server_id` 调 `purge_server_data`，单台 write_tx、失败记录续跑；审计 `action="orphan_purge"`（`admin_id` 明文、`server_name` 逐台名或哨兵、`detail` 各表计数、`success`/`failed_server_ids`）；返回清理结果。
- **说明**：既有 `cleanup_orphan_bindings`（`sqlite_repository.py:88-97`）只回收 `group_servers` 孤儿、`prune`（`sqlite_repository.py:275-307`）只回收 `player_bindings`/`hidden_players` 的 world 孤儿——二者都**不**回收 `worlds`/`players`/…等 world_id 数据孤儿；server 级残留必须由本孤儿清理端点用 `purge_server_data` 显式回收（M4）。

## 5. 前端组件（access 连接章）

- **模式切换控件**：把现只读 mode-badge（"切换请到齿轮"）升级为带切换入口——显示当前模式 + 「切换到 单/多 服务器」按钮，点击按当前模式 + 就绪服务器数派发下列 UI。齿轮仍留裸切兜底。
- **确认对话框组件**（single↔multi、multi→single 1 台）：显示目标模式；restricted 时列可迁移群勾选清单——
  - single→multi：清单来自前端 state 的 `single_allowed_groups`（`collect.ts:14-16`），默认全勾（皆为保留、绑到唯一就绪台）；
  - multi→single（1 台）：拉 `mode/transfer/preview?target=single` 得 `bindings`，对每 umo 标注「已有保留台权限（默认勾）/ 将获新权（默认不勾）」，管理员可改；
  - 未勾任何群时告警"restricted 下未迁移，切后相关群需重新授权否则无法查询"。
  - 确认→POST `mode/transfer`（载荷含 `migrate_umos`=勾选集）→`applyConfig(res.config)`+回执摘要 toast；`res.warnings.migration_failed` 时弹迁移失败告警。
- **转移向导组件**（multi→single 多台）：先拉 `mode/transfer/preview?target=single`。步 ① 单选保留哪台（**仅 `ready_servers`**，权威源来自预览、非脱敏 config）；步 ② 据 `bindings`+已选保留台渲染迁移群清单（已有权默认勾 / 将获新权默认不勾、可改）；步 ③ 其余「保留 / 删除（含历史数据，破坏性）」二选一；末尾**摘要页**（保留台 / 迁移 N 群，其中含 X 个「新授权」/ 删除 M 台及数据）+ 最终确认。
  - **删除侧额外强确认（用户已定）**：摘要页删除项**标红**列"将永久删除以下服务器及其全部历史数据，**不可恢复**" + **勾选闸**「我了解此操作不可恢复」——勾选前「确认删除并切换」按钮**禁用**（仿 Phase 1 点选前禁用范式）。保留数据侧无此额外闸。
- **孤儿清理入口（决策 3）**：连接章（或维护小节）提供只读列表（GET `mode/orphans`）+「清理残留数据」按钮（POST `mode/orphans/purge`，同样破坏性、带二次确认）。用于 purge 部分失败后的重试。
- **失败不留半态（复用 Phase 1 教训）**：模式只在后端成功后经 `applyConfig(res.config)` 改变；端点失败（`ok:False`）→错误 toast、模式与页面不变（不乐观改 state）。bind 失败 / purge 部分失败返回 `ok:True`（模式确已切、必须 applyConfig 对齐后端），但附 `warnings` 弹告警——不是「假装成功」而是「模式已切+清理未尽如实告知」。

## 6. 错误处理 / 边界

- 非 2PC 失败处理见 §4.4 矩阵；所有分支都落审计。
- **业务错误码**（`payload.error`，皆 HTTP 200）：`transfer_in_progress` / `busy` / `no_change` / `invalid_surviving` / `no_ready_server` / `no_ready_target` / `invalid_migrate_umos` / `restart_failed_rolled_back`（透传 `_apply_and_restart`）/ `restart_failed`（回滚二次失败）。
- multi→single 保留台须就绪（向导只列就绪；后端 B1 复核）；就绪服务器 `==0` → 阻止切 single。
- single→multi 有 `migrate_umos` 但就绪台 `==0` → 阻止（无台可绑，B2）。
- 迁移源为空（`migrate_umos=[]`）→ 正常 no-op 切换（仅 world_mode + 清源，不 bind/不并入名单）。`purge_server_data` world_id 集为空 → 只删三张 server 行、零计数。
- `migrate_umos` 须 ⊆ 真实源集（不信客户端）；越集即拒（决策 1）。
- 迁移幂等去重（集合语义）；候选 `single_allowed_groups` 自守 `{umo,note}` 行形 + `≤200`（绕过 `validate_and_backfill` 的自校，Minor）。
- purge 只作用 `purge_set`（`{就绪台}−{surviving}`）、不误伤保留台数据（测试须坐实隔离）。
- **并发**：入口 `_save_lock.locked()` 拒 busy；整编排持 `_save_lock`（B4），与 `config/save`/另一转移/孤儿清理互斥；读 container 前查 `_busy_msg()`/container-None。
- 转移基于**最后保存的 config**：前端应先保存或脏时警告（转移直接读 `self._raw_config`，未落盘的编辑不会进候选）。
- `setup_confirmed` 贯穿转移保持 true；四端点不受首次设置闸约束。
- restricted 切 single 未迁移 → 确认框告警 + 既有空名单启动告警兜底（`main.py:157-162`）。
- 非就绪 / 从未轮询台被删：`purge_set` 只含就绪台，故非就绪被删台的 DB `servers` 裸行成孤儿 → 由孤儿清理端点扫除（决策 3；其无 world_id 数据、残留仅一行 servers/可能 group_servers，已被 `clear_all_group_servers` 清）。

## 7. 测试策略

- **后端 Repository**：
  - `list_allowed_bindings`：只列 `allowed=1`、`(umo,server_id)` 对齐、跨 umo/跨 server 聚合正确。
  - `bind_umos_to_server`：批量置 `allowed=1`；**active pin**——umo 无既有 active → 置 active=1；umo 已有 active（别台）→ 本行 active 保持 0、既有 active 不被夺；**断言每 umo `active=1` 行 ≤1**（M3）。
  - `purge_server_data`：跨 12 表 seed→purge 后 world_id 行/`servers`/`worlds`/`group_servers` 全清 + 各表计数正确；空 world_id 集只删三张 server 行、零计数；**保留台数据隔离不受损**（另一 server 的 world 数据一行不少）。
  - `clear_all_group_servers`：全表清空、返回行数、不误删其他表。
  - `list_orphan_server_ids`：DB server_id ∉ valid 的正确列出；valid 全覆盖时空列表。
- **端点编排** `handle_mode_transfer`（三类互转 × 迁移子集 × 保留/删除）：
  - config 断言：`world_mode` 切换；multi→single 保留台归位 `servers[0]`；`migrate_umos` 并入**顶层** `single_allowed_groups`（**非** `routing` 下）；`purge_others` 删其余 servers 行 + 指向 purge_set 的 `group_bindings` 种子行；single→multi 清空 `single_allowed_groups`。
  - **持久化 round-trip（M7）**：转移后 `parse_config(raw)` 真读到迁移进 `single_allowed_groups` 的项（证实写对了顶层键、未静默丢失）。
  - **候选保全 round-trip（M8）**：转移前后 `routing.access_mode`/`default_server`/`setup_confirmed` 不被静默重置；保留台 `password`/`password_env` 存活（保留台切后仍 `ready`）。
  - DB 断言：single→multi 绑定写入**生效就绪台**（B2：构造 `servers[0]` 非就绪的配置，断言绑到就绪台而非 `servers[0]`）；multi→single `clear_all_group_servers` 后 `group_servers` 空；purge 生效。
  - **move round-trip 复活测试（M2）**：multi→single move 后**切回 multi**，断言旧 DB 授权**不复活**（`get_allowed` 不返回已 move 的 umo，除保留台合法种子外）；single→multi move 后切回 single，断言 config `single_allowed_groups` 不复活。
  - **B1 负测**：非法 / 失效 `surviving_server_id`（不在就绪集）→ 拒 `invalid_surviving`、**零状态变更**（config+DB 皆未动）；就绪台=0 → 拒。
  - **M5 负测**：`_apply_and_restart` 返回 `{ok:False}` → 断言 **DB 完全未动**（bind/clear/purge 均未跑，非仅「模式不变」）+ 审计 success=0。
  - **B3 负测**：bind 抛异常 → 模式仍切（config 已变）、审计 success=0/migrated=0、回执带迁移失败告警、**无静默异常逃逸**。
  - **purge 部分失败**：一台 purge 抛错 → 其余台仍清、审计 success=1 + failed_server_ids、回执告警。
  - **审计断言（M6）**：五类退出（拒绝 / 回滚 / bind 失败 / purge 部分失败 / 全成功）**都写审计**；`admin_id` = `_current_username()` **明文**；`server_name` 非空（`None` 会 IntegrityError）；`action="mode_transfer"`；detail 计数完整。
  - **鉴权**：`_has_identity` 未鉴权拒（四端点）。
  - **migrate_umos ⊆ 源**：越集 → 拒 `invalid_migrate_umos`、零变更。
  - **并发（B4）**：`_save_lock.locked()` 时入口拒 busy；container-None/`_busy_msg` 时零变更。
- **孤儿清理**：`handle_orphans_list` 列 config 已无的 DB server_id；`handle_orphans_purge` 逐台 purge + 审计 + 失败续跑。
- **前端**：模式切换控件按模式渲染并开对应流；预览端点驱动清单（ready_servers 作保留台候选、bindings 作迁移勾选、已有权/将获新权标注与默认勾逻辑）；确认框/向导（`migrate_umos` 载荷、删除侧勾选闸禁用逻辑、摘要、错误→模式不变、`migration_failed`/`purge_failed` 告警）；孤儿清理入口。
- 无新命令锚定（四端点是 web 端点、非 `/pal` 命令）。前端改源后 `npm run build` 保 `pages/settings/**` no-drift + LF。

## 8. 锚定 / 约束（沿用项目铁律）

- 相对导入红线；提交不出现 Claude；前端 build no-drift + LF。
- README/docs 改中文用词须核 `tests/unit/readme_test.py` 锚点。
- **版本号不变（v0.9.7）**——不动任何版本源/断言。
- **审计字段（本功能订正）**：`admin_id` **明文**存 `_current_username()`（Dashboard 用户）——与 `admin_service` 现有明文 `admin_id`、`config_view.audit_rows` 直接回显 `admin` 一致；早稿「userid 只 hash」样板不适用本 web 场景。`server_name` 非空（列 `NOT NULL`）。审计留存沿 `audit_retention_days` 折进现有 `prune`（`sqlite_repository.py:281,304`）。
- purge 表清单以 `migrations.py` 建表为准（12 张 world_id 键表 + 三张 server 行；`unknown_classes` 不碰）——新增表须同步 `purge_server_data`（漏表=孤儿滞留）。

## 9. 依赖顺序 / 风险

- **依赖顺序**：Repository 五方法（`list_allowed_bindings` / `bind_umos_to_server` / `purge_server_data` / `clear_all_group_servers` / `list_orphan_server_ids`，purge 先测透）→ `mode/transfer/preview` 只读端点 → `mode/transfer` 原子编排（持 `_save_lock` + 迁移读先于 reload + reload 失败中止 + move 清源 + bind/purge 失败处理 + 最外层审计）→ `mode/orphans` 列/清端点 → 前端模式切换控件 + 确认框 + 转移向导 + 孤儿清理入口 → 文档 + 终检。
- **头号风险（purge 正确性 + 隔离）**：server 级 purge 跨 12 表全新写，须充分测（漏表=孤儿滞留；误删=打到保留台数据）。`world_id` 解析须精确按 `worlds.server_id`；purge_set 显式 `{就绪台}−{surviving}`、绝不含 surviving（B1）。
- **次风险（非 2PC 部分失败）**：post-reload 的 bind/clear/purge 失败但模式已切 → 审计+回执必须如实告警（B3/purge 部分失败），不假装成功；孤儿清理端点兜底重试（决策 3）。
- **迁移方向易错**：multi→single 读 DB 写 config 顶层名单（写对顶层键，M7）；single→multi 读 config 名单写 DB 绑定（绑生效就绪台，B2）——两向别写反、别写错介质位置。
- **候选构造陷阱（M8）**：必须深拷贝完整 `_raw_config` 原地改、逐字保 routing/servers（含密码）、绝不 redact/parse 重建、绝不预改 `self._raw_config`——否则静默重置 access_mode/default_server 或丢密码或污染回滚快照。
- **move 清源正确性（决策 2）**：迁移后清空源介质（DB `group_servers` / config `single_allowed_groups`）+ 删指向被删台的 `group_bindings` 种子行，切回原模式不复活——round-trip 测试坐实。
- **保留台归位 + 生效就绪台（B1/B2）**：切 single 后 `_ready_servers()[0]` 必是保留台（归位 servers[0]）；single→multi 绑到 reload 前捕获的 `_ready_servers()[0]`——皆硬约束、须测。
