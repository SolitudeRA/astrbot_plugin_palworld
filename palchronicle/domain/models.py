"""领域模型（dataclass）。字段见契约领域模型节。Phase 1 仅需 World。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class World:
    world_id: str
    server_id: str
    worldguid: str
    epoch: int
    server_name: str
    version: str
    first_seen_at: int
    last_seen_at: int
    current_day: int
