"""textkit 共享格式 helper：折叠 / 时长 / 相对日期 / 引号回显（spec §2.3–2.5, §2.7）。

后续全部 formatter 任务消费本模块；此处锁定 helper 语义与边界。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from palworld_terminal.presentation.textkit import (
    fmt_duration,
    fold,
    quote_echo,
    rel_date,
    rel_datetime,
    time_of_day,
)

_TZ = ZoneInfo("Asia/Tokyo")


def _ep(y, mo, d, h=0, mi=0, tz=_TZ):
    return int(datetime(y, mo, d, h, mi, tzinfo=tz).timestamp())


# ---- fold（spec §2.7）----

def test_fold_at_limit_no_fold():
    lines = [f"· item{i}" for i in range(7)]
    assert fold(lines, 7, "人") == lines


def test_fold_below_limit_no_fold():
    lines = [f"· item{i}" for i in range(3)]
    assert fold(lines, 7, "人") == lines


def test_fold_over_limit_appends_tail_total_count():
    lines = [f"· item{i}" for i in range(10)]
    out = fold(lines, 7, "人")
    assert out[:7] == lines[:7]
    assert out[7] == "…等共 10 人"
    assert len(out) == 8


def test_fold_tail_quantifier_follows_unit():
    lines = [f"· e{i}" for i in range(8)]
    assert fold(lines, 7, "条")[-1] == "…等共 8 条"


def test_fold_empty_list():
    assert fold([], 7, "人") == []


def test_fold_does_not_mutate_input():
    lines = [f"· item{i}" for i in range(10)]
    snapshot = list(lines)
    fold(lines, 7, "人")
    assert lines == snapshot


# ---- fmt_duration（spec §2.4）----

def test_fmt_duration_zero_minutes():
    assert fmt_duration(0) == "0分"


def test_fmt_duration_under_one_hour():
    assert fmt_duration(45 * 60) == "45分"


def test_fmt_duration_hours_pads_minutes_two_digits():
    assert fmt_duration(3600 + 5 * 60) == "1时05分"


def test_fmt_duration_two_digit_hour_padded_minutes():
    assert fmt_duration(21 * 3600 + 5 * 60) == "21时05分"


def test_fmt_duration_whole_hour():
    assert fmt_duration(3600) == "1时00分"


def test_fmt_duration_days_from_25_hours():
    assert fmt_duration(25 * 3600) == "1天1时"


def test_fmt_duration_days_drop_minutes():
    assert fmt_duration(6 * 86400 + 9 * 3600 + 30 * 60) == "6天9时"


def test_fmt_duration_exactly_one_day():
    assert fmt_duration(86400) == "1天0时"


def test_fmt_duration_negative_clamped_to_zero():
    assert fmt_duration(-100) == "0分"


def test_fmt_duration_sub_minute_floors():
    assert fmt_duration(59) == "0分"


# ---- rel_date（spec §2.5）----

def test_rel_date_today():
    now = _ep(2026, 7, 17, 10, 0)
    ts = _ep(2026, 7, 17, 8, 0)
    assert rel_date(ts, now, _TZ) == "今天"


def test_rel_date_yesterday():
    now = _ep(2026, 7, 17, 10, 0)
    ts = _ep(2026, 7, 16, 23, 0)
    assert rel_date(ts, now, _TZ) == "昨天"


def test_rel_date_same_year_mmdd():
    now = _ep(2026, 7, 17, 10, 0)
    ts = _ep(2026, 7, 14, 9, 15)
    assert rel_date(ts, now, _TZ) == "07-14"


def test_rel_date_cross_year_full_iso():
    now = _ep(2026, 1, 3, 10, 0)
    ts = _ep(2025, 12, 31, 23, 0)
    assert rel_date(ts, now, _TZ) == "2025-12-31"


def test_rel_date_accepts_tz_string():
    now = _ep(2026, 7, 17, 10, 0)
    ts = _ep(2026, 7, 16, 23, 0)
    assert rel_date(ts, now, "Asia/Tokyo") == "昨天"


def test_rel_date_dst_boundary_uses_calendar_day():
    # America/New_York 2026-03-08 spring-forward：当地日只有 23 小时。
    # 朴素 (now-ts)//86400 == 0 会误判「今天」；按自然日应为「昨天」。
    tz = ZoneInfo("America/New_York")
    ts = int(datetime(2026, 3, 8, 0, 30, tzinfo=tz).timestamp())
    now = int(datetime(2026, 3, 9, 0, 30, tzinfo=tz).timestamp())
    assert now - ts < 86400  # DST 使该日短于 24h
    assert rel_date(ts, now, tz) == "昨天"


# ---- rel_datetime（spec §2.5：全档带 HH:MM）----

def test_rel_datetime_today_with_time():
    now = _ep(2026, 7, 17, 10, 0)
    assert rel_datetime(_ep(2026, 7, 17, 14, 32), now, _TZ) == "今天 14:32"


def test_rel_datetime_yesterday_with_time():
    now = _ep(2026, 7, 17, 10, 0)
    assert rel_datetime(_ep(2026, 7, 16, 23, 41), now, _TZ) == "昨天 23:41"


def test_rel_datetime_same_year_mmdd_with_time():
    now = _ep(2026, 7, 17, 10, 0)
    assert rel_datetime(_ep(2026, 7, 14, 9, 15), now, _TZ) == "07-14 09:15"


def test_rel_datetime_cross_year_full_with_time():
    now = _ep(2026, 1, 3, 10, 0)
    assert rel_datetime(_ep(2025, 12, 31, 23, 0), now, _TZ) == "2025-12-31 23:00"


# ---- time_of_day（spec §2.5：events 今天条目 / today 变体带 HH:MM）----

def test_time_of_day_hhmm():
    assert time_of_day(_ep(2026, 7, 17, 14, 32), _TZ) == "14:32"


def test_time_of_day_pads_zero():
    assert time_of_day(_ep(2026, 7, 17, 9, 5), _TZ) == "09:05"


def test_time_of_day_accepts_tz_string():
    assert time_of_day(_ep(2026, 7, 17, 0, 0), "Asia/Tokyo") == "00:00"


# ---- quote_echo（spec §2.3：回执回显用全角双引号 “ ”）----

def test_quote_echo_wraps_in_fullwidth_double_quotes():
    assert quote_echo("今晚 10 点维护重启") == "“今晚 10 点维护重启”"


def test_quote_echo_empty():
    assert quote_echo("") == "“”"
