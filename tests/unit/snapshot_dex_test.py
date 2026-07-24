"""ingest_game_data 采集图鉴地基（spec §4.4）：消费已脱敏 gd、仅真帕鲁物种入库、
first_seen_name 只取明文名永不回退 id、strict 下仍只记物种/明文名。"""
from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.snapshot_service import SnapshotService
from palworld_terminal.domain import privacy as _privacy_mod
from palworld_terminal.domain.enums import AccessMode, ActionCategory, UnitType
from palworld_terminal.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    PalBoxActor,
    World,
)
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

# 任何 id/GUID/steamid 形——first_seen_name 绝不可命中其一（该表不 prune，回退 = 永久泄漏）
_ID_STRINGS = {"steam_00001", "INST-P1", "INST-O1", "INST-B1", "INST-W1"}


class _FakeMeta:
    _NAMES = {
        "BP_ChickenPal_C": "鸡", "BP_LambPal_C": "绵羊", "BP_FoxPal_C": "狐",
        "BP_Player_Female_C": "玩家", "BP_NPC_Merchant_C": "商人",
    }
    _ELEM = {
        "BP_ChickenPal_C": "grass", "BP_LambPal_C": "neutral", "BP_FoxPal_C": "fire",
    }

    def pal_name(self, cls):
        return self._NAMES.get(cls, cls)

    def element(self, cls):
        return self._ELEM.get(cls, "unknown")


class _FakeGuilds:
    async def apply(self, world, gd):
        return []


class _FakeBases:
    async def apply(self, world, gd):
        return []


def _make_normalizer(snap):
    class _N:
        @staticmethod
        def normalize_game_data(raw, now, meta):
            return snap
    return _N


def _char(unit_type, instance_id, nickname, trainer_nickname, player_userid, pal_class):
    return CharacterActor(
        unit_type=unit_type, instance_id=instance_id, nickname=nickname,
        trainer_instance_id=None, trainer_nickname=trainer_nickname,
        player_userid=player_userid, level=10, hp=80, max_hp=100,
        guild_id="g1", guild_name="Noema", pal_class=pal_class,
        action=ActionCategory.WORKING, ai_action=ActionCategory.WORKING,
        x=1.0, y=2.0, z=3.0, is_active=True,
    )


def _snapshot():
    # Player / NPC（排除）+ OtomoPal / BaseCampPal / WildPal（收录）+ PalBox（另桶，天然排除）
    chars = [
        _char(UnitType.PLAYER, "INST-P1", "Akari", None, "steam_00001", "BP_Player_Female_C"),
        _char(UnitType.NPC, "INST-N1", "Merchant", None, None, "BP_NPC_Merchant_C"),
        _char(UnitType.OTOMO, "INST-O1", "小鸡", "Akari", None, "BP_ChickenPal_C"),
        _char(UnitType.BASE_CAMP, "INST-B1", "打工鸡", None, None, "BP_LambPal_C"),
        # 无明文名（nickname/trainer_nickname 皆空）→ first_seen_name 须 NULL，绝不回退 INST-W1
        _char(UnitType.WILD, "INST-W1", None, None, None, "BP_FoxPal_C"),
    ]
    boxes = [PalBoxActor("g1", "Noema", "BP_BuildObject_PalBoxV2_C", 1.0, 2.0, 3.0)]
    return GameDataSnapshot(5000, 60.0, 60.0, chars, boxes, [])


def _cfg(mode="balanced"):
    from palworld_terminal.config import (
        AppConfig,
        BasesConfig,
        HistoryConfig,
        PollingConfig,
        PrivacyConfig,
        RoutingConfig,
        WorldConfig,
    )
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig(mode, False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


def _world():
    return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


async def _ingest(tmp_path, snap, mode="balanced"):
    db = Database(tmp_path / "d.db"); await db.open(); await apply_migrations(db)
    repo = Repository(db, FakeClock(5000))
    svc = SnapshotService(
        repo=repo, normalizer_mod=_make_normalizer(snap), privacy_mod=_privacy_mod,
        meta=_FakeMeta(), salt=b"0" * 32, cfg=_cfg(mode), clock=FakeClock(5000),
        players=None, guilds=_FakeGuilds(), bases=_FakeBases(), events=None,
    )
    await svc.ingest_game_data(_world(), RestResponse(True, 200, {"any": []}, 1, 2, None))
    rows = await repo.observed_species()
    await db.close()
    return {r.species_class: r for r in rows}


async def test_only_pal_unit_types_recorded(tmp_path):
    by_class = await _ingest(tmp_path, _snapshot())
    # 只含 3 类帕鲁物种；无 Player/NPC/PalBox 的 BP_*
    assert set(by_class) == {"BP_ChickenPal_C", "BP_LambPal_C", "BP_FoxPal_C"}
    assert all(r.observe_count == 1 for r in by_class.values())
    assert all(r.first_seen_at == 5000 for r in by_class.values())
    assert by_class["BP_ChickenPal_C"].species_name == "鸡"
    assert by_class["BP_ChickenPal_C"].element == "grass"


async def test_first_seen_name_only_plaintext_never_id(tmp_path):
    by_class = await _ingest(tmp_path, _snapshot())
    assert by_class["BP_ChickenPal_C"].first_seen_name == "小鸡"     # NickName 明文
    assert by_class["BP_LambPal_C"].first_seen_name == "打工鸡"      # NickName 明文
    assert by_class["BP_FoxPal_C"].first_seen_name is None          # 无明文名 → NULL，不回退 id
    names = {r.first_seen_name for r in by_class.values()}
    assert names & _ID_STRINGS == set()                            # 绝不含任何 id/GUID


async def test_strict_still_records_species_and_plaintext_name(tmp_path):
    by_class = await _ingest(tmp_path, _snapshot(), mode="strict")
    assert set(by_class) == {"BP_ChickenPal_C", "BP_LambPal_C", "BP_FoxPal_C"}
    assert by_class["BP_ChickenPal_C"].first_seen_name == "小鸡"
    names = {r.first_seen_name for r in by_class.values()}
    assert names & _ID_STRINGS == set()
