"""插件页面 HTTP 端点的 async 编排：副作用（save/stop/start/锁）经参数注入，
返回 (status_code, payload)。业务成败一律 HTTP 200，用 payload['ok'] 区分。"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from .config_view import redact_config, status_rows


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
