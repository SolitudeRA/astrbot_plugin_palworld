from __future__ import annotations

from ..application.command_permissions import effective_enabled
from ..application.query_service import PlayerProfileDTO, RankBoardsDTO
from ..config import SkippedServer
from ..domain.enums import Confidence, PingBucket
from ..presentation.command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    HELP_TEXT,
    ActionSpec,
)
from ..presentation.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventDTO,
    GuildDetailDTO,
    GuildDTO,
    OnlineDTO,
    RulesDTO,
    ServerStatusRow,
    StatusDTO,
    WorldSummaryDTO,
)
from ..presentation.locale import L
from ..presentation.textkit import fmt_duration, fold, rel_date, time_of_day

_PING_LABEL = {
    PingBucket.GOOD: "优秀", PingBucket.OK: "正常",
    PingBucket.HIGH: "偏高", PingBucket.UNKNOWN: "未知",
}
_CONF_LABEL = {Confidence.HIGH: "高", Confidence.MEDIUM: "中", Confidence.LOW: "低"}

# 性能流畅度档位 → 状态色点（spec §2.2/§4.1）：流畅🟢 / 一般🟡 / 卡顿·严重卡顿🔴。
_SMOOTH_DOT = {"流畅": "🟢", "一般": "🟡", "卡顿": "🔴", "严重卡顿": "🔴"}


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(max(seconds, 0), 3600)
    m = rem // 60
    if h:
        return f"{h}小时{m}分"
    return f"{m}分"


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


def format_online(dto: OnlineDTO) -> str:
    if not dto.rows:
        return "当前无玩家在线。"
    lines = ["当前在线玩家："]
    for r in dto.rows:
        ping = _PING_LABEL[r.ping_bucket]
        lines.append(f"· {r.name} Lv{r.level} · Ping {ping} · 在线 {_fmt_duration(r.online_seconds)}")
    return "\n".join(lines)


def format_guilds(dto: list[GuildDTO]) -> str:
    if not dto:
        return L("guilds_unavailable")
    lines = ["世界公会（已观察/推导）："]
    for g in dto:
        lines.append(
            f"· {g.name} · 成员~{g.observed_members} · PalBox {g.palbox} · "
            f"工作帕鲁 {g.base_pals} · 近7日活跃 {g.active_7d}"
        )
    return "\n".join(lines)


def format_guild(dto: GuildDetailDTO) -> str:
    lines = [
        f"公会：{dto.name}（已观察/推导）",
        f"观察成员：~{dto.observed_members} · 当日活跃 {dto.active_today} · 当周活跃 {dto.active_week}",
        f"PalBox {dto.palbox} · 工作帕鲁 {dto.base_pals} · 平均等级 {dto.average_level:.1f}",
    ]
    if dto.base_event_lines:
        lines.append("据点变化：")
        lines.extend(f"  · {line}" for line in dto.base_event_lines)
    return "\n".join(lines)


def format_bases(dto: list[BaseDTO]) -> str:
    if not dto:
        return "暂无可展示的据点（插件推导）。"
    lines = ["据点列表（插件推导）："]
    for b in dto:
        guild = b.guild_name or "未确定公会"
        lines.append(f"#{b.index} {b.display_name} · {guild} · 置信度 {_CONF_LABEL[b.confidence]}")
    return "\n".join(lines)


def format_base(dto: BaseDetailDTO) -> str:
    guild = dto.guild_name or "未确定公会"
    dist = "、".join(f"{k}:{v}" for k, v in dto.action_distribution.items()) or "无"
    return "\n".join([
        f"据点：{dto.display_name}（插件推导）",
        f"所属公会：{guild} · 置信度 {_CONF_LABEL[dto.confidence]} · PalBox {dto.palbox_count}",
        f"工作帕鲁 {dto.worker_count} · 活跃 {dto.active_count} · 平均等级 {dto.average_level:.1f}",
        f"平均HP比 {dto.average_hp_ratio:.0%} · 活跃度 {dto.activity_score:.1f} · 健康度 {dto.health_score:.1f}",
        f"Action 分布：{dist}",
    ])


def format_events(
    events: list[EventDTO], server_name: str, *,
    now: int, tz, today_only: bool, fold_limit: int,
) -> str:
    """world events（spec §4.4）。标题锚点 server_name = 配置名 srv.name（commands 层供数）。

    events 已由 query 层隐藏收敛 + 名字解析 + 八类措辞渲染（EventDTO.summary），按 occurred_at
    DESC 排列。本函数只做呈现：日分组 / 仅今天条目带 HH:MM / 消息级折叠 / 空态两变体。

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
    tail = fold([e.summary for e in events], fold_limit, "条")[len(visible):]

    lines = [title]
    if today_only:
        lines.append("")
        lines.extend(f"· {time_of_day(e.occurred_at, tz)} {e.summary}" for e in visible)
    else:
        current_day: str | None = None
        for e in visible:
            day = rel_date(e.occurred_at, now, tz)
            if day != current_day:
                lines.append("")          # 空行分节（含标题与首节之间）
                lines.append(day)         # 素节头无图标
                current_day = day
            if day == "今天":
                lines.append(f"· {time_of_day(e.occurred_at, tz)} {e.summary}")
            else:
                lines.append(f"· {e.summary}")
    lines.extend(tail)                     # 折叠尾行（未折叠时为空）
    return "\n".join(lines)


def format_servers(
    rows: list[ServerStatusRow], skipped: list[SkippedServer], is_admin: bool
) -> str:
    if not rows and not skipped:
        return L("no_server_configured")
    lines = ["已配置服务器："]
    for r in rows:
        ready = "就绪" if r.ready else "未就绪"
        online = "在线" if r.online else "离线"
        allowed = "已授权" if r.allowed else "未授权"
        active = " ·活动" if r.active else ""
        lines.append(f"· {r.name} · {ready}/{online} · 本群{allowed}{active}")
    if is_admin and skipped:
        lines.append("⚠ 被跳过的无效服务器配置：")
        lines.extend(f"  · {s.raw_name}（{s.reason}）" for s in skipped)
    return "\n".join(lines)


# 命令组显示标签（分级 help / 裸组迷你帮助共用；避免英文词汇泄漏干扰功能门测试）。
_GROUP_LABEL: dict[str, str] = {
    "world": "世界查询",
    "guild": "公会与据点",
    "player": "玩家",
    "server": "服务器管控（管理员）",
    "link": "服务器选择",
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
    desc = HELP_TEXT.get(path, "")
    return f"/pal {path}  {desc}" if desc else f"/pal {path}"


def format_help(topic: str | None, is_admin: bool, overrides, world_mode: str = "multi") -> str:
    lines = ["PalWorldTerminal 命令："]
    for group in DISPATCH:  # world/guild/player/server/link（插入序）
        vis = visible_actions(group, is_admin, overrides, world_mode)
        if not vis:
            continue
        lines.append(f"【{_GROUP_LABEL.get(group, group)}】")
        lines.extend(_help_line(f"{group} {sub}") for sub, _spec in vis)
    flat = [name for name, spec in FLAT_ACTIONS.items()
            if _action_visible(name, spec, is_admin, overrides)]
    if flat:
        lines.append(f"【{_FLAT_LABEL}】")
        lines.extend(_help_line(name) for name in flat)
    lines.append("提示：命令末尾可加 @服务器名 指定服务器。")
    return "\n".join(lines)


def format_status(dto: StatusDTO, server_name: str, *, show_bases: bool = True) -> str:
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
        lines.extend(fold([f"· {n} Lv{lv}" for n, lv, _ in dto.players], 7, "人"))
    return "\n".join(lines)


def format_world(dto: WorldSummaryDTO, server_name: str, *, strict: bool = False) -> str:
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
        lines.extend(fold([f"· {w.name} ×{w.count}" for w in dto.wild_top], 7, "种"))
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


def format_today(dto) -> str:
    if getattr(dto, "is_empty", False):
        return L("empty_day")
    hours = dto.total_online_seconds // 3600
    lines = [
        f"今日日报 · {dto.day}",
        f"世界天数：第 {dto.world_day_start} → {dto.world_day_end} 天",
        f"活跃玩家 {dto.active_players} · 最高同时在线 {dto.peak_online} · 累计观察在线 {hours} 小时",
    ]
    if dto.records:
        lines.append("今日纪录：")
        lines.extend(f"  · {r}" for r in dto.records)
    if dto.level_events:
        lines.append("玩家成长：")
        lines.extend(f"  · {e}" for e in dto.level_events)
    if dto.base_events:
        lines.append("据点变化：")
        lines.extend(f"  · {e}" for e in dto.base_events)
    lines.append(dto.summary)
    return "\n".join(lines)


def format_player(dto: PlayerProfileDTO, *, strict: bool) -> str:
    lines = [f"玩家 {dto.name}", f"· 等级 Lv{dto.level}",
             f"· 状态 {'在线' if dto.online else '离线'}"]
    if not strict and dto.online:
        lines.append(f"· 本次在线 {_fmt_duration(dto.online_seconds)}")
    return "\n".join(lines)


def format_rank(dto: RankBoardsDTO, *, which: str, strict: bool) -> str:
    blocks: list[str] = []
    if which in ("both", "today", "time") and not strict and dto.time_rows:
        lines = ["今日在线时长榜："]
        for name, secs in dto.time_rows:
            lines.append(f"· {name} {_fmt_duration(secs)}")
        blocks.append("\n".join(lines))
    # total 同为时长榜,strict 下同砍(not strict 守卫覆盖 total 块)。
    if which in ("both", "total") and not strict and dto.total_rows:
        lines = ["留存期内累计时长榜："]
        for name, secs in dto.total_rows:
            lines.append(f"· {name} {_fmt_duration(secs)}")
        blocks.append("\n".join(lines))
    if which in ("both", "level") and dto.level_rows:
        lines = ["等级榜："]
        for name, level in dto.level_rows:
            lines.append(f"· {name} Lv{level}")
        blocks.append("\n".join(lines))
    if not blocks:
        return L("rank_empty")
    return "\n\n".join(blocks)
