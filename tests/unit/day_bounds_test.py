from types import SimpleNamespace

from palworld_terminal.application.report_service import day_bounds
from palworld_terminal.domain.models import World

_W = World(world_id="w:g:0", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)


def _cfg(server_tz="", world_tz="Asia/Tokyo"):
    return SimpleNamespace(
        servers=[SimpleNamespace(server_id="w", timezone=server_tz)],
        world=SimpleNamespace(timezone=world_tz),
    )


def test_day_bounds_is_24h_and_midnight_aligned():
    # Asia/Tokyo 无 DST：一天恰 86400s，start 对齐本地午夜
    day, start, end = day_bounds(_cfg(), _W, 1_700_000_000)
    assert end - start == 86400
    assert day == "2023-11-15"  # 2023-11-15 09:33:20 JST 所在自然日


def test_per_server_tz_overrides_world_tz():
    # server tz 优先于全局 tz
    _, s_utc, _ = day_bounds(_cfg(server_tz="UTC", world_tz="Asia/Tokyo"), _W, 1_700_000_000)
    _, s_jst, _ = day_bounds(_cfg(server_tz="", world_tz="Asia/Tokyo"), _W, 1_700_000_000)
    assert s_utc != s_jst  # 不同时区午夜起点不同
