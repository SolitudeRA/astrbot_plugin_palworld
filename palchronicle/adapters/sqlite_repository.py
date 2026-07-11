"""所有表读写（跨阶段增长的同一个 Repository 类）。

Phase 1：server / binding / world / prune 方法。
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from ..config import BindingConfig, HistoryConfig, ServerConfig
from ..domain.enums import (
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
)
from ..domain.models import (
    Base,
    BaseObservation,
    Guild,
    PalBox,
    PlayerIdentity,
    PlayerObservation,
    PlayerSession,
    World,
    WorldEvent,
    WorldMetric,
)
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database

_SECONDS_PER_DAY = 86400


class Repository:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    # ---- servers ----
    async def sync_servers(self, servers: list[ServerConfig]) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            for s in servers:
                await conn.execute(
                    "INSERT INTO servers (server_id, name, host, enabled, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(server_id) DO UPDATE SET "
                    "  name=excluded.name, host=excluded.host, "
                    "  enabled=excluded.enabled, last_seen_at=excluded.last_seen_at",
                    (s.server_id, s.name, s.base_url, 1 if s.enabled else 0, now, now),
                )

    # ---- bindings / routing ----
    async def seed_bindings(self, bindings: list[BindingConfig]) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            for b in bindings:
                cursor = await conn.execute(
                    "SELECT 1 FROM group_servers WHERE umo=? AND server_id=?",
                    (b.umo, b.server),
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists:
                    continue  # seed-only：已存在行不动，绝不覆盖运行时的 allowed/active
                # seed-only 也不得偷走运行时既有的 active：仅当该 umo 尚无任何 active
                # 行时，seed 的 active=true 才生效；否则新行以 allowed=1, active=0 落库。
                seed_active = 0
                if b.active:
                    cursor = await conn.execute(
                        "SELECT 1 FROM group_servers WHERE umo=? AND active=1 LIMIT 1",
                        (b.umo,),
                    )
                    has_active = await cursor.fetchone()
                    await cursor.close()
                    if not has_active:
                        seed_active = 1
                await conn.execute(
                    "INSERT OR IGNORE INTO group_servers "
                    "(umo, server_id, allowed, active, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (b.umo, b.server, seed_active, now),
                )

    async def cleanup_orphan_bindings(self, valid_server_ids: set[str]) -> None:
        rows = await self._db.query("SELECT DISTINCT server_id FROM group_servers")
        orphans = [r[0] for r in rows if r[0] not in valid_server_ids]
        if not orphans:
            return
        async with self._db.write_tx() as conn:
            for server_id in orphans:
                await conn.execute(
                    "DELETE FROM group_servers WHERE server_id=?", (server_id,)
                )

    async def get_binding_active(self, umo: str) -> str | None:
        rows = await self._db.query(
            "SELECT server_id FROM group_servers WHERE umo=? AND active=1 LIMIT 1",
            (umo,),
        )
        return rows[0][0] if rows else None

    async def get_allowed(self, umo: str) -> set[str]:
        rows = await self._db.query(
            "SELECT server_id FROM group_servers WHERE umo=? AND allowed=1", (umo,)
        )
        return {r[0] for r in rows}

    async def list_group_servers(self, umo: str) -> dict[str, tuple[bool, bool]]:
        rows = await self._db.query(
            "SELECT server_id, allowed, active FROM group_servers WHERE umo=?", (umo,)
        )
        return {r["server_id"]: (bool(r["allowed"]), bool(r["active"])) for r in rows}

    async def set_active(self, umo: str, server_id: str) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            # active 唯一：先清同 umo 其它 active。
            await conn.execute(
                "UPDATE group_servers SET active=0, updated_at=? WHERE umo=?",
                (now, umo),
            )
            await conn.execute(
                "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
                "VALUES (?, ?, 1, 1, ?) "
                "ON CONFLICT(umo, server_id) DO UPDATE SET allowed=1, active=1, updated_at=excluded.updated_at",
                (umo, server_id, now),
            )

    async def revoke(self, umo: str, server_id: str) -> None:
        await self._db.execute_write(
            "DELETE FROM group_servers WHERE umo=? AND server_id=?", (umo, server_id)
        )

    # ---- world ----
    async def upsert_world(self, w: World) -> None:
        await self._db.execute_write(
            "INSERT INTO worlds "
            "(world_id, server_id, worldguid, epoch, server_name, version, "
            " first_seen_at, last_seen_at, current_day) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(world_id) DO UPDATE SET "
            "  server_name=excluded.server_name, version=excluded.version, "
            "  last_seen_at=excluded.last_seen_at, current_day=excluded.current_day",
            (
                w.world_id, w.server_id, w.worldguid, w.epoch, w.server_name,
                w.version, w.first_seen_at, w.last_seen_at, w.current_day,
            ),
        )

    async def get_current_world(self, server_id: str) -> World | None:
        rows = await self._db.query(
            "SELECT world_id, server_id, worldguid, epoch, server_name, version, "
            "       first_seen_at, last_seen_at, current_day "
            "FROM worlds WHERE server_id=? ORDER BY last_seen_at DESC LIMIT 1",
            (server_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return World(
            world_id=r[0], server_id=r[1], worldguid=r[2], epoch=r[3],
            server_name=r[4], version=r[5], first_seen_at=r[6],
            last_seen_at=r[7], current_day=r[8],
        )

    async def list_worlds_with_open_sessions(
        self, server_id: str, exclude_world_id: str
    ) -> list[World]:
        """除 exclude_world_id 外, 该服务器仍有 open(active/uncertain) 会话的世界。

        用于重启后从 DB 重建换世界待收敛集合（§10.1）: _prev_worlds 仅存内存,
        热重载会丢失, 旧世界 open 会话若无此路径将永久悬置。
        """
        rows = await self._db.query(
            "SELECT world_id, server_id, worldguid, epoch, server_name, version, "
            "       first_seen_at, last_seen_at, current_day "
            "FROM worlds WHERE server_id=? AND world_id != ? "
            "  AND EXISTS (SELECT 1 FROM player_sessions s "
            "              WHERE s.world_id = worlds.world_id "
            "                AND s.status IN ('active', 'uncertain')) "
            "ORDER BY last_seen_at DESC",
            (server_id, exclude_world_id),
        )
        return [
            World(
                world_id=r[0], server_id=r[1], worldguid=r[2], epoch=r[3],
                server_name=r[4], version=r[5], first_seen_at=r[6],
                last_seen_at=r[7], current_day=r[8],
            )
            for r in rows
        ]

    # ---- retention ----
    async def prune(self, history: HistoryConfig, now: int) -> None:
        metric_cutoff = now - history.raw_metrics_days * _SECONDS_PER_DAY
        obs_cutoff = now - history.observation_days * _SECONDS_PER_DAY
        session_cutoff = now - history.session_days * _SECONDS_PER_DAY
        async with self._db.write_tx() as conn:
            await conn.execute(
                "DELETE FROM world_metrics WHERE observed_at < ?", (metric_cutoff,)
            )
            await conn.execute(
                "DELETE FROM player_observations WHERE observed_at < ?", (obs_cutoff,)
            )
            await conn.execute(
                "DELETE FROM player_sessions WHERE left_at IS NOT NULL AND left_at < ?",
                (session_cutoff,),
            )
            # world_events / daily_aggregates 长期保留（spec §9.3）。

    # ---- metrics ----
    async def insert_metric(self, m: WorldMetric) -> None:
        await self._db.execute_write(
            "INSERT INTO world_metrics"
            " (world_id, observed_at, fps, frame_time, online_players,"
            "  world_day, basecamp_count, max_players)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                m.world_id, m.observed_at, m.fps, m.frame_time,
                m.online_players, m.world_day, m.basecamp_count, m.max_players,
            ),
        )

    async def latest_metric(self, world_id: str) -> WorldMetric | None:
        rows = await self._db.query(
            "SELECT world_id, observed_at, fps, frame_time, online_players,"
            " world_day, basecamp_count, max_players FROM world_metrics"
            " WHERE world_id = ? ORDER BY observed_at DESC LIMIT 1",
            (world_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return WorldMetric(
            world_id=r["world_id"],
            observed_at=r["observed_at"],
            fps=r["fps"],
            frame_time=r["frame_time"],
            online_players=r["online_players"],
            world_day=r["world_day"],
            basecamp_count=r["basecamp_count"],
            max_players=r["max_players"],
        )

    async def peak_online(self, world_id: str, since: int | None = None) -> int:
        if since is None:
            rows = await self._db.query(
                "SELECT MAX(online_players) AS peak FROM world_metrics"
                " WHERE world_id = ?",
                (world_id,),
            )
        else:
            rows = await self._db.query(
                "SELECT MAX(online_players) AS peak FROM world_metrics"
                " WHERE world_id = ? AND observed_at >= ?",
                (world_id, since),
            )
        peak = rows[0]["peak"] if rows else None
        return int(peak) if peak is not None else 0

    async def upsert_unknown_classes(self, classes: list[str]) -> None:
        if not classes:
            return
        now = self._clock.now()
        await self._db.executemany_write(
            "INSERT INTO unknown_classes (class_name, first_seen_at, count)"
            " VALUES (?, ?, 1)"
            " ON CONFLICT(class_name) DO UPDATE SET count = count + 1",
            [(c, now) for c in classes],
        )

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

    # ---- guilds ----
    async def upsert_guild(self, g: Guild) -> None:
        await self._db.execute_write(
            """
            INSERT INTO guilds
                (guild_key, world_id, latest_name, first_seen_at, last_seen_at,
                 observed_member_count, palbox_count, base_pal_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_key, world_id) DO UPDATE SET
                latest_name = excluded.latest_name,
                last_seen_at = excluded.last_seen_at,
                observed_member_count = excluded.observed_member_count,
                palbox_count = excluded.palbox_count,
                base_pal_count = excluded.base_pal_count
            """,
            (g.guild_key, g.world_id, g.latest_name, g.first_seen_at, g.last_seen_at,
             g.observed_member_count, g.palbox_count, g.base_pal_count),
        )

    async def list_guilds(self, world_id: str) -> list[Guild]:
        rows = await self._db.query(
            """
            SELECT guild_key, world_id, latest_name, first_seen_at, last_seen_at,
                   observed_member_count, palbox_count, base_pal_count
            FROM guilds WHERE world_id = ? ORDER BY latest_name ASC
            """,
            (world_id,),
        )
        return [Guild(r["guild_key"], r["world_id"], r["latest_name"],
                      r["first_seen_at"], r["last_seen_at"], r["observed_member_count"],
                      r["palbox_count"], r["base_pal_count"]) for r in rows]

    # ---- palboxes ----
    async def upsert_palbox(self, pb: PalBox) -> None:
        await self._db.execute_write(
            """
            INSERT INTO palboxes
                (palbox_key, world_id, guild_key, position_cell,
                 first_seen_at, last_seen_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(palbox_key, world_id) DO UPDATE SET
                guild_key = excluded.guild_key,
                position_cell = excluded.position_cell,
                last_seen_at = excluded.last_seen_at,
                status = excluded.status
            """,
            (pb.palbox_key, pb.world_id, pb.guild_key, pb.position_cell,
             pb.first_seen_at, pb.last_seen_at, pb.status),
        )

    async def list_palboxes(self, world_id: str) -> list[PalBox]:
        rows = await self._db.query(
            """
            SELECT palbox_key, world_id, guild_key, position_cell,
                   first_seen_at, last_seen_at, status
            FROM palboxes WHERE world_id = ? ORDER BY palbox_key ASC
            """,
            (world_id,),
        )
        return [PalBox(r["palbox_key"], r["world_id"], r["guild_key"],
                       r["position_cell"], r["first_seen_at"], r["last_seen_at"],
                       r["status"]) for r in rows]

    # ---- bases ----
    async def upsert_base(self, b: Base) -> None:
        await self._db.execute_write(
            """
            INSERT INTO bases
                (base_key, world_id, palbox_key, display_name, guild_key,
                 confidence, locked_by_admin, hidden, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(base_key, world_id) DO UPDATE SET
                palbox_key = excluded.palbox_key,
                display_name = excluded.display_name,
                guild_key = excluded.guild_key,
                confidence = excluded.confidence,
                locked_by_admin = excluded.locked_by_admin,
                hidden = excluded.hidden,
                last_seen_at = excluded.last_seen_at
            """,
            (b.base_key, b.world_id, b.palbox_key, b.display_name, b.guild_key,
             str(b.confidence), int(b.locked_by_admin), int(b.hidden),
             b.first_seen_at, b.last_seen_at),
        )

    async def list_bases(self, world_id: str, include_low: bool = False,
                         include_hidden: bool = False) -> list[Base]:
        sql = ["SELECT base_key, world_id, palbox_key, display_name, guild_key,",
               "confidence, locked_by_admin, hidden, first_seen_at, last_seen_at",
               "FROM bases WHERE world_id = ?"]
        params: list = [world_id]
        if not include_low:
            sql.append("AND confidence != 'low'")
        if not include_hidden:
            sql.append("AND hidden = 0")
        sql.append("ORDER BY guild_key ASC, palbox_key ASC")
        rows = await self._db.query(" ".join(sql), params)
        return [Base(r["base_key"], r["world_id"], r["palbox_key"], r["display_name"],
                     r["guild_key"], Confidence(r["confidence"]),
                     bool(r["locked_by_admin"]), bool(r["hidden"]),
                     r["first_seen_at"], r["last_seen_at"]) for r in rows]

    # ---- base observations ----
    async def insert_base_observation(self, o: BaseObservation) -> None:
        await self._db.execute_write(
            """
            INSERT INTO base_observations
                (world_id, base_key, observed_at, worker_count, active_count,
                 average_level, average_hp_ratio, action_distribution_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (o.world_id, o.base_key, o.observed_at, o.worker_count, o.active_count,
             o.average_level, o.average_hp_ratio, json.dumps(o.action_distribution)),
        )

    async def latest_base_observation(self, world_id: str, base_key: str) -> BaseObservation | None:
        rows = await self._db.query(
            """
            SELECT world_id, base_key, observed_at, worker_count, active_count,
                   average_level, average_hp_ratio, action_distribution_json
            FROM base_observations WHERE world_id = ? AND base_key = ?
            ORDER BY observed_at DESC LIMIT 1
            """,
            (world_id, base_key),
        )
        if not rows:
            return None
        r = rows[0]
        return BaseObservation(
            base_key=r["base_key"], world_id=r["world_id"], observed_at=r["observed_at"],
            worker_count=r["worker_count"], active_count=r["active_count"],
            average_level=r["average_level"], average_hp_ratio=r["average_hp_ratio"],
            action_distribution=json.loads(r["action_distribution_json"]),
        )

    # ---- world events ----
    async def insert_event(self, e: WorldEvent) -> bool:
        try:
            await self._db.execute_write(
                """INSERT INTO world_events
                   (world_id, event_type, subject_type, subject_key,
                    occurred_at, confirmed_at, payload_json, visibility,
                    confidence, dedup_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e.world_id,
                    e.event_type.value,
                    e.subject_type,
                    e.subject_key,
                    e.occurred_at,
                    e.confirmed_at,
                    json.dumps(e.payload, ensure_ascii=False, sort_keys=True),
                    e.visibility,
                    e.confidence.value,
                    e.dedup_key,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    async def list_events(
        self, world_id: str, since: int | None = None, limit: int = 20
    ) -> list[WorldEvent]:
        sql = "SELECT * FROM world_events WHERE world_id = ?"
        params: list = [world_id]
        if since is not None:
            sql += " AND occurred_at >= ?"
            params.append(since)
        sql += " ORDER BY occurred_at DESC, event_id DESC LIMIT ?"
        params.append(limit)
        rows = await self._db.query(sql, params)
        return [
            WorldEvent(
                event_id=r["event_id"],
                world_id=r["world_id"],
                event_type=EventType(r["event_type"]),
                subject_type=r["subject_type"],
                subject_key=r["subject_key"],
                occurred_at=r["occurred_at"],
                confirmed_at=r["confirmed_at"],
                payload=json.loads(r["payload_json"]),
                visibility=r["visibility"],
                confidence=Confidence(r["confidence"]),
                dedup_key=r["dedup_key"],
            )
            for r in rows
        ]

    # ---- daily aggregates ----
    async def upsert_daily_aggregate(
        self, world_id: str, day: str, key: str, value: Any
    ) -> None:
        await self._db.execute_write(
            """INSERT INTO daily_aggregates (world_id, day, key, value_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(world_id, day, key)
               DO UPDATE SET value_json = excluded.value_json""",
            (world_id, day, key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
        )

    async def get_daily_aggregate(
        self, world_id: str, day: str, key: str
    ) -> Any | None:
        rows = await self._db.query(
            "SELECT value_json FROM daily_aggregates WHERE world_id = ? AND day = ? AND key = ?",
            (world_id, day, key),
        )
        if not rows:
            return None
        return json.loads(rows[0]["value_json"])
