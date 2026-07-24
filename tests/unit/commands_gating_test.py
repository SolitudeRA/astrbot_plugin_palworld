"""命令 gating：禁用命令回 feature_disabled、不触达底层（spec §5/§6）。

门控查命令生效值（command_overrides 组键/叶子/默认三级继承），非旧 features 组。
"""
from types import SimpleNamespace

import pytest

from palworld_terminal.presentation.commands import Commands, feature_disabled_text
from palworld_terminal.presentation.locale import L
from palworld_terminal.shared.command_permissions import CommandOverride as CO
from tests.unit._perm import overrides


def _cfg(guilds_bases: bool, events: bool = True, report: bool = True):
    ov = overrides(guilds_bases=guilds_bases, events=events, report=report)
    return SimpleNamespace(permissions=SimpleNamespace(command_overrides=ov))


class _BoomQuery:
    """任何被调用的 query 方法都抛错——用于证明禁用命令根本没触达 query。"""
    def __getattr__(self, _name):
        async def _boom(*a, **k):
            raise AssertionError("query 不应被触达")
        return _boom


class _Repo:
    async def get_current_world(self, sid):
        raise AssertionError("repo 不应被触达")


async def test_guilds_disabled_returns_feature_disabled():
    # guilds_bases 关（普通可配 off）→ feature_disabled 主句 + 「设置页开启」引导脚注。
    cmds = Commands(routing=None, query=_BoomQuery(), repo=_Repo(),
                    cfg=_cfg(guilds_bases=False), clock=None)
    fd = feature_disabled_text("guild list")
    assert await cmds.guilds("u", "", True) == fd
    assert await cmds.bases("u", "", True) == fd
    assert await cmds.guild("u", "x", True) == fd
    assert await cmds.base("u", "x", True) == fd


async def test_events_and_today_gated():
    cmds = Commands(None, _BoomQuery(), _Repo(),
                    cfg=_cfg(guilds_bases=False, events=False, report=False), clock=None)
    # events/today 非上游不可用 → 主句 ⚠️ + 「设置页开启」引导脚注（spec §3）。
    assert await cmds.events("u", "", True) == feature_disabled_text("world events")
    assert await cmds.today("u", "", True) == feature_disabled_text("world today")


async def test_enabled_group_not_gated():
    # guilds_bases 开启 → gate 放行 → 进入路由解析 → 返回路由错误文案（证明未被 gating 拦截）。
    from palworld_terminal.application.routing_service import Resolution, RoutingError

    class _Routing:
        async def resolve(self, umo, override, is_group):
            return Resolution(None, RoutingError.NO_SERVER_RESOLVED)

    cmds = Commands(_Routing(), _BoomQuery(), _Repo(), cfg=_cfg(guilds_bases=True), clock=None)
    assert await cmds.guilds("u", "", True) == L("no_server_resolved")


# ---- 继承感知门控：组键 disable 波及叶子；叶子 admin_only 锁非管理员 ----

def _mk(overrides_map):
    cfg = SimpleNamespace(permissions=SimpleNamespace(command_overrides=overrides_map))
    return Commands(routing=None, query=_BoomQuery(), repo=_Repo(), cfg=cfg,
                    clock=SimpleNamespace(now=lambda: 0))


@pytest.mark.asyncio
async def test_group_disable_blocks_leaf():
    # 组键 guild.enabled=False → 叶子 guild list 继承为关 → feature_disabled（含引导脚注），不触达底层。
    cmds = _mk({"guild": CO(enabled=False)})
    out = await cmds.guild_grp("umo", "list", True, "u1", False)
    assert out == feature_disabled_text("guild list")


@pytest.mark.asyncio
async def test_leaf_admin_lock_denies_guest():
    # 门序（功能门先于 admin 锁）：player 开 + 叶子 player info 锁 admin_only →
    # 非管理员回 admin_required（功能门放行后 admin 锁分支可达）。
    cmds = _mk({"player": CO(enabled=True), "player info": CO(admin_only=True)})
    out = await cmds.player_grp("umo", "info", True, "guest", False)
    assert out == L("admin_required")
