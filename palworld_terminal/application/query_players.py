from __future__ import annotations

from ..domain.models import PlayerIdentity, World
from ..infrastructure.clock import Clock
from .query_privacy import _PrivacyBase
from .query_support import PlayerProfileDTO, RankBoardsDTO
from .report_service import day_bounds


class _RankProfileQueries(_PrivacyBase):
    """排行榜 / 玩家档案查询（rank、player_profile、profile_for_key）。"""

    _clock: Clock

    def _converge_by_name(
        self, pairs: list[tuple[str, int]], excluded_names: set[str], n: int,
    ) -> list[tuple[str, int]]:
        """(name, secs) 列表按显示名归并求和,被排除/隐藏名字整组剔除,取 Top-N。
        今日/total 两榜共用同一名字级收敛剔除(存在性收敛:不让同名另一 key 补位,
        泄露被隐藏者的活动)。"""
        name_totals: dict[str, int] = {}
        for name, secs in pairs:
            if secs <= 0:
                continue
            name_totals[name] = name_totals.get(name, 0) + secs
        for name in excluded_names:
            name_totals.pop(name, None)
        return sorted(name_totals.items(), key=lambda kv: (-kv[1], kv[0]))[:n]

    async def rank(self, world: World, mode: str = "both") -> RankBoardsDTO:
        excluded = await self.load_excluded_keys(world)
        n = self._cfg.players.rank_top_n
        now = self._clock.now()

        time_rows: list[tuple[str, int]] = []
        if mode in ("both", "today", "time"):
            _day, start, end = day_bounds(self._cfg, world, now)
            sessions = await self._repo.sessions_in_day(world.world_id, start, end)
            # 时长按会话与今日窗口的墙钟交叠计入、以 observed_seconds 封顶——
            # 跨午夜会话不再把昨日时长整段灌进今日榜,采样缺口也不虚增。
            pairs: list[tuple[str, int]] = []
            banned_names: set[str] = set()
            for s in sessions:
                ident = await self._repo.get_player(world.world_id, s.player_key)
                name = ident.latest_name if ident is not None else s.player_key[:8]
                if s.player_key in excluded:
                    banned_names.add(name)
                    continue
                wall_end = s.left_at if s.left_at is not None else now
                overlap = min(end, wall_end) - max(start, s.joined_at)
                secs = min(s.observed_seconds, max(overlap, 0))
                pairs.append((name, secs))
            time_rows = self._converge_by_name(pairs, banned_names, n)

        total_rows: list[tuple[str, int]] = []
        if mode == "total":
            # total = 留存期内(受 prune session_days 裁剪)累计 Σobserved_seconds,
            # 直接求和、无墙钟窗口封顶(与今日榜逻辑不同套)。隐私必须复用同一名字级
            # 收敛:被排除/隐藏 key 的整组名字剔除,不得只按 player_key 裸过滤。
            durations = await self._repo.total_durations(world.world_id)
            pairs = []
            banned_names = set()
            for player_key, secs in durations.items():
                ident = await self._repo.get_player(world.world_id, player_key)
                name = ident.latest_name if ident is not None else player_key[:8]
                if player_key in excluded:
                    banned_names.add(name)
                    continue
                pairs.append((name, secs))
            total_rows = self._converge_by_name(pairs, banned_names, n)

        level_rows: list[tuple[str, int]] = []
        if mode in ("both", "level"):
            players = await self._repo.list_players_by_level(world.world_id)
            # 与时长榜同一收敛语义:名字被任何被排除/隐藏 key 占用即整组不上榜
            hidden_names = {p.latest_name for p in players if p.player_key in excluded}
            seen: set[str] = set()
            for p in players:
                if p.latest_name in hidden_names or p.latest_name in seen:
                    continue
                seen.add(p.latest_name)
                level_rows.append((p.latest_name, p.latest_level))
                if len(level_rows) >= n:
                    break

        return RankBoardsDTO(time_rows=time_rows, level_rows=level_rows, total_rows=total_rows)

    async def _profile_extras(
        self, world: World, ident: PlayerIdentity
    ) -> tuple[int, int, str | None]:
        """卡片扩字段供数（spec §5#5/§5#16）：今日在线（day 窗口 per-player 墙钟交叠，
        与 rank today 同源同封顶口径）、留存期累计（同源 rank total，Σobserved_seconds）、
        公会名（latest_guild_key → list_guilds 解析；gamedata 锁定期公会表空→None→省行）。"""
        now = self._clock.now()
        _day, start, end = day_bounds(self._cfg, world, now)
        today = 0
        for s in await self._repo.sessions_in_day(world.world_id, start, end):
            if s.player_key != ident.player_key:
                continue
            wall_end = s.left_at if s.left_at is not None else now
            overlap = min(end, wall_end) - max(start, s.joined_at)
            today += min(s.observed_seconds, max(overlap, 0))
        totals = await self._repo.total_durations(world.world_id)
        total = totals.get(ident.player_key, 0)
        guild_name: str | None = None
        if ident.latest_guild_key is not None:
            for g in await self._repo.list_guilds(world.world_id):
                if g.guild_key == ident.latest_guild_key:
                    guild_name = g.latest_name
                    break
        return today, total, guild_name

    async def _build_profile(
        self, world: World, ident: PlayerIdentity, *, hidden: bool
    ) -> PlayerProfileDTO:
        session = await self._repo.get_open_session(world.world_id, ident.player_key)
        today, total, guild_name = await self._profile_extras(world, ident)
        return PlayerProfileDTO(
            name=ident.latest_name, level=ident.latest_level,
            online=session is not None,
            online_seconds=session.observed_seconds if session is not None else 0,
            first_seen_at=ident.first_seen_at, last_seen_at=ident.last_seen_at,
            guild_name=guild_name, today_seconds=today, total_seconds=total,
            hidden=hidden,
        )

    async def player_profile(self, world: World, name: str) -> PlayerProfileDTO | None:
        """/pal player info：按名解析 + name_banned 名字级收敛（隐藏玩家返 None，
        故 player info 卡片 hidden 恒 False——不泄漏被隐藏者存在）。"""
        ident = await self._repo.get_player_by_name(world.world_id, name)
        if ident is None:
            return None
        excluded = await self.load_excluded_keys(world)
        if await self.name_banned(world, ident.latest_name, excluded):
            return None
        return await self._build_profile(world, ident, hidden=False)

    async def profile_for_key(
        self, world: World, player_key: str
    ) -> PlayerProfileDTO | None:
        """/pal me：按绑定 player_key 直取（不套 name_banned——本人可见自己即便已隐藏）；
        hidden 标记查 get_hidden_keys 落「· 已隐藏」角标。悬空绑定（玩家行不存在）返 None。"""
        ident = await self._repo.get_player(world.world_id, player_key)
        if ident is None:
            return None
        hidden = player_key in await self._repo.get_hidden_keys(world.world_id)
        return await self._build_profile(world, ident, hidden=hidden)
