"""命令 gating：禁用组命令回 feature_disabled、不触达底层（spec §5/§6）。"""
from palworld_terminal.config import parse_config
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.locale import L


def _cfg(guilds_bases: bool, events: bool = True, report: bool = True):
    return parse_config({
        "servers": [], "routing": {"access_mode": "open", "default_server": ""},
        "group_bindings": [], "polling": {}, "world": {}, "bases": {},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": report, "events": events, "guilds_bases": guilds_bases},
    }, {})


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
    cmds = Commands(routing=None, query=_BoomQuery(), repo=_Repo(),
                    cfg=_cfg(guilds_bases=False), clock=None)
    assert await cmds.guilds("u", "", True) == L("feature_disabled")
    assert await cmds.bases("u", "", True) == L("feature_disabled")
    assert await cmds.guild("u", "x", True) == L("feature_disabled")
    assert await cmds.base("u", "x", True) == L("feature_disabled")


async def test_events_and_today_gated():
    cmds = Commands(None, _BoomQuery(), _Repo(),
                    cfg=_cfg(guilds_bases=False, events=False, report=False), clock=None)
    assert await cmds.events("u", "", True) == L("feature_disabled")
    assert await cmds.today("u", "", True) == L("feature_disabled")


async def test_enabled_group_not_gated():
    # guilds_bases 开启 → gate 放行 → 进入路由解析 → 返回路由错误文案（证明未被 gating 拦截）
    from palworld_terminal.application.routing_service import Resolution

    class _Routing:
        async def resolve(self, umo, override, is_group):
            return Resolution(None, "ROUTING_ERR")

    cmds = Commands(_Routing(), _BoomQuery(), _Repo(), cfg=_cfg(guilds_bases=True), clock=None)
    assert await cmds.guilds("u", "", True) == "ROUTING_ERR"
