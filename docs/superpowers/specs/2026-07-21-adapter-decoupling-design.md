# Spec C：适配器解耦（消除 application → adapters 反向依赖）

> 状态：设计定稿（待对抗复核）｜日期：2026-07-21｜分支：feat/adapter-decoupling（栈于 feat/commands-split @6c20b23）
> 系列：架构解耦三部曲之 **C**。A（presentation 解耦）= PR #29；B（拆 commands.py）= PR #30。本 spec 只做 C。

## 1. 目标与非目标

### 目标
彻底消除 `application` 层对 `adapters` 层的反向依赖。当前 application 有 **12 处** `from ..adapters.*` import（+1 infrastructure），全部清零：纯逻辑/契约迁到中立层（domain/shared），有状态的 Repository 依赖抽象为 Protocol 端口（adapter 结构化满足）。

**硬约束：零运行时行为变化、零用户可见输出字节变化。** 纯结构重构——golden `.txt` + 全量 1194 测试是安全网。

### 非目标（明确排除）
- 任何行为/语义/输出字节改变；任何新功能。
- 改动 Repository 的实现或 DB schema。
- presentation 层（Spec A/B 已完成）。

## 2. 现状：12 处 application→adapters（+1 infrastructure），5 类

| 类 | import | 位置 | 去向 |
|---|---|---|---|
| Repository 类型 | `sqlite_repository.Repository` | query/report/routing/event/name_resolver（5）+ container | **application/ports.py 分离端口**（重标注；Repository 结构化满足） |
| privacy_filter 纯函数 | `hash_user_id/quantize_cell/bucketize_ping` | admin/base/guild/player（4）+ presentation/read_commands + container | **domain/privacy.py**（隐私=域策略；含 PrivacyConfig 迁 domain 解环） |
| RestResponse 类型 | `palworld_rest.RestResponse` | admin/snapshot（2）+ infrastructure/scheduler（1）+ container（1）+ adapters 自定义 | **shared/rest.py**（传输 DTO，三层共用；palworld_rest re-export 保旧路径） |
| _ADMIN_PATH 私有常量 | `palworld_rest._ADMIN_PATH` | admin_service（reach-in `if path not in _ADMIN_PATH`）| **domain 公开常量 ADMIN_ACTIONS**（域概念，干掉私有 reach-in） |
| normalize_players 自由函数 | `normalizer.normalize_players` | admin_service（:203 解析 /players 定位 kick/ban 目标）| **注入 callable**（与 snapshot 已有注入 normalizer 一致模式） |

> snapshot/base/guild/player_service 不 import Repository 类型（duck-type，已 import-clean）；base/guild/player 的 adapters 依赖仅 privacy_filter（Part 1.1 处理）。admin_service 四类 adapters 依赖全在（Part 1 全处理 + AuditPort 标注）。

## 3. 架构：解耦后依赖方向

```
domain  ← infrastructure ← adapters
  ↑           ↑              ↑
  │           │              │(adapters 实现 application 定义的端口)
shared ───────┤              │
  ↑           │              │
application ──┴──────────────┘   (application 定义 ports.py；adapters.Repository 结构化满足)
  ↑
presentation
```

本 spec 后 application 对 adapters 的箭头**全部消失**。adapters 反过来依赖 application 的端口契约 + domain/shared（正确方向：外层依赖内层抽象）。

## 4. Part 1 — 纯逻辑/契约迁移

### 4.1 privacy_filter → `domain/privacy.py`（+ PrivacyConfig 迁 domain）

**动作**：
- `adapters/privacy_filter.py` → `domain/privacy.py`（内容原样搬：`hash_user_id`/`bucketize_ping`/`quantize_cell`/`_hash_or_none`/`redact_players`/`redact_game_data`）。**删除 `adapters/privacy_filter.py`（不留 shim）**——它本就不该在 adapters（无 IO），迁 domain 后彻底移除。
- **解 config 环**：privacy_filter import `config.PrivacyConfig`，而 `config → application.command_permissions`，故 privacy 若在 domain 直接 import config 会让 **domain 经 config 依赖 application（违反 domain 最内层）**。解法：把 `class PrivacyConfig`（config.py:112）**迁到 domain**（放 `domain/privacy.py`），迁后 `domain/privacy` 只依赖 domain 内部（enums/models）——无 config 依赖、无环（config→domain 本已存在 domain.enums.AccessMode，加 domain.privacy.PrivacyConfig 同向无新环）。
- **PrivacyConfig re-export 不变量（复核 Major）**：`PrivacyConfig` 的**生产侧消费者是 2**（domain/privacy + config），但**约 28 个测试文件** `from palworld_terminal.config import PrivacyConfig`。config.py 迁移后**必须保留模块级 `from .domain.privacy import PrivacyConfig`**（config.py:220 的 `AppConfig.privacy` 字段注解 + :501 的构造本就强制 config import 它 → `config.PrivacyConfig` re-export 自动成立）→ 这 ~28 测试**零改动**。**铁律：不得把该 import 挪进函数局部作用域**，否则 re-export 失效、28 文件集体 ImportError。
- **重指消费者 import**：
  - 生产代码：`application/{admin,base,guild,player}_service.py` 的 `from ..adapters.privacy_filter import ...` → `from ..domain.privacy import ...`；`presentation/read_commands.py` 同理；`container.py:9/:129` 的 **`_privacy_mod` 模块注入**改 `from .domain import privacy as _privacy_mod`（这是**模块整体注入**给 SnapshotService，非函数 import）；config.py 构造 PrivacyConfig 改从 domain import。
  - **测试连带（诚实计数）**：privacy_filter 是本 spec 唯一「删除式迁移」适配器，约 **12 个测试文件**须重指旧路径——3 个直接 import 函数（`privacy_filter_{primitives,players,game_data}_test`）、9 个以 `from ..adapters import privacy_filter as privacy_mod` 形式注入给 Snapshot（`cache_wiring`/`player_uncertain`/`pipeline` 集成 + `snapshot_*` 单测 6 个）。以 grep 全量为准逐一重指 domain.privacy。

### 4.2 RestResponse → `shared/rest.py`

**动作**：
- 新建 `shared/rest.py`，把 `RestResponse` dataclass（palworld_rest.py:28-34，6 字段 ok/status/data/duration_ms/payload_bytes/error）**原样搬入**。它只需 `from dataclasses import dataclass` + `from typing import Any`（零重依赖、叶子）。
- `adapters/palworld_rest.py`：删 RestResponse 定义，改 `from ..shared.rest import RestResponse`（adapter 构造/返回它——此 import 天然 re-export，`palworld_rest.RestResponse` 仍可解析）。
- 重指消费者：`application/{admin,snapshot}_service.py`、`infrastructure/scheduler.py`、**`container.py:12`**（`from .adapters.palworld_rest import PalworldRestClient, RestResponse` → 拆成 `from .adapters.palworld_rest import PalworldRestClient` + `from .shared.rest import RestResponse`；container.py:172/178/185 的 RestResponse 类型标注不变）。均改从 `shared.rest` import（复核 Minor：container 原漏列）。
- RestResponse 放 shared（非 application）是因 **infrastructure/scheduler 也消费它**，放 application 会致 infrastructure→application 越界；shared 三层可依赖。
- 测试若从旧路径 `adapters.palworld_rest import RestResponse` 消费：palworld_rest 的 re-export 天然保住（其仍 import RestResponse 构造）→ 这类测试零改动；以 grep 全量确认无遗漏。

### 4.3 _ADMIN_PATH → domain `ADMIN_ACTIONS`

**动作**：
- 把 `_ADMIN_PATH = frozenset({...})`（palworld_rest.py:25）**迁 domain**（如 `domain/enums.py` 尾部）为公开常量 `ADMIN_ACTIONS`（合法 admin 写动作集=域概念）。
- `adapters/palworld_rest.py` 若仍用则 `from ..domain.enums import ADMIN_ACTIONS`。
- `admin_service.py:66` 的 `if path not in _ADMIN_PATH` 改 `if path not in ADMIN_ACTIONS`（`from ..domain.enums import ADMIN_ACTIONS`）——干掉对 adapter 私有符号的 reach-in。

### 4.4 normalize_players 注入

**动作**：
- `admin_service.__init__` **末位增必填参数** `normalize_players`（callable，签名 `(raw: Mapping, now: int) -> list[dict]`），存 `self._normalize_players`。**不设 adapter 默认值**——默认指向 `adapters.normalizer.normalize_players` 会把正要删的 import 重新引回 admin_service、抵消解耦，故必填。
- `admin_service.py:203` 的 `normalize_players(resp.data, now)` 改 `self._normalize_players(resp.data, now)`。删 `from ..adapters.normalizer import normalize_players`。
- **6 处构造点全部追加 `normalize_players=` kwarg（复核 Major：必填参数破坏面，原 spec 只列 container）**：
  - `container.py:141`：传 `normalizer.normalize_players`（container 在 adapters 边界注入，与 snapshot 已注入 `_normalizer_mod` 一致模式）。
  - `tests/unit/admin_service_test.py:60/93/143/192/263`（5 处 6-kwarg 构造）：追加 `normalize_players=`。**其中 `:143`/`:263`（`_svc_players` 系列 = resolve_target/kick 路径，`fetch` 返回 `{"players": ...}`）会真正调到注入的 callable，须传入 `adapters.normalizer.normalize_players`（测试层可 import adapters）以保注入等价**；其余不触达该路径的构造可传该真函数或等价桩。
  - `tests/unit/commands_admin_write_test.py:106`（第 6 处，同形态）：追加 `normalize_players=`。

## 5. Part 2 — RepositoryPort（分离端口）

**动作**：新建 `application/ports.py`，定义 4 个 Protocol（`@runtime_checkable` 可选），每个端口的方法签名**逐字复制自 Repository 对应 public 方法**（实现期从 `adapters/sqlite_repository.py` 抄准签名与返回类型）：

| 端口 | 消费 service | 方法（名，签名照 Repository 抄） |
|---|---|---|
| `ReadRepositoryPort` | query/report/name_resolver | get_hidden_keys, get_open_session, get_player, get_player_by_name, latest_base_observation, latest_metric, latest_observation, list_bases, list_events, list_guilds, list_open_sessions, list_players_by_level, list_players_by_name, peak_online, sessions_in_day, total_durations, world_day_bounds（17） |
| `WriteRepositoryPort` | event_service | insert_event, peak_online（2） |
| `RoutingRepositoryPort` | routing_service | get_allowed, get_binding_active, list_group_servers, revoke, set_active（5） |
| `AuditRepositoryPort` | admin_service | get_current_world, insert_audit（2） |

**重标注（6 处）**：
- `query_service.py` / `report_service.py`：`repo: Repository` → `repo: ReadRepositoryPort`；删 `from ..adapters.sqlite_repository import Repository`，改 `from .ports import ReadRepositoryPort`。
- `name_resolver.py`：自由函数的 `repo: Repository` 参数 → `repo: ReadRepositoryPort`；同上改 import。
- `event_service.py`：`repo: Repository` → `repo: WriteRepositoryPort`。
- `routing_service.py`：`repo: Repository` → `repo: RoutingRepositoryPort`。
- `admin_service.py`：`self._repo` 标注为 `AuditRepositoryPort`（admin 当前不 import Repository，此为新增类型标注，从 `.ports` import）。

**Repository 结构化满足**：`adapters/sqlite_repository.Repository` 无需继承/声明——mypy 在各 service 标注处（传入 Repository 实例）自动校验结构化子类型一致；签名漂移即 mypy 报错（=防漂移守卫）。`container.py` 仍构造 `Repository(...)` 传入各 service（Repository 满足各端口）。

> 端口重叠澄清（复核 Minor）：**peak_online** 是真·双端口重叠——ReadRepositoryPort 与 WriteRepositoryPort 各自独立列出，Repository 同时满足二者。**get_current_world** 仅 AuditRepositoryPort 列出；另一消费者 `snapshot_service` 按 §2 保持 **duck-type 不建端口**（其 repo 参数无标注），故不是「各端口独立列同名方法」的重叠。

## 6. Part 3 — application→adapters 静态守卫

新增 `tests/unit/adapter_layering_guard_test.py`（同 Spec A 的 layering_guard 手法）：扫 `palworld_terminal/application/*.py`，断言无 `from ..adapters` 与 `import palworld_terminal.adapters`。写完应即通过（Part 1/2 已清零）。植入 offender→FAIL→删→PASS 咬合自证。

## 7. 约束与不变量
- **零字节变化**：全部 golden `.txt` 输出字节不变。
- **config 环解法**：PrivacyConfig 迁 domain，domain/privacy 不依赖 config（§4.1）。核实迁后无 domain→config→application 环。
- **RestResponse 放 shared 非 application**：因 infrastructure/scheduler 消费它，放 application 越界（§4.2）。
- **re-export 不变量（铁律）**：①config.py 迁移后须模块级 `from .domain.privacy import PrivacyConfig`（供 AppConfig.privacy 注解 + 构造），保住 `config.PrivacyConfig` 供 ~28 测试零改动——不得挪进函数局部；②palworld_rest 须 `from ..shared.rest import RestResponse`（供构造），保住 `palworld_rest.RestResponse` 供旧路径消费者零改动。二者是 re-export 载重不变量，撤除即批量 ImportError。
- **mypy 结构化守卫**：Repository 满足 4 端口经 mypy 在标注处校验；签名漂移即报错。
- **注入一致性**：normalize_players 注入模式与 snapshot 已有 normalizer 注入一致。
- 相对 import；AstrBot 命名空间安全（新文件相对 import，无绝对自导入，被 rglob 守卫覆盖）。
- commit 无 Claude / Co-Authored-By；不 bump 版本。

## 8. 测试策略
- **安全网**：全部 golden `.txt` 字节不变 + 全量 1194 passed。纯迁移/重标注，行为零变化；**测试计数级绝大多数不动，但文件级有明确连带（下）**。
- **诚实测试连带（复核修正）**：
  - **privacy_filter 删除式迁移 → ~12 测试文件重指** domain.privacy（3 直接 import 函数 + 9 模块注入给 Snapshot）——本 spec 唯一真旧路径 ImportError 源，grep 全量逐一重指。
  - **normalize_players 注入 → 6 处 AdminService 构造点追加 `normalize_players=` kwarg**（container:141 + admin_service_test:60/93/143/192/263 + commands_admin_write_test:106）；`:143`/`:263`（resolve_target/kick 路径）须传真 normalize_players 保注入等价。
  - **PrivacyConfig → ~28 测试文件零改动**（靠 config re-export 不变量，§4.1）。**RestResponse → 旧路径消费者零改动**（靠 palworld_rest re-export）。
- **注入等价回归网（复核修正——原 §8 归错文件）**：真正跑到注入 callable 的是 **`admin_service_test.py` 的 `resolve_target` 三测**（`test_resolve_target_by_name_unique/_multi/_none`，经 `_svc_players` 喂 `{"players":...}`），**非 `commands_admin_write_test`**（其 routing 先失败、根本不触达 fetch/normalize_players）。这三测传真 normalize_players 后仍绿 = 注入等价。
- **mypy 严格**：端口重标注后 `mypy palworld_terminal` 全绿 = Repository 结构化满足 4 端口的证明（防漂移）。
- **新守卫咬合自证**：adapter_layering_guard 植入 offender 验真咬合（§6）。
- 新文件的 ruff I001 跑 `ruff check .`（全仓）修；三新文件（domain/privacy、shared/rest、application/ports）被绝对自导入守卫（rglob）覆盖。

## 9. 实施相位（建议，供 writing-plans 细化）
1. **相 1 — privacy_filter → domain/privacy.py + PrivacyConfig 迁 domain**：迁移 + 删 adapters/privacy_filter.py + 重指 app 4 service/read_commands/container(_privacy_mod 模块注入)/config；**config.py 保留 `from .domain.privacy import PrivacyConfig` re-export 不变量**；**~12 测试文件重指 domain.privacy**（PrivacyConfig 的 ~28 测试靠 re-export 零改）。全绿（无环，golden 兜底）。
2. **相 2 — RestResponse → shared/rest.py**：迁移 + 重指 app(admin/snapshot)/infra(scheduler)/container；palworld_rest re-export 保旧路径测试零改。全绿。
3. **相 3 — _ADMIN_PATH → domain ADMIN_ACTIONS + normalize_players 注入**：admin_service 三处 adapters 依赖清零（palworld_rest 私有 + normalizer）；**6 处 AdminService 构造点追加 normalize_players= kwarg**（resolve_target 路径传真函数保等价）。全绿（admin_service_test resolve_target 三测兜注入等价）。
4. **相 4 — RepositoryPort 4 分离端口 + 重标注 5 service + name_resolver**：application/ports.py + 重标注 + 删 Repository import。全绿（mypy 结构化校验）。
5. **相 5 — application→adapters=0 静态守卫 + 终审**：新守卫 + 全绿 + golden 字节对比。

每相独立可跑独立绿（golden + 全量安全网贯穿）。相 1-3 迁移各自独立、相 4 端口独立、相 5 锁死。

## 10. 验收标准
- [ ] `application/*.py` 中 `from ..adapters` import 数 = **0**（相 5 静态守卫锚定）。
- [ ] 全部 golden `.txt` 字节不变；全量 1194 passed + `ruff check .`（全仓）+ mypy 全绿。
- [ ] 无导入环（PrivacyConfig 迁 domain 解 config 环；domain/shared 不反向依赖 application）。
- [ ] Repository 结构化满足 4 端口（mypy 在重标注处校验）；container 构造不变。
- [ ] RestResponse 在 shared（infra/app/adapters 三层共用无越界）；_ADMIN_PATH 私有 reach-in 已干掉（domain ADMIN_ACTIONS）；normalize_players 经注入（admin 不 import adapters.normalizer）。
- [ ] 三新文件被绝对自导入守卫覆盖；相对 import 无绝对自导入。
