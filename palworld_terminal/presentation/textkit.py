"""命令输出共享格式 helper：折叠 / 时长 / 相对日期 / 引号回显。

命令输出重设计的基建模块，后续全部 formatter 任务消费；语义定于
spec §2.3（引号）/ §2.4（时长）/ §2.5（相对日期）/ §2.7（折叠）。
纯函数，无 IO / 无 await，可脱离 AstrBot 单测。
"""
from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from .locale import L

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
    return list(lines[:limit]) + [L("fold_tail", n=len(lines), unit=unit)]


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
        return L("duration_dh", d=d, h=hh)
    if h:
        # 分钟两位补零在此完成，模板只承 `{mm}` 位（补零语义随渲染语言不变）。
        return L("duration_hm", h=h, mm=f"{m:02d}")
    return L("duration_m", m=m)


def _resolve_tz(tz: str | tzinfo) -> tzinfo:
    return ZoneInfo(tz) if isinstance(tz, str) else tz


def _local(ts: int, tz: tzinfo) -> datetime:
    return datetime.fromtimestamp(int(ts), tz)


def rel_date_key(ts: int, now: int, tz: str | tzinfo) -> str:
    """相对日期三档的**结构化档位键**（i18n §3.5 结构性比较修正）：
    `today` / `yesterday` / `date`，供调用方做语义判断（不再拿本地化渲染串字面比较）。

    按 tz 下的自然日历日比较（非 86400 秒差）→ DST 的 23/25 小时日安全。
    tz 接受 IANA 字符串或 tzinfo。
    """
    z = _resolve_tz(tz)
    delta = (_local(now, z).date() - _local(ts, z).date()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "yesterday"
    return "date"


def rel_date(ts: int, now: int, tz: str | tzinfo) -> str:
    """相对日期三档词形（spec §2.5）：今天 / 昨天 / MM-DD（跨年 YYYY-MM-DD）。

    档位由 rel_date_key 判定，词形经 locale 渲染（`today`/`yesterday` 走键，`date`
    档保持 MM-DD / YYYY-MM-DD 数字格式，语言无关）。tz 接受 IANA 字符串或 tzinfo。
    """
    z = _resolve_tz(tz)
    key = rel_date_key(ts, now, z)
    if key == "today":
        return L("rel_today")
    if key == "yesterday":
        return L("rel_yesterday")
    t = _local(ts, z)
    if t.year == _local(now, z).year:
        return t.strftime("%m-%d")
    return t.strftime("%Y-%m-%d")


def rel_datetime(ts: int, now: int, tz: str | tzinfo) -> str:
    """相对日期 + 时分（spec §2.5）：全档在 rel_date 词形后附 ` HH:MM`。"""
    z = _resolve_tz(tz)
    return f"{rel_date(ts, now, z)} {_local(ts, z).strftime('%H:%M')}"


def abs_date(ts: int, tz: str | tzinfo) -> str:
    """绝对日期 YYYY-MM-DD（spec §2.4）：玩家「首次现身」等固定日期场景，
    不走相对词形。tz 接受 IANA 字符串或 tzinfo。"""
    return _local(int(ts), _resolve_tz(tz)).strftime("%Y-%m-%d")


def time_of_day(ts: int, tz: str | tzinfo) -> str:
    """当日时分 HH:MM（spec §2.5）：events 今天条目 / events today 变体带时刻，
    节头/标题行已承载日期，故此处只出时分。tz 接受 IANA 字符串或 tzinfo。"""
    return _local(int(ts), _resolve_tz(tz)).strftime("%H:%M")


def quote_echo(content: str) -> str:
    """回执内容回显（spec §2.3）：包全角双引号 “ ”。"""
    return f"{_LQUO}{content}{_RQUO}"
