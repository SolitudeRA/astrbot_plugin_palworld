import pytest

from palworld_terminal.config import parse_config
from palworld_terminal.container import Container
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.presentation.server_arg import ArgError, parse_arg
from tests.integration.conftest import _FakeRest, _FakeSched, make_config

UMO = "aiocqhttp:GroupMessage:123456"


def config_two_servers_with_seed() -> dict:
    cfg = make_config(access_mode="restricted")
    cfg["routing"]["world_mode"] = "multi"
    cfg["servers"] = [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": ""},
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": ""},
    ]
    cfg["group_bindings"] = [{"umo": UMO, "server": "alpha", "active": True}]
    return cfg


@pytest.fixture
async def routed(tmp_path):
    """（container, cfg）双服务器 restricted 路由夹具，预设 alpha 为 active。

    注入 fake rest/scheduler 工厂（conftest 先例），避免真实 HTTP 与调度器非确定性；
    验证 seed-only 不覆盖运行时 use 与每 umo active 唯一性端到端成立。
    """
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(config_two_servers_with_seed(), env={})
    container = Container(
        config=cfg, data_dir=tmp_path, clock=clock,
        rest_factory=lambda s, clk: _FakeRest(),
        scheduler_factory=lambda **k: _FakeSched(),
    )
    await container.start()
    try:
        yield container, cfg
    finally:
        await container.stop()


async def test_seed_only_does_not_override_runtime_use(routed):
    container, cfg = routed
    # 预设让 alpha 为 active；运行时管理员 /pal use beta
    await container.routing.use(UMO, "beta")
    assert await container.repo.get_binding_active(UMO) == "beta"

    # 再次触发一次 seed（模拟重载后 start 再次播种）→ 不得把 active 覆盖回 alpha
    await container.repo.seed_bindings(cfg.group_bindings)
    assert await container.repo.get_binding_active(UMO) == "beta", "seed 覆盖了运行时 use"
    # alpha 仍在 allowed 集合（预设授权保留），但 active 归 beta
    assert "alpha" in await container.repo.get_allowed(UMO)
    assert "beta" in await container.repo.get_allowed(UMO)


async def test_active_uniqueness_per_umo(routed):
    container, cfg = routed
    await container.routing.use(UMO, "alpha")
    await container.routing.use(UMO, "beta")
    # 每 umo 至多一个 active
    rows = await container.db.query(
        "SELECT server_id FROM group_servers WHERE umo=? AND active=1", (UMO,))
    assert [r[0] for r in rows] == ["beta"]


def test_parse_arg_strips_trailing_server_and_keeps_spaced_name():
    # "/pal guild Sunset Valley @beta" → name="Sunset Valley", override="beta"
    parsed = parse_arg("/pal guild Sunset Valley @beta", subcommand="guild")
    assert parsed.name == "Sunset Valley"
    assert parsed.server_override == "beta"


def test_parse_arg_no_server_override():
    parsed = parse_arg("/pal guild Noema Alliance", subcommand="guild")
    assert parsed.name == "Noema Alliance"
    assert parsed.server_override is None


def test_parse_arg_multiple_trailing_at_is_illegal():
    with pytest.raises(ArgError):
        parse_arg("/pal guild Name @alpha @beta", subcommand="guild")


async def test_restricted_denies_then_allows_after_use(routed):
    container, cfg = routed
    umo = "aiocqhttp:GroupMessage:999"  # 无任何绑定的新群

    # restricted 下未授权 → resolve 返回 error（拒绝），server 为 None
    denied = await container.routing.resolve(umo, override="alpha", is_group=True)
    assert denied.server is None
    assert denied.error is not None

    # 管理员 /pal use alpha 授权后 → resolve 命中 alpha
    await container.routing.use(umo, "alpha")
    allowed = await container.routing.resolve(umo, override=None, is_group=True)
    assert allowed.error is None
    assert allowed.server is not None
    assert allowed.server.server_id == "alpha"


async def test_dangling_binding_after_server_removed_falls_back(tmp_path):
    clock = FakeClock(start=1_700_000_000)
    umo = "aiocqhttp:GroupMessage:555"

    # 第一次启动：alpha + beta，授权并激活 beta
    cfg1 = parse_config(config_two_servers_with_seed(), env={})
    c1 = Container(
        config=cfg1, data_dir=tmp_path, clock=clock,
        rest_factory=lambda s, clk: _FakeRest(),
        scheduler_factory=lambda **k: _FakeSched(),
    )
    await c1.start()
    await c1.routing.use(umo, "beta")
    assert (await c1.repo.get_binding_active(umo)) == "beta"
    await c1.stop()

    # 第二次启动：配置删除 beta（仅剩 alpha）→ 复用同一 data_dir（绑定表保留）
    raw2 = config_two_servers_with_seed()
    raw2["servers"] = [s for s in raw2["servers"] if s["name"] == "alpha"]
    raw2["group_bindings"] = []  # 不再预设
    cfg2 = parse_config(raw2, env={})
    c2 = Container(
        config=cfg2, data_dir=tmp_path, clock=clock,
        rest_factory=lambda s, clk: _FakeRest(),
        scheduler_factory=lambda **k: _FakeSched(),
    )
    await c2.start()
    try:
        # 本群 active 指向已消失的 beta → 视为未绑定，走兜底（error 非空，server 为 None），不崩溃
        res = await c2.routing.resolve(umo, override=None, is_group=True)
        assert res.server is None
        assert res.error is not None
        # 显式 @beta 指向不存在/未就绪 → 明确提示（error 非空）
        res2 = await c2.routing.resolve(umo, override="beta", is_group=True)
        assert res2.server is None
        assert res2.error is not None
    finally:
        await c2.stop()
