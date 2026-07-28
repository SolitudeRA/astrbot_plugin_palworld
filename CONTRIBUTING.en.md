<a id="contributing"></a>
# Contributing

[简体中文](CONTRIBUTING.md) | [日本語](CONTRIBUTING.ja.md) | **English**

<a id="development"></a>
## Development environment

- Python ≥ 3.11. Install dependencies with `pip install -r requirements-dev.txt` (includes the test toolchain).
- Frontend: Node ≥ 20, then run `cd frontend && npm ci`.

<a id="frontend-build"></a>
## Rebuild distributed assets after frontend changes

The settings-page output in `pages/settings/` is committed and distributed with the plugin. After changing
`frontend/src`, you must run:

```bash
cd frontend && npm run build
```

Commit the updated `pages/settings/` files together with the source change. `npm run build` already normalizes line
endings through `normalize-eol`, so Windows does not create phantom CRLF diffs. CI also runs `verify-bundle` to confirm
that the output remains a single-file bundle (1 JS, no more than 1 CSS, and no dynamic import). Backend-only changes do
not require this step.

<a id="checks"></a>
## Tests and checks

```bash
# Backend (use the virtual-environment Python on Windows)
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
./.venv/Scripts/lint-imports.exe

# Frontend
cd frontend && npm run test:run && npm run typecheck
```

CI runs the same checks on Linux and Windows. A change may be merged only when all checks pass.

<a id="commit-conventions"></a>
## Commit conventions

- Use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) with a Chinese description.
- Feature development follows the repository workflow: spec (`docs/superpowers/specs/`) → review → plan →
  implementation → whole-branch final review → PR.
