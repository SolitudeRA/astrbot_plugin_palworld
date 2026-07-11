from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, Confidence, EventType
from palchronicle.domain.models import Base, BaseObservation, Guild, World, WorldEvent
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


async def test_guilds_dto(qs):
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    dtos = await q.guilds(_world())
    assert dtos[0].name == "Noema"
    assert dtos[0].palbox == 2


async def test_guild_detail_found(qs):
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    dto = await q.guild(_world(), "Noema")
    assert dto is not None
    assert dto.name == "Noema"
    assert dto.first_seen_at == 900
    assert dto.last_seen_at == 1200
    assert dto.observed_members == 4
    assert dto.palbox == 2
    assert dto.base_pals == 10
    # v0.1 degradation placeholders
    assert dto.active_today == 0
    assert dto.active_week == 0
    assert dto.average_level == 0.0
    assert dto.base_event_lines == []


async def test_guild_detail_not_found(qs):
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    assert await q.guild(_world(), "Ghost") is None


async def test_bases_have_stable_index(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("b2", WID, "pb2", "Noema-2", "g1", Confidence.MEDIUM, False, False, 900, 1200))
    dtos = await q.bases(_world())
    assert [d.index for d in dtos] == [1, 2]


async def test_base_by_index(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.insert_base_observation(
        BaseObservation("b1", WID, 1200, 8, 6, 17.5, 0.9, {"working": 6, "idle": 2})
    )
    dto = await q.base(_world(), "#1")
    assert dto is not None
    assert dto.display_name == "Noema-1"
    assert dto.worker_count == 8
    # activity_score = 100*(0.75*(6/8) + 0.25*(8/8)) = 100*(0.5625+0.25)=81.25
    assert abs(dto.activity_score - 81.25) < 0.01


async def test_base_by_name(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-2", "g1", Confidence.HIGH, False, False, 900, 1200))
    dto = await q.base(_world(), "Noema-2")
    assert dto is not None
    assert dto.display_name == "Noema-2"


async def test_base_missing_returns_none(qs):
    repo, q, _ = qs
    assert await q.base(_world(), "#9") is None
    assert await q.base(_world(), "Ghost") is None


async def test_events_today_only_filters(qs):
    repo, q, clock = qs
    old = clock.now() - 100000
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "p1", old, old, {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p1"))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "p2", 1200, 1200, {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p2"))
    all_events = await q.events(_world(), today_only=False)
    assert len(all_events) == 2
    today = await q.events(_world(), today_only=True)
    assert len(today) == 1
    assert today[0].event_type == "new_player"
