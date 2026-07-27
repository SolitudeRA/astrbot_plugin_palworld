from pathlib import Path

from palworld_terminal.application.dtos import (
    EventView,
    OnlineDTO,
    OnlinePlayerRow,
    RulesDTO,
    RuleSection,
    StatusDetailDTO,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
)
from palworld_terminal.domain.enums import EventType, PingBucket
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
        max_players=32, basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="smooth",
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
    # 节奏保游戏原单位 / 上限裸数）。i18n §3.2：DTO 携 (节标题稳定键, (标签稳定键, 值, kind))
    # ——节标题/标签/单位词/倍率 x 由 formatter 经 L() 渲染；enum 值为 setting_display 成品，
    # 数值类携原始数值串（rate 一位小数、hours/minutes/int 去尾）。golden 字节不变锁 zh 渲染。
    dto = RulesDTO(
        sections=[
            RuleSection("rules_section_mode", [
                ("rules_label_difficulty", "普通", "enum"),
                ("rules_label_hardcore", "关闭", "enum"),
                ("rules_label_death_penalty", "掉落物品", "enum"),
                ("rules_label_pal_lost", "关闭", "enum"),
                ("rules_label_pvp_damage", "关闭", "enum"),
                ("rules_label_friendly_fire", "关闭", "enum"),
                ("rules_label_invader", "开启", "enum"),
            ]),
            RuleSection("rules_section_rate", [
                ("rules_label_exp", "1.0", "rate"),
                ("rules_label_capture", "1.2", "rate"),
                ("rules_label_work_speed", "1.0", "rate"),
                ("rules_label_pal_spawn", "1.0", "rate"),
                ("rules_label_day_speed", "1.0", "rate"),
                ("rules_label_night_speed", "1.0", "rate"),
            ]),
            RuleSection("rules_section_tempo", [
                ("rules_label_egg_hatch", "72", "hours"),
                ("rules_label_supply_drop", "180", "minutes"),
            ]),
            RuleSection("rules_section_cap", [
                ("rules_label_player_max", "32", "int"),
                ("rules_label_guild_member_max", "20", "int"),
                ("rules_label_basecamp_per_guild", "4", "int"),
                ("rules_label_basecamp_total", "128", "int"),
            ]),
        ],
        available=True, privacy_note=None, updated_at=1700000000,
    )
    _check_golden("rules.txt", format_rules(dto, "Palpagos"))


def test_today_golden():
    # 样张镜像 spec §4.5（三节：今日纪录/玩家成长/据点变化）。三节现为 EventView 列
    # （ReportService 经 event_view 构造），措辞由 render_event 逐字复现旧串；累计在线
    # 12时40分=45600s / fmt_duration。golden today.txt 字节不变即锁定 render_event 复现保真。
    class _Report:
        day = "2026-07-17"
        is_empty = False
        world_day_start = 42
        world_day_end = 45
        active_players = 3
        peak_online = 7
        total_online_seconds = 45600  # 12时40分
        records = [
            EventView(occurred_at=0, event_type=EventType.WORLD_DAY_MILESTONE, name="", milestone=100),
            EventView(occurred_at=0, event_type=EventType.ONLINE_RECORD, name="", value=8),
            EventView(occurred_at=0, event_type=EventType.NEW_PLAYER, name="Trinity"),
            EventView(occurred_at=0, event_type=EventType.NEW_GUILD, name="Matrix"),
        ]
        growth = [
            EventView(occurred_at=0, event_type=EventType.PLAYER_LEVEL_UP, name="Neo", old=21, new=22),
            EventView(occurred_at=0, event_type=EventType.PLAYER_LEVEL_UP, name="Trinity", old=17, new=18),
        ]
        base_changes = [
            EventView(occurred_at=0, event_type=EventType.NEW_BASE, name="海岸木材场"),
            EventView(occurred_at=0, event_type=EventType.WORKER_DELTA, name="河谷矿场", prev=12, cur=18),
        ]
        # i18n §3.2：DTO 携稳定键 + 计数（措辞拼装移入 format_today）。
        summary_kind = "editorial"
        new_players = 1

    _check_golden("today.txt", format_today(_Report(), "Palpagos"))


def test_online_redacted_golden():
    # 样张镜像 spec §4.24（Palpagos=配置名 srv.name，经 server_name 参数供数）。
    # 头行分子=len(rows)=2（收敛后名单数，T3 seam）；/32 容量=max_players、今日峰值=peak_online；
    # Ping 恒渲染为语义档位（优秀/偏高），绝不泄漏 raw ms；时长走 fmt_duration。
    dto = OnlineDTO(
        rows=[
            OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661),
            OnlinePlayerRow("Trinity", 18, PingBucket.HIGH, 600),
        ],
        updated_at=1700000000, degraded=False, max_players=32, peak_online=7,
    )
    text = format_online(dto, "Palpagos")
    # privacy/format: raw online_seconds (3661) must render via fmt_duration, never dumped raw.
    assert "3661" not in text
    assert "优秀" in text and "偏高" in text
    _check_golden("online_redacted.txt", text)
