from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..application.dtos import ServerStatusRow
from ..application.query_service import metric_stale
from ..domain.enums import AccessMode
from ..presentation.formatters import (
    format_help,
    format_servers,
    visible_actions,
)
from ..presentation.locale import L
from ..presentation.server_arg import ArgError, parse_group
from ..shared.command_permissions import (
    effective_admin_only,
    effective_enabled,
)
from ..shared.command_registry import DISPATCH
from .admin_write_flow import AdminWriteFlow
from .command_support import (
    _SENDER_METHODS,
    _fold_limit,
    _world_mode,
    feature_disabled_text,
)
from .read_commands import ReadCommands


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
        self._reads = ReadCommands(routing, query, repo, cfg, clock, salt)
        self._writes = AdminWriteFlow(admin_service, routing, confirmations, cfg, clock)

    async def _resolve_world(self, umo: str, message_str: str, subcommand: str, is_group: bool):
        return await self._reads._resolve_world(umo, message_str, subcommand, is_group)

    async def handle_query(
        self, umo: str, message_str: str, subcommand: str, is_group: bool,
        formatter: Callable, query_fn: Callable[..., Awaitable],
    ) -> str:
        return await self._reads.handle_query(
            umo, message_str, subcommand, is_group, formatter, query_fn
        )

    async def status(self, umo, message_str, is_group) -> str:
        return await self._reads.status(umo, message_str, is_group)

    async def online(self, umo, message_str, is_group) -> str:
        return await self._reads.online(umo, message_str, is_group)

    async def world(self, umo, message_str, is_group) -> str:
        return await self._reads.world(umo, message_str, is_group)

    async def rules(self, umo, message_str, is_group) -> str:
        return await self._reads.rules(umo, message_str, is_group)

    async def guilds(self, umo, message_str, is_group) -> str:
        return await self._reads.guilds(umo, message_str, is_group)

    async def guild(self, umo, message_str, is_group) -> str:
        return await self._reads.guild(umo, message_str, is_group)

    async def bases(self, umo, message_str, is_group) -> str:
        return await self._reads.bases(umo, message_str, is_group)

    async def base(self, umo, message_str, is_group) -> str:
        return await self._reads.base(umo, message_str, is_group)

    async def events(self, umo, message_str, is_group) -> str:
        return await self._reads.events(umo, message_str, is_group)

    async def today(self, umo, message_str, is_group) -> str:
        return await self._reads.today(umo, message_str, is_group)

    async def rank(self, umo, message_str, is_group, sender_id=None) -> str:
        return await self._reads.rank(umo, message_str, is_group, sender_id)

    async def player(self, umo, message_str, is_group) -> str:
        return await self._reads.player(umo, message_str, is_group)

    async def bind(self, umo, message_str, is_group, sender_id) -> str:
        return await self._reads.bind(umo, message_str, is_group, sender_id)

    async def me(self, umo, message_str, is_group, sender_id) -> str:
        return await self._reads.me(umo, message_str, is_group, sender_id)

    async def unbind_self(self, umo, message_str, is_group, sender_id) -> str:
        return await self._reads.unbind_self(umo, message_str, is_group, sender_id)

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

    def _group_help(self, group: str, is_admin: bool) -> str:
        """裸组 / 未知子动作迷你帮助——**复用 format_help 同一 visible_actions 谓词**
        （单一真相源，绝不另写过滤）：guest 绝不见管理员写动作（kick/ban/stop）。
        """
        vis = visible_actions(
            group, is_admin, self._cfg.permissions.command_overrides, _world_mode(self._cfg),
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
            return feature_disabled_text(f"{group} {p.sub}")
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
            return feature_disabled_text(f"link {p.sub}")
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

    async def _server_reachable(self, server_id: str, now: int, metrics_seconds: int) -> bool:
        """link list 可达性派生（spec §4.20/§3）：该服当前 world 最新 metric 新鲜 → 在线。

        无 world / 无 metric / 陈旧 → 不可达（离线）。复用 T2 metric_stale 同阈值同 helper
        （status 降级与 link list 可达共用同一新鲜度判定，避免语义分叉）。
        """
        world = await self._repo.get_current_world(server_id)
        if world is None:
            return False
        metric = await self._repo.latest_metric(world.world_id)
        if metric is None:
            return False
        return not metric_stale(metric.observed_at, now, metrics_seconds)

    async def link_list(self, umo, is_group, is_admin) -> str:
        """/pal link list（spec §4.20）：ready + 群授权状态 + 三态可达点 → format_servers。

        三态点：未就绪(🟡)=配置不完整(not ready)；在线(🟢)/离线(🔴)=ready 服务器按其当前
        world 最新 metric 新鲜度派生（reachability）。私聊不查群授权（授权段由 formatter 省略）。
        """
        now = self._clock.now() if self._clock else 0
        metrics_seconds = getattr(
            getattr(self._cfg, "polling", None), "metrics_seconds", 30)
        group = await self._repo.list_group_servers(umo) if is_group else {}
        rows = []
        for s in (self._cfg.servers if self._cfg else self._routing.ready_servers()):
            allowed, active = group.get(s.server_id, (False, False))
            online = s.ready and await self._server_reachable(s.server_id, now, metrics_seconds)
            rows.append(ServerStatusRow(
                name=s.name, ready=s.ready, online=online,
                allowed=allowed, active=active,
            ))
        skipped = self._cfg.skipped if self._cfg else []
        return format_servers(
            rows, skipped, is_admin, is_group=is_group, fold_limit=_fold_limit(self._cfg),
        )

    async def link_add(self, umo, name, is_group) -> str:
        """/pal link add（spec §4.21）：routing.use 结构化返回 → 渲染上提本层。"""
        if not is_group:
            return L("use_only_group")
        if not name:
            return L("link_add_usage")
        result = await self._routing.use(umo, name)
        if not result.ok:
            return L("link_add_unknown", server=name)   # 拆键：routing server_unknown 素文不用
        if result.replaced_active is not None:
            return L("link_add_ok_replaced", server=result.server_id, old=result.replaced_active)
        return L("link_add_ok", server=result.server_id)

    async def link_remove(self, umo, name, is_group) -> str:
        """/pal link remove（spec §4.22）：routing.unbind 结构化返回 → 渲染上提本层。"""
        if not is_group:
            return L("use_only_group")
        if not name:
            return L("link_remove_usage")
        result = await self._routing.unbind(umo, name)
        if not result.removed:
            return L("link_remove_none", server=name)   # 无授权记录：素文中性无操作
        if result.was_active:
            return L("link_remove_ok_active", server=name)
        return L("link_remove_ok", server=name)

    def help(self, message_str, is_admin) -> str:
        # help 输出与 @服务器 无关：跳过 parse_arg（§6#3）——尾双 @（/pal help x @a @b）不再
        # 裸抛 ArgError 致用户无回复。topic 维持忽略（不扩 /pal help <组>，YAGNI）。
        del message_str
        return format_help(
            None, is_admin,
            self._cfg.permissions.command_overrides, _world_mode(self._cfg),
        )

    async def whoami(self, sender_id: str) -> str:
        """/pal whoami（spec §4.27）：账号标识 + 引导脚注；已是管理员次行加注（零查询）。"""
        if sender_id.endswith(":"):  # 账号段为空(取不到 sender)
            return L("whoami_no_sender")
        if self.is_plugin_admin(sender_id):
            return L("whoami_admin", id=sender_id)
        return L("whoami", id=sender_id)

    async def whereami(self, umo: str) -> str:
        """/pal whereami（spec §4.28）：群标识 + 授权态按 access_mode 分流。

        open 模式 → 授权名单不参与 resolve，改显「开放模式无需授权」（否则输出与真实
        可用性相反）；restricted → 渲染授权段 + 脚注，多模式查 list_group_servers、单模式
        零查询 single_allowed_groups（active 括注是多模式概念，单模式变体省略）。
        """
        if not umo:
            return L("whereami_no_umo")
        head = L("whereami_head", umo=umo)
        if self._cfg.routing.access_mode is not AccessMode.RESTRICTED:
            return f"{head}\n{L('whereami_open')}"
        if _world_mode(self._cfg) == "single":
            allowed = {e.umo for e in self._cfg.routing.single_allowed_groups}
            if umo in allowed:
                ready = self._routing.ready_servers()
                status = L("whereami_authed", servers=ready[0].name) if ready \
                    else L("whereami_authed", servers="")
            else:
                status = L("whereami_unauthed")
        else:
            group = await self._repo.list_group_servers(umo)
            authed: list[str] = []
            for s in self._cfg.servers:
                is_allowed, active = group.get(s.server_id, (False, False))
                if is_allowed:
                    authed.append(f"{s.name}（当前活动）" if active else s.name)
            status = (L("whereami_authed", servers="、".join(authed))
                      if authed else L("whereami_unauthed"))
        return f"{head}\n{status}\n{L('whereami_footer')}"

    # ---- 服务器管控写编排（门面委派 → AdminWriteFlow；写安全心脏隔离进独立文件）----
    # server_grp 里的 self.admin_write(...) 命中此委派 stub（保 monkeypatch 语义：
    # commands_dispatch_test patch c.admin_write 经 server_grp 调到它）——绝不改成 self._writes。

    async def admin_write(
        self, command_str: str, group: str, admin_id: str, umo: str,
        is_group: bool, arg_str: str, is_admin: bool,
    ) -> str:
        return await self._writes.admin_write(
            command_str, group, admin_id, umo, is_group, arg_str, is_admin,
        )

    async def confirm(self, admin_id: str, umo: str, is_group: bool, is_admin: bool) -> str:
        return await self._writes.confirm(admin_id, umo, is_group, is_admin)

    def clear_pending(self) -> None:
        self._writes.clear_pending()

    def is_plugin_admin(self, sender_id: str) -> bool:
        return sender_id in {a.id for a in self._cfg.permissions.admins}

    def admin_denied(self, command_str: str, sender_id: str) -> str | None:
        if effective_admin_only(self._cfg.permissions.command_overrides, command_str) \
                and not self.is_plugin_admin(sender_id):
            return L("admin_required")
        return None
