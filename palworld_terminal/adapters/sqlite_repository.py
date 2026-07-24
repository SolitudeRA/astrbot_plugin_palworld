"""Repository 组合主体：按实体表族拆入 7 个 mixin（repo_*.py）继承组合；
跨表原子事务（purge_server_data/prune）留本体，直接持 self._db.write_tx。"""
from __future__ import annotations

from ..config import HistoryConfig
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database
from .repo_audit import _AuditRepo
from .repo_dex import _DexRepo
from .repo_event import _EventRepo
from .repo_guild_base import _GuildBaseRepo
from .repo_player_binding import _PlayerBindingRepo
from .repo_player_profile import _PlayerProfileRepo
from .repo_routing import _ServerRoutingRepo
from .repo_world import _WorldMetricRepo

_SECONDS_PER_DAY = 86400


class Repository(
    _ServerRoutingRepo,
    _PlayerBindingRepo,
    _WorldMetricRepo,
    _PlayerProfileRepo,
    _GuildBaseRepo,
    _EventRepo,
    _AuditRepo,
    _DexRepo,
):
    """所有表读写。实现按实体表族拆入 8 个 mixin（repo_*.py）继承组合；
    跨表原子事务（purge/prune）留主体，直接持 self._db.write_tx 保单事务原子性。"""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    _PURGE_WORLD_TABLES = (
        "players", "player_sessions", "player_observations", "guilds",
        "palboxes", "bases", "base_observations", "world_metrics",
        "world_events", "daily_aggregates", "player_bindings", "hidden_players",
    )

    async def purge_server_data(self, server_id: str) -> dict[str, int]:
        """server 级 purge：解析该 server 的 world_id 集 → 逐表删 12 张 world_id 键表 +
        删 group_servers/worlds/servers 的 server_id 行。单台一个 write_tx（任一 DELETE
        抛错整台回滚）。空 world_id 集短路（跳过 12 表、绝不发空 IN ()）。返回各表计数。"""
        counts: dict[str, int] = {}
        async with self._db.write_tx() as conn:
            cur = await conn.execute(
                "SELECT world_id FROM worlds WHERE server_id=?", (server_id,)
            )
            world_rows = await cur.fetchall()
            await cur.close()
            world_ids = [r[0] for r in world_rows]
            if world_ids:
                placeholders = ",".join("?" for _ in world_ids)
                for table in self._PURGE_WORLD_TABLES:
                    cursor = await conn.execute(
                        f"DELETE FROM {table} WHERE world_id IN ({placeholders})",
                        tuple(world_ids),
                    )
                    counts[table] = cursor.rowcount
                    await cursor.close()
            else:
                for table in self._PURGE_WORLD_TABLES:
                    counts[table] = 0
            for table in ("group_servers", "worlds", "servers"):
                cursor = await conn.execute(
                    f"DELETE FROM {table} WHERE server_id=?", (server_id,)
                )
                counts[table] = cursor.rowcount
                await cursor.close()
        return counts

    # ---- retention ----
    async def prune(
        self, history: HistoryConfig, now: int, audit_retention_days: int
    ) -> None:
        metric_cutoff = now - history.raw_metrics_days * _SECONDS_PER_DAY
        obs_cutoff = now - history.observation_days * _SECONDS_PER_DAY
        session_cutoff = now - history.session_days * _SECONDS_PER_DAY
        audit_cutoff = now - audit_retention_days * _SECONDS_PER_DAY
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
            # world 级孤儿清理（players spec §6）：世界被移除后其绑定/自助
            # 隐藏记录不再可达，随 prune 一并清掉
            await conn.execute(
                "DELETE FROM player_bindings WHERE world_id NOT IN"
                " (SELECT world_id FROM worlds)"
            )
            await conn.execute(
                "DELETE FROM hidden_players WHERE world_id NOT IN"
                " (SELECT world_id FROM worlds)"
            )
            # 管理审计留存（与历史留存同一入口，spec 服务器管控）。
            await conn.execute(
                "DELETE FROM admin_audit WHERE ts < ?", (audit_cutoff,)
            )
            # world_events / daily_aggregates 长期保留（spec §9.3）。
