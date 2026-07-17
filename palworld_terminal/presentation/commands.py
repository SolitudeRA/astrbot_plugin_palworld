from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable

from ..adapters.privacy_filter import hash_user_id
from ..application.command_permissions import (
    active_endpoints,
    effective_admin_only,
    effective_enabled,
)
from ..application.query_service import PlayerProfileDTO
from ..application.report_service import server_timezone
from ..domain.enums import EndpointName
from ..presentation.command_registry import DISPATCH, METHOD_PATH
from ..presentation.confirmation import PendingAction
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
    visible_actions,
)
from ..presentation.locale import L
from ..presentation.server_arg import ArgError, parse_arg, parse_group

# shutdown 倒计时秒数上界（spec §3：正整数、1–86400）。
_SHUTDOWN_MAX_SECONDS = 86400


def _parse_shutdown_seconds(token: str) -> int | None:
    """解析 shutdown 首 token 为倒计时秒数：正整数且 ≤ 上界，否则 None。"""
    if not token.isdigit():  # 空串/负号/非数字均落此（isdigit 对 "-5"/"" 返 False）
        return None
    seconds = int(token)
    if seconds < 1 or seconds > _SHUTDOWN_MAX_SECONDS:
        return None
    return seconds

# 写命令 → 面向用户的中文动作名（渲染消息/预览用；同时区分 stop 与 shutdown 的
# 「已发起」文案——二者共用 admin_shutdown_initiated 键，靠 action 值区分）。
_ACTION_LABEL = {
    "announce": "广播公告",
    "save": "存档",
    "kick": "踢出",
    "unban": "解封",
    "ban": "封禁",
    "shutdown": "关服",
    "stop": "停止服务",
}


def _target_display(name: str | None, userid: str | None) -> str:
    """预览/回执里的目标显示：角色名 + userid 尾段（消同名歧义）。"""
    tail = userid[-4:] if userid else ""
    if name:
        return f"玩家 {name}（…{tail}）"
    if tail:
        return f"玩家（…{tail}）"
    return ""


def _gated(fn):
    """命令 gating：按方法名查 METHOD_PATH 得完整路径，查该路径生效值（组键/叶子/默认
    三级继承），未启用则回 feature_disabled、不触达底层（spec §5）。
    METHOD_PATH 须覆盖全部 @_gated 方法，否则此处 KeyError（meta 测试防回归）。
    """
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        path = METHOD_PATH[fn.__name__]
        if not effective_enabled(self._cfg.permissions.command_overrides, path):
            return L("feature_disabled")
        return await fn(self, *args, **kwargs)
    return wrapper


# 分发到需 sender_id 的实现方法（组内仅 player 用 bind/unbind_self）——分发器据此
# 决定传参形态。其余读实现签名为 (umo, message_str, is_group)。
_SENDER_METHODS = frozenset({"bind", "me", "unbind_self"})


class Commands:
    def __init__(
        self, routing, query, repo, cfg, clock, salt: bytes = b"",
        admin_service=None, confirmations=None,
    ) -> None:
        self._routing = routing
        self._query = query
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt
        self._admin = admin_service
        self._confirmations = confirmations

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
            return None, arg, res.error, ""
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
        return format_status(dto, server_name, show_bases=self._guilds_bases_on())

    async def online(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "online", is_group,
            formatter=format_online, query_fn=self._query.online,
        )

    async def world(self, umo, message_str, is_group) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "world", is_group
        )
        if err is not None:
            return err
        dto = await self._query.world_summary(world)
        return format_world(dto, server_name, strict=self._is_strict())

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
        return await self.handle_query(
            umo, message_str, "guilds", is_group,
            formatter=format_guilds, query_fn=self._query.guilds,
        )

    @_gated
    async def guild(self, umo, message_str, is_group) -> str:
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "guild", is_group)
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
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "base", is_group)
        if err is not None:
            return err
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
            fold_limit=self._cfg.players.list_fold_limit,
        )

    @_gated
    async def today(self, umo, message_str, is_group) -> str:
        world, _arg, err, server_name = await self._resolve_world(
            umo, message_str, "today", is_group
        )
        if err is not None:
            return err
        return format_today(await self._query.today(world), server_name)

    @_gated
    async def rank(self, umo, message_str, is_group) -> str:
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "rank", is_group)
        if err is not None:
            return err
        strict = self._cfg.privacy.mode == "strict"
        which = arg.name.strip().lower()
        if which not in ("today", "total", "level"):
            which = "today"  # 缺省 today（spec §6）
        # strict 双砍：today 与 total 同为时长榜(≈作息)均回 notice；level 不受影响。
        if which in ("today", "total") and strict:
            return L("rank_duration_strict")
        dto = await self._query.rank(world, which)
        return format_rank(dto, which=which, strict=strict)

    @_gated
    async def player(self, umo, message_str, is_group) -> str:
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "player", is_group)
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
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "bind", is_group)
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
        world, arg, err, _srv = await self._resolve_world(umo, message_str, "me", is_group)
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

    @_gated
    async def unbind_self(self, umo, message_str, is_group, sender_id) -> str:
        world, _arg, err, _srv = await self._resolve_world(umo, message_str, "unbind", is_group)
        if err is not None:
            return err
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        player_key = await self._repo.get_binding(phash, world.world_id)
        if player_key is None:
            return L("unbind_self_none")
        ident = await self._repo.get_player(world.world_id, player_key)
        name = ident.latest_name if ident is not None else player_key
        await self._repo.delete_binding(phash, world.world_id)
        return L("unbind_self_ok", name=name)

    # ---- 分级组分发 + 门控下沉（安全模型心脏；spec §4.1 门控落点重构）----
    # 门不再挂方法级 _gated（一个 world_grp 跨 core/events/report 三门）；分发循环内
    # 解析出子动作后，按分发表 ActionSpec 逐子动作施门：
    #   gate=read        —— per-子动作功能门 + admin_denied 完整路径锁（均下沉至此）。
    #   gate=admin_write —— 走 admin_write（门序 admin 硬门先于 feature + 审计）。
    #   gate=admin       —— 需 is_admin（link add/remove）。
    # 组分发器命名 *_grp：world/guild/player 已是实现方法名（DISPATCH 复用），不可撞。
    # T8 保留 *_grp 后缀（handler 串是「world」、调 world_grp），实现方法与分发器共存。

    def _admin_locked(self, path: str, sender_id: str, is_admin: bool) -> bool:
        """命令锁（下沉）：按完整路径查生效 admin_only（组键/叶子/gate 强制三级），
        锁定且非管理员 → True。"""
        return (
            effective_admin_only(self._cfg.permissions.command_overrides, path)
            and not is_admin
        )

    def _world_mode(self) -> str:
        """真实 AppConfig 恒有 routing.world_mode；默认 multi 兼容不完整测试替身。"""
        return getattr(getattr(self._cfg, "routing", None), "world_mode", "multi")

    def _group_help(self, group: str, is_admin: bool) -> str:
        """裸组 / 未知子动作迷你帮助——**复用 format_help 同一 visible_actions 谓词**
        （单一真相源，绝不另写过滤）：guest 绝不见管理员写动作（kick/ban/stop）。
        """
        vis = visible_actions(
            group, is_admin, self._cfg.permissions.command_overrides, self._world_mode(),
        )
        if not vis:
            return L("group_no_actions")
        subs = " / ".join(sub for sub, _spec in vis)
        return f"用法：/pal {group} <{subs}>"

    @staticmethod
    def _rebuild_arg(p) -> str:
        """把 parse_group 拆出的 rest + 尾 @override 复原为 message_str，供复用的扁平
        实现再经 parse_arg 解析——@override 穿过分发不丢（否则 override 被吞）。
        """
        parts = [p.rest] if p.rest else []
        if p.server_override:
            parts.append(f"@{p.server_override}")
        return " ".join(parts)

    async def _dispatch_read(
        self, group: str, umo, message_str, is_group, sender_id, is_admin,
    ) -> str:
        """world/guild/player 组（全 gate=read）共享分发骨架。"""
        try:
            p = parse_group(message_str, group)
        except ArgError:
            return L("arg_error")
        if not p.sub:
            return self._group_help(group, is_admin)
        spec = DISPATCH[group].get(p.sub)
        if spec is None:
            return self._group_help(group, is_admin)      # 未知子动作 → 组用法
        method, _feat_group, _gate = spec
        # per-子动作功能门（下沉）：逐子动作查完整路径生效值（组键/叶子/默认三级继承）。
        if not effective_enabled(self._cfg.permissions.command_overrides, f"{group} {p.sub}"):
            return L("feature_disabled")
        # admin_denied 下沉：按完整路径判锁，锁定且非管理员不触达实现。
        if self._admin_locked(f"{group} {p.sub}", sender_id, is_admin):
            return L("admin_required")
        rebuilt = self._rebuild_arg(p)
        if method in _SENDER_METHODS:
            return await getattr(self, method)(umo, rebuilt, is_group, sender_id)
        return await getattr(self, method)(umo, rebuilt, is_group)

    async def world_grp(self, umo, message_str, is_group, sender_id, is_admin) -> str:
        return await self._dispatch_read("world", umo, message_str, is_group, sender_id, is_admin)

    async def guild_grp(self, umo, message_str, is_group, sender_id, is_admin) -> str:
        return await self._dispatch_read("guild", umo, message_str, is_group, sender_id, is_admin)

    async def player_grp(self, umo, message_str, is_group, sender_id, is_admin) -> str:
        return await self._dispatch_read("player", umo, message_str, is_group, sender_id, is_admin)

    async def server_grp(self, umo, message_str, is_group, sender_id, is_admin) -> str:
        """server 组（全 gate=admin_write）：每写子动作走 admin_write——门序 admin 硬门
        先于 feature + 审计；绝不套方法级 _gated（跨 basic/danger 两组会误判）。
        """
        try:
            p = parse_group(message_str, "server")
        except ArgError:
            return L("arg_error")
        if not p.sub:
            return self._group_help("server", is_admin)
        spec = DISPATCH["server"].get(p.sub)
        if spec is None:
            return self._group_help("server", is_admin)
        method, feat_group, _gate = spec
        return await self.admin_write(
            command_str=method, group=feat_group, admin_id=sender_id, umo=umo,
            is_group=is_group, arg_str=self._rebuild_arg(p), is_admin=is_admin,
        )

    async def link(self, umo, message_str, is_group, sender_id, is_admin) -> str:
        """link 组：list=gate read（群内可见）；add/remove=gate admin（需 is_admin，
        非 admin_write）。底层沿用旧 /pal server 列表 + routing.use/unbind（迁入守卫）。
        """
        try:
            p = parse_group(message_str, "link")
        except ArgError:
            return L("arg_error")
        if not p.sub:
            return self._group_help("link", is_admin)
        spec = DISPATCH["link"].get(p.sub)
        if spec is None:
            return self._group_help("link", is_admin)
        method, _feat_group, gate = spec
        if not effective_enabled(self._cfg.permissions.command_overrides, f"link {p.sub}"):
            return L("feature_disabled")
        if gate == "admin":
            if not is_admin:
                return L("admin_required")
            name = p.server_override or p.rest      # 保旧优先级：override 先于 rest
            return await getattr(self, method)(umo, name, is_group)
        # gate == read（list）
        if self._admin_locked(f"link {p.sub}", sender_id, is_admin):
            return L("admin_required")
        # link 现仅 list 一个 read 子动作，故此处直调 link_list；
        # 若日后新增第二个 read 子动作，须改回按 DISPATCH 泛化分发（getattr(method)）。
        return await self.link_list(umo, is_group, is_admin)

    async def link_list(self, umo, is_group, is_admin) -> str:
        """旧裸 /pal server 列表逻辑迁入（ready + 群绑定状态 → format_servers）。"""
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

    async def link_add(self, umo, name, is_group) -> str:
        """旧 /pal server add 逻辑迁入（routing.use；is_group/空名守卫）。"""
        if not is_group:
            return L("use_only_group")
        if not name:
            return L("server_usage")
        return await self._routing.use(umo, name)

    async def link_remove(self, umo, name, is_group) -> str:
        """旧 /pal server remove 逻辑迁入（routing.unbind；is_group/空名守卫）。"""
        if not is_group:
            return L("use_only_group")
        if not name:
            return L("server_usage")
        return await self._routing.unbind(umo, name)

    def help(self, message_str, is_admin) -> str:
        arg = parse_arg(message_str, "help")
        return format_help(
            arg.name or None, is_admin,
            self._cfg.permissions.command_overrides, self._world_mode(),
        )

    async def whoami(self, sender_id: str) -> str:
        if sender_id.endswith(":"):  # 账号段为空(取不到 sender)
            return L("whoami_no_sender")
        return L("whoami", id=sender_id)

    async def whereami(self, umo: str) -> str:
        if not umo:
            return L("whereami_no_umo")
        return L("whereami", umo=umo)

    # ---- 服务器管控写编排（本功能安全模型的心脏；门序为铁律）----

    async def admin_write(
        self, command_str: str, group: str, admin_id: str, umo: str,
        is_group: bool, arg_str: str, is_admin: bool,
    ) -> str:
        # 门 1（铁律）：admin 硬门先于 feature——非管理员一律 admin_required，
        # 与组开关无关（防「组开时才 admin_required」的配置态泄漏）。
        if not is_admin:
            return L("admin_required")
        # 门 2：feature 门（按完整路径生效值；门序仍在 admin 硬门之后，铁律不变）。
        if not effective_enabled(
            self._cfg.permissions.command_overrides, f"server {command_str}"
        ):
            return L("feature_disabled")

        try:
            arg = parse_arg(arg_str, command_str)
        except ArgError:
            return L("arg_error")
        rest = arg.name.strip()
        require = self._cfg.server_admin.require_confirmation

        # 目标类命令（kick/ban）：先解析目标；multi/none 直接回文案、不进 pending、不执行。
        if command_str in ("kick", "ban"):
            parts = rest.split(maxsplit=1)
            token = parts[0] if parts else ""
            reason = parts[1] if len(parts) > 1 else ""
            if not token:
                return L("admin_target_usage", action=_ACTION_LABEL[command_str])
            # 目标解析与执行须落在同一台服务器：用 override=None（与 AdminService
            # ._execute 的路由一致，避免「在 A 解析、在 B 执行」的错位）。
            # 写路径：for_write=True → 单模式绕过读授权名单（admin 硬门已在上文把守）。
            resolution = await self._routing.resolve(umo, None, is_group, for_write=True)
            if resolution.server is None:
                return L("admin_resolve_failed", reason=resolution.error or "")
            server = resolution.server
            target = await self._admin.resolve_target(server.server_id, token)
            if target.kind == "unreachable":
                # 拉取在线列表失败：不进 pending、不执行、不 post（区别于「无此玩家」）。
                return L("target_unreachable", target=token)
            if target.kind == "none":
                return L("target_none", target=token)
            if target.kind == "multi":
                return L(
                    "target_multi", target=token,
                    candidates="、".join(c["name"] for c in target.candidates),
                )
            if command_str == "ban" and require:
                return self._store_pending(
                    command_str, group, admin_id, umo, server,
                    payload={"userid": target.userid, "name": target.name, "reason": reason},
                    target_disp=_target_display(target.name, target.userid),
                )
            result = await self._admin.execute_target(
                admin_id, umo, is_group, action=command_str, path=command_str,
                userid=target.userid, name=target.name, reason=reason,
            )
            return self._render_result(result)

        if command_str == "unban":
            if not rest:
                return L("admin_unban_usage")
            result = await self._admin.unban(admin_id, umo, is_group, rest)
            return self._render_result(result)

        if command_str == "announce":
            if not rest:
                return L("admin_announce_usage")
            result = await self._admin.announce(admin_id, umo, is_group, rest)
            return self._render_result(result)

        if command_str == "save":
            result = await self._admin.save(admin_id, umo, is_group)
            return self._render_result(result)

        if command_str == "shutdown":
            # 首 token=倒计时秒数（正整数 + 上界校验），其余=公告（可空）。
            parts = rest.split(maxsplit=1)
            seconds = _parse_shutdown_seconds(parts[0] if parts else "")
            if seconds is None:
                return L("admin_shutdown_usage")
            message = parts[1] if len(parts) > 1 else ""
            if require:
                # 写路径：for_write=True → 单模式绕过读授权名单。
                resolution = await self._routing.resolve(umo, None, is_group, for_write=True)
                if resolution.server is None:
                    return L("admin_resolve_failed", reason=resolution.error or "")
                return self._store_pending(
                    command_str, group, admin_id, umo, resolution.server,
                    payload={"seconds": seconds, "message": message},
                    target_disp=L("admin_shutdown_summary", seconds=seconds),
                )
            result = await self._admin.shutdown(admin_id, umo, is_group, seconds, message)
            return self._render_result(result)

        if command_str == "stop":
            if require:
                # 写路径：for_write=True → 单模式绕过读授权名单。
                resolution = await self._routing.resolve(umo, None, is_group, for_write=True)
                if resolution.server is None:
                    return L("admin_resolve_failed", reason=resolution.error or "")
                return self._store_pending(
                    command_str, group, admin_id, umo, resolution.server,
                    payload={}, target_disp="",
                )
            result = await self._admin.stop(admin_id, umo, is_group)
            return self._render_result(result)

        return L("feature_disabled")  # 未知写命令：不触达底层

    def _store_pending(
        self, command_str, group, admin_id, umo, server, *, payload, target_disp,
    ) -> str:
        timeout = self._cfg.server_admin.confirmation_timeout
        self._confirmations.put(admin_id, PendingAction(
            command_str=command_str, group=group, payload=payload,
            server_id=server.server_id, umo=umo,
            expiry=self._clock.now() + timeout,
        ))
        return L(
            "admin_confirm_preview", action=_ACTION_LABEL[command_str],
            target=target_disp, server=server.name, timeout=timeout,
        )

    async def confirm(self, admin_id: str, umo: str, is_group: bool, is_admin: bool) -> str:
        # confirm 自身也过 admin 硬门。
        if not is_admin:
            return L("admin_required")
        # claim-then-execute：原子 pop（过期一并作废），再执行。
        p = self._confirmations.claim(admin_id)
        if p is None:
            return L("admin_no_pending")
        # 执行前复检：danger 命令仍启用 + 重跑目标授权（任一失败 → 丢弃回 stale）。
        if not effective_enabled(
            self._cfg.permissions.command_overrides, f"server {p.command_str}"
        ):
            return L("admin_confirm_stale")
        # 写路径：for_write=True → 单模式绕过读授权名单（confirm 已过 admin 硬门）。
        resolution = await self._routing.resolve(p.umo, None, is_group, for_write=True)
        if resolution.server is None:
            return L("admin_confirm_stale")

        # 不重解析目标（玩家可能已离线）：直接用 payload 里首发解析好的参数执行。
        if p.command_str == "ban":
            result = await self._admin.execute_target(
                admin_id, p.umo, is_group, action="ban", path="ban",
                userid=p.payload["userid"], name=p.payload.get("name"),
                reason=p.payload.get("reason", ""),
            )
            target_disp = _target_display(p.payload.get("name"), p.payload["userid"])
        elif p.command_str == "shutdown":
            # 复用首发存入 payload 的 seconds+message（confirm 不重解析，秒数不丢）。
            seconds = p.payload["seconds"]
            result = await self._admin.shutdown(
                admin_id, p.umo, is_group, seconds, p.payload.get("message", "")
            )
            target_disp = L("admin_shutdown_summary", seconds=seconds)
        elif p.command_str == "stop":
            result = await self._admin.stop(admin_id, p.umo, is_group)
            target_disp = ""
        else:
            return L("admin_confirm_stale")

        if not result.ok:
            return self._render_result(result)  # 如实回执失败，不谎报「已确认执行」
        return L(
            "admin_confirm_done", action=_ACTION_LABEL[p.command_str],
            target=target_disp, server=resolution.server.name,
        )

    def _render_result(self, result) -> str:
        """AdminResult → 面向用户文案。action 英文键转中文；候选名列表转串。"""
        params = dict(result.params)
        if "action" in params:
            params["action"] = _ACTION_LABEL.get(params["action"], params["action"])
        cand = params.get("candidates")
        if isinstance(cand, list):
            params["candidates"] = "、".join(str(x) for x in cand)
        return L(result.message_key, **params)

    def clear_pending(self) -> None:
        """config 热重载时清空所有 pending（避免旧上下文被误确认）。"""
        if self._confirmations is not None:
            self._confirmations.clear_all()

    def is_plugin_admin(self, sender_id: str) -> bool:
        return sender_id in {a.id for a in self._cfg.permissions.admins}

    def admin_denied(self, command_str: str, sender_id: str) -> str | None:
        if effective_admin_only(self._cfg.permissions.command_overrides, command_str) \
                and not self.is_plugin_admin(sender_id):
            return L("admin_required")
        return None
