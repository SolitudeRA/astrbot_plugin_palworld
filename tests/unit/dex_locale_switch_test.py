"""Task 15（spec critical 修）：dex 展示名**查询时按 species_class 经 meta 现解**——
历史落库的 species_name（ingest 当时的渲染名）不再随 locale 混杂。

旧行为：dex_progress() 用 ingest 落库的 species_name 构桶 → 切语言后历史观测行永不刷新
→ 图鉴语言混杂。新行为：查询时按 species_class 经 MetadataRepository.pal_name_or 现解；
meta 查不到的未知 class 优雅回退 DB species_name（历史落库名兜底，不被现解顶掉）。"""
from pathlib import Path

import pytest

from palworld_terminal.adapters.metadata_repository import MetadataRepository
from palworld_terminal.adapters.sqlite_repository import Repository
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

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


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


def _meta(locale: str) -> MetadataRepository:
    meta = MetadataRepository(METADATA_DIR, locale)
    meta.load()
    return meta


def _qs(repo, clock, meta) -> QueryService:
    return QueryService(repo, TTLCache(clock), _cfg(), meta, clock, {}, world_cache={})


@pytest.fixture
async def env(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    yield repo, clock
    await db.close()


# ---- ① 现解覆盖历史落库名：zh 落库 → en 现解 → 桶内英文名（历史 zh 名被顶掉）----

async def test_live_resolve_overrides_historical_persisted_name(env):
    repo, clock = env
    # 模拟历史 zh 落库：species_name 落中文「皮皮鸡」（ingest 当时的渲染名）。
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1200, None)
    # 切 en：dex 按 species_class 经 meta 现解 → "Chikipi"，历史 zh 名不再泄漏到英文图鉴。
    dto = await _qs(repo, clock, _meta("en")).dex_progress()
    by = {b.element: b for b in dto.buckets}
    assert by["neutral"].observed == ["Chikipi"]
    assert all("皮皮鸡" not in b.observed for b in dto.buckets)


# ---- ② 未知 class（meta 查不到）优雅回退 DB 落库名 ----

async def test_unknown_class_falls_back_to_persisted_name(env):
    repo, clock = env
    # meta 查不到的 class（不在 pals.json）——DB 落库名兜底、不被现解顶成类名缩写。
    await repo.upsert_observed_species(
        "BP_TotallyUnknownMysteryPal_C", "神秘帕鲁", "neutral", 1200, None
    )
    dto = await _qs(repo, clock, _meta("en")).dex_progress()
    by = {b.element: b for b in dto.buckets}
    assert by["neutral"].observed == ["神秘帕鲁"]


# ---- ③ zh 下同名同值（dex golden 输出不变佐证）----

async def test_zh_resolve_is_same_name_same_value(env):
    repo, clock = env
    await repo.upsert_observed_species("BP_ChickenPal_C", "皮皮鸡", "neutral", 1200, None)
    dto = await _qs(repo, clock, _meta("zh-CN")).dex_progress()
    by = {b.element: b for b in dto.buckets}
    assert by["neutral"].observed == ["皮皮鸡"]
