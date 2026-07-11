"""插件页面 HTTP 端点的 async 编排：副作用（save/stop/start/锁）经参数注入，
返回 (status_code, payload)。业务成败一律 HTTP 200，用 payload['ok'] 区分。"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from .config_view import redact_config, status_rows, validate_and_backfill


async def handle_config_get(get_raw: Callable[[], Mapping]) -> tuple[int, dict]:
    return 200, {"ok": True, "config": redact_config(get_raw()), "page_version": 1}


async def handle_status_overview(container, restarting: bool) -> tuple[int, dict]:
    if restarting or container is None:
        return 200, {"ok": True, "servers": [], "restarting": True}
    entries = []
    for s in container.config.servers:
        world = await container.repo.get_current_world(s.server_id)
        dto = await container.query.status(world) if world is not None else None
        entries.append((s.name, s.ready, dto))
    return 200, {"ok": True, "servers": status_rows(entries)}


async def handle_config_save(
    body, *, old_raw, env, lock, now, last_save_ts,
    apply_and_restart, min_interval: float = 5,
) -> tuple[int, dict]:
    if lock.locked():
        return 200, {"ok": False, "error": "save_in_progress", "detail": {}}
    if last_save_ts is not None and now - last_save_ts < min_interval:
        return 200, {"ok": False, "error": "too_frequent", "detail": {}}
    async with lock:
        ok, result = validate_and_backfill(body, old_raw, env)
        if not ok:
            return 200, {"ok": False, **result}
        outcome = await apply_and_restart(result)
        if not outcome.get("ok"):
            return 200, outcome
        return 200, {"ok": True, "warnings": outcome.get("warnings", {}),
                     "saved_ts": now}
