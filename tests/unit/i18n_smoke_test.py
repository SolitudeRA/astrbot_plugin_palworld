"""en locale 冒烟（i18n Phase 1 · §6）：load_locale("en") 后渲染代表 formatter，
断言英文措辞样例 + CJK 统一表意文字（[一-鿿]）零容忍扫描。

CJK 豁免（ledger 注记，spec §3.2/§3.5）：
  · ME 卡输入别名 `卡` `图`（`_ME_CARD_TOKENS` 三语通收，任何 locale 下继续可用）——
    出现在 `/pal help` / `/pal me` 用法行，属输入别名非输出文案，扫描前剔除。
  · 玩家名/公会名/据点名/物种名等**输入数据**一律用 ASCII 假数据构造，从源头回避
    （匿名公会落库名「公会-xxx」模式不在本冒烟被测路径，无需额外豁免）。

teardown 复位 zh 由 conftest autouse `_reset_locale` 兜底。
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from palworld_terminal.application.dtos import (
    BaseDetailDTO,
    CompanionView,
    DexElementBucket,
    DexProgressDTO,
    EventView,
    MeCardDTO,
    StatusDetailDTO,
    StatusDTO,
)
from palworld_terminal.domain.enums import Confidence, EventType
from palworld_terminal.presentation.formatters import (
    format_base,
    format_dex,
    format_events,
    format_help,
    format_me,
    format_status,
)
from palworld_terminal.presentation.locale import L, load_locale

_CJK = re.compile(r"[一-鿿]")  # CJK 统一表意文字（U+4E00–U+9FFF）
_ALIAS_EXEMPT = str.maketrans("", "", "卡图")  # ME 卡输入别名（spec §3.5 豁免）
_TZ = "Asia/Tokyo"


@pytest.fixture(autouse=True)
def _en():
    load_locale("en")
    yield
    # 复位交给 conftest autouse _reset_locale（zh-CN）。


def _assert_no_cjk(text: str) -> None:
    hit = _CJK.search(text.translate(_ALIAS_EXEMPT))
    assert hit is None, f"CJK 残留于 en 输出：{hit.group()!r} in {text!r}"


def _ep(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(_TZ)).timestamp())


# ---- format_status ----

def test_status_renders_english_and_no_cjk():
    dto = StatusDTO(
        server_name="cfg", world_name="w", world_day=42, online=2, max_players=32,
        basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="smooth",
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")], peak_online_today=7,
        updated_at=1_700_000_000, degraded=False, last_ok=1_700_000_000,
        detail=StatusDetailDTO(version="0.6.5", description="", uptime_seconds=550800,
                               frametime_ms=17.2, address="", rules={}),
    )
    text = format_status(dto, "Palpagos")
    assert "🌍 World Status · Palpagos" in text
    assert "Smooth" in text                 # smoothness_smooth
    assert "Online players" in text
    assert "today's peak 7" in text
    _assert_no_cjk(text)


# ---- format_me（含随身高光：元素/动作稳定键渲染）----

def test_me_card_renders_english_terms_and_no_cjk():
    dto = MeCardDTO(
        name="Neo", level=30, online=True, online_seconds=3900, guild_name="Matrix",
        hidden=False, today_seconds=7200, total_seconds=360000, percentile=40.0,
        last_seen_at=0, first_seen_at=10,
        companion=CompanionView(species_name="Lamball", element="grass", level=48,
                                action_label="working", hp_ratio=0.8),
        companion_status="shown",
    )
    text = format_me(dto)
    assert "🎴 My Card · Neo" in text
    assert "Ahead of 40% of recorded players" in text
    assert "Companion Lamball (Grass) Lv48" in text   # element grass → Grass
    assert "Working" in text                          # action working → Working
    assert 'Guild "Matrix"' in text
    _assert_no_cjk(text)


# ---- format_base（车间现场：徽章/摸鱼率/行为分布）----

def test_base_renders_english_and_no_cjk():
    dto = BaseDetailDTO(
        display_name="Coastal Yard", guild_name="Matrix", confidence=Confidence.HIGH,
        worker_count=18, active_count=12, average_level=17.5, average_hp_ratio=0.92,
        action_distribution={"working": 8, "moving": 5, "slacking": 3, "unknown": 2},
        health_score=90.0, mood="fired_up", slacker_rate=0.15,
        species_top=[("Lamball", 4), ("Cattiva", 2)],
    )
    text = format_base(dto)
    assert "🏕️ Base · Coastal Yard" in text
    assert 'Guild "Matrix" · confidence high' in text
    assert "🔥 Fired up" in text
    assert "Status 🟢 Healthy · avg HP 92%" in text
    assert "🚬 Slacking rate 15%" in text
    assert "Activity breakdown" in text
    assert "Working" in text and "Slacking" in text
    _assert_no_cjk(text)


# ---- format_dex（图鉴：observed 术语 + 缺失清单）----

def test_dex_renders_english_observed_term_and_no_cjk():
    dto = DexProgressDTO(
        observed_count=2, total=5,
        buckets=[DexElementBucket("fire", ["Foxparks"], ["Rooby"]),
                 DexElementBucket("grass", ["Lamball"], [])],
    )
    text = format_dex(dto)
    assert "📖 Server Paldex" in text
    assert "This plugin has observed 2/5 species" in text  # observed 术语
    assert "Not yet observed" in text                      # dex_missing
    assert "Fire" in text and "Grass" in text              # element_* 渲染
    _assert_no_cjk(text)


# ---- format_help（分级帮助：组头 + 命令描述 + @server 尾注；卡/图 别名豁免）----

def test_help_renders_english_and_no_cjk_with_alias_exemption():
    from tests.unit._perm import all_on
    text = format_help(None, is_admin=True, overrides=all_on())
    assert "📖 PalWorldTerminal Commands" in text
    assert "/pal world status World status" in text
    assert "Guild" in text                                 # 术语样例
    assert "└ Append @<server> to a command" in text
    # help 输出含 ME 卡输入别名「卡/图」（help_desc_me），豁免后应无其它 CJK 残留。
    assert "卡" in text and "图" in text                   # 别名确在输出（豁免前提成立）
    _assert_no_cjk(text)


# ---- admin 回执（写命令回执 + 二次确认；{action}/{verb} 局部化名词）----

def test_admin_receipts_render_english():
    assert L("admin_ok_kick", target="Neo", server="Palpagos") == "✅ Kicked Neo · Palpagos"
    assert L("admin_confirm_preview", phrase="Shutdown (30s countdown)",
             server="Palpagos", timeout=60).startswith("⚠️ Pending confirmation")
    # {action} 承接 admin_action_* 局部化名词（广播公告 → Broadcast）。
    failed = L("admin_failed", action=L("admin_action_announce"), server="S", error="boom")
    assert failed == "❌ Broadcast failed · S\n└ boom"
    for text in (L("admin_ok_kick", target="Neo", server="S"), failed):
        _assert_no_cjk(text)


# ---- format_events 今天分支（构造今天时间戳 → HH:MM + Today 节头 + 英文措辞）----

def test_events_today_branch_shows_hhmm_and_english():
    now = _ep(2026, 7, 17, 15, 0)
    events = [
        EventView(occurred_at=_ep(2026, 7, 17, 14, 32), event_type=EventType.PLAYER_LEVEL_UP,
                  name="Neo", old=21, new=22),
        EventView(occurred_at=_ep(2026, 7, 17, 9, 15), event_type=EventType.NEW_PLAYER,
                  name="Trinity"),
    ]
    text = format_events(events, "Palpagos", now=now, tz=_TZ, today_only=False, fold_limit=7)
    assert "📰 World Events · Palpagos" in text
    assert "Today" in text                                 # rel_today 节头
    assert "· 14:32 Neo leveled up Lv21→Lv22" in text      # 今天条目带 HH:MM + 英文措辞
    assert "New player Trinity joined the world" in text
    _assert_no_cjk(text)
