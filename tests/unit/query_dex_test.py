"""服务器图鉴（spec §8·功能④）：dex_progress() 已观测**去重**物种数（非 observe_count
之和）+ 按元素分桶 + 分母/缺失**同降级**（roster 未知 → 仅已点亮、不出缺失，SD5）；
format_dex 出「本插件已观测 N[/总数] 种」+ 按元素已点亮/缺失 + C2「曾被观测到」口径。

口径承重（T4 决策）：observed_species 跨插件全局累积（无 world_id）→ 措辞「本插件已观测」，
非「本服/全服全部物种」；observe_count 按 actor 计（同种 N 只 +N）→ 物种数只用去重行数。"""
from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.dtos import DexElementBucket, DexProgressDTO
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.formatters import format_dex


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
async def env(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    yield repo, clock
    await db.close()


def _qs(repo, clock) -> QueryService:
    return QueryService(repo, TTLCache(clock), _cfg(), None, clock, {}, world_cache={})


class _QSWithRoster(QueryService):
    """分母已知（完整 roster）分支：override 生产恒 None 的 _species_roster ClassVar。
    真实 paldex 源未权威确定完整物种表 → 生产降级；本桩演示满态（N/总数 + 缺失）。"""

    _species_roster = {
        "BP_ChickenPal_C": ("皮皮鸡", "neutral"),
        "BP_KitsunebiPal_C": ("火绒狐", "fire"),
        "BP_PenguinPal_C": ("企丸丸", "water"),
    }


def _qs_roster(repo, clock) -> QueryService:
    return _QSWithRoster(repo, TTLCache(clock), _cfg(), None, clock, {}, world_cache={})


# ---- ① 已观测数 = 去重物种行数（**非 observe_count 之和**）----

async def test_observed_count_is_distinct_species_not_observe_sum(env):
    repo, clock = env
    # 皮皮鸡观测两次（同种 → observe_count 自增至 2），火绒狐一次。
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1200, "Akari")
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1300, "Akari")
    await repo.upsert_observed_species("BP_KitsunebiPal_C", "火绒狐", "fire", 1200, None)
    dto = await _qs(repo, clock).dex_progress()
    # 去重物种数 = 2；若误用 observe_count 之和会得 3。
    assert dto.observed_count == 2


# ---- ② 按元素分桶（元素取自入库稳定键）----

async def test_buckets_group_by_element(env):
    repo, clock = env
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1200, None)
    await repo.upsert_observed_species("BP_KitsunebiPal_C", "火绒狐", "fire", 1200, None)
    await repo.upsert_observed_species("BP_FlameBambiPal_C", "燎火鹿", "fire", 1200, None)
    dto = await _qs(repo, clock).dex_progress()
    by = {b.element: b for b in dto.buckets}
    assert by["fire"].observed == ["火绒狐", "燎火鹿"]   # 桶内按名排序
    assert by["neutral"].observed == ["皮皮鸡"]


# ---- ③ 分母未知 → 降级：total None + 只出已点亮、无缺失（SD5）----

async def test_degraded_no_denominator_no_missing(env):
    repo, clock = env
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1200, None)
    dto = await _qs(repo, clock).dex_progress()
    assert dto.total is None
    assert all(b.missing == [] for b in dto.buckets)
    assert any("皮皮鸡" in b.observed for b in dto.buckets)


# ---- ④ 分母已知 → N/总数 + 缺失清单（按 species_class 身份比对）----

async def test_known_roster_reports_total_and_missing(env):
    repo, clock = env
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1200, None)
    dto = await _qs_roster(repo, clock).dex_progress()
    assert dto.total == 3
    assert dto.observed_count == 1
    by = {b.element: b for b in dto.buckets}
    assert by["fire"].missing == ["火绒狐"] and by["fire"].observed == []
    assert by["water"].missing == ["企丸丸"]
    assert by["neutral"].observed == ["皮皮鸡"] and by["neutral"].missing == []


# ---- ⑤ 空图鉴 ----

async def test_empty_dex(env):
    repo, clock = env
    dto = await _qs(repo, clock).dex_progress()
    assert dto.observed_count == 0
    assert dto.total is None
    assert dto.buckets == []


# ---- ⑥ format_dex 降级：无分母、无缺失、C2「曾被观测」口径 ----

def test_format_dex_degraded_no_denominator_no_missing():
    dto = DexProgressDTO(observed_count=2, total=None, buckets=[
        DexElementBucket("fire", ["火绒狐"], []),
        DexElementBucket("neutral", ["皮皮鸡"], []),
    ])
    out = format_dex(dto, server_name="Palpagos")
    assert "服务器图鉴" in out and "Palpagos" in out
    assert "已观测 2" in out
    assert "总数" not in out and "尚未被观测" not in out   # 降级不出分母/缺失
    assert "火" in out and "火绒狐" in out
    assert "曾被观测" in out                               # C2 口径脚注


# ---- ⑦ format_dex 满态：N/总数 + 缺失清单 ----

def test_format_dex_known_shows_denominator_and_missing():
    dto = DexProgressDTO(observed_count=1, total=3, buckets=[
        DexElementBucket("fire", [], ["火绒狐"]),
        DexElementBucket("neutral", ["皮皮鸡"], []),
    ])
    out = format_dex(dto, server_name="Palpagos")
    assert "1/3" in out
    assert "尚未被观测" in out and "火绒狐" in out


# ---- ⑧ format_dex 空图鉴 ----

def test_format_dex_empty():
    dto = DexProgressDTO(observed_count=0, total=None, buckets=[])
    out = format_dex(dto, server_name="Palpagos")
    assert "服务器图鉴" in out and "Palpagos" in out
