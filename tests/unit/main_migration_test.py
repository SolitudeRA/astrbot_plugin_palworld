"""装载时 legacy 权限迁移落库 + 往返不丢锁（复核 F1/B2 关键回归）。

老用户升级后 storage 仍是旧 features/admin_only_commands，GET 下发的 raw 不含
command_permissions；若只在内存态迁移，前端树从空初始化、一保存就把不含旧锁的
配置落库 → 旧 admin 锁永久失效。根治 = 装载时把 legacy 迁移成 command_permissions
行写回存储并删旧键，使 存储/GET/运行时/保存 四者同源。
"""
import pytest

from main import PalWorldTerminal, _migrate_permissions_config
from tests.unit.main_test import _FakeContext, _raw_config


class _FakeAstrBotConfig(dict):
    """AstrBotConfig 最小替身：dict-like（真实 AstrBotConfig 亦是 dict 子类），
    暴露 .data 指向自身、save_config() 置 saved=True（对应真实 save_config 落盘）。"""

    def __init__(self, data):
        super().__init__(data)
        self.saved = False

    @property
    def data(self):
        return self

    def save_config(self):
        self.saved = True


@pytest.fixture
def fake_astrbot_config():
    def _make(data):
        return _FakeAstrBotConfig(data)
    return _make


def _run_plugin_load(cfg):
    # main.py 抽出的可单测装载迁移入口（initialize 在 parse_config/建容器前调用它）。
    _migrate_permissions_config(cfg)


def test_load_migration_persists_and_no_lock_loss(fake_astrbot_config):
    cfg = fake_astrbot_config({"admin_only_commands": ["guild list"], "features": {"guilds_bases": True}})
    _run_plugin_load(cfg)                    # 触发装载迁移
    assert "command_permissions" in cfg.data
    assert "admin_only_commands" not in cfg.data and "features" not in cfg.data
    assert cfg.saved is True
    # GET 读路径（redact_config(cfg.data)）现含 command_permissions → 保存不丢锁
    from palworld_terminal.config import parse_config
    from palworld_terminal.shared.command_permissions import effective_admin_only
    ov = parse_config(cfg.data, {}).permissions.command_overrides
    assert effective_admin_only(ov, "guild list") is True


def test_load_migration_idempotent(fake_astrbot_config):
    cfg = fake_astrbot_config({"command_permissions": []})   # 新键在场 → 跳过
    _run_plugin_load(cfg)
    assert cfg.saved is False


def test_load_migration_absent_absent_noop(fake_astrbot_config):
    # 全新装（legacy 与新键都缺席）：不动、不 save。
    cfg = fake_astrbot_config({"servers": []})
    _run_plugin_load(cfg)
    assert cfg.saved is False
    assert "command_permissions" not in cfg.data


async def test_initialize_wires_migration(tmp_path, monkeypatch, fake_astrbot_config):
    """端到端锚定装载钩子确实接入 initialize()（在建容器前）：legacy 配置经
    initialize() 后落库、旧键清除，且新建容器的解析配置仍保留旧锁（F1/B2 不丢锁）。"""
    import main as main_mod
    from palworld_terminal.container import Container
    from palworld_terminal.shared.command_permissions import effective_admin_only

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
    monkeypatch.setattr(main_mod, "_resolve_data_dir", lambda: tmp_path)

    raw = {**_raw_config(tmp_path), "features": {"guilds_bases": True},
           "admin_only_commands": ["guild list"]}
    cfg = fake_astrbot_config(raw)
    plugin = main_mod.PalWorldTerminal(_FakeContext(), cfg)
    await plugin.initialize()
    try:
        assert "command_permissions" in cfg.data
        assert "features" not in cfg.data and "admin_only_commands" not in cfg.data
        assert cfg.saved is True
        ov = plugin._container.config.permissions.command_overrides
        assert effective_admin_only(ov, "guild list") is True
    finally:
        await plugin.terminate()


def test_migration_entry_is_module_level():
    # 迁移入口须是可单测的独立函数（不强制实例化 Star / 运行时依赖）。
    assert callable(_migrate_permissions_config)
    assert PalWorldTerminal is not None
