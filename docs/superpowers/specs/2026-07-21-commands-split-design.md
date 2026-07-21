# Spec B：拆分 commands.py god 对象（953 行 → 协调器 + 两焦点单元）

> 状态：设计定稿（待对抗复核）｜日期：2026-07-21｜分支：feat/commands-split（栈于 feat/presentation-decoupling @0c1c78b 之上）
> 系列：架构解耦三部曲之 **B**。A（presentation 解耦）= PR #29；C（适配器解耦）待启。本 spec 只做 B。

## 1. 目标与非目标

### 目标
把 `presentation/commands.py`（953 行、`Commands` 类 ~50 方法的 god 对象）按职责拆成聚焦文件：把**两个最重、最需隔离的单元**——查询 handler 与写安全心脏——抽成独立协作类，`Commands` 瘦身为协调器 + 门面。

**硬约束：零运行时行为变化、零用户可见输出字节变化。** 纯结构重构——golden `.txt` + 全量 1194 测试是安全网。

### 非目标（明确排除）
- 任何行为/语义/输出字节改变；任何新功能。
- 改动 `main.py` / `container.py` 对 `Commands` 的调用契约（**门面必须保留**）。
- 门控/门序/隐私逻辑的任何改动（只搬位置，不改逻辑）。
- 适配器解耦（Spec C）。

## 2. 现状：Commands god 对象的六类职责（953 行）

| 职责 | 方法（当前行号） | 去向 |
|---|---|---|
| 查询 handler | status/online/world/rules/guilds/guild/bases/base/events/today/rank/player(188-356)、bind/me/unbind_self(363-437) | **ReadCommands** |
| 读共享 helper | _resolve_world(132)、handle_query(154)、_guilds_bases_on/_is_strict/_fold_limit(166-186)、_server_anchor(357) | **ReadCommands** |
| 写编排（安全心脏·门序铁律） | admin_write(675)、confirm(820)、_store_pending(805)、_pending_phrase(791)、_render_result(871)、_render_admin_ok(906)、clear_pending(941) | **AdminWriteFlow** |
| 分发 + 门控 | _dispatch_read(481)、world_grp/guild_grp/player_grp/server_grp(506-532)、_admin_locked(447)、_group_help(459)、_rebuild_arg(472) | **Commands（协调器）** |
| link 管理 | link(534)、link_list(576)、link_add(599)、link_remove(612)、_server_reachable(562) | **Commands（协调器）** |
| meta + gating | help(625)、whoami(634)、whereami(642)、is_plugin_admin(946)、admin_denied(949) | **Commands（协调器）** |

**耦合事实（决定拆法）：**
- 分发器 `_dispatch_read` 用 `getattr(self, method)` 反射调读 handler（method 名来自 `DISPATCH`）；`server_grp → self.admin_write`；`link → getattr(self, method)`。
- **测试大量 monkeypatch `cmds.admin_write` / `cmds.status` 等并靠 dispatcher/server_grp 调到它**（如 commands_dispatch_test patch admin_write 避开真体）。→ **铁律：dispatcher/server_grp 的 `getattr(self, method)`/`self.admin_write` 反射目标必须保持 `self`（不改指 `self._reads`/`self._writes`），否则 monkeypatch 被绕过 = 静默行为变化。** 委派 stub 本身即反射目标（未 patch 时委派子对象，被 patch 时用 patch）。
- `main.py` 调 `Commands` 的：world_grp/guild_grp/player_grp/server_grp/link/rank/online/me/whoami/whereami/help/confirm/is_plugin_admin/admin_denied；`main.py`（热重载路径）调 clear_pending。**这些是必须保留的公共门面。**
- 测试**直接触达/monkeypatch** `.admin_write`（52 处，其中 dispatch 测 1 处 patch）、`._resolve_world`（5，全是 patch 赋值）、`.handle_query`（2，直调无 patch）、及读 handler（status/today/guilds/bases/guild/events/base）——9 个测试文件直接构造 `Commands(...)`。委派 stub 保住**外部直调**，但 **monkeypatch 有存活/失效之分（见 §7.1）——`_resolve_world` 的 5 处 patch 会失效、须改测点**。
- `_world_mode`、`_fold_limit`（均纯 cfg 读取器）被**读区与协调器共用**（_world_mode 8 处：读区 player/me/bind 353/360/397/414/425 + 协调器 _group_help:464/help:631/whereami:654；_fold_limit 跨 ReadCommands 读 handler 与协调器 link_list:596）→ **二者均提升为模块级函数** `_world_mode(cfg)` / `_fold_limit(cfg)`（入 command_support），两侧都调 `_world_mode(self._cfg)` / `_fold_limit(self._cfg)`，消除跨类方法共享、无需 stub。`_is_strict`/`_guilds_bases_on`（仅读区用）留 ReadCommands 私有方法。
- `@_gated` 装饰 11 个读方法（当前行 233-418），装饰器随方法搬到 ReadCommands。

## 3. 文件结构：3 协作类 + 1 避环支撑模块

```
presentation/
  command_support.py   (新·小)  模块级共享 helper（避免 commands↔read/write 导入环）
  read_commands.py     (新)     class ReadCommands —— 查询 handler + 读 helper
  admin_write_flow.py  (新)     class AdminWriteFlow —— 写安全心脏（门序铁律隔离）
  commands.py          (瘦身)   class Commands —— 协调器（分发/门控/link/meta/gating）+ 门面委派
```

依赖方向（无环 DAG）：`commands → {read_commands, admin_write_flow, command_support}`；`read_commands → command_support`；`admin_write_flow → command_support`；`command_support → {shared.command_registry, application.command_permissions, application.routing_service, presentation.locale}`（**不含 formatters**——support 成员不调 format_*，加了会触 ruff F401）。support 绝不 import 三个类文件。read_commands/admin_write_flow 各自另 import 所需的 presentation.formatters/application.query_service 等叶子（已核不成环）。

## 4. `command_support.py`（避环支撑模块）

把当前 commands.py 顶部的**跨单元共享**模块级 helper 原样搬入（逻辑零改）：

- `feature_disabled_text(path)` —— _gated + _dispatch_read 共用。
- `_gated(fn)` —— 读方法装饰器（读 `self._cfg`、`METHOD_PATH`、`effective_enabled`）；ReadCommands 方法用它。
- `_render_routing_error(err, params)`（A 引入）—— 被 `_resolve_world`（迁 ReadCommands）**与** admin_write 内联/`_render_result`（迁 AdminWriteFlow）共用 → 真跨单元共享，入 command_support。
- `_world_mode(cfg) -> str` —— 由 `Commands._world_mode` 方法提升为**模块函数**，读区与协调器都调 `_world_mode(self._cfg)`（消除跨类方法共享）。
- `_fold_limit(cfg) -> int` —— 同理由 `Commands._fold_limit` 方法提升为**模块函数**（唯一被协调器 link_list:596 触达的读 helper，故须共享）；ReadCommands 读 handler 与协调器 link_list 都调 `_fold_limit(self._cfg)`。
- `_SENDER_METHODS = frozenset({"bind","me","unbind_self"})` —— _dispatch_read 据此决定传参形态。

import 来源：`shared.command_registry.METHOD_PATH`、`application.command_permissions.{effective_enabled, upstream_unavailable}`（`feature_disabled_text` 体内调 `upstream_unavailable(path)`，漏则 NameError）、`application.routing_service.RoutingError`、`presentation.locale.L`。**无 cycle**（不 import commands/read_commands/admin_write_flow）。

> 仅被 AdminWriteFlow 用的 `_parse_shutdown_seconds`、`_target_phrase` **不入 support**，直接搬进 `admin_write_flow.py`（就近原则）。

## 5. `read_commands.py` — `class ReadCommands`

**职责**：全部查询 handler + 读共享 helper。**方法体逐字搬迁**（含 `@_gated` 装饰器、注释、golden 对齐的措辞），只改 `self._X` 引用到本类持有的同名依赖、`self._world_mode()`→`_world_mode(self._cfg)`、`self._fold_limit()`→`_fold_limit(self._cfg)`（两模块函数 from command_support）。

**构造**：
```python
class ReadCommands:
    def __init__(self, routing, query, repo, cfg, clock, salt: bytes = b"") -> None:
        self._routing = routing; self._query = query; self._repo = repo
        self._cfg = cfg; self._clock = clock; self._salt = salt
```
（deps 由 read 区实测依赖确定：self._routing/_query/_repo/_cfg/_clock/_salt。）

**含方法**：`_resolve_world`、`handle_query`、`_guilds_bases_on`、`_is_strict`、`_server_anchor`、status、online、world、rules、guilds、guild、bases、base、events、today、rank、player、bind、me、unbind_self。（`_fold_limit` 不在此——已升为 command_support 模块函数，见 §4。）

**@_gated**：11 个读方法的装饰器逐字保留，从 `command_support import _gated`。`_gated` 读 `self._cfg`（ReadCommands 有）→ 生效值判定不变。

## 6. `admin_write_flow.py` — `class AdminWriteFlow`

**职责**：服务器管控写编排——**本 feature 安全模型的心脏，门序铁律**。隔离进独立文件后，安全逻辑（admin 硬门先于 feature、二次确认 claim-then-execute、审计）可审计性大增。**逻辑零改，逐字搬迁**。

**构造**：
```python
class AdminWriteFlow:
    def __init__(self, admin_service, routing, confirmations, cfg, clock) -> None:
        self._admin = admin_service; self._routing = routing
        self._confirmations = confirmations; self._cfg = cfg; self._clock = clock
```
（deps 由 admin 区实测依赖确定：self._admin/_routing/_confirmations/_cfg/_clock；无 self._salt。）

**含方法**：`admin_write`、`confirm`、`_store_pending`、`_pending_phrase`、`_render_result`、`_render_admin_ok`、`clear_pending` + 就近搬入的**模块函数 `_parse_shutdown_seconds`、`_target_phrase`** 及**模块常量 `_SHUTDOWN_MAX_SECONDS`（_parse_shutdown_seconds 用）、`_ACTION_LABEL`（_pending_phrase/_render_result/_render_admin_ok/confirm 用）**——这两常量纯 admin 用、协调器/读区零引用，漏迁则 NameError。

## 7. `commands.py` — `class Commands`（协调器 + 门面）

**协调器逻辑（留下、逻辑零改）**：分发（_dispatch_read/world_grp/guild_grp/player_grp/server_grp）、门控（_admin_locked/_group_help/_rebuild_arg）、link 管理（link/link_list/link_add/link_remove/_server_reachable）、meta（help/whoami/whereami）、gating（is_plugin_admin/admin_denied）。`_world_mode()` 调用改 `_world_mode(self._cfg)`（from command_support）。

**装配（`__init__` 签名不变，container.py 零改动）**：
```python
class Commands:
    def __init__(self, routing, query, repo, cfg, clock, salt=b"", admin_service=None, confirmations=None):
        self._routing = routing; self._repo = repo; self._cfg = cfg; self._clock = clock
        self._reads = ReadCommands(routing, query, repo, cfg, clock, salt)
        self._writes = AdminWriteFlow(admin_service, routing, confirmations, cfg, clock)
```

**分发/内部调用一律不动（铁律）**：`_dispatch_read` 的 `getattr(self, method)`、`server_grp` 的 `self.admin_write(...)`、`link` 的 `getattr(self, method)`/`self.link_list`——**全部保持 `self`，一字不改**。这些 `self.X` 命中的是下方的委派 stub（未 patch 时委派子对象，被 patch 时用 patch）——保住 monkeypatch 语义 = 零行为变化。`_SENDER_METHODS` 分支不变。

**门面委派 stub（保住公共 API + 外部直调面 + 反射目标）**——Commands 为下列搬出方法保留 1 行委派方法，签名与原方法逐字一致：
- reads → 委派 `self._reads.X`：`_resolve_world`、`handle_query`、status、online、world、rules、guilds、guild、bases、base、events、today、rank、player、bind、me、unbind_self。
- writes → 委派 `self._writes.X`：`admin_write`、confirm、clear_pending。
- （`world_grp`/`guild_grp`/`player_grp`/`server_grp`/`link`/link_list/link_add/link_remove/`_server_reachable`/help/whoami/whereami/is_plugin_admin/admin_denied 是协调器**真实现**，非委派。）
- **不 stub 的内部 helper**：`_guilds_bases_on`/`_is_strict`/`_server_anchor`（经 grep 确认仅读区内用、无外部/反射触达）留 ReadCommands 私有（YAGNI，不硬造 stub）。`_fold_limit`/`_world_mode` 已升为 command_support 模块函数（§4），非 stub。

> 委派 stub 让 Commands 表面仍列被调用的方法名（皆 1 行），但**方法体**（953 行逻辑）已分入 3 焦点文件、写安全心脏独立可审。这是本 spec 认可的权衡（用户定案「目标提取」+ 零行为/低风险优先）。

### 7.1 monkeypatch 存活/失效判据（对抗复核 Blocker：决定测试是否需改）

委派 stub 保住 monkeypatch **仅当 patch 的方法其调用方仍在 Commands**。判据：

| patch 的方法 | 调用方（谁调它） | 拆分后 self | patch 是否存活 | 处置 |
|---|---|---|---|---|
| `admin_write` | server_grp（**留 Commands**）| server_grp 的 self = Commands，`self.admin_write` 命中 stub | ✅ 存活 | 不改测试 |
| `bind`/`unbind_self` | _dispatch_read getattr(**self**=Commands) | 命中 stub | ✅ 存活 | 不改测试 |
| `handle_query` | 测试直调（无 patch，2 处）| — | — | 委派 stub 够 |
| **`_resolve_world`** | 读 handler（bind/me/player/rank/guilds/guild/bases/base）**随 handler 迁 ReadCommands**，内部调 `self._resolve_world`（self=ReadCommands）| **绕过 Commands stub** | ❌ **失效** | **须改测点** |

**Blocker 修法（必做）**：5 个测试文件把 `c._resolve_world = _rw` 改为 **`c._reads._resolve_world = _rw`**（patch 打到 ReadCommands 实例，读 handler 内部 `self._resolve_world` 才命中）：
- `commands_me_bind_test.py:45`（→ c.bind/c.me/c.unbind_self）
- `commands_player_test.py:36`（→ c.player）
- `commands_rank_test.py:23`（→ c.rank）
- `commands_guild_test.py:63`（→ c.guilds/guild/bases/base）
- `rank_total_test.py:133`（→ c.rank）

**根因**：§3 DAG 禁止 ReadCommands→Commands 反向引用，故 _resolve_world 不能留 Commands 让子对象回调；它随读 handler 迁 ReadCommands，patch seam 也随之迁到 `c._reads`。这是**诚实的非零测试改**（5 文件各 1 行），不是零改——`_resolve_world` 的 stub 仍保留（供外部直调的 5 处 `._resolve_world` 断言/调用），但 patch 语义靠改测点保真。

## 8. 约束与不变量
- **零字节变化**：全部 golden `.txt` 输出字节不变（最终裁判）。
- **门面保面**：main.py/container 调用契约、测试触达面（含 52 处 admin_write）经委派 stub 全保留 → main.py/container 零改、测试近零改。
- **反射目标铁律**：`_dispatch_read`/`server_grp`/`link` 的 `getattr(self, …)`/`self.admin_write` **保持 `self` 一字不改**（命中委派 stub），保 monkeypatch 语义；`DISPATCH` 真相源不变。改指 `self._reads`/`self._writes` = 静默行为变化，禁止。
- **门控/门序/隐私逻辑逐字搬迁不改**：`@_gated`、_admin_locked、admin_write 门序、confirm claim-then-execute、隐私收敛——只换文件，不换逻辑。
- **无导入环**：共享 helper 下沉 command_support；DAG 见 §3。
- 相对 import；AstrBot 命名空间安全（新文件相对 import，无绝对自导入）。
- commit 无 Claude 署名；不 bump 版本。

## 9. 测试策略
- **安全网**：全部 golden `.txt` 字节不变 + 全量 1194 passed。门面委派保住被调用面，绝大多数测试**不动**——**唯一例外**：§7.1 的 **5 个测试文件须把 `c._resolve_world = _rw` 改指 `c._reads._resolve_world`**（monkeypatch seam 随读 handler 迁 ReadCommands）。这是诚实的非零测试改（5 文件各 1 行），非「零测试改」。
- **可能的机械连带**：新文件的相对 import 若触发 ruff I001，跑 `ruff check .`（**全仓**）修（A 的门教训）；新 `command_support.py`/`read_commands.py`/`admin_write_flow.py` 三文件须被绝对自导入静态守卫覆盖（rglob 已自动，核实）。
- **新增聚焦单测（增强，非替代）**：ReadCommands / AdminWriteFlow 现可脱离 Commands 直接构造测试——**可选**加少量直接单测证明可独立测试（YAGNI：不硬造，若自然则加）。
- **反射防回归**：现有 `command_registry` meta 测试（METHOD_PATH 覆盖全 @_gated 方法）+ dispatch 测试仍绿，证明反射目标保持 `self`（命中委派 stub）后 getattr 命中不变、monkeypatch 语义不变。

## 10. 实施相位（建议，供 writing-plans 细化）
1. **相 1 — command_support.py**：抽共享模块 helper（feature_disabled_text[含 upstream_unavailable]/_gated/_render_routing_error/_SENDER_METHODS + `_world_mode(cfg)`、`_fold_limit(cfg)` 两模块函数）；commands.py 改为 import 之 + 内部 `_world_mode()`/`_fold_limit()` 调用改 `_world_mode(self._cfg)`/`_fold_limit(self._cfg)`。此相后 commands.py 仍单文件、全绿（纯 helper 外移 + 两处方法→函数）。
2. **相 2 — read_commands.py**：搬全部读 handler + 读 helper 成 ReadCommands；Commands.__init__ 建 self._reads；**_dispatch_read 的 getattr(self, …) 不动**，为搬出的读方法加委派 stub（stub 即反射目标）。全绿（golden 兜底 + dispatch/gating 测试证反射命中不变 + monkeypatch 测试证 patch 仍生效）。
3. **相 3 — admin_write_flow.py**：搬写编排成 AdminWriteFlow；Commands.__init__ 建 self._writes；**server_grp 的 self.admin_write(...) 不动**，为 admin_write/confirm/clear_pending 加委派 stub。全绿（commands_admin_write_test 兜底门序+字节 + patch admin_write 的 dispatch 测试仍生效）。
4. **相 4 — 收尾**：commands.py 净剩协调器+门面；no-drift/守卫/全仓 ruff/mypy 全绿 + golden 字节对比 + 终审。

每相独立可跑、独立绿（golden + 全量安全网贯穿）。

## 11. 验收标准
- [ ] commands.py 从 953 行降至协调器规模（~350 行含委派 stub）；ReadCommands/AdminWriteFlow 各自焦点文件。
- [ ] 全部 golden `.txt` 字节不变；全量 1194 passed（+ 可选新单测）+ `ruff check .`（全仓）+ mypy 全绿。
- [ ] main.py / container.py **零改动**（门面契约保留）；仅 §7.1 的 5 个测试文件改 `_resolve_world` patch 测点。
- [ ] 无导入环（command_support DAG）；三新文件被绝对自导入守卫覆盖。
- [ ] 门控/门序/隐私逻辑逐字未改（admin_write 门序、@_gated、confirm claim-then-execute、隐私收敛）——仅换文件。
- [ ] `_dispatch_read`/`server_grp`/`link` 反射目标**保持 `self`**（命中委派 stub）后 dispatch/gating 测试全绿、monkeypatch 语义保真。
