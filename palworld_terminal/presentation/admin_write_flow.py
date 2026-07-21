from __future__ import annotations

from ..application.command_permissions import effective_enabled
from ..presentation.confirmation import PendingAction
from ..presentation.locale import L
from ..presentation.server_arg import ArgError, parse_arg
from .command_support import _render_routing_error, feature_disabled_text

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


class AdminWriteFlow:
    """服务器管控写编排（本功能安全模型的心脏；门序为铁律）。

    从 Commands 隔离进独立文件（BT3）：admin_write/confirm/pending/render 全套写安全逻辑
    逐字搬迁、零行为变化——门序（admin 硬门先于 feature）、二次确认、审计一字未动。
    内部方法互调保持 self（同类内 AdminWriteFlow 自持）。
    """

    def __init__(self, admin_service, routing, confirmations, cfg, clock) -> None:
        self._admin = admin_service
        self._routing = routing
        self._confirmations = confirmations
        self._cfg = cfg
        self._clock = clock

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
