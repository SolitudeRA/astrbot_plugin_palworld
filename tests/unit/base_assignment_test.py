from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.base_service import BaseService
from palworld_terminal.domain.enums import ActionCategory, Confidence, UnitType
from palworld_terminal.domain.models import CharacterActor, GameDataSnapshot, PalBoxActor, World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg(confirmation=1):
    from palworld_terminal.config import BasesConfig
    return BasesConfig(True, 5000, 0.2, confirmation, 2000, 0.5)


def _bcp(guild_id, x, y, level=10, action=ActionCategory.WORKING, hp=100, max_hp=100):
    return CharacterActor(UnitType.BASE_CAMP, None, None, None, None, None, level,
                          hp, max_hp, guild_id, None, "PalX", action, action, x, y, 0.0, True)


def _pb(guild_id, x, y):
    return PalBoxActor(guild_id, None, "Box", x, y, 0.0)


def _gd(chars, boxes):
    return GameDataSnapshot(1000, 60.0, 60.0, chars, boxes, [])


async def _mk(tmp_path, confirmation=1):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = BaseService(repo, _cfg(confirmation), clock, b"0" * 32)
    return db, repo, svc


async def test_assigns_pal_to_nearest_palbox_high_confidence(tmp_path):
    db, repo, svc = await _mk(tmp_path, confirmation=1)
    gd = _gd([_bcp("G1", 110.0, 210.0)], [_pb("G1", 100.0, 200.0)])
    updates = await svc.apply(_world(), gd)
    assert len(updates) == 1
    u = updates[0]
    assert u.worker_count == 1
    assert u.active_count == 1
    assert u.confidence == Confidence.HIGH  # d≈14 << 2500
    assert u.is_new is True
    bases = await repo.list_bases("w1", include_low=True)
    assert len(bases) == 1
    assert bases[0].base_key == u.base_key
    await db.close()


async def test_far_pal_unassigned(tmp_path):
    db, repo, svc = await _mk(tmp_path, confirmation=1)
    gd = _gd([_bcp("G1", 90000.0, 90000.0)], [_pb("G1", 100.0, 200.0)])
    updates = await svc.apply(_world(), gd)
    # pal 过远(>assignment_radius) → 不计入任何 base 的 worker
    assert all(u.worker_count == 0 for u in updates) or updates == []
    await db.close()


async def test_ambiguous_two_close_palboxes_low(tmp_path):
    db, repo, svc = await _mk(tmp_path, confirmation=1)
    # 两箱落入相隔≥2格的不同 cell(0:0:0 与 2:0:0, grid=2000), 避免量化塌缩/相邻格复用;
    # pal 居中: d_A≈1900, d_B≈2100, 两距差比 (2100-1900)/2100≈0.095 < 0.2 → ambiguous → low
    gd = _gd(
        [_bcp("G1", 2400.0, 0.0)],
        [_pb("G1", 500.0, 0.0), _pb("G1", 4500.0, 0.0)],
    )
    updates = await svc.apply(_world(), gd)
    assigned = [u for u in updates if u.worker_count > 0]
    assert assigned and assigned[0].confidence == Confidence.LOW
    await db.close()
