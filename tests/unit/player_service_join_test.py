from palworld_terminal.application.player_service import PlayerService
from palworld_terminal.domain.enums import IdConfidence, SessionStatus
from palworld_terminal.domain.models import PlayerRow, PlayersSnapshot, World
from palworld_terminal.infrastructure.clock import FakeClock


class FakeEvents:
    def __init__(self):
        self.new_players = []
        self.level_ups = []

    async def new_player(self, world, player_key):
        self.new_players.append(player_key)

    async def level_up(self, world, player_key, old, new):
        self.level_ups.append((player_key, old, new))

    async def new_guild(self, world, guild_key):
        pass


def _world():
    return World(world_id="w1", server_id="s1", worldguid="g", epoch=0,
                 server_name="S", version="1", first_seen_at=0,
                 last_seen_at=0, current_day=1)


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
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(AccessMode.RESTRICTED, ""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


async def test_first_appearance_creates_active_session(tmp_path):
    from palworld_terminal.adapters.sqlite_repository import Repository
    from palworld_terminal.infrastructure.database import Database
    from palworld_terminal.infrastructure.migrations import apply_migrations
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); events = FakeEvents()
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock)
    svc.events = events
    world = _world()
    row = PlayerRow(userid="pk-alice", player_id="pid", name="Alice",
                    level=5, ping=40.0, building_count=3)
    await svc.apply_players(world, PlayersSnapshot(observed_at=1000, players=[row]))

    sess = await repo.get_open_session("w1", "pk-alice")
    assert sess is not None
    assert sess.status == SessionStatus.ACTIVE
    assert sess.joined_at == 1000
    assert sess.last_confirmed_at == 1000
    assert sess.observed_seconds == 0
    assert events.new_players == ["pk-alice"]

    ident = await repo.get_player_by_name("w1", "Alice")
    assert ident.player_key == "pk-alice"
    assert ident.latest_level == 5
    assert ident.id_confidence == IdConfidence.HIGH

    obs = await repo.latest_observation("w1", "pk-alice")
    assert obs.level == 5
    assert obs.building_count == 3
    await db.close()


async def test_second_appearance_no_duplicate_new_player(tmp_path):
    from palworld_terminal.adapters.sqlite_repository import Repository
    from palworld_terminal.infrastructure.database import Database
    from palworld_terminal.infrastructure.migrations import apply_migrations
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); events = FakeEvents()
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock)
    svc.events = events
    world = _world()
    row = PlayerRow(userid="pk-alice", player_id="pid", name="Alice",
                    level=5, ping=40.0, building_count=3)
    await svc.apply_players(world, PlayersSnapshot(1000, [row]))
    clock.set(1030)
    await svc.apply_players(world, PlayersSnapshot(1030, [row]))
    assert events.new_players == ["pk-alice"]  # 只一次
    await db.close()
