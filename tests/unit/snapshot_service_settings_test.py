import pytest

from palworld_terminal.adapters import normalizer as normalizer_mod
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
    WorldConfig,
)
from palworld_terminal.domain import privacy as privacy_mod
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


class _Noop:
    async def apply(self, *a, **k):
        return []

    async def mark_uncertain(self, *a, **k):
        return None


def _cfg():
    return AppConfig(
        servers=[], skipped=[],
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
        server_name="S", version="0.3", first_seen_at=1, last_seen_at=1,
        current_day=0,
    )


@pytest.fixture
async def svc(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=3000)
    svc = SnapshotService(
        repo=Repository(db, clock), normalizer_mod=normalizer_mod,
        privacy_mod=privacy_mod, meta=None, salt=b"\x00" * 32, cfg=_cfg(),
        clock=clock, players=_Noop(), guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield svc, clock
    await db.close()


def _settings_resp(exp_rate, ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"ExpRate": exp_rate, "PalCaptureRate": 1.0} if ok else None,
        duration_ms=2, payload_bytes=4, error=None if ok else "timeout",
    )


async def test_ingest_settings_caches_data(svc):
    service, clock = svc
    await service.ingest_settings(_world(), _settings_resp(2.0))
    cached = service.get_settings("s1:GUID-A:0")
    assert cached is not None
    assert cached["data"]["ExpRate"] == 2.0
    assert cached["observed_at"] == 3000


async def test_get_settings_none_when_absent(svc):
    service, _ = svc
    assert service.get_settings("unknown") is None


async def test_ingest_settings_failed_keeps_old_cache(svc):
    service, clock = svc
    await service.ingest_settings(_world(), _settings_resp(2.0))
    clock.advance(100)
    await service.ingest_settings(_world(), _settings_resp(99.0, ok=False))
    cached = service.get_settings("s1:GUID-A:0")
    assert cached["data"]["ExpRate"] == 2.0  # 旧值保留
    assert cached["observed_at"] == 3000     # 未刷新
