from __future__ import annotations

from typing import Any

from ..infrastructure.database import Database


class _AuditRepo:
    """admin_audit 表族：管理操作审计写入、读取、留存裁剪。"""

    _db: Database

    # ---- admin audit ----
    async def insert_audit(
        self, *, ts: int, admin_id: str, action: str, server_name: str,
        target_name: str | None, target_hash: str | None, detail: str | None,
        success: int, error: str | None,
    ) -> None:
        await self._db.execute_write(
            "INSERT INTO admin_audit"
            " (ts, admin_id, action, server_name, target_name,"
            "  target_hash, detail, success, error)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, admin_id, action, server_name, target_name,
             target_hash, detail, success, error),
        )

    async def list_audit(self, limit: int) -> list[dict[str, Any]]:
        rows = await self._db.query(
            "SELECT ts, admin_id, action, server_name, target_name, target_hash,"
            " detail, success, error FROM admin_audit"
            " ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def prune_audit(self, before_ts: int) -> int:
        async with self._db.write_tx() as conn:
            cur = await conn.execute(
                "DELETE FROM admin_audit WHERE ts < ?", (before_ts,)
            )
            return cur.rowcount
