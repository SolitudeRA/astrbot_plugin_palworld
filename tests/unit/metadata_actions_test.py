"""真实 game-data 动作 token → ActionCategory 覆盖（含新增 SLACKING 摸鱼类）。

真服探测所得 token 是 BP_Action*/BP_AIAction*，与旧 EPal* 键并存（旧键防御回退不删）。
归类口径见 spec §4.3（钉死）。"""
from pathlib import Path

from palworld_terminal.adapters.metadata_repository import MetadataRepository
from palworld_terminal.domain.enums import ActionCategory

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _repo() -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR)
    repo.load()
    return repo


def test_slacking_category_member_exists():
    assert ActionCategory.SLACKING == "slacking"


def test_real_working_tokens_map_to_working():
    repo = _repo()
    for tok in (
        "BP_AIAction_Worker_Working",
        "BP_ActionMining",
        "BP_ActionHarvesting",
        "BP_ActionDeforest",
        "BP_ActionFeeding",
        "BP_ActionGenerateEnergy_Electric",
        "BP_ActionCool",
    ):
        assert repo.action_category(tok) is ActionCategory.WORKING, tok


def test_real_slacking_tokens_map_to_slacking():
    repo = _repo()
    for tok in (
        "BP_ActionIdleInSpa",
        "BP_AIActionBaseCamp_InSpa",
        "InSpa",
        "BP_AIAction_BaseCamp_DodgeWork",
        "DodgeWork",
    ):
        assert repo.action_category(tok) is ActionCategory.SLACKING, tok


def test_real_idle_tokens_map_to_idle():
    repo = _repo()
    for tok in (
        "BP_ActionDefenseWait_Wait",
        "BP_ActionRandomRest_BaseCamp",
        "BP_AIAction_BaseCampWorker_Wait",
        "BP_AIAction_Work_WaitForWorkable",
    ):
        assert repo.action_category(tok) is ActionCategory.IDLE, tok


def test_real_moving_tokens_map_to_moving():
    repo = _repo()
    for tok in (
        "BP_AIAction_BaseCampWorker_Approach",
        "BP_AIAction_WanderingCage",
        "BP_AIAction_WildLife_Wandering",
    ):
        assert repo.action_category(tok) is ActionCategory.MOVING, tok


def test_legacy_epal_tokens_retained_for_defensive_fallback():
    repo = _repo()
    assert repo.action_category("EPalActionType::Work") is ActionCategory.WORKING
    assert repo.action_category("Work") is ActionCategory.WORKING
    assert repo.action_category("EPalWorkType::Cool") is ActionCategory.WORKING


def test_unknown_action_degrades_to_unknown():
    repo = _repo()
    assert repo.action_category("BP_ActionNeverHeardOf") is ActionCategory.UNKNOWN
    assert repo.action_category(None) is ActionCategory.UNKNOWN
