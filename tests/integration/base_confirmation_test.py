from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.base_service import BaseService
from palworld_terminal.domain.enums import ActionCategory, UnitType
from palworld_terminal.domain.models import CharacterActor, GameDataSnapshot, PalBoxActor, World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palworld_terminal.config import BasesConfig
    return BasesConfig(True, 5000, 0.2, 3, 2000, 0.5)  # confirmation_samples=3


def _bcp(x, y):
    return CharacterActor(UnitType.BASE_CAMP, None, None, None, None, None, 10, 100, 100,
                          "G1", None, "PalX", ActionCategory.WORKING,
                          ActionCategory.WORKING, x, y, 0.0, True)


def _gd(px, py, obs_at):
    return GameDataSnapshot(obs_at, 60.0, 60.0, [_bcp(px + 10, py + 10)],
                            [PalBoxActor("G1", None, "Box", px, py, 0.0)], [])


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = BaseService(repo, _cfg(), clock, b"0" * 32)
    return db, repo, svc


async def test_base_persisted_only_after_confirmation_samples(tmp_path):
    db, repo, svc = await _mk(tmp_path)
    u1 = await svc.apply(_world(), _gd(100.0, 200.0, 1000))
    assert await repo.list_bases("w1", include_low=True) == []  # 第1次不落
    assert all(not u.is_new for u in u1)
    await svc.apply(_world(), _gd(100.0, 200.0, 1030))            # 第2次不落
    assert await repo.list_bases("w1", include_low=True) == []
    u3 = await svc.apply(_world(), _gd(100.0, 200.0, 1060))       # 第3次落
    bases = await repo.list_bases("w1", include_low=True)
    assert len(bases) == 1
    assert any(u.is_new for u in u3)
    await db.close()


async def test_palbox_jitter_within_grid_does_not_create_second_base(tmp_path):
    db, repo, svc = await _mk(tmp_path)
    # 抖动都落在同一网格(grid=2000) → 同 palbox_key → 同 base_key
    await svc.apply(_world(), _gd(100.0, 200.0, 1000))
    await svc.apply(_world(), _gd(150.0, 250.0, 1030))
    await svc.apply(_world(), _gd(80.0, 190.0, 1060))
    bases = await repo.list_bases("w1", include_low=True)
    assert len(bases) == 1
    await db.close()
