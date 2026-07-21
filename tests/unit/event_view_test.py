from palworld_terminal.application.dtos import EventView, event_view
from palworld_terminal.domain.enums import Confidence, EventType
from palworld_terminal.domain.models import WorldEvent


def _ev(event_type, payload, *, subject_type="world", subject_key="w", occurred_at=100):
    return WorldEvent(
        event_id=None,
        world_id="s1:w",
        event_type=event_type,
        subject_type=subject_type,
        subject_key=subject_key,
        occurred_at=occurred_at,
        confirmed_at=occurred_at,
        payload=payload,
        visibility="public",
        confidence=Confidence.HIGH,
        dedup_key="d",
    )


def test_level_up_extracts_old_new_only():
    v = event_view(_ev(EventType.PLAYER_LEVEL_UP, {"old": 9, "new": 12},
                       subject_type="player", subject_key="p1"), "Neo")
    assert isinstance(v, EventView)
    assert v.event_type is EventType.PLAYER_LEVEL_UP
    assert v.name == "Neo"
    assert (v.old, v.new) == (9, 12)
    assert v.prev is v.cur is v.milestone is v.value is None


def test_new_base_never_exposes_internal_keys():
    # NEW_BASE.payload 有 guild_key/worker_count/confidence——绝不进 EventView（§6.1 隐私）
    v = event_view(_ev(EventType.NEW_BASE,
                       {"guild_key": "G#7", "worker_count": 4, "confidence": "high"},
                       subject_type="base", subject_key="b1"), "河谷矿场")
    assert v.name == "河谷矿场"
    assert v.old is v.new is v.prev is v.cur is v.milestone is v.value is None
    # EventView 无任何字段承载 guild_key/worker_count/confidence
    assert not hasattr(v, "guild_key")


def test_milestone_extracts_milestone_not_day():
    v = event_view(_ev(EventType.WORLD_DAY_MILESTONE, {"milestone": 5, "day": 5}), "")
    assert v.milestone == 5
    assert v.value is None  # 'day' 不进任何字段


def test_online_record_extracts_value():
    v = event_view(_ev(EventType.ONLINE_RECORD, {"value": 17}), "")
    assert v.value == 17


def test_worker_delta_extracts_prev_cur():
    v = event_view(_ev(EventType.WORKER_DELTA, {"prev": 2, "cur": 5},
                       subject_type="base", subject_key="b1"), "河谷矿场")
    assert (v.prev, v.cur) == (2, 5)


def test_event_view_carries_no_subject_fields():
    v = event_view(_ev(EventType.NEW_PLAYER, {}, subject_type="player", subject_key="p1"), "Neo")
    assert not hasattr(v, "subject_key")
    assert not hasattr(v, "subject_type")
