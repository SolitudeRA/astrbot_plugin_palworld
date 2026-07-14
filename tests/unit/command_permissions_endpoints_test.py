from palworld_terminal.application.command_permissions import (
    CommandOverride as CO, active_endpoints, OBSERVATION_FLOOR,
)
from palworld_terminal.domain.enums import EndpointName as E


def test_floor_always_present_even_when_all_disabled():
    ov = {g: CO(enabled=False) for g in ("world", "guild", "player", "server")}
    act = active_endpoints(ov)
    assert OBSERVATION_FLOOR <= act
    assert E.GAME_DATA not in act


def test_game_data_derived_from_guild_enable():
    assert E.GAME_DATA not in active_endpoints({})
    assert E.GAME_DATA in active_endpoints({"guild": CO(enabled=True)})
    assert E.GAME_DATA in active_endpoints({"guild bases": CO(enabled=True)})
