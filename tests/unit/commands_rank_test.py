from types import SimpleNamespace

from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.application.query_service import RankBoardsDTO
from palworld_terminal.presentation.commands import Commands


class _Query:
    async def rank(self, world, mode="both"):
        return RankBoardsDTO(time_rows=[("A", 60)], level_rows=[("A", 9)],
                             total_rows=[("A", 120)])


def _cmds(mode="balanced", players_on=True):
    ov = {"rank": CommandOverride(enabled=players_on)}
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=ov),
        privacy=SimpleNamespace(mode=mode),
    )
    c = Commands(routing=None, query=_Query(), repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))
    async def _rw(umo, msg, sub, is_group):
        return SimpleNamespace(world_id="w1", server_id="w"), SimpleNamespace(name=msg, server_override=None), None, "srv"
    c._resolve_world = _rw
    return c


async def test_rank_gated_off_returns_feature_disabled():
    out = await _cmds(players_on=False).rank("u", "", True)
    assert out == "该功能未开放：当前配置或服务器不支持。"


async def test_rank_today_in_strict_returns_notice():
    out = await _cmds(mode="strict").rank("u", "today", True)
    assert "strict" in out or "停用" in out


async def test_rank_total_in_strict_returns_notice():
    out = await _cmds(mode="strict").rank("u", "total", True)
    assert "strict" in out or "停用" in out


async def test_rank_level_not_affected_by_strict():
    out = await _cmds(mode="strict").rank("u", "level", True)
    assert "等级榜" in out


async def test_rank_default_is_today_board():
    out = await _cmds().rank("u", "", True)
    assert "今日在线时长榜" in out and "等级榜" not in out
