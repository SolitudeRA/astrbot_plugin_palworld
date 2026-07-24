from __future__ import annotations

from typing import Any

from ..domain.enums import ActionCategory, UnitType
from ..domain.models import CharacterActor, PlayerIdentity, World
from ..infrastructure.clock import Clock
from .dtos import CompanionView, MeCardDTO, RankClimbDTO, RankClimbEntry
from .player_service import PlayerService
from .query_privacy import _PrivacyBase
from .query_support import PlayerProfileDTO, RankBoardsDTO
from .report_service import day_bounds

# 飞升榜周窗（spec §7）：now−7d 起算，直算 player_observations 跨周 level 差。
_CLIMB_WINDOW_SECONDS = 7 * 86400


def _days_ago(now: int, ts: int) -> int:
    """绝对时刻 → 距今整天数（预粗化，隐私 P1）：剥离时刻精度，绝不外泄 epoch。"""
    return max(0, (now - ts) // 86400)


def _companion_view(meta: Any, otomo: CharacterActor | None, pal_class: str) -> CompanionView:
    """OtomoPal actor → CompanionView：物种/元素经 meta 解析（缺 meta 优雅降级），
    等级/血比/动作取自 actor。element/action_label 落稳定键，中文/图标映射归 presentation。"""
    species = meta.pal_name(pal_class) if meta is not None else pal_class
    element = meta.element(pal_class) if meta is not None else "unknown"
    level = otomo.level if (otomo is not None and otomo.level is not None) else 0
    action = otomo.action.value if otomo is not None else ActionCategory.UNKNOWN.value
    hp_ratio = 0.0
    if otomo is not None and otomo.hp is not None and otomo.max_hp:
        hp_ratio = min(1.0, max(0.0, otomo.hp / otomo.max_hp))
    return CompanionView(
        species_name=species, element=element, level=level,
        action_label=action, hp_ratio=hp_ratio,
    )


class _RankProfileQueries(_PrivacyBase):
    """排行榜 / 玩家档案查询（rank、rank_climb、player_profile、profile_for_key、me_card）。"""

    _clock: Clock
    _meta: Any          # 随身物种/元素解析（me_card）；隐式 Any，见 query_service 拆分契约
    _world_cache: Any   # 脱敏 game-data 快照（me_card 读随身）；防 mypy attr-defined（复核 SD6）

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

    async def rank_climb(
        self, world: World, viewer_key: str | None = None
    ) -> RankClimbDTO:
        """飞升榜（spec §7）：周窗 [now−7d, now] 内每个有记录玩家的 level 涨幅。

        baseline=窗前最新观测（无则窗内最早）、current=最新观测、gain=max(0, current−baseline)
        （负增量归零：LOW 置信按名 hash 玩家同名换人/存档重置会掉级）。gain==0 不上榜。
        名字级收敛与两时长榜同语义（被排除/隐藏 key 整组剔除，同名多 key 取最高 gain）。
        shallow=全无窗前观测→措辞诚实；viewer_key 命中给「你第 N，离前一位差 X」榜位。
        口径：仅统计有快照记录的玩家。"""
        excluded = await self.load_excluded_keys(world)
        n = self._cfg.players.rank_top_n
        window_start = self._clock.now() - _CLIMB_WINDOW_SECONDS
        raw = await self._repo.climb_levels(world.world_id, window_start)
        shallow = bool(raw) and not any(pre for (_k, _b, _c, pre) in raw)

        banned_names: set[str] = set()
        best: dict[str, int] = {}   # 同名多 key 取最高 gain（名字级去重）
        for player_key, baseline, current, _pre in raw:
            ident = await self._repo.get_player(world.world_id, player_key)
            name = ident.latest_name if ident is not None else player_key[:8]
            if player_key in excluded:
                banned_names.add(name)
                continue
            gain = max(0, current - baseline)
            if gain == 0:
                continue
            if name not in best or gain > best[name]:
                best[name] = gain
        for name in banned_names:
            best.pop(name, None)

        ordered = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
        rows = [RankClimbEntry(name=nm, gain=g) for nm, g in ordered[:n]]

        viewer_rank = viewer_gain = viewer_gap = None
        if viewer_key is not None and viewer_key not in excluded:
            vident = await self._repo.get_player(world.world_id, viewer_key)
            vname = vident.latest_name if vident is not None else None
            if vname is not None and vname in best:
                for i, (nm, g) in enumerate(ordered, 1):
                    if nm == vname:
                        viewer_rank, viewer_gain = i, g
                        viewer_gap = ordered[i - 2][1] - g if i > 1 else None
                        break
        return RankClimbDTO(
            rows=rows, shallow=shallow, viewer_rank=viewer_rank,
            viewer_gain=viewer_gain, viewer_gap=viewer_gap,
        )

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

    async def me_card(self, world: World, player_key: str) -> MeCardDTO | None:
        """/pal me 名片数据层（spec §5）：百分位 + 随身高光三态 + 离线预粗化字段。

        百分位（复核 SD4）：复用 list_players_by_level 等级分布算「超越有记录玩家」比例（C2）。
        随身 join（复核 SD1）：快照已脱敏，Player.player_userid 与 player_key 同为
        hash_user_id 产物、**二者已相等 → 直比命中，绝不再套 hash**（否则 hash(hash)≠key、
        随身恒空）；命中本人 actor 取 instance_id（redact 透传未 hash），经
        link_companions(owner_instance→pal_class) 判随身。
        三态（复核 SD2）：默认部署下 game-data 不轮询 → 在线玩家快照恒空 → no_data，
        **绝不谎称没带**；仅在线 + 有快照 + 本人 actor 在 + 无匹配 OtomoPal → none_out。
        离线时间字段预粗化为距今天数（隐私 P1，无绝对时间戳）。悬空绑定→None。"""
        ident = await self._repo.get_player(world.world_id, player_key)
        if ident is None:
            return None
        now = self._clock.now()
        session = await self._repo.get_open_session(world.world_id, player_key)
        online = session is not None
        today, total, guild_name = await self._profile_extras(world, ident)
        hidden = player_key in await self._repo.get_hidden_keys(world.world_id)

        # 百分位：超越「有记录玩家」的比例（等级严格低于本人者占比）。
        players = await self._repo.list_players_by_level(world.world_id)
        below = sum(1 for p in players if p.latest_level < ident.latest_level)
        percentile = (below / len(players) * 100.0) if players else 0.0

        # 随身三态：默认无快照/本人不在快照/离线 → no_data（不谎称没带）。
        companion: CompanionView | None = None
        companion_status = "no_data"
        gd = self._world_cache.get(world.server_id) if online else None
        if gd is not None:
            actor = next(
                (a for a in gd.characters
                 if a.unit_type == UnitType.PLAYER and a.player_userid == player_key),
                None,
            )
            if actor is not None and actor.instance_id:
                pal_class = PlayerService.link_companions(gd).get(actor.instance_id)
                if pal_class is not None:
                    otomo = next(
                        (a for a in gd.characters
                         if a.unit_type == UnitType.OTOMO
                         and a.trainer_instance_id == actor.instance_id
                         and a.pal_class == pal_class),
                        None,
                    )
                    companion = _companion_view(self._meta, otomo, pal_class)
                    companion_status = "shown"
                else:
                    companion_status = "none_out"

        return MeCardDTO(
            name=ident.latest_name, level=ident.latest_level, online=online,
            online_seconds=session.observed_seconds if session is not None else 0,
            guild_name=guild_name, hidden=hidden,
            today_seconds=today, total_seconds=total, percentile=percentile,
            last_seen_at=_days_ago(now, ident.last_seen_at),
            first_seen_at=_days_ago(now, ident.first_seen_at),
            companion=companion, companion_status=companion_status,
        )
