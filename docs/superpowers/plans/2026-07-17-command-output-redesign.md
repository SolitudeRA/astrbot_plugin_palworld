# 命令输出重设计 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 29 条 /pal 命令输出与横切回执面按 spec §4/§3 全量重做为「纯文本精装」体系，随行完成 §5 十六项后端小扩与 §6 十一项捎带 bug 修。

**Architecture:** formatter/locale 层全量改写；供数按 §5 小扩表逐点扩（query stale helper / 事件名字共享 resolver / DTO 通管 / RoutingService 结构化返回 / AdminResult.target_userid）；门控与安全语义零改动（门序铁律、visible_actions、confirm 原子性、name_banned）。基建（折叠/时长/日期 helper + 折叠上限配置键）先行，各命令组 formatter 依序重做，文档与 golden 收尾。

**Tech Stack:** Python（AstrBot 插件，相对导入）+ Vue3（仅 schema.ts 一处）+ pytest/vitest。

**Spec（需求真源，样张与规则全在 §4，横切在 §2/§3，两轮设计复核+一轮 spec 复核定稿）:** `docs/superpowers/specs/2026-07-17-command-output-redesign-design.md`

## Global Constraints

- **样张真源 = spec §4**：每任务的输出形态逐字以 spec 样张为准（「Palpagos/主服/主服务器/据点名」为示意，落地按 §2.1 锚点数据源=配置名 srv.name）；规则句与样张冲突时以样张结构+规则句语义合并判断，存疑升级控制方。
- 包内 Python 一律**相对导入**（绝对自导入运行时炸，有静态防回归测试）。
- **门控/安全语义零改动**：admin 硬门先于 feature 门、visible_actions 唯一谓词、confirm claim-then-execute、name_banned 收敛判定、审计不落明文——现有安全测试**严禁削弱迎合新输出**；输出断言按 §9 改写，安全断言只换文案锚不换语义。
- **golden 纪律**：tests/golden 5 文件只允许「人工核对后重生成」——实现者须在报告中贴出新 golden 全文供评审比对 spec 样张；**禁止裸删重跑**（机制上文件缺失即静默用当前输出生成）。
- 时长/日期/折叠一律经 T1 的共享 helper，**禁止各 formatter 自拼**（防三处日期规则漂移复发）。
- README/docs 中文用词改动与 `tests/unit/readme_test.py` 锚点**同一提交**；「未开放」两义分治（§8）。
- `_conf_schema.json` **只加键不删键不改既有键结构**（平台铁律：装载即按 schema 裁键落盘）。
- 产物 `pages/settings` 只经 `cd frontend && npm run build`（内置 normalize-eol）重建，T1 一次完成（本 feature 唯一前端改动点）。
- 版本号不动（定版留 finishing）；提交信息**不得出现 Claude**。
- 测试命令：后端 `./.venv/Scripts/python.exe -m pytest -q`（基线=任务开工前在本分支实测并记录；repository_sessions_test 偶发 Windows teardown flake 复跑即消）、`ruff check .`、`./.venv/Scripts/python.exe -m mypy palworld_terminal`；前端 `cd frontend && npx vitest run`、`npm run typecheck`（仅 T1 涉及）。
- locale 键族命名沿现有小写下划线风格；新增键在 §7 处置框架内，具体键名实现者定并在报告列出。

---

### Task 1: 输出基建——格式 helper + locale 第一波 + 折叠上限配置键（跨端 5 落点）

**Files:**
- Create: `palworld_terminal/presentation/textkit.py`（新模块：折叠/时长/相对日期/引号回显 helper）
- Modify: `palworld_terminal/presentation/locale.py`（死键删除 auth_error/derived_note；新增 busy/arg_error 键；键表见 spec §7）
- Modify: `main.py`（busy 硬编码 → `L("busy")`）
- Modify: `palworld_terminal/presentation/commands.py`（`_ARG_ERROR_MSG` 三处 → `L("arg_error")`）
- Modify: `palworld_terminal/config.py`（players 节新键 `list_fold_limit` 解析 clamp ≥1 默认 7；`rank_top_n` clamp 1–50、0/负回默认 5）
- Modify: `_conf_schema.json`（players 节加 `list_fold_limit`，default 7，描述一句话；**不动其他键**）
- Modify: `palworld_terminal/presentation/config_view.py`（数值类型表加 `("players","list_fold_limit"): "int"`，validate 同步）
- Modify: `frontend/src/lib/schema.ts`（players 节字段声明加 list_fold_limit）+ `frontend/src/lib/schema.test.ts`（字段 drift 断言同步）
- Test: `tests/unit/textkit_test.py`（新）、`tests/unit/locale_test.py`/`locale_rework_test.py`（键表同步）、`tests/unit/players_config_test.py` 同族（clamp 界值）、`tests/unit/conf_schema_test.py`（若有键锚定）

**Interfaces（Produces，后续全部 formatter 任务消费）:**
- `fold(lines: list[str], limit: int, unit: str) -> list[str]`——超限截断并追尾行 `…等共 N {unit}`；limit 来自 cfg.players.list_fold_limit。
- `fmt_duration(seconds: int) -> str`——「N天N时 / N时M分」；有小时段分钟两位补零（`21时05分`）、不足 1 时只写 `45分`（spec §2.4）。
- `rel_date(ts: int, now: int, tz) -> str` 与 `rel_datetime(ts, now, tz) -> str`——三档词形 今天/昨天/MM-DD（跨年 YYYY-MM-DD）；datetime 版全档带 HH:MM（spec §2.5）。
- `L("busy")` / `L("arg_error")`。

- [ ] **Step 1（TDD 红）**：textkit_test——fold 界值（=limit 不折/limit+1 折且尾行量词正确）、fmt_duration（0 分/45 分/1 时 5 分→`1时05分`/25 时→`1天1时`）、rel_date/rel_datetime（今天/昨天/同年 MM-DD/跨年，DST 安全用 tz 构造）；config 测试——list_fold_limit 缺省 7/0 回 1？（clamp ≥1）/rank_top_n 0→5、-3→5、200→50。跑 → 红。
- [ ] **Step 2**：实现 textkit.py 与 config clamp；locale 键第一波（删 2 死键、加 busy/arg_error）；main.py/commands.py 收编（三处 `_ARG_ERROR_MSG` 同串归一到 `L("arg_error")`，文案 `⚠️ 一条命令只能指定一个 @服务器`；busy `⚠️ 插件正在重载配置，请稍后重试`）。
- [ ] **Step 3**：_conf_schema.json/config_view/前端 schema.ts+schema.test.ts 四落点（spec §5#10：挂 players 既有节白拿字段 drift 测试）。
- [ ] **Step 4**：`cd frontend && npm run build` 重建产物（本 feature 唯一一次）。
- [ ] **Step 5**：全套绿（后端+前端+no-drift），提交（可拆 2 commit：后端基建 / 前端落点+产物）。

### Task 2: 降级态三落点 + 新鲜度 helper

**Files:**
- Modify: `palworld_terminal/application/query_service.py`（staleness helper + status 降级双态供数）
- Modify: `palworld_terminal/presentation/formatters.py`（format_degraded 扩 server_name、statusDTO 消费）
- Modify: `palworld_terminal/presentation/commands.py`（_resolve_world 降级分支传 res.server.name）
- Test: `tests/unit/`（stale 边界假 clock；degraded 双句；第三落点锚点）

**Interfaces:**
- Produces: `metric_stale(observed_at: int, now: int, metrics_seconds: int) -> bool`——阈值 = metrics_seconds × 3 + 60（spec §3；T12 link list 可达性复用）；`format_degraded(last_ok, now, server_name)` 新签名。
- 降级输出（spec §4.1/§3）：标题 `🌍 世界状态 · {服务器名}` + `🔴 当前无法获取世界数据 · 最后成功于 N 分钟前`；从未成功 `🔴 尚未成功连接过服务器，请检查「连接」配置`。锚点全局统一不随发起命令变化。

- [ ] **Step 1（TDD 红）**：假 clock——metric 恰过期/未过期边界；status()：metric 存在但 stale → degraded=True 且 last_ok=observed_at（现死分支复活）；metric=None → last_ok=None「从未成功」句；_resolve_world world=None → 输出含服务器名标题。
- [ ] **Step 2**：实现三落点 + locale degraded/degraded_never 新句；改写既有 degraded 断言（locale_test.py:23 红线负断言**保持不动**，spec §9.4）。
- [ ] **Step 3**：全套绿，提交。

### Task 3: 隐私收敛下沉 _online_rows（status/online 两入口）

**Files:**
- Modify: `palworld_terminal/application/query_service.py`（_online_rows 内做 excluded/hidden 名字级收敛：load_excluded_keys + 与 rank `_converge_by_name` 同语义的名字级剔除）
- Test: `tests/unit/`（两入口各一：me hide 后 status 玩家节与 online 名单均不含该名；同名多 key 一 key 隐藏整组剔除；头行分子=名单数）

**Interfaces:** Consumes 既有 `load_excluded_keys`/`name_banned` 语义；Produces：收敛后的 `_online_rows`（status/online 共用，行数即头行分子——spec §3 隐私收敛）。

- [ ] **Step 1（TDD 红）**：上述用例。跑 → 红（现状两处均不剔）。
- [ ] **Step 2**：实现收敛（供数层，不动 formatter 样式）；确认 rank 既有收敛测试零回归。
- [ ] **Step 3**：全套绿，提交。

### Task 4: world status + overview + rules formatter 重做 + 锚点供数机制

**Files:**
- Modify: `palworld_terminal/presentation/formatters.py`（format_status/format_world/format_rules 按 spec §4.1/§4.2/§4.3 样张重写）
- Modify: `palworld_terminal/presentation/commands.py`（handle_query 链路把 resolve 出的 `srv.name` 传入 formatter——**锚点供数机制在此建立，后续任务沿用，不扩 DTO**，spec §2.1）
- Modify: `palworld_terminal/application/query_service.py`（overview：接 latest_metric.max_players/basecamp_count；rules：策展分节供数）
- Test: golden `status.txt`/`world.txt`/`rules.txt` 人工核对重生成 + spec §9#2 该三条的子串断言测试改写；overview 快照缺失 ⚠️ 态新用例（spec §6#8）

**要点（照 spec §4 逐字）:** status=定稿样张+据点行随组关消失+玩家节折叠/收敛（T3 供数）；overview=人口普查分节、FPS 删除、快照缺失 `⚠️ 尚未获取到世界快照，稍后再试`、strict 砍 PalBox 项；rules=四节策展+剔除清单+两句隐私注分叉+取数失败态 ⚠️；游戏设定原值不套时长格式（§2.4 豁免）。

- [ ] **Step 1（TDD 红）**：三条新形态断言 + overview ⚠️ 态 + rules 取数失败态。
- [ ] **Step 2**：实现 + 既有子串断言改写 + golden 重生成（报告贴全文）。
- [ ] **Step 3**：全套绿，提交。

### Task 5: 事件主体名共享 resolver + 据点序号空间统一

**Files:**
- Create: `palworld_terminal/application/name_resolver.py`（或挂 Repository——实现者定，报告说明取舍）
- Modify: `palworld_terminal/application/query_service.py`（_bases_indexed 改 `list_bases(include_low=True)`；events() 接 resolver）
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（list_bases 加 include_low 参数，默认保持现行为）
- Test: `tests/unit/`（三类 key 解析；hidden 玩家事件跳过；hidden 据点回退「据点」；#序号跨 events/bases/base 一致性）

**Interfaces:**
- Produces: `resolve_subjects(world_id, events) -> dict[str, str]`（player_key/guild_key/base_key → 显示名；批量、hidden 玩家事件由调用方跳过或 resolver 返 None；据点名=display_name 或 `BASE-{i}`，i 来自 include_low 清单位次，hidden 不入清单查无回退「据点」——spec §3 据点名口径）。T6 events、T7 today、T10 guild info 消费。

- [ ] **Step 1（TDD 红）** → **Step 2 实现** → **Step 3 全套绿提交**（含 guild bases/base 既有序号测试随 include_low 改写）。

### Task 6: world events formatter 重做

**Files:**
- Modify: `palworld_terminal/presentation/formatters.py`（format_events：日分组/池 20/消息级折叠 7/today 变体）
- Modify: `palworld_terminal/presentation/commands.py`（events 传 resolver 结果与 srv.name）
- Modify: `palworld_terminal/presentation/locale.py` 或 formatter 常量（**八类事件措辞表单一真相源**，spec §4.4 表——T7 today、T10 guild info 复用同表）
- Test: spec §9#2 events 子串改写 + 新形态断言（日分组/仅今天带 HH:MM/折叠尾行/空态两句/隐藏玩家缺席）

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 7: world today——ReportService 结构化 + epoch bug 修 + formatter

**Files:**
- Modify: `palworld_terminal/application/report_service.py`（DailyReport 条目结构化：records 废 f-string 预渲染改类型化条目；名字解析接 T5 resolver；三节分派去重=今日纪录只收里程碑/纪录/新玩家/新公会；world_day_start/end 改真实世界天数）
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（日窗口内 metrics 首末 world_day 查询，spec §5#4）
- Modify: `palworld_terminal/presentation/formatters.py`（format_today 按 §4.5 样张）
- Test: `report_service_test.py` 专项（:74-75 epoch 断言反转为真实 world_day；:194 随名字解析反转；:102 核对留置）+ golden `today.txt` 人工核对重生成 + 新形态断言（去重/措辞同源/空态）

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 8: player info + bind + unbind + me

**Files:**
- Modify: `palworld_terminal/application/query_service.py`（PlayerProfileDTO 扩 first_seen_at/last_seen_at/guild_name/today_seconds/total_seconds/hidden 字段，spec §5#16；今日/累计聚合同源 rank，§5#5）
- Modify: `palworld_terminal/presentation/commands.py`（bind 前查旧绑定改绑透明化；unbind 悬空不出哈希；me hide/show 新回执；多模式锚=world_mode 判定）
- Modify: `palworld_terminal/presentation/formatters.py`（format_player 按 §4.10/§4.25 卡片；strict 双砍）
- Test: format_player_test/commands_player_test/commands_me_bind_test 改写 + 新态断言（在线/离线/strict/未找到/改绑/悬空/hide-show 带锚/未绑定带服/单模式去锚）

**要点:** 样张照 §4.10-4.12/§4.25 逐字；「最后在线」用 rel_datetime（全档带 HH:MM）；找不到正字「未找到」；未绑定正字「你还没有绑定玩家」；多模式锚族=bind/unbind/me hide/show/未绑定五处，单模式全部省略。

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 9: rank + online formatter 重做

**Files:**
- Modify: `palworld_terminal/presentation/formatters.py`（format_rank：标题三变体/名次序号/strict ⚠️ 句+脚注/空榜；format_online：头行 分子=名单数+/max_players+峰值/条目式/strict 砍时长/空态收编 locale/折叠尾行「人」）
- Modify: `palworld_terminal/application/query_service.py`/`commands.py`（online 头行供数 max_players+peak_online；rank 标题 srv.name）
- Test: format_rank_test/commands_rank_test 改写 + golden `online_redacted.txt` 人工核对重生成 + 头行=名单数一致性断言（T3 已供收敛）

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 10: guild 组四条（上游恢复后生效，落码即备）

**Files:**
- Modify: `palworld_terminal/application/query_service.py`（§5#15 供数：每公会据点数分组；bases worker_count 实填 latest_base_observation；info 据点列表过滤+近期动态实填替换恒空 base_event_lines；GuildDTO/GuildDetailDTO/BaseDTO/BaseDetailDTO 字段随砍位/增补调整）
- Modify: `palworld_terminal/presentation/formatters.py`（四条按 §4.6-4.9 样张：分组/置信度/健康度状态点阈值 🟢≥75/🟡≥40/🔴<40/行为分布=ActionCategory 8 档中文/PalBox 不渲染）
- Modify: `palworld_terminal/presentation/commands.py`（strict 守卫：bases/base 整命令拒执行 `⚠️ 据点模块在 strict 隐私模式下停用`（bases_disabled_strict 接线）；list/info 字段级裁剪——据点计数/节省略；guild info/base 无参 usage 态）
- Test: 既有 guild 输出断言改写 + 新态断言（strict 四条分派/无观测 ⚠️/找不到+脚注/无参 usage/含 low 行/序号一致（T5 供））；测试环境经 conftest `_wire_game_data` 保持可覆盖（门关验证独立）

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 11: server 写命令 + confirm 回执重做

**Files:**
- Modify: `palworld_terminal/application/admin_service.py`（AdminResult.params 补 target_userid，spec §5#7；unban 本地 steam_ 前缀校验）
- Modify: `palworld_terminal/presentation/commands.py`/`locale.py`（per-action 成功短语键族；失败式 `❌ {动作}失败 · {server}` + `└ {error}`；目标族三态新式；usage 全改英文子命令；preview/confirm 新式；confirm 断连「已发起」语义修复；no_pending 并句「（可能已超时作废）」）
- Test: commands_admin_write_test 及 confirmation/admin 链路消费方测试改写（spec §9#7）+ 新态断言（回执含目标尾4/announce 回显/ban 理由脚注/shutdown 倒计时脚注/断连 confirm 语义/unban 前缀校验/usage 无中文动作名）

**要点:** 样张照 §4.13-4.19/§4.29 逐字（全角引号 §2.3）；门序/二次确认/审计逻辑零改动，只改文案与 params。

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 12: link 组 + whereami + whoami

**Files:**
- Modify: `palworld_terminal/application/routing_service.py`（use/unbind 改结构化返回 dataclass——use `{ok, server_id, replaced_active}`（set_active 前 get_binding_active 取旧值）、unbind `{removed, was_active}`（revoke 前查存在性或 rowcount，实现者定并报告）；locale 渲染上提 commands 层，spec §5#8）
- Modify: `palworld_terminal/presentation/commands.py`/`formatters.py`（link list 三态点=T2 metric_stale 派生可达/私聊授权段省略/skipped 素节头+reason 中文化/折叠；add/remove 回执按 §4.21/4.22 含拆键 link_list_empty/link_add_unknown；whereami access_mode 分流+单模式变体；whoami 按 §4.27）
- Modify: `palworld_terminal/presentation/locale.py`（拆键；use_only_group 加 ⚠️；whoami/whereami 新式）
- Test: routing_service_use_test/main_link_single_test 断言改写（结构化返回）+ format_servers/link 各态新断言（三态点/私聊/中文 reason/无授权记录素文/open 分流/单模式 restricted 变体）

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 13: help 重做 + 横切拦截文案收尾

**Files:**
- Modify: `palworld_terminal/presentation/formatters.py`（format_help：素节头+组头词表 世界/公会/玩家/服务器管控（管理员）/服务器授权/其他+行式 `· /pal {路径} {描述}`+单模式省略 @ 尾注；_GROUP_LABEL 与前端 GROUP_LABELS 对齐）
- Modify: `palworld_terminal/presentation/commands.py`（help 跳过 parse_arg 根治双 @ 裸抛；admin_required/feature_disabled/场景类 ⚠️ 全落点换新句；feature_disabled 条件脚注=upstream_unavailable(path) 时省略）
- Modify: `palworld_terminal/presentation/locale.py`（admin_required/feature_disabled/private_restricted 新句）
- Test: formatters_hierarchy_test/formatters_admin_help_test 低风险核对（"/pal" 子串多数存活，跑红补改）+ 新态断言（help 双 @ 不抛/单模式无尾注/upstream 无脚注 vs 普通 off 有脚注/private_restricted ⚠️ 而其余六分支素文）

**要点:** visible_actions 谓词与角色/功能/模式过滤逻辑零改动；group_no_actions 与裸组迷你帮助沿用（spec §3/§7）。

- [ ] Step 1 红 → Step 2 实现 → Step 3 全套绿提交。

### Task 14: 文档同步（与锚点同提交）

**Files:**
- Modify: `docs/commands.md`/`docs/configuration.md`/`README.md`（§8：行为义「回「未开放」」→「未开启」；「上游未开放（PalGameDataBridge）」不动；rank 变体描述随新式；输出示例随新样张）
- Test: `tests/unit/readme_test.py`（锚点显式重锚：行为义「未开启」+另立「上游未开放」锚；同提交）

- [ ] Step 1：照 §8 逐处改+锚点重锚 → Step 2：readme_test/conf_schema_test 绿+全套绿，提交。

### Task 15: golden 终核 + 全库终验收尾

- [ ] **Step 1**：五 golden 与 spec §4 样张逐字终核（人工比对，报告贴 diff 说明）；补漏的跨任务一致性断言（八类措辞三处同源锚定、时长/日期 helper 无旁路直拼）。
- [ ] **Step 2**：全套终验——后端 pytest（含 no-drift）+ruff+mypy、前端 vitest+typecheck 全绿；`git status` 干净。
- [ ] **Step 3**：报告基线净变数字与 §6 十一项 bug 的回归测试映射表（供全分支终审对照 §10 验收）。

## Self-Review

- Spec 覆盖：§2/§3 → T1（helper/键）/T2（降级）/T3（收敛）/T13（拦截文案）分持；§4.1-4.3→T4、§4.4→T6、§4.5→T7、§4.6-4.9→T10、§4.10-4.12+4.25→T8、§4.13-4.19+4.29→T11、§4.20-4.22+4.27-4.28→T12、§4.23-4.24→T9、§4.26→T13；§5 十六行→T1(#10)/T2(#1,#9)/T3(#6)/T4(#14)/T5(#2,#11)/T7(#3,#4)/T8(#5,#13,#16)/T10(#12,#15)/T11(#7)/T12(#8)；§6 十一项→T2(死分支)/T3(#2)/T4(#8 overview)/T7(#1,#7 today)/T8(#10)/T10(#4,#8 base,#11)/T11(#6)/T12(#5,#9)/T13(#3)；§7→T1/T2/T11/T12/T13 分持；§8→T14；§9→逐任务携带+T15 收口。无缺口。
- 占位符扫描：样张与措辞表以 spec §4 为真源（brief 随附 spec 路径与章节号），helper 签名/阈值/dataclass 形状在 plan 内给出；无 TBD。
- 类型一致：`metric_stale(observed_at, now, metrics_seconds)->bool`、`fold(lines, limit, unit)->list[str]`、`fmt_duration(seconds)->str`、`rel_date/rel_datetime`、use→`{ok, server_id, replaced_active}`、unbind→`{removed, was_active}`、`resolve_subjects(world_id, events)->dict` 前后一致。
