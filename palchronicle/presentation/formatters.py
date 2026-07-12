from __future__ import annotations

from ..application.query_service import RankBoardsDTO
from ..config import SkippedServer
from ..domain.enums import Confidence, PingBucket
from ..presentation.command_registry import COMMANDS, HELP_LINE
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

_PING_LABEL = {
    PingBucket.GOOD: "优秀", PingBucket.OK: "正常",
    PingBucket.HIGH: "偏高", PingBucket.UNKNOWN: "未知",
}
_CONF_LABEL = {Confidence.HIGH: "高", Confidence.MEDIUM: "中", Confidence.LOW: "低"}


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(max(seconds, 0), 3600)
    m = rem // 60
    if h:
        return f"{h}小时{m}分"
    return f"{m}分"


def format_degraded(last_ok: int | None, now: int) -> str:
    if last_ok is None:
        return L("degraded_never")
    minutes = max(0, (now - last_ok) // 60)
    return L("degraded", minutes=minutes)


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


def format_events(dto: list[EventDTO]) -> str:
    if not dto:
        return L("no_events")
    lines = ["近期世界事件："]
    lines.extend(f"· {e.summary}" for e in dto)
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


_HELP_ADMIN_EXTRA = [
    "管理员命令：",
    "/pal use <名称>  授权本群并设为活动服务器（仅群聊）",
    "/pal unbind <名称>  撤销本群授权",
]


def format_help(topic: str | None, is_admin: bool, features) -> str:
    lines = ["PalChronicle 命令："]
    for name, group in COMMANDS:
        if group == "core" or features.enabled(group):
            lines.append(HELP_LINE[name])
    lines.append("提示：命令末尾可加 @服务器名 指定服务器。")
    if is_admin:
        lines.append("")
        lines.extend(_HELP_ADMIN_EXTRA)
    return "\n".join(lines)


def format_status(dto: StatusDTO) -> str:
    if dto.degraded:
        return format_degraded(dto.last_ok, dto.updated_at)
    lines = [
        f"世界：{dto.world_name} · 第 {dto.world_day} 天",
        f"在线：{dto.online}/{dto.max_players} 人 · 今日最高 {dto.peak_online_today}",
        f"据点：{dto.basecamp_count}（官方指标）",
        f"性能：FPS {dto.fps:.0f}（{dto.smoothness_label}） · 帧时间 {dto.frame_time:.1f}ms",
    ]
    if dto.players:
        lines.append("在线玩家：")
        lines.extend(f"  · {n} Lv{lv}" for n, lv, _ in dto.players)
    return "\n".join(lines)


def format_world(dto: WorldSummaryDTO) -> str:
    lines = [
        f"世界概览 · 第 {dto.world_day} 天 · 在线 {dto.online} 人",
        f"角色 {dto.players} · 随行 {dto.otomo} · 工作帕鲁 {dto.base_pal} · "
        f"野生 {dto.wild} · NPC {dto.npc}",
        f"PalBox {dto.palbox} · 公会 {dto.guilds}",
        f"FPS 瞬时 {dto.fps:.0f} / 平均 {dto.average_fps:.0f}",
    ]
    if dto.wild_top:
        top = "、".join(f"{w.name}×{w.count}" for w in dto.wild_top)
        lines.append(f"当前野生帕鲁 Top（仅当前快照）：{top}")
    return "\n".join(lines)


def format_rules(dto: RulesDTO) -> str:
    lines = ["世界规则："]
    for r in dto.rows:
        lines.append(f"· {r.label}：{r.value}")
    if dto.advanced_note:
        lines.append(f"注：{dto.advanced_note}")
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


def format_rank(dto: RankBoardsDTO, *, which: str, strict: bool) -> str:
    blocks: list[str] = []
    if which in ("both", "time") and not strict and dto.time_rows:
        lines = ["今日在线时长榜："]
        for name, secs in dto.time_rows:
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
