from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..application.command_permissions import (
    effective_admin_only,
    effective_enabled,
)
from ..application.dtos import ServerStatusRow
from ..application.query_service import metric_stale
from ..domain.enums import AccessMode
from ..presentation.confirmation import PendingAction
from ..presentation.formatters import (
    format_help,
    format_servers,
    visible_actions,
)
from ..presentation.locale import L
from ..presentation.server_arg import ArgError, parse_arg, parse_group
from ..shared.command_registry import DISPATCH
from .command_support import (
    _SENDER_METHODS,
    _fold_limit,
    _render_routing_error,
    _world_mode,
    feature_disabled_text,
)
from .read_commands import ReadCommands

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

# 写命令 → 面向用户的中文动作名（失败回执 `{action}失败`、预览/confirm 短语用）。
_ACTION_LABEL = {
    "announce": "广播公告",
    "save": "存档",
    "kick": "踢出",
    "unban": "解封",
    "ban": "封禁",
    "shutdown": "关服",
    "stop": "停止服务",
}


def _target_phrase(name: str | None, userid: str | None) -> str:
    """回执/预览/confirm 里的目标显示：角色名 +（…userid 尾4）消同名歧义。
    steam_ 直传 / unban 无名字解析时退化为 `…尾4`（无「玩家」前缀）。"""
    tail = userid[-4:] if userid else ""
    if name:
        return f"{name}（…{tail}）"
    if tail:
        return f"…{tail}"
    return ""


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

    async def rank(self, umo, message_str, is_group) -> str:
        return await self._reads.rank(umo, message_str, is_group)

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
            return feature_disabled_text(f"server {command_str}")

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
                return L("admin_target_usage", sub=command_str)
            # 目标解析与执行须落在同一台服务器：用 override=None（与 AdminService
            # ._execute 的路由一致，避免「在 A 解析、在 B 执行」的错位）。
            # 写路径：for_write=True → 单模式绕过读授权名单（admin 硬门已在上文把守）。
            resolution = await self._routing.resolve(umo, None, is_group, for_write=True)
            if resolution.server is None:
                reason = _render_routing_error(resolution.error, resolution.error_params)
                return L("admin_resolve_failed", reason=reason)
            server = resolution.server
            target = await self._admin.resolve_target(server.server_id, token)
            if target.kind == "unreachable":
                # 拉取在线列表失败：不进 pending、不执行、不 post（区别于「无此玩家」）。
                return L("target_unreachable")
            if target.kind == "none":
                return L("target_none", target=token)
            if target.kind == "multi":
                # 候选行带 userid 尾4 消歧（· Neo（…1234））。
                cand_lines = "\n".join(
                    f"· {_target_phrase(c['name'], c['userid'])}"
                    for c in target.candidates
                )
                return L("target_multi", target=token, candidates=cand_lines)
            if command_str == "ban" and require:
                return self._store_pending(
                    command_str, group, admin_id, umo, server,
                    payload={"userid": target.userid, "name": target.name, "reason": reason},
                )
            result = await self._admin.execute_target(
                admin_id, umo, is_group, action=command_str, path=command_str,
                userid=target.userid, name=target.name, reason=reason,
            )
            return self._render_result(result)

        if command_str == "unban":
            if not rest:
                return L("admin_unban_usage")
            # 本地 steam_ 前缀校验（零成本防不透明 REST 错误；解封无名字解析路径）。
            if not rest.startswith("steam_"):
                return L("admin_unban_prefix")
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
                    reason = _render_routing_error(resolution.error, resolution.error_params)
                    return L("admin_resolve_failed", reason=reason)
                return self._store_pending(
                    command_str, group, admin_id, umo, resolution.server,
                    payload={"seconds": seconds, "message": message},
                )
            result = await self._admin.shutdown(admin_id, umo, is_group, seconds, message)
            return self._render_result(result)

        if command_str == "stop":
            if require:
                # 写路径：for_write=True → 单模式绕过读授权名单。
                resolution = await self._routing.resolve(umo, None, is_group, for_write=True)
                if resolution.server is None:
                    reason = _render_routing_error(resolution.error, resolution.error_params)
                    return L("admin_resolve_failed", reason=reason)
                return self._store_pending(
                    command_str, group, admin_id, umo, resolution.server,
                    payload={},
                )
            result = await self._admin.stop(admin_id, umo, is_group)
            return self._render_result(result)

        return feature_disabled_text(f"server {command_str}")  # 未知写命令：不触达底层

    @staticmethod
    def _pending_phrase(command_str: str, payload: dict) -> str:
        """二次确认预览 / confirm 成功回执共用的「动作短语」（单一真相源）：
        ban=封禁 Neo（…1234）；shutdown=关服（60 秒倒计时）；stop=停止服务。"""
        if command_str == "ban":
            return (
                f"{_ACTION_LABEL['ban']} "
                f"{_target_phrase(payload.get('name'), payload.get('userid'))}"
            )
        if command_str == "shutdown":
            return f"{_ACTION_LABEL['shutdown']}（{payload['seconds']} 秒倒计时）"
        if command_str == "stop":
            return _ACTION_LABEL["stop"]
        return _ACTION_LABEL.get(command_str, command_str)

    def _store_pending(
        self, command_str, group, admin_id, umo, server, *, payload,
    ) -> str:
        timeout = self._cfg.server_admin.confirmation_timeout
        self._confirmations.put(admin_id, PendingAction(
            command_str=command_str, group=group, payload=payload,
            server_id=server.server_id, umo=umo,
            expiry=self._clock.now() + timeout,
        ))
        return L(
            "admin_confirm_preview",
            phrase=self._pending_phrase(command_str, payload),
            server=server.name, timeout=timeout,
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
        elif p.command_str == "shutdown":
            # 复用首发存入 payload 的 seconds+message（confirm 不重解析，秒数不丢）。
            result = await self._admin.shutdown(
                admin_id, p.umo, is_group, p.payload["seconds"],
                p.payload.get("message", ""),
            )
        elif p.command_str == "stop":
            result = await self._admin.stop(admin_id, p.umo, is_group)
        else:
            return L("admin_confirm_stale")

        if not result.ok:
            return self._render_result(result)  # 如实回执失败，不谎报「已确认执行」
        # §6#6：区分「正常完成=已确认执行」与「断连已发起=已确认 · X指令已发出」。
        # shutdown/stop 断连由 AdminService 标 message_key=admin_shutdown_initiated。
        if result.message_key == "admin_shutdown_initiated":
            return L(
                "admin_confirm_initiated", verb=_ACTION_LABEL[p.command_str],
                server=resolution.server.name,
            )
        return L(
            "admin_confirm_done",
            phrase=self._pending_phrase(p.command_str, p.payload),
            server=resolution.server.name,
        )

    def _render_result(self, result) -> str:
        """AdminResult → 面向用户回执（spec §4.13-4.19）。

        成功 = per-action 短语 + 可选脚注；断连已发起（直接路径）= 通用「指令已发出」；
        失败 = ❌ {动作}失败 + error 脚注；resolve 失败 = ❌ 无法执行：{reason}。
        目标族（target_none/multi/unreachable）在 admin_write 分发内直接渲染，正常写流程
        不经此处；下方保留兜底以防其它调用方（AdminService.kick/ban 直调）经此渲染。
        """
        params = dict(result.params)
        key = result.message_key
        if key == "admin_ok":
            return self._render_admin_ok(params)
        if key == "admin_shutdown_initiated":  # 断连已发起（直接路径，仅 shutdown/stop）
            return L("admin_initiated", server=params.get("server", ""))
        if key == "admin_failed":
            action = str(params.get("action", ""))
            return L(
                "admin_failed", action=_ACTION_LABEL.get(action, action),
                server=params.get("server", ""), error=params.get("error", ""),
            )
        if key == "admin_resolve_failed":
            reason = _render_routing_error(params.get("error"), params.get("error_params", {}))
            return L("admin_resolve_failed", reason=reason)
        if key == "target_unreachable":
            return L("target_unreachable")
        if key == "target_none":
            return L("target_none", target=params.get("target", ""))
        if key == "target_multi":
            cand = params.get("candidates")
            lines = ("\n".join(f"· {x}" for x in cand)
                     if isinstance(cand, list) else str(cand or ""))
            return L("target_multi", target=params.get("target", ""), candidates=lines)
        return L(key, **params)  # 兜底

    @staticmethod
    def _render_admin_ok(params: dict) -> str:
        """成功回执 per-action 短语 + 可选脚注（announce 回显 / ban 理由 / shutdown 倒计时）。"""
        action = params.get("action", "")
        server = params.get("server", "")
        # content 含义随 action（announce 公告 / shutdown 公告 / ban 理由），供数自 _execute。
        content = params.get("content", "") or ""
        name = params.get("target") or None
        userid = params.get("target_userid") or None
        target = _target_phrase(name, userid)
        if action == "announce":
            lines = [L("admin_ok_announce", server=server)]
            if content:
                lines.append(L("admin_fn_announce", content=content))
            return "\n".join(lines)
        if action == "save":
            return L("admin_ok_save", server=server)
        if action == "kick":
            return L("admin_ok_kick", target=target, server=server)
        if action == "unban":
            return L("admin_ok_unban", target=target, server=server)
        if action == "ban":
            lines = [L("admin_ok_ban", target=target, server=server)]
            if content:  # ban 的 content = 理由
                lines.append(L("admin_fn_ban_reason", reason=content))
            return "\n".join(lines)
        if action == "shutdown":
            seconds = params.get("seconds", 0)
            head = L("admin_ok_shutdown", server=server)
            fn = (L("admin_fn_shutdown_msg", seconds=seconds, message=content)
                  if content else L("admin_fn_shutdown", seconds=seconds))
            return f"{head}\n{fn}"
        if action == "stop":
            return L("admin_ok_stop", server=server)
        return L("admin_ok_save", server=server)  # 理论不可达兜底

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
