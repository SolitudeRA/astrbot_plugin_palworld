from palchronicle.application.routing_service import Resolution
from palchronicle.config import ServerConfig, parse_config
from palchronicle.domain.models import World
from palchronicle.presentation.commands import Commands
from palchronicle.presentation.locale import L

WID = "alpha:guid-1:0"


def _cfg_all_on():
    return parse_config({
        "servers": [], "routing": {"access_mode": "open", "default_server": ""},
        "group_bindings": [], "polling": {}, "world": {}, "bases": {},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": True, "events": True, "guilds_bases": True},
    }, {})


def _server() -> ServerConfig:
    return ServerConfig("alpha", "alpha", True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


class _FakeRouting:
    def __init__(self, res: Resolution):
        self._res = res
        self.used = None

    async def resolve(self, umo, override, is_group):
        self._last_override = override
        return self._res

    async def use(self, umo, name):
        self.used = (umo, name)
        return f"USE_OK:{name}"

    async def unbind(self, umo, name):
        return f"UNBIND_OK:{name}"

    def ready_servers(self):
        return [_server()]


class _FakeQuery:
    def __init__(self):
        self.status_called_with = None

    async def status(self, world):
        self.status_called_with = world.world_id
        return "STATUS_DTO"


class _FakeRepo:
    async def get_current_world(self, server_id):
        return _world()

    async def latest_metric(self, world_id):
        return object()

    async def list_group_servers(self, umo):
        return {"alpha": (True, True)}


def _fmt_status(dto, cfg=None):
    return f"FORMATTED:{dto}"


async def test_query_happy_path():
    routing = _FakeRouting(Resolution(_server(), None))
    query = _FakeQuery()
    cmds = Commands(routing, query, _FakeRepo(), cfg=None, clock=None)
    out = await cmds.handle_query(
        "umo1", "/pal status @alpha", "status", is_group=True,
        formatter=lambda world_dto: f"OUT:{world_dto}",
        query_fn=query.status,
    )
    assert out == "OUT:STATUS_DTO"
    assert query.status_called_with == WID


async def test_query_resolution_error_returns_error_text():
    routing = _FakeRouting(Resolution(None, "服务器「x」不存在或未就绪。"))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), cfg=None, clock=None)
    out = await cmds.handle_query(
        "umo1", "/pal status", "status", is_group=True,
        formatter=lambda d: "SHOULD_NOT_RENDER", query_fn=_FakeQuery().status,
    )
    assert "不存在或未就绪" in out


async def test_use_requires_group():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.use("umo1", "/pal use alpha", is_group=False, is_admin=True)
    assert "仅可在群聊" in out


async def test_use_requires_admin():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.use("umo1", "/pal use alpha", is_group=True, is_admin=False)
    assert out == L("admin_required")


async def test_unbind_requires_admin():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.unbind("umo1", "/pal unbind alpha", is_group=True, is_admin=False)
    assert out == L("admin_required")


async def test_use_happy_path():
    routing = _FakeRouting(Resolution(_server(), None))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.use("umo1", "/pal use alpha", is_group=True, is_admin=True)
    assert out == "USE_OK:alpha"
    assert routing.used == ("umo1", "alpha")


async def test_unbind_happy_path():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.unbind("umo1", "/pal unbind alpha", is_group=True, is_admin=True)
    assert out == "UNBIND_OK:alpha"


def test_help_role_separation():
    cmds = Commands(
        _FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), _cfg_all_on(), None
    )
    assert "use" in cmds.help("/pal help", is_admin=True)
    assert "use" not in cmds.help("/pal help", is_admin=False)
