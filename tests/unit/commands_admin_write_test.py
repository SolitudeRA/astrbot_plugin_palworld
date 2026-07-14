"""Commands.admin_write 中央写编排 + confirm 复检（本功能安全模型的心脏）。

门序铁律（测试锁定）：
- admin 硬门先于 feature 门：非管理员一律 admin_required（组开/组关都一样，防配置态泄漏）。
- 管理员 + 组关 → feature_disabled。
- 管理员 + basic 组开 → 直接执行。
- 管理员 + danger + require_confirmation=False → 直接执行。
- 管理员 + danger + require_confirmation=True → 存 pending 回预览（不执行）；随后 confirm → 执行。
- confirm 无 pending → admin_no_pending；confirm 复检 danger 组已关 → admin_confirm_stale。
"""
from __future__ import annotations

from types import SimpleNamespace

from palworld_terminal.application.admin_service import AdminResult, TargetResult
from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.confirmation import ConfirmationStore
from palworld_terminal.presentation.locale import L

_SERVER_WRITES = ("announce", "save", "kick", "unban", "ban", "shutdown", "stop")


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
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def announce(self, admin_id, umo, is_group, message):
        self.calls.append(("announce", message))
        return AdminResult(
            ok=True, message_key="admin_ok",
            params={"server": "Alpha", "action": "announce", "target": "", "error": ""},
        )

    async def save(self, admin_id, umo, is_group):
        self.calls.append(("save",))
        return AdminResult(
            ok=True, message_key="admin_ok",
            params={"server": "Alpha", "action": "save", "target": "", "error": ""},
        )

    async def stop(self, admin_id, umo, is_group):
        self.calls.append(("stop",))
        return AdminResult(
            ok=True, message_key="admin_shutdown_initiated",
            params={"server": "Alpha", "action": "stop", "target": "", "error": ""},
        )

    async def shutdown(self, admin_id, umo, is_group, seconds, message):
        self.calls.append(("shutdown", seconds, message))
        return AdminResult(
            ok=True, message_key="admin_shutdown_initiated",
            params={"server": "Alpha", "action": "shutdown", "target": "", "error": ""},
        )

    async def unban(self, admin_id, umo, is_group, userid):
        self.calls.append(("unban", userid))
        return AdminResult(
            ok=True, message_key="admin_ok",
            params={"server": "Alpha", "action": "unban", "target": "", "error": ""},
        )

    async def resolve_target(self, server_id, token):
        self.calls.append(("resolve_target", server_id, token))
        return TargetResult(kind="unique", userid="steam_76561198000003210", name=token)

    async def execute_target(self, admin_id, umo, is_group, *, action, path, userid, name, reason):
        self.calls.append(("execute_target", action, userid, name, reason))
        return AdminResult(
            ok=True, message_key="admin_ok",
            params={"server": "Alpha", "action": action, "target": name or "", "error": ""},
        )


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


# ---- 门序：admin 硬门先于 feature ----

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


# ---- basic 直执 ----

async def test_admin_basic_announce_executes():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True))
    out = await c.admin_write(
        "announce", "server_admin_basic", "p:1", "umo", True, "服务器 5 分钟后维护",
        is_admin=True,
    )
    assert ("announce", "服务器 5 分钟后维护") in admin.calls
    assert out == L("admin_ok", server="Alpha", action="广播公告", target="", error="")


# ---- danger + require_confirmation=False → 直执 ----

async def test_admin_danger_stop_no_confirm_executes():
    admin = _FakeAdmin()
    c = _cmds(admin=admin, cfg=_cfg(group_on=True, require=False))
    out = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    assert ("stop",) in admin.calls
    assert "停止服务" in out or "Alpha" in out


# ---- danger + require_confirmation=True → pending 回预览（不执行）→ confirm 执行 ----

async def test_admin_danger_stop_confirm_flow():
    admin = _FakeAdmin()
    clock = _Clock(0)
    store = ConfirmationStore(clock)
    cfg = _cfg(group_on=True, require=True, timeout=30)
    c = _cmds(admin=admin, cfg=cfg, clock=clock, confirmations=store)

    preview = await c.admin_write(
        "stop", "server_admin_danger", "p:1", "umo", True, "", is_admin=True
    )
    # 预览态：未执行
    assert ("stop",) not in admin.calls
    assert "confirm" in preview  # 预览指示 /pal confirm

    done = await c.confirm("p:1", "umo", True, is_admin=True)
    assert ("stop",) in admin.calls  # confirm 后才执行
    assert "Alpha" in done


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
    assert exec_calls[0][2] == "steam_76561198000003210"  # userid
    assert exec_calls[0][3] == "Alice"  # 首发解析到的角色名（审计落名字，非把 userid 当名字）
    assert "3210" in done


# ---- shutdown 秒数/公告参数链路 ----

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


# ---- confirm 无 pending ----

async def test_confirm_no_pending():
    admin = _FakeAdmin()
    store = ConfirmationStore(_Clock(0))
    c = _cmds(admin=admin, confirmations=store)
    out = await c.confirm("p:1", "umo", True, is_admin=True)
    assert out == L("admin_no_pending")
    assert admin.calls == []


async def test_confirm_requires_admin():
    admin = _FakeAdmin()
    store = ConfirmationStore(_Clock(0))
    c = _cmds(admin=admin, confirmations=store)
    out = await c.confirm("p:1", "umo", True, is_admin=False)
    assert out == L("admin_required")


# ---- confirm 复检：danger 组已关 → 丢弃回 stale ----

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
    assert out == L("admin_confirm_stale")
    assert ("stop",) not in admin.calls  # 复检失败：不执行


# ---- confirm 复检：目标服务器授权在确认前被撤 → 丢弃回 stale ----

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


# ---- 单模式绕过读名单：写路径 resolve 须以 for_write=True 调用 ----


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
