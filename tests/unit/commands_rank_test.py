from types import SimpleNamespace

import pytest

from palchronicle.application.query_service import RankBoardsDTO
from palchronicle.presentation.commands import Commands


class _Query:
    async def rank(self, world):
        return RankBoardsDTO(time_rows=[("A", 60)], level_rows=[("A", 9)])


def _cmds(mode="balanced", players_on=True):
    features = SimpleNamespace(enabled=lambda g: players_on if g == "players" else True)
    cfg = SimpleNamespace(features=features, privacy=SimpleNamespace(mode=mode))
    c = Commands(routing=None, query=_Query(), repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))
    async def _rw(umo, msg, sub, is_group):
        return SimpleNamespace(world_id="w1", server_id="w"), SimpleNamespace(name=msg, server_override=None), None
    c._resolve_world = _rw
    return c


async def test_rank_gated_off_returns_feature_disabled():
    out = await _cmds(players_on=False).rank("u", "", True)
    assert out == "该功能未开放：当前配置或服务器不支持。"


async def test_rank_time_in_strict_returns_notice():
    out = await _cmds(mode="strict").rank("u", "time", True)
    assert "strict" in out or "停用" in out


async def test_rank_default_shows_boards():
    out = await _cmds().rank("u", "", True)
    assert "等级榜" in out
