from __future__ import annotations

import logging
from dataclasses import dataclass

from ..adapters.sqlite_repository import Repository
from ..config import AppConfig, ServerConfig
from ..domain.enums import AccessMode
from ..presentation.locale import L

_log = logging.getLogger("palworld_terminal.routing")


@dataclass(slots=True)
class Resolution:
    server: ServerConfig | None
    error: str | None


class RoutingService:
    def __init__(self, repo: Repository, cfg: AppConfig) -> None:
        self._repo = repo
        self._cfg = cfg
        self._single_multi_warned = False

    def _ready_servers(self) -> list[ServerConfig]:
        return [s for s in self._cfg.servers if s.ready]

    def _ready_by_name(self, name: str) -> ServerConfig | None:
        for s in self._ready_servers():
            if s.server_id == name:
                return s
        return None

    async def _authorized(self, umo: str, server_id: str, is_group: bool) -> bool:
        if self._cfg.routing.access_mode is AccessMode.OPEN:
            return True
        if not is_group:
            return False
        return server_id in await self._repo.get_allowed(umo)

    async def resolve(
        self, umo: str, override: str | None, is_group: bool, *, for_write: bool = False
    ) -> Resolution:
        # 单世界模式：恒解析到唯一就绪服务器。restricted 读授权查 single_allowed_groups；
        # 写命令(for_write)绕过读名单（admin 硬门独立把守）。忽略 @override 与群绑定。
        if self._cfg.routing.world_mode == "single":
            ready = self._ready_servers()
            if not ready:
                return Resolution(None, L("no_server_configured"))
            if self._cfg.routing.access_mode is AccessMode.RESTRICTED and not for_write:
                allowed = {e.umo for e in self._cfg.routing.single_allowed_groups}
                if umo not in allowed:
                    return Resolution(None, L("single_not_authorized"))
            if len(ready) > 1 and not self._single_multi_warned:
                self._single_multi_warned = True
                _log.warning(
                    "world_mode=single 但检测到 %d 台就绪服务器，仅使用首台「%s」；"
                    "其余将被忽略。若需多服务器请改用 world_mode=multi。",
                    len(ready), ready[0].server_id,
                )
            return Resolution(ready[0], None)

        if not self._ready_servers():
            return Resolution(None, L("no_server_configured"))

        # private chat under restricted: no allowed records possible
        if self._cfg.routing.access_mode is AccessMode.RESTRICTED and not is_group:
            return Resolution(None, L("private_restricted"))

        # Step 1: explicit @server override
        if override:
            srv = self._ready_by_name(override)
            if srv is None:
                return Resolution(None, L("server_unknown", server=override))
            if not await self._authorized(umo, srv.server_id, is_group):
                return Resolution(None, L("not_authorized", server=srv.server_id))
            return Resolution(srv, None)

        # Step 2: group active binding
        if is_group:
            active = await self._repo.get_binding_active(umo)
            if active:
                srv = self._ready_by_name(active)
                if srv is None:
                    return Resolution(None, L("active_server_stale"))
                if await self._authorized(umo, srv.server_id, is_group):
                    return Resolution(srv, None)

        # Step 3: global default server
        default = self._cfg.routing.default_server
        if default:
            srv = self._ready_by_name(default)
            if srv is not None and await self._authorized(umo, srv.server_id, is_group):
                return Resolution(srv, None)

        # Step 4: single ready server
        ready = self._ready_servers()
        if len(ready) == 1 and await self._authorized(umo, ready[0].server_id, is_group):
            return Resolution(ready[0], None)

        # Step 5: friendly prompt
        return Resolution(None, L("no_server_resolved"))

    async def use(self, umo: str, name: str) -> str:
        srv = self._ready_by_name(name)
        if srv is None:
            return L("server_unknown", server=name)
        await self._repo.set_active(umo, srv.server_id)
        return L("use_ok", server=srv.server_id)

    async def unbind(self, umo: str, name: str) -> str:
        srv = self._ready_by_name(name)
        target = srv.server_id if srv is not None else name
        await self._repo.revoke(umo, target)
        return L("unbind_ok", server=target)

    def ready_servers(self) -> list[ServerConfig]:
        return self._ready_servers()
