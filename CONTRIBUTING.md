<a id="contributing"></a>
# 贡献指南

**简体中文** | [日本語](CONTRIBUTING.ja.md) | [English](CONTRIBUTING.en.md)

<a id="development"></a>
## 开发环境

- Python ≥ 3.11,依赖:`pip install -r requirements-dev.txt`(叠加测试工具链)
- 前端:Node ≥ 20,`cd frontend && npm ci`

<a id="frontend-build"></a>
## 改动前端后必须重新构建产物

设置页产物(`pages/settings/`)**入库分发**。改动 `frontend/src` 后必须:

```bash
cd frontend && npm run build
```

然后把 `pages/settings/` 一并提交。`npm run build` 已内置行尾规范化(`normalize-eol`),
Windows 上也不会产生 CRLF 幻影脏;`verify-bundle` 会在 CI 校验产物为单文件(1 JS/≤1 CSS/无动态 import)。
只改后端不需要此步。

<a id="checks"></a>
## 测试与检查

```bash
# 后端(Windows 上用 venv 内的 python)
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
./.venv/Scripts/lint-imports.exe

# 前端
cd frontend && npm run test:run && npm run typecheck
```

CI 在 Linux 上运行静态检查、前端检查和后端测试，并在 Windows 上重复后端测试；所有检查通过后方可合并。

<a id="commit-conventions"></a>
## 提交约定

- Conventional Commits 风格(`feat:`/`fix:`/`docs:`/`chore:`),中文描述。
- 功能开发走仓库惯例流程:spec(`docs/superpowers/specs/`)→ 复核 → plan → 实现 → 整分支终审 → PR。
