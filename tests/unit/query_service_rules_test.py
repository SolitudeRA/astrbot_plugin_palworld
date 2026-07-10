from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, ActionCategory, UnitType
from palchronicle.domain.models import (
    CharacterActor, GameDataSnapshot, PalBoxActor, World, WorldMetric,
)
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


class _FakeMeta:
    def setting_label(self, field):
        return {"ExpRate": ("经验倍率", "x")}.get(field, (field, ""))

    def pal_name(self, cls):
        return cls


class _FakeReport:
    async def daily(self, world, day=None):
        return "DAILY_SENTINEL"


def _cfg(privacy_mode="balanced") -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig(privacy_mode, False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


def _char(unit: UnitType, pal="Lamball") -> CharacterActor:
    return CharacterActor(
        unit_type=unit, instance_id=None, nickname=None, trainer_instance_id=None,
        trainer_nickname=None, player_userid=None, level=5, hp=100, max_hp=100,
        guild_id="g1", guild_name="Noema", pal_class=pal, action=ActionCategory.IDLE,
        ai_action=ActionCategory.IDLE, x=None, y=None, z=None, is_active=True,
    )


async def _make(tmp_path, privacy_mode="balanced"):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    settings_cache = {"alpha": {"ExpRate": "1.5"}}
    world_cache = {
        "alpha": GameDataSnapshot(
            observed_at=1200, fps=58.0, average_fps=57.0,
            characters=[_char(UnitType.PLAYER), _char(UnitType.WILD, "Lamball"),
                        _char(UnitType.WILD, "Lamball"), _char(UnitType.NPC)],
            palboxes=[PalBoxActor("g1", "Noema", None, 1.0, 2.0, 3.0)],
            unknown_classes=[],
        )
    }
    q = QueryService(
        repo, TTLCache(clock), _cfg(privacy_mode), meta=_FakeMeta(), clock=clock,
        settings_cache=settings_cache, world_cache=world_cache, report=_FakeReport(),
    )
    return db, repo, q


async def test_rules_maps_settings_labels(tmp_path):
    db, repo, q = await _make(tmp_path)
    dto = await q.rules(_world())
    labels = {r.label: r.value for r in dto.rows}
    assert labels["经验倍率"] == "1.5x"
    assert dto.advanced_note is None
    await db.close()


async def test_rules_advanced_note(tmp_path):
    db, repo, q = await _make(tmp_path, privacy_mode="advanced")
    dto = await q.rules(_world())
    assert dto.advanced_note is not None
    assert "balanced" in dto.advanced_note
    await db.close()


async def test_world_summary_counts_unit_types(tmp_path):
    db, repo, q = await _make(tmp_path)
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.0, 1, 42, 5))
    dto = await q.world_summary(_world())
    assert dto.players == 1
    assert dto.wild == 2
    assert dto.npc == 1
    assert dto.palbox == 1
    assert dto.wild_top[0].name == "Lamball"
    assert dto.wild_top[0].count == 2
    await db.close()


async def test_today_delegates_to_report(tmp_path):
    db, repo, q = await _make(tmp_path)
    result = await q.today(_world())
    assert result == "DAILY_SENTINEL"
    await db.close()
