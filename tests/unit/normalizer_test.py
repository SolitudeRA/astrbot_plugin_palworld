import pytest

from palworld_terminal.adapters.normalizer import (
    ci_get,
    normalize_info,
    normalize_metrics,
    str_bool,
)


def test_ci_get_case_insensitive():
    d = {"WorldGuid": "abc", "Version": "0.1"}
    assert ci_get(d, "worldguid") == "abc"
    assert ci_get(d, "VERSION") == "0.1"


def test_ci_get_multiple_keys_first_hit():
    d = {"currentplayernum": 5}
    assert ci_get(d, "CurrentPlayerNum", "online", default=0) == 5


def test_ci_get_default_when_missing():
    assert ci_get({}, "nope", default=-1) == -1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("TRUE", True), ("1", True),
        (1, True), (True, True),
        ("false", False), ("False", False), ("0", False), (0, False),
        (False, False), (None, False), ("", False),
    ],
)
def test_str_bool(raw, expected):
    assert str_bool(raw) is expected


def test_normalize_info_mixed_case_and_missing():
    raw = {"Version": "0.3.1", "ServerName": "My World", "WorldGuid": "GUID123"}
    snap = normalize_info(raw, now=1000)
    assert snap.observed_at == 1000
    assert snap.version == "0.3.1"
    assert snap.server_name == "My World"
    assert snap.worldguid == "GUID123"
    assert snap.description == ""  # 缺失字段宽容


def test_normalize_metrics_mixed_case_and_types():
    raw = {
        "ServerFps": 58, "ServerFrameTime": "17.2", "CurrentPlayerNum": "4",
        "MaxPlayerNum": 32, "Uptime": 3600, "Days": 12, "BaseCampNum": 7,
    }
    snap = normalize_metrics(raw, now=2000)
    assert snap.observed_at == 2000
    assert snap.fps == 58.0
    assert snap.frame_time == 17.2
    assert snap.online == 4
    assert snap.max_players == 32
    assert snap.uptime == 3600
    assert snap.days == 12
    assert snap.basecamp_count == 7


def test_normalize_metrics_missing_fields_default_zero():
    snap = normalize_metrics({}, now=3000)
    assert snap.fps == 0.0
    assert snap.online == 0
    assert snap.basecamp_count == 0
    assert snap.days == 0
