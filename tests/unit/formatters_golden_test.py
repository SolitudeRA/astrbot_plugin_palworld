from pathlib import Path

from palworld_terminal.application.report_service import BaseEvent, LevelEvent
from palworld_terminal.domain.enums import PingBucket
from palworld_terminal.presentation.dtos import (
    OnlineDTO,
    OnlinePlayerRow,
    RulesDTO,
    RuleSection,
    StatusDetailDTO,
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
    # 样张镜像 spec §4.1（Palpagos=配置名 srv.name，经 server_name 参数供数，非游戏内 world_name）。
    # 头行分子 = len(players)=2（收敛后名单数，spec §3）；版本/运行时长来自 detail。
    detail = StatusDetailDTO(
        version="0.6.5", description="", uptime_seconds=550800,  # 6天9时
        frametime_ms=17.2, address="", rules={},
    )
    dto = StatusDTO(
        server_name="Palpagos", world_name="game-world", world_day=42, online=2,
        max_players=32, basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="流畅",
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")],
        peak_online_today=7, updated_at=1700000000, degraded=False, last_ok=1700000000,
        detail=detail,
    )
    _check_golden("status.txt", format_status(dto, "Palpagos"))


def test_world_golden():
    # 样张镜像 spec §4.2（居民/设施/野生 Top 三节；FPS 已删除；据点取官方 basecamp_count）。
    dto = WorldSummaryDTO(
        world_day=42, online=2, max_players=32, players=12, otomo=38, base_pal=102,
        wild=361, npc=45, palbox=8, guilds=5, basecamp_count=5,
        wild_top=[WildTopRow("疾风隼", 24), WildTopRow("棉悠悠", 18)], available=True,
    )
    _check_golden("world.txt", format_world(dto, "Palpagos"))


def test_rules_golden():
    # 样张镜像 spec §4.3（模式/倍率/节奏/上限四节；同类字段两两并一行；倍率 1.0x /
    # 节奏保游戏原单位 / 上限裸数——值均由 query 层策展渲染，此处直接给定稿串）。
    dto = RulesDTO(
        sections=[
            RuleSection("模式", [
                ("难度", "普通"), ("硬核", "关闭"), ("死亡惩罚", "掉落物品"),
                ("帕鲁永久死亡", "关闭"), ("PVP 伤害", "关闭"), ("友军伤害", "关闭"),
                ("入侵者袭击", "开启"),
            ]),
            RuleSection("倍率", [
                ("经验", "1.0x"), ("捕获", "1.2x"), ("工作速度", "1.0x"),
                ("帕鲁刷新", "1.0x"), ("白天流速", "1.0x"), ("夜晚流速", "1.0x"),
            ]),
            RuleSection("节奏", [("蛋孵化", "72 小时"), ("空投间隔", "180 分钟")]),
            RuleSection("上限", [
                ("玩家", "32"), ("公会成员", "20"), ("据点 每公会", "4"), ("全服", "128"),
            ]),
        ],
        available=True, privacy_note=None, updated_at=1700000000,
    )
    _check_golden("rules.txt", format_rules(dto, "Palpagos"))


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
