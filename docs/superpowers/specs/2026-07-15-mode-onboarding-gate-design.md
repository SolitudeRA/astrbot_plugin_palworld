# 首次强制模式选择：命令闸 + 设置页引导屏（Phase 1）设计

> 关联：本功能是「让运行模式选择变成有意识、被引导的动作」的 **Phase 1**。
> Phase 2（有条件模式互转 + 转移引导）另立 spec，不在本文件范围。
> 前置已交付：模式分道 v0.9.7（`docs/superpowers/specs/2026-07-15-mode-separation-design.md`）——
> `world_mode`（single/multi，默认 single）、`single_allowed_groups` 授权群名单、`/pal whereami`、
> 设置页模式只读 badge、模式开关唯一入口=AstrBot 齿轮。
>
> **本文已并入一轮 4 视角对抗复核结论**（平台可行性 / 数据安全回归 / 安全门序 / 锚定完整性），
> 4 条 major 已折进 §4.2/§4.3/§5/§6/§9/§10，标注 🛡 处即对抗复核加固点。

## 1. 背景与目标

**痛点（用户确认）**：默认改 single 后，用户可能装了插件、从没碰过模式开关，静默跑在可能不对的默认上而不自知；希望新装时**强制用户有意识地选一次模式**。

**平台现实（勘探结论）**：AstrBot 插件模型**没有**"配置未完成就阻塞激活/弹窗"的钩子（生命周期仅 `initialize()`/`terminate()`）；启动时无主动推送渠道（只能被动响应命令 / 打控制台日志），也拿不到会话目标。且 `world_mode` 因 **AstrBot 递归回填 schema 默认并落盘**，"接受默认的 single"与"主动选的 single"字节相同——**"用户没选过"这个状态在 `world_mode` 上不可表示**。

**目标**：在平台允许的最接近"强制"的形态下，用**独立的确认标志 + 命令闸 + 设置页引导屏**，让全新安装必须完成一次有意识的模式确认才能正常使用 `/pal`；确认入口是自定义设置页（Web UI 始终可达）。

**成功标准**：
- 全新安装：`/pal` 常规命令被闸、返回引导语；自助命令（help/whoami/whereami）仍可用；设置页显示引导屏。
- 用户在引导屏显式选 single/multi 并确认后：标志置 true、闸清、`/pal` 恢复正常、页面转正常设置。
- **已确认的安装：行为与 v0.9.7 完全一致（零回归）**——这条是硬约束，读侧 hydrate（§5/§6）与 fail-safe 谓词（§7/§8）都是为守住它。

## 2. 非目标（明确划出，属 Phase 2 或不做）

- **有条件模式互转 / 转移引导**（single↔multi 的二次确认、多台切单的转移向导、link 绑定迁移为授权群名单、其余服务器数据去留）——Phase 2。
- **设置页常态可写模式**：Phase 1 里设置页**只有引导屏**这一处写 `world_mode`（首次一次性）；确认后模式恢复只读 badge、更改仍走齿轮（与 v0.9.7 一致），直到 Phase 2 加入设置页内带引导的互转。
- **引导屏配服务器**：引导屏只做"选模式 + 确认"；配服务器留给确认后的正常设置页（「连接」章）。
- **聊天内确认命令**（如 `/pal setup <mode>`）：不做；确认统一在设置页（Web UI 始终可达，逗口聊天命令负责把用户指向它）。
- **拦截齿轮裸切**：齿轮改 `world_mode` 仍是裸切、不被引导流约束（后端已有安全网：单模式检测到多台就绪→告警+只用首台，不崩不丢数据）。
- **版本号不变**：Phase 1 不发版（见 §11）。

## 3. 术语

- **setup 闸 / 命令闸**：`setup_confirmed` 非 true 时拦截非逗口 `/pal` 命令、代之以引导语的语义门。
- **逗口集（exempt set）**：闸放行的纯信息自助命令 `{help, whoami, whereami}`。🛡（对抗复核：`confirm` 从逗口集**移除**，见 §4.2）。
- **引导屏（onboarding screen）**：设置页在未确认时呈现的首屏，选模式 + 确认。

## 4. 架构

### 4.1 `setup_confirmed` 标志（bool，默认 false）

- 语义：用户是否已完成一次有意识的首次模式确认。默认 `false`；靠 AstrBot 回填默认→全新安装恒 `false`。
- **无用户 → 无迁移**（插件尚无真实用户；加默认 false 的新键，所有现存皆全新安装自然为未确认）。
- 独立于 `world_mode`：不把 `world_mode` 做成三态；用单独标志承载"是否确认过"。
- 🛡 **首个顶层裸标量 bool 风险**：全仓 13 个顶层键皆 object/template_list、bool 全嵌套（如 `servers.items.enabled`），无顶层标量先例。放置策略与验证见 §4.3。
- 🛡 **解析严格布尔**：`setup_confirmed` 只认 JSON `true`（`raw.get("setup_confirmed") is True`），字符串 `"false"`/其它一律视为未确认——避免 `bool("false")===True` 脚枪。

### 4.2 命令闸（chat 侧，硬闸 + 逗口）

🛡 **对抗复核订正：main.py 现实无单一"中央 choke point"。** `_guarded(self, call)` 拿不到命令身份、且被逗口 `{help,whoami,whereami}` 与非逗口组命令 `{world,guild,player,server,link}` 共用；另 3 个非逗口扁平命令 `rank/online/me` 走带 `command_str` 的 `_guarded_cmd`。故闸**不能**只塞进 `_guarded` 一处（否则要么连逗口一起拦死=砸掉逃生出口，要么漏掉 rank/online/me=fail-open 破防）。

**落地方式**：闸做成**命令感知**，同时落在两处包装器：
- `_guarded_cmd`（已带 `command_str`，天然知道命令身份）：首词 ∉ 逗口集 → 返回 `L("setup_required")`。
- `_guarded`（不带身份）：由各 handler 传入自己的首词字面量后判定；**未知/无法识别首词一律拦（fail-closed）**。
- 逗口集 `{help, whoami, whereami}`：放行。

> 🛡 **勘探订正**：spec 前一稿写的 `_dispatch_read`/`_guarded_admin` 在当前 `main.py` **不存在**（过时命名）。planning 期以真实 `main.py` 的 `_guarded`(≈:195) / `_guarded_cmd`(≈:215) 及各组 handler(:426-453 组 / :467-481 rank/online/me / :488-506 逗口) 为准确认插桩点，保证：**每个非逗口注册命令必被闸、逗口命令确实绕过**。

**门序**：setup 闸是**语义门**、置于 enable/admin/授权判定**之前**；但须放在 **busy / container-None 等运行时守卫之后**（闸读 live `AppConfig`，容器未就绪时先走既有兜底，别在 None 上取值）。

🛡 **实现约束（保逃生出口恒可达）**：闸**只能**落在聊天命令 handler 侧，**绝不下沉**到 `register_web_api` 的 HTTP 端点或 `Container`/`scheduler`——否则会锁死设置页这个唯一确认入口。web 设置页因此始终可达。

**引导语 `setup_required`（新 locale 键）**：🛡 自包含、不设断头指针（不再让用户"发 /pal help 看说明"，因 help 未必提未设置态）。形如：「🔧 帕鲁世界终端尚未完成首次设置。请打开插件设置页，选择运行模式（单服务器 / 多服务器）并确认后即可使用。」

### 4.3 配置管道（解析 / schema / 往返）

- `config.py`：`AppConfig` 加 `setup_confirmed: bool = False`；`parse_config` 严格解析（`raw.get("setup_confirmed") is True`，见 §4.1）。
- `_conf_schema.json`：加 `setup_confirmed`（布尔类型**以现有 schema 布尔字段写法为准**，参照 `servers.items.enabled` 的类型键；`default: false`；description：「首次设置确认标志：一般由插件设置页在你完成模式选择后自动写入，通常无需手动改动。」）。
- 🛡 **放置与验证（对抗复核重定向）**：
  - **验证矛头指向 AstrBot 原生层**（不是 config_view——经核实 config_view 只遍历 `_LIST_SECTIONS`、标量原样透传，本就安全）：**planning 期须在真实 AstrBot 实例验证**顶层 `{"type":"bool","default":false}` 能①齿轮页正常渲染、②新装回填出 `false`、③经 GET/save 往返持久。**验证通过再下沉命令闸**（闸的正确性依赖"新装恒 false"这一承重假设）。
  - **降级预案**：若 AstrBot 不支持顶层裸标量，改把 `setup_confirmed` **嵌进既有 object 节**（如 `routing`），随该 object 往返，`parse_config` 读取位置相应调整；此时它非顶层键，`_TOP_KEYS` 不需加。
  - 🛡 **`config_view.py` 只改一处**：`setup_confirmed`（若走顶层）**仅加入 `_TOP_KEYS`**，**禁止**加入 `_LIST_SECTIONS`/`_ROW_ID_PREFIX`/`_SECTION_KEYS`（照搬 single_allowed_groups 四常量会把 bool 当 list 校验 → 每次保存 invalid_shape 被拒）。
  - 🛡 `validate_and_backfill`：body 含 `setup_confirmed` 时须为 bool，否则 invalid_shape。
- 闸读**解析后的 live 值**（挂 AppConfig），热重载后重新生效——用户确认保存触发 config reload → 闸清。

## 5. 组件与接口

- **后端**
  - `config.py`：`AppConfig.setup_confirmed: bool`；`parse_config` 严格接线。
  - `main.py`：`_SETUP_EXEMPT = {"help","whoami","whereami"}`（常量，锚定）；setup 闸落在 `_guarded` + `_guarded_cmd`（§4.2）。
  - `locale.py`：`setup_required` 键。
  - `_conf_schema.json` / `config_view.py`：schema + `_TOP_KEYS`（§4.3）。
  - 🛡 **GET/redact 读侧透出**：`config_view` 的 redact/GET 路径须把 `setup_confirmed` 透给前端（否则前端读不到、无法判定显不显引导屏）。
- **前端**
  - `SettingsPanel.vue`：`ready` 之上加 `onboarding` 相态（谓词见 §7）；🛡 初始 reactive state 加 `setup_confirmed` 字段；🛡 `applyConfig` **无条件 hydrate** `setup_confirmed`（读侧，见 §6）。
  - 新组件 `ModeOnboarding.vue`：两张模式卡（single/multi）+ 显式点选 + 「确认并开始」（点选前禁用）。🛡 用**组件内部独立选择态（初值 null）**，与被回填成 `'single'` 的 `world_mode` **解耦**——否则会默认预选"单服务器"、违反"不预选"。
  - `collect.ts`：`collectBody` 回传顶层 `setup_confirmed`（🛡 严格 `state.setup_confirmed === true`，参照 collect.ts 现有布尔风格）；`SettingsState` 加字段。

## 6. 数据流：读侧 hydrate + 首次引导写入

🛡 **读侧（对抗复核补：无条件回传必须配无条件 hydrate——正是 v0.9.7 single_allowed_groups 同型坑）**：
- 初始 reactive state 含 `setup_confirmed`（默认 false）。
- `applyConfig`（GET 后、及每次保存返回后的刷新点）**无条件**执行 `state.setup_confirmed = c.setup_confirmed === true`（缺失/非 true → false），镜像 `SettingsPanel.vue` 对 `single_allowed_groups` 的无条件 hydrate。
- 缺了它的两个致命后果：①`state.setup_confirmed` 恒 undefined → 引导屏永不渲染而后端闸 active → **无 UI 出路死锁**；②已确认老装任意一次普通保存把 falsy 回传落库成 false → **闸对全体复活**（零回归被破坏）。

**写侧（首次引导）**：
1. 设置页加载配置（GET，含 `setup_confirmed`）→ hydrate → 谓词判未确认 → 渲染引导屏。
2. 用户点选一张模式卡（组件内部选择态）→ 「确认并开始」启用。
3. 点确认 → 前端置 `state.sections.routing.world_mode = 所选` + `state.setup_confirmed = true` → 走**现有保存链路**（`collectBody` → POST save 端点 → `config_view` redact/strip → `save_config`）。
4. 插件 reload 配置 → `setup_confirmed=true` → 闸清。
5. 前端保存成功 → 切到正常设置页（落「连接」章，引导接着配服务器）。

🛡 **鉴权**：确认写入复用**现有带 Dashboard 登录鉴权（`_has_identity`）的 save 端点**，**不新增任何未鉴权端点**——防止未鉴权翻转 `setup_confirmed`。

> `world_mode` 本就被 `collectBody` 原样回传（v0.9.7 数据安全不变量），且 onboarding 分支在 `applyConfig` 之后、state 仍持有**全量** config，故引导屏保存发送的是完整配置（servers/permission_admins/single_allowed_groups/command_permissions/polling… 全在），不会因引导屏没渲染某些 section 而抹除它们。

## 7. 设置页引导屏 UX

- 🛡 **触发谓词统一为 `setup_confirmed !== true`**（不是 `=== false`）：使 缺失 ≡ false ≡ 被闸 ≡ 显引导屏，与后端 `is True` 判定**同向 fail-safe**（避免"闸开着但引导屏不显示"的半态锁死）。相态：`ready && setup_confirmed !== true` → 引导屏取代正常章节。
- **内容**：欢迎语 + 两张并列模式卡：
  - **单服务器**：唯一服务器，群授权走「授权群名单 + `/pal whereami`」。
  - **多服务器**：多台服务器，用 `/pal link` 绑定切换。
- **强制有意识选择**：🛡 组件内部选择态初值 null、不预选（与回填的 `world_mode` 解耦）；「确认并开始」在显式点选前**禁用**。
- **确认后**：转正常设置页（模式恢复只读 badge + 齿轮，与 v0.9.7 一致）。底部小字：模式日后可在 AstrBot 齿轮更改（Phase 2 会加设置页内带引导互转）。
- **无"跳过"**：唯一出路是选 + 确认。

## 8. 错误处理与边界

- 齿轮把 `setup_confirmed` 手改回 false → 闸复活（schema 注明勿手改，可接受）。
- 确认后热重载 → 闸清（走现有 reload 路径）。
- 确认后删光服务器 → 仍算已确认（闸不复活，合理）。
- 保存失败（save_config 异常/网络）→ 引导屏保持、提示重试，不误置 confirmed（沿用现有保存 UX 错误处理）。
- 🛡 `setup_confirmed` 缺失/非布尔 → 前端谓词 `!==true` 归"未确认显引导屏"、后端 `is True` 归"未确认被闸"，两侧同向、无半态。
- 逗口命令在未确认时正常工作，帮助用户走向设置页。

## 9. 测试策略

🛡 **头号铁律（跨端）——「已确认安装」fixture 必须喂 `setup_confirmed=true`**，否则测试静默/响亮失真（直接来自 v0.9.7 全分支终审教训，且本次对抗复核指出前端波及面更大）：
- **Python 侧**：`tests/unit/namespace_runtime_smoke_test.py` 的 `_raw_config` 须设 `setup_confirmed=true`，否则全部被闸命令短路成引导语、深支覆盖**静默丢失**（与该测试固定 `world_mode=multi` 同理）。波及面有界：闸在 handler 层，只影响经 handler 驱动命令的测试；直接调 `Commands`/service 的单测不过闸。
- 🛡 **前端侧（对抗复核新增，波及更大）**：所有 mount `SettingsPanel`（或落 settings 章）的既有测试代表「已确认安装」，其 config fixture（`SettingsPanel.test.ts` 的 `cfg()` 等）**必须加 `setup_confirmed:true`**，否则 onboarding 取代正常章节 → 十余条正常章节断言（访问控制/授权群名单/ServerCard 数量/保存设置）集体炸红。`collect.test.ts` 的 `TOP_KEYS` literal 会因 `collectBody` 新增 `setup_confirmed` 而需同步。
- **审计任务**：把"审计所有经 handler 驱动命令的测试（Python）"与"审计所有 mount SettingsPanel/落 settings 章的测试（前端）"列为**两个并列的专门任务**。

**新增测试**：
- 闸：`setup_confirmed` 非 true → 被闸命令返回 `setup_required`；逗口集（help/whoami/whereami）放行。`true` → 正常。门序：setup 闸先于 enable/admin、后于 busy/container 守卫。
- 🛡 **数据驱动穷举**：遍历 `PAL_REGISTERED \ _SETUP_EXEMPT`，断言每条未确认时返回 `setup_required`（防新增/改名命令漏挂闸 fail-open）。
- 配置：`setup_confirmed` 默认 false、严格解析（`"false"` 字符串→未确认）、`config_view` 往返闭合、含 `setup_confirmed=true` 的 body 不被判 invalid_shape。
- 🛡 **零回归回归测试**：装 `setup_confirmed=true` → 走一次普通（非引导）保存 → 断言 POST body 里 `setup_confirmed` 仍为 `true`（闸不被普通保存重置）。
- 🛡 **读侧 hydrate 测试**：GET 返回 `setup_confirmed=true` → 前端 hydrate 后不显引导屏；返回 false/缺失 → 显引导屏。
- 前端：未确认显引导屏 / 已确认隐藏；点选+确认写 `world_mode`+`setup_confirmed=true`；确认按钮点选前禁用；`collectBody` 严格 `=== true` 回传。
- 🛡 **鉴权**：无 `g.username` 时 POST config/save 返回 unauthorized、`setup_confirmed` 不被翻转。

## 10. 锚定约束（沿用项目铁律 + 对抗复核加固）

- 🛡 `_SETUP_EXEMPT` **跨源锚定**：单一真相源 + 测试 literal 全等，**且 `_SETUP_EXEMPT ⊆ command_registry 已注册扁平首词集`**（命令改名/删除即断链报红，防漂移 fail-open）。
- 🛡 `collect.test.ts` 的 `TOP_KEYS` 作为 `config_view._TOP_KEYS` 之外的**第三个跨源锚点**纳入维护（`setup_confirmed` 三处同步）。
- 相对导入红线；提交不出现 Claude；前端改源后 `npm run build` 保 `pages/settings` no-drift + LF。
- README/docs 改中文用词须核 `tests/unit/readme_test.py` 锚点。

## 11. 版本

**版本号不变（保持 v0.9.7）**：Phase 1 不单独发版，随 Phase 2 或后续统一发版。**不动**六处版本源与断言（`metadata.yaml` / `main.py @register` / `palworld_terminal/__init__.py __version__` / `README` badge / `phase1_smoke_test.py` / `skeleton_test.py`）。

## 12. 依赖顺序 / 风险

- 依赖顺序：🛡 **先在真实 AstrBot 验证顶层标量 bool 回填（§4.3）** → 标志解析（config）→ schema + config_view 往返（含读侧透出）→ 命令闸（main，`_guarded`+`_guarded_cmd` 两处）→ 前端读侧 hydrate + 引导屏 + collect → 文档 + 终检（版本号不变、不发版）。
- 🛡 **头号风险（读侧自锁）**：无条件回传缺配无条件 hydrate → 无 UI 出路死锁 / 闸对全体复活。§5/§6 已定读侧 hydrate + `!==true` fail-safe 谓词，plan 须把它作为与写侧同等的一等任务。
- 🛡 **次风险（闸插桩）**：无中央 choke point，须落 `_guarded`+`_guarded_cmd` 两处、未知首词 fail-closed；数据驱动穷举测试兜底。
- 🛡 **平台风险（顶层标量 bool）**：承重假设"新装回填 false"须真实 AstrBot 验证；有嵌进 routing 的降级预案。
- 🛡 **测试波及面（跨端）**：Python 冒烟 + 前端 SettingsPanel/collect fixture 两侧都要喂 `setup_confirmed=true`，两个并列审计任务。
