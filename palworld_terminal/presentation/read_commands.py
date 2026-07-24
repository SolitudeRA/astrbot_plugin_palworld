from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..application.report_service import server_timezone
from ..domain.enums import EndpointName
from ..domain.privacy import hash_user_id
from ..presentation.formatters import (
    format_base,
    format_bases,
    format_degraded,
    format_events,
    format_guild,
    format_guilds,
    format_online,
    format_player,
    format_rank,
    format_rules,
    format_status,
    format_today,
    format_world,
)
from ..presentation.locale import L
from ..presentation.server_arg import ArgError, parse_arg
from ..shared.command_permissions import active_endpoints
from .command_support import _fold_limit, _gated, _render_routing_error, _world_mode


class ReadCommands:
    def __init__(
        self, routing, query, repo, cfg, clock, salt: bytes = b"",
    ) -> None:
        self._routing = routing
        self._query = query
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt

    async def _resolve_world(self, umo: str, message_str: str, subcommand: str, is_group: bool):
        """解析 (world, arg, err, server_name)。

        server_name = 解析出的配置名 srv.name（spec §2.1 锚点供数机制）：查询类 formatter
        以此作标题锚点主体名，**不扩 DTO、不取游戏内 world.server_name**。后续查询任务
        （T6/T8/T9/T10…）沿用本 4 元返回把 server_name 透传各自 formatter。err 分支下
        server_name 无意义，回 ""（调用方遇 err 直接返回，不消费该位）。
        """
        try:
            arg = parse_arg(message_str, subcommand)
        except ArgError:
            return None, None, L("arg_error"), ""
        res = await self._routing.resolve(umo, arg.server_override, is_group)
        if res.server is None:
            return None, arg, _render_routing_error(res.error, res.error_params), ""
        world = await self._repo.get_current_world(res.server.server_id)
        if world is None:
            # server ready 但无世界快照（恒「从未成功」句）：降级标题带配置名 res.server.name
            now = self._clock.now() if self._clock else 0
            return None, arg, format_degraded(None, now, res.server.name), res.server.name
        return world, arg, None, res.server.name

    async def handle_query(
        self, umo: str, message_str: str, subcommand: str, is_group: bool,
        formatter: Callable, query_fn: Callable[..., Awaitable],
    ) -> str:
        world, _arg, err, _server_name = await self._resolve_world(
            umo, message_str, subcommand, is_group
        )
        if err is not None:
            return err
        dto = await query_fn(world)
        return formatter(dto)

    def _guilds_bases_on(self) -> bool:
        """guilds_bases 家族是否生效开启（GAME_DATA 端点派生自任一 guilds_bases 命令生效值）。
        status 的 `据点` 独立行随此谓词开合（spec §4.1）；测试替身缺 cfg 时保守回 False。"""
        cfg = self._cfg
        if cfg is None:
            return False
        return EndpointName.GAME_DATA in active_endpoints(cfg.permissions.command_overrides)

    def _is_strict(self) -> bool:
        cfg = self._cfg
        if cfg is None:
            return False
        return getattr(getattr(cfg, "privacy", None), "mode", "") == "strict"

    async def status(self, umo, message_str, is_group) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "status", is_group
        )
        if err is not None:
            return err
        dto = await self._query.status(world)
        return format_status(
            dto, server_name, show_bases=self._guilds_bases_on(),
            fold_limit=_fold_limit(self._cfg),
        )

    async def online(self, umo, message_str, is_group) -> str:
        # online 是查询类但需标题锚点 server_name + strict 砍时长（spec §4.24），故不走
        # handle_query（其 formatter 仅收 dto）：显式 resolve 后透传 server_name/strict。
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "online", is_group
        )
        if err is not None:
            return err
        dto = await self._query.online(world)
        return format_online(
            dto, server_name, strict=self._is_strict(), fold_limit=_fold_limit(self._cfg),
        )

    async def world(self, umo, message_str, is_group) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "world", is_group
        )
        if err is not None:
            return err
        dto = await self._query.world_summary(world)
        return format_world(
            dto, server_name, strict=self._is_strict(), fold_limit=_fold_limit(self._cfg),
        )

    async def rules(self, umo, message_str, is_group) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "rules", is_group
        )
        if err is not None:
            return err
        dto = await self._query.rules(world)
        return format_rules(dto, server_name)

    @_gated
    async def guilds(self, umo, message_str, is_group) -> str:
        # guild list（spec §4.6）：标题锚点 server_name + strict 字段级裁剪（砍据点计数位，
        # 命令仍产出）——故不走 handle_query（其 formatter 仅收 dto），显式 resolve 后透传。
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "guilds", is_group
        )
        if err is not None:
            return err
        dto = await self._query.guilds(world)
        return format_guilds(
            dto, server_name, strict=self._is_strict(), fold_limit=_fold_limit(self._cfg),
        )

    @_gated
    async def guild(self, umo, message_str, is_group) -> str:
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "guild", is_group)
        if err is not None:
            return err
        if not arg.name:
            return L("guild_usage")             # 无参补 usage（修 §6#11「未找到公会「」」）
        dto = await self._query.guild(world, arg.name)
        if dto is None:
            return L("guild_not_found", name=arg.name)
        # guild info（spec §4.7）：标题锚点=公会名（formatter 内取 dto.name）；strict 字段级裁剪
        # （砍据点节/近期动态节/据点计数）；「最近」相对日期需 now/tz（与 events 同源）。
        return format_guild(
            dto, strict=self._is_strict(),
            now=self._clock.now(), tz=server_timezone(self._cfg, world),
            fold_limit=_fold_limit(self._cfg),
        )

    @_gated
    async def bases(self, umo, message_str, is_group) -> str:
        # strict 整命令拒执行（spec §4.8/§6#4；同 rank 双砍先例——commands 层判）：strict 切换后
        # DB 残留据点不经本命令绕出（接线死键 bases_disabled_strict）。
        if self._is_strict():
            return L("bases_disabled_strict")
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "bases", is_group
        )
        if err is not None:
            return err
        dto = await self._query.bases(world)
        return format_bases(dto, server_name, fold_limit=_fold_limit(self._cfg))

    @_gated
    async def base(self, umo, message_str, is_group) -> str:
        # strict 整命令拒执行（spec §4.9/§6#4，与 bases 同判）：据点详情不可绕出 strict。
        if self._is_strict():
            return L("bases_disabled_strict")
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "base", is_group)
        if err is not None:
            return err
        if not arg.name:
            return L("base_usage")              # 无参补 usage（§6#11）
        dto = await self._query.base(world, arg.name)
        if dto is None:
            return L("base_not_found", name=arg.name)
        return format_base(dto)

    @_gated
    async def events(self, umo, message_str, is_group) -> str:
        today_only = "today" in message_str.split()
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "events", is_group
        )
        if err is not None:
            return err
        dtos = await self._query.events(world, today_only=today_only)
        return format_events(
            dtos, server_name,
            now=self._clock.now(),
            tz=server_timezone(self._cfg, world),
            today_only=today_only,
            fold_limit=_fold_limit(self._cfg),
        )

    @_gated
    async def today(self, umo, message_str, is_group) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "today", is_group
        )
        if err is not None:
            return err
        return format_today(
            await self._query.today(world), server_name, fold_limit=_fold_limit(self._cfg),
        )

    @_gated
    async def rank(self, umo, message_str, is_group) -> str:
        world, arg, err, server_name = await self._resolve_world(
            umo, message_str, "rank", is_group
        )
        if err is not None:
            return err
        strict = self._cfg.privacy.mode == "strict"
        which = arg.name.strip().lower()
        if which not in ("today", "total", "level"):
            which = "today"  # 缺省 today（spec §4.23：未识别首词回落 today）
        # strict 双砍：today 与 total 同为时长榜(≈作息)均回 notice；level 不受影响。
        if which in ("today", "total") and strict:
            return L("rank_duration_strict")
        dto = await self._query.rank(world, which)
        return format_rank(dto, which=which, server_name=server_name)

    @_gated
    async def player(self, umo, message_str, is_group) -> str:
        world, arg, err, server_name = await self._resolve_world(
            umo, message_str, "player", is_group
        )
        if err is not None:
            return err
        if not arg.name:
            return L("player_usage")
        dto = await self._query.player_profile(world, arg.name)
        if dto is None:
            return L("player_not_found", name=arg.name)
        return format_player(
            dto, strict=self._cfg.privacy.mode == "strict",
            server_name=server_name, world_mode=_world_mode(self._cfg),
            tz=server_timezone(self._cfg, world), now=self._clock.now(),
        )

    def _server_anchor(self, server_name: str) -> str:
        """账号状态族尾锚（spec §3）：多模式 ` · {srv}`，单模式空串（world_mode 判定
        与 help 尾注同源）。bind/unbind 成功回执的尾部服务器锚共用。"""
        return f" · {server_name}" if _world_mode(self._cfg) != "single" else ""

    @_gated
    async def bind(self, umo, message_str, is_group, sender_id) -> str:
        world, arg, err, server_name = await self._resolve_world(
            umo, message_str, "bind", is_group
        )
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
        # 改绑透明化（spec §4.11）：upsert 前查旧绑定；仅换到不同玩家且旧绑定可解析出不同名
        # 才出「原绑定」子句——同名重绑/首次绑定/悬空旧绑定一律走朴素 ✅（不啰嗦、不漏哈希）。
        old_key = await self._repo.get_binding(phash, world.world_id)
        await self._repo.upsert_binding(phash, world.world_id, ident.player_key)
        anchor = self._server_anchor(server_name)
        if old_key is not None and old_key != ident.player_key:
            old_ident = await self._repo.get_player(world.world_id, old_key)
            if old_ident is not None and old_ident.latest_name != ident.latest_name:
                return L("bind_rebind", name=ident.latest_name,
                         old=old_ident.latest_name, anchor=anchor)
        return L("bind_ok", name=ident.latest_name, anchor=anchor)

    @_gated
    async def me(self, umo, message_str, is_group, sender_id) -> str:
        world, arg, err, server_name = await self._resolve_world(
            umo, message_str, "me", is_group
        )
        if err is not None:
            return err
        scoped = _world_mode(self._cfg) != "single"   # 多模式句内带服 / 尾锚（§3 账号状态族）
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        player_key = await self._repo.get_binding(phash, world.world_id)
        if player_key is None:
            return L("me_unbound_scoped", server=server_name) if scoped else L("me_unbound")
        sub = arg.name.strip().lower()
        if sub == "hide":
            await self._repo.set_hidden(world.world_id, player_key, phash)
            return L("me_hidden_scoped", server=server_name) if scoped else L("me_hidden")
        if sub == "show":
            await self._repo.unset_hidden(world.world_id, player_key)
            return L("me_shown_scoped", server=server_name) if scoped else L("me_shown")
        dto = await self._query.profile_for_key(world, player_key)
        if dto is None:   # 悬空绑定（玩家行不存在）：回未绑定态，不冒空卡片
            return L("me_unbound_scoped", server=server_name) if scoped else L("me_unbound")
        return format_player(
            dto, strict=self._cfg.privacy.mode == "strict",
            server_name=server_name, world_mode=_world_mode(self._cfg),
            tz=server_timezone(self._cfg, world), now=self._clock.now(), is_me=True,
        )

    @_gated
    async def unbind_self(self, umo, message_str, is_group, sender_id) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "unbind", is_group
        )
        if err is not None:
            return err
        scoped = _world_mode(self._cfg) != "single"
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        player_key = await self._repo.get_binding(phash, world.world_id)
        if player_key is None:
            return (L("unbind_self_none_scoped", server=server_name)
                    if scoped else L("unbind_self_none"))
        ident = await self._repo.get_player(world.world_id, player_key)
        await self._repo.delete_binding(phash, world.world_id)
        anchor = self._server_anchor(server_name)
        if ident is None:   # 悬空绑定（spec §6#10）：绝不渲染 player_key 哈希
            return L("unbind_self_dangling", anchor=anchor)
        return L("unbind_self_ok", name=ident.latest_name, anchor=anchor)
