from pathlib import Path

from palworld_terminal.adapters import normalizer as normalizer_mod
from palworld_terminal.adapters import privacy_filter as privacy_mod
from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.application.snapshot_service import SnapshotService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PermissionsConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palworld_terminal.container import Container
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.clock import FakeClock


def _server() -> ServerConfig:
    return ServerConfig("alpha", "alpha", True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[_server()], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
        # 容器装配门读 command_overrides：guild 组开 → game-data 接线 + Guild/BaseService 构造。
        permissions=PermissionsConfig(
            admins=[], command_overrides={"guild": CommandOverride(enabled=True)},
        ),
    )


class _FakeRest:
    async def close(self):
        pass


class _FakeSched:
    async def start(self):
        pass

    async def stop(self):
        pass


def _world() -> World:
    return World("alpha:guid-1:0", "alpha", "guid-1", 0, "alpha", "0.3", 1, 1700000000, 42)


async def _container(tmp_path: Path):
    clock = FakeClock(1700000000)
    c = Container(_cfg(), tmp_path, clock,
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    await c.routing._repo.upsert_world(_world())
    return c


async def test_rules_reads_shared_settings_cache(tmp_path: Path):
    c = await _container(tmp_path)
    try:
        world = _world()
        resp = RestResponse(ok=True, status=200, data={"ExpRate": "1.5"},
                            duration_ms=2, payload_bytes=4, error=None)
        await c._snapshot.ingest_settings(world, resp)
        dto = await c.query.rules(world)
        assert dto.rows, "rules should render rows from the shared settings cache"
        assert any("1.5" in row.value for row in dto.rows)
    finally:
        await c.stop()


async def test_world_summary_reads_shared_world_cache(tmp_path: Path):
    c = await _container(tmp_path)
    try:
        world = _world()
        resp = RestResponse(
            ok=True, status=200,
            data={"characters": [{"type": "Player", "isactive": "true"}], "palboxes": []},
            duration_ms=2, payload_bytes=4, error=None,
        )
        await c._snapshot.ingest_game_data(world, resp)
        dto = await c.query.world_summary(world)
        assert dto.players == 1
    finally:
        await c.stop()


async def test_snapshot_service_backward_compatible_without_shared_caches(tmp_path):
    # 2.17 contract: constructing SnapshotService WITHOUT the new kwargs keeps
    # the private cache + get_settings behavior intact.
    from palworld_terminal.adapters.sqlite_repository import Repository
    from palworld_terminal.infrastructure.database import Database
    from palworld_terminal.infrastructure.migrations import apply_migrations

    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(3000)

    class _Noop:
        async def apply(self, *a, **k):
            return []

        async def mark_uncertain(self, *a, **k):
            return None

    svc = SnapshotService(
        Repository(db, clock), normalizer_mod, privacy_mod, None, b"\x00" * 32,
        _cfg(), clock, _Noop(), _Noop(), _Noop(), _Noop(),
    )
    try:
        resp = RestResponse(ok=True, status=200, data={"ExpRate": 2.0},
                            duration_ms=2, payload_bytes=4, error=None)
        await svc.ingest_settings(_world(), resp)
        cached = svc.get_settings("alpha:guid-1:0")
        assert cached is not None
        assert cached["data"]["ExpRate"] == 2.0
        assert cached["observed_at"] == 3000
    finally:
        await db.close()
