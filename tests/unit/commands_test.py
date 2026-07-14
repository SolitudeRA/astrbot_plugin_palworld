from types import SimpleNamespace

from palworld_terminal.application.routing_service import Resolution
from palworld_terminal.config import ServerConfig, parse_config
from palworld_terminal.domain.models import World
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.locale import L

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


# ---- link 组（原 /pal server 绑定分发迁入；门在 Commands.link 内）----
# 完整 link 分发/门控三态锚定在 commands_dispatch_test；此处覆盖底层 routing 契约。

def _cfg_link(servers=None):
    return SimpleNamespace(
        features=SimpleNamespace(enabled=lambda g: True),
        permissions=SimpleNamespace(admin_only_commands=[]),
        servers=servers if servers is not None else [],
        skipped=[],
    )


async def test_link_add_requires_group():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link add alpha", is_group=False,
                          sender_id="s:1", is_admin=True)
    assert "仅可在群聊" in out


async def test_link_add_requires_admin():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link add alpha", is_group=True,
                          sender_id="s:1", is_admin=False)
    assert out == L("admin_required")


async def test_link_add_happy_path():
    routing = _FakeRouting(Resolution(_server(), None))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link add alpha", is_group=True,
                          sender_id="s:1", is_admin=True)
    assert out == "USE_OK:alpha"
    assert routing.used == ("umo1", "alpha")


async def test_link_remove_happy_path():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link remove alpha", is_group=True,
                          sender_id="s:1", is_admin=True)
    assert out == "UNBIND_OK:alpha"


async def test_link_add_without_name_returns_usage():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link add", is_group=True,
                          sender_id="s:1", is_admin=True)
    assert out == L("server_usage")


async def test_link_typo_subcommand_returns_group_help():
    # 未知子动作 → 组用法(列出合法子动作),不静默列表
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link addd alpha", is_group=True,
                          sender_id="s:1", is_admin=True)
    assert "list" in out and "add" in out and "remove" in out


async def test_link_list_lists_servers():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(servers=[_server()]), None)
    out = await cmds.link("umo1", "/pal link list", is_group=True,
                          sender_id="s:1", is_admin=False)
    assert "已配置服务器" in out and "alpha" in out


async def test_link_add_override_token():
    # /pal link add @alpha 被剥成 server_override;override 优先命中
    routing = _FakeRouting(Resolution(_server(), None))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link add @alpha", is_group=True,
                          sender_id="s:1", is_admin=True)
    assert out == "USE_OK:alpha"
    assert routing.used == ("umo1", "alpha")


async def test_link_double_at_returns_arg_error():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(),
                    _cfg_link(), None)
    out = await cmds.link("umo1", "/pal link @a @b", is_group=True,
                          sender_id="s:1", is_admin=True)
    assert "参数格式错误" in out


def test_help_role_separation():
    cmds = Commands(
        _FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), _cfg_all_on(), None
    )
    assert "/pal link add" in cmds.help("/pal help", is_admin=True)
    assert "/pal link add" not in cmds.help("/pal help", is_admin=False)
