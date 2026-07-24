# import-linter 声明式分层契约（架构解耦 Spec ③）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 import-linter 声明式契约取代两道手写 grep 分层守卫，并顺手修掉全契约揭出的 `config → application.command_permissions` 真耦合（把纯函数模块 command_permissions 从 application 迁到 shared）。

**Architecture:** Part 1 先修耦合——`application/command_permissions.py`（纯函数，只依赖 shared.command_registry + domain.enums）迁 `shared/command_permissions.py`，全仓重指 27 导入方，删原文件（零行为变化）。Part 2 再加契约——`pyproject.toml` 的 `[tool.importlinter]` 全 hexagonal layers + forbidden 契约（移走 command_permissions 后 2 kept/0 broken）、`requirements-dev.txt` 加 import-linter、CI lint job 加 `lint-imports` 步、删两道 grep 守卫。

**Tech Stack:** import-linter 2.13 / grimp 3.15（静态分析·dev-CI-only 依赖）/ pytest / ruff / mypy / GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-07-24-import-linter-layering-design.md`（导入方清单见 §2/§3.2/§8、契约 TOML 见 §4、CI 见 §5）。

## Global Constraints

- **command_permissions 逐字保留**：方法体/常量/docstring 字节不变、LF；**唯一改动 = 内部相对 import 深度**（`from ..shared.command_registry import (...)` → `from .command_registry import (...)`；`from ..domain.enums import EndpointName` 不变）。
- **零行为变化**：现有全库测试保持全绿。基线 **1198 passed / 1 skipped**（main @ 80451e2）→ T3 删 2 grep 守卫后 **1196 passed / 1 skipped**。契约走 CI lint 步、非 pytest，不加计。
- **导入方普查 repo-wide + 全 import 形**：重指须覆盖 `application.command_permissions`（config/container/main/6 presentation/17 test）**与** `application import command_permissions`（command_permissions_meta_test 的 `import command_permissions as cp` 形）。**⚠️ main.py 在仓库根（palworld_terminal 包外）且被 import-linter 契约豁免（顶层非 layer）——契约不查它，普查须 repo-wide（非只扫 palworld_terminal/）；漏改则插件加载炸 + 8 个 import main 的测试 collection 失败。**
- **不 bump 版本**：v1.1.0 不动。
- **相对导入**（shared/__init__ 空，导入风格不变）；保留 `no_absolute_self_import_test`（正交）。
- **验收命令**（python 不在 Bash PATH）：`.venv/Scripts/lint-imports.exe`（读 pyproject 默认配置）/ `.venv/Scripts/ruff.exe check .`（全仓）/ `.venv/Scripts/python.exe -m mypy palworld_terminal/`（Success 64）/ `.venv/Scripts/python.exe -m pytest -q`。
- **commit 不含 Claude / Co-Authored-By / 任何 AI 署名。**
- **零改动**：`no_absolute_self_import_test.py`、所有 service/adapter/domain/infra 逻辑、command_permissions 的符号与行为。

## File Structure

- Move（LF）：`application/command_permissions.py` → `shared/command_permissions.py`（唯一改 1 import-depth 行）。
- Modify：27 导入方（9 源：config/container/main + 6 presentation；18 测试）。
- Modify：`pyproject.toml`（加 `[tool.importlinter]`）、`requirements-dev.txt`（加 import-linter）、`.github/workflows/ci.yml`（lint job 加步）。
- Delete：`tests/unit/layering_guard_test.py`、`tests/unit/adapter_layering_guard_test.py`。

---

## Task 1: 迁 `command_permissions` → shared + 重指 27 导入方 + 删原文件

**Files:**
- Create: `palworld_terminal/shared/command_permissions.py`（LF）
- Modify: `palworld_terminal/config.py` · `container.py` · `main.py`（2 行）· `presentation/{admin_write_flow,commands,command_support,config_view,formatters,read_commands}.py` · 18 测试文件（§8 清单）
- Delete: `palworld_terminal/application/command_permissions.py`

**Interfaces:**
- Produces: `palworld_terminal.shared.command_permissions`（全部符号不变：COMMAND_META/CommandMeta/CommandOverride/effective_enabled/active_endpoints/migrate_legacy_to_rows/upstream_unavailable/... 供全部导入方消费）。

- [ ] **Step 1: 建 shared/command_permissions.py（逐字复制 + 唯一 import-depth 改动）**

用 git 移动保真：从 `palworld_terminal/application/command_permissions.py` 复制内容到 `palworld_terminal/shared/command_permissions.py`，只改内部相对 import 深度一行：
```python
# 原（application/ 视角）：
from ..shared.command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    LOCKABLE_COMMANDS,
)
# 改为（shared/ 视角，command_registry 是同包 sibling）：
from .command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    LOCKABLE_COMMANDS,
)
```
`from ..domain.enums import EndpointName` **不变**（shared/ 的 `..` = palworld_terminal）。其余全部字节不变、LF。

- [ ] **Step 2: 重指全部 27 导入方（两种 import 形，repo-wide）**

对全仓（含仓库根 main.py）除 `application/command_permissions.py`（待删）外的所有 .py，做两处路径替换：
- `application.command_permissions` → `shared.command_permissions`（覆盖 config/container/main[2 行]/6 presentation/17 test，含 main.py:59 `.palworld_terminal.application.command_permissions` 相对形与 :67 绝对形）。
- `application import command_permissions` → `shared import command_permissions`（覆盖 `command_permissions_meta_test.py:1` 的 `from palworld_terminal.application import command_permissions as cp`）。

**注意**：配置键字符串 `"command_permissions"`（如 `raw.get("command_permissions")`、`config["command_permissions"]`）**不含 `application.` 前缀，不受替换影响**——正确保留。

- [ ] **Step 3: 删原文件**

删 `palworld_terminal/application/command_permissions.py`（删除式迁移无 shim；定义已随文件迁 shared）。

- [ ] **Step 4: repo-wide 零残留复核（含 main.py）**

Run:
```bash
grep -rnE "application\.command_permissions|application import command_permissions" --include="*.py" . | grep -v "__pycache__"
```
Expected: **无输出**（零残留，含仓库根 main.py 已重指）。若有输出=漏改，逐一补。

- [ ] **Step 5: 全库回归 + ruff + mypy（等价性总验证）**

Run: `.venv/Scripts/ruff.exe check . && .venv/Scripts/python.exe -m mypy palworld_terminal/ && .venv/Scripts/python.exe -m pytest -q`
Expected: ruff `All checks passed!`；mypy `Success: no issues found in 64 source files`（move 非新增文件，净 0）；pytest `1198 passed, 1 skipped`（含 8 个 import main 的测试 + 18 个 import command_permissions 的测试全绿=重指完整的证据）。若某 test collection 失败=漏改某导入方，回 Step 2/4。

- [ ] **Step 6: 确认模块已迁 + 符号可达**

Run: `.venv/Scripts/python.exe -c "from palworld_terminal.shared.command_permissions import COMMAND_META, effective_enabled, active_endpoints, migrate_legacy_to_rows; import importlib,sys; assert 'palworld_terminal.application.command_permissions' not in sys.modules or __import__('importlib').util.find_spec('palworld_terminal.application.command_permissions') is None; print('shared.command_permissions OK, application 版已删')"`
Expected: `shared.command_permissions OK, application 版已删`。

- [ ] **Step 7: Commit（原子）**

```bash
git add -A
git commit -m "refactor: command_permissions 迁 application→shared + 重指 27 导入方（解 config 向上耦合）"
```

---

## Task 2: import-linter 契约（pyproject + requirements-dev）

**Files:**
- Modify: `pyproject.toml`（加 `[tool.importlinter]`）
- Modify: `requirements-dev.txt`（加 import-linter）

**Interfaces:**
- Consumes: Task 1 已迁 command_permissions（否则契约 broken）。
- Produces: `lint-imports` 可跑、2 kept/0 broken。

- [ ] **Step 1: requirements-dev.txt 加 import-linter**

在 `requirements-dev.txt` 追加（与 ruff/mypy 同段）：
```
import-linter>=2.13   # 声明式分层契约（配置见 pyproject.toml [tool.importlinter]）
```
并本地装：`.venv/Scripts/python.exe -m pip install "import-linter>=2.13"`（若未装）。

- [ ] **Step 2: pyproject.toml 加 [tool.importlinter] 契约**

在 `pyproject.toml` 末尾追加（spec §4 逐字）：
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

- [ ] **Step 3: 跑 lint-imports——应 2 kept / 0 broken**

Run: `.venv/Scripts/lint-imports.exe`
Expected:
```
Hexagonal layered architecture KEPT
presentation must not import adapters directly KEPT
Contracts: 2 kept, 0 broken.
```
（`lint-imports` 无 `--config` 时默认读仓库根 `pyproject.toml` 的 `[tool.importlinter]`。）若 BROKEN=Task 1 的耦合未修净或契约格式错，查违规链。

- [ ] **Step 4: 对抗验证——契约真咬合（植入越界 import → BROKEN → 还原）**

临时在 `palworld_terminal/application/routing_service.py` 顶部加一行 `from ..adapters.sqlite_repository import Repository`（application↛adapters 越界），跑 `.venv/Scripts/lint-imports.exe` → **应 BROKEN**（`application is not allowed to import ...adapters`）。然后 `git checkout -- palworld_terminal/application/routing_service.py` **还原**。确认契约非假绿。

- [ ] **Step 5: 全套验收（契约不动现有测试）**

Run: `.venv/Scripts/ruff.exe check . && .venv/Scripts/python.exe -m mypy palworld_terminal/ && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/lint-imports.exe`
Expected: ruff clean；mypy Success 64；pytest `1198 passed, 1 skipped`（契约非 pytest，count 不变）；lint-imports `2 kept, 0 broken`。

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements-dev.txt
git commit -m "build: import-linter 全 hexagonal 分层契约（layers + presentation↛adapters forbidden）"
```

---

## Task 3: CI lint-imports 步 + 删两道 grep 守卫

**Files:**
- Modify: `.github/workflows/ci.yml`（lint job 加步）
- Delete: `tests/unit/layering_guard_test.py` · `tests/unit/adapter_layering_guard_test.py`

**Interfaces:**
- Consumes: Task 2 的契约（0 broken）+ requirements-dev 的 import-linter。

- [ ] **Step 1: ci.yml lint job 加 Import contracts 步**

在 `.github/workflows/ci.yml` 的 `lint` job、`Mypy` 步之后追加：
```yaml
      - name: Import contracts
        run: lint-imports
```
（CI 已 `pip install -r requirements-dev.txt`，import-linter 就位；工作目录=仓库根，默认读 pyproject。）

- [ ] **Step 2: 删两道 grep 守卫**

Run: `git rm tests/unit/layering_guard_test.py tests/unit/adapter_layering_guard_test.py`
（契约的 application↛presentation + application↛adapters（+对称 adapters↛application + 传递链）完全覆盖且更强；`no_absolute_self_import_test.py` **保留**。）

- [ ] **Step 3: 复核无残留引用**

Run: `grep -rn "layering_guard\|adapter_layering_guard\|test_application_has_no_presentation\|test_application_has_no_adapters" --include="*.py" --include="*.md" . | grep -v "docs/superpowers"`
Expected: **无输出**（除 docs/spec/plan 记述外，代码/CI 零引用）。

- [ ] **Step 4: 全套验收（−2 守卫 → 1196）**

Run: `.venv/Scripts/ruff.exe check . && .venv/Scripts/python.exe -m mypy palworld_terminal/ && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/lint-imports.exe`
Expected: ruff clean；mypy Success 64；pytest **`1196 passed, 1 skipped`**（1198 − 2 删守卫）；lint-imports `2 kept, 0 broken`。

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git rm tests/unit/layering_guard_test.py tests/unit/adapter_layering_guard_test.py
git commit -m "ci: 加 import-linter 契约步 + 退役两道 grep 分层守卫（契约完全覆盖且更强）"
```

---

## 完成标准

- `command_permissions` 从 application 迁 shared（config 不再向上依赖 application）、27 导入方全重指、原文件删、零行为变化。
- `pyproject.toml` 全 hexagonal import-linter 契约（layers + forbidden）2 kept/0 broken；对抗验证证真咬合。
- CI lint job 新增 `Import contracts` 步；两道 grep 守卫退役（`no_absolute_self_import_test` 保留）。
- `lint-imports`（0 broken）+ `ruff check .` + `mypy(64)` + `pytest`（1196 passed/1 skipped）+ CI 全绿。
- 全程零行为变化、不 bump（v1.1.0）。

## Self-Review 检查点（写完自查）

- Spec 覆盖：§3 move→T1、§4 契约→T2、§5 CI→T3、§6 删守卫→T3——全覆盖。
- Placeholder：无 TBD/TODO；命令与期望输出具体。
- 计数一致：27 导入方（9 源 + 18 测试）、1198→1196、mypy 64——与 spec 一致。
- 类型/签名：command_permissions 符号名跨 task 一致；契约 TOML 与 spec §4 逐字。
