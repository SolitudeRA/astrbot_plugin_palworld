"""八类世界事件措辞单一真相源（spec §4.4）。

events（T6）/ today（T7）/ guild info 近期动态（T10）三处共用本表——此处逐类锁定
精确措辞，任一处改词即在此红，杜绝多源漂移。
"""
from palworld_terminal.domain.enums import Confidence, EventType
from palworld_terminal.domain.models import WorldEvent
from palworld_terminal.presentation.event_wording import event_wording


def _ev(et, payload, subject_type="world", subject_key="k"):
    return WorldEvent(
        None, "w", et, subject_type, subject_key, 1000, 1000,
        payload, "public", Confidence.HIGH, "d",
    )


def test_player_level_up():
    e = _ev(EventType.PLAYER_LEVEL_UP, {"old": 21, "new": 22}, "player", "pk")
    assert event_wording(e, "Neo") == "Neo 升级 Lv21→Lv22"


def test_new_player():
    e = _ev(EventType.NEW_PLAYER, {}, "player", "pk")
    assert event_wording(e, "Trinity") == "新玩家 Trinity 加入世界"


def test_new_guild():
    e = _ev(EventType.NEW_GUILD, {}, "guild", "gk")
    assert event_wording(e, "Matrix") == "新公会「Matrix」出现"


def test_new_base():
    e = _ev(EventType.NEW_BASE, {}, "base", "bk")
    assert event_wording(e, "海岸木材场") == "新据点「海岸木材场」确认"


def test_base_vanished_carries_own_uncertainty():
    e = _ev(EventType.BASE_VANISHED, {"first_missing_day": 42}, "base", "bk")
    # 「疑似消失」自带不确定性，不另加（推导）标（spec §4.4）
    assert event_wording(e, "海岸木材场") == "据点「海岸木材场」疑似消失（连续多次未观察到）"
    assert "（推导）" not in event_wording(e, "海岸木材场")


def test_worker_delta():
    e = _ev(EventType.WORKER_DELTA, {"prev": 12, "cur": 18}, "base", "bk")
    assert event_wording(e, "海岸木材场") == "据点「海岸木材场」工作帕鲁 12→18"


def test_world_day_milestone():
    e = _ev(EventType.WORLD_DAY_MILESTONE, {"milestone": 100, "day": 100})
    assert event_wording(e, "") == "世界迎来第 100 天"


def test_online_record():
    e = _ev(EventType.ONLINE_RECORD, {"value": 8})
    assert event_wording(e, "") == "在线人数新纪录 8 人"
