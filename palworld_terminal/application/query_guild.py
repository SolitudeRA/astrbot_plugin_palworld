from __future__ import annotations

from ..domain.enums import EventType
from ..domain.models import Base, BaseObservation, World
from ..infrastructure.cache import TTLCache
from .dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventView,
    GuildDetailDTO,
    GuildDTO,
    event_view,
)
from .query_privacy import _PrivacyBase


class _GuildBaseQueries(_PrivacyBase):
    """公会 / 据点查询（guilds、guild、bases、base）。"""

    _cache: TTLCache
    _GUILDS_TTL: int
    _BASES_TTL: int

    @staticmethod
    def _health_score(o: BaseObservation) -> float:
        return round(100 * (0.8 * o.average_hp_ratio + 0.2 * 1.0), 2)

    async def _base_counts_by_guild(self, world: World) -> dict[str | None, int]:
        """每公会据点数（spec §5#15）：按统一序号空间（include_low，hidden 排除）的
        guild_key 分组计数——与 guild bases 列表 / guild info 据点节口径一致。"""
        counts: dict[str | None, int] = {}
        for b in await self._repo.list_bases(world.world_id, include_low=True):
            counts[b.guild_key] = counts.get(b.guild_key, 0) + 1
        return counts

    async def guilds(self, world: World) -> list[GuildDTO]:
        key = f"guilds:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        guilds = await self._repo.list_guilds(world.world_id)
        base_counts = await self._base_counts_by_guild(world)
        dtos = [
            GuildDTO(
                name=g.latest_name, observed_members=g.observed_member_count,
                base_pals=g.base_pal_count, base_count=base_counts.get(g.guild_key, 0),
            )
            for g in guilds
        ]
        self._cache.set(key, dtos, self._GUILDS_TTL)
        return dtos

    async def guild(self, world: World, name: str) -> GuildDetailDTO | None:
        key = f"guild:{world.world_id}:{name}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        guilds = await self._repo.list_guilds(world.world_id)
        target = None
        for g in guilds:
            if g.latest_name == name:
                target = g
                break
        if target is None:
            return None  # not found: do not cache None
        # 据点列表（§5#15）：统一序号空间（include_low、hidden 排除，与 guild bases/事件解析同源），
        # 按 guild_key 过滤；无名据点回退 BASE-{序号}。
        guild_bases = [
            (i, b) for i, b in await self._bases_indexed(world) if b.guild_key == target.guild_key
        ]
        bases_list = [(b.display_name or f"BASE-{i}", b.confidence) for i, b in guild_bases]
        recent = await self._guild_recent_events(world, {b.base_key for _, b in guild_bases})
        # active_today/active_week/average_level/palbox 均 v0.1 恒 0 占位，本次砍位不再入 DTO。
        dto = GuildDetailDTO(
            name=target.latest_name,
            first_seen_at=target.first_seen_at,
            last_seen_at=target.last_seen_at,
            observed_members=target.observed_member_count,
            base_pals=target.base_pal_count,
            base_count=len(guild_bases),
            bases=bases_list,
            recent_events=recent,
        )
        self._cache.set(key, dto, self._GUILDS_TTL)
        return dto

    # guild info 近期动态实填（spec §4.7）：仅该公会据点的三类据点事件；本层只经 event_view
    # 构造 EventView（与 events/today 同源单一构造入口，措辞渲染下沉 presentation.render_event），
    # 据点名经 name_resolver 统一序号空间解析。
    _GUILD_BASE_EVENTS = (EventType.NEW_BASE, EventType.WORKER_DELTA, EventType.BASE_VANISHED)

    async def _guild_recent_events(
        self, world: World, guild_base_keys: set[str]
    ) -> list[EventView]:
        if not guild_base_keys:
            return []
        events = await self._repo.list_events(world.world_id, since=None, limit=20)
        relevant = [
            e for e in events
            if e.subject_type == "base"
            and e.subject_key in guild_base_keys
            and e.event_type in self._GUILD_BASE_EVENTS
        ]
        if not relevant:
            return []
        names = await self.resolve_event_subjects(world, relevant)
        return [event_view(e, names.get(e.subject_key, "")) for e in relevant]

    async def _bases_indexed(self, world: World) -> list[tuple[int, Base]]:
        # 统一序号空间（spec §3 据点名口径）：BASE-n 编号 / guild bases 列表序号 /
        # guild base #序号 查找 / 事件主体解析全部基于同一张含 low 置信度、hidden 排除
        # 的清单——否则事件里的 #N 与 /pal guild base #N 会对不上。
        bases = await self._repo.list_bases(world.world_id, include_low=True)
        return list(enumerate(bases, start=1))

    async def bases(self, world: World) -> list[BaseDTO]:
        key = f"bases:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        # 键放宽为 str | None：Base.guild_key 可能为 None，get(None) 返回 None 即可
        guild_names: dict[str | None, str] = {
            g.guild_key: g.latest_name for g in await self._repo.list_guilds(world.world_id)
        }
        # worker_count 实填（§5#15）：每据点一条 latest_base_observation 索引查询（现恒 0）。
        dtos = []
        for i, b in await self._bases_indexed(world):
            obs = await self._repo.latest_base_observation(world.world_id, b.base_key)
            dtos.append(BaseDTO(
                index=i, display_name=b.display_name or f"BASE-{i}",
                guild_name=guild_names.get(b.guild_key), confidence=b.confidence,
                worker_count=obs.worker_count if obs else 0,
            ))
        self._cache.set(key, dtos, self._BASES_TTL)
        return dtos

    async def base(self, world: World, key_or_index: str) -> BaseDetailDTO | None:
        indexed = await self._bases_indexed(world)
        # 键放宽为 str | None：Base.guild_key 可能为 None，get(None) 返回 None 即可
        guild_names: dict[str | None, str] = {
            g.guild_key: g.latest_name for g in await self._repo.list_guilds(world.world_id)
        }
        target = None
        target_idx = 0
        token = key_or_index.strip()
        if token.startswith("#"):
            try:
                idx = int(token[1:])
            except ValueError:
                return None
            for i, b in indexed:
                if i == idx:
                    target, target_idx = b, i
                    break
        else:
            for i, b in indexed:
                if (b.display_name and b.display_name == token) or guild_names.get(b.guild_key) == token:
                    target, target_idx = b, i
                    break
        if target is None:
            return None
        # 无观测（obs is None）→ available=False：formatter 走 ⚠️「尚无观测数据」，不再全 0 假数据（§6#8）。
        obs = await self._repo.latest_base_observation(world.world_id, target.base_key)
        return BaseDetailDTO(
            display_name=target.display_name or f"BASE-{target_idx}",
            guild_name=guild_names.get(target.guild_key),
            confidence=target.confidence,
            worker_count=obs.worker_count if obs else 0,
            active_count=obs.active_count if obs else 0,
            average_level=obs.average_level if obs else 0.0,
            average_hp_ratio=obs.average_hp_ratio if obs else 0.0,
            action_distribution=obs.action_distribution if obs else {},
            health_score=self._health_score(obs) if obs else 0.0,
            available=obs is not None,
        )
