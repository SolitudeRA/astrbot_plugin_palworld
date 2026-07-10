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
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


class SpyPlayers:
    def __init__(self):
        self.snapshots = []

    async def apply_players(self, world, snap):
        self.snapshots.append(snap)

    async def mark_uncertain(self, world):
        return None


class SpyAgg:
    async def apply(self, world, gd):
        return []


def _server():
    return ServerConfig(
        server_id="srvA", name="srvA", enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _cfg():
    return AppConfig(
        servers=[_server()], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.0, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
async def ctx(tmp_path):
    db = Database(tmp_path / "pipeline.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=10000)
    repo = Repository(db, clock)
    meta = MetadataRepository(METADATA_DIR)
    meta.load()
    players = SpyPlayers()
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=meta, salt=b"\x11" * 32, cfg=_cfg(), clock=clock,
        players=players, guilds=SpyAgg(), bases=SpyAgg(), events=SpyAgg(),
    )
    yield svc, repo, clock, players, db
    await db.close()


async def test_full_ingest_pipeline_builds_world_and_metrics_no_pii(ctx):
    svc, repo, clock, players, db = ctx
    info = RestResponse(ok=True, status=200,
                        data={"Version": "0.3", "ServerName": "Alpha", "WorldGuid": "WG-1"},
                        duration_ms=1, payload_bytes=1, error=None)
    metrics = RestResponse(ok=True, status=200,
                           data={"ServerFps": 58, "ServerFrameTime": 17, "CurrentPlayerNum": 2,
                                 "MaxPlayerNum": 32, "Uptime": 500, "Days": 9, "BaseCampNum": 3},
                           duration_ms=1, payload_bytes=1, error=None)
    players_resp = RestResponse(ok=True, status=200,
                                data={"players": [{"UserId": "secret-uid-777", "Name": "Zed",
                                                   "Level": 8, "Ping": 200, "BuildingCount": 4,
                                                   "Ip": "203.0.113.9", "AccountName": "steam_zed"}]},
                                duration_ms=1, payload_bytes=1, error=None)

    world = await svc.ingest_info(_server(), info)
    assert world.world_id == "srvA:WG-1:0"
    await svc.ingest_metrics(world, metrics)
    await svc.ingest_players(world, players_resp)

    m = await repo.latest_metric("srvA:WG-1:0")
    assert m.online_players == 2 and m.world_day == 9 and m.basecamp_count == 3

    # 脱敏快照(内存)已到达 players
    assert players.snapshots[0].players[0].name == "Zed"
    assert players.snapshots[0].players[0].userid != "secret-uid-777"

    # 隐私红线: DB 全表 dump 无 IP / 原始 id / 原始账号
    dumped = await _dump_all_text(db)
    assert "203.0.113.9" not in dumped
    assert "secret-uid-777" not in dumped
    assert "steam_zed" not in dumped


async def _dump_all_text(db) -> str:
    tables = await db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    parts = []
    for t in tables:
        name = t["name"]
        rows = await db.query(f"SELECT * FROM {name}")
        for r in rows:
            parts.append("|".join(str(r[k]) for k in r.keys()))
    return "\n".join(parts)
