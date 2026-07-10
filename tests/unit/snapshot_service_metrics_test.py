import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


class _Noop:
    async def apply(self, *a, **k):
        return []

    async def mark_uncertain(self, *a, **k):
        return None


def _cfg(servers):
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


def _world():
    return World(
        world_id="s1:GUID-A:0", server_id="s1", worldguid="GUID-A", epoch=0,
        server_name="S", version="0.3", first_seen_at=1000, last_seen_at=1000,
        current_day=0,
    )


@pytest.fixture
async def svc_repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=2000)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=None, salt=b"\x00" * 32, cfg=_cfg([]), clock=clock,
        players=_Noop(), guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield svc, repo, clock
    await db.close()


def _metrics_resp(ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={
            "ServerFps": 57, "ServerFrameTime": 17.5, "CurrentPlayerNum": 6,
            "MaxPlayerNum": 32, "Uptime": 1000, "Days": 42, "BaseCampNum": 4,
        } if ok else None,
        duration_ms=3, payload_bytes=8, error=None if ok else "timeout",
    )


async def test_ingest_metrics_persists_world_metric(svc_repo):
    svc, repo, clock = svc_repo
    await svc.ingest_metrics(_world(), _metrics_resp())
    m = await repo.latest_metric("s1:GUID-A:0")
    assert m is not None
    assert m.fps == 57.0
    assert m.online_players == 6
    assert m.world_day == 42
    assert m.basecamp_count == 4
    assert m.observed_at == 2000


async def test_ingest_metrics_updates_world_current_day(svc_repo):
    svc, repo, clock = svc_repo
    await svc.ingest_metrics(_world(), _metrics_resp())
    stored = await repo.get_current_world("s1")
    assert stored.current_day == 42


async def test_ingest_metrics_failed_response_no_persist(svc_repo):
    svc, repo, clock = svc_repo
    await svc.ingest_metrics(_world(), _metrics_resp(ok=False))
    assert await repo.latest_metric("s1:GUID-A:0") is None
