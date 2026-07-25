from palworld_terminal.domain.enums import EndpointName as E
from palworld_terminal.shared.command_permissions import (
    OBSERVATION_FLOOR,
    active_endpoints,
)
from palworld_terminal.shared.command_permissions import (
    CommandOverride as CO,
)


def test_floor_always_present_even_when_all_disabled():
    # 显式关全部可配组 + dex 扁平命令（guilds_bases 默认开，须逐一关掉才无 GAME_DATA）。
    ov = {g: CO(enabled=False) for g in ("world", "guild", "player", "server")}
    ov["dex"] = CO(enabled=False)
    act = active_endpoints(ov)
    assert OBSERVATION_FLOOR <= act
    assert E.GAME_DATA not in act


def test_game_data_derived_from_guild_enable():
    # GAME_DATA 端点当某条 guilds_bases 命令 effective_enabled 才轮询；guilds_bases 默认开 → 默认在。
    assert E.GAME_DATA in active_endpoints({})
    # 关掉全部 guilds_bases 源（world overview 经 world 组、guild 组、dex 扁平）→ 不轮询
    off = {"world": CO(enabled=False), "guild": CO(enabled=False), "dex": CO(enabled=False)}
    assert E.GAME_DATA not in active_endpoints(off)
    # 单独开一条即恢复
    assert E.GAME_DATA in active_endpoints({"guild bases": CO(enabled=True)})
