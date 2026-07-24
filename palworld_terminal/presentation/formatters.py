from __future__ import annotations

from ..application.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventView,
    GuildDetailDTO,
    GuildDTO,
    OnlineDTO,
    RankClimbDTO,
    RulesDTO,
    ServerStatusRow,
    StatusDTO,
    WorldSummaryDTO,
)
from ..application.query_service import PlayerProfileDTO, RankBoardsDTO
from ..config import SkippedServer
from ..domain.enums import ActionCategory, Confidence, PingBucket
from ..presentation.event_wording import render_event
from ..presentation.locale import L
from ..presentation.textkit import (
    abs_date,
    fmt_duration,
    fold,
    rel_date,
    rel_datetime,
    time_of_day,
)
from ..shared.command_permissions import effective_enabled
from ..shared.command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    HELP_TEXT,
    ActionSpec,
)

_PING_LABEL = {
    PingBucket.GOOD: "优秀", PingBucket.OK: "正常",
    PingBucket.HIGH: "偏高", PingBucket.UNKNOWN: "未知",
}
_CONF_LABEL = {Confidence.HIGH: "高", Confidence.MEDIUM: "中", Confidence.LOW: "低"}

# 行为分布类目（spec §4.9）：ActionCategory 8 档中文（细分工种数据面不存在，不臆造「伐木/搬运」）。
_ACTION_CAT_LABEL = {
    ActionCategory.WORKING: "工作中", ActionCategory.MOVING: "移动",
    ActionCategory.IDLE: "闲置", ActionCategory.SLACKING: "摸鱼",
    ActionCategory.COMBAT: "战斗",
    ActionCategory.SLEEPING: "睡觉", ActionCategory.EATING: "进食",
    ActionCategory.INCAPACITATED: "濒死", ActionCategory.UNKNOWN: "未知",
}

# 性能流畅度档位 → 状态色点（spec §2.2/§4.1）：流畅🟢 / 一般🟡 / 卡顿·严重卡顿🔴。
_SMOOTH_DOT = {"流畅": "🟢", "一般": "🟡", "卡顿": "🔴", "严重卡顿": "🔴"}


def format_degraded(last_ok: int | None, now: int, server_name: str) -> str:
    """降级态两行（spec §3/§4.1）：标题锚点全局统一 `🌍 世界状态 · {服务器名}`（不随
    发起命令变化）+ 🔴 状态行。last_ok=None 为「从未成功」句；否则「最后成功于 N 分钟前」。
    """
    if last_ok is None:
        status = L("degraded_never")
    else:
        minutes = max(0, (now - last_ok) // 60)
        status = L("degraded", minutes=minutes)
    return f"🌍 世界状态 · {server_name}\n{status}"


def format_online(
    dto: OnlineDTO, server_name: str, *, strict: bool = False, fold_limit: int = 7,
) -> str:
    """online 当前在线（spec §4.24）。标题锚点 server_name = 配置名 srv.name（commands 层供数）。

    头行在线数分子 = 收敛后名单数 len(dto.rows)（spec §3 隐私收敛——与名单行数必然同数，
    T3 seam 在此闭合，杜绝「在线 3」却只列 2 人的存在性泄漏）；/max 容量取 dto.max_players、
    今日峰值取 dto.peak_online（metric 聚合值，不可归因，保留）。strict 砍时长字段（名/Lv/Ping
    保留，同 rank/me 双砍哲学）。空态收编 locale online_empty。>7 折叠尾行「…等共 N 人」。
    """
    title = f"👥 当前在线 · {server_name}"
    if not dto.rows:
        return f"{title}\n{L('online_empty')}"
    entries: list[str] = []
    for r in dto.rows:
        cells = [f"{r.name} Lv{r.level}", f"Ping {_PING_LABEL[r.ping_bucket]}"]
        if not strict:
            cells.append(fmt_duration(r.online_seconds))
        entries.append("· " + " · ".join(cells))
    lines = [
        title,
        f"在线 {len(dto.rows)}/{dto.max_players} · 今日峰值 {dto.peak_online}",
        "",
        *fold(entries, fold_limit, "人"),
    ]
    return "\n".join(lines)


def format_guilds(
    dto: list[GuildDTO], server_name: str, *, strict: bool = False, fold_limit: int = 7,
) -> str:
    """guild list（spec §4.6）。标题锚点=服务器名（commands 层供数）。每公会成员~/工作帕鲁/
    据点数（PalBox 归 overview 设施节，此处不渲染；active_7d 砍位）。strict=字段级裁剪：
    砍「据点 N」计数位，公会本体保留（命令仍产出，非拒执行）。空态素文；>7 折叠「…等共 N 个」。"""
    title = f"🏰 公会 · {server_name}"
    if not dto:
        return f"{title}\n{L('guilds_empty')}"
    entries: list[str] = []
    for g in dto:
        cells = [f"{g.name} 成员 ~{g.observed_members}", f"工作帕鲁 {g.base_pals}"]
        if not strict:
            cells.append(f"据点 {g.base_count}")
        entries.append("· " + " · ".join(cells))
    lines = [title, "", *fold(entries, fold_limit, "个")]
    lines.append("└ 公会与据点均为插件观察推导")
    return "\n".join(lines)


def format_guild(
    dto: GuildDetailDTO, *, strict: bool, now: int, tz, fold_limit: int = 7,
) -> str:
    """guild info（spec §4.7）。标题锚点=公会名 dto.name。首次观察=绝对日期；最近=相对
    日期词表（时间戳字段全档带 HH:MM）。据点节 + 近期动态节实填（近期动态经 render_event
    渲染，query 层已构造 EventView）。恒 0 占位（active_*/average_level）与 PalBox 砍位。
    strict=字段级裁剪：省略据点节 + 近期动态节 + 首行「据点 N」计数（据点类不经本命令绕出
    strict）；公会本体（成员/工作帕鲁/首次观察/最近）保留。"""
    head = [f"成员 ~{dto.observed_members}", f"工作帕鲁 {dto.base_pals}"]
    if not strict:
        head.append(f"据点 {dto.base_count}")
    lines = [
        f"🏰 公会 · {dto.name}",
        " · ".join(head),
        f"首次观察 {abs_date(dto.first_seen_at, tz)} · 最近 {rel_datetime(dto.last_seen_at, now, tz)}",
    ]
    if not strict:
        if dto.bases:
            lines.append("")
            lines.append("据点")
            lines.extend(fold(
                [f"· {name} 置信度{_CONF_LABEL[conf]}" for name, conf in dto.bases],
                fold_limit, "个",
            ))
        if dto.recent_events:
            lines.append("")
            lines.append("近期动态")
            lines.extend(fold([f"· {render_event(ev)}" for ev in dto.recent_events], fold_limit, "条"))
    return "\n".join(lines)


def format_bases(dto: list[BaseDTO], server_name: str, *, fold_limit: int = 7) -> str:
    """guild bases（spec §4.8）。标题锚点=服务器名（commands 层供数）。按公会分组（未归属→
    「未确定公会」）；每据点 #序号（T5 统一含 low 序号空间）+ 置信度 + worker_count 实填
    （>0 才渲染，无观测据点省该位）；hidden 恒不入清单；全局折叠（textkit.fold 单一尾行
    格式「…等共 N 个」，共用 cfg.players.list_fold_limit）。空态素文。"""
    title = f"🏕️ 据点 · {server_name}"
    if not dto:
        return f"{title}\n{L('bases_empty')}"
    visible = dto[:fold_limit]
    # 折叠尾行经 textkit.fold 生成（与其它列表共用同一限额与「…等共 N 个」尾格式）：
    # 分组渲染用 visible，尾行只取 fold 汇总部分（未折叠时为空）。
    tail = fold([b.display_name for b in dto], fold_limit, "个")[len(visible):]
    lines = [title]
    current_guild: str | None = None
    for b in visible:
        guild = b.guild_name or "未确定公会"
        if guild != current_guild:
            lines.append("")
            lines.append(guild)
            current_guild = guild
        cells = [f"#{b.index} {b.display_name} 置信度{_CONF_LABEL[b.confidence]}"]
        if b.worker_count > 0:
            cells.append(f"工作帕鲁 {b.worker_count}")
        lines.append("· " + " · ".join(cells))
    lines.extend(tail)
    lines.append("└ 据点为插件观察推导；#序号可用于 /pal guild base")
    return "\n".join(lines)


def _health_status(score: float) -> tuple[str, str]:
    """健康度 → 状态点+词（spec §4.9）：🟢 健康 ≥75 / 🟡 一般 ≥40 / 🔴 低迷 <40。"""
    if score >= 75:
        return "🟢", "健康"
    if score >= 40:
        return "🟡", "一般"
    return "🔴", "低迷"


def format_base(dto: BaseDetailDTO) -> str:
    """guild base（spec §4.9）。标题锚点=据点名 dto.display_name。健康度→状态点+词；行为分布=
    ActionCategory 8 档中文（有计数者按枚举定序渲染）。activity_score 裸数与 palbox_count 砍位。
    available=False（无观测）→ ⚠️ 取数失败态（不再全 0 假数据，§6#8）。"""
    title = f"🏕️ 据点 · {dto.display_name}"
    guild = f"公会「{dto.guild_name}」" if dto.guild_name else "未确定公会"
    ident = f"{guild} · 置信度{_CONF_LABEL[dto.confidence]}"
    if not dto.available:
        return f"{title}\n{ident}\n{L('base_no_observation')}"
    dot, word = _health_status(dto.health_score)
    lines = [
        title,
        ident,
        "",
        f"工作帕鲁 {dto.worker_count} · 活跃 {dto.active_count} · 平均 Lv{dto.average_level:.1f}",
        f"状态 {dot} {word} · 平均HP {dto.average_hp_ratio:.0%}",
    ]
    dist = [
        f"{_ACTION_CAT_LABEL[cat]} {dto.action_distribution[cat.value]}"
        for cat in ActionCategory
        if dto.action_distribution.get(cat.value, 0) > 0
    ]
    if dist:
        lines.append("")
        lines.append("行为分布")
        lines.append("· " + " · ".join(dist))
    return "\n".join(lines)


def format_events(
    events: list[EventView], server_name: str, *,
    now: int, tz, today_only: bool, fold_limit: int,
) -> str:
    """world events（spec §4.4）。标题锚点 server_name = 配置名 srv.name（commands 层供数）。

    events 已由 query 层隐藏收敛 + 名字解析 + event_view 构造 EventView，按 occurred_at
    DESC 排列；措辞经 render_event 渲染。本函数只做呈现：日分组 / 仅今天条目带 HH:MM /
    消息级折叠 / 空态两变体。

    - today 变体（today_only）：标题「今日事件」，不设日节头，直列条目均带 HH:MM。
    - 常规：按 rel_date 词形（今天/昨天/MM-DD）分节，仅「今天」节条目带 HH:MM，过往日靠
      节头定位不带时刻（spec §2.5）。
    - 折叠为**消息级特例**（spec §2.7）：多日节合计 ≤ fold_limit，尾行「…等共 N 条」；
      经 textkit.fold 生成尾行（量词「条」，N=池内总条数）。
    """
    title = f"📰 今日事件 · {server_name}" if today_only else f"📰 世界事件 · {server_name}"
    if not events:
        empty = L("events_empty_today") if today_only else L("events_empty")
        return f"{title}\n{empty}"

    # 消息级折叠：截前 fold_limit 条渲染，尾行经 textkit.fold 复用同一「…等共 N 条」格式。
    visible = events[:fold_limit]
    tail = fold([render_event(e) for e in events], fold_limit, "条")[len(visible):]

    lines = [title]
    if today_only:
        lines.append("")
        lines.extend(f"· {time_of_day(e.occurred_at, tz)} {render_event(e)}" for e in visible)
    else:
        current_day: str | None = None
        for e in visible:
            day = rel_date(e.occurred_at, now, tz)
            if day != current_day:
                lines.append("")          # 空行分节（含标题与首节之间）
                lines.append(day)         # 素节头无图标
                current_day = day
            if day == "今天":
                lines.append(f"· {time_of_day(e.occurred_at, tz)} {render_event(e)}")
            else:
                lines.append(f"· {render_event(e)}")
    lines.extend(tail)                     # 折叠尾行（未折叠时为空）
    return "\n".join(lines)


# skipped 配置 reason 中文化（spec §4.20）：无效配置节逐条回显原始名 + 中文原因。
_SKIP_REASON = {
    "empty": "名称为空",
    "duplicate": "名称重复",
    "illegal_char": "名称含非法字符",
    "no_credential": "缺少凭据",
}


def format_servers(
    rows: list[ServerStatusRow], skipped: list[SkippedServer], is_admin: bool,
    *, is_group: bool = True, fold_limit: int = 7,
) -> str:
    """/pal link list（spec §4.20）。标题无服务器主体（§2.1 豁免）。

    状态三态点：🟡 未就绪（not ready）/ 🟢 在线（ready 且可达）/ 🔴 离线（ready 不可达）——
    可达性由 commands 层按 metric 新鲜度派生填 row.online。私聊（is_group=False）授权段省略
    （不出「本群未授权」怪语义）。无效配置素节头（无 ⚠️）+ reason 中文化，仅管理员可见。
    空态拆键 link_list_empty（routing 的 no_server_configured 保原素文）；主列表折叠 7。
    """
    if not rows and not (is_admin and skipped):
        return L("link_list_empty")
    entries: list[str] = []
    for r in rows:
        if not r.ready:
            dot, word = "🟡", "未就绪"
        elif r.online:
            dot, word = "🟢", "在线"
        else:
            dot, word = "🔴", "离线"
        cells = [f"{r.name} {dot} {word}"]
        if is_group:
            cells.append("本群已授权" if r.allowed else "本群未授权")
            if r.active:
                cells.append("当前活动")
        entries.append("· " + " · ".join(cells))
    lines = ["🔗 已配置服务器", "", *fold(entries, fold_limit, "条")]
    if is_admin and skipped:
        lines.append("")
        lines.append("无效配置")
        lines.extend(
            f"· {s.raw_name}（{_SKIP_REASON.get(s.reason, s.reason)}）" for s in skipped
        )
    return "\n".join(lines)


# 命令组显示标签（分级 help / 裸组迷你帮助共用；避免英文词汇泄漏干扰功能门测试）。
# 组头词表与前端设置页 GROUP_LABELS 统一定字（spec §4.26）：world/guild/player/link
# 同词；server 于聊天帮助补「（管理员）」标注（前端权限章靠锁图标呈现，无需此后缀）。
_GROUP_LABEL: dict[str, str] = {
    "world": "世界",
    "guild": "公会",
    "player": "玩家",
    "server": "服务器管控（管理员）",
    "link": "服务器授权",
}
_FLAT_LABEL = "其他"


def _action_visible(path: str, spec: ActionSpec, is_admin: bool, overrides) -> bool:
    """单一可见性判定：功能门（生效值）+ 角色门。

    写动作（gate=admin_write）与需管理员的动作（gate=admin，含 link add/remove、
    confirm）仅管理员可见——非管理员绝不泄漏其存在（安全线）。功能门只换数据源
    （查完整路径生效值），角色语义不变——不引入「锁读→不可见」。
    """
    _method, _feat_group, gate = spec
    if not effective_enabled(overrides, path):
        return False
    if gate in ("admin_write", "admin"):
        return is_admin
    return True


def visible_actions(
    group: str, is_admin: bool, overrides, world_mode: str = "multi",
) -> list[tuple[str, ActionSpec]]:
    """分级 help + 裸组迷你帮助的**单一过滤真相源**（谓词）。

    返回组内按功能门（生效值）+ 角色过滤后的可见 (子动作, ActionSpec) 有序列表。
    单世界模式省略整个 link 组（视觉；运行时守卫在 main 的 link handler）。
    _group_help（commands.py 裸组迷你帮助）复用本函数——绝不另写一份过滤。
    """
    if group == "link" and world_mode == "single":
        return []
    return [
        (sub, spec)
        for sub, spec in DISPATCH.get(group, {}).items()
        if _action_visible(f"{group} {sub}", spec, is_admin, overrides)
    ]


def _help_line(path: str) -> str:
    """行式 `· /pal {路径} {描述}`（spec §4.26）：一级 `· ` 前缀，路径与描述单空格分隔。"""
    desc = HELP_TEXT.get(path, "")
    return f"· /pal {path} {desc}" if desc else f"· /pal {path}"


def format_help(topic: str | None, is_admin: bool, overrides, world_mode: str = "multi") -> str:
    """分级 help（spec §4.26）：📖 标题 + 素节头（废【】，对齐全局素节头定案）+ 行式条目。

    角色/功能/模式过滤逻辑零改动——visible_actions 是唯一谓词（guest 不见写命令/confirm）；
    本函数只定版式与组头词表。尾注 `└ 命令末尾加 @服务器名 可指定服务器` 单模式省略（single
    下 resolve 忽略 @override，尾注是空承诺）。topic 参数维持忽略（不扩 /pal help <组>）。
    """
    lines = ["📖 PalWorldTerminal 命令"]
    for group in DISPATCH:  # world/guild/player/server/link（插入序）
        vis = visible_actions(group, is_admin, overrides, world_mode)
        if not vis:
            continue
        lines.append("")                                      # 空行分节
        lines.append(_GROUP_LABEL.get(group, group))          # 素节头无图标/无【】
        lines.extend(_help_line(f"{group} {sub}") for sub, _spec in vis)
    flat = [name for name, spec in FLAT_ACTIONS.items()
            if _action_visible(name, spec, is_admin, overrides)]
    if flat:
        lines.append("")
        lines.append(_FLAT_LABEL)
        lines.extend(_help_line(name) for name in flat)
    if world_mode != "single":                                # 单模式省略 @ 尾注（空承诺）
        lines.append("")
        lines.append("└ 命令末尾加 @服务器名 可指定服务器")
    return "\n".join(lines)


def format_status(
    dto: StatusDTO, server_name: str, *, show_bases: bool = True, fold_limit: int = 7,
) -> str:
    """world status（spec §4.1）。标题锚点 server_name = 配置名 srv.name（commands 层供数，
    不取游戏内 world.server_name）。`据点` 独立行随 guilds_bases 组关闭而整行消失。

    头行在线数分子 = 收敛后名单数（len(dto.players)，spec §3 隐私收敛）——与名单行数
    必然同数，绝不出现「在线 3」却只列 2 人的存在性泄漏；容量 /max 与今日峰值取 metric
    聚合值（不可归因，保留原值）。
    """
    if dto.degraded:
        # now 用 dto.now（真实当下）：陈旧时 updated_at==last_ok，不能充当 now。
        return format_degraded(dto.last_ok, dto.now, server_name)
    detail = dto.detail
    lines = [f"🌍 世界状态 · {server_name}"]
    if detail is not None:
        lines.append(
            f"第 {dto.world_day} 天 · v{detail.version} · 已运行 {fmt_duration(detail.uptime_seconds)}"
        )
    else:  # 防御：live 恒有 detail；缺失时仅出天数，不冒 AttributeError。
        lines.append(f"第 {dto.world_day} 天")
    lines.append("")
    lines.append(f"在线 {len(dto.players)}/{dto.max_players} · 今日峰值 {dto.peak_online_today}")
    dot = _SMOOTH_DOT.get(dto.smoothness_label, "🟡")
    lines.append(
        f"性能 {dot} {dto.smoothness_label} · FPS {dto.fps:.0f} · 帧时间 {dto.frame_time:.1f}ms"
    )
    if show_bases:
        lines.append(f"据点 {dto.basecamp_count}")
    if dto.players:  # 0 人省略整节（含其上方空行）
        lines.append("")
        lines.append("在线玩家")
        lines.extend(fold([f"· {n} Lv{lv}" for n, lv, _ in dto.players], fold_limit, "人"))
    return "\n".join(lines)


def format_world(
    dto: WorldSummaryDTO, server_name: str, *, strict: bool = False, fold_limit: int = 7,
) -> str:
    """world overview 人口普查（spec §4.2）。FPS 归 status（不渲染）；据点数取官方口径。

    快照缺失（available=False）→ ⚠️ 取数失败态（不再静默全 0）。strict 下省略设施节的
    PalBox 项（保留公会/据点两计数——据点/公会为官方推导计数，非个体隐私）。
    """
    title = f"🗺️ 世界概览 · {server_name}"
    if not dto.available:
        return f"{title}\n{L('world_snapshot_missing')}"
    lines = [
        title,
        f"第 {dto.world_day} 天 · 在线 {dto.online}/{dto.max_players}",
        "",
        "居民",
        f"· 角色 {dto.players} · NPC {dto.npc}",
        f"· 帕鲁 随行 {dto.otomo} · 工作 {dto.base_pal} · 野生 {dto.wild}",
        "",
        "设施",
    ]
    facility = [] if strict else [f"PalBox {dto.palbox}"]
    facility.append(f"公会 {dto.guilds}")
    facility.append(f"据点 {dto.basecamp_count}")
    lines.append("· " + " · ".join(facility))
    if dto.wild_top:
        lines.append("")
        lines.append("野生帕鲁 Top（当前快照）")
        lines.extend(fold([f"· {w.name} ×{w.count}" for w in dto.wild_top], fold_limit, "种"))
    return "\n".join(lines)


def format_rules(dto: RulesDTO, server_name: str) -> str:
    """world rules 策展分节（spec §4.3）。同类字段两两并一行 `· A · B`。

    快照缺失（available=False）→ ⚠️ 取数失败态。隐私模式注两句分叉走脚注 `└ `。
    游戏设定原值（蛋孵化 72 小时 / 空投间隔 180 分钟）保游戏原单位（§2.4 豁免，query 已渲）。
    """
    title = f"📜 世界规则 · {server_name}"
    if not dto.available:
        return f"{title}\n{L('rules_unavailable')}"
    lines = [title]
    for sec in dto.sections:
        lines.append("")
        lines.append(sec.title)
        for i in range(0, len(sec.items), 2):
            cells = [f"{label} {value}" for label, value in sec.items[i:i + 2]]
            lines.append("· " + " · ".join(cells))
    if dto.privacy_note:
        lines.append(f"└ {dto.privacy_note}")
    return "\n".join(lines)


def format_today(dto, server_name: str, *, fold_limit: int = 7) -> str:
    """world today 日报（spec §4.5）。标题锚点 server_name = 配置名 srv.name（commands
    层供数），标题带日期（§2.1）。

    三节（今日纪录/玩家成长/据点变化）已由 ReportService 经 event_view 构造 EventView
    （名字解析后、隐藏玩家跳过），措辞经 render_event 渲染，本函数只做版式：素节头无图标；每节独立折叠 7
    （today 为节级特例，spec §2.7）；累计在线走 textkit.fmt_duration（N时M分，废 N 小时
    聚合式）。空态标题同带日期 + 素文一句。据点变化节 gamedata 锁定期自然缺席（既有屏蔽）。
    """
    title = f"📅 今日日报 · {server_name} · {dto.day}"
    if getattr(dto, "is_empty", False):
        return f"{title}\n{L('empty_day')}"
    lines = [
        title,
        "",
        f"第 {dto.world_day_start} → {dto.world_day_end} 天 · 活跃玩家 {dto.active_players}"
        f" · 峰值在线 {dto.peak_online} · 累计在线 {fmt_duration(dto.total_online_seconds)}",
    ]
    for header, items in (
        ("今日纪录", dto.records),
        ("玩家成长", dto.growth),
        ("据点变化", dto.base_changes),
    ):
        if items:
            lines.append("")
            lines.append(header)
            lines.extend(fold([f"· {render_event(x)}" for x in items], fold_limit, "条"))
    lines.append("")
    lines.append(dto.summary)
    return "\n".join(lines)


def format_player(
    dto: PlayerProfileDTO, *, strict: bool, server_name: str,
    world_mode: str, tz, now: int, is_me: bool = False,
) -> str:
    """player info / me 卡片（spec §4.10 / §4.25）。

    标题锚点主体=玩家名（is_me → `我的玩家`）；多模式补服务器锚 ` · {srv}`，单模式省略
    （§3 账号状态族，world_mode 判定与 help 尾注同源）。在线佩 🟢，离线不佩点。
    strict 双砍（同 rank 哲学）：砍本次/今日/累计/最后在线，留 Lv/在线状态/公会/首次现身。
    「最后在线」用 rel_datetime（时间戳字段全档带 HH:MM）；「首次现身」用绝对日期。
    公会名缺席（gamedata 锁定期）省整行；已隐藏角标仅 me 路径缀于首次现身行。
    """
    head = "我的玩家" if is_me else "玩家"
    title = f"👤 {head} · {dto.name}"
    if world_mode != "single":
        title += f" · {server_name}"

    if dto.online:
        status = [f"Lv{dto.level}", "🟢 在线"]
        if not strict:
            status.append(f"本次 {fmt_duration(dto.online_seconds)}")
    else:
        status = [f"Lv{dto.level}", "离线"]
        if not strict:
            status.append(f"最后在线 {rel_datetime(dto.last_seen_at, now, tz)}")

    block: list[str] = []
    if not strict:
        block.append(
            f"今日在线 {fmt_duration(dto.today_seconds)} · 累计 {fmt_duration(dto.total_seconds)}"
        )
    if dto.guild_name:
        block.append(f"公会「{dto.guild_name}」")
    first_seen = f"首次现身 {abs_date(dto.first_seen_at, tz)}"
    if is_me and dto.hidden:
        first_seen += " · 已隐藏"
    block.append(first_seen)

    return "\n".join([title, " · ".join(status), "", *block])


# rank 三变体榜名（spec §4.23）。which=time 为 today 别名；未识别值回落 today
# （命令层已把非法首词归 today，此处 mapping 兜底防越界）。
_RANK_TITLE = {
    "today": "今日在线时长榜",
    "time": "今日在线时长榜",
    "total": "累计在线时长榜",
    "level": "等级榜",
}


def format_rank(dto: RankBoardsDTO, *, which: str, server_name: str) -> str:
    """rank 单榜三变体（spec §4.23）。标题锚点 server_name = 配置名 srv.name（commands 层供数）。

    strict 隐私模式的双砍（today/total 时长榜拒渲染）在 commands 层完成——rank_duration_strict
    直返先于本函数调用（真正的守卫落点），故本函数不接 strict、只渲染实际单榜；level 不受影响。
    名次序号 `1. `/`2. ` 纯渲染零成本；时长走 textkit.fmt_duration。total 变体附脚注
    `└ 统计范围为数据留存期`。空榜=标题锚点 + 素文 rank_empty（无脚注）。
    """
    board = which if which in _RANK_TITLE else "today"
    title = f"🏆 {_RANK_TITLE[board]} · {server_name}"
    if board == "level":
        rows = [f"{i}. {name} Lv{lv}" for i, (name, lv) in enumerate(dto.level_rows, 1)]
    else:
        source = dto.total_rows if board == "total" else dto.time_rows
        rows = [f"{i}. {name} {fmt_duration(secs)}" for i, (name, secs) in enumerate(source, 1)]
    if not rows:
        return f"{title}\n{L('rank_empty')}"
    lines = [title, *rows]
    if board == "total":
        lines.append("└ 统计范围为数据留存期")
    return "\n".join(lines)


def format_rank_climb(dto: RankClimbDTO, *, server_name: str) -> str:
    """rank climb 飞升榜（spec §7）：周窗 level 涨幅榜，标题锚点 server_name。

    行 `1. {name} +{gain} 级`；口径脚注随 shallow 分叉（历史不足 7 天时诚实标「自 bot
    记录以来」）；末尾「你第 N，离前一位差 X 级」为调用方本人榜位（榜首无差）。空榜=标题 +
    素文（无脚注、无本人榜位）。gain 恒 > 0（query 层已剔零/负增量），此处纯渲染。"""
    title = f"🚀 飞升榜 · {server_name}"
    if not dto.rows:
        return f"{title}\n{L('rank_climb_empty')}"
    rows = [f"{i}. {e.name} +{e.gain} 级" for i, e in enumerate(dto.rows, 1)]
    lines = [title, *rows]
    lines.append(
        "└ 涨幅自 bot 开始记录以来（历史不足 7 天）" if dto.shallow
        else "└ 统计近 7 天等级涨幅"
    )
    if dto.viewer_rank is not None:
        if dto.viewer_gap is None:
            lines.append(f"你第 {dto.viewer_rank}，已登顶飞升榜 🎉")
        else:
            lines.append(f"你第 {dto.viewer_rank}，离前一位差 {dto.viewer_gap} 级")
    return "\n".join(lines)
