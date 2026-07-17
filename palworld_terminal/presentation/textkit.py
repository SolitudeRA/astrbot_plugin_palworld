"""命令输出共享格式 helper：折叠 / 时长 / 相对日期 / 引号回显。

命令输出重设计的基建模块，后续全部 formatter 任务消费；语义定于
spec §2.3（引号）/ §2.4（时长）/ §2.5（相对日期）/ §2.7（折叠）。
纯函数，无 IO / 无 await，可脱离 AstrBot 单测。
"""
from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

# 全角双引号（spec §2.3：回执内容回显专用；名字/引用另用「」由 formatter 内联）。
_LQUO = "“"  # “
_RQUO = "”"  # ”


def fold(lines: list[str], limit: int, unit: str) -> list[str]:
    """列表折叠（spec §2.7）：≤limit 原样返回；超限取前 limit 行并追一条尾行
    `…等共 N {unit}`，N=总条数（非隐藏余数）。尾行不带 `· ` 前缀（折叠汇总，
    与列表项视觉区分）；unit 为量词（人/条/项）。不修改入参。
    """
    if len(lines) <= limit:
        return list(lines)
    return list(lines[:limit]) + [f"…等共 {len(lines)} {unit}"]


def fmt_duration(seconds: int) -> str:
    """时长（spec §2.4）「N天N时 / N时M分 / N分」，全局统一（废「N小时M分」聚合式）。

    - ≥24h：`{d}天{h}时`（丢弃分钟，时不补零）。
    - 1h–<24h：`{h}时{mm}分`（分钟两位补零，如 1时05分）。
    - <1h：`{m}分`（不补零，如 45分 / 0分）。

    亚分钟向下取整；负值归 0。
    """
    total_min = max(int(seconds), 0) // 60
    h, m = divmod(total_min, 60)
    if h >= 24:
        d, hh = divmod(h, 24)
        return f"{d}天{hh}时"
    if h:
        return f"{h}时{m:02d}分"
    return f"{m}分"


def _resolve_tz(tz: str | tzinfo) -> tzinfo:
    return ZoneInfo(tz) if isinstance(tz, str) else tz


def _local(ts: int, tz: tzinfo) -> datetime:
    return datetime.fromtimestamp(int(ts), tz)


def rel_date(ts: int, now: int, tz: str | tzinfo) -> str:
    """相对日期三档词形（spec §2.5）：今天 / 昨天 / MM-DD（跨年 YYYY-MM-DD）。

    按 tz 下的自然日历日比较（非 86400 秒差）→ DST 的 23/25 小时日安全。
    tz 接受 IANA 字符串或 tzinfo。
    """
    z = _resolve_tz(tz)
    t = _local(ts, z)
    n = _local(now, z)
    delta = (n.date() - t.date()).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "昨天"
    if t.year == n.year:
        return t.strftime("%m-%d")
    return t.strftime("%Y-%m-%d")


def rel_datetime(ts: int, now: int, tz: str | tzinfo) -> str:
    """相对日期 + 时分（spec §2.5）：全档在 rel_date 词形后附 ` HH:MM`。"""
    z = _resolve_tz(tz)
    return f"{rel_date(ts, now, z)} {_local(ts, z).strftime('%H:%M')}"


def quote_echo(content: str) -> str:
    """回执内容回显（spec §2.3）：包全角双引号 “ ”。"""
    return f"{_LQUO}{content}{_RQUO}"
