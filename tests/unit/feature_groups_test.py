"""端点→组映射与 active_endpoints（spec §4）。"""
from palworld_terminal.application.feature_groups import active_endpoints
from palworld_terminal.config import FeaturesConfig
from palworld_terminal.domain.enums import EndpointName

_CORE = {EndpointName.INFO, EndpointName.METRICS, EndpointName.PLAYERS, EndpointName.SETTINGS}


def test_guilds_bases_off_excludes_game_data():
    eps = active_endpoints(FeaturesConfig(True, True, False))
    assert EndpointName.GAME_DATA not in eps
    assert _CORE <= eps


def test_guilds_bases_on_includes_game_data():
    assert EndpointName.GAME_DATA in active_endpoints(FeaturesConfig(True, True, True))


def test_core_endpoints_always_present_even_all_off():
    assert _CORE <= active_endpoints(FeaturesConfig(False, False, False))
