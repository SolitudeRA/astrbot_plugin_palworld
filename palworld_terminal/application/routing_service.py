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


@dataclass(slots=True)
class UseResult:
    """/pal link add 结构化结果（spec §5#8）：locale 渲染上提 commands 层。

    ok=False → 名字不存在/未就绪（commands 渲染 link_add_unknown）；ok=True 时
    replaced_active 为被替换的旧活动服务器 id（set_active 前 get_binding_active 取旧值，
    仅旧≠新时填），commands 据此决定是否出「原活动服务器已替换」脚注。
    """
    ok: bool
    server_id: str | None
    replaced_active: str | None


@dataclass(slots=True)
class UnbindResult:
    """/pal link remove 结构化结果（spec §5#8）：先查存在性，修幂等假成功。

    removed=False → 本群无该服务器授权记录（commands 渲染中性素文，不谎报「已撤销」）；
    was_active → 撤的是本群当前活动服务器（commands 据此出「原为活动服务器」脚注）。
    """
    removed: bool
    was_active: bool


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

    async def use(self, umo: str, name: str) -> UseResult:
        """授权本群使用某服务器并设为当前活动（spec §5#8：结构化返回，渲染上提）。"""
        srv = self._ready_by_name(name)
        if srv is None:
            return UseResult(ok=False, server_id=None, replaced_active=None)
        old_active = await self._repo.get_binding_active(umo)  # set_active 前取旧活动
        await self._repo.set_active(umo, srv.server_id)
        replaced = old_active if (old_active is not None and old_active != srv.server_id) else None
        return UseResult(ok=True, server_id=srv.server_id, replaced_active=replaced)

    async def unbind(self, umo: str, name: str) -> UnbindResult:
        """撤销本群对某服务器的授权（spec §5#8：先查存在性 → 修幂等假成功）。

        target 用 _ready_by_name 命中的 server_id，未命中回退原名（残留记录仍可清理）。
        revoke 前查 list_group_servers：无该记录 → removed=False（不谎报已撤销）。
        """
        srv = self._ready_by_name(name)
        target = srv.server_id if srv is not None else name
        group = await self._repo.list_group_servers(umo)
        if target not in group:
            return UnbindResult(removed=False, was_active=False)
        _allowed, was_active = group[target]
        await self._repo.revoke(umo, target)
        return UnbindResult(removed=True, was_active=was_active)

    def ready_servers(self) -> list[ServerConfig]:
        return self._ready_servers()
