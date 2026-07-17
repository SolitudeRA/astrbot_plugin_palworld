from types import SimpleNamespace

from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.application.query_service import PlayerProfileDTO
from palworld_terminal.presentation.commands import Commands


class _Query:
    def __init__(self, dto):
        self._dto = dto
    async def player_profile(self, world, name):
        return self._dto


def _cmds(dto, mode="balanced"):
    ov = {"player info": CommandOverride(enabled=True)}
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=ov),
        privacy=SimpleNamespace(mode=mode),
    )
    c = Commands(routing=None, query=_Query(dto), repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))
    async def _rw(umo, msg, sub, is_group):
        return SimpleNamespace(world_id="w1"), SimpleNamespace(name=msg, server_override=None), None, "srv"
    c._resolve_world = _rw
    return c


async def test_player_found():
    out = await _cmds(PlayerProfileDTO("Alice", 12, True, 900)).player("u", "Alice", True)
    assert "Alice" in out and "Lv12" in out


async def test_player_not_found():
    out = await _cmds(None).player("u", "Ghost", True)
    assert out == "未找到玩家「Ghost」。"


async def test_player_empty_name_usage():
    out = await _cmds(None).player("u", "", True)
    assert "用法" in out
