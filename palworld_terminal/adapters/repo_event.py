from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..domain.enums import Confidence, EventType
from ..domain.models import WorldEvent
from ..infrastructure.database import Database


class _EventRepo:
    """world_events / daily_aggregates 表族：世界事件与日聚合。"""

    _db: Database

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
        self, world_id: str, since: int | None = None, limit: int = 20,
        offset: int = 0,
    ) -> list[WorldEvent]:
        sql = "SELECT * FROM world_events WHERE world_id = ?"
        params: list = [world_id]
        if since is not None:
            sql += " AND occurred_at >= ?"
            params.append(since)
        sql += " ORDER BY occurred_at DESC, event_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
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
