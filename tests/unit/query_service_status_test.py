from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    WorldConfig,
)
from palchronicle.domain.enums import AccessMode, IdConfidence, PingBucket, SessionStatus
from palchronicle.domain.models import (
    PlayerIdentity,
    PlayerObservation,
    PlayerSession,
    World,
    WorldMetric,
)
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


@pytest.fixture
async def qs(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    q = QueryService(repo, TTLCache(clock), _cfg(), meta=None, clock=clock, settings_cache={})
    yield repo, q, clock
    await db.close()


async def test_status_assembles_dto(qs):
    repo, q, _ = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    # one online player with a recent observation + session
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 1000, 1200, 21, "g1", IdConfidence.HIGH))
    sid = await repo.insert_session(
        PlayerSession(None, WID, "pk1", 1000, 1200, None, 200, SessionStatus.ACTIVE, None)
    )
    await repo.insert_observation(
        PlayerObservation(1200, WID, "pk1", "Neo", 21, PingBucket.GOOD, 3, "g1", None, None)
    )
    dto = await q.status(_world())
    assert dto.world_day == 42
    assert dto.online == 2
    assert dto.basecamp_count == 5
    assert dto.smoothness_label == "流畅"
    assert dto.degraded is False
    assert ("Neo", 21, "good") in dto.players
    assert sid >= 1


async def test_status_degraded_when_no_metric(qs):
    repo, q, _ = qs
    dto = await q.status(_world())
    assert dto.degraded is True
    assert dto.online == 0


async def test_status_is_cached(qs):
    repo, q, clock = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    first = await q.status(_world())
    # mutate DB; cached result should be returned within TTL
    await repo.insert_metric(WorldMetric(WID, 1201, 20.0, 40.0, 9, 42, 5))
    second = await q.status(_world())
    assert second.online == first.online == 2
    # advance beyond TTL 15s -> fresh read
    clock.advance(16)
    third = await q.status(_world())
    assert third.online == 9


async def test_online_dto(qs):
    repo, q, _ = qs
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 1000, 1200, 21, "g1", IdConfidence.HIGH))
    await repo.insert_session(
        PlayerSession(None, WID, "pk1", 1000, 1200, None, 200, SessionStatus.ACTIVE, None)
    )
    await repo.insert_observation(
        PlayerObservation(1200, WID, "pk1", "Neo", 21, PingBucket.HIGH, 3, "g1", None, None)
    )
    dto = await q.online(_world())
    assert len(dto.rows) == 1
    assert dto.rows[0].name == "Neo"
    assert dto.rows[0].ping_bucket is PingBucket.HIGH
    assert dto.rows[0].online_seconds == 200
