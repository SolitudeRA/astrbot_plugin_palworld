from datetime import datetime
from zoneinfo import ZoneInfo

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
    RulesDTO,
    RuleSection,
    ServerStatusRow,
    StatusDetailDTO,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
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
    format_rules,
    format_servers,
    format_status,
    format_world,
)


def _detail(version="0.6.5", uptime=550800):
    return StatusDetailDTO(
        version=version, description="", uptime_seconds=uptime,
        frametime_ms=17.2, address="", rules={},
    )


def _status(*, players, online=2, max_players=32, basecamp_count=5, detail=None):
    return StatusDTO(
        server_name="cfg-name", world_name="game-world", world_day=42, online=online,
        max_players=max_players, basecamp_count=basecamp_count, fps=58.0, frame_time=17.2,
        smoothness_label="流畅", players=players, peak_online_today=7,
        updated_at=1700000000, degraded=False, last_ok=1700000000, detail=detail,
    )


def test_format_degraded_shows_minutes_not_shutdown():
    # 降级态两行：标题锚点 + 🔴 状态行「最后成功于 N 分钟前」（1500s / 60 = 25）
    text = format_degraded(last_ok=1000, now=1000 + 1500, server_name="Palpagos")
    assert "🌍 世界状态 · Palpagos" in text
    assert "25 分钟前" in text
    assert "关机" not in text


def test_format_degraded_never_ok():
    text = format_degraded(last_ok=None, now=1000, server_name="Palpagos")
    assert "🌍 世界状态 · Palpagos" in text
    assert "尚未成功连接过服务器" in text


def test_format_status_degraded_two_line_title_and_status():
    # 陈旧降级：format_status 走两行降级块（标题锚点=server_name 参数 + 🔴 状态），用 dto.now 算分钟
    dto = StatusDTO(
        server_name="ignored", world_name="game-world", world_day=0, online=0,
        max_players=0, basecamp_count=0, fps=0.0, frame_time=0.0, smoothness_label="",
        players=[], peak_online_today=0, updated_at=1000, degraded=True,
        last_ok=1000, now=1000 + 1500,
    )
    text = format_status(dto, "Palpagos")
    lines = text.split("\n")
    assert len(lines) == 2
    assert lines[0] == "🌍 世界状态 · Palpagos"
    assert "25 分钟前" in lines[1]


def test_format_status_new_layout_matches_spec_4_1():
    # spec §4.1 定稿样张逐行（标题锚点=配置名参数；据点独立行；玩家轻条目）。
    dto = _status(
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")], detail=_detail(),
    )
    assert format_status(dto, "Palpagos") == (
        "🌍 世界状态 · Palpagos\n"
        "第 42 天 · v0.6.5 · 已运行 6天9时\n"
        "\n"
        "在线 2/32 · 今日峰值 7\n"
        "性能 🟢 流畅 · FPS 58 · 帧时间 17.2ms\n"
        "据点 5\n"
        "\n"
        "在线玩家\n"
        "· Neo Lv21\n"
        "· Trinity Lv18"
    )


def test_format_status_head_count_is_converged_list_length_not_raw():
    # spec §3/§4.1 要点（B）：头行分子=收敛后名单长度，而非 metric 原始在线数（dto.online）。
    # dto.online=9（原始/聚合）但收敛名单仅 2 人 → 头行须 2/32，杜绝「在线 9」列 2 人的存在性泄漏。
    dto = _status(players=[("Neo", 21, "good"), ("Trinity", 18, "ok")], online=9, detail=_detail())
    text = format_status(dto, "Palpagos")
    assert "在线 2/32" in text
    assert "在线 9" not in text


def test_format_status_bases_line_hidden_when_group_off():
    dto = _status(players=[("Neo", 21, "good")], detail=_detail())
    on = format_status(dto, "Palpagos", show_bases=True)
    off = format_status(dto, "Palpagos", show_bases=False)
    assert "据点 5" in on
    assert "据点" not in off


def test_format_status_folds_players_over_seven():
    players = [(f"P{i}", 20 + i, "good") for i in range(9)]
    text = format_status(_status(players=players, max_players=32, detail=_detail()), "Palpagos")
    assert "…等共 9 人" in text
    assert "· P7" not in text  # 超 7 条后不再逐条列出


def test_format_status_zero_players_omits_section():
    text = format_status(_status(players=[], detail=_detail()), "Palpagos")
    assert "在线玩家" not in text
    assert "在线 0/32" in text


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


_EVT_TZ = "Asia/Tokyo"


def _evt_ep(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(_EVT_TZ)).timestamp())


def _evt(occurred_at, summary, event_type="x"):
    return EventDTO(occurred_at=occurred_at, event_type=event_type, summary=summary)


def test_format_events_by_day_grouping_spec_4_4():
    # spec §4.4：标题锚点 + 空行 + 日分组；仅今天条目带 HH:MM，过往日靠节头定位不带时刻。
    now = _evt_ep(2026, 7, 17, 15, 0)
    events = [
        _evt(_evt_ep(2026, 7, 17, 14, 32), "Neo 升级 Lv21→Lv22"),
        _evt(_evt_ep(2026, 7, 17, 9, 15), "在线人数新纪录 8 人"),
        _evt(_evt_ep(2026, 7, 16, 20, 0), "新玩家 Trinity 加入世界"),
        _evt(_evt_ep(2026, 7, 14, 10, 0), "新公会「Matrix」出现"),
    ]
    assert format_events(
        events, "Palpagos", now=now, tz=_EVT_TZ, today_only=False, fold_limit=7,
    ) == (
        "📰 世界事件 · Palpagos\n"
        "\n"
        "今天\n"
        "· 14:32 Neo 升级 Lv21→Lv22\n"
        "· 09:15 在线人数新纪录 8 人\n"
        "\n"
        "昨天\n"
        "· 新玩家 Trinity 加入世界\n"
        "\n"
        "07-14\n"
        "· 新公会「Matrix」出现"
    )


def test_format_events_today_variant_no_day_headers():
    # spec §4.4 today 变体：标题「今日事件」，无节头，直列带 HH:MM。
    now = _evt_ep(2026, 7, 17, 15, 0)
    events = [
        _evt(_evt_ep(2026, 7, 17, 14, 32), "Neo 升级 Lv21→Lv22"),
        _evt(_evt_ep(2026, 7, 17, 9, 15), "在线人数新纪录 8 人"),
    ]
    text = format_events(
        events, "Palpagos", now=now, tz=_EVT_TZ, today_only=True, fold_limit=7,
    )
    assert text == (
        "📰 今日事件 · Palpagos\n"
        "\n"
        "· 14:32 Neo 升级 Lv21→Lv22\n"
        "· 09:15 在线人数新纪录 8 人"
    )
    assert "\n今天\n" not in text  # today 变体无日节头


def test_format_events_message_level_fold_across_days():
    # spec §2.7：events 为消息级折叠特例——多日节合计 ≤ fold_limit，尾行「…等共 N 条」。
    now = _evt_ep(2026, 7, 17, 15, 0)
    events = [_evt(_evt_ep(2026, 7, 17, 14, 0) - i * 60, f"今日{i}") for i in range(4)]
    events += [_evt(_evt_ep(2026, 7, 16, 20, 0) - i * 60, f"昨日{i}") for i in range(5)]
    text = format_events(
        events, "Palpagos", now=now, tz=_EVT_TZ, today_only=False, fold_limit=7,
    )
    assert "…等共 9 条" in text            # 尾行量词「条」，N=池内总条数
    assert "昨日2" in text                 # 第 7 条（4 今日 + 3 昨日）在编
    assert "昨日3" not in text             # 第 8 条被折叠出
    assert "昨日4" not in text


def test_format_events_empty_normal_variant():
    # spec §4.4/§9：集合空 → 素文（标题 + 一句话），不佩 ⚠️。
    now = _evt_ep(2026, 7, 17, 15, 0)
    assert format_events(
        [], "Palpagos", now=now, tz=_EVT_TZ, today_only=False, fold_limit=7,
    ) == "📰 世界事件 · Palpagos\n最近还没有新事件"


def test_format_events_empty_today_variant():
    now = _evt_ep(2026, 7, 17, 15, 0)
    assert format_events(
        [], "Palpagos", now=now, tz=_EVT_TZ, today_only=True, fold_limit=7,
    ) == "📰 今日事件 · Palpagos\n今天还没有新事件"


def _world_dto(*, available=True):
    return WorldSummaryDTO(
        world_day=42, online=2, max_players=32, players=12, otomo=38, base_pal=102,
        wild=361, npc=45, palbox=8, guilds=5, basecamp_count=5,
        wild_top=[WildTopRow("疾风隼", 24), WildTopRow("棉悠悠", 18)], available=available,
    )


def test_format_world_new_layout_matches_spec_4_2():
    assert format_world(_world_dto(), "Palpagos") == (
        "🗺️ 世界概览 · Palpagos\n"
        "第 42 天 · 在线 2/32\n"
        "\n"
        "居民\n"
        "· 角色 12 · NPC 45\n"
        "· 帕鲁 随行 38 · 工作 102 · 野生 361\n"
        "\n"
        "设施\n"
        "· PalBox 8 · 公会 5 · 据点 5\n"
        "\n"
        "野生帕鲁 Top（当前快照）\n"
        "· 疾风隼 ×24\n"
        "· 棉悠悠 ×18"
    )


def test_format_world_snapshot_missing_is_error_state():
    # spec §4.2/§6#8：快照缺失不再静默全 0，走 ⚠️ 取数失败态。
    text = format_world(_world_dto(available=False), "Palpagos")
    assert text == "🗺️ 世界概览 · Palpagos\n⚠️ 尚未获取到世界快照，稍后再试"


def test_format_world_strict_omits_palbox_keeps_guild_and_base():
    text = format_world(_world_dto(), "Palpagos", strict=True)
    assert "· 公会 5 · 据点 5" in text
    assert "PalBox" not in text


def _rules_dto(*, available=True, privacy_note=None):
    return RulesDTO(
        sections=[
            RuleSection("模式", [("难度", "普通"), ("硬核", "关闭")]),
            RuleSection("倍率", [("经验", "1.0x"), ("捕获", "1.2x")]),
        ],
        available=available, privacy_note=privacy_note, updated_at=1700000000,
    )


def test_format_rules_pairs_two_per_line():
    text = format_rules(_rules_dto(), "Palpagos")
    assert text == (
        "📜 世界规则 · Palpagos\n"
        "\n"
        "模式\n"
        "· 难度 普通 · 硬核 关闭\n"
        "\n"
        "倍率\n"
        "· 经验 1.0x · 捕获 1.2x"
    )


def test_format_rules_unavailable_is_error_state():
    # spec §4.3/§9：settings 未获取 → ⚠️ 取数失败态。
    text = format_rules(_rules_dto(available=False), "Palpagos")
    assert text == "📜 世界规则 · Palpagos\n⚠️ 尚未从服务器获取到规则数据，稍后再试"


def test_format_rules_privacy_note_footer():
    text = format_rules(_rules_dto(privacy_note="据点模块在 strict 隐私模式下停用"), "Palpagos")
    assert text.endswith("└ 据点模块在 strict 隐私模式下停用")


def test_format_servers_admin_shows_skipped_section():
    rows = [ServerStatusRow("alpha", True, True, True, True)]
    skipped = [SkippedServer(raw_name="dup", reason="duplicate")]
    admin_text = format_servers(rows, skipped, is_admin=True)
    assert "alpha" in admin_text
    assert "被跳过" in admin_text
    guest_text = format_servers(rows, skipped, is_admin=False)
    assert "被跳过" not in guest_text


def test_format_help_role_separation():
    from tests.unit._perm import all_on
    ov = all_on()
    admin = format_help(None, is_admin=True, overrides=ov)
    assert "/pal link add" in admin  # 管理员服务器授权（原 /pal server add）
    guest = format_help(None, is_admin=False, overrides=ov)
    assert "/pal link add" not in guest and "/pal world status" in guest


def test_format_help_filters_disabled_groups():
    # 「启用组出现在 help」示范载体迁 player（guild 上游不可用恒不列，另有 force-off 断言）。
    from tests.unit._perm import overrides
    off = format_help(None, is_admin=False, overrides=overrides(players=False))
    assert "/pal player info" not in off and "/pal player bind" not in off
    assert "/pal world status" in off
    on = format_help(None, is_admin=False, overrides=overrides(players=True))
    assert "/pal player info" in on and "/pal player bind" in on
    # guild 组即便开也恒不列（force-off）。
    assert "/pal guild info" not in on
