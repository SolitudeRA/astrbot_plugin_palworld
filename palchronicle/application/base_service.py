from __future__ import annotations

import math
from dataclasses import dataclass

from palchronicle.adapters.privacy_filter import hash_user_id, quantize_cell
from palchronicle.domain.enums import Confidence
from palchronicle.domain.models import GameDataSnapshot, PalBox, World


@dataclass(slots=True)
class BaseUpdate:
    base_key: str
    world_id: str
    palbox_key: str
    guild_key: str | None
    confidence: Confidence
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int]
    is_new: bool
    is_vanished: bool
    prev_worker_count: int | None


class BaseService:
    def __init__(self, repo, cfg, clock, salt: bytes):
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt

    @staticmethod
    def palbox_key(world_id: str, guild_key: str | None, cell: str) -> str:
        return f"{world_id}|{guild_key}|{cell}"

    @staticmethod
    def base_key(world_id: str, anchor_palbox_key: str) -> str:
        return f"{world_id}|BASE|{anchor_palbox_key}"

    def _guild_key(self, world_id: str, guild_id: str | None) -> str | None:
        if not guild_id:
            return None
        return hash_user_id(self._salt, world_id, "GUILD:" + guild_id)

    def _match_palboxes(self, world: World, gd: GameDataSnapshot,
                        existing: list[PalBox]) -> dict[int, PalBox]:
        grid = self._cfg.position_grid_size
        now = gd.observed_at
        by_guild: dict[str | None, list[PalBox]] = {}
        for pb in existing:
            by_guild.setdefault(pb.guild_key, []).append(pb)

        result: dict[int, PalBox] = {}
        for idx, box in enumerate(gd.palboxes):
            gk = self._guild_key(world.world_id, box.guild_id)
            cell = quantize_cell(box.x, box.y, box.z, grid)
            candidates = by_guild.get(gk, [])
            match = self._nearest_within_grid(cell, candidates, grid)
            if match is not None:
                match.last_seen_at = now
                match.status = "active"
                result[idx] = match
            else:
                key = self.palbox_key(world.world_id, gk, cell)
                pb = PalBox(key, world.world_id, gk, cell, now, now, "active")
                by_guild.setdefault(gk, []).append(pb)
                result[idx] = pb
        return result

    @staticmethod
    def _nearest_within_grid(cell: str, candidates: list[PalBox], grid: int) -> PalBox | None:
        cx, cy, cz = (int(p) for p in cell.split(":"))
        best: PalBox | None = None
        best_d = None
        for c in candidates:
            px, py, pz = (int(p) for p in c.position_cell.split(":"))
            d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2)
            if d <= 1.0 and (best_d is None or d < best_d):  # 相邻/同格(以格为单位)
                best, best_d = c, d
        return best
