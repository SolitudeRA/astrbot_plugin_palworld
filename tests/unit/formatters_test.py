from palworld_terminal.config import SkippedServer
from palworld_terminal.domain.enums import Confidence, PingBucket
from palworld_terminal.presentation.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventDTO,
    GuildDetailDTO,
    GuildDTO,
    OnlineDTO,
    OnlinePlayerRow,
    ServerStatusRow,
    StatusDTO,
)
from palworld_terminal.presentation.formatters import (
    format_base,
    format_bases,
    format_degraded,
    format_events,
    format_guild,
    format_guilds,
    format_help,
    format_online,
    format_servers,
    format_status,
)


def test_format_degraded_shows_minutes_not_shutdown():
    text = format_degraded(last_ok=1000, now=1000 + 300)
    assert "5" in text
    assert "关机" not in text


def test_format_degraded_never_ok():
    text = format_degraded(last_ok=None, now=1000)
    assert "无法获取" in text


def test_format_status_takes_only_dto():
    # fps 分档（smoothness_label）由应用层依据 WorldConfig 计算并放入 DTO，
    # formatter 不再接收 config —— 签名为 format_status(dto)。
    dto = StatusDTO(
        server_name="alpha", world_name="Palpagos", world_day=42, online=2, max_players=32,
        basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="流畅",
        players=[("Neo", 21, "good")],
        peak_online_today=7, updated_at=1700000000, degraded=False, last_ok=1700000000,
    )
    text = format_status(dto)
    assert "Palpagos" in text
    assert "流畅" in text
    assert "Neo" in text


def test_format_online_lists_players_and_bucket_label():
    dto = OnlineDTO(
        rows=[OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661)], updated_at=1000, degraded=False
    )
    text = format_online(dto)
    assert "Neo" in text
    assert "21" in text
    # ping bucket rendered as a friendly label, never a raw ms number
    assert "优秀" in text


def test_format_online_empty():
    text = format_online(OnlineDTO(rows=[], updated_at=1000, degraded=False))
    assert "当前无玩家在线" in text


def test_format_bases_folds_low_confidence_note():
    dtos = [BaseDTO(1, "Noema-1", "Noema", Confidence.HIGH, 8)]
    text = format_bases(dtos)
    assert "Noema-1" in text
    assert "#1" in text


def test_format_bases_empty():
    assert "暂无" in format_bases([])


def test_format_base_marks_derived():
    dto = BaseDetailDTO("Noema-1", "Noema", Confidence.HIGH, 1, 8, 6, 17.5, 0.9,
                        {"working": 6, "idle": 2}, 81.25, 90.0)
    text = format_base(dto)
    assert "插件推导" in text
    assert "Noema-1" in text


def test_format_guilds_and_guild():
    gs = format_guilds([GuildDTO("Noema", 4, 2, 10, 3)])
    assert "Noema" in gs
    gd = format_guild(GuildDetailDTO("Noema", 1, 2, 4, 2, 3, 2, 10, 15.0, ["据点新增：Noema-2"]))
    assert "Noema" in gd
    assert "据点新增" in gd


def test_format_events_and_empty():
    text = format_events([EventDTO(1000, "new_player", "新玩家加入世界")])
    assert "新玩家加入世界" in text
    assert "暂无" in format_events([])


def test_format_servers_admin_shows_skipped_section():
    rows = [ServerStatusRow("alpha", True, True, True, True)]
    skipped = [SkippedServer(raw_name="dup", reason="duplicate")]
    admin_text = format_servers(rows, skipped, is_admin=True)
    assert "alpha" in admin_text
    assert "被跳过" in admin_text
    guest_text = format_servers(rows, skipped, is_admin=False)
    assert "被跳过" not in guest_text


def test_format_help_role_separation():
    from palworld_terminal.config import FeaturesConfig
    feats = FeaturesConfig(report=True, events=True, guilds_bases=True)
    admin = format_help(None, is_admin=True, features=feats)
    assert "use" in admin
    guest = format_help(None, is_admin=False, features=feats)
    assert "use" not in guest and "status" in guest


def test_format_help_filters_disabled_groups():
    from palworld_terminal.config import FeaturesConfig
    off = format_help(None, is_admin=False, features=FeaturesConfig(True, True, False))
    assert "guilds" not in off and "bases" not in off
    assert "status" in off and "world" in off
    on = format_help(None, is_admin=False, features=FeaturesConfig(True, True, True))
    assert "guilds" in on and "bases" in on
