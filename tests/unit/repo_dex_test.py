import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_upsert_inserts_then_reads(repo):
    await repo.upsert_observed_species("BP_ChickenPal_C", "鸡", "grass", 1000, "小鸡")
    rows = await repo.observed_species()
    assert len(rows) == 1
    r = rows[0]
    assert r.species_class == "BP_ChickenPal_C"
    assert r.species_name == "鸡"
    assert r.element == "grass"
    assert r.first_seen_at == 1000
    assert r.first_seen_name == "小鸡"
    assert r.observe_count == 1


async def test_conflict_increments_and_pins_first_seen(repo):
    await repo.upsert_observed_species("BP_ChickenPal_C", "鸡", "grass", 1000, "小鸡")
    # 二次观测：换了明文名与时刻——首见字段须钉死，仅计数自增
    await repo.upsert_observed_species("BP_ChickenPal_C", "鸡", "grass", 2000, "打工鸡")
    rows = await repo.observed_species()
    assert len(rows) == 1
    r = rows[0]
    assert r.observe_count == 2
    assert r.first_seen_at == 1000          # 首见时刻不被覆盖
    assert r.first_seen_name == "小鸡"        # 首见明文名不被覆盖


async def test_first_seen_name_none_stored_as_null(repo):
    await repo.upsert_observed_species("BP_FoxPal_C", "狐", "fire", 1000, None)
    rows = await repo.observed_species()
    assert rows[0].first_seen_name is None


async def test_observed_species_orders_by_class(repo):
    await repo.upsert_observed_species("BP_ZebraPal_C", "斑马", "ground", 1000, None)
    await repo.upsert_observed_species("BP_AntPal_C", "蚁", "ground", 1000, None)
    rows = await repo.observed_species()
    assert [r.species_class for r in rows] == ["BP_AntPal_C", "BP_ZebraPal_C"]
