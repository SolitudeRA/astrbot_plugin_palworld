from palchronicle.domain.enums import EventType
from palchronicle.domain.events import (
    level_up_payload,
    make_dedup_key,
    worker_delta_payload,
)


def test_make_dedup_key_uses_uppercase_type_and_pipe():
    key = make_dedup_key("s1:guid:0", EventType.NEW_PLAYER, "pk123")
    assert key == "s1:guid:0|NEW_PLAYER|pk123"


def test_make_dedup_key_multiple_parts_stringified():
    key = make_dedup_key("w", EventType.WORKER_DELTA, "base9", 3, "up")
    assert key == "w|WORKER_DELTA|base9|3|up"


def test_make_dedup_key_no_parts():
    key = make_dedup_key("w", EventType.ONLINE_RECORD)
    assert key == "w|ONLINE_RECORD"


def test_level_up_payload():
    assert level_up_payload(4, 7) == {"old_level": 4, "new_level": 7}


def test_worker_delta_payload():
    assert worker_delta_payload("b1", 10, 15) == {
        "base_key": "b1",
        "baseline": 10,
        "current": 15,
        "delta": 5,
    }
