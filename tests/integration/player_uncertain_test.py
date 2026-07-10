from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.domain.enums import SessionStatus, LeaveReason
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
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


async def test_mark_uncertain_does_not_close(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1050)
    await svc.mark_uncertain(_world())
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.status == SessionStatus.UNCERTAIN
    assert sess.joined_at == 1000
    assert sess.left_at is None
    await db.close()


async def test_uncertain_recovery_reuses_same_session(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    first = await repo.get_open_session("w1", "pk-a")
    # /players 中断 30s 后又中断，标 uncertain
    clock.set(1030); await svc.mark_uncertain(_world())
    # 恢复：同玩家再现
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, [_row()]))
    resumed = await repo.get_open_session("w1", "pk-a")
    assert resumed.id == first.id           # 复用同会话, 不新建
    assert resumed.status == SessionStatus.ACTIVE
    assert resumed.joined_at == 1000        # joined_at 不变
    assert resumed.observed_seconds == 45   # min(1060-1000, 45) 连续累计
    await db.close()


async def test_sweep_closes_stale_uncertain(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1010); await svc.mark_uncertain(_world())
    clock.set(1010 + 901)  # last_confirmed_at=1000, timeout 900
    await svc.sweep_uncertain(_world())
    assert await repo.get_open_session("w1", "pk-a") is None
    rows = await repo._db.query(
        "SELECT status, leave_reason FROM player_sessions WHERE player_key='pk-a'", ()
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    await db.close()


async def test_sweep_keeps_fresh_uncertain(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1010); await svc.mark_uncertain(_world())
    clock.set(1500)  # 500s < 900
    await svc.sweep_uncertain(_world())
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.status == SessionStatus.UNCERTAIN
    await db.close()
