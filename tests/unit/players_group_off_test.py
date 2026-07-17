"""players 组 OFF 语义端到端：关组→四命令回 feature_disabled、help 不列（spec §5/§6）。"""
from types import SimpleNamespace

from palworld_terminal.presentation.commands import Commands, feature_disabled_text
from palworld_terminal.presentation.formatters import format_help
from tests.unit._perm import overrides


def _cmds(players_on):
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=overrides(players=players_on)),
        privacy=SimpleNamespace(mode="balanced"),
    )
    return Commands(routing=None, query=None, repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))


async def test_players_commands_gated_off():
    c = _cmds(players_on=False)
    # players 组各命令非上游不可用 → 主句 ⚠️ + 「设置页开启」引导脚注（spec §3）。
    expected = feature_disabled_text("player info")
    for coro in (c.rank("u", "", True), c.player("u", "Alice", True),
                 c.me("u", "", True, "p:1"), c.bind("u", "Alice", True, "p:1"),
                 c.unbind_self("u", "", True, "p:1")):
        assert await coro == expected


def test_help_hides_players_when_off():
    off = format_help(None, False, overrides(players=False))
    on = format_help(None, False, overrides(players=True))
    assert "/pal rank" not in off and "/pal player info" not in off and "/pal player unbind" not in off
    assert "/pal rank" in on and "/pal player bind" in on and "/pal player unbind" in on
