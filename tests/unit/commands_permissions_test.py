from types import SimpleNamespace

from palworld_terminal.config import AdminEntry, PermissionsConfig
from palworld_terminal.presentation.commands import Commands


def _cmds(admins=(), locked=()):
    perms = PermissionsConfig(
        admins=[AdminEntry(id=a, note="") for a in admins],
        command_overrides={},
        admin_only_commands=list(locked),
    )
    cfg = SimpleNamespace(permissions=perms)
    return Commands(routing=None, query=None, repo=None, cfg=cfg, clock=None, salt=b"")


async def test_whoami_returns_identity():
    out = await _cmds().whoami("aiocqhttp:12345")
    assert "aiocqhttp:12345" in out


async def test_whoami_empty_account():
    out = await _cmds().whoami("aiocqhttp:")
    assert "aiocqhttp:" not in out and "无法识别" in out


def test_is_plugin_admin():
    c = _cmds(admins=["aiocqhttp:1"])
    assert c.is_plugin_admin("aiocqhttp:1") is True
    assert c.is_plugin_admin("aiocqhttp:2") is False


def test_admin_denied_only_for_locked_non_admin():
    c = _cmds(admins=["aiocqhttp:1"], locked=["player"])
    assert c.admin_denied("player", "aiocqhttp:2") == "该命令需要管理员权限。"  # 锁定+非管理员
    assert c.admin_denied("player", "aiocqhttp:1") is None                    # 管理员放行
    assert c.admin_denied("rank", "aiocqhttp:2") is None                      # 未锁放行
