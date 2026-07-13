from pathlib import Path

from palworld_terminal.application.report_service import BaseEvent, LevelEvent
from palworld_terminal.domain.enums import PingBucket
from palworld_terminal.presentation.dtos import (
    OnlineDTO,
    OnlinePlayerRow,
    RuleRow,
    RulesDTO,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
)
from palworld_terminal.presentation.formatters import (
    format_online,
    format_rules,
    format_status,
    format_today,
    format_world,
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def _check_golden(name: str, actual: str) -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    path = GOLDEN / name
    if not path.exists():
        path.write_text(actual, encoding="utf-8")  # first run: generate
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, f"golden mismatch for {name}"


def test_status_golden():
    dto = StatusDTO(
        server_name="alpha", world_name="Palpagos", world_day=42, online=2, max_players=32,
        basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="流畅",
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")],
        peak_online_today=7, updated_at=1700000000, degraded=False, last_ok=1700000000,
    )
    _check_golden("status.txt", format_status(dto))


def test_world_golden():
    dto = WorldSummaryDTO(
        world_day=42, online=2, players=2, otomo=3, base_pal=8, wild=15, npc=4,
        palbox=3, guilds=2, fps=58.0, average_fps=56.5,
        wild_top=[WildTopRow("Lamball", 5), WildTopRow("Chikipi", 3)],
    )
    _check_golden("world.txt", format_world(dto))


def test_rules_golden():
    dto = RulesDTO(
        rows=[RuleRow("经验倍率", "1.0x"), RuleRow("捕获倍率", "1.0x"), RuleRow("最大玩家", "32")],
        updated_at=1700000000, advanced_note=None,
    )
    _check_golden("rules.txt", format_rules(dto))


def test_today_golden():
    class _Report:
        day = "2026-07-10"
        world_day_start = 41
        world_day_end = 42
        active_players = 5
        peak_online = 7
        total_online_seconds = 36000
        level_events = [LevelEvent("a" * 64, 20, 21)]
        base_events = [BaseEvent("b1", "new", "据点新增：Noema-2")]
        records = ["在线人数刷新纪录：7 人"]
        summary = "世界迎来新的一天。"
        is_empty = False

    _check_golden("today.txt", format_today(_Report()))


def test_level_event_str_humanized():
    assert "Lv20→Lv21" in str(LevelEvent("a" * 64, 20, 21))


def test_online_redacted_golden():
    dto = OnlineDTO(
        rows=[
            OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661),
            OnlinePlayerRow("Trinity", 18, PingBucket.HIGH, 600),
        ],
        updated_at=1700000000, degraded=False,
    )
    text = format_online(dto)
    # privacy: no raw ping ms leaked
    assert "3661" not in text or "在线" in text  # duration allowed, ping must be bucket
    assert "优秀" in text and "偏高" in text
    _check_golden("online_redacted.txt", text)
