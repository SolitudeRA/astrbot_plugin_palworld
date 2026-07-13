from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.player_service import PlayerService
from palworld_terminal.domain.models import PlayerRow, PlayersSnapshot, World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


class FakeEvents:
    def __init__(self):
        self.new_players, self.level_ups = [], []
    async def new_player(self, world, player_key): self.new_players.append(player_key)
    async def level_up(self, world, player_key, old, new): self.level_ups.append((player_key, old, new))
    async def new_guild(self, world, guild_key): pass


def _world():
    return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


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
    clock = FakeClock(1000); repo = Repository(db, clock); events = FakeEvents()
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock); svc.events = events
    return db, clock, repo, events, svc


def _row(level=5):
    return PlayerRow(userid="pk-a", player_id="p", name="Alice", level=level, ping=40.0, building_count=3)


async def test_observed_seconds_accumulates_within_tolerance(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, [_row()]))
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.observed_seconds == 30  # 30 <= 30*1.5
    assert sess.last_confirmed_at == 1030
    await db.close()


async def test_observed_seconds_capped_on_large_gap(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1000 + 600)  # 600s 间隔（API 中断），players_seconds=30, cap=45
    await svc.apply_players(_world(), PlayersSnapshot(1600, [_row()]))
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.observed_seconds == 45  # min(600, 30*1.5)
    await db.close()


async def test_level_up_emits_event(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row(level=5)]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, [_row(level=8)]))
    assert events.level_ups == [("pk-a", 5, 8)]
    await db.close()


async def test_level_down_no_event(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row(level=8)]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, [_row(level=5)]))
    assert events.level_ups == []
    await db.close()
