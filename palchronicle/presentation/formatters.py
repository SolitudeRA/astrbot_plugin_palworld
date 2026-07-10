from __future__ import annotations

from palchronicle.config import SkippedServer
from palchronicle.domain.enums import Confidence, PingBucket
from palchronicle.presentation.dtos import (
    BaseDetailDTO, BaseDTO, EventDTO, GuildDetailDTO, GuildDTO,
    OnlineDTO, ServerStatusRow,
)
from palchronicle.presentation.locale import L

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


_HELP_GUEST = [
    "PalChronicle 命令：",
    "/pal status  世界状态", "/pal online  当前在线", "/pal world  世界概览",
    "/pal rules  世界规则", "/pal guilds  公会列表", "/pal guild <名称>  公会详情",
    "/pal bases  据点列表", "/pal base <名称|#序号>  据点详情", "/pal events  世界事件",
    "/pal today  今日日报", "/pal servers  服务器列表", "/pal help  帮助",
    "提示：命令末尾可加 @服务器名 指定服务器。",
]
_HELP_ADMIN_EXTRA = [
    "管理员命令：",
    "/pal use <名称>  授权本群并设为活动服务器（仅群聊）",
    "/pal unbind <名称>  撤销本群授权",
]


def format_help(topic: str | None, is_admin: bool) -> str:
    lines = list(_HELP_GUEST)
    if is_admin:
        lines.append("")
        lines.extend(_HELP_ADMIN_EXTRA)
    return "\n".join(lines)
