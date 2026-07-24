# import-linter 声明式分层契约（架构解耦 Spec ③）

**日期**：2026-07-24
**分支**：`feat/import-linter-layering`（叠于 main @ `80451e2` v1.1.0）
**类型**：纯重构 + 工具化，零行为变化，**不 bump 版本**
**前序**：架构解耦三部曲 A/B/C（PR #29/#32/#31）+ god 类拆分 D（#33 Repository）/②（#34 QueryService）已合并 main v1.1.0。本 Spec 是系列收官——用声明式契约取代两道手写 grep 分层守卫，并修掉全契约揭出的一处真耦合。

---

## 1. 背景与目标

系列前作把跨层反向依赖清零、god 类拆成 mixin。分层不变式目前由**两道手写 grep 守卫**锚定：
- `tests/unit/layering_guard_test.py`：扫 `application/*.py` 子串 `from ..presentation` / `import palworld_terminal.presentation` → application ↛ presentation。
- `tests/unit/adapter_layering_guard_test.py`：扫 `application/*.py` 子串 `from ..adapters` / `import palworld_terminal.adapters` → application ↛ adapters。

这两道守卫的局限（已知）：①只查 **2 条直接边**（application 出发的两条），不表达完整六边形契约；②子串匹配脆（漏绝对形 `from palworld_terminal.presentation`，靠 `no_absolute_self_import_test` 兜）；③**不查传递依赖**（下文揭出的 config 耦合正因此从未被发现）；④每加一条分层规则=新写一个测试文件。

**目标**：用 [import-linter](https://import-linter.readthedocs.io) 声明式契约替换这两道守卫，一次锚定**完整六边形分层**（catches 全部 7+ 条边含传递链），并顺手修掉全契约揭出的 `config → application.command_permissions` 真耦合。

**为何 import-linter 合适（用户已拍板全契约）**：dev/CI-only 依赖（`requirements-dev.txt`，**不进用户运行时**，插件运行零影响）；**静态分析**（grimp 3.15 AST 解析，**无需装 astrbot 即可分析**——已实测 `Analyzed 64 files, 202 dependencies`）；声明式、自文档化、覆盖全边。

**非目标（YAGNI）**：
- 不改任何运行时逻辑/行为（command_permissions 是**纯移动**）。
- 不把契约做成 pytest 测试（与 ruff/mypy 一致，走 CI lint 步；见 §5 权衡）。
- 不守 layer→config/container/main 方向（config/container/main 是配置/组装根，天然在 layer 之外，不约束；与现 grep 守卫同范围）。
- 不改 `no_absolute_self_import_test`（正交：管相对导入风格，非分层）。
- 不重命名/不改 command_permissions 的任何符号或逻辑。

---

## 2. 现状锚点（已逐条经 import-linter 实测/grep 核实）

**跨层 import 图（who imports whom，grep 核实）**：
| 层 | 导入（允许依赖） |
|---|---|
| `domain` | 无（最内） |
| `shared` | **无**（当前 command_registry + rest 均不碰 domain） |
| `infrastructure` | domain, shared |
| `application` | domain, infrastructure, shared（不含 adapters/presentation） |
| `adapters` | domain, infrastructure, shared（不含 application/presentation） |
| `presentation` | application, domain, infrastructure, shared（不含 adapters） |
| `config` / `container` / `main`（顶层非 layer） | config→application.command_permissions + domain + shared；container/main→全部 |

**揭出的真耦合（全契约实测·grep 守卫从未查）**：`palworld_terminal.config` → `palworld_terminal.application.command_permissions`（config.py:8 多符号 import）。因 adapters（sqlite_repository→config）、infrastructure（scheduler→config）都 import config，**传递出 adapters→application、infrastructure→application** 两条违规。实测：全 layers 契约在此**唯一** BROKEN（`ignore` 该边或移走 command_permissions 后即 `2 kept, 0 broken`）。

**command_permissions 本质（已核）**：`application/command_permissions.py` = 214 行，**纯函数、无 IO**，import 仅 `..domain.enums.EndpointName` + `..shared.command_registry`（DISPATCH/FLAT_ACTIONS/LOCKABLE_COMMANDS）。**零 application 层内部依赖**——与 `command_registry`（Spec A 已因 config 依赖而迁 shared）同类，架构上属 shared。config.py 从它 import 8 符号（COMMAND_META/CommandOverride/admin_configurable/admin_forced_true/enable_configurable/upstream_unavailable/upstream_unavailable_group）。

**command_permissions 导入方（re-point 面，全仓 grep 核实·全 import 形）**：**9 源文件**（`config.py`·`container.py`·**`main.py`**·presentation 的 `admin_write_flow`/`commands`/`command_support`/`config_view`/`formatters`/`read_commands`）+ **18 测试文件**。共 **27 导入方**。
> **⚠️ main.py 是仓库根的 AstrBot 插件入口（在 palworld_terminal 包外）**，有**两条 import 行**：`:59 from .palworld_terminal.application.command_permissions import migrate_legacy_to_rows`（相对命名空间形，AstrBot 加载 try 分支）+ `:67 from palworld_terminal.application.command_permissions import ...`（绝对形，except 分支）——**均须重指**（`migrate_legacy_to_rows` 定义在 command_permissions:177，随文件迁 shared）。**main.py 被 import-linter 契约豁免（顶层非 layer，§4）——契约不会捕获它的悬空 import，pytest（+8 个 import main 的测试）是唯一安全网。** 测试导入方含 `command_permissions_meta_test.py`（用 `from palworld_terminal.application import command_permissions as cp` 形，非 `.command_permissions import` 形）。

**import-linter 可行性（已实测）**：import-linter 2.13 / grimp 3.15；`lint-imports --config <toml>` 读 `[tool.importlinter]`；layers 契约 `|` 独立同级语法可用；forbidden 契约可用；静态分析无需 astrbot。

**CI 现状**（`.github/workflows/ci.yml`）：`lint` job（ubuntu，checkout@v7/setup-python@v6 3.12，`pip install -r requirements-dev.txt`，`ruff check .`，`python -m mypy palworld_terminal/`）+ `test` 矩阵（ubuntu 3.11/3.12/3.13 + windows 3.12，pytest）。

**当前基线**：main @ 80451e2、v1.1.0、**1201 passed / 1 skipped**、ruff/mypy(64) 全绿。

---

## 3. Part 1：`command_permissions` → `shared`（架构修复）

### 3.1 移动模块
`application/command_permissions.py` → `shared/command_permissions.py`（与 `command_registry.py`/`rest.py` 共位）。文件内容**逐字保留，唯一改动 = 内部相对 import 深度**：
- `from ..shared.command_registry import (DISPATCH, FLAT_ACTIONS, LOCKABLE_COMMANDS)` → `from .command_registry import (DISPATCH, FLAT_ACTIONS, LOCKABLE_COMMANDS)`（迁后 command_registry 是同包 sibling）。
- `from ..domain.enums import EndpointName` **不变**（shared/ 的 `..domain` = palworld_terminal.domain，正确）。
- 其余全部方法/常量/docstring 字节不变。LF 保持。

### 3.2 重指 27 导入方
`application.command_permissions` → `shared.command_permissions`。**须全仓 grep 全 import 形（`application.command_permissions` + `application import command_permissions` + `.palworld_terminal.application.command_permissions`），不信硬编码清单**：
- **9 源文件**：`config.py`（`from .application.command_permissions` → `from .shared.command_permissions`）、`container.py`（同）、6 presentation（`from ..application.command_permissions` → `from ..shared.command_permissions`）、**`main.py`（仓库根，2 行）**：`:59 from .palworld_terminal.application.command_permissions import migrate_legacy_to_rows` → `from .palworld_terminal.shared.command_permissions import migrate_legacy_to_rows`；`:67 from palworld_terminal.application.command_permissions import ...` → `from palworld_terminal.shared.command_permissions import ...`。
- **18 测试文件**：`from palworld_terminal.application.command_permissions import ...` → `from palworld_terminal.shared.command_permissions import ...`；**`command_permissions_meta_test.py` 特殊形** `from palworld_terminal.application import command_permissions as cp` → `from palworld_terminal.shared import command_permissions as cp`（清单见 §8）。

### 3.3 删原文件
删 `application/command_permissions.py`。**删除式迁移无自然 re-export**（定义随文件迁走，application 不再持有）→ 不留 shim（承 Spec C 教训：只有构造点仍在原模块才用自然 re-export；此处是整模块迁出，须逐一重指）。

### 3.4 零行为变化
纯移动 + 重指路径，无逻辑改动。双验证：全库 pytest 回归 + import-linter 契约（Part 2）。

---

## 4. Part 2：import-linter 契约

`pyproject.toml` 追加 `[tool.importlinter]`（实测移走 command_permissions 后 `2 kept, 0 broken`）：

```toml
[tool.importlinter]
root_package = "palworld_terminal"

[[tool.importlinter.contracts]]
name = "Hexagonal layered architecture"
type = "layers"
containers = ["palworld_terminal"]
layers = [
    "presentation",
    "application | adapters",
    "infrastructure",
    "shared",
    "domain",
]

[[tool.importlinter.contracts]]
name = "presentation must not import adapters directly"
type = "forbidden"
source_modules = ["palworld_terminal.presentation"]
forbidden_modules = ["palworld_terminal.adapters"]
```

**layers 契约语义**（高→低，高可 import 低、低不可 import 高，同级 `|` 独立不可互 import）：
- `presentation`（顶）→ 可 import application/infrastructure/shared/domain。
- `application | adapters`（同级独立）→ 各可 import infrastructure/shared/domain；**application ⊥ adapters**（互不 import，取代旧 adapter_layering_guard 且对称加 adapters↛application）；二者 ↛ presentation（上行禁，取代旧 layering_guard）。
- `infrastructure` → 可 import shared/domain；↛ application/adapters/presentation（上行禁）。
- `shared` → 可 import domain（**新边，仅 command_permissions 引入**；shared 在 domain 之上）；↛ 上层。
- `domain`（底）→ import 无；↛ 上层。

**forbidden 契约**：layers 中 presentation 在 adapters 之上，下探本被允许——单列一条 forbidden 禁 `presentation → adapters`（presentation 只经 application 间接触达数据，不直连 adapters）。

**config/container/main 天然豁免**：`containers=["palworld_terminal"]` 令 layer = `palworld_terminal.<layer>` 子包；`config.py`/`container.py`/`main.py` 是顶层模块、不在任何 layer → 非 layers 契约的 source，不被约束（正确：config=配置基座、container/main=组装根）。移走 command_permissions 后 config 的 import 全落 shared/domain，adapters/infra 经 config 的传递链只达 shared/domain（允许）→ 契约通过。

**覆盖对比**：旧 grep = 2 条直接边。新契约 = application↛presentation + application↛adapters + adapters↛presentation + adapters↛application + infrastructure↛{application,adapters,presentation} + shared↛上层 + domain↛上层 + presentation↛adapters + **传递链**（正是揭出 config 耦合的能力）。严格超集且更强。

---

## 5. CI 集成

`requirements-dev.txt` 追加：
```
import-linter>=2.13   # 声明式分层契约（配置见 pyproject.toml [tool.importlinter]）
```

`.github/workflows/ci.yml` 的 `lint` job 在 `Mypy` 步后追加：
```yaml
      - name: Import contracts
        run: lint-imports
```
（`lint-imports` 默认读 `pyproject.toml` 的 `[tool.importlinter]`，工作目录=仓库根，无需 `--config`。）

**权衡（CI-only，非 pytest）**：契约走 CI lint 步而非 pytest 测试——与 `ruff`/`mypy` 一致（本仓既有惯例：静态分析工具=lint job，非 pytest）。代价：本地只跑 `pytest` 不再捕分层违规（须像 ruff/mypy 一样跑 `lint-imports`）。此权衡为一致性有意接受；开发者 `pip install -r requirements-dev.txt` 后 `lint-imports` 即可本地跑。

---

## 6. 守卫删除/保留

- **删** `tests/unit/layering_guard_test.py` + `tests/unit/adapter_layering_guard_test.py`（契约完全覆盖且更强）。
- **保留** `tests/unit/no_absolute_self_import_test.py`（正交：禁绝对自导入=相对导入风格，非分层；import-linter 不管导入风格）。

---

## 7. 硬约束

1. **command_permissions 逐字保留**（除 §3.1 唯一 import-depth 行）：方法体/常量/docstring 字节不变、LF。
2. **零行为变化**：现有全库测试（除删的 2 守卫）保持全绿。基线 1201 passed → **1199 passed / 1 skipped**（−2 删守卫；契约非 pytest 不加计）。
3. **契约 0 broken**：`lint-imports` 报 `2 kept, 0 broken`（移走 command_permissions 后实测）。
4. **ruff/mypy 全绿**：`ruff check .`（全仓）+ `mypy palworld_terminal/`（Success，文件数 64 不变——move 非新增文件）。
5. **相对导入**（`shared/__init__` 空，导入风格不变）。
6. **不 bump 版本**：v1.1.0 不动。
7. **commit 无 Claude / Co-Authored-By / AI 署名。**
8. 本机 python 不在 Bash PATH：用 `.venv/Scripts/python.exe` / `.venv/Scripts/ruff.exe` / `.venv/Scripts/lint-imports.exe`。

---

## 8. 测试策略与验收

- **等价性（Part 1 move）**：靠全库 pytest 回归（command_permissions 的现有测试 `command_permissions_effective/endpoints/migrate_test` + config/container/gating/permissions 等 18 测试导入方，全走真实例，任何路径/行为漂移转红）+ import-linter 契约（结构等价的传递证据）。
- **契约正确性**：`lint-imports` 0 broken（Part 2 加契约后）；**对抗验证：临时植入一条越界 import（如 application 加 `from ..adapters import X`）→ `lint-imports` 须 BROKEN → 还原**（证契约真咬合，非假绿）。
- **删守卫无损**：删的 2 grep 守卫的语义被 layers 契约的 application↛presentation/adapters 完全覆盖且更强（含 adapters↛application 对称边、传递链）。
- **18 测试导入方清单**（re-point，须逐一改 import 路径）：`commands_admin_write` · `commands_dispatch` · `commands_gating` · `commands_guild` · `commands_permissions` · `commands_player` · `commands_rank` · `command_permissions_effective` · `command_permissions_endpoints` · `command_permissions_migrate` · **`command_permissions_meta`（特殊形 `from ...application import command_permissions as cp`）** · `config_command_permissions` · `container_features` · `frontend_pal_commands` · `gamedata_output_suppression` · `main_migration` · `rank_total` · `_perm`（+ 复核 grep 全仓**全 import 形** `application.command_permissions` **与** `application import command_permissions` 零残留）。
- **验收命令**：`.venv/Scripts/lint-imports.exe`（2 kept/0 broken）+ `ruff check .` + `.venv/Scripts/python.exe -m mypy palworld_terminal/`（Success 64）+ 全库 `pytest -q`（1199 passed / 1 skipped）+ CI 全绿（lint job 新增 Import contracts 步 pass）。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| move 后漏改某导入方 → `ImportError`/`ModuleNotFoundError` | 全仓 grep **全 import 形**（`application.command_permissions` + `application import command_permissions` + `.palworld_terminal.` 相对形）零残留复核 + 全库 pytest（导入方炸）。**⚠️ main.py（仓库根）被 import-linter 契约豁免——契约不查它、非-repo-root grep 也漏它；必须 repo-wide grep + 靠 8 个 import main 的测试兜（漏则插件加载炸+这 8 测试 collection 失败，1201 不成立）** |
| command_permissions 内部 `.command_registry` import 深度改错 | mypy + import 该模块的测试立即炸 |
| shared→domain 新边未被 layers 允许 → 契约反而 broken | layers 序 `shared` 在 `domain` 之上（shared 可下探 domain）；已实测新序 0 broken |
| 契约 `|` 语法/格式错 → lint-imports 读不到或报错 | §4 TOML 已实测可解析运行（2 kept/0 broken）；SDD 加契约后即跑 lint-imports 验证 |
| CI 缺 import-linter → lint 步炸 | requirements-dev.txt 已加 import-linter>=2.13（CI `pip install -r requirements-dev.txt` 覆盖） |
| 契约漏掉某边（假绿） | §8 对抗验证：植入越界 import 须 BROKEN 才算守卫真咬合 |
| grimp 静态分析需装 astrbot？ | 已实测**无需**（静态 AST，Analyzed 64 files 无 astrbot） |
| 本地 pytest 不再捕分层违规 | §5 有意权衡（同 ruff/mypy）；CI lint 步 + 本地 lint-imports 兜 |
| lint-imports 读错配置（找不到 pyproject 的 [tool.importlinter]） | CI 工作目录=仓库根，默认读 pyproject.toml；SDD 验证 |

---

## 10. 交付形态

- **移动 1 文件**：`application/command_permissions.py` → `shared/command_permissions.py`（唯一改 1 import-depth 行）。
- **改 27 导入方**：9 源（config/container/**main** + 6 presentation）+ 18 测试，`application.command_permissions` → `shared.command_permissions`（main.py 2 行、command_permissions_meta_test 特殊形）。
- **改 `pyproject.toml`**：追加 `[tool.importlinter]`（2 契约）。
- **改 `requirements-dev.txt`**：追加 `import-linter>=2.13`。
- **改 `.github/workflows/ci.yml`**：lint job 加 `Import contracts` 步。
- **删 2 测试**：`layering_guard_test.py` + `adapter_layering_guard_test.py`。
- **零改动**：`no_absolute_self_import_test.py`、所有 service/adapter/domain/infra 逻辑、command_permissions 的符号与行为。
- **验收**：`lint-imports`（2 kept/0 broken）+ `ruff check .` + `mypy(64)` + `pytest`（1199 passed/1 skipped）+ CI 全绿。**不 bump**（v1.1.0）。

---

## 11. 执行结构（供 plan/SDD 参考）

**Part 1 先于 Part 2**（加契约前先修掉 config 耦合，否则契约首跑 broken）：
1. **T1**：move `command_permissions` → shared（§3.1 改 import-depth）+ 重指 27 导入方（§3.2，**含 main.py 2 行 + command_permissions_meta_test 特殊形**）+ 删原文件（§3.3）。验收：全库 pytest 1201（此刻 grep 守卫仍在、仍绿，move 不碰 application↛presentation/adapters）+ ruff + mypy + **全仓全 import 形 grep `application.command_permissions`/`application import command_permissions` 零残留**（含 main.py：import-linter 豁免顶层不查，pytest[8 个 import main 的测试]是唯一网）。**原子提交**（导入方须同提交切换否则中途 ImportError）。
2. **T2**：加 `requirements-dev.txt` 的 import-linter + `pyproject.toml` 的 `[tool.importlinter]` 契约。验收：`lint-imports` **2 kept/0 broken**（config 耦合已 T1 修掉）+ 对抗验证（植入越界 import→BROKEN→还原）。
3. **T3**：CI lint job 加 `Import contracts` 步 + 删 2 grep 守卫。验收：全库 pytest **1199 passed**（−2 守卫）+ ruff + mypy + lint-imports 0 broken + 全仓 grep `layering_guard`/`adapter_layering_guard` 引用零残留。

> T1（move）先立地基修掉耦合；T2 加契约此刻即 0 broken；T3 接管 CI + 退役旧守卫。每步独立绿。
