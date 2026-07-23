from __future__ import annotations

from ..config import BindingConfig, ServerConfig
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database


class _ServerRoutingRepo:
    """servers / group_servers 表族：服务器同步、群绑定/路由授权、active 与 revoke。"""

    _db: Database
    _clock: Clock

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

    async def list_allowed_bindings(self) -> list[tuple[str, str]]:
        """全表 allowed=1 的 (umo, server_id) 对（不聚合）。供预览端点按 umo 聚合，
        以及 multi→single 迁移的真实源集（distinct umo）与 migrate_umos ⊆ 源 校验。"""
        rows = await self._db.query(
            "SELECT umo, server_id FROM group_servers WHERE allowed=1"
        )
        return [(r[0], r[1]) for r in rows]

    async def list_orphan_server_ids(self, valid_server_ids: set[str]) -> list[str]:
        """DB 中出现（servers∪worlds∪group_servers）但不在 valid_server_ids 的
        server_id——供孤儿清理端点列待清台。UNION 去重、sorted 稳定序。"""
        rows = await self._db.query(
            "SELECT server_id FROM servers "
            "UNION SELECT server_id FROM worlds "
            "UNION SELECT server_id FROM group_servers"
        )
        seen = {r[0] for r in rows}
        return sorted(sid for sid in seen if sid not in valid_server_ids)

    async def bind_umos_to_server(self, umos: list[str], server_id: str) -> None:
        """批量把 umos 绑到 server_id：allowed=1 恒置；active pin——该 umo 尚无任何
        active 行时把本行 active 升到 1，否则保持既有（不夺别台 active）。镜像
        seed_bindings seed-only-active + set_active one-active-per-umo 不变量。"""
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            for umo in umos:
                cursor = await conn.execute(
                    "SELECT 1 FROM group_servers WHERE umo=? AND active=1 LIMIT 1",
                    (umo,),
                )
                has_active = await cursor.fetchone()
                await cursor.close()
                want_active = 0 if has_active else 1
                await conn.execute(
                    "INSERT INTO group_servers "
                    "(umo, server_id, allowed, active, updated_at) "
                    "VALUES (?, ?, 1, ?, ?) "
                    "ON CONFLICT(umo, server_id) DO UPDATE SET "
                    "  allowed=1, "
                    "  active=CASE WHEN ?=1 THEN 1 ELSE group_servers.active END, "
                    "  updated_at=excluded.updated_at",
                    (umo, server_id, want_active, now, want_active),
                )

    async def clear_all_group_servers(self) -> int:
        """清空全部 DB group_servers（multi→single move 清源）。返回删除行数。"""
        async with self._db.write_tx() as conn:
            cursor = await conn.execute("DELETE FROM group_servers")
            return cursor.rowcount

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
