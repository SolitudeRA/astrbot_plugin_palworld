from palworld_terminal.domain.enums import EndpointName as E
from palworld_terminal.shared.command_permissions import (
    OBSERVATION_FLOOR,
    active_endpoints,
)
from palworld_terminal.shared.command_permissions import (
    CommandOverride as CO,
)


def test_floor_always_present_even_when_all_disabled():
    ov = {g: CO(enabled=False) for g in ("world", "guild", "player", "server")}
    act = active_endpoints(ov)
    assert OBSERVATION_FLOOR <= act
    assert E.GAME_DATA not in act


def test_game_data_derived_from_guild_enable():
    # GAME_DATA 端点仅当某条 guilds_bases 命令 effective_enabled 才轮询（派生自组/叶生效值）。
    assert E.GAME_DATA not in active_endpoints({})
    assert E.GAME_DATA in active_endpoints({"guild": CO(enabled=True)})
    assert E.GAME_DATA in active_endpoints({"guild bases": CO(enabled=True)})
