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


def test_game_data_not_derived_when_guilds_bases_unavailable():
    # guilds_bases 上游不可用 force-off（§5A②/§5B④）：guild 组/叶显式 on 也不派生
    # GAME_DATA（effective_enabled 恒 False → 端点自然不轮询，采集派生逻辑零改动）。
    assert E.GAME_DATA not in active_endpoints({})
    assert E.GAME_DATA not in active_endpoints({"guild": CO(enabled=True)})
    assert E.GAME_DATA not in active_endpoints({"guild bases": CO(enabled=True)})
