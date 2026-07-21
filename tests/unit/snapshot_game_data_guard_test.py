"""guilds_bases 禁用时 guilds/bases 为 None → ingest_game_data 首行短路（spec §4.2）。"""
from palworld_terminal.adapters import normalizer as _norm
from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.application.snapshot_service import SnapshotService
from palworld_terminal.domain import privacy as _priv
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.clock import FakeClock


def _snap(guilds, bases, events, shared_world):
    class _Cfg:  # 最小 cfg 占位（ingest_game_data 短路前不触 cfg）
        pass
    return SnapshotService(
        None, _norm, _priv, None, b"salt", _Cfg(), FakeClock(0),
        players=None, guilds=guilds, bases=bases, events=events,
        shared_settings={}, shared_world=shared_world,
    )


async def test_ingest_game_data_noop_when_guilds_none():
    shared = {}
    snap = _snap(guilds=None, bases=None, events=None, shared_world=shared)
    resp = RestResponse(ok=True, status=200, data={"characters": []},
                        duration_ms=1, payload_bytes=2, error=None)
    world = World("alpha:g:0", "alpha", "g", 0, "alpha", "0.3", 900, 1200, 42)
    await snap.ingest_game_data(world, resp)   # 不得抛
    assert shared == {}                        # 短路在 _world_cache 写入之前
