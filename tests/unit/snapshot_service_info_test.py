import pytest

from palworld_terminal.adapters import normalizer as normalizer_mod
from palworld_terminal.adapters import privacy_filter as privacy_mod
from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.snapshot_service import SnapshotService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


class FakePlayers:
    def __init__(self):
        self.marked_uncertain = []

    async def mark_uncertain(self, world):
        self.marked_uncertain.append(world.world_id)


class _Noop:
    async def apply(self, *a, **k):
        return []


def _app_config(servers):
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://x", username="admin", password="pw",
        timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def service_and_ctx(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1000)
    repo = Repository(db, clock)
    players = FakePlayers()
    cfg = _app_config([_server()])
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=None, salt=b"\x00" * 32, cfg=cfg, clock=clock,
        players=players, guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield svc, repo, clock, players
    await db.close()


def _info_resp(worldguid, ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"Version": "0.3", "ServerName": "S", "WorldGuid": worldguid} if ok else None,
        duration_ms=5, payload_bytes=10, error=None if ok else "timeout",
    )


async def test_ingest_info_creates_new_world(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    world = await svc.ingest_info(_server(), _info_resp("GUID-A"))
    assert world is not None
    assert world.world_id == "s1:GUID-A:0"
    assert world.epoch == 0
    assert world.worldguid == "GUID-A"
    assert world.first_seen_at == 1000
    stored = await repo.get_current_world("s1")
    assert stored is not None
    assert stored.world_id == "s1:GUID-A:0"


async def test_ingest_info_same_guid_updates_last_seen(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    await svc.ingest_info(_server(), _info_resp("GUID-A"))
    clock.advance(500)
    world = await svc.ingest_info(_server(), _info_resp("GUID-A"))
    assert world.world_id == "s1:GUID-A:0"
    assert world.first_seen_at == 1000
    assert world.last_seen_at == 1500
    assert players.marked_uncertain == []  # 未换世界不置 uncertain


async def test_ingest_info_worldguid_change_switches_epoch_and_marks_uncertain(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    await svc.ingest_info(_server(), _info_resp("GUID-A"))
    clock.advance(100)
    new_world = await svc.ingest_info(_server(), _info_resp("GUID-B"))
    assert new_world.world_id == "s1:GUID-B:0"
    stored = await repo.get_current_world("s1")
    assert stored.world_id == "s1:GUID-B:0"
    # 旧世界被置 uncertain
    assert players.marked_uncertain == ["s1:GUID-A:0"]


async def test_ingest_info_failed_response_returns_none(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    world = await svc.ingest_info(_server(), _info_resp("X", ok=False))
    assert world is None
    assert await repo.get_current_world("s1") is None
