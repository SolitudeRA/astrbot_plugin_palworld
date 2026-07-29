"""三语运行时冒烟：目录卫生由静态检查负责，代表渲染验证 locale 接线。"""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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

_CJK = re.compile(r"[一-鿿]")
_ALIAS_EXEMPT = str.maketrans("", "", "卡图")
_TZ = "Asia/Tokyo"
_LOCALES_DIR = Path(__file__).resolve().parents[2] / "palworld_terminal" / "presentation" / "locales"


def _assert_no_cjk(text: str) -> None:
    hit = _CJK.search(text.translate(_ALIAS_EXEMPT))
    assert hit is None, f"CJK 残留于 en 输出：{hit.group()!r} in {text!r}"


def _load_catalog(locale: str) -> dict[str, str]:
    return json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def _ep(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(_TZ)).timestamp())


def _status_dto():
    return StatusDTO(
        server_name="cfg",
        world_name="w",
        world_day=42,
        online=2,
        max_players=32,
        basecamp_count=5,
        fps=58.0,
        frame_time=17.2,
        smoothness_label="smooth",
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")],
        peak_online_today=7,
        updated_at=1_700_000_000,
        degraded=False,
        last_ok=1_700_000_000,
        detail=StatusDetailDTO(
            version="0.6.5",
            description="",
            uptime_seconds=550800,
            frametime_ms=17.2,
            address="",
            rules={},
        ),
    )


def _me_dto():
    return MeCardDTO(
        name="Neo",
        level=30,
        online=True,
        online_seconds=3900,
        guild_name="Matrix",
        hidden=False,
        today_seconds=7200,
        total_seconds=360000,
        percentile=40.0,
        last_seen_at=0,
        first_seen_at=10,
        companion=CompanionView(
            species_name="Lamball",
            element="grass",
            level=48,
            action_label="working",
            hp_ratio=0.8,
        ),
        companion_status="shown",
    )


def _base_dto():
    return BaseDetailDTO(
        display_name="Coastal Yard",
        guild_name="Matrix",
        confidence=Confidence.HIGH,
        worker_count=18,
        active_count=12,
        average_level=17.5,
        average_hp_ratio=0.92,
        action_distribution={"working": 8, "moving": 5, "slacking": 3, "unknown": 2},
        health_score=90.0,
        mood="fired_up",
        slacker_rate=0.15,
        species_top=[("Lamball", 4), ("Cattiva", 2)],
    )


def _dex_dto():
    return DexProgressDTO(
        observed_count=2,
        total=5,
        buckets=[
            DexElementBucket("fire", ["Foxparks"], ["Rooby"]),
            DexElementBucket("grass", ["Lamball"], []),
        ],
    )


def _events():
    now = _ep(2026, 7, 17, 15, 0)
    rows = [
        EventView(
            occurred_at=_ep(2026, 7, 17, 14, 32),
            event_type=EventType.PLAYER_LEVEL_UP,
            name="Neo",
            old=21,
            new=22,
        ),
        EventView(
            occurred_at=_ep(2026, 7, 17, 9, 15),
            event_type=EventType.NEW_PLAYER,
            name="Trinity",
        ),
    ]
    return rows, now


def _representative_outputs() -> dict[str, str]:
    events, now = _events()
    return {
        "status": format_status(_status_dto(), "Palpagos"),
        "me": format_me(_me_dto()),
        "base": format_base(_base_dto()),
        "dex": format_dex(_dex_dto()),
        "help": format_help(None, is_admin=True, overrides=all_on()),
        "events": format_events(events, "Palpagos", now=now, tz=_TZ, today_only=False, fold_limit=7),
    }


def test_en_catalog_has_no_unexpected_cjk():
    _assert_no_cjk("\n".join(_load_catalog("en").values()))


def test_en_representative_renderers_use_loaded_locale():
    load_locale("en")
    outputs = _representative_outputs()
    expected = {
        "status": "World Status",
        "me": "My Card",
        "base": "Base",
        "dex": "Server Paldex",
        "help": "Commands",
        "events": "World Events",
    }
    for surface, token in expected.items():
        assert token in outputs[surface], surface
        _assert_no_cjk(outputs[surface])
    assert "Kicked Neo" in L("admin_ok_kick", target="Neo", server="Palpagos")


def test_en_structural_punctuation_is_ascii():
    load_locale("en")
    dto = DexProgressDTO(
        observed_count=3,
        total=5,
        buckets=[
            DexElementBucket("fire", ["Foxparks", "Rushoar"], ["Rooby", "Arsox"]),
            DexElementBucket("grass", ["Lamball"], []),
        ],
    )
    text = format_dex(dto)
    assert "Fire 2: Foxparks, Rushoar" in text
    assert "  └ Not yet observed: Rooby, Arsox" in text
    assert "Alpha, Beta" in L("whereami_authed", servers=L("list_sep").join(["Alpha", "Beta"]))
    assert _target_phrase("Neo", "steam_1234") == "Neo (…1234)"
    assert not any(ch in text for ch in ("：", "、", "　", "（", "）"))


def test_ja_representative_renderers_use_loaded_locale():
    load_locale("ja")
    outputs = _representative_outputs()
    expected = {
        "status": "ワールド状態",
        "me": "マイ名刺",
        "base": "拠点",
        "dex": "サーバーパルデックス",
        "help": "コマンド",
        "events": "ワールドイベント",
    }
    for surface, token in expected.items():
        assert token in outputs[surface], surface
    assert "キックしました" in L("admin_ok_kick", target="Neo", server="Palpagos")


def test_zh_dex_keeps_fullwidth_punctuation():
    load_locale("zh-CN")
    dto = DexProgressDTO(
        observed_count=2,
        total=5,
        buckets=[
            DexElementBucket("fire", ["Foxparks", "Rushoar"], ["Rooby"]),
            DexElementBucket("grass", ["Lamball"], []),
        ],
    )
    text = format_dex(dto)
    assert "2：Foxparks、Rushoar" in text
    assert "　└ 尚未被观测：Rooby" in text
