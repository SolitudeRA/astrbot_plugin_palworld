from pathlib import Path

import yaml

from palworld_terminal.config import (
    AppConfig,  # noqa: F401  (ensure importable)
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _raw_config(tmp_path: Path) -> dict:
    return {
        "servers": [
            {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
             "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
             "timezone": ""},
        ],
        "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {"metrics_seconds": 30, "players_seconds": 30, "info_seconds": 600,
                    "settings_seconds": 1800, "game_data_seconds": 120, "jitter_ratio": 0.1,
                    "max_concurrency": 6},
        "world": {"timezone": "Asia/Tokyo", "locale": "zh-CN", "fps_smooth": 50,
                  "fps_moderate": 35, "fps_laggy": 20},
        "bases": {"enabled": True, "assignment_radius": 5000, "ambiguity_ratio": 0.2,
                  "confirmation_samples": 3, "position_grid_size": 2000, "z_weight": 0.5},
        "privacy": {"mode": "balanced", "public_exact_ping": False, "public_positions": False,
                    "ping_good_ms": 60, "ping_ok_ms": 120, "uncertain_timeout": 900},
        "history": {"raw_metrics_days": 7, "aggregate_days": 90, "session_days": 365,
                    "observation_days": 180},
    }


class _FakeContext:
    pass


async def test_initialize_and_terminate(tmp_path: Path, monkeypatch):
    import main as main_mod

    # avoid real network + real scheduler: monkeypatch Container factory used by main
    from palworld_terminal.container import Container

    class _FakeRest:
        async def close(self):
            pass

    class _FakeSched:
        async def start(self):
            pass

        async def stop(self):
            pass

    orig_init = Container.__init__

    def patched_init(self, config, data_dir, clock, **kw):
        kw.setdefault("rest_factory", lambda s, c: _FakeRest())
        kw.setdefault("scheduler_factory", lambda **k: _FakeSched())
        orig_init(self, config, data_dir, clock, **kw)

    monkeypatch.setattr(Container, "__init__", patched_init)
    # main.initialize must place data under tmp_path
    monkeypatch.setattr(main_mod, "_resolve_data_dir", lambda: tmp_path)

    plugin = main_mod.PalWorldTerminal(_FakeContext(), _raw_config(tmp_path))
    await plugin.initialize()
    assert plugin._container is not None
    assert plugin._container.commands is not None
    await plugin.terminate()
    assert (tmp_path / "palworld_terminal.sqlite3").exists()


def test_register_version_matches_metadata():
    # @register 的版本字符串须与 metadata.yaml 的 version 一致（动态对比,不锁具体值）
    meta = yaml.safe_load((REPO_ROOT / "metadata.yaml").read_text(encoding="utf-8"))
    source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert f'"{meta["version"]}"' in source, (
        f"main.py @register 版本应为 {meta['version']}"
    )


def test_pal_command_group_is_plain_def():
    import inspect

    import main as main_mod

    # command group handler is a plain (non-async) def per AstrBot convention
    assert not inspect.iscoroutinefunction(main_mod.PalWorldTerminal.pal)
