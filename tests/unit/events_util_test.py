from palchronicle.domain.enums import EventType
from palchronicle.domain.events import make_dedup_key


def test_make_dedup_key_uses_uppercase_type_and_pipe():
    key = make_dedup_key("s1:guid:0", EventType.NEW_PLAYER, "pk123")
    assert key == "s1:guid:0|NEW_PLAYER|pk123"


def test_make_dedup_key_multiple_parts_stringified():
    key = make_dedup_key("w", EventType.WORKER_DELTA, "base9", 3, "up")
    assert key == "w|WORKER_DELTA|base9|3|up"


def test_make_dedup_key_no_parts():
    key = make_dedup_key("w", EventType.ONLINE_RECORD)
    assert key == "w|ONLINE_RECORD"
