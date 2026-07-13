from palworld_terminal.application.base_service import BaseService, BaseUpdate
from palworld_terminal.domain.enums import Confidence


def test_palbox_key_format():
    assert BaseService.palbox_key("w1", "gk", "10:20:0") == "w1|gk|10:20:0"


def test_base_key_deterministic_from_anchor():
    pbk = BaseService.palbox_key("w1", "gk", "10:20:0")
    assert BaseService.base_key("w1", pbk) == "w1|BASE|w1|gk|10:20:0"


def test_base_update_fields():
    u = BaseUpdate(
        base_key="bk", world_id="w1", palbox_key="pbk", guild_key="gk",
        confidence=Confidence.HIGH, worker_count=6, active_count=4,
        average_level=12.0, average_hp_ratio=0.9,
        action_distribution={"working": 4}, is_new=True, is_vanished=False,
        prev_worker_count=None,
    )
    assert u.confidence == Confidence.HIGH
    assert u.is_new and not u.is_vanished
    assert u.prev_worker_count is None
