from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable

from ..adapters.privacy_filter import hash_user_id
from ..application.query_service import PlayerProfileDTO
from ..presentation.command_registry import COMMAND_GROUP
from ..presentation.dtos import ServerStatusRow
from ..presentation.formatters import (
    format_base,
    format_bases,
    format_degraded,
    format_events,
    format_guild,
    format_guilds,
    format_help,
    format_online,
    format_player,
    format_rank,
    format_rules,
    format_servers,
    format_status,
    format_today,
    format_world,
)
from ..presentation.locale import L
from ..presentation.server_arg import ArgError, parse_arg


def _gated(fn):
    """命令组 gating：按方法名查 COMMAND_GROUP 得组，未启用则回 feature_disabled，
    不触达底层（spec §5）。gating 与 help 物理共享同一张表，消除漂移面。
    """
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        group = COMMAND_GROUP[fn.__name__]
        if not self._cfg.features.enabled(group):
            return L("feature_disabled")
        return await fn(self, *args, **kwargs)
    return wrapper


class Commands:
    def __init__(self, routing, query, repo, cfg, clock, salt: bytes = b"") -> None:
        self._routing = routing
        self._query = query
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt

    async def _resolve_world(self, umo: str, message_str: str, subcommand: str, is_group: bool):
        try:
            arg = parse_arg(message_str, subcommand)
        except ArgError:
            return None, None, "参数格式错误：一条命令只能指定一个 @服务器。"
        res = await self._routing.resolve(umo, arg.server_override, is_group)
        if res.server is None:
            return None, arg, res.error
        world = await self._repo.get_current_world(res.server.server_id)
        if world is None:
            return None, arg, format_degraded(None, self._clock.now() if self._clock else 0)
        return world, arg, None

    async def handle_query(
        self, umo: str, message_str: str, subcommand: str, is_group: bool,
        formatter: Callable, query_fn: Callable[..., Awaitable],
    ) -> str:
        world, _arg, err = await self._resolve_world(umo, message_str, subcommand, is_group)
        if err is not None:
            return err
        dto = await query_fn(world)
        return formatter(dto)

    async def status(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "status", is_group,
            formatter=format_status, query_fn=self._query.status,
        )

    async def online(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "online", is_group,
            formatter=format_online, query_fn=self._query.online,
        )

    async def world(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "world", is_group,
            formatter=format_world, query_fn=self._query.world_summary,
        )

    async def rules(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "rules", is_group,
            formatter=format_rules, query_fn=self._query.rules,
        )

    @_gated
    async def guilds(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "guilds", is_group,
            formatter=format_guilds, query_fn=self._query.guilds,
        )

    @_gated
    async def guild(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "guild", is_group)
        if err is not None:
            return err
        dto = await self._query.guild(world, arg.name)
        if dto is None:
            return L("guild_not_found", name=arg.name)
        return format_guild(dto)

    @_gated
    async def bases(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "bases", is_group,
            formatter=format_bases, query_fn=self._query.bases,
        )

    @_gated
    async def base(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "base", is_group)
        if err is not None:
            return err
        dto = await self._query.base(world, arg.name)
        if dto is None:
            return L("base_not_found", name=arg.name)
        return format_base(dto)

    @_gated
    async def events(self, umo, message_str, is_group) -> str:
        today_only = "today" in message_str.split()
        world, _arg, err = await self._resolve_world(umo, message_str, "events", is_group)
        if err is not None:
            return err
        dto = await self._query.events(world, today_only=today_only)
        return format_events(dto)

    @_gated
    async def today(self, umo, message_str, is_group) -> str:
        world, _arg, err = await self._resolve_world(umo, message_str, "today", is_group)
        if err is not None:
            return err
        return format_today(await self._query.today(world))

    @_gated
    async def rank(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "rank", is_group)
        if err is not None:
            return err
        strict = self._cfg.privacy.mode == "strict"
        which = arg.name.strip().lower()
        if which not in ("time", "level"):
            which = "both"
        if which == "time" and strict:
            return L("rank_time_strict")
        dto = await self._query.rank(world)
        return format_rank(dto, which=which, strict=strict)

    @_gated
    async def player(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "player", is_group)
        if err is not None:
            return err
        if not arg.name:
            return L("player_usage")
        dto = await self._query.player_profile(world, arg.name)
        if dto is None:
            return L("player_not_found", name=arg.name)
        return format_player(dto, strict=self._cfg.privacy.mode == "strict")

    @_gated
    async def bind(self, umo, message_str, is_group, sender_id) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "bind", is_group)
        if err is not None:
            return err
        if not arg.name:
            return L("bind_usage")
        ident = await self._repo.get_player_by_name(world.world_id, arg.name)
        if ident is None:
            return L("bind_not_found", name=arg.name)
        excluded = await self._query.load_excluded_keys(world)
        if await self._query.name_banned(world, ident.latest_name, excluded):
            return L("bind_not_found", name=arg.name)   # 存在性收敛(名字级,与榜单/查询一致)
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        await self._repo.upsert_binding(phash, world.world_id, ident.player_key)
        return L("bind_ok", name=ident.latest_name)

    @_gated
    async def me(self, umo, message_str, is_group, sender_id) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "me", is_group)
        if err is not None:
            return err
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        player_key = await self._repo.get_binding(phash, world.world_id)
        if player_key is None:
            return L("me_unbound")
        sub = arg.name.strip().lower()
        if sub == "hide":
            await self._repo.set_hidden(world.world_id, player_key, phash)
            return L("me_hidden")
        if sub == "show":
            await self._repo.unset_hidden(world.world_id, player_key)
            return L("me_shown")
        ident = await self._repo.get_player(world.world_id, player_key)
        if ident is None:
            return L("me_unbound")
        session = await self._repo.get_open_session(world.world_id, player_key)
        dto = PlayerProfileDTO(
            name=ident.latest_name, level=ident.latest_level,
            online=session is not None,
            online_seconds=session.observed_seconds if session is not None else 0,
        )
        return format_player(dto, strict=self._cfg.privacy.mode == "strict")

    async def server(self, umo, message_str, is_group, is_admin) -> str:
        try:
            arg = parse_arg(message_str, "server")
        except ArgError:
            return "参数格式错误：一条命令只能指定一个 @服务器。"
        tokens = arg.name.split()
        sub = tokens[0].lower() if tokens else ""
        name = arg.server_override or (" ".join(tokens[1:]) if len(tokens) > 1 else "")

        if sub in ("add", "remove"):
            if not is_admin:
                return L("admin_required")
            if not is_group:
                return L("use_only_group")
            if not name:
                return L("server_usage")
            if sub == "add":
                return await self._routing.use(umo, name)       # 底层不变
            return await self._routing.unbind(umo, name)         # 底层不变

        if sub:  # 非空非 add/remove:打错的子命令 → 用法提示,不静默回落列表
            return L("server_usage")

        # 裸命令（空首词）= 服务器列表（原 servers() 逻辑，私聊也可）
        ready_ids = {s.server_id for s in self._routing.ready_servers()}
        group = await self._repo.list_group_servers(umo) if is_group else {}
        rows = []
        for s in (self._cfg.servers if self._cfg else self._routing.ready_servers()):
            allowed, active = group.get(s.server_id, (False, False))
            rows.append(ServerStatusRow(
                name=s.name, ready=s.ready, online=s.server_id in ready_ids,
                allowed=allowed, active=active,
            ))
        skipped = self._cfg.skipped if self._cfg else []
        return format_servers(rows, skipped, is_admin)

    def help(self, message_str, is_admin) -> str:
        arg = parse_arg(message_str, "help")
        return format_help(arg.name or None, is_admin, self._cfg.features)
