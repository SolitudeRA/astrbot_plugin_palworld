# 首次强制模式选择：命令闸 + 设置页引导屏（Phase 1）设计

> 关联：本功能是「让运行模式选择变成有意识、被引导的动作」的 **Phase 1**。
> Phase 2（有条件模式互转 + 转移引导）另立 spec，不在本文件范围。
> 前置已交付：模式分道 v0.9.7（`docs/superpowers/specs/2026-07-15-mode-separation-design.md`）——
> `world_mode`（single/multi，默认 single）、`single_allowed_groups` 授权群名单、`/pal whereami`、
> 设置页模式只读 badge、模式开关唯一入口=AstrBot 齿轮。

## 1. 背景与目标

**痛点（用户确认）**：默认改 single 后，用户可能装了插件、从没碰过模式开关，静默跑在可能不对的默认上而不自知；希望新装时**强制用户有意识地选一次模式**。

**平台现实（勘探结论）**：AstrBot 插件模型**没有**"配置未完成就阻塞激活/弹窗"的钩子（生命周期仅 `initialize()`/`terminate()`）；启动时无主动推送渠道（只能被动响应命令 / 打控制台日志），也拿不到会话目标。且 `world_mode` 因 **AstrBot 递归回填 schema 默认并落盘**，"接受默认的 single"与"主动选的 single"字节相同——**"用户没选过"这个状态在 `world_mode` 上不可表示**。

**目标**：在平台允许的最接近"强制"的形态下，用**独立的确认标志 + 命令闸 + 设置页引导屏**，让全新安装必须完成一次有意识的模式确认才能正常使用 `/pal`；确认入口是自定义设置页（Web UI 始终可达）。

**成功标准**：
- 全新安装：`/pal` 常规命令被闸、返回引导语；自助命令（help/whoami/whereami/confirm）仍可用；设置页显示引导屏。
- 用户在引导屏显式选 single/multi 并确认后：标志置 true、闸清、`/pal` 恢复正常、页面转正常设置。
- 已确认的安装：行为与 v0.9.7 完全一致（零回归）。

## 2. 非目标（明确划出，属 Phase 2 或不做）

- **有条件模式互转 / 转移引导**（single↔multi 的二次确认、多台切单的转移向导、link 绑定迁移为授权群名单、其余服务器数据去留）——Phase 2。
- **设置页常态可写模式**：Phase 1 里设置页**只有引导屏**这一处写 `world_mode`（首次一次性）；确认后模式恢复只读 badge、更改仍走齿轮（与 v0.9.7 一致），直到 Phase 2 加入设置页内带引导的互转。
- **引导屏配服务器**：引导屏只做"选模式 + 确认"；配服务器留给确认后的正常设置页（「连接」章）。
- **聊天内确认命令**（如 `/pal setup <mode>`）：不做；确认统一在设置页（Web UI 始终可达，逗口聊天命令负责把用户指向它）。
- **拦截齿轮裸切**：齿轮改 `world_mode` 仍是裸切、不被引导流约束（后端已有安全网：单模式检测到多台就绪→告警+只用首台，不崩不丢数据）。

## 3. 术语

- **setup 闸 / 命令闸**：`setup_confirmed=false` 时拦截非逗口 `/pal` 命令、代之以引导语的中央前置门。
- **逗口集（exempt set）**：闸放行的自助/元命令 `{help, whoami, whereami, confirm}`。
- **引导屏（onboarding screen）**：设置页在未确认时呈现的首屏，选模式 + 确认。

## 4. 架构

### 4.1 `setup_confirmed` 标志（顶层 bool，默认 false）

- 语义：用户是否已完成一次有意识的首次模式确认。默认 `false`；靠 AstrBot 回填默认→全新安装恒 `false`。
- **无用户 → 无迁移**（见既有事实：插件尚无真实用户；改默认/加键直接改，不写迁移护栏）。加一个默认 false 的新键，所有现存（皆全新）安装自然为未确认。
- 独立于 `world_mode`：不试图把 `world_mode` 做成三态；用单独标志承载"是否确认过"。

### 4.2 命令闸（chat 侧，硬闸 + 逗口）

- 位置：`main.py` 现有中央门序的**最前**一道（先于 enable/admin/授权判定）。`setup_confirmed=false` 且命令首词 ∉ 逗口集 → 直接返回 `L("setup_required")`、不进正常处理。
- 逗口集 `{help, whoami, whereami, confirm}`（扁平命令名）：放行，让用户能看说明、查身份、查 UMO。
- **web 设置页不受此闸**：闸只作用于 `/pal` 聊天命令；设置页（`register_web_api` 挂的 HTTP 端点）始终可达——引导就在那里做，故硬闸也锁不死用户。
- 门序铁律：setup 闸位于最前，未确认时一切从简、只引导。
- 引导语 `setup_required`（新 locale 键）：形如「🔧 帕鲁世界终端尚未完成首次设置。请打开插件设置页选择运行模式（单/多服务器）并确认后再使用。发送 `/pal help` 查看说明。」
- 闸读**解析后的 live 值**（挂 AppConfig），热重载后重新生效——用户确认保存触发 config reload → 闸清。

> **接口勘探待办（留给 writing-plans）**：确认当前 `main.py` 分级命令分发的确切 choke point（`_guarded` / `_dispatch_read` / `_guarded_admin` 等），把 setup 闸插在所有非逗口命令必经的最前一处，且逗口命令确实绕过。逗口命令当前是否经同一 `_guarded` 需核实。

### 4.3 配置管道（解析 / schema / 往返）

- `config.py`：`AppConfig` 加顶层字段 `setup_confirmed: bool = False`；`parse_config` 解析（`bool(raw.get("setup_confirmed", False))`，缺省/非法→False）。
- `_conf_schema.json`：顶层加 `setup_confirmed`（布尔类型**以现有 schema 布尔字段写法为准**，如 `servers.items.enabled`；`default: false`；description：「首次设置确认标志：一般由插件设置页在你完成模式选择后自动写入，通常无需手动改动。」）。放 schema 让 AstrBot 回填生效。
- `config_view.py`：`_TOP_KEYS` 加 `setup_confirmed`。**注意**：现有顶层键多为 list/object（servers/routing/permission_admins/single_allowed_groups…），`setup_confirmed` 可能是**首个顶层标量 bool**——须确认 `redact_config`/`_strip_meta` 对顶层标量原样透传、不假设每个顶层键都是 list/object（否则往返会炸）。此为 planning/实现须验证的接口点。

## 5. 组件与接口

- **后端**
  - `config.py`：`AppConfig.setup_confirmed: bool`；`parse_config` 接线。
  - `main.py`：`_SETUP_EXEMPT = {"help","whoami","whereami","confirm"}`（常量，锚定）；setup 闸方法/内联判定（入口 choke point）。
  - `locale.py`：`setup_required` 键。
  - `_conf_schema.json` / `config_view.py`：schema + TOP_KEYS。
- **前端**
  - `SettingsPanel.vue`：`ready` 之上加 `onboarding` 分支（`setup_confirmed===false` 时渲染引导屏取代正常章节）。
  - 新组件 `ModeOnboarding.vue`：两张模式卡（single/multi）+ 显式点选 + 「确认并开始」（点选前禁用）。
  - `collect.ts`：`collectBody` 增补顶层 `setup_confirmed` 回传；`SettingsState` 加字段。
  - 视觉复用已定稿的模式卡/卡片风格。

## 6. 数据流：首次引导写入

1. 设置页加载配置（GET）→ `setup_confirmed===false` → 渲染引导屏。
2. 用户点选一张模式卡（single 或 multi）→ 「确认并开始」启用。
3. 点确认 → 前端置 `state.sections.routing.world_mode = 所选` + `state.setup_confirmed = true` → 走**现有保存链路**（`collectBody` → POST save 端点 → `config_view` redact/strip → `save_config`）。
4. 插件 reload 配置 → `setup_confirmed=true` → 闸清。
5. 前端保存成功 → 切到正常设置页（落「连接」章，引导接着配服务器）。

> `world_mode` 本就被 `collectBody` 原样回传（v0.9.7 数据安全不变量）；引导屏只是把它从"隐藏只读"变成"首屏可写一次"。`setup_confirmed` 是新增的顶层回传项。

## 7. 设置页引导屏 UX

- **触发**：`ready && setup_confirmed===false`。
- **内容**：欢迎语 + 两张并列模式卡：
  - **单服务器**：唯一服务器，群授权走「授权群名单 + `/pal whereami`」。
  - **多服务器**：多台服务器，用 `/pal link` 绑定切换。
- **强制有意识选择**：不预选任何一张；「确认并开始」在显式点选前**禁用**。
- **确认后**：转正常设置页（模式恢复只读 badge + 齿轮，与 v0.9.7 一致）。底部小字：模式日后可在 AstrBot 齿轮更改（Phase 2 会加设置页内带引导互转）。
- **无"跳过"**：唯一出路是选 + 确认（否则失去"强制"意义）。

## 8. 错误处理与边界

- 齿轮把 `setup_confirmed` 手改回 false → 闸复活（schema 注明勿手改，可接受）。
- 确认后热重载 → 闸清（走现有 reload 路径）。
- 确认后删光服务器 → 仍算已确认（闸不复活，合理——已完成一次有意识确认）。
- 保存失败（save_config 异常/网络）→ 引导屏保持、提示重试，不误置 confirmed（沿用现有保存 UX 的错误处理）。
- 逗口命令在未确认时正常工作，帮助用户走向设置页。

## 9. 测试策略

- **⚠️ 头号铁律（直接来自 v0.9.7 全分支终审教训）**：新增 setup 闸后，`tests/unit/namespace_runtime_smoke_test.py` 的 `_raw_config` **必须设 `setup_confirmed=true`**，否则全部被闸命令短路成引导语、深支覆盖再次静默丢失（与该测试固定 `world_mode=multi` 同理）。plan 必须显式处理。
- **波及面有界**：闸在 `main.py` handler 层，只影响"经插件 handler 驱动命令"的测试（命名空间冒烟 + 少量 main 层用例）；直接调 `Commands`/service 的单测不过闸、不受影响。planning 时须审计所有经 handler 驱动命令的测试是否需补 `setup_confirmed=true`。
- **新增测试**：
  - 闸：`setup_confirmed=false` → 被闸命令返回 `setup_required`；逗口集（help/whoami/whereami/confirm）放行。`true` → 正常。门序：setup 闸先于 enable/admin。
  - 配置：`setup_confirmed` 默认 false、解析 true/false、`config_view` 往返闭合。
  - 前端：未确认显引导屏 / 已确认隐藏；点选+确认写 `world_mode`+`setup_confirmed`；`collectBody` 无条件往返 `setup_confirmed`；确认按钮点选前禁用。
  - 锚定：`_SETUP_EXEMPT` 常量 ↔ 测试 literal 全等。

## 10. 锚定约束（沿用项目铁律）

- 逗口集 `_SETUP_EXEMPT` 单一真相源 + 测试 literal 全等。
- 相对导入红线；提交不出现 Claude；前端改源后 `npm run build` 保 `pages/settings` no-drift + LF。
- README/docs 改中文用词须核 `tests/unit/readme_test.py` 锚点。

## 11. 版本

Phase 1 单独一版 **v0.9.8**：`metadata.yaml` / `main.py @register` / `palworld_terminal/__init__.py __version__` / `README` badge / `phase1_smoke_test.py` / `skeleton_test.py` 六源全等（v0.9.7 终审已确认版本断言有此六处）。

## 12. 依赖顺序 / 风险

- 依赖顺序：标志解析（config）→ schema+config_view 往返 → 命令闸（main）→ 前端引导屏+collect → 版本+文档+终检。
- **头号风险**：setup 闸的测试波及面——须在 plan 里把"经 handler 驱动命令的测试补 `setup_confirmed=true`"作为专门任务/审计项，避免深支覆盖静默丢失（复用 v0.9.7 教训）。
- 次风险：闸 choke point 定位——须接口勘探确认插桩点，保证所有非逗口命令必经、逗口命令确实绕过、门序在最前。
