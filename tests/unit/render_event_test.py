from palworld_terminal.application.dtos import EventView
from palworld_terminal.domain.enums import EventType
from palworld_terminal.presentation.event_wording import render_event


def test_level_up():
    v = EventView(occurred_at=1, event_type=EventType.PLAYER_LEVEL_UP, name="Neo", old=9, new=12)
    assert render_event(v) == "Neo 升级 Lv9→Lv12"


def test_level_up_missing_defaults_to_question():
    v = EventView(occurred_at=1, event_type=EventType.PLAYER_LEVEL_UP, name="Neo")
    assert render_event(v) == "Neo 升级 Lv?→Lv?"


def test_new_player():
    v = EventView(occurred_at=1, event_type=EventType.NEW_PLAYER, name="Neo")
    assert render_event(v) == "新玩家 Neo 加入世界"


def test_new_guild():
    v = EventView(occurred_at=1, event_type=EventType.NEW_GUILD, name="曙光")
    assert render_event(v) == "新公会「曙光」出现"


def test_new_base():
    v = EventView(occurred_at=1, event_type=EventType.NEW_BASE, name="河谷矿场")
    assert render_event(v) == "新据点「河谷矿场」确认"


def test_base_vanished():
    v = EventView(occurred_at=1, event_type=EventType.BASE_VANISHED, name="河谷矿场")
    assert render_event(v) == "据点「河谷矿场」疑似消失（连续多次未观察到）"


def test_worker_delta():
    v = EventView(occurred_at=1, event_type=EventType.WORKER_DELTA, name="河谷矿场", prev=2, cur=5)
    assert render_event(v) == "据点「河谷矿场」工作帕鲁 2→5"


def test_world_day_milestone():
    v = EventView(occurred_at=1, event_type=EventType.WORLD_DAY_MILESTONE, milestone=5, name="")
    assert render_event(v) == "世界迎来第 5 天"


def test_online_record():
    v = EventView(occurred_at=1, event_type=EventType.ONLINE_RECORD, value=17, name="")
    assert render_event(v) == "在线人数新纪录 17 人"
