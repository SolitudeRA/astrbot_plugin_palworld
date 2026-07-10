import pytest

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.infrastructure.clock import FakeClock


class _FakeRest:
    async def close(self):
        pass


class _FakeSched:
    async def start(self):
        pass

    async def stop(self):
        pass


def make_config(mode: str = "balanced", access_mode: str = "restricted") -> dict:
    return {
        "servers": [
            {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
             "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": "Asia/Tokyo"}
        ],
        "routing": {"access_mode": access_mode, "default_server": ""},
        "group_bindings": [],
        "polling": {"metrics_seconds": 30, "players_seconds": 30, "info_seconds": 600,
                    "settings_seconds": 1800, "game_data_seconds": 120, "jitter_ratio": 0.0, "max_concurrency": 6},
        "world": {"timezone": "Asia/Tokyo", "locale": "zh-CN", "fps_smooth": 50, "fps_moderate": 35, "fps_laggy": 20},
        "bases": {"enabled": True, "assignment_radius": 5000, "ambiguity_ratio": 0.20,
                  "confirmation_samples": 3, "position_grid_size": 2000, "z_weight": 0.5},
        "privacy": {"mode": mode, "public_exact_ping": False, "public_positions": False,
                    "ping_good_ms": 60, "ping_ok_ms": 120, "uncertain_timeout": 900},
        "history": {"raw_metrics_days": 7, "aggregate_days": 90, "session_days": 365, "observation_days": 180},
    }


def make_config_two() -> dict:
    base = make_config()
    base["servers"] = [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": "Asia/Tokyo"},
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": "Asia/Tokyo"},
    ]
    return base


def ok(data) -> RestResponse:
    return RestResponse(ok=True, status=200, data=data, duration_ms=5, payload_bytes=len(str(data)), error=None)


def fail(status: int | None = None, error: str = "unreachable") -> RestResponse:
    return RestResponse(ok=False, status=status, data=None, duration_ms=5, payload_bytes=0, error=error)


@pytest.fixture
async def harness(tmp_path):
    """返回 (container, server_config, clock, snap_service) 单服务器采集夹具。

    注入 fake rest/scheduler 工厂（5.16/5.16b 先例），避免真实 HTTP 与真实调度器的
    非确定性；集成测试通过 snap_service 手动驱动 ingest_* 全链路。
    """
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(make_config(), env={})
    container = Container(
        config=cfg, data_dir=tmp_path, clock=clock,
        rest_factory=lambda s, clk: _FakeRest(),
        scheduler_factory=lambda **k: _FakeSched(),
    )
    await container.start()
    server = cfg.servers[0]
    snap = container.snapshot_service_for(server.server_id)
    try:
        yield container, server, clock, snap
    finally:
        await container.stop()


@pytest.fixture
async def harness_two(tmp_path):
    """返回 (container, cfg, clock) 双服务器采集夹具（alpha/beta）。

    与 `harness` 同样注入 fake rest/scheduler 工厂（6.3 先例），验证多服务器数据隔离。
    """
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(make_config_two(), env={})
    container = Container(
        config=cfg, data_dir=tmp_path, clock=clock,
        rest_factory=lambda s, clk: _FakeRest(),
        scheduler_factory=lambda **k: _FakeSched(),
    )
    await container.start()
    try:
        yield container, cfg, clock
    finally:
        await container.stop()
