from __future__ import annotations

from dataclasses import dataclass

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.enums import AccessMode
from palchronicle.presentation.locale import L


@dataclass(slots=True)
class Resolution:
    server: ServerConfig | None
    error: str | None


class RoutingService:
    def __init__(self, repo: Repository, cfg: AppConfig) -> None:
        self._repo = repo
        self._cfg = cfg

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

    async def resolve(self, umo: str, override: str | None, is_group: bool) -> Resolution:
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
