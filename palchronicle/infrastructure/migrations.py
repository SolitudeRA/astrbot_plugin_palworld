"""顺序迁移器：PRAGMA user_version 驱动，幂等，失败抛 MigrationError。

migration_0001 建 spec §9.1 全部 v0.1 表 + §9.2 全部索引。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import aiosqlite

from ..infrastructure.database import Database


class MigrationError(Exception):
    pass


_MIGRATION_0001_SQL = [
    """
    CREATE TABLE IF NOT EXISTS servers (
        server_id     TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        host          TEXT,
        enabled       INTEGER NOT NULL DEFAULT 1,
        first_seen_at INTEGER,
        last_seen_at  INTEGER,
        last_ok_at    INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS group_servers (
        umo        TEXT NOT NULL,
        server_id  TEXT NOT NULL,
        allowed    INTEGER NOT NULL DEFAULT 0,
        active     INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER,
        PRIMARY KEY (umo, server_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS worlds (
        world_id      TEXT PRIMARY KEY,
        server_id     TEXT NOT NULL,
        worldguid     TEXT NOT NULL,
        epoch         INTEGER NOT NULL DEFAULT 0,
        server_name   TEXT,
        version       TEXT,
        first_seen_at INTEGER,
        last_seen_at  INTEGER,
        current_day   INTEGER,
        UNIQUE (server_id, worldguid, epoch)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS players (
        player_key       TEXT NOT NULL,
        world_id         TEXT NOT NULL,
        latest_name      TEXT,
        first_seen_at    INTEGER,
        last_seen_at     INTEGER,
        latest_level     INTEGER,
        latest_guild_key TEXT,
        id_confidence    TEXT,
        PRIMARY KEY (player_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_sessions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id          TEXT NOT NULL,
        player_key        TEXT NOT NULL,
        joined_at         INTEGER NOT NULL,
        last_confirmed_at INTEGER NOT NULL,
        left_at           INTEGER,
        observed_seconds  INTEGER NOT NULL DEFAULT 0,
        status            TEXT NOT NULL,
        leave_reason      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_observations (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id       TEXT NOT NULL,
        player_key     TEXT NOT NULL,
        observed_at    INTEGER NOT NULL,
        level          INTEGER,
        ping_bucket    TEXT,
        building_count INTEGER,
        guild_key      TEXT,
        companion_class TEXT,
        position_cell  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guilds (
        guild_key            TEXT NOT NULL,
        world_id             TEXT NOT NULL,
        latest_name          TEXT,
        first_seen_at        INTEGER,
        last_seen_at         INTEGER,
        observed_member_count INTEGER DEFAULT 0,
        palbox_count         INTEGER DEFAULT 0,
        base_pal_count       INTEGER DEFAULT 0,
        PRIMARY KEY (guild_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS palboxes (
        palbox_key    TEXT NOT NULL,
        world_id      TEXT NOT NULL,
        guild_key     TEXT,
        position_cell TEXT NOT NULL,
        first_seen_at INTEGER,
        last_seen_at  INTEGER,
        status        TEXT NOT NULL DEFAULT 'active',
        PRIMARY KEY (palbox_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bases (
        base_key       TEXT NOT NULL,
        world_id       TEXT NOT NULL,
        palbox_key     TEXT NOT NULL,
        display_name   TEXT,
        guild_key      TEXT,
        confidence     TEXT NOT NULL,
        locked_by_admin INTEGER NOT NULL DEFAULT 0,
        hidden         INTEGER NOT NULL DEFAULT 0,
        first_seen_at  INTEGER,
        last_seen_at   INTEGER,
        PRIMARY KEY (base_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS base_observations (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id                 TEXT NOT NULL,
        base_key                 TEXT NOT NULL,
        observed_at              INTEGER NOT NULL,
        worker_count             INTEGER,
        active_count             INTEGER,
        average_level            REAL,
        average_hp_ratio         REAL,
        action_distribution_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_metrics (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id       TEXT NOT NULL,
        observed_at    INTEGER NOT NULL,
        fps            REAL,
        frame_time     REAL,
        online_players INTEGER,
        world_day      INTEGER,
        basecamp_count INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_events (
        event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id     TEXT NOT NULL,
        event_type   TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_key  TEXT,
        occurred_at  INTEGER NOT NULL,
        confirmed_at INTEGER NOT NULL,
        payload_json TEXT,
        visibility   TEXT NOT NULL,
        confidence   TEXT NOT NULL,
        dedup_key    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_aggregates (
        world_id   TEXT NOT NULL,
        day        TEXT NOT NULL,
        key        TEXT NOT NULL,
        value_json TEXT,
        PRIMARY KEY (world_id, day, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unknown_classes (
        class_name    TEXT PRIMARY KEY,
        first_seen_at INTEGER,
        count         INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON world_events(dedup_key)",
    "CREATE INDEX IF NOT EXISTS idx_events_world_time ON world_events(world_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_player_time ON player_sessions(world_id, player_key, joined_at)",
    "CREATE INDEX IF NOT EXISTS idx_obs_player_time ON player_observations(world_id, player_key, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_world_time ON world_metrics(world_id, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_baseobs_base_time ON base_observations(world_id, base_key, observed_at)",
]


async def migration_0001(conn: aiosqlite.Connection) -> None:
    for stmt in _MIGRATION_0001_SQL:
        await conn.execute(stmt)


_MIGRATION_0002_SQL = [
    "ALTER TABLE world_metrics ADD COLUMN max_players INTEGER NOT NULL DEFAULT 0",
]


async def migration_0002(conn: aiosqlite.Connection) -> None:
    for stmt in _MIGRATION_0002_SQL:
        await conn.execute(stmt)


MIGRATIONS: list[Callable[[aiosqlite.Connection], Awaitable[None]]] = [
    migration_0001,
    migration_0002,
]


async def apply_migrations(db: Database) -> None:
    rows = await db.query("PRAGMA user_version")
    current = int(rows[0][0]) if rows else 0
    target = len(MIGRATIONS)
    if current >= target:
        return
    for version in range(current, target):
        migration = MIGRATIONS[version]
        try:
            async with db.write_tx() as conn:
                await migration(conn)
                # user_version 不接受占位参数，须内联整数。
                await conn.execute(f"PRAGMA user_version = {version + 1}")
        except MigrationError:
            raise
        except Exception as exc:  # noqa: BLE001 — 迁移失败统一包装
            raise MigrationError(
                f"migration #{version + 1} failed: {type(exc).__name__}"
            ) from exc
