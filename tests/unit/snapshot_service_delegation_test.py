from pathlib import Path

import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


class SpyPlayers:
    def __init__(self):
        self.applied = []
        self.uncertain = []

    async def apply_players(self, world, snap):
        self.applied.append((world.world_id, snap))

    async def mark_uncertain(self, world):
        self.uncertain.append(world.world_id)


class SpyAgg:
    def __init__(self):
        self.applied = []

    async def apply(self, world, gd):
        self.applied.append((world.world_id, gd))
        return []


def _cfg(mode="balanced"):
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig(mode, False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world():
    return World(
        world_id="s1:GUID-A:0", server_id="s1", worldguid="GUID-A", epoch=0,
        server_name="S", version="0.3", first_seen_at=1, last_seen_at=1,
        current_day=0,
    )


@pytest.fixture
async def make_svc(tmp_path):
    created = {}

    async def _factory(mode="balanced"):
        db = Database(tmp_path / f"{mode}.db")
        await db.open()
        await apply_migrations(db)
        clock = FakeClock(start=4000)
        meta = MetadataRepository(METADATA_DIR)
        meta.load()
        players = SpyPlayers()
        guilds = SpyAgg()
        bases = SpyAgg()
        svc = SnapshotService(
            repo=Repository(db, clock), normalizer_mod=normalizer_mod,
            privacy_mod=privacy_mod, meta=meta, salt=b"\x02" * 32, cfg=_cfg(mode),
            clock=clock, players=players, guilds=guilds, bases=bases, events=SpyAgg(),
        )
        created["db"] = db
        return svc, players, guilds, bases

    yield _factory
    if "db" in created:
        await created["db"].close()


def _players_resp(ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"players": [{"UserId": "u-1", "Name": "Alice", "Level": 5,
                           "Ping": 40, "BuildingCount": 2, "Ip": "10.0.0.1",
                           "AccountName": "steam_a"}]} if ok else None,
        duration_ms=2, payload_bytes=5, error=None if ok else "timeout",
    )


def _game_data_resp(ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"characters": [
            {"type": "Player", "userid": "raw-1", "Level": 5,
             "GuildID": "g1", "locationx": 1, "locationy": 2, "locationz": 3,
             "isactive": "true"}
        ], "palboxes": [
            {"guildid": "g1", "class": "PalDataParameter/SheepBall",
             "locationx": 1, "locationy": 2, "locationz": 3}
        ]} if ok else None,
        duration_ms=9, payload_bytes=99, error=None if ok else "timeout",
    )


async def test_ingest_players_delegates_redacted_snapshot(make_svc):
    svc, players, _, _ = await make_svc("balanced")
    await svc.ingest_players(_world(), _players_resp())
    assert len(players.applied) == 1
    world_id, snap = players.applied[0]
    assert world_id == "s1:GUID-A:0"
    row = snap.players[0]
    assert row.name == "Alice"
    # 脱敏发生: userid 已 hash, 无原始 id / ip
    assert row.userid != "u-1"
    assert "10.0.0.1" not in repr(snap)
    assert "steam_a" not in repr(snap)


async def test_ingest_players_failure_marks_uncertain(make_svc):
    svc, players, _, _ = await make_svc("balanced")
    await svc.ingest_players(_world(), _players_resp(ok=False))
    assert players.applied == []
    assert players.uncertain == ["s1:GUID-A:0"]


async def test_ingest_game_data_delegates_to_guilds_and_bases(make_svc):
    svc, _, guilds, bases = await make_svc("balanced")
    await svc.ingest_game_data(_world(), _game_data_resp())
    assert len(guilds.applied) == 1
    assert len(bases.applied) == 1
    _, gd = guilds.applied[0]
    assert len(gd.characters) == 1
    # 身份脱敏发生在委托前
    assert gd.characters[0].player_userid != "raw-1"


async def test_ingest_game_data_strict_drops_palboxes_before_delegate(make_svc):
    svc, _, guilds, bases = await make_svc("strict")
    await svc.ingest_game_data(_world(), _game_data_resp())
    _, gd = bases.applied[0]
    assert gd.palboxes == []
    assert gd.characters[0].x is None


async def test_ingest_game_data_failure_no_delegate(make_svc):
    svc, _, guilds, bases = await make_svc("balanced")
    await svc.ingest_game_data(_world(), _game_data_resp(ok=False))
    assert guilds.applied == []
    assert bases.applied == []
