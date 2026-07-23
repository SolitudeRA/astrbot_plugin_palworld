from __future__ import annotations

import json

from ..domain.enums import Confidence
from ..domain.models import Base, BaseObservation, Guild, PalBox
from ..infrastructure.database import Database


class _GuildBaseRepo:
    """guilds / palboxes / bases / base_observations 表族：公会、帕鲁箱、据点及其观测。"""

    _db: Database

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
