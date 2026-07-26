from __future__ import annotations

from ..application.dtos import (
    BaseDetailDTO,
    BaseDTO,
    DexProgressDTO,
    EventView,
    GuildDetailDTO,
    GuildDTO,
    MeCardDTO,
    OnlineDTO,
    RankClimbDTO,
    RulesDTO,
    ServerStatusRow,
    StatusDTO,
    WorldSummaryDTO,
)
from ..application.query_service import PlayerProfileDTO, RankBoardsDTO
from ..config import SkippedServer
from ..domain.enums import ActionCategory
from ..presentation.event_wording import render_event
from ..presentation.locale import MESSAGES, L
from ..presentation.textkit import (
    abs_date,
    fmt_duration,
    fold,
    rel_date,
    rel_date_key,
    rel_datetime,
    time_of_day,
)
from ..shared.command_permissions import effective_enabled
from ..shared.command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    ActionSpec,
)

# 七映射表已全量抽键入 locale（i18n §3.5）：ping_* / confidence_* / action_* /
# element_* / skip_reason_* / help_group_* / rank_title_*，消费处经 L(f"…_{key}") 渲染。
# 行为分布中文（原 _ACTION_CAT_LABEL）→ action_*：ActionCategory 9 档（细分工种数据面
# 不存在，不臆造「伐木/搬运」）；理论外值优雅回落原键（不炸/不臆造）。

# 车间现场行为 emoji（spec §6）：与 action_* 同键、按枚举定序渲染（⛏工作/🚬摸鱼…）。
_ACTION_CAT_EMOJI = {
    ActionCategory.WORKING: "⛏", ActionCategory.MOVING: "🚶",
    ActionCategory.IDLE: "💤", ActionCategory.SLACKING: "🚬",
    ActionCategory.COMBAT: "⚔️",
    ActionCategory.SLEEPING: "🛌", ActionCategory.EATING: "🍖",
    ActionCategory.INCAPACITATED: "💫", ActionCategory.UNKNOWN: "❓",
}

# 车间氛围（spec §6）：mood 稳定键白名单（越界值防御回落 fired_up）；徽章/吐槽措辞在 locale。
_MOODS = ("fired_up", "slacking_off")

# 性能流畅度稳定键 → 状态色点（spec §2.2/§4.1）：smooth🟢 / moderate🟡 / laggy·very_laggy🔴。
# 键为 query_status 产出的稳定键（DTO 不再带中文）；文案经 L(f"smoothness_{key}") 渲染。
_SMOOTH_DOT = {"smooth": "🟢", "moderate": "🟡", "laggy": "🔴", "very_laggy": "🔴"}

def _label_or_key(prefix: str, key: str) -> str:
    """理论外键优雅回落原键（不炸/不臆造）：`L(f"{prefix}_{key}")` 前先查 zh 基线 MESSAGES；
    缺键（如未收录元素/未归类动作）返回原始 key，复现旧 `.get(k, k)` 回落语义（i18n §3.5）。"""
    full = f"{prefix}_{key}"
    return L(full) if full in MESSAGES else key


def _companion_action(value: str) -> str:
    """随身动作中文：OtomoPal 的 Action 字段常为空 / AI_Action=OtomoFollow 未归类 → UNKNOWN。
    此时给「随行」而非「未知」（随身默认跟随主人；与图片卡 card_render 一致）。"""
    if value in ("unknown", ""):
        return L("companion_following")
    return _label_or_key("action", value)


def format_degraded(last_ok: int | None, now: int, server_name: str) -> str:
    """降级态两行（spec §3/§4.1）：标题锚点全局统一 `🌍 世界状态 · {服务器名}`（不随
    发起命令变化）+ 🔴 状态行。last_ok=None 为「从未成功」句；否则「最后成功于 N 分钟前」。
    """
    if last_ok is None:
        status = L("degraded_never")
    else:
        minutes = max(0, (now - last_ok) // 60)
        status = L("degraded", minutes=minutes)
    return f"{L('status_title')} · {server_name}\n{status}"


def format_online(
    dto: OnlineDTO, server_name: str, *, strict: bool = False, fold_limit: int = 7,
) -> str:
    """online 当前在线（spec §4.24）。标题锚点 server_name = 配置名 srv.name（commands 层供数）。

    头行在线数分子 = 收敛后名单数 len(dto.rows)（spec §3 隐私收敛——与名单行数必然同数，
    T3 seam 在此闭合，杜绝「在线 3」却只列 2 人的存在性泄漏）；/max 容量取 dto.max_players、
    今日峰值取 dto.peak_online（metric 聚合值，不可归因，保留）。strict 砍时长字段（名/Lv/Ping
    保留，同 rank/me 双砍哲学）。空态收编 locale online_empty。>7 折叠尾行「…等共 N 人」。
    """
    title = f"{L('online_title')} · {server_name}"
    if not dto.rows:
        return f"{title}\n{L('online_empty')}"
    entries: list[str] = []
    for r in dto.rows:
        cells = [f"{r.name} Lv{r.level}", f"Ping {L(f'ping_{r.ping_bucket.value}')}"]
        if not strict:
            cells.append(fmt_duration(r.online_seconds))
        entries.append("· " + " · ".join(cells))
    lines = [
        title,
        L("common_online_peak", online=len(dto.rows), max=dto.max_players, peak=dto.peak_online),
        "",
        *fold(entries, fold_limit, L("quantifier_person")),
    ]
    return "\n".join(lines)


def format_guilds(
    dto: list[GuildDTO], server_name: str, *, strict: bool = False, fold_limit: int = 7,
) -> str:
    """guild list（spec §4.6）。标题锚点=服务器名（commands 层供数）。每公会成员~/工作帕鲁/
    据点数（PalBox 归 overview 设施节，此处不渲染；active_7d 砍位）。strict=字段级裁剪：
    砍「据点 N」计数位，公会本体保留（命令仍产出，非拒执行）。空态素文；>7 折叠「…等共 N 个」。"""
    title = f"{L('guild_title')} · {server_name}"
    if not dto:
        return f"{title}\n{L('guilds_empty')}"
    entries: list[str] = []
    for g in dto:
        cells = [
            f"{g.name} {L('guild_members', n=g.observed_members)}",
            L("guild_work_pals", n=g.base_pals),
        ]
        if not strict:
            cells.append(L("common_base_count", n=g.base_count))
        entries.append("· " + " · ".join(cells))
    lines = [title, "", *fold(entries, fold_limit, L("quantifier_item"))]
    lines.append(L("guilds_footer"))
    return "\n".join(lines)


def format_guild(
    dto: GuildDetailDTO, *, strict: bool, now: int, tz, fold_limit: int = 7,
) -> str:
    """guild info（spec §4.7）。标题锚点=公会名 dto.name。首次观察=绝对日期；最近=相对
    日期词表（时间戳字段全档带 HH:MM）。据点节 + 近期动态节实填（近期动态经 render_event
    渲染，query 层已构造 EventView）。恒 0 占位（active_*/average_level）与 PalBox 砍位。
    strict=字段级裁剪：省略据点节 + 近期动态节 + 首行「据点 N」计数（据点类不经本命令绕出
    strict）；公会本体（成员/工作帕鲁/首次观察/最近）保留。"""
    head = [L("guild_members", n=dto.observed_members), L("guild_work_pals", n=dto.base_pals)]
    if not strict:
        head.append(L("common_base_count", n=dto.base_count))
    lines = [
        f"{L('guild_title')} · {dto.name}",
        " · ".join(head),
        L("guild_seen",
          first=abs_date(dto.first_seen_at, tz),
          last=rel_datetime(dto.last_seen_at, now, tz)),
    ]
    if not strict:
        if dto.bases:
            lines.append("")
            lines.append(L("guild_section_bases"))
            lines.extend(fold(
                [f"· {name} {L('base_confidence', conf=L(f'confidence_{conf.value}'))}"
                 for name, conf in dto.bases],
                fold_limit, L("quantifier_item"),
            ))
        if dto.recent_events:
            lines.append("")
            lines.append(L("guild_section_events"))
            lines.extend(fold(
                [f"· {render_event(ev)}" for ev in dto.recent_events],
                fold_limit, L("quantifier_entry"),
            ))
    return "\n".join(lines)


def format_bases(dto: list[BaseDTO], server_name: str, *, fold_limit: int = 7) -> str:
    """guild bases（spec §4.8）。标题锚点=服务器名（commands 层供数）。按公会分组（未归属→
    「未确定公会」）；每据点 #序号（T5 统一含 low 序号空间）+ 置信度 + worker_count 实填
    （>0 才渲染，无观测据点省该位）；hidden 恒不入清单；全局折叠（textkit.fold 单一尾行
    格式「…等共 N 个」，共用 cfg.players.list_fold_limit）。空态素文。"""
    title = f"{L('base_title')} · {server_name}"
    if not dto:
        return f"{title}\n{L('bases_empty')}"
    visible = dto[:fold_limit]
    # 折叠尾行经 textkit.fold 生成（与其它列表共用同一限额与「…等共 N 个」尾格式）：
    # 分组渲染用 visible，尾行只取 fold 汇总部分（未折叠时为空）。
    tail = fold([b.display_name for b in dto], fold_limit, L("quantifier_item"))[len(visible):]
    lines = [title]
    current_guild: str | None = None
    for b in visible:
        guild = b.guild_name or L("base_guild_unknown")
        if guild != current_guild:
            lines.append("")
            lines.append(guild)
            current_guild = guild
        cells = [
            f"#{b.index} {b.display_name} "
            f"{L('base_confidence', conf=L(f'confidence_{b.confidence.value}'))}"
        ]
        if b.worker_count > 0:
            cells.append(L("guild_work_pals", n=b.worker_count))
        lines.append("· " + " · ".join(cells))
    lines.extend(tail)
    lines.append(L("bases_footer"))
    return "\n".join(lines)


def _health_status(score: float) -> tuple[str, str]:
    """健康度 → 状态点+词（spec §4.9）：🟢 健康 ≥75 / 🟡 一般 ≥40 / 🔴 低迷 <40。"""
    if score >= 75:
        return "🟢", L("health_good")
    if score >= 40:
        return "🟡", L("health_ok")
    return "🔴", L("health_low")


def format_base(dto: BaseDetailDTO) -> str:
    """guild base 车间现场（spec §4.9 / §6）。标题锚点=据点名 dto.display_name。

    健康度→状态点+词；**氛围徽章**（🔥热火朝天/😴集体摆烂，按 dto.mood 稳定键取 locale 模板）
    + 一句吐槽；**摸鱼行**（🚬 摸鱼率 N%，dto.slacker_rate 派生）；行为分布以 emoji 呈现
    （⛏工作中/🚬摸鱼…，有计数者按枚举定序）；物种 Top（就近可见快照聚合）。
    C2 口径：只报「此刻可见 N 只」（非「共有」）；脚注标观察推导（C4）。activity_score 裸数与
    palbox_count 砍位。available=False（无观测）→ ⚠️ 取数失败态（不再全 0 假数据，§6#8）。"""
    title = f"{L('base_title')} · {dto.display_name}"
    guild = L("guild_label", name=dto.guild_name) if dto.guild_name else L("base_guild_unknown")
    ident = f"{guild} · {L('base_confidence', conf=L(f'confidence_{dto.confidence.value}'))}"
    if not dto.available:
        return f"{title}\n{ident}\n{L('base_no_observation')}"
    dot, word = _health_status(dto.health_score)
    mood = dto.mood if dto.mood in _MOODS else "fired_up"  # 越界值防御回落
    lines = [
        title,
        ident,
        f"{L(f'base_badge_{mood}')} · {L(f'base_snark_{mood}')}",
        "",
        # C2：只报此刻可见（就近可见快照），不吹「共有」。
        L("base_visible_stats",
          visible=dto.worker_count, active=dto.active_count,
          level=f"{dto.average_level:.1f}"),
        L("base_status_line", dot=dot, word=word, hp=f"{dto.average_hp_ratio:.0%}"),
        L("base_slacker_rate", rate=f"{dto.slacker_rate:.0%}"),
    ]
    dist = [
        f"{_ACTION_CAT_EMOJI[cat]}{dto.action_distribution[cat.value]} {L(f'action_{cat.value}')}"
        for cat in ActionCategory
        if dto.action_distribution.get(cat.value, 0) > 0
    ]
    if dist:
        lines.append("")
        lines.append(L("base_section_actions"))
        lines.append("· " + " · ".join(dist))
    if dto.species_top:
        lines.append("")
        # C2 作用域披露：species_top 按公会名聚合（含本公会全部据点），非本据点独有——
        # 表头显式标「本公会此刻可见」，与上方本据点「此刻可见 N 只」区分，杜绝多据点合计 > N 的自相矛盾。
        lines.append(L("base_section_species"))
        lines.append("· " + " · ".join(f"{name} ×{count}" for name, count in dto.species_top))
    lines.append(L("base_footer"))
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
    title = (
        f"{L('events_title_today')} · {server_name}" if today_only
        else f"{L('events_title')} · {server_name}"
    )
    if not events:
        empty = L("events_empty_today") if today_only else L("events_empty")
        return f"{title}\n{empty}"

    # 消息级折叠：截前 fold_limit 条渲染，尾行经 textkit.fold 复用同一「…等共 N 条」格式。
    visible = events[:fold_limit]
    tail = fold([render_event(e) for e in events], fold_limit, L("quantifier_entry"))[len(visible):]

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
            # 结构性判断（i18n §3.5）：拿 rel_date_key 档位而非本地化渲染串字面——
            # 「今天」条目附 HH:MM 的分支在 ja/en 下仍正确命中（渲染串本地化后无法字面比较）。
            if rel_date_key(e.occurred_at, now, tz) == "today":
                lines.append(f"· {time_of_day(e.occurred_at, tz)} {render_event(e)}")
            else:
                lines.append(f"· {render_event(e)}")
    lines.extend(tail)                     # 折叠尾行（未折叠时为空）
    return "\n".join(lines)


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
            dot, word = "🟡", L("server_not_ready")
        elif r.online:
            dot, word = "🟢", L("server_online")
        else:
            dot, word = "🔴", L("server_offline")
        cells = [f"{r.name} {dot} {word}"]
        if is_group:
            cells.append(L("server_authed") if r.allowed else L("server_unauthed"))
            if r.active:
                cells.append(L("server_active"))
        entries.append("· " + " · ".join(cells))
    lines = [L("link_list_title"), "", *fold(entries, fold_limit, L("quantifier_entry"))]
    if is_admin and skipped:
        lines.append("")
        lines.append(L("server_section_invalid"))
        lines.extend(
            f"· {s.raw_name}（{_label_or_key('skip_reason', s.reason)}）" for s in skipped
        )
    return "\n".join(lines)


# 命令组显示标签（分级 help / 裸组迷你帮助共用；避免英文词汇泄漏干扰功能门测试）→ help_group_*。
# 组头词表与前端设置页 GROUP_LABELS 统一定字（spec §4.26）：world/guild/player/link 同词；
# server 于聊天帮助补「（管理员）」标注（前端权限章靠锁图标呈现，无需此后缀）；flat 组=「其他」。
# 未登记组优雅回落原组名（_label_or_key）。


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
    """行式 `· /pal {路径} {描述}`（spec §4.26）：一级 `· ` 前缀，路径与描述单空格分隔。

    描述经 locale 键 `help_desc_<路径，空格转下划线>` 取；缺键（不在 zh 基线 MESSAGES 中）
    出空串——保持旧 `HELP_TEXT.get(path, "")` 的防御语义，避免把 key 本身渲进 help 输出。
    """
    key = f"help_desc_{path.replace(' ', '_')}"
    desc = L(key) if key in MESSAGES else ""
    return f"· /pal {path} {desc}" if desc else f"· /pal {path}"


def format_help(topic: str | None, is_admin: bool, overrides, world_mode: str = "multi") -> str:
    """分级 help（spec §4.26）：📖 标题 + 素节头（废【】，对齐全局素节头定案）+ 行式条目。

    角色/功能/模式过滤逻辑零改动——visible_actions 是唯一谓词（guest 不见写命令/confirm）；
    本函数只定版式与组头词表。尾注 `└ 命令末尾加 @服务器名 可指定服务器` 单模式省略（single
    下 resolve 忽略 @override，尾注是空承诺）。topic 参数维持忽略（不扩 /pal help <组>）。
    """
    lines = [L("help_title")]
    for group in DISPATCH:  # world/guild/player/server/link（插入序）
        vis = visible_actions(group, is_admin, overrides, world_mode)
        if not vis:
            continue
        lines.append("")                                      # 空行分节
        lines.append(_label_or_key("help_group", group))      # 素节头无图标/无【】
        lines.extend(_help_line(f"{group} {sub}") for sub, _spec in vis)
    flat = [name for name, spec in FLAT_ACTIONS.items()
            if _action_visible(name, spec, is_admin, overrides)]
    if flat:
        lines.append("")
        lines.append(L("help_group_flat"))
        lines.extend(_help_line(name) for name in flat)
    if world_mode != "single":                                # 单模式省略 @ 尾注（空承诺）
        lines.append("")
        lines.append(L("help_footer"))
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
    lines = [f"{L('status_title')} · {server_name}"]
    if detail is not None:
        lines.append(L(
            "status_detail_line",
            day=dto.world_day, version=detail.version,
            uptime=fmt_duration(detail.uptime_seconds),
        ))
    else:  # 防御：live 恒有 detail；缺失时仅出天数，不冒 AttributeError。
        lines.append(L("common_world_day", day=dto.world_day))
    lines.append("")
    lines.append(L("common_online_peak",
                   online=len(dto.players), max=dto.max_players, peak=dto.peak_online_today))
    dot = _SMOOTH_DOT.get(dto.smoothness_label, "🟡")
    label = L(f"smoothness_{dto.smoothness_label}")
    lines.append(L(
        "status_perf",
        dot=dot, label=label, fps=f"{dto.fps:.0f}", frame_time=f"{dto.frame_time:.1f}",
    ))
    if show_bases:
        lines.append(L("common_base_count", n=dto.basecamp_count))
    if dto.players:  # 0 人省略整节（含其上方空行）
        lines.append("")
        lines.append(L("status_section_online"))
        lines.extend(fold(
            [f"· {n} Lv{lv}" for n, lv, _ in dto.players], fold_limit, L("quantifier_person"),
        ))
    return "\n".join(lines)


def format_world(
    dto: WorldSummaryDTO, server_name: str, *, strict: bool = False, fold_limit: int = 7,
) -> str:
    """world overview 人口普查（spec §4.2）。FPS 归 status（不渲染）；据点数取官方口径。

    快照缺失（available=False）→ ⚠️ 取数失败态（不再静默全 0）。strict 下省略设施节的
    PalBox 项（保留公会/据点两计数——据点/公会为官方推导计数，非个体隐私）。
    """
    title = f"{L('world_title')} · {server_name}"
    if not dto.available:
        return f"{title}\n{L('world_snapshot_missing')}"
    lines = [
        title,
        L("world_day_online", day=dto.world_day, online=dto.online, max=dto.max_players),
        "",
        L("world_section_residents"),
        L("world_residents_chars", players=dto.players, npc=dto.npc),
        L("world_residents_pals", otomo=dto.otomo, base_pal=dto.base_pal, wild=dto.wild),
        "",
        L("world_section_facility"),
    ]
    facility = [] if strict else [f"PalBox {dto.palbox}"]
    facility.append(L("world_guilds_count", n=dto.guilds))
    facility.append(L("common_base_count", n=dto.basecamp_count))
    lines.append("· " + " · ".join(facility))
    if dto.wild_top:
        lines.append("")
        lines.append(L("world_section_wild_top"))
        lines.extend(fold(
            [f"· {w.name} ×{w.count}" for w in dto.wild_top], fold_limit, L("quantifier_species"),
        ))
    return "\n".join(lines)


def _rule_cell(label_key: str, value: str, kind: str) -> str:
    """规则单元格 `标签 值`（i18n §3.2）：标签经 L() 稳定键取措辞；值按 kind 组装单位——
    rate 补 ASCII x（1.0→1.0x）、hours/minutes 经单位词键、enum/int 值即成品（enum 经
    query 侧 setting_display，int 裸数）。策展措辞在此唯一落点，不再由 application 预渲染。"""
    label = L(label_key)
    if kind == "rate":
        rendered = f"{value}x"
    elif kind == "hours":
        rendered = L("rules_unit_hours", num=value)
    elif kind == "minutes":
        rendered = L("rules_unit_minutes", num=value)
    else:  # enum / int
        rendered = value
    return f"{label} {rendered}"


def format_rules(dto: RulesDTO, server_name: str) -> str:
    """world rules 策展分节（spec §4.3）。同类字段两两并一行 `· A · B`。

    快照缺失（available=False）→ ⚠️ 取数失败态。隐私模式注两句分叉走脚注 `└ `。
    节标题/标签/单位词/隐私注记均为 presentation locale 稳定键，经 L() 渲染（i18n §3.2）；
    游戏设定原值（蛋孵化 72 小时 / 空投间隔 180 分钟）保游戏原单位（§2.4 豁免）。
    """
    title = f"{L('rules_title')} · {server_name}"
    if not dto.available:
        return f"{title}\n{L('rules_unavailable')}"
    lines = [title]
    for sec in dto.sections:
        lines.append("")
        lines.append(L(sec.title))
        cells = [_rule_cell(label_key, value, kind) for label_key, value, kind in sec.items]
        for i in range(0, len(cells), 2):
            lines.append("· " + " · ".join(cells[i:i + 2]))
    if dto.privacy_note:
        lines.append(f"└ {L(dto.privacy_note)}")
    return "\n".join(lines)


def format_today(dto, server_name: str, *, fold_limit: int = 7) -> str:
    """world today 日报（spec §4.5）。标题锚点 server_name = 配置名 srv.name（commands
    层供数），标题带日期（§2.1）。

    三节（今日纪录/玩家成长/据点变化）已由 ReportService 经 event_view 构造 EventView
    （名字解析后、隐藏玩家跳过），措辞经 render_event 渲染，本函数只做版式：素节头无图标；每节独立折叠 7
    （today 为节级特例，spec §2.7）；累计在线走 textkit.fmt_duration（N时M分，废 N 小时
    聚合式）。空态标题同带日期 + 素文一句。据点变化节 gamedata 锁定期自然缺席（既有屏蔽）。
    """
    title = f"{L('today_title')} · {server_name} · {dto.day}"
    if getattr(dto, "is_empty", False):
        return f"{title}\n{L('empty_day')}"
    lines = [
        title,
        "",
        L("today_summary",
          start=dto.world_day_start, end=dto.world_day_end, active=dto.active_players,
          peak=dto.peak_online, online=fmt_duration(dto.total_online_seconds)),
    ]
    for header, items in (
        (L("today_section_records"), dto.records),
        (L("today_section_growth"), dto.growth),
        (L("today_section_bases"), dto.base_changes),
    ):
        if items:
            lines.append("")
            lines.append(header)
            lines.extend(fold(
                [f"· {render_event(x)}" for x in items], fold_limit, L("quantifier_entry"),
            ))
    lines.append("")
    lines.append(_report_summary(dto))
    return "\n".join(lines)


def _report_summary(dto) -> str:
    """末行编辑部总结渲染（i18n §3.2）：application 只产 summary_kind + 计数，措辞拼装在此。
    quiet_day → 「平静的一天」；editorial → 「今天：N 名新玩家加入，N 次成长，N 处据点变化。」
    （无事件但有活跃玩家时回落在线活跃句）。逐字复现旧 ReportService._summary。"""
    if dto.summary_kind == "quiet_day":
        return L("report_quiet_day")
    parts: list[str] = []
    if dto.new_players:
        parts.append(L("report_new_players", n=dto.new_players))
    if dto.growth:
        parts.append(L("report_growth", n=len(dto.growth)))
    if dto.base_changes:
        parts.append(L("report_base_changes", n=len(dto.base_changes)))
    if not parts and dto.active_players:
        parts.append(L("report_active", n=dto.active_players))
    return L("report_summary", body=L("report_summary_sep").join(parts))


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
    head = L("player_head_me") if is_me else L("player_head")
    title = f"👤 {head} · {dto.name}"
    if world_mode != "single":
        title += f" · {server_name}"

    if dto.online:
        status = [f"Lv{dto.level}", L("player_online")]
        if not strict:
            status.append(L("player_session", duration=fmt_duration(dto.online_seconds)))
    else:
        status = [f"Lv{dto.level}", L("player_offline")]
        if not strict:
            status.append(L("player_last_seen", time=rel_datetime(dto.last_seen_at, now, tz)))

    block: list[str] = []
    if not strict:
        block.append(L("common_today_total",
                       today=fmt_duration(dto.today_seconds),
                       total=fmt_duration(dto.total_seconds)))
    if dto.guild_name:
        block.append(L("guild_label", name=dto.guild_name))
    first_seen = L("player_first_seen", date=abs_date(dto.first_seen_at, tz))
    if is_me and dto.hidden:
        first_seen += f" · {L('player_hidden_suffix')}"
    block.append(first_seen)

    return "\n".join([title, " · ".join(status), "", *block])


def _days_ago_label(days: int) -> str:
    """距今天数（MeCardDTO.last_seen_at/first_seen_at 已预粗化为 int，0=今天）→ 词形
    「今天」/「N天前」（spec §5·隐私 P1）。**绝不 fromtimestamp**——入参是天数差非 epoch，
    当时间戳会显 1970 乱数据 + 泄漏绝对登录时刻（作息）。负值防御归 0（今天）。"""
    n = max(int(days), 0)
    return L("days_ago_today") if n == 0 else L("days_ago_n", n=n)


def format_me(dto: MeCardDTO) -> str:
    """/pal me 文字版名片（spec §5·功能①）：消费 MeCardDTO，四状态文字渲染。

    状态优先级：online==False → 离线卡（无实时血量/随身，最近上线走距今天数、累计在线）；
    否则在线卡（等级/公会/百分位「超越有记录玩家 X%」/本次·今日·累计时长）+ 随身三态——
    companion_status: shown → 随身高光行（物种（元素）Lv/HP%/状态）；none_out →「此刻未带出
    随身帕鲁」；no_data →「随身数据暂不可用（需启用 guilds_bases）」（**绝不谎称没带**，C2）。

    时间字段（last_seen_at/first_seen_at）是**距今天数 int**（T6 已预粗化），经 _days_ago_label
    渲染，绝不当 epoch（隐私 P1，无绝对时间戳）。签名仅收 dto——百分位/时长/天数皆自足，
    无需 now/tz/server_name（同图片版 build_me_card_html 的 DTO 自足边界）。
    """
    title = f"{L('me_card_title')} · {dto.name}"

    if not dto.online:
        # 离线卡：无实时状态点、无随身/血量；最近上线走距今天数（非绝对时刻）+ 累计在线。
        lines = [
            title,
            f"Lv{dto.level} · {L('me_card_offline')}",
            "",
            L("me_card_last_online",
              days=_days_ago_label(dto.last_seen_at),
              total=fmt_duration(dto.total_seconds)),
        ]
        if dto.guild_name:
            lines.append(L("guild_label", name=dto.guild_name))
        if dto.hidden:
            lines.append(L("me_card_hidden"))
        return "\n".join(lines)

    # 在线卡：状态点 🟢 + 本次在线 + 百分位（hero）+ 今日/累计 + 公会 + 随身三态。
    lines = [
        title,
        f"Lv{dto.level} · {L('me_card_online_status', session=fmt_duration(dto.online_seconds))}",
        "",
        L("me_card_percentile", pct=f"{dto.percentile:.0f}"),
        L("common_today_total",
          today=fmt_duration(dto.today_seconds), total=fmt_duration(dto.total_seconds)),
    ]
    if dto.guild_name:
        lines.append(L("guild_label", name=dto.guild_name))

    if dto.companion_status == "shown" and dto.companion is not None:
        c = dto.companion
        element = _label_or_key("element", c.element)
        action = _companion_action(c.action_label)
        lines.append(L(
            "me_card_companion",
            name=c.species_name, element=element, level=c.level,
            hp=f"{c.hp_ratio:.0%}", action=action,
        ))
    elif dto.companion_status == "none_out":
        lines.append(L("me_card_none_out"))
    else:  # no_data（无快照/本人不在快照/game-data 未轮询）——绝不谎称没带
        lines.append(L("me_card_no_data"))

    if dto.hidden:
        lines.append(L("me_card_hidden"))
    return "\n".join(lines)


# rank 三变体榜名（spec §4.23）→ rank_title_*（today/time/total/level）。which=time 为 today
# 别名；未识别值回落 today（命令层已把非法首词归 today，此处以 locale 键存在性兜底防越界）。


def format_rank(dto: RankBoardsDTO, *, which: str, server_name: str) -> str:
    """rank 单榜三变体（spec §4.23）。标题锚点 server_name = 配置名 srv.name（commands 层供数）。

    strict 隐私模式的双砍（today/total 时长榜拒渲染）在 commands 层完成——rank_duration_strict
    直返先于本函数调用（真正的守卫落点），故本函数不接 strict、只渲染实际单榜；level 不受影响。
    名次序号 `1. `/`2. ` 纯渲染零成本；时长走 textkit.fmt_duration。total 变体附脚注
    `└ 统计范围为数据留存期`。空榜=标题锚点 + 素文 rank_empty（无脚注）。
    """
    board = which if f"rank_title_{which}" in MESSAGES else "today"
    title = f"🏆 {L(f'rank_title_{board}')} · {server_name}"
    if board == "level":
        rows = [f"{i}. {name} Lv{lv}" for i, (name, lv) in enumerate(dto.level_rows, 1)]
    else:
        source = dto.total_rows if board == "total" else dto.time_rows
        rows = [f"{i}. {name} {fmt_duration(secs)}" for i, (name, secs) in enumerate(source, 1)]
    if not rows:
        return f"{title}\n{L('rank_empty')}"
    lines = [title, *rows]
    if board == "total":
        lines.append(L("rank_footer_total"))
    return "\n".join(lines)


def format_rank_climb(dto: RankClimbDTO, *, server_name: str) -> str:
    """rank climb 飞升榜（spec §7）：周窗 level 涨幅榜，标题锚点 server_name。

    行 `1. {name} +{gain} 级`；口径脚注随 shallow 分叉（历史不足 7 天时诚实标「自 bot
    记录以来」）；末尾「你第 N，离前一位差 X 级」为调用方本人榜位（榜首无差）。空榜=标题 +
    素文（无脚注、无本人榜位）。gain 恒 > 0（query 层已剔零/负增量），此处纯渲染。"""
    title = f"{L('rank_climb_title')} · {server_name}"
    if not dto.rows:
        return f"{title}\n{L('rank_climb_empty')}"
    rows = [L("rank_climb_row", rank=i, name=e.name, gain=e.gain)
            for i, e in enumerate(dto.rows, 1)]
    lines = [title, *rows]
    lines.append(
        L("rank_climb_footer_shallow") if dto.shallow
        else L("rank_climb_footer")
    )
    if dto.viewer_rank is not None:
        if dto.viewer_gap is None:
            lines.append(L("rank_climb_viewer_top", rank=dto.viewer_rank))
        else:
            lines.append(L("rank_climb_viewer_gap", rank=dto.viewer_rank, gap=dto.viewer_gap))
    return "\n".join(lines)


def format_dex(dto: DexProgressDTO) -> str:
    """服务器图鉴进度（spec §8·功能④）：本插件曾观测到的**去重**物种进度，按元素分桶。

    口径「本插件已观测」（observed_species 跨插件全局累积、无 world_id，非本服/全服全部物种，
    C2）；「曾被观测到」≠「服上存在全物种」（末尾脚注钉死）。分母已知 → 「已观测 N/总数 种」
    + 每元素缺失清单（「尚未被观测」）；分母未知（roster 不完整）→ 降级为「已观测 N 种」+ 仅
    已点亮列表，**不显分母、不出缺失**（SD5：分母与缺失绑同一前置一起降级）。空图鉴 → 素文。
    元素中文经 element_* locale 键渲染（unknown/理论外键优雅回落原键，不炸）。
    标题**不带服名**：observed_species 无 world_id、跨插件全局累积，per-server 锚点会误导口径。"""
    title = L("dex_title")
    if not dto.buckets:
        return f"{title}\n{L('dex_empty')}"
    head = (
        L("dex_progress", observed=dto.observed_count, total=dto.total)
        if dto.total is not None
        else L("dex_progress_degraded", observed=dto.observed_count)
    )
    lines = [title, head, ""]
    for b in dto.buckets:
        elem = _label_or_key("element", b.element)
        lit = "、".join(b.observed) if b.observed else "—"
        lines.append(f"{elem} {len(b.observed)}：{lit}")
        if b.missing:   # 缺失仅分母已知时非空（降级恒空）
            lines.append(f"　└ {L('dex_missing')}：{'、'.join(b.missing)}")
    lines.append(L("dex_note"))
    return "\n".join(lines)
