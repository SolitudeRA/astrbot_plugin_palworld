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


_VANISH_MISSES = 3


class BaseService:
    def __init__(self, repo, cfg, clock, salt: bytes):
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt
        self._confirm: dict[str, int] = {}
        self._anchor_xy: dict[str, tuple[float, float, float]] = {}
        # 连续缺失计数：base_key -> streak；达到 _VANISH_MISSES 触发消失（spec §11）
        self._base_missing: dict[str, int] = {}

    async def apply(self, world: World, gd: GameDataSnapshot) -> list[BaseUpdate]:
        from palchronicle.domain.enums import ActionCategory, UnitType
        from palchronicle.domain.models import Base, BaseObservation

        existing = await self._repo.list_palboxes(world.world_id)
        matched = self._match_palboxes(world, gd, existing)
        for pb in {id(v): v for v in matched.values()}.values():
            await self._repo.upsert_palbox(pb)

        radius = self._cfg.assignment_radius
        zw = self._cfg.z_weight
        # 每个 palbox_key 聚合分配到它的 BaseCampPal
        agg: dict[str, dict] = {}
        ambiguous: dict[str, bool] = {}
        palbox_by_key = {pb.palbox_key: pb for pb in matched.values()}

        for a in gd.characters:
            if a.unit_type != UnitType.BASE_CAMP or a.x is None:
                continue
            gk = self._guild_key(world.world_id, a.guild_id)
            same_guild = [pb for pb in palbox_by_key.values() if pb.guild_key == gk]
            dists = sorted(
                ((self._distance(a, pb, zw), pb) for pb in same_guild),
                key=lambda t: t[0],
            )
            if not dists or dists[0][0] >= radius:
                continue
            nearest_d, nearest = dists[0]
            is_amb = (len(dists) > 1 and dists[1][0] > 0
                      and (dists[1][0] - nearest_d) / dists[1][0] < self._cfg.ambiguity_ratio)
            key = nearest.palbox_key
            bucket = agg.setdefault(key, {"pals": [], "nearest_d": nearest_d})
            bucket["pals"].append(a)
            bucket["nearest_d"] = min(bucket["nearest_d"], nearest_d)
            ambiguous[key] = ambiguous.get(key, False) or is_amb

        updates: list[BaseUpdate] = []
        now = gd.observed_at
        for palbox_key, bucket in agg.items():
            pals = bucket["pals"]
            pb = palbox_by_key[palbox_key]
            base_key = self.base_key(world.world_id, palbox_key)
            self._confirm[base_key] = self._confirm.get(base_key, 0) + 1
            confirmed = self._confirm[base_key] >= self._cfg.confirmation_samples

            worker = len(pals)
            active = sum(1 for p in pals if p.action == ActionCategory.WORKING)
            avg_level = sum(p.level or 0 for p in pals) / worker
            hp_ratios = [(p.hp / p.max_hp) for p in pals if p.hp is not None and p.max_hp]
            avg_hp = sum(hp_ratios) / len(hp_ratios) if hp_ratios else 0.0
            dist: dict[str, int] = {}
            for p in pals:
                dist[str(p.action)] = dist.get(str(p.action), 0) + 1

            if ambiguous.get(palbox_key) or not confirmed or pb.guild_key is None:
                confidence = Confidence.LOW
            elif bucket["nearest_d"] < radius * 0.5:
                confidence = Confidence.HIGH
            else:
                confidence = Confidence.MEDIUM

            prev = await self._repo.latest_base_observation(world.world_id, base_key)
            prev_worker = prev.worker_count if prev else None

            is_new = False
            if confirmed:
                already = {b.base_key for b in await self._repo.list_bases(
                    world.world_id, include_low=True, include_hidden=True)}
                is_new = base_key not in already
                await self._repo.upsert_base(Base(
                    base_key=base_key, world_id=world.world_id, palbox_key=palbox_key,
                    display_name=None, guild_key=pb.guild_key, confidence=confidence,
                    locked_by_admin=False, hidden=False,
                    first_seen_at=now, last_seen_at=now,
                ))
                await self._repo.insert_base_observation(BaseObservation(
                    base_key=base_key, world_id=world.world_id, observed_at=now,
                    worker_count=worker, active_count=active,
                    average_level=avg_level, average_hp_ratio=avg_hp,
                    action_distribution=dist,
                ))

            updates.append(BaseUpdate(
                base_key=base_key, world_id=world.world_id, palbox_key=palbox_key,
                guild_key=pb.guild_key, confidence=confidence,
                worker_count=worker, active_count=active, average_level=avg_level,
                average_hp_ratio=avg_hp, action_distribution=dist,
                is_new=is_new, is_vanished=False, prev_worker_count=prev_worker,
            ))

        # 据点消失检测（spec §11）：本轮聚合到帕鲁的 base 视为在场；
        # 已落库 base 连续 _VANISH_MISSES 次缺失 → 发一次 BASE_VANISHED。
        # apply() 仅在 game-data 健康时被调用（SnapshotService 守卫），
        # 且 base_key 以 world_id 键入 → worldguid 变更天然隔离，两前置条件结构性成立。
        present_base_keys = {
            self.base_key(world.world_id, pk) for pk in agg.keys()
        }
        persisted = await self._repo.list_bases(
            world.world_id, include_low=True, include_hidden=True
        )
        for b in persisted:
            if b.base_key in present_base_keys:
                self._base_missing.pop(b.base_key, None)
                continue
            streak = self._base_missing.get(b.base_key, 0) + 1
            if streak >= _VANISH_MISSES:
                updates.append(BaseUpdate(
                    base_key=b.base_key, world_id=world.world_id,
                    palbox_key=b.palbox_key, guild_key=b.guild_key,
                    confidence=b.confidence, worker_count=0, active_count=0,
                    average_level=0.0, average_hp_ratio=0.0, action_distribution={},
                    is_new=False, is_vanished=True, prev_worker_count=None,
                ))
                self._base_missing.pop(b.base_key, None)
            else:
                self._base_missing[b.base_key] = streak
        return updates

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

        self._anchor_xy = {}
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
                self._anchor_xy[match.palbox_key] = (box.x, box.y, box.z)
            else:
                key = self.palbox_key(world.world_id, gk, cell)
                pb = PalBox(key, world.world_id, gk, cell, now, now, "active")
                by_guild.setdefault(gk, []).append(pb)
                result[idx] = pb
                self._anchor_xy[key] = (box.x, box.y, box.z)
        return result

    def _distance(self, actor, pb, z_weight: float) -> float:
        ax, ay, az = self._anchor_xy.get(pb.palbox_key, (0.0, 0.0, 0.0))
        dx = actor.x - ax
        dy = actor.y - ay
        dz = (actor.z or 0.0) - az
        return math.sqrt(dx * dx + dy * dy + z_weight * dz * dz)

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
