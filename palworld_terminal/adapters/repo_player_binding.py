from __future__ import annotations

from ..infrastructure.clock import Clock
from ..infrastructure.database import Database


class _PlayerBindingRepo:
    """player_bindings / hidden_players 表族：平台账号↔玩家绑定、玩家自助隐藏。"""

    _db: Database
    _clock: Clock

    # ---- player bindings / hidden ----
    async def upsert_binding(self, platform_hash: str, world_id: str, player_key: str) -> None:
        now = self._clock.now()
        await self._db.execute_write(
            "INSERT INTO player_bindings (platform_hash, world_id, player_key, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(platform_hash, world_id) DO UPDATE SET "
            "player_key=excluded.player_key, created_at=excluded.created_at",
            (platform_hash, world_id, player_key, now),
        )

    async def get_binding(self, platform_hash: str, world_id: str) -> str | None:
        rows = await self._db.query(
            "SELECT player_key FROM player_bindings WHERE platform_hash=? AND world_id=?",
            (platform_hash, world_id),
        )
        return rows[0][0] if rows else None

    async def set_hidden(self, world_id: str, player_key: str, hidden_by: str) -> None:
        now = self._clock.now()
        await self._db.execute_write(
            "INSERT INTO hidden_players (world_id, player_key, hidden_by, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(world_id, player_key) DO UPDATE SET "
            "hidden_by=excluded.hidden_by, created_at=excluded.created_at",
            (world_id, player_key, hidden_by, now),
        )

    async def unset_hidden(self, world_id: str, player_key: str) -> None:
        await self._db.execute_write(
            "DELETE FROM hidden_players WHERE world_id=? AND player_key=?",
            (world_id, player_key),
        )

    async def delete_binding(self, platform_hash: str, world_id: str) -> None:
        await self._db.execute_write(
            "DELETE FROM player_bindings WHERE platform_hash=? AND world_id=?",
            (platform_hash, world_id),
        )

    async def get_hidden_keys(self, world_id: str) -> set[str]:
        rows = await self._db.query(
            "SELECT player_key FROM hidden_players WHERE world_id=?", (world_id,)
        )
        return {r[0] for r in rows}
