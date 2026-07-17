from types import SimpleNamespace

from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.application.query_service import PlayerProfileDTO
from palworld_terminal.presentation.commands import Commands

_FULL = PlayerProfileDTO(
    name="Alice", level=12, online=True, online_seconds=900,
    first_seen_at=0, last_seen_at=0, guild_name="Matrix",
    today_seconds=900, total_seconds=900, hidden=False,
)


class _Query:
    def __init__(self, dto):
        self._dto = dto
    async def player_profile(self, world, name):
        return self._dto


def _cmds(dto, mode="balanced", world_mode="multi"):
    ov = {"player info": CommandOverride(enabled=True)}
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=ov),
        privacy=SimpleNamespace(mode=mode),
        routing=SimpleNamespace(world_mode=world_mode),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )
    c = Commands(routing=None, query=_Query(dto), repo=None, cfg=cfg,
                 clock=SimpleNamespace(now=lambda: 0))

    async def _rw(umo, msg, sub, is_group):
        world = SimpleNamespace(world_id="w1", server_id="w")
        return world, SimpleNamespace(name=msg, server_override=None), None, "主服"
    c._resolve_world = _rw
    return c


async def test_player_found():
    out = await _cmds(_FULL).player("u", "Alice", True)
    assert "👤 玩家 · Alice" in out and "Lv12" in out and "在线" in out


async def test_player_multi_mode_has_server_anchor():
    out = await _cmds(_FULL, world_mode="multi").player("u", "Alice", True)
    assert "主服" in out


async def test_player_single_mode_omits_server_anchor():
    out = await _cmds(_FULL, world_mode="single").player("u", "Alice", True)
    assert "主服" not in out


async def test_player_not_found():
    out = await _cmds(None).player("u", "Ghost", True)
    assert out.startswith("❌ 未找到玩家「Ghost」")
    assert "/pal online" in out


async def test_player_empty_name_usage():
    out = await _cmds(None).player("u", "", True)
    assert out == "用法：/pal player info <玩家名>"
