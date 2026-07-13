from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.player_service import PlayerService
from palworld_terminal.domain.enums import SessionStatus
from palworld_terminal.domain.models import PlayerRow, PlayersSnapshot, World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
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
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock); svc.events = FakeEvents()
    return db, clock, repo, svc


def _row():
    return PlayerRow(userid="pk-a", player_id="p", name="Alice", level=5, ping=40.0, building_count=3)


async def test_single_miss_keeps_active(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, []))  # 缺失 1
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess is not None and sess.status == SessionStatus.ACTIVE
    await db.close()


async def test_two_consecutive_misses_closes(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030); await svc.apply_players(_world(), PlayersSnapshot(1030, []))
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, []))
    assert await repo.get_open_session("w1", "pk-a") is None
    rows = await repo._db.query(
        "SELECT status, leave_reason, left_at FROM player_sessions WHERE player_key='pk-a'", ()
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "observed_timeout"
    assert rows[0]["left_at"] == 1060
    await db.close()


async def test_reappearance_resets_miss_streak(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030); await svc.apply_players(_world(), PlayersSnapshot(1030, []))     # miss 1
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, [_row()]))  # reappear
    clock.set(1090); await svc.apply_players(_world(), PlayersSnapshot(1090, []))     # miss 1 again
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess is not None and sess.status == SessionStatus.ACTIVE  # 未连续两次
    await db.close()
