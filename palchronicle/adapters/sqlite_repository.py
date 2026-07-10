"""所有表读写（跨阶段增长的同一个 Repository 类）。

Phase 1：server / binding / world / prune 方法。
"""
from __future__ import annotations

from palchronicle.config import BindingConfig, HistoryConfig, ServerConfig
from palchronicle.domain.enums import IdConfidence
from palchronicle.domain.models import PlayerIdentity, World, WorldMetric
from palchronicle.infrastructure.clock import Clock
from palchronicle.infrastructure.database import Database

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
            "  world_day, basecamp_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                m.world_id, m.observed_at, m.fps, m.frame_time,
                m.online_players, m.world_day, m.basecamp_count,
            ),
        )

    async def latest_metric(self, world_id: str) -> WorldMetric | None:
        rows = await self._db.query(
            "SELECT world_id, observed_at, fps, frame_time, online_players,"
            " world_day, basecamp_count FROM world_metrics"
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
