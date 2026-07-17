"""format_player 卡片（spec §4.10 player info / §4.25 me）：在线/离线/strict/多单模式锚/
me 变体（我的玩家标题 + 已隐藏角标）/公会省略/最后在线相对日期。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from palworld_terminal.application.query_service import PlayerProfileDTO
from palworld_terminal.presentation.formatters import format_player
from palworld_terminal.presentation.textkit import rel_datetime

_TZ = "Asia/Tokyo"
_Z = ZoneInfo(_TZ)


def _ep(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=_Z).timestamp())


_NOW = _ep(2026, 7, 17, 10, 0)
_FIRST = _ep(2026, 6, 30, 12, 0)
_LAST = _ep(2026, 7, 16, 23, 41)


def _dto(*, online, level=21, guild="Matrix", hidden=False,
         online_seconds=8100, today=13200, total=75900, last_seen=_LAST):
    return PlayerProfileDTO(
        name="Neo", level=level, online=online,
        online_seconds=online_seconds, first_seen_at=_FIRST,
        last_seen_at=last_seen, guild_name=guild,
        today_seconds=today, total_seconds=total, hidden=hidden,
    )


def _fmt(dto, *, strict=False, server="备用服", mode="multi", is_me=False):
    return format_player(dto, strict=strict, server_name=server,
                         world_mode=mode, tz=_TZ, now=_NOW, is_me=is_me)


# ---- 在线态（§4.10）----

def test_online_card_full():
    out = _fmt(_dto(online=True))
    assert out.splitlines()[0] == "👤 玩家 · Neo · 备用服"
    assert "Lv21 · 🟢 在线 · 本次 2时15分" in out
    assert "今日在线 3时40分 · 累计 21时05分" in out
    assert "公会「Matrix」" in out
    assert "首次现身 2026-06-30" in out


# ---- 离线态（§4.10：不佩状态点；最后在线用 rel_datetime）----

def test_offline_no_dot_last_seen_rel_datetime():
    out = _fmt(_dto(online=False, level=18))
    assert "Lv18 · 离线 · 最后在线 " + rel_datetime(_LAST, _NOW, _TZ) in out
    assert "昨天 23:41" in out
    assert "🟢" not in out
    assert "本次" not in out
    # 次行块仍在（今日/累计/公会/首次现身）
    assert "今日在线 3时40分 · 累计 21时05分" in out


# ---- strict 双砍（§4.10：砍时长+最后在线，留 Lv/在线状态/公会/首次现身）----

def test_strict_online_cuts_durations():
    out = _fmt(_dto(online=True), strict=True)
    assert "Lv21" in out and "🟢 在线" in out
    assert "本次" not in out
    assert "今日在线" not in out and "累计" not in out
    assert "公会「Matrix」" in out
    assert "首次现身 2026-06-30" in out


def test_strict_offline_cuts_last_seen():
    out = _fmt(_dto(online=False, level=18), strict=True)
    assert "Lv18 · 离线" in out
    assert "最后在线" not in out
    assert "今日在线" not in out


# ---- 公会缺席省略（gamedata 锁定期）----

def test_guild_line_omitted_when_none():
    out = _fmt(_dto(online=True, guild=None))
    assert "公会" not in out
    assert "首次现身 2026-06-30" in out


# ---- 多/单模式锚（§3 账号状态族）----

def test_multi_mode_appends_server_anchor():
    assert "备用服" in _fmt(_dto(online=True), mode="multi")


def test_single_mode_omits_server_anchor():
    out = _fmt(_dto(online=True), mode="single", server="备用服")
    assert "备用服" not in out
    assert out.splitlines()[0] == "👤 玩家 · Neo"


# ---- me 变体（§4.25：我的玩家标题 + 已隐藏角标）----

def test_me_title_and_hidden_badge():
    out = _fmt(_dto(online=True, hidden=True), is_me=True)
    assert out.splitlines()[0].startswith("👤 我的玩家 · Neo")
    assert "首次现身 2026-06-30 · 已隐藏" in out


def test_me_not_hidden_no_badge():
    out = _fmt(_dto(online=True, hidden=False), is_me=True)
    assert "已隐藏" not in out


def test_player_info_never_shows_hidden_badge():
    # player info 走 name_banned 收敛，hidden 恒 False；即便误置也不缀角标（非 me）
    out = _fmt(_dto(online=True, hidden=True), is_me=False)
    assert "已隐藏" not in out
