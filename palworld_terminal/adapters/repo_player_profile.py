from __future__ import annotations

from typing import cast

from ..domain.enums import IdConfidence, LeaveReason, PingBucket, SessionStatus
from ..domain.models import PlayerIdentity, PlayerObservation, PlayerSession
from ..infrastructure.database import Database


class _PlayerProfileRepo:
    """players / player_sessions / player_observations 表族：玩家档案、会话、观测。"""

    _db: Database

    # ---- players ----
    async def upsert_player(self, p: PlayerIdentity) -> None:
        await self._db.execute_write(
            """
            INSERT INTO players
                (player_key, world_id, latest_name, first_seen_at, last_seen_at,
                 latest_level, latest_guild_key, id_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_key, world_id) DO UPDATE SET
                latest_name = excluded.latest_name,
                last_seen_at = excluded.last_seen_at,
                latest_level = excluded.latest_level,
                latest_guild_key = excluded.latest_guild_key,
                id_confidence = excluded.id_confidence
            """,
            (p.player_key, p.world_id, p.latest_name, p.first_seen_at,
             p.last_seen_at, p.latest_level, p.latest_guild_key, str(p.id_confidence)),
        )

    async def get_player(self, world_id: str, player_key: str) -> PlayerIdentity | None:
        rows = await self._db.query(
            "SELECT player_key, world_id, latest_name, first_seen_at, last_seen_at,"
            " latest_level, latest_guild_key, id_confidence"
            " FROM players WHERE world_id = ? AND player_key = ?",
            (world_id, player_key),
        )
        if not rows:
            return None
        r = rows[0]
        return PlayerIdentity(
            player_key=r["player_key"], world_id=r["world_id"],
            latest_name=r["latest_name"], first_seen_at=r["first_seen_at"],
            last_seen_at=r["last_seen_at"], latest_level=r["latest_level"],
            latest_guild_key=r["latest_guild_key"],
            id_confidence=IdConfidence(r["id_confidence"]),
        )

    async def get_player_by_name(self, world_id: str, name: str) -> PlayerIdentity | None:
        rows = await self._db.query(
            """
            SELECT player_key, world_id, latest_name, first_seen_at, last_seen_at,
                   latest_level, latest_guild_key, id_confidence
            FROM players WHERE world_id = ? AND latest_name = ?
            ORDER BY last_seen_at DESC LIMIT 1
            """,
            (world_id, name),
        )
        if not rows:
            return None
        r = rows[0]
        return PlayerIdentity(
            player_key=r["player_key"], world_id=r["world_id"],
            latest_name=r["latest_name"], first_seen_at=r["first_seen_at"],
            last_seen_at=r["last_seen_at"], latest_level=r["latest_level"],
            latest_guild_key=r["latest_guild_key"],
            id_confidence=IdConfidence(r["id_confidence"]),
        )

    async def list_players_by_name(self, world_id: str, name: str) -> list[str]:
        rows = await self._db.query(
            "SELECT player_key FROM players WHERE world_id=? AND latest_name=?",
            (world_id, name),
        )
        return [r[0] for r in rows]

    async def list_players_by_level(self, world_id: str) -> list[PlayerIdentity]:
        rows = await self._db.query(
            "SELECT player_key, world_id, latest_name, first_seen_at, last_seen_at,"
            " latest_level, latest_guild_key, id_confidence"
            " FROM players"
            " WHERE world_id=? AND latest_level IS NOT NULL AND latest_name IS NOT NULL"
            " ORDER BY latest_level DESC, last_seen_at DESC, player_key ASC",
            (world_id,),
        )
        return [
            PlayerIdentity(
                player_key=r["player_key"], world_id=r["world_id"],
                latest_name=r["latest_name"], first_seen_at=r["first_seen_at"],
                last_seen_at=r["last_seen_at"], latest_level=r["latest_level"],
                latest_guild_key=r["latest_guild_key"],
                id_confidence=IdConfidence(r["id_confidence"]),
            )
            for r in rows
        ]

    # ---- sessions ----
    @staticmethod
    def _row_to_session(r) -> PlayerSession:
        return PlayerSession(
            id=r["id"], world_id=r["world_id"], player_key=r["player_key"],
            joined_at=r["joined_at"], last_confirmed_at=r["last_confirmed_at"],
            left_at=r["left_at"], observed_seconds=r["observed_seconds"],
            status=SessionStatus(r["status"]),
            leave_reason=LeaveReason(r["leave_reason"]) if r["leave_reason"] else None,
        )

    async def insert_session(self, s: PlayerSession) -> int:
        async with self._db.write_tx() as conn:
            cur = await conn.execute(
                """
                INSERT INTO player_sessions
                    (world_id, player_key, joined_at, last_confirmed_at, left_at,
                     observed_seconds, status, leave_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (s.world_id, s.player_key, s.joined_at, s.last_confirmed_at,
                 s.left_at, s.observed_seconds, str(s.status),
                 str(s.leave_reason) if s.leave_reason else None),
            )
            s.id = cur.lastrowid
            # INSERT 成功后 lastrowid 必非 None（sqlite3 类型标注偏宽）
            return cast(int, cur.lastrowid)

    async def update_session(self, s: PlayerSession) -> None:
        await self._db.execute_write(
            """
            UPDATE player_sessions SET
                last_confirmed_at = ?, left_at = ?, observed_seconds = ?,
                status = ?, leave_reason = ?
            WHERE id = ?
            """,
            (s.last_confirmed_at, s.left_at, s.observed_seconds, str(s.status),
             str(s.leave_reason) if s.leave_reason else None, s.id),
        )

    async def get_open_session(self, world_id: str, player_key: str) -> PlayerSession | None:
        rows = await self._db.query(
            """
            SELECT * FROM player_sessions
            WHERE world_id = ? AND player_key = ? AND status IN ('active', 'uncertain')
            ORDER BY (status = 'active') DESC, joined_at DESC LIMIT 1
            """,
            (world_id, player_key),
        )
        return self._row_to_session(rows[0]) if rows else None

    async def list_open_sessions(self, world_id: str) -> list[PlayerSession]:
        rows = await self._db.query(
            """
            SELECT * FROM player_sessions
            WHERE world_id = ? AND status IN ('active', 'uncertain')
            ORDER BY joined_at ASC
            """,
            (world_id,),
        )
        return [self._row_to_session(r) for r in rows]

    async def sessions_in_day(
        self, world_id: str, start_ts: int, end_ts: int
    ) -> list[PlayerSession]:
        """与 [start_ts, end_ts) 窗口有交叠的会话（进行中会话 left_at 为 NULL 也计入）。"""
        rows = await self._db.query(
            """
            SELECT * FROM player_sessions
            WHERE world_id = ? AND joined_at < ?
              AND (left_at IS NULL OR left_at >= ?)
            ORDER BY joined_at ASC
            """,
            (world_id, end_ts, start_ts),
        )
        return [self._row_to_session(r) for r in rows]

    async def total_durations(self, world_id: str) -> dict[str, int]:
        """各 player_key 在留存期内(受 prune 按 session_days 裁剪)的累计
        observed_seconds。直接 Σ 求和、无日窗/墙钟封顶——与 sessions_in_day 的
        当日窗口交叠逻辑不同套(留存期累计时长榜 total 用)。"""
        rows = await self._db.query(
            "SELECT player_key, SUM(observed_seconds) AS total FROM player_sessions"
            " WHERE world_id = ? GROUP BY player_key",
            (world_id,),
        )
        return {r["player_key"]: int(r["total"]) for r in rows if r["total"] is not None}

    # ---- observations ----
    async def insert_observation(self, o: PlayerObservation) -> None:
        await self._db.execute_write(
            """
            INSERT INTO player_observations
                (world_id, player_key, observed_at, level, ping_bucket,
                 building_count, guild_key, companion_class, position_cell)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (o.world_id, o.player_key, o.observed_at, o.level, str(o.ping_bucket),
             o.building_count, o.guild_key, o.companion_class, o.position_cell),
        )

    async def climb_levels(
        self, world_id: str, window_start: int
    ) -> list[tuple[str, int, int, bool]]:
        """飞升榜数据源（spec §7）：每个有等级观测的玩家一行
        (player_key, baseline_level, current_level, has_pre_window_baseline)。

        current = 最新观测 level；baseline = observed_at <= window_start 的最新观测 level，
        无窗前观测则取该玩家最早观测 level（新玩家 fallback）。has_pre_window_baseline 供
        application 判定「历史深度不足」（全体皆 False → bot 记录不足一窗）。level 为 NULL 的
        观测（未采到等级）忽略；gain=max(0,…) / 名字级收敛 / 排名均在 application 层。"""
        rows = await self._db.query(
            """
            SELECT cur.player_key AS player_key, cur.level AS current_level,
                   (SELECT b.level FROM player_observations b
                     WHERE b.world_id = cur.world_id AND b.player_key = cur.player_key
                       AND b.level IS NOT NULL AND b.observed_at <= ?
                     ORDER BY b.observed_at DESC LIMIT 1) AS pre_level,
                   (SELECT e.level FROM player_observations e
                     WHERE e.world_id = cur.world_id AND e.player_key = cur.player_key
                       AND e.level IS NOT NULL
                     ORDER BY e.observed_at ASC LIMIT 1) AS earliest_level
            FROM player_observations cur
            WHERE cur.world_id = ? AND cur.level IS NOT NULL
              AND cur.observed_at = (SELECT MAX(o.observed_at) FROM player_observations o
                                      WHERE o.world_id = cur.world_id
                                        AND o.player_key = cur.player_key
                                        AND o.level IS NOT NULL)
            """,
            (window_start, world_id),
        )
        out: dict[str, tuple[str, int, int, bool]] = {}
        for r in rows:
            pre = r["pre_level"]
            baseline = pre if pre is not None else r["earliest_level"]
            # observed_at 并列理论可致同玩家多行——dict 去重（同刻 level 一致，任取其一）。
            out[r["player_key"]] = (
                r["player_key"], baseline, r["current_level"], pre is not None,
            )
        return list(out.values())

    async def latest_observation(self, world_id: str, player_key: str) -> PlayerObservation | None:
        rows = await self._db.query(
            """
            SELECT world_id, player_key, observed_at, level, ping_bucket,
                   building_count, guild_key, companion_class, position_cell
            FROM player_observations
            WHERE world_id = ? AND player_key = ?
            ORDER BY observed_at DESC LIMIT 1
            """,
            (world_id, player_key),
        )
        if not rows:
            return None
        r = rows[0]
        return PlayerObservation(
            observed_at=r["observed_at"], world_id=r["world_id"],
            player_key=r["player_key"], name="", level=r["level"],
            ping_bucket=PingBucket(r["ping_bucket"]),
            building_count=r["building_count"], guild_key=r["guild_key"],
            position_cell=r["position_cell"], companion_class=r["companion_class"],
        )
