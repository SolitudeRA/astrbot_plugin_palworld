from palchronicle.application.guild_service import GuildService
from palchronicle.domain.models import CharacterActor, PalBoxActor, GameDataSnapshot, World
from palchronicle.domain.enums import UnitType, ActionCategory
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    def __init__(self): self.new_guilds = []
    async def new_guild(self, world, guild_key): self.new_guilds.append(guild_key)
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _char(unit_type, guild_id=None, guild_name=None):
    return CharacterActor(unit_type, None, None, None, None, None, None, None, None,
                          guild_id, guild_name, None, ActionCategory.IDLE,
                          ActionCategory.IDLE, None, None, None, True)


def _pb(guild_id):
    return PalBoxActor(guild_id, None, "Box", 0.0, 0.0, 0.0)


def _gd(chars, boxes):
    return GameDataSnapshot(1000, 60.0, 60.0, chars, boxes, [])


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = GuildService(repo, b"0" * 32, clock); events = FakeEvents(); svc.events = events
    return db, repo, svc, events


async def test_aggregates_multiple_guilds(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd(
        chars=[
            _char(UnitType.PLAYER, "G1", "Alpha"),
            _char(UnitType.PLAYER, "G1", "Alpha"),
            _char(UnitType.BASE_CAMP, "G1", "Alpha"),
            _char(UnitType.PLAYER, "G2", "Beta"),
        ],
        boxes=[_pb("G1"), _pb("G1"), _pb("G2")],
    )
    guilds = await svc.apply(_world(), gd)
    by_name = {g.latest_name: g for g in guilds}
    assert by_name["Alpha"].observed_member_count == 2
    assert by_name["Alpha"].palbox_count == 2
    assert by_name["Alpha"].base_pal_count == 1
    assert by_name["Beta"].observed_member_count == 1
    assert by_name["Beta"].palbox_count == 1
    assert len(events.new_guilds) == 2  # 首见两公会
    persisted = {g.latest_name for g in await repo.list_guilds("w1")}
    assert persisted == {"Alpha", "Beta"}
    await db.close()


async def test_missing_guild_id_not_grouped(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd([_char(UnitType.PLAYER, None, None), _char(UnitType.PLAYER, "G1", "Alpha")], [])
    guilds = await svc.apply(_world(), gd)
    assert {g.latest_name for g in guilds} == {"Alpha"}
    await db.close()


async def test_missing_guild_name_degrades(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd([_char(UnitType.PLAYER, "G1", None)], [])
    guilds = await svc.apply(_world(), gd)
    assert guilds[0].latest_name.startswith("公会-")
    await db.close()


async def test_new_guild_only_first_time(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd([_char(UnitType.PLAYER, "G1", "Alpha")], [])
    await svc.apply(_world(), gd)
    await svc.apply(_world(), gd)
    assert len(events.new_guilds) == 1
    await db.close()
