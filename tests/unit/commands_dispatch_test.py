"""组分发方法 + 门控下沉（spec §4.1 门控落点重构，安全模型心脏）。

门控三态（本任务核心交付，测试锁死）：
- gate=read（world/guild/player）：per-子动作功能门（下沉）+ admin_denied 完整路径锁（下沉）。
- gate=admin_write（server 7 写）：走 admin_write（门序 admin 硬门先于 feature）+ 正确功能组映射。
- gate=admin（link add/remove）：需 is_admin，非 admin_write。

命名：组分发器 world_grp/guild_grp/player_grp/server_grp/link（world/guild/player 已是实现
方法名，additive 不可撞——T8 删旧实现后再改裸名）。
"""
from __future__ import annotations

from types import SimpleNamespace

from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.application.routing_service import Resolution
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.locale import L
from tests.unit._perm import overrides


class _Clock:
    def now(self) -> float:
        return 0.0


class _BoomQuery:
    def __getattr__(self, _name):
        async def _boom(*a, **k):
            raise AssertionError("query 不应被触达")
        return _boom


class _BoomRepo:
    async def get_current_world(self, sid):
        raise AssertionError("repo 不应被触达")


class _ErrRouting:
    """resolve 恒回路由错误串——证明「过了门、触达实现」而不必备齐深层 fake。"""

    async def resolve(self, umo, override, is_group):
        return Resolution(None, "ROUTING_ERR")


class _WorldRouting:
    """resolve 成功给出 world——用于测「缺必填参数」等需过 resolve 的分支。"""

    def __init__(self) -> None:
        self.override_seen: object = "UNSET"

    async def resolve(self, umo, override, is_group):
        self.override_seen = override
        return Resolution(SimpleNamespace(server_id="s1", name="Alpha"), None)


class _WorldRepo:
    async def get_current_world(self, sid):
        return SimpleNamespace(world_id="w1")


class _RecordRouting:
    def __init__(self) -> None:
        self.use_calls: list = []
        self.unbind_calls: list = []
        self.ready_called = False

    async def use(self, umo, name):
        self.use_calls.append((umo, name))
        return "USE_OK"

    async def unbind(self, umo, name):
        self.unbind_calls.append((umo, name))
        return "UNBIND_OK"

    def ready_servers(self):
        self.ready_called = True
        return []


class _RecordRepo:
    async def list_group_servers(self, umo):
        return {}


class _FakeAdmin:
    def __init__(self) -> None:
        self.calls: list = []

    async def announce(self, admin_id, umo, is_group, message):
        self.calls.append(("announce", message))
        return SimpleNamespace(
            ok=True, message_key="admin_ok",
            params={"server": "Alpha", "action": "announce", "target": "", "error": ""},
        )


def _cfg(feats=None, locked=(), require=False):
    """feats: {功能组: bool} 门开关（镜像旧 _Features，默认全开）；
    locked: 完整路径列表，逐路径落 admin_only=True（叶子锁）。"""
    ov = dict(overrides(**(feats or {})))
    for path in locked:
        prev = ov.get(path)
        ov[path] = CommandOverride(
            enabled=prev.enabled if prev is not None else None, admin_only=True,
        )
    return SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=ov),
        server_admin=SimpleNamespace(require_confirmation=require, confirmation_timeout=30),
        servers=[],
        skipped=[],
    )


def _mk(routing=None, query=None, repo=None, cfg=None, admin=None):
    return Commands(
        routing, query, repo, cfg or _cfg(), _Clock(), b"",
        admin_service=admin, confirmations=None,
    )


# ============================================================================
# gate=read —— per-子动作功能门（下沉），一个 world_grp 跨 core/events/report 三门
# ============================================================================

async def test_world_per_subaction_feature_gate():
    # core 恒开；events/report 关
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(),
            _cfg(feats={"events": False, "report": False}))
    # status(core) 过功能门 → 触达实现 → 回路由错误串（证明未被门拦）
    assert await c.world_grp("u", "/pal world status", True, "s", False) == "ROUTING_ERR"
    # events(events 组关) → feature_disabled，不触达实现
    assert await c.world_grp("u", "/pal world events", True, "s", False) == L("feature_disabled")
    # today(report 组关) → feature_disabled，不触达实现
    assert await c.world_grp("u", "/pal world today", True, "s", False) == L("feature_disabled")


async def test_world_overview_force_off_feature_disabled():
    # overview 归队 guilds_bases + 上游不可用 force-off：恒短路 feature_disabled，不触达实现
    # （原「非递归路由到 world 实现」护栏在 force-off 期间死于门后，恢复上游后反转即回归）。
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(), _cfg())
    assert await c.world_grp("u", "/pal world overview", True, "s", False) == L("feature_disabled")


async def test_guild_per_subaction_feature_gate():
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(), _cfg(feats={"guilds_bases": False}))
    assert await c.guild_grp("u", "/pal guild list", True, "s", False) == L("feature_disabled")
    assert await c.guild_grp("u", "/pal guild info X", True, "s", False) == L("feature_disabled")
    assert await c.guild_grp("u", "/pal guild bases", True, "s", False) == L("feature_disabled")


async def test_guild_and_overview_force_off_even_when_configured_on():
    # §5B②：guilds_bases 上游不可用——即便配置 guild 组 on / world overview 叶 on，
    # commands 层仍收既有 feature_disabled（force-off 先于门，不触达实现；防实现时另加新文案）。
    cfg = _cfg()
    cfg.permissions.command_overrides["guild"] = CommandOverride(enabled=True)
    cfg.permissions.command_overrides["guild list"] = CommandOverride(enabled=True)
    cfg.permissions.command_overrides["world overview"] = CommandOverride(enabled=True)
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(), cfg)
    assert await c.guild_grp("u", "/pal guild list", True, "s", False) == L("feature_disabled")
    assert await c.world_grp("u", "/pal world overview", True, "s", False) == L("feature_disabled")


# ============================================================================
# gate=read —— admin_denied 下沉，按完整路径判（world status / player info …）
# ============================================================================

async def test_admin_denied_downshift_full_path():
    # 锁完整路径 "player info"，非管理员 → admin_required 且不触达 query。
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(), _cfg(locked=["player info"]))
    out = await c.player_grp("u", "/pal player info Alice", True, "nonadmin", False)
    assert out == L("admin_required")  # 锁生效，query Boom 未炸 = 未触达底层
    # 管理员放行 → 过锁 → 触达实现（resolve 回错误串证明过锁）
    out2 = await c.player_grp("u", "/pal player info Alice", True, "admin", True)
    assert out2 == "ROUTING_ERR"


async def test_admin_lock_is_leaf_isolated():
    # 锁一个兄弟叶子 "player bind" 绝不波及 "player info"（完整路径叶子隔离语义）。
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(), _cfg(locked=["player bind"]))
    out = await c.player_grp("u", "/pal player info Alice", True, "nonadmin", False)
    assert out == "ROUTING_ERR"  # 未被锁 → 触达实现


async def test_world_status_lock_downshift():
    # 完整路径 "world status" 锁：非管理员 → admin_required，管理员放行。
    c = _mk(_ErrRouting(), _BoomQuery(), _BoomRepo(), _cfg(locked=["world status"]))
    assert await c.world_grp("u", "/pal world status", True, "nonadmin", False) == L("admin_required")
    assert await c.world_grp("u", "/pal world status", True, "admin", True) == "ROUTING_ERR"


# ============================================================================
# gate=read —— signature/override 适配（rebuild rest + @override）
# ============================================================================

async def test_override_survives_dispatch():
    # /pal player info Alice @beta → 实现须收到 name=Alice、override=beta。
    captured: dict = {}

    class _Q:
        async def player_profile(self, world, name):
            captured["name"] = name
            return None

    routing = _WorldRouting()
    c = _mk(routing, _Q(), _WorldRepo(), _cfg())
    out = await c.player_grp("u", "/pal player info Alice @beta", True, "s", False)
    assert routing.override_seen == "beta"   # @override 存活穿过分发
    assert captured["name"] == "Alice"       # name 不含 @token
    assert out == L("player_not_found", name="Alice")


async def test_player_bind_and_unbind_pass_sender_id():
    # player bind/unbind → 实现 bind/unbind_self，须传 sender_id；rebuilt 参数正确。
    c = _mk(_ErrRouting(), None, None, _cfg())
    seen: dict = {}

    async def spy_bind(umo, message_str, is_group, sender_id):
        seen["bind"] = (umo, message_str, is_group, sender_id)
        return "B"

    async def spy_unbind(umo, message_str, is_group, sender_id):
        seen["unbind"] = (umo, message_str, is_group, sender_id)
        return "U"

    c.bind = spy_bind
    c.unbind_self = spy_unbind
    assert await c.player_grp("u", "/pal player bind Alice", True, "sender9", False) == "B"
    assert seen["bind"] == ("u", "Alice", True, "sender9")
    assert await c.player_grp("u", "/pal player unbind", True, "sender9", False) == "U"
    assert seen["unbind"] == ("u", "", True, "sender9")


# ============================================================================
# 未知子动作 / 缺必填参数 → 用法
# ============================================================================

async def test_unknown_subaction_returns_group_help():
    c = _mk(None, None, None, _cfg())
    out = await c.world_grp("u", "/pal world foo", True, "s", False)
    assert "status" in out and "today" in out  # 列出合法子动作


async def test_bare_group_returns_group_help():
    c = _mk(None, None, None, _cfg())
    out = await c.world_grp("u", "/pal world", True, "s", False)
    assert "status" in out          # 仍列可见子动作
    assert "overview" not in out    # overview force-off：裸组 help 不列


async def test_player_info_missing_name_returns_usage():
    # 子动作合法但缺名 → 该子动作用法（player_usage）；需过 resolve 才到达名校验。
    c = _mk(_WorldRouting(), _BoomQuery(), _WorldRepo(), _cfg())
    out = await c.player_grp("u", "/pal player info", True, "s", False)
    assert out == L("player_usage")


# ============================================================================
# gate=admin_write —— server 7 写走 admin_write（门序 admin 先于 feature + 正确组）
# ============================================================================

async def test_server_write_nonadmin_admin_required():
    admin = _FakeAdmin()
    c = _mk(_ErrRouting(), None, None, _cfg(), admin=admin)
    out = await c.server_grp("u", "/pal server kick Alice", True, "nonadmin", False)
    assert out == L("admin_required")
    assert admin.calls == []  # 未触达底层


async def test_server_write_admin_hard_gate_before_feature():
    # 门序铁律：admin 硬门先于 feature——组关也必须回 admin_required（防配置态泄漏）。
    admin = _FakeAdmin()
    c = _mk(_ErrRouting(), None, None,
            _cfg(feats={"server_admin_basic": False, "server_admin_danger": False}), admin=admin)
    out = await c.server_grp("u", "/pal server stop", True, "nonadmin", False)
    assert out == L("admin_required")
    assert admin.calls == []


async def test_server_write_maps_correct_feature_group():
    # 逐写子动作锚定：走 admin_write + 正确功能组（漏门/错组=无鉴权关服）。
    c = _mk(None, None, None, _cfg())
    captured: list = []

    async def spy(command_str, group, admin_id, umo, is_group, arg_str, is_admin):
        captured.append((command_str, group, arg_str, is_admin))
        return "OK"

    c.admin_write = spy
    await c.server_grp("u", "/pal server kick Alice 破坏", True, "admin", True)
    await c.server_grp("u", "/pal server stop", True, "admin", True)
    assert captured[0][:2] == ("kick", "server_admin_basic")
    assert captured[0][2] == "Alice 破坏"     # arg_str = rebuilt rest
    assert captured[0][3] is True             # is_admin 透传
    assert captured[1][:2] == ("stop", "server_admin_danger")

    captured.clear()
    basic = {"announce", "save", "kick", "unban"}
    danger = {"ban", "shutdown", "stop"}
    for sub in [*basic, *danger]:
        await c.server_grp("u", f"/pal server {sub}", True, "admin", True)
    got = {cmd: grp for cmd, grp, *_ in captured}
    for sub in basic:
        assert got[sub] == "server_admin_basic", sub
    for sub in danger:
        assert got[sub] == "server_admin_danger", sub


async def test_server_write_admin_executes_via_admin_write():
    admin = _FakeAdmin()
    c = _mk(_ErrRouting(), None, None, _cfg(), admin=admin)
    out = await c.server_grp("u", "/pal server announce hello", True, "admin", True)
    assert ("announce", "hello") in admin.calls
    assert "Alpha" in out


async def test_server_unknown_subaction_returns_group_help():
    c = _mk(None, None, None, _cfg())
    out = await c.server_grp("u", "/pal server foo", True, "admin", True)
    assert "kick" in out and "stop" in out


# ============================================================================
# gate=admin —— link add/remove 需 is_admin（非 admin_write）；list 走 read
# ============================================================================

async def test_link_add_requires_admin():
    routing = _RecordRouting()
    c = _mk(routing, None, None, _cfg())
    out = await c.link("u", "/pal link add Alpha", True, "nonadmin", False)
    assert out == L("admin_required")
    assert routing.use_calls == []  # 非管理员未触达底层
    out2 = await c.link("u", "/pal link add Alpha", True, "admin", True)
    assert out2 == "USE_OK"
    assert routing.use_calls == [("u", "Alpha")]


async def test_link_remove_requires_admin():
    routing = _RecordRouting()
    c = _mk(routing, None, None, _cfg())
    out = await c.link("u", "/pal link remove Alpha", True, "nonadmin", False)
    assert out == L("admin_required")
    assert routing.unbind_calls == []
    await c.link("u", "/pal link remove Alpha", True, "admin", True)
    assert routing.unbind_calls == [("u", "Alpha")]


async def test_link_add_only_in_group():
    routing = _RecordRouting()
    c = _mk(routing, None, None, _cfg())
    out = await c.link("u", "/pal link add Alpha", False, "admin", True)  # 私聊
    assert out == L("use_only_group")
    assert routing.use_calls == []


async def test_link_add_empty_name_usage():
    routing = _RecordRouting()
    c = _mk(routing, None, None, _cfg())
    out = await c.link("u", "/pal link add", True, "admin", True)
    assert out == L("server_usage")
    assert routing.use_calls == []


async def test_link_add_name_via_override():
    # 保旧优先级：name = server_override or rest（/pal link add @Alpha）。
    routing = _RecordRouting()
    c = _mk(routing, None, None, _cfg())
    await c.link("u", "/pal link add @Alpha", True, "admin", True)
    assert routing.use_calls == [("u", "Alpha")]


async def test_link_list_reaches_impl():
    routing = _RecordRouting()
    c = _mk(routing, None, _RecordRepo(), _cfg())
    out = await c.link("u", "/pal link list", True, "s", False)
    assert isinstance(out, str)
    assert routing.ready_called  # 触达 link_list 底层


async def test_link_bare_group_returns_group_help():
    # 裸组迷你帮助复用 visible_actions 谓词（T9 角色隔离）：guest 只见 list（读），
    # add/remove（gate=admin）对 guest 不可见——与 format_help 同一真相源。
    c = _mk(None, None, None, _cfg())
    guest = await c.link("u", "/pal link", True, "s", False)
    assert "list" in guest and "add" not in guest and "remove" not in guest
    admin = await c.link("u", "/pal link", True, "s", True)
    assert "list" in admin and "add" in admin and "remove" in admin
