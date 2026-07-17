from palworld_terminal.adapters.sqlite_repository import Repository
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
from palworld_terminal.domain.enums import AccessMode, ActionCategory, UnitType
from palworld_terminal.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    PalBoxActor,
    World,
    WorldMetric,
)
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


class _FakeMeta:
    _ENUMS = {"DeathPenalty": {"Item": "掉落物品", "ItemAndEquipment": "掉落物品与装备"}}

    def setting_label(self, field):
        return {"ExpRate": ("经验倍率", "x")}.get(field, (field, ""))

    def setting_display(self, field, value):
        enum = self._ENUMS.get(field)
        if enum is not None:
            return enum.get(str(value), str(value))
        _label, unit = self.setting_label(field)
        return f"{value}{unit}"

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


def _rule_items(dto) -> dict[str, str]:
    return {label: value for sec in dto.sections for label, value in sec.items}


async def test_rules_curates_rate_field(tmp_path):
    # 策展分节（spec §4.3）：ExpRate 落 倍率 节，值渲染为 1.5x（ASCII x，非全角 ×）。
    db, repo, q = await _make(tmp_path)
    dto = await q.rules(_world())
    assert dto.available is True
    assert _rule_items(dto)["经验"] == "1.5x"
    assert dto.privacy_note is None
    await db.close()


async def test_rules_rate_whole_number_keeps_one_decimal(tmp_path):
    # Finding 3（spec §2.4/§4.3）：倍率恒一位小数——默认 1.0 必须渲染 1.0x（非去尾成 1x），
    # 默认服全倍率=1.0 属最常见场景。锚定真渲染路径（golden 用预渲染 DTO 测不出本回归）。
    db, repo, q = await _make(tmp_path)
    q._settings_cache["alpha"] = {"ExpRate": "1.000000"}
    dto = await q.rules(_world())
    assert _rule_items(dto)["经验"] == "1.0x"
    await db.close()


async def test_rules_maps_enum_values_via_setting_display(tmp_path):
    # 枚举字段走 setting_display（enum_map 措辞，不直出 "ItemAndEquipment"）。
    db, repo, q = await _make(tmp_path)
    q._settings_cache["alpha"] = {"DeathPenalty": "ItemAndEquipment"}
    dto = await q.rules(_world())
    assert _rule_items(dto)["死亡惩罚"] == "掉落物品与装备"
    await db.close()


async def test_rules_unavailable_when_snapshot_empty(tmp_path):
    # 取数失败态（spec §4.3/§9）：settings 快照未获取 → available=False（formatter 走 ⚠️）。
    db, repo, q = await _make(tmp_path)
    q._settings_cache.clear()
    dto = await q.rules(_world())
    assert dto.available is False
    assert dto.sections == []
    await db.close()


async def test_rules_advanced_note(tmp_path):
    db, repo, q = await _make(tmp_path, privacy_mode="advanced")
    dto = await q.rules(_world())
    assert dto.privacy_note == "advanced 隐私模式暂按 balanced 生效"
    await db.close()


async def test_rules_strict_note_diverges(tmp_path):
    # 两模式两句分叉（spec §4.3，勿混）：strict = 据点模块停用句。
    db, repo, q = await _make(tmp_path, privacy_mode="strict")
    dto = await q.rules(_world())
    assert dto.privacy_note == "据点模块在 strict 隐私模式下停用"
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
