"""players 组 OFF 语义端到端：关组→四命令回 feature_disabled、help 不列（spec §5/§6）。"""
from types import SimpleNamespace

from palworld_terminal.config import FeaturesConfig
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.formatters import format_help


def _cmds(players_on):
    features = FeaturesConfig(report=True, events=True, guilds_bases=False, players=players_on)
    cfg = SimpleNamespace(features=features, privacy=SimpleNamespace(mode="balanced"))
    return Commands(routing=None, query=None, repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))


async def test_players_commands_gated_off():
    c = _cmds(players_on=False)
    for coro in (c.rank("u", "", True), c.player("u", "Alice", True),
                 c.me("u", "", True, "p:1"), c.bind("u", "Alice", True, "p:1")):
        assert await coro == "该功能未开放：当前配置或服务器不支持。"


def test_help_hides_players_when_off():
    off = format_help(None, False, FeaturesConfig(report=True, events=True, guilds_bases=False, players=False))
    on = format_help(None, False, FeaturesConfig(report=True, events=True, guilds_bases=False, players=True))
    assert "/pal rank" not in off and "/pal player" not in off
    assert "/pal rank" in on and "/pal bind" in on
