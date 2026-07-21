from datetime import datetime
from zoneinfo import ZoneInfo

from palworld_terminal.config import SkippedServer
from palworld_terminal.domain.enums import Confidence, PingBucket
from palworld_terminal.application.dtos import (
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
    format_today,
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
        rows=[OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661)], updated_at=1000,
        degraded=False, max_players=32, peak_online=7,
    )
    text = format_online(dto, "Palpagos")
    assert text.splitlines()[0] == "👥 当前在线 · Palpagos"
    # 头行分子 = 收敛后名单数 len(rows)=1（T3 seam），/max 与今日峰值取聚合值。
    assert "在线 1/32 · 今日峰值 7" in text
    assert "· Neo Lv21" in text
    # ping bucket rendered as a friendly label, never a raw ms number
    assert "优秀" in text and "3661" not in text
    assert "1时01分" in text  # online_seconds 走 fmt_duration


def test_format_online_head_count_is_converged_list_length():
    # spec §3 / T3 seam：头行分子严格 = len(dto.rows)——OnlineDTO 不携带 raw metric 在线数，
    # 名单数即分子，杜绝「在线 N」与名单行数不一致的存在性泄漏。
    dto = OnlineDTO(
        rows=[OnlinePlayerRow("Trinity", 18, PingBucket.OK, 2700)], updated_at=1000,
        degraded=False, max_players=32, peak_online=9,
    )
    text = format_online(dto, "Palpagos")
    assert "在线 1/32" in text
    assert len([ln for ln in text.splitlines() if ln.startswith("· ")]) == 1


def test_format_online_strict_drops_duration_keeps_name_lv_ping():
    # spec §4.24：strict 砍时长字段，保留 名/Lv/Ping。
    dto = OnlineDTO(
        rows=[OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661)], updated_at=1000,
        degraded=False, max_players=32, peak_online=7,
    )
    text = format_online(dto, "Palpagos", strict=True)
    assert "· Neo Lv21 · Ping 优秀" in text
    assert "1时01分" not in text and "3661" not in text


def test_format_online_folds_over_seven_with_person_unit():
    # spec §2.7 折叠 7，尾行「…等共 N 人」。
    rows = [OnlinePlayerRow(f"P{i}", 20 - i, PingBucket.OK, 600) for i in range(9)]
    dto = OnlineDTO(rows=rows, updated_at=1000, degraded=False, max_players=32, peak_online=9)
    text = format_online(dto, "Palpagos")
    assert "…等共 9 人" in text
    assert "在线 9/32" in text  # 头行分子仍为名单全长（非折叠可见数）


def test_format_online_empty():
    text = format_online(
        OnlineDTO(rows=[], updated_at=1000, degraded=False), "Palpagos"
    )
    assert text.splitlines()[0] == "👥 当前在线 · Palpagos"
    assert "当前无玩家在线" in text


# ---- guild 组四条（spec §4.6-4.9；上游恢复后生效，落码即备）----

_G_TZ = "Asia/Tokyo"


def _g_ep(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(_G_TZ)).timestamp())


def test_format_guilds_list_sample_4_6():
    # spec §4.6：标题锚点=服务器名；每公会成员~/工作帕鲁/据点数；免责脚注；PalBox/active_7d 砍位。
    dtos = [GuildDTO("Matrix", 4, 28, 2), GuildDTO("Zion", 2, 9, 1)]
    assert format_guilds(dtos, "Palpagos") == (
        "🏰 公会 · Palpagos\n"
        "\n"
        "· Matrix 成员 ~4 · 工作帕鲁 28 · 据点 2\n"
        "· Zion 成员 ~2 · 工作帕鲁 9 · 据点 1\n"
        "└ 公会与据点均为插件观察推导"
    )


def test_format_guilds_no_palbox():
    # PalBox 计数归 overview 设施节，guild list 不再渲染（§4.6 定案）。
    assert "PalBox" not in format_guilds([GuildDTO("Matrix", 4, 28, 2)], "Palpagos")


def test_format_guilds_empty_plain_state():
    assert format_guilds([], "Palpagos") == "🏰 公会 · Palpagos\n暂无公会观察数据"


def test_format_guilds_strict_drops_base_count():
    # 字段级裁剪：砍「据点 N」计数位，公会本体（成员/工作帕鲁）保留（命令仍产出）。
    text = format_guilds([GuildDTO("Matrix", 4, 28, 2)], "Palpagos", strict=True)
    assert "据点 2" not in text
    assert "· Matrix 成员 ~4 · 工作帕鲁 28" in text


def _guild_detail(**kw):
    base = dict(
        name="Matrix", first_seen_at=_g_ep(2026, 6, 28),
        last_seen_at=_g_ep(2026, 7, 17, 14, 30), observed_members=4,
        base_pals=28, base_count=2,
        bases=[("海岸木材场", Confidence.HIGH), ("河谷矿场", Confidence.MEDIUM)],
        recent_events=["新据点「河谷矿场」确认", "据点「海岸木材场」工作帕鲁 12→18"],
    )
    base.update(kw)
    return GuildDetailDTO(**base)


def test_format_guild_info_sample_4_7():
    now = _g_ep(2026, 7, 17, 15, 0)
    assert format_guild(_guild_detail(), strict=False, now=now, tz=_G_TZ) == (
        "🏰 公会 · Matrix\n"
        "成员 ~4 · 工作帕鲁 28 · 据点 2\n"
        "首次观察 2026-06-28 · 最近 今天 14:30\n"
        "\n"
        "据点\n"
        "· 海岸木材场 置信度高\n"
        "· 河谷矿场 置信度中\n"
        "\n"
        "近期动态\n"
        "· 新据点「河谷矿场」确认\n"
        "· 据点「海岸木材场」工作帕鲁 12→18"
    )


def test_format_guild_info_no_palbox():
    now = _g_ep(2026, 7, 17, 15, 0)
    assert "PalBox" not in format_guild(_guild_detail(), strict=False, now=now, tz=_G_TZ)


def test_format_guild_info_strict_field_trim():
    # 字段级裁剪：省略「据点」节 + 「近期动态」节 + 首行「据点 N」计数；公会本体保留。
    now = _g_ep(2026, 7, 17, 15, 0)
    text = format_guild(_guild_detail(), strict=True, now=now, tz=_G_TZ)
    assert "据点 2" not in text
    assert "\n据点\n" not in text
    assert "近期动态" not in text
    assert "成员 ~4 · 工作帕鲁 28" in text
    assert "首次观察 2026-06-28" in text


def test_format_bases_sample_4_8():
    # spec §4.8：按公会分组；worker_count 实填；含 low 行（#3 无观测省工作帕鲁位）；免责脚注。
    dtos = [
        BaseDTO(1, "海岸木材场", "Matrix", Confidence.HIGH, 18),
        BaseDTO(2, "河谷矿场", "Matrix", Confidence.MEDIUM, 9),
        BaseDTO(3, "BASE-3", None, Confidence.LOW, 0),
    ]
    assert format_bases(dtos, "Palpagos") == (
        "🏕️ 据点 · Palpagos\n"
        "\n"
        "Matrix\n"
        "· #1 海岸木材场 置信度高 · 工作帕鲁 18\n"
        "· #2 河谷矿场 置信度中 · 工作帕鲁 9\n"
        "\n"
        "未确定公会\n"
        "· #3 BASE-3 置信度低\n"
        "└ 据点为插件观察推导；#序号可用于 /pal guild base"
    )


def test_format_bases_empty_plain_state():
    assert format_bases([], "Palpagos") == "🏕️ 据点 · Palpagos\n暂无可展示的据点"


def test_format_bases_folds_at_seven():
    dtos = [BaseDTO(i, f"B-{i}", "G", Confidence.HIGH, i) for i in range(1, 10)]
    text = format_bases(dtos, "Palpagos")
    assert "…等共 9 个" in text
    assert "#8" not in text  # 只渲染前 7 条据点行


def test_format_base_sample_4_9():
    dto = BaseDetailDTO(
        display_name="海岸木材场", guild_name="Matrix", confidence=Confidence.HIGH,
        worker_count=18, active_count=12, average_level=17.5, average_hp_ratio=0.92,
        action_distribution={"working": 8, "moving": 5, "idle": 3, "unknown": 2},
        health_score=90.0,
    )
    assert format_base(dto) == (
        "🏕️ 据点 · 海岸木材场\n"
        "公会「Matrix」 · 置信度高\n"
        "\n"
        "工作帕鲁 18 · 活跃 12 · 平均 Lv17.5\n"
        "状态 🟢 健康 · 平均HP 92%\n"
        "\n"
        "行为分布\n"
        "· 工作中 8 · 移动 5 · 闲置 3 · 未知 2"
    )


def test_format_base_no_palbox_no_activity_score():
    dto = BaseDetailDTO("B", "G", Confidence.HIGH, 18, 12, 17.5, 0.92,
                        {"working": 8}, 90.0)
    text = format_base(dto)
    assert "PalBox" not in text
    assert "活跃度" not in text  # activity_score 裸数砍位


def _health(score):
    dto = BaseDetailDTO("B", "G", Confidence.HIGH, 1, 1, 1.0, 1.0, {}, score)
    return format_base(dto)


def test_format_base_health_dot_thresholds():
    assert "状态 🟢 健康" in _health(75.0)
    assert "状态 🟡 一般" in _health(74.9)
    assert "状态 🟡 一般" in _health(40.0)
    assert "状态 🔴 低迷" in _health(39.9)


def test_format_base_action_distribution_eight_categories():
    dist = {"working": 1, "moving": 2, "idle": 3, "combat": 4,
            "sleeping": 5, "eating": 6, "incapacitated": 7, "unknown": 8}
    dto = BaseDetailDTO("B", None, Confidence.LOW, 1, 1, 1.0, 1.0, dist, 50.0)
    text = format_base(dto)
    assert "· 工作中 1 · 移动 2 · 闲置 3 · 战斗 4 · 睡觉 5 · 进食 6 · 濒死 7 · 未知 8" in text
    assert "未确定公会" in text  # guild_name None


def test_format_base_no_observation_state():
    # §6#8：无观测 → ⚠️ 取数失败态（不再全 0 假数据）。
    dto = BaseDetailDTO("海岸木材场", "Matrix", Confidence.HIGH, 0, 0, 0.0, 0.0,
                        {}, 0.0, available=False)
    text = format_base(dto)
    assert text == (
        "🏕️ 据点 · 海岸木材场\n"
        "公会「Matrix」 · 置信度高\n"
        "⚠️ 该据点尚无观测数据"
    )
    assert "工作帕鲁 0" not in text
    assert "行为分布" not in text


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


def test_format_servers_three_state_dots():
    # spec §4.20：🟢 在线（ready+可达）/ 🔴 离线（ready 不可达）/ 🟡 未就绪（配置不完整）。
    rows = [
        ServerStatusRow("主服", ready=True, online=True, allowed=True, active=True),
        ServerStatusRow("备用服", ready=True, online=False, allowed=False, active=False),
        ServerStatusRow("测试服", ready=False, online=False, allowed=False, active=False),
    ]
    text = format_servers(rows, [], is_admin=False, is_group=True)
    assert text.startswith("🔗 已配置服务器")
    assert "· 主服 🟢 在线 · 本群已授权 · 当前活动" in text
    assert "· 备用服 🔴 离线 · 本群未授权" in text
    assert "· 测试服 🟡 未就绪 · 本群未授权" in text


def test_format_servers_private_omits_auth_segment():
    # spec §4.20：私聊时授权段省略（不出「本群未授权」怪语义）。
    rows = [ServerStatusRow("主服", ready=True, online=True, allowed=False, active=False)]
    text = format_servers(rows, [], is_admin=False, is_group=False)
    assert "· 主服 🟢 在线" in text
    assert "本群" not in text
    assert "当前活动" not in text


def test_format_servers_admin_shows_skipped_section_cn_reason():
    # spec §4.20：无效配置素节头（无 ⚠️）+ reason 中文化；仅管理员可见。
    rows = [ServerStatusRow("alpha", ready=True, online=True, allowed=True, active=True)]
    skipped = [SkippedServer(raw_name="bad name", reason="illegal_char")]
    admin_text = format_servers(rows, skipped, is_admin=True, is_group=True)
    assert "alpha" in admin_text
    assert "无效配置" in admin_text
    assert "· bad name（名称含非法字符）" in admin_text
    assert "被跳过" not in admin_text  # 旧节头素文废弃
    guest_text = format_servers(rows, skipped, is_admin=False, is_group=True)
    assert "无效配置" not in guest_text
    assert "bad name" not in guest_text


def test_format_servers_skipped_reason_map():
    rows = [ServerStatusRow("alpha", ready=True, online=True, allowed=True, active=False)]
    skipped = [
        SkippedServer(raw_name="", reason="empty"),
        SkippedServer(raw_name="dup", reason="duplicate"),
        SkippedServer(raw_name="nocred", reason="no_credential"),
    ]
    text = format_servers(rows, skipped, is_admin=True, is_group=True)
    assert "（名称为空）" in text
    assert "· dup（名称重复）" in text
    assert "· nocred（缺少凭据）" in text


def test_format_servers_empty_state_uses_link_list_empty():
    # spec §4.20：拆键 link_list_empty（routing 的 no_server_configured 保持原素文）。
    text = format_servers([], [], is_admin=True, is_group=True)
    assert text == "尚未配置 Palworld 服务器\n└ 在插件设置页「连接」章添加"


def test_format_servers_admin_only_skipped_still_shows_section():
    # 无有效 rows 但管理员有 skipped → 展示无效配置节（不落空态）。
    skipped = [SkippedServer(raw_name="dup", reason="duplicate")]
    text = format_servers([], skipped, is_admin=True, is_group=True)
    assert "无效配置" in text and "dup" in text
    # guest 看不到 skipped → 空态
    assert format_servers([], skipped, is_admin=False, is_group=True) == (
        "尚未配置 Palworld 服务器\n└ 在插件设置页「连接」章添加"
    )


def test_format_servers_folds_over_seven():
    rows = [
        ServerStatusRow(f"srv{i}", ready=True, online=True, allowed=True, active=False)
        for i in range(9)
    ]
    text = format_servers(rows, [], is_admin=False, is_group=True)
    assert "…等共 9 条" in text
    assert "srv7" not in text  # 第 8 台起被折叠


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


class _TodayReport:
    """format_today 输入桩：ReportService 已把三节措辞渲染成串（event_wording 单一
    真相源），formatter 只做版式（标题锚点/节级折叠/累计时长 fmt_duration）。"""

    def __init__(self, **kw):
        self.day = kw.get("day", "2026-07-17")
        self.is_empty = kw.get("is_empty", False)
        self.world_day_start = kw.get("world_day_start", 42)
        self.world_day_end = kw.get("world_day_end", 45)
        self.active_players = kw.get("active_players", 3)
        self.peak_online = kw.get("peak_online", 7)
        self.total_online_seconds = kw.get("total_online_seconds", 45600)
        self.records = kw.get("records", [])
        self.growth = kw.get("growth", [])
        self.base_changes = kw.get("base_changes", [])
        self.summary = kw.get("summary", "今天：无。")


def test_today_title_carries_server_and_date():
    text = format_today(_TodayReport(records=["世界迎来第 100 天"]), "Palpagos")
    assert text.startswith("📅 今日日报 · Palpagos · 2026-07-17")


def test_today_accumulated_time_uses_fmt_duration():
    text = format_today(_TodayReport(total_online_seconds=45600, records=["x"]), "Palpagos")
    assert "累计在线 12时40分" in text
    assert "小时" not in text  # 废「N 小时」聚合式（spec §2.4）


def test_today_header_line_shape():
    text = format_today(
        _TodayReport(world_day_start=42, world_day_end=45, active_players=3,
                     peak_online=7, total_online_seconds=45600, records=["x"]),
        "Palpagos",
    )
    assert "第 42 → 45 天 · 活跃玩家 3 · 峰值在线 7 · 累计在线 12时40分" in text


def test_today_empty_state():
    text = format_today(_TodayReport(is_empty=True), "Palpagos")
    assert text == "📅 今日日报 · Palpagos · 2026-07-17\n平静的一天，没有新事件"


def test_today_section_headers_plain_no_icons():
    text = format_today(
        _TodayReport(records=["a"], growth=["b"], base_changes=["c"]), "Palpagos"
    )
    assert "\n今日纪录\n" in text
    assert "\n玩家成长\n" in text
    assert "\n据点变化\n" in text
    # 节头素文无图标（与 status/rules/events 一致）。
    for header in ("今日纪录", "玩家成长", "据点变化"):
        assert f"📅{header}" not in text


def test_today_fold_per_section_at_7():
    # 节级折叠特例（spec §2.7）：每节独立折叠 7 条，尾行「…等共 N 条」。
    recs = [f"事件{i}" for i in range(8)]
    text = format_today(_TodayReport(records=recs), "Palpagos")
    assert "· 事件0" in text and "· 事件6" in text
    assert "· 事件7" not in text
    assert "…等共 8 条" in text


def test_today_absent_section_omitted():
    text = format_today(_TodayReport(records=["只有纪录"]), "Palpagos")
    assert "今日纪录" in text
    assert "玩家成长" not in text
    assert "据点变化" not in text


# ---- Finding 1 回归：全部列表 formatter 遵从传入的 fold_limit（非硬编码 7）----
# config → formatter 的 fold_limit 穿线一旦断（某 formatter 回退硬编码 7），本组即红。


def test_formatters_honor_non_default_fold_limit():
    # online：5 行、limit=3 → 前 3 行 + 「…等共 5 人」，第 4 行（P3）折叠出。
    o_rows = [OnlinePlayerRow(f"P{i}", 20, PingBucket.OK, 600) for i in range(5)]
    online = format_online(
        OnlineDTO(rows=o_rows, updated_at=0, degraded=False, max_players=32, peak_online=5),
        "S", fold_limit=3,
    )
    assert "…等共 5 人" in online
    assert "· P3" not in online

    # status：在线玩家 5 人、limit=3 → 前 3 + 「…等共 5 人」。
    status = format_status(
        _status(players=[(f"P{i}", 20, "good") for i in range(5)], detail=_detail()),
        "S", fold_limit=3,
    )
    assert "…等共 5 人" in status
    assert "· P3" not in status

    # guilds：5 公会、limit=3 → 前 3 + 「…等共 5 个」。
    guilds = format_guilds([GuildDTO(f"G{i}", 1, 1, 1) for i in range(5)], "S", fold_limit=3)
    assert "…等共 5 个" in guilds
    assert "G3" not in guilds

    # today：今日纪录 5 条、limit=3 → 前 3 + 「…等共 5 条」（节级折叠）。
    today = format_today(
        _TodayReport(records=[f"E{i}" for i in range(5)]), "S", fold_limit=3,
    )
    assert "…等共 5 条" in today
    assert "· E3" not in today

    # bases：5 据点、limit=3 → 前 3 + 「…等共 5 个」（textkit.fold 重构后仍遵从 limit）。
    bases = format_bases(
        [BaseDTO(i, f"B{i}", "G", Confidence.HIGH, 0) for i in range(1, 6)],
        "S", fold_limit=3,
    )
    assert "…等共 5 个" in bases
    assert "#4" not in bases


def test_format_bases_default_limit_unchanged_when_seven():
    # 默认 limit=7 行为不变（textkit.fold 重构不改既有折叠语义）：8 据点 → 前 7 + 尾行。
    dtos = [BaseDTO(i, f"B-{i}", "G", Confidence.HIGH, i) for i in range(1, 9)]
    text = format_bases(dtos, "Palpagos")
    assert "…等共 8 个" in text
    assert "#8" not in text
    assert "#7" in text
