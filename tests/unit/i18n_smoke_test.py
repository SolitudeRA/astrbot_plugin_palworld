"""i18n Phase 1 冒烟（§6）：load_locale 后渲染代表 formatter，断言译文措辞样例。

- en：CJK 统一表意文字（`[一-鿿]`）零容忍扫描（日文含汉字，此法仅对 en 成立）。
- ja：不可 CJK 零容忍——改「zh 专属值片段残留检测」（spec §3.5 定案）：渲染输出不得含
  zh-CN.json 的简中专属值片段。取样若干高频串（世界状态 / 当前在线 / 我的名片 /
  服务器图鉴 / 超越有记录玩家 …）断言不出现（主）+ 全量 ≥4 纯 CJK 片段扫描（全量法，
  zh 值中不在 ja 值集的 ≥4 连续 CJK 串一律不得漏进 ja 渲染语料）。

残留检测豁免（ledger 注记，spec §3.5）：
  · ME 卡输入别名 `卡` `图`（`_ME_CARD_TOKENS` 三语通收，任何 locale 下继续可用）——
    单字符别名，既非 ≥4 片段亦不入取样表；en 侧扫描前 `str.translate` 剔除。
  · 匿名公会落库名「公会-xxx」（T6 落库豁免）——属输入数据，本冒烟全程以 ASCII 假数据
    构造回避，不进入任何被测渲染路径。

各 locale 用例经其所属类的 autouse fixture 装载对应语言（模块级不再共用单一 autouse，
避免 en/ja 串扰）；teardown 复位 zh 由 conftest autouse `_reset_locale` 兜底。
"""
import json
import re
import string
from datetime import datetime
from pathlib import Path
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
from palworld_terminal.presentation.admin_write_flow import _target_phrase
from palworld_terminal.presentation.formatters import (
    format_base,
    format_dex,
    format_events,
    format_help,
    format_me,
    format_status,
)
from palworld_terminal.presentation.locale import L, load_locale
from tests.unit._perm import all_on

_CJK = re.compile(r"[一-鿿]")  # CJK 统一表意文字（U+4E00–U+9FFF）
_ALIAS_EXEMPT = str.maketrans("", "", "卡图")  # ME 卡输入别名（spec §3.5 豁免）
_TZ = "Asia/Tokyo"

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "palworld_terminal" / "presentation" / "locales"


def _assert_no_cjk(text: str) -> None:
    hit = _CJK.search(text.translate(_ALIAS_EXEMPT))
    assert hit is None, f"CJK 残留于 en 输出：{hit.group()!r} in {text!r}"


def _ep(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(_TZ)).timestamp())


# ---- 共享 DTO 工厂（en/ja 冒烟与残留语料共用同批代表数据；一律 ASCII 假数据）----

def _status_dto():
    return StatusDTO(
        server_name="cfg", world_name="w", world_day=42, online=2, max_players=32,
        basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="smooth",
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")], peak_online_today=7,
        updated_at=1_700_000_000, degraded=False, last_ok=1_700_000_000,
        detail=StatusDetailDTO(version="0.6.5", description="", uptime_seconds=550800,
                               frametime_ms=17.2, address="", rules={}),
    )


def _me_dto():
    return MeCardDTO(
        name="Neo", level=30, online=True, online_seconds=3900, guild_name="Matrix",
        hidden=False, today_seconds=7200, total_seconds=360000, percentile=40.0,
        last_seen_at=0, first_seen_at=10,
        companion=CompanionView(species_name="Lamball", element="grass", level=48,
                                action_label="working", hp_ratio=0.8),
        companion_status="shown",
    )


def _base_dto():
    return BaseDetailDTO(
        display_name="Coastal Yard", guild_name="Matrix", confidence=Confidence.HIGH,
        worker_count=18, active_count=12, average_level=17.5, average_hp_ratio=0.92,
        action_distribution={"working": 8, "moving": 5, "slacking": 3, "unknown": 2},
        health_score=90.0, mood="fired_up", slacker_rate=0.15,
        species_top=[("Lamball", 4), ("Cattiva", 2)],
    )


def _dex_dto():
    return DexProgressDTO(
        observed_count=2, total=5,
        buckets=[DexElementBucket("fire", ["Foxparks"], ["Rooby"]),
                 DexElementBucket("grass", ["Lamball"], [])],
    )


def _events_now():
    now = _ep(2026, 7, 17, 15, 0)
    events = [
        EventView(occurred_at=_ep(2026, 7, 17, 14, 32), event_type=EventType.PLAYER_LEVEL_UP,
                  name="Neo", old=21, new=22),
        EventView(occurred_at=_ep(2026, 7, 17, 9, 15), event_type=EventType.NEW_PLAYER,
                  name="Trinity"),
    ]
    return events, now


# ==== en 冒烟（CJK 零容忍）========================================================

class TestEnSmoke:
    @pytest.fixture(autouse=True)
    def _en(self):
        load_locale("en")
        yield
        # 复位交给 conftest autouse _reset_locale（zh-CN）。

    def test_status_renders_english_and_no_cjk(self):
        text = format_status(_status_dto(), "Palpagos")
        assert "🌍 World Status · Palpagos" in text
        assert "Smooth" in text                 # smoothness_smooth
        assert "Online players" in text
        assert "today's peak 7" in text
        _assert_no_cjk(text)

    def test_me_card_renders_english_terms_and_no_cjk(self):
        text = format_me(_me_dto())
        assert "🎴 My Card · Neo" in text
        assert "Ahead of 40% of recorded players" in text
        assert "Companion Lamball (Grass) Lv48" in text   # element grass → Grass
        assert "Working" in text                          # action working → Working
        assert 'Guild "Matrix"' in text
        _assert_no_cjk(text)

    def test_base_renders_english_and_no_cjk(self):
        text = format_base(_base_dto())
        assert "🏕️ Base · Coastal Yard" in text
        assert 'Guild "Matrix" · confidence high' in text
        assert "🔥 Fired up" in text
        assert "Status 🟢 Healthy · avg HP 92%" in text
        assert "🚬 Slacking rate 15%" in text
        assert "Activity breakdown" in text
        assert "Working" in text and "Slacking" in text
        _assert_no_cjk(text)

    def test_dex_renders_english_observed_term_and_no_cjk(self):
        text = format_dex(_dex_dto())
        assert "📖 Server Paldex" in text
        assert "This plugin has observed 2/5 species" in text  # observed 术语
        assert "Not yet observed" in text                      # dex_missing
        assert "Fire" in text and "Grass" in text              # element_* 渲染
        _assert_no_cjk(text)

    def test_dex_english_structural_punctuation_is_ascii(self):
        """终审对抗复核修：结构性分隔符/冒号/缩进走 locale 键，en 取 ASCII——
        不得再渲染硬编码全角标点（：/、/　）。多物种 observed + 多物种 missing 触发 join。"""
        dto = DexProgressDTO(
            observed_count=3, total=5,
            buckets=[DexElementBucket("fire", ["Foxparks", "Rushoar"], ["Rooby", "Arsox"]),
                     DexElementBucket("grass", ["Lamball"], [])],
        )
        text = format_dex(dto)
        assert "Fire 2: Foxparks, Rushoar" in text            # 观测行 ASCII 冒号/逗号
        assert "  └ Not yet observed: Rooby, Arsox" in text   # 缺失行 ASCII 缩进/冒号/逗号
        for ch in ("：", "、", "　", "（", "）"):  # ：、　（）
            assert ch not in text, f"全角标点残留于 en dex: {ch!r}"
        _assert_no_cjk(text)

    def test_whereami_english_joins_servers_with_ascii_comma(self):
        """复现 commands.whereami（:391）多服组装：list_sep 作胶水，en 下为 ', ' 不含全角 '、'。"""
        status = L("whereami_authed", servers=L("list_sep").join(["Alpha", "Beta"]))
        assert "Alpha, Beta" in status                        # ASCII 逗号连接
        assert "、" not in status                         # 无全角顿号
        _assert_no_cjk(status)

    def test_target_phrase_english_uses_ascii_parens(self):
        """_target_phrase（admin_write_flow）括号走 paren_open/close，en 取 ASCII '(' ')'。"""
        assert _target_phrase("Neo", "steam_1234") == "Neo (…1234)"  # … 语言中立保留
        phrase = _target_phrase("Neo", "1234")
        for ch in ("（", "）"):                       # （）
            assert ch not in phrase, f"全角括号残留于 en target: {ch!r}"
        _assert_no_cjk(phrase)

    def test_help_renders_english_and_no_cjk_with_alias_exemption(self):
        text = format_help(None, is_admin=True, overrides=all_on())
        assert "📖 PalWorldTerminal Commands" in text
        assert "/pal world status World status" in text
        assert "Guild" in text                                 # 术语样例
        assert "└ Append @<server> to a command" in text
        # help 输出含 ME 卡输入别名「卡/图」（help_desc_me），豁免后应无其它 CJK 残留。
        assert "卡" in text and "图" in text                   # 别名确在输出（豁免前提成立）
        _assert_no_cjk(text)

    def test_admin_receipts_render_english(self):
        assert L("admin_ok_kick", target="Neo", server="Palpagos") == "✅ Kicked Neo · Palpagos"
        assert L("admin_confirm_preview", phrase="Shutdown (30s countdown)",
                 server="Palpagos", timeout=60).startswith("⚠️ Pending confirmation")
        # {action} 承接 admin_action_* 局部化名词（广播公告 → Broadcast）。
        failed = L("admin_failed", action=L("admin_action_announce"), server="S", error="boom")
        assert failed == "❌ Broadcast failed · S\n└ boom"
        for text in (L("admin_ok_kick", target="Neo", server="S"), failed):
            _assert_no_cjk(text)

    def test_events_today_branch_shows_hhmm_and_english(self):
        events, now = _events_now()
        text = format_events(events, "Palpagos", now=now, tz=_TZ, today_only=False, fold_limit=7)
        assert "📰 World Events · Palpagos" in text
        assert "Today" in text                                 # rel_today 节头
        assert "· 14:32 Neo leveled up Lv21→Lv22" in text      # 今天条目带 HH:MM + 英文措辞
        assert "New player Trinity joined the world" in text
        _assert_no_cjk(text)


# ==== ja 冒烟（日文措辞样例；残留检测见 TestJaResidue）============================

class TestJaSmoke:
    @pytest.fixture(autouse=True)
    def _ja(self):
        load_locale("ja")
        yield
        # 复位交给 conftest autouse _reset_locale（zh-CN）。

    def test_status_renders_japanese(self):
        text = format_status(_status_dto(), "Palpagos")
        assert "🌍 ワールド状態 · Palpagos" in text
        assert "滑らか" in text                  # smoothness_smooth
        assert "オンラインプレイヤー" in text     # status_section_online
        assert "今日のピーク 7" in text           # common_online_peak

    def test_me_card_renders_japanese_terms(self):
        text = format_me(_me_dto())
        assert "🎴 マイ名刺 · Neo" in text
        assert "記録のあるプレイヤーの 40% を上回る" in text     # me_card_percentile
        assert "お供 Lamball（草）Lv48" in text                  # element grass → 草（お供パル語感）
        assert "作業中" in text                                  # action working → 作業中
        assert "ギルド「Matrix」" in text                        # guild_label

    def test_base_renders_japanese(self):
        text = format_base(_base_dto())
        assert "🏕️ 拠点 · Coastal Yard" in text
        assert "ギルド「Matrix」 · 信頼度高" in text
        assert "🔥 絶好調" in text                               # base_badge_fired_up
        assert "状態 🟢 健康 · 平均HP 92%" in text
        assert "🚬 サボり率 15%" in text                         # 摸鱼 → サボり
        assert "行動分布" in text
        assert "作業中" in text and "サボり" in text

    def test_dex_renders_japanese_observed_term(self):
        text = format_dex(_dex_dto())
        assert "📖 サーバーパルデックス" in text                 # 图鉴 → パルデックス
        assert "このプラグインは 2/5 種を観測済み" in text        # 观测 → 観測
        assert "未観測" in text                                  # dex_missing
        assert "炎" in text and "草" in text                     # element_* 渲染

    def test_help_renders_japanese_with_alias_exemption(self):
        text = format_help(None, is_admin=True, overrides=all_on())
        assert "📖 PalWorldTerminal コマンド" in text
        assert "/pal world status ワールド状態" in text
        assert "ギルド" in text                                  # 公会 → ギルド
        assert "└ コマンド末尾に @サーバー名" in text
        # help 输出含 ME 卡输入别名「卡/图」（help_desc_me）——三语通收，ja 下亦保留。
        assert "卡" in text and "图" in text

    def test_admin_receipts_render_japanese(self):
        assert L("admin_ok_kick", target="Neo", server="Palpagos") == "✅ Neo をキックしました · Palpagos"
        phrase = L("admin_phrase_shutdown", action=L("admin_action_shutdown"), seconds=30)
        assert L("admin_confirm_preview", phrase=phrase,
                 server="Palpagos", timeout=60).startswith("⚠️ 確認待ち")
        # {action} 承接 admin_action_* 局部化名词（广播公告 → 告知配信）。
        failed = L("admin_failed", action=L("admin_action_announce"), server="S", error="boom")
        assert failed == "❌ 告知配信に失敗 · S\n└ boom"

    def test_events_today_branch_shows_hhmm_and_japanese(self):
        events, now = _events_now()
        text = format_events(events, "Palpagos", now=now, tz=_TZ, today_only=False, fold_limit=7)
        assert "📰 ワールドイベント · Palpagos" in text
        assert "今日" in text                                    # rel_today 节头（結構性档位命中）
        assert "· 14:32 Neo がレベルアップ Lv21→Lv22" in text    # 今天条目带 HH:MM
        assert "新規プレイヤー Trinity がワールドに参加" in text


# ==== ja 残留检测（spec §3.5 定案：zh 专属值片段不得漏进 ja 渲染）================

# 取样高频简中专属串（均实存于 zh-CN.json 值中，且 ja 应无）：主断言。
_SAMPLE_ZH_PHRASES = (
    "世界状态", "当前在线", "我的名片", "服务器图鉴", "超越有记录玩家",
    "工作帕鲁", "行为分布", "热火朝天", "飞升榜", "尚未被观测",
    "加入世界", "管理员权限", "服务器", "帕鲁", "公会", "据点",
)

_CJK_RUN4 = re.compile(r"[一-鿿㐀-䶿]{4,}")  # 连续 CJK 统一表意文字 ≥4（全量法片段抽取）


def _load_locale_json(locale: str) -> dict[str, str]:
    return json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def _placeholders(template: str) -> set[str]:
    names: set[str] = set()
    for _literal, field_name, _spec, _conv in string.Formatter().parse(template):
        if field_name is None:
            continue
        names.add(field_name.split(".")[0].split("[")[0])
    return names


def _ja_render_corpus() -> str:
    """ja 全渲染语料（须先 load_locale("ja")）：337 键逐键 L() 填充占位 + 六代表 formatter。

    覆盖全部 ja 值（逐键渲染）+ 措辞组装路径（formatter 注入），供残留扫描一网打尽。
    输入一律 ASCII 假数据，匿名公会名不构造（豁免前提）。
    """
    zh = _load_locale_json("zh-CN")
    parts = [L(key, **{p: "X" for p in _placeholders(tmpl)}) for key, tmpl in zh.items()]
    parts.append(format_status(_status_dto(), "Palpagos"))
    parts.append(format_me(_me_dto()))
    parts.append(format_base(_base_dto()))
    parts.append(format_dex(_dex_dto()))
    parts.append(format_help(None, is_admin=True, overrides=all_on()))
    events, now = _events_now()
    parts.append(format_events(events, "Palpagos", now=now, tz=_TZ, today_only=False, fold_limit=7))
    return "\n".join(parts)


class TestJaResidue:
    @pytest.fixture(autouse=True)
    def _ja(self):
        load_locale("ja")
        yield

    def test_sampled_zh_phrases_absent(self):
        """取样法：高频简中专属串不得出现在 ja 渲染语料。"""
        zh = _load_locale_json("zh-CN")
        zh_blob = "\n".join(zh.values())
        corpus = _ja_render_corpus()
        # 前置自证：取样串确为 zh 基线真值片段（否则断言空转）。
        assert all(p in zh_blob for p in _SAMPLE_ZH_PHRASES), "取样串须实存于 zh 基线"
        leaked = [p for p in _SAMPLE_ZH_PHRASES if p in corpus]
        assert not leaked, f"简中值片段残留于 ja 渲染：{leaked}"

    def test_zh_exclusive_cjk_fragments_absent(self):
        """全量法：zh 值中长度 ≥4、且不属 ja 值集的连续 CJK 片段，一律不得漏进 ja 语料。

        `卡/图` 单字符别名与匿名公会「公会-」（2 字 + ASCII）均非 ≥4 纯 CJK 串，自然豁免。
        """
        zh = _load_locale_json("zh-CN")
        ja = _load_locale_json("ja")
        ja_blob = "\n".join(ja.values())
        fragments = {
            run
            for value in zh.values()
            for run in _CJK_RUN4.findall(value)
            if run not in ja_blob   # zh 专属（不属 ja 值集）
        }
        assert fragments, "应抽到若干 zh 专属 ≥4 CJK 片段（否则抽取逻辑失效）"
        corpus = _ja_render_corpus()
        leaked = sorted(f for f in fragments if f in corpus)
        assert not leaked, f"zh 专属 CJK 片段残留于 ja 渲染：{leaked}"


# ==== zh 不变佐证（终审对抗复核修）：结构性标点键在 zh 下仍精确复现全角原字符 ==========

def test_zh_dex_keeps_fullwidth_punctuation():
    """本修把结构性标点抽键后，zh 输出须逐字节不变——列表顿号/标签冒号/缺失缩进仍全角。"""
    load_locale("zh-CN")
    dto = DexProgressDTO(
        observed_count=2, total=5,
        buckets=[DexElementBucket("fire", ["Foxparks", "Rushoar"], ["Rooby"]),
                 DexElementBucket("grass", ["Lamball"], [])],
    )
    text = format_dex(dto)
    assert "2：Foxparks、Rushoar" in text          # 观测行：全角冒号 U+FF1A + 全角顿号 U+3001
    assert "　└ 尚未被观测：Rooby" in text          # 缺失行：全角空格 U+3000 缩进 + 全角冒号
