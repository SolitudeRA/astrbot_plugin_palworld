from __future__ import annotations

from ..domain.models import World, WorldMetric
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database


class _WorldMetricRepo:
    """worlds / world_metrics / unknown_classes 表族：世界档案与性能指标。"""

    _db: Database
    _clock: Clock

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

    async def world_day_bounds(
        self, world_id: str, start: int, end: int
    ) -> tuple[int, int] | None:
        """日窗口 [start, end) 内 metrics 首末 world_day（spec §5#4 / §6#1 epoch 修）。

        按 observed_at 升序取首/末样本的 world_day，即当日「第 X → Y 天」；窗口内无
        metric 采样时返回 None（无从推断，调用方回退 world.current_day）。修根治日报
        误把窗口 epoch 秒直出为世界天数（「第 1752624000 天」）的现网 bug。
        """
        rows = await self._db.query(
            "SELECT"
            " (SELECT world_day FROM world_metrics WHERE world_id = ?"
            "  AND observed_at >= ? AND observed_at < ?"
            "  ORDER BY observed_at ASC LIMIT 1) AS first_day,"
            " (SELECT world_day FROM world_metrics WHERE world_id = ?"
            "  AND observed_at >= ? AND observed_at < ?"
            "  ORDER BY observed_at DESC LIMIT 1) AS last_day",
            (world_id, start, end, world_id, start, end),
        )
        if not rows or rows[0]["first_day"] is None:
            return None
        return int(rows[0]["first_day"]), int(rows[0]["last_day"])

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
