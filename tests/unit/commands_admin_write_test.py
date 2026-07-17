"""Commands.admin_write 中央写编排 + confirm 复检（本功能安全模型的心脏）。

门序铁律（测试锁定）：
- admin 硬门先于 feature 门：非管理员一律 admin_required（组开/组关都一样，防配置态泄漏）。
- 管理员 + 组关 → feature_disabled。
- 管理员 + basic 组开 → 直接执行。
- 管理员 + danger + require_confirmation=False → 直接执行。
- 管理员 + danger + require_confirmation=True → 存 pending 回预览（不执行）；随后 confirm → 执行。
- confirm 无 pending → admin_no_pending；confirm 复检 danger 组已关 → admin_confirm_stale。

回执样张锁定（spec §4.13-4.19 / §4.29）：成功回执统一式 `✅ 动作短语 · {server}` 用上目标尾4；
断连「已发起」直接/confirm 两路语义分立（§6#6）；usage 全英文子命令；unban 本地 steam_ 前缀校验。
"""
from __future__ import annotations

from types import SimpleNamespace

from palworld_terminal.application.admin_service import AdminResult, TargetResult
from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.confirmation import ConfirmationStore
from palworld_terminal.presentation.locale import L

_SERVER_WRITES = ("announce", "save", "kick", "unban", "ban", "shutdown", "stop")
_UID = "steam_76561198000003210"  # 尾4 = 3210


class _Clock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t


class _FakeRouting:
    def __init__(self, server_name: str = "Alpha", server_id: str = "s1") -> None:
        self._name = server_name
        self._id = server_id
        self.resolve_calls: list[tuple] = []
        self.write_flags: list[bool] = []

    async def resolve(self, umo, override, is_group, *, for_write=False):
        self.resolve_calls.append((umo, override, is_group))
        self.write_flags.append(for_write)
        return SimpleNamespace(
            server=SimpleNamespace(server_id=self._id, name=self._name), error=None
        )


class _FakeRoutingRevoke:
    """首发 resolve 给出服务器(存 pending);置 revoked 后 confirm 时 server=None(撤授权)。"""

    def __init__(self, server_name: str = "Alpha", server_id: str = "s1") -> None:
        self._name = server_name
        self._id = server_id
        self.revoked = False

    async def resolve(self, umo, override, is_group, *, for_write=False):
        if self.revoked:
            return SimpleNamespace(server=None, error="not_authorized")
        return SimpleNamespace(
            server=SimpleNamespace(server_id=self._id, name=self._name), error=None
        )


class _FakeAdmin:
    """忠实镜像 AdminService 输出：params 携 target_userid/content/seconds（spec §5#7）。

    initiated=True 模拟 shutdown/stop 断连(视为已发起,message_key=admin_shutdown_initiated)。
    target 覆盖 resolve_target 返回(none/multi/unreachable 三态)。
    """

    def __init__(self, *, initiated: bool = False, target: TargetResult | None = None,
                 fail: bool = False) -> None:
        self.calls: list = []
        self._initiated = initiated
        self._target = target
        self._fail = fail

    def _result(self, action, *, target="", target_userid="", content="", seconds=0):
        if self._fail:
            return AdminResult(
                ok=False, message_key="admin_failed",
                params={"server": "Alpha", "action": action, "target": target,
                        "target_userid": target_userid, "content": content,
                        "seconds": seconds, "error": "http_status_500"},
            )
        key = ("admin_shutdown_initiated"
               if (self._initiated and action in ("shutdown", "stop")) else "admin_ok")
        return AdminResult(
            ok=True, message_key=key,
            params={"server": "Alpha", "action": action, "target": target,
                    "target_userid": target_userid, "content": content,
                    "seconds": seconds, "error": ""},
        )

    async def announce(self, admin_id, umo, is_group, message):
        self.calls.append(("announce", message))
        return self._result("announce", content=message)

    async def save(self, admin_id, umo, is_group):
        self.calls.append(("save",))
        return self._result("save")

    async def stop(self, admin_id, umo, is_group):
        self.calls.append(("stop",))
        return self._result("stop")

    async def shutdown(self, admin_id, umo, is_group, seconds, message):
        self.calls.append(("shutdown", seconds, message))
        return self._result("shutdown", seconds=seconds, content=message)

    async def unban(self, admin_id, umo, is_group, userid):
        self.calls.append(("unban", userid))
        return self._result("unban", target_userid=userid)

    async def resolve_target(self, server_id, token):
        self.calls.append(("resolve_target", server_id, token))
        if self._target is not None:
            return self._target
        return TargetResult(kind="unique", userid=_UID, name=token)

    async def execute_target(self, admin_id, umo, is_group, *, action, path, userid, name, reason):
        self.calls.append(("execute_target", action, userid, name, reason))
        return self._result(action, target=name or "", target_userid=userid, content=reason)


def _cfg(group_on: bool = True, require: bool = False, timeout: int = 30):
    # 门控查完整路径生效值：逐 server 写命令落 enable=group_on（危险命令不从组键继承）。
    ov = {f"server {c}": CommandOverride(enabled=group_on) for c in _SERVER_WRITES}
    return SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=ov),
        server_admin=SimpleNamespace(
            require_confirmation=require, confirmation_timeout=timeout
        ),
    )


def _cmds(admin=None, cfg=None, clock=None, confirmations=None, routing=None):
    return Commands(
        routing or _FakeRouting(), None, None,
        cfg or _cfg(), clock or _Clock(), b"",
        admin_service=admin, confirmations=confirmations,
    )


# ---- 门序：admin 硬门先于 feature（安全铁律，逻辑零改动）----

async def test_nonadmin_group_on_returns_admin_required():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=False
    )
    assert out == L("admin_required")
    assert admin.calls == []  # 未触达底层


async def test_nonadmin_group_off_still_admin_required():
    # 门序：admin 先于 feature——组关也必须回 admin_required（防配置态泄漏）
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=False))
    out = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=False
    )
    assert out == L("admin_required")
    assert admin.calls == []


async def test_admin_group_off_returns_feature_disabled():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=False))
    out = await c.admin_write(
        "announce", "server_admin_basic", "p:1", "umo", True, "hi", is_admin=True
    )
    assert out == L("feature_disabled")
    assert admin.calls == []


# ---- 成功回执逐条样张（spec §4.13-4.19）----

async def test_announce_receipt_echoes_content():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "announce", "server_admin_basic", "p:1", "umo", True, "服务器 5 分钟后维护",
        is_admin=True,
    )
    assert ("announce", "服务器 5 分钟后维护") in admin.calls
    assert out == "✅ 公告已广播 · Alpha\n└ “服务器 5 分钟后维护”"


async def test_save_receipt():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "save", "server_admin_basic", "p:1", "umo", True, "", is_admin=True
    )
    assert out == "✅ 已执行存档 · Alpha"


async def test_kick_receipt_shows_target_tail4():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "kick", "server_admin_basic", "p:1", "umo", True, "Neo afk", is_admin=True
    )
    assert out == "✅ 已踢出 Neo（…3210） · Alpha"


async def test_unban_receipt_shows_userid_tail4():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "unban", "server_admin_basic", "p:1", "umo", True, "steam_76561198000001234",
        is_admin=True,
    )
    assert out == "✅ 已解封 …1234 · Alpha"


async def test_ban_receipt_with_reason_footnote():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "ban", "server_admin_danger", "p:1", "umo", True, "Neo 刷屏", is_admin=True
    )
    assert out == "✅ 已封禁 Neo（…3210） · Alpha\n└ 理由：刷屏"


async def test_ban_receipt_no_reason_no_footnote():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "ban", "server_admin_danger", "p:1", "umo", True, "Neo", is_admin=True
    )
    assert out == "✅ 已封禁 Neo（…3210） · Alpha"


async def test_shutdown_receipt_countdown_footnote():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "60 服务器维护",
        is_admin=True,
    )
    assert out == "✅ 已发出关服指令 · Alpha\n└ 60 秒后关服 · 公告：“服务器维护”"


async def test_shutdown_receipt_countdown_no_message():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "45", is_admin=True
    )
    assert out == "✅ 已发出关服指令 · Alpha\n└ 45 秒后关服"


async def test_stop_receipt_normal_success():
    admin = _FakeAdmin(initiated=False)
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    assert ("stop",) in admin.calls
    assert out == "✅ 已停止服务进程 · Alpha"


# ---- 断连已发起（直接路径，仅 shutdown/stop；§4.13-4.19 末条）----

async def test_direct_disconnect_initiated_shutdown():
    admin = _FakeAdmin(initiated=True)
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "60", is_admin=True
    )
    assert out == "✅ 指令已发出 · Alpha\n└ 服务器连接已断开，按已生效处理"


async def test_direct_disconnect_initiated_stop():
    admin = _FakeAdmin(initiated=True)
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    assert out == "✅ 指令已发出 · Alpha\n└ 服务器连接已断开，按已生效处理"


# ---- 失败回执 ----

async def test_failed_receipt():
    admin = _FakeAdmin(fail=True)
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "60", is_admin=True
    )
    assert out == "❌ 关服失败 · Alpha\n└ http_status_500"


# ---- 目标族三态（§4.13-4.19）----

async def test_target_none_receipt():
    admin = _FakeAdmin(target=TargetResult(kind="none", name="Neo2"))
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "kick", "server_admin_basic", "p:1", "umo", True, "Neo2", is_admin=True
    )
    assert out == "❌ 未找到在线玩家「Neo2」\n└ 离线玩家可用 steam_ userid 直接指定"
    assert not any(x[0] == "execute_target" for x in admin.calls)  # 未执行


async def test_target_unreachable_receipt():
    admin = _FakeAdmin(target=TargetResult(kind="unreachable", name="Neo"))
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "kick", "server_admin_basic", "p:1", "umo", True, "Neo", is_admin=True
    )
    assert out == "❌ 无法获取在线玩家列表（服务器可能不可达），请稍后重试"
    assert not any(x[0] == "execute_target" for x in admin.calls)


async def test_target_multi_receipt_lists_candidates_with_tail4():
    admin = _FakeAdmin(target=TargetResult(
        kind="multi", name="Neo",
        candidates=[
            {"name": "Neo", "userid": "steam_76561198000003210"},
            {"name": "Neo", "userid": "steam_76561198000005678"},
        ],
    ))
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "kick", "server_admin_basic", "p:1", "umo", True, "Neo", is_admin=True
    )
    assert out == (
        "⚠️ 「Neo」有多个同名在线玩家\n"
        "· Neo（…3210）\n"
        "· Neo（…5678）\n"
        "└ 用 steam_ userid 精确指定"
    )
    assert not any(x[0] == "execute_target" for x in admin.calls)


# ---- usage 全英文子命令（修「/pal server 踢出」不通顺）----

async def test_kick_usage_english_subcommand():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "kick", "server_admin_basic", "p:1", "umo", True, "", is_admin=True
    )
    assert out == "用法：/pal server kick <玩家名|steam_userid> [理由]"
    assert admin.calls == []  # 空目标：不触达底层


async def test_ban_usage_english_subcommand():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "ban", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    assert out == "用法：/pal server ban <玩家名|steam_userid> [理由]"


# ---- unban 本地 steam_ 前缀校验（零成本防不透明 REST 错误）----

async def test_unban_missing_arg_returns_usage():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "unban", "server_admin_basic", "p:1", "umo", True, "", is_admin=True
    )
    assert out == L("admin_unban_usage")
    assert admin.calls == []


async def test_unban_non_steam_prefix_rejected_locally():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "unban", "server_admin_basic", "p:1", "umo", True, "abc123", is_admin=True
    )
    assert out == "❌ userid 须以 steam_ 开头"
    assert admin.calls == []  # 前缀不符：不触达底层 REST


# ---- 二次确认预览三变体（§4.13-4.19）----

async def test_preview_ban_variant():
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=True, timeout=30),
              clock=clock, confirmations=store)
    out = await c.admin_write(
        "ban", "server_admin_danger", "p:1", "umo", True, "Neo 刷屏", is_admin=True
    )
    assert out == (
        "⚠️ 待确认 · 封禁 Neo（…3210） · Alpha\n"
        "└ 30 秒内发送 /pal confirm 执行，逾期自动作废"
    )
    assert not any(x[0] == "execute_target" for x in admin.calls)  # 预览未执行


async def test_preview_shutdown_variant():
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=True, timeout=30),
              clock=clock, confirmations=store)
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "60 维护", is_admin=True
    )
    assert out == (
        "⚠️ 待确认 · 关服（60 秒倒计时） · Alpha\n"
        "└ 30 秒内发送 /pal confirm 执行，逾期自动作废"
    )
    assert not any(x[0] == "shutdown" for x in admin.calls)


async def test_preview_stop_variant():
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=True, timeout=30),
              clock=clock, confirmations=store)
    out = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    assert out == (
        "⚠️ 待确认 · 停止服务 · Alpha\n"
        "└ 30 秒内发送 /pal confirm 执行，逾期自动作废"
    )
    assert ("stop",) not in admin.calls


# ---- confirm 成功 / 断连 / 无待确认 / 失效（§4.29）----

async def test_confirm_ban_success_shows_phrase_and_tail4():
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "ban", "server_admin_danger", "p:1", "umo", True, "Neo 刷屏", is_admin=True
    )
    admin.calls.clear()
    done = await c.confirm("p:1", "umo", True, is_admin=True)
    assert not any(x[0] == "resolve_target" for x in admin.calls)  # 不重解析
    assert done == "✅ 已确认执行 · 封禁 Neo（…3210） · Alpha"


async def test_confirm_shutdown_disconnect_restores_initiated_semantics():
    # §6#6：confirm 不再吞 shutdown 断连「已发起」——区别于正常「已确认执行」。
    admin = _FakeAdmin(initiated=True)
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "60 维护", is_admin=True
    )
    done = await c.confirm("p:1", "umo", True, is_admin=True)
    assert done == (
        "✅ 已确认 · 关服指令已发出 · Alpha\n"
        "└ 服务器连接已断开，按已生效处理"
    )


async def test_confirm_stop_disconnect_restores_initiated_semantics():
    admin = _FakeAdmin(initiated=True)
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    done = await c.confirm("p:1", "umo", True, is_admin=True)
    assert done == (
        "✅ 已确认 · 停止服务指令已发出 · Alpha\n"
        "└ 服务器连接已断开，按已生效处理"
    )


async def test_confirm_stop_normal_success_says_confirmed_executed():
    # 非断连（HTTP 成功）：confirm 回「已确认执行」而非「已发起」。
    admin = _FakeAdmin(initiated=False)
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    done = await c.confirm("p:1", "umo", True, is_admin=True)
    assert done == "✅ 已确认执行 · 停止服务 · Alpha"


async def test_confirm_failure_renders_failed_receipt():
    admin = _FakeAdmin(fail=True)
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    done = await c.confirm("p:1", "umo", True, is_admin=True)
    assert done == "❌ 停止服务失败 · Alpha\n└ http_status_500"


# ---- shutdown 秒数/公告参数链路（安全逻辑不变，仅 usage 键沿用）----

async def test_admin_shutdown_parses_seconds_and_message():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "60 维护", is_admin=True
    )
    assert ("shutdown", 60, "维护") in admin.calls
    assert "Alpha" in out


async def test_admin_shutdown_seconds_only_empty_message():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "45", is_admin=True
    )
    assert ("shutdown", 45, "") in admin.calls


async def test_admin_shutdown_invalid_seconds_returns_usage():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "abc 维护", is_admin=True
    )
    assert out == L("admin_shutdown_usage")
    assert not any(x[0] == "shutdown" for x in admin.calls)  # 非法秒数：不触达底层


async def test_admin_shutdown_missing_seconds_returns_usage():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    assert out == L("admin_shutdown_usage")
    assert not any(x[0] == "shutdown" for x in admin.calls)


async def test_admin_shutdown_seconds_over_upper_bound_returns_usage():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "99999999 x", is_admin=True
    )
    assert out == L("admin_shutdown_usage")
    assert not any(x[0] == "shutdown" for x in admin.calls)


async def test_admin_shutdown_confirm_flow_preserves_seconds():
    # danger + require_confirmation：pending payload 须携带 seconds+message，
    # confirm 执行时原样传入（不丢秒数）。
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    preview = await c.admin_write(
        "shutdown", "server_admin_danger", "p:1", "umo", True, "120 例行维护", is_admin=True
    )
    assert not any(x[0] == "shutdown" for x in admin.calls)  # 预览未执行
    assert "120" in preview  # 预览含秒数

    done = await c.confirm("p:1", "umo", True, is_admin=True)
    shutdown_calls = [x for x in admin.calls if x[0] == "shutdown"]
    assert shutdown_calls and shutdown_calls[0][1] == 120  # confirm 用对 seconds
    assert shutdown_calls[0][2] == "例行维护"  # message 不丢
    assert "120" in done


async def test_admin_danger_ban_pending_carries_resolved_target():
    # confirm 不重解析目标：pending payload 携带首发解析到的 userid+name
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    preview = await c.admin_write(
        "ban", "server_admin_danger", "p:1", "umo", True, "Alice 破坏据点", is_admin=True
    )
    assert any(x[0] == "resolve_target" for x in admin.calls)
    assert not any(x[0] == "execute_target" for x in admin.calls)  # 预览未执行
    assert "3210" in preview  # userid 尾段入预览消同名歧义

    admin.calls.clear()
    done = await c.confirm("p:1", "umo", True, is_admin=True)
    # confirm 复用 payload：execute_target 直传已解析 userid+name，绝不再 resolve_target
    assert not any(x[0] == "resolve_target" for x in admin.calls)
    exec_calls = [x for x in admin.calls if x[0] == "execute_target"]
    assert exec_calls and exec_calls[0][1] == "ban"
    assert exec_calls[0][2] == _UID  # userid
    assert exec_calls[0][3] == "Alice"  # 首发解析到的角色名（审计落名字，非把 userid 当名字）
    assert "3210" in done


# ---- confirm 无 pending / stale / 权限 ----

async def test_confirm_no_pending_says_maybe_timed_out():
    admin = _FakeAdmin()
    store = ConfirmationStore(_Clock(0))
    c = _cmds(admin=admin, confirmations=store)
    out = await c.confirm("p:1", "umo", True, is_admin=True)
    assert out == "当前没有待确认的操作（可能已超时作废）"
    assert admin.calls == []


async def test_confirm_requires_admin():
    admin = _FakeAdmin()
    store = ConfirmationStore(_Clock(0))
    c = _cmds(admin=admin, confirmations=store)
    out = await c.confirm("p:1", "umo", True, is_admin=False)
    assert out == L("admin_required")


async def test_confirm_stale_when_group_disabled_after_pending():
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    # danger 命令在确认前被关（叶子 enable=False）
    cfg.permissions.command_overrides["server stop"] = CommandOverride(enabled=False)
    out = await c.confirm("p:1", "umo", True, is_admin=True)
    assert out == "⚠️ 该操作已失效（功能已关闭或服务器不可用），请重新发起"
    assert ("stop",) not in admin.calls  # 复检失败：不执行


async def test_confirm_stale_when_server_revoked_after_pending():
    # 首发存 danger pending 后，routing.resolve 撤授权(server=None)：
    # confirm 复检失败回 stale，且 pending 被 claim 丢弃(第二次 confirm 回 no_pending)。
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    routing = _FakeRoutingRevoke()
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store, routing=routing)

    await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    routing.revoked = True  # 授权在确认前被撤
    out = await c.confirm("p:1", "umo", True, is_admin=True)
    assert out == L("admin_confirm_stale")
    assert ("stop",) not in admin.calls  # 复检失败：不执行
    # pending 已被 claim 原子 pop 丢弃：第二次 confirm 无 pending
    again = await c.confirm("p:1", "umo", True, is_admin=True)
    assert again == L("admin_no_pending")


# ---- 单模式绕过读名单：写路径 resolve 须以 for_write=True 调用（安全，逻辑不变）----

async def test_admin_write_paths_pass_for_write_true():
    # commands.py 4 处写路径 resolve：kick 目标解析 / shutdown+确认 / stop+确认 / confirm。
    # 单模式下 for_write=True 才能绕过读名单；漏穿线则默认 False → 非授权群被拒。
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)

    # kick 目标解析路径（require 不影响 kick 的目标 resolve 先行）
    r_kick = _FakeRouting()
    c = _cmds(admin=_FakeAdmin(), cfg=cfg, clock=clock,
              confirmations=ConfirmationStore(clock), routing=r_kick)
    await c.admin_write("kick", "server_admin_basic", "p:1", "umo", True, "Alice afk",
                        is_admin=True)
    assert r_kick.write_flags and all(f is True for f in r_kick.write_flags)

    # shutdown + 确认路径
    r_sd = _FakeRouting()
    c = _cmds(admin=_FakeAdmin(), cfg=cfg, clock=clock, confirmations=store, routing=r_sd)
    await c.admin_write("shutdown", "server_admin_danger", "p:1", "umo", True, "60 维护",
                        is_admin=True)
    assert r_sd.write_flags == [True]

    # stop + 确认路径
    r_stop = _FakeRouting()
    c = _cmds(admin=_FakeAdmin(), cfg=cfg, clock=clock,
              confirmations=ConfirmationStore(clock), routing=r_stop)
    await c.admin_write("stop", "server_admin_danger", "p:1", "umo", True, "",
                        is_admin=True)
    assert r_stop.write_flags == [True]

    # confirm 复检路径（p.umo）
    r_cf = _FakeRouting()
    st = ConfirmationStore(clock)
    c = _cmds(admin=_FakeAdmin(), cfg=cfg, clock=clock, confirmations=st, routing=r_cf)
    await c.admin_write("stop", "server_admin_danger", "p:1", "umo", True, "",
                        is_admin=True)
    r_cf.write_flags.clear()
    await c.confirm("p:1", "umo", True, is_admin=True)
    assert r_cf.write_flags == [True]  # confirm 内 resolve 也 for_write=True


# ---- claim 原子性：连发两次 confirm，只执行一次 ----

async def test_double_confirm_executes_only_once():
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    first = await c.confirm("p:1", "umo", True, is_admin=True)
    second = await c.confirm("p:1", "umo", True, is_admin=True)
    assert "Alpha" in first             # 第一次执行
    assert second == L("admin_no_pending")  # 第二次无 pending
    # AdminService.stop 恰被调用一次(claim 原子 pop 保证不双执行)
    assert [x for x in admin.calls if x == ("stop",)] == [("stop",)]
