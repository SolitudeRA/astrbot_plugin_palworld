"""特性分组：端点→所属组映射与启用端点计算（spec §4）。core 端点恒启用。"""
from __future__ import annotations

from ..config import FeaturesConfig
from ..domain.enums import EndpointName

ENDPOINT_GROUP: dict[EndpointName, str] = {
    EndpointName.INFO: "core",
    EndpointName.METRICS: "core",
    EndpointName.PLAYERS: "core",
    EndpointName.SETTINGS: "core",
    EndpointName.GAME_DATA: "guilds_bases",
}


def active_endpoints(features: FeaturesConfig) -> frozenset[EndpointName]:
    return frozenset(
        ep for ep, group in ENDPOINT_GROUP.items()
        if group == "core" or features.enabled(group)
    )
