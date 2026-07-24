"""据点车间现场（spec §6）：base() 派生 slacker_rate（slacking 占 action_distribution 比例）
+ mood（由 slacker_rate 阈值派生的稳定键）+ species_top（Class→meta.pal_name，就近可见快照按
公会名聚合 BaseCampPal 物种）；format_base 出氛围徽章（🔥热火朝天/😴集体摆烂）+ 一句吐槽 +
摸鱼行（摸鱼率）+ 行为分布 emoji + C2「此刻可见 N 只」措辞。"""
from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.dtos import BaseDetailDTO
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import (
    AccessMode,
    ActionCategory,
    Confidence,
    UnitType,
)
from palworld_terminal.domain.models import (
    Base,
    BaseObservation,
    CharacterActor,
    GameDataSnapshot,
    Guild,
    World,
)
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.formatters import format_base

WID = "alpha:guid-1:0"
SRV = "alpha"


class _Meta:
    """物种名解析桩：识别皮皮鸡/羊球，其余优雅降级返原 class。"""

    def pal_name(self, cls):
        return {"BP_ChickenPal_C": "皮皮鸡", "BP_SheepBallPal_C": "羊球"}.get(cls, cls)


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
    return World(WID, SRV, "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


def _basecamp(guild_name: str, pal_class: str) -> CharacterActor:
    return CharacterActor(
        unit_type=UnitType.BASE_CAMP, instance_id=None, nickname=None,
        trainer_instance_id=None, trainer_nickname=None, player_userid=None,
        level=None, hp=None, max_hp=None, guild_id=None, guild_name=guild_name,
        pal_class=pal_class, action=ActionCategory.WORKING, ai_action=ActionCategory.WORKING,
        x=None, y=None, z=None, is_active=True,
    )


def _gd(*actors: CharacterActor) -> GameDataSnapshot:
    return GameDataSnapshot(observed_at=1200, fps=60.0, average_fps=60.0,
                            characters=list(actors), palboxes=[])


@pytest.fixture
async def env(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    yield repo, clock
    await db.close()


def _qs(repo, clock, *, world_cache=None, meta=None) -> QueryService:
    return QueryService(
        repo, TTLCache(clock), _cfg(), meta, clock, {},
        world_cache=world_cache if world_cache is not None else {},
    )


async def _base_with_obs(repo, dist: dict[str, int]) -> None:
    await repo.upsert_guild(Guild("g1", WID, "Matrix", 900, 1200, 4, 2, 10))
    await repo.upsert_base(
        Base("b1", WID, "pb1", "海岸木材场", "g1", Confidence.HIGH, False, False, 900, 1200)
    )
    total = sum(dist.values())
    active = dist.get("working", 0)
    await repo.insert_base_observation(
        BaseObservation("b1", WID, 1200, total, active, 17.5, 0.9, dist)
    )


# ---- ① slacker_rate：slacking 占 action_distribution 比例 ----

async def test_slacker_rate_derived_from_slacking_share(env):
    repo, clock = env
    await _base_with_obs(repo, {"working": 3, "slacking": 5, "idle": 2})  # 5/10
    dto = await _qs(repo, clock).base(_world(), "#1")
    assert dto is not None
    assert dto.slacker_rate == 0.5


async def test_slacker_rate_zero_when_no_slacking(env):
    repo, clock = env
    await _base_with_obs(repo, {"working": 8, "idle": 2})
    dto = await _qs(repo, clock).base(_world(), "#1")
    assert dto is not None
    assert dto.slacker_rate == 0.0


# ---- ② mood：由 slacker_rate 阈值派生（≥0.3 集体摆烂 / 否则热火朝天）----

async def test_mood_slacking_off_at_or_above_threshold(env):
    repo, clock = env
    await _base_with_obs(repo, {"working": 7, "slacking": 3})  # 0.3 → 阈值含边界
    dto = await _qs(repo, clock).base(_world(), "#1")
    assert dto is not None
    assert dto.mood == "slacking_off"


async def test_mood_fired_up_below_threshold(env):
    repo, clock = env
    await _base_with_obs(repo, {"working": 71, "slacking": 29})  # 0.29 → 热火朝天
    dto = await _qs(repo, clock).base(_world(), "#1")
    assert dto is not None
    assert dto.mood == "fired_up"


# ---- ③ species_top：Class→名（就近可见快照，按公会名过滤 BaseCampPal，降序 Top-N）----

async def test_species_top_from_snapshot_by_guild(env):
    repo, clock = env
    await _base_with_obs(repo, {"working": 5})
    gd = _gd(
        _basecamp("Matrix", "BP_ChickenPal_C"),
        _basecamp("Matrix", "BP_ChickenPal_C"),
        _basecamp("Matrix", "BP_ChickenPal_C"),
        _basecamp("Matrix", "BP_SheepBallPal_C"),
        _basecamp("Matrix", "BP_SheepBallPal_C"),
        _basecamp("OtherGuild", "BP_ChickenPal_C"),  # 他公会不计入
    )
    dto = await _qs(repo, clock, world_cache={SRV: gd}, meta=_Meta()).base(_world(), "#1")
    assert dto is not None
    assert dto.species_top == [("皮皮鸡", 3), ("羊球", 2)]


async def test_species_top_empty_without_snapshot(env):
    repo, clock = env
    await _base_with_obs(repo, {"working": 5})
    dto = await _qs(repo, clock).base(_world(), "#1")  # 无 world_cache → 无快照
    assert dto is not None
    assert dto.species_top == []


# ---- ④ format_base：氛围徽章 + 吐槽 + 摸鱼行 + 分布 emoji + C2「此刻可见」----

def _dto(*, mood="fired_up", slacker_rate=0.0, dist=None, species=None) -> BaseDetailDTO:
    return BaseDetailDTO(
        display_name="海岸木材场", guild_name="Matrix", confidence=Confidence.HIGH,
        worker_count=18, active_count=12, average_level=17.5, average_hp_ratio=0.92,
        action_distribution=dist if dist is not None else {"working": 8},
        health_score=90.0, available=True,
        mood=mood, slacker_rate=slacker_rate,
        species_top=species if species is not None else [],
    )


def test_format_base_badge_fired_up():
    text = format_base(_dto(mood="fired_up"))
    assert "🔥" in text
    assert "热火朝天" in text


def test_format_base_badge_slacking_off():
    text = format_base(_dto(
        mood="slacking_off", slacker_rate=0.5,
        dist={"working": 3, "slacking": 5, "idle": 2},
    ))
    assert "😴" in text
    assert "集体摆烂" in text


def test_format_base_slacker_line_shows_rate():
    text = format_base(_dto(
        mood="slacking_off", slacker_rate=0.5,
        dist={"working": 3, "slacking": 5, "idle": 2},
    ))
    assert "摸鱼率" in text
    assert "50%" in text


def test_format_base_action_distribution_uses_emoji():
    text = format_base(_dto(dist={"working": 8, "slacking": 5}))
    assert "⛏" in text   # 工作
    assert "🚬" in text   # 摸鱼


def test_format_base_c2_visible_now_wording():
    text = format_base(_dto())
    assert "此刻可见" in text
    assert "此刻可见 18 只" in text


def test_format_base_species_top_line():
    text = format_base(_dto(species=[("皮皮鸡", 3), ("羊球", 2)]))
    assert "皮皮鸡" in text
    assert "羊球" in text
