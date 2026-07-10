from palchronicle.application.player_service import PlayerService
from palchronicle.application.guild_service import GuildService
from palchronicle.application.base_service import BaseService
from palchronicle.domain.models import (
    World, PlayerRow, PlayersSnapshot, CharacterActor, PalBoxActor, GameDataSnapshot,
)
from palchronicle.domain.enums import UnitType, ActionCategory
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 1, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


async def test_two_worlds_do_not_share_data(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); cfg = _cfg()
    ps = PlayerService(repo, b"s" * 32, cfg, clock); ps.events = FakeEvents()
    gs = GuildService(repo, b"s" * 32, clock); gs.events = FakeEvents()
    bs = BaseService(repo, cfg.bases, clock, b"s" * 32)

    wA = World("wA", "sA", "g", 0, "A", "1", 0, 0, 1)
    wB = World("wB", "sB", "g", 0, "B", "1", 0, 0, 1)

    row = PlayerRow("pkA", "p", "Alice", 5, 40.0, 3)
    await ps.apply_players(wA, PlayersSnapshot(1000, [row]))
    assert await repo.get_open_session("wA", "pkA") is not None
    assert await repo.get_open_session("wB", "pkA") is None  # 世界隔离

    gd = GameDataSnapshot(1000, 60.0, 60.0,
        [CharacterActor(UnitType.BASE_CAMP, None, None, None, None, None, 10, 100, 100,
                        "G1", "Alpha", "PalX", ActionCategory.WORKING,
                        ActionCategory.WORKING, 110.0, 210.0, 0.0, True)],
        [PalBoxActor("G1", "Alpha", "Box", 100.0, 200.0, 0.0)], [])
    await gs.apply(wA, gd)
    updates = await bs.apply(wA, gd)
    assert len(updates) == 1
    assert await repo.list_guilds("wB") == []
    assert await repo.list_bases("wB", include_low=True) == []
    await db.close()
