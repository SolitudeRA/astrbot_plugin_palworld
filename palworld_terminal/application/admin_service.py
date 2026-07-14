from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..adapters.palworld_rest import _ADMIN_PATH, RestResponse
from ..adapters.privacy_filter import hash_user_id

_NETWORK_ERROR = "network error"

FetchFn = Callable[[str, str], Awaitable[RestResponse]]
PostFn = Callable[[str, str, "dict[str, Any] | None"], Awaitable[RestResponse]]


@dataclass(slots=True)
class AdminResult:
    ok: bool
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)


class AdminService:
    """无目标写命令（announce/save/shutdown/stop）+ 审计落库。

    目标类命令（kick/ban/unban）在 T5 补齐，届时复用 ``_execute`` 的
    ``target_name``/``target_userid`` 通道（target_hash 用 world_id 命名空间）。
    """

    def __init__(self, routing, fetch: FetchFn, post: PostFn, repo, salt: bytes, clock):
        self._routing = routing
        self._fetch = fetch
        self._post = post
        self._repo = repo
        self._salt = salt
        self._clock = clock

    async def _execute(
        self,
        admin_id: str,
        umo: str,
        is_group: bool,
        *,
        action: str,
        path: str,
        json_body: dict[str, Any] | None,
        target_name: str | None = None,
        target_userid: str | None = None,
        detail: str = "",
        initiated_ok_on_disconnect: bool = False,
    ) -> AdminResult:
        # path 必须是已知写端点：消费 _ADMIN_PATH，杜绝拼错端点静默打偏。
        if path not in _ADMIN_PATH:
            raise ValueError(f"unknown admin path: {path!r}")

        resolution = await self._routing.resolve(umo, None, is_group)
        if resolution.server is None:
            return AdminResult(
                ok=False,
                message_key="admin_resolve_failed",
                params={"reason": resolution.error or ""},
            )
        server = resolution.server

        world = await self._repo.get_current_world(server.server_id)
        world_id = world.world_id if world is not None else ""

        resp = await self._post(server.server_id, path, json_body)
        initiated = (
            initiated_ok_on_disconnect
            and not resp.ok
            and resp.error == _NETWORK_ERROR
        )
        ok = resp.ok or initiated

        target_hash = (
            hash_user_id(self._salt, world_id, target_userid) if target_userid else None
        )

        await self._repo.insert_audit(
            ts=self._clock.now(),
            admin_id=admin_id,
            action=action,
            server_name=server.name,
            target_name=target_name,
            target_hash=target_hash,
            detail=detail or None,
            success=1 if ok else 0,
            error=None if ok else resp.error,
        )

        if not ok:
            message_key = "admin_failed"
        elif initiated:
            message_key = "admin_shutdown_initiated"
        else:
            message_key = "admin_ok"

        return AdminResult(
            ok=ok,
            message_key=message_key,
            params={
                "server": server.name,
                "action": action,
                "target": target_name or "",
                "error": resp.error or "",
            },
        )

    async def announce(
        self, admin_id: str, umo: str, is_group: bool, message: str
    ) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="announce",
            path="announce",
            json_body={"message": message},
            detail=message,
        )

    async def save(self, admin_id: str, umo: str, is_group: bool) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="save",
            path="save",
            json_body=None,
        )

    async def shutdown(self, admin_id: str, umo: str, is_group: bool) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="shutdown",
            path="shutdown",
            json_body=None,
            initiated_ok_on_disconnect=True,
        )

    async def stop(self, admin_id: str, umo: str, is_group: bool) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="stop",
            path="stop",
            json_body=None,
            initiated_ok_on_disconnect=True,
        )
