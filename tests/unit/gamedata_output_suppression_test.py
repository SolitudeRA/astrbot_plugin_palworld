"""game-data 输出屏蔽链路锁定（spec §3.6 / §5B⑥）。

承重命题**不在 formatter 层**（golden today.txt 保留「据点变化」渲染能力是有意的，
直喂空 DTO 属同义反复），而在两处上游：

1. **写侧**：guild 组上游不可用 force-off 后，生产装配门读生效值（effective_enabled
   恒 False）→ 容器不装配 GuildService/BaseService（snapshot._guilds/_bases 为 None），
   携带公会/据点载荷驱动 ingest_game_data 仍整体短路 → events 表零
   NEW_GUILD/NEW_BASE/BASE_VANISHED/WORKER_DELTA 行落库。
   ⚠️ 本测试**必须走生产装配路径**（不经 integration/conftest 的 _wire_game_data
   helper）——测的就是生产门关着。

2. **装配层**：guilds/bases 缺席 → daily 报告 DTO 的 base_events 为空、records 无
   新公会/新据点行、summary 无「N 处据点变化」；world events 查询无公会/据点类条目。
"""
from pathlib import Path

from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.application.command_permissions import CommandOverride as CO
from palworld_terminal.config import parse_config
from palworld_terminal.container import Container
from palworld_terminal.domain.enums import EventType
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.presentation.event_wording import render_event
from tests.fixtures.loader import load_fixture

# game-data 唯一产生的事件家族（spec §3.6 四枚举）
_GAME_DATA_EVENTS = {
    EventType.NEW_GUILD,
    EventType.NEW_BASE,
    EventType.BASE_VANISHED,
    EventType.WORKER_DELTA,
}


class _FakeRest:
    async def close(self): ...


class _FakeSched:
    async def start(self): ...
    async def stop(self): ...


def _ok(data) -> RestResponse:
    return RestResponse(ok=True, status=200, data=data, duration_ms=5,
                        payload_bytes=len(str(data)), error=None)


def _cfg_guild_on():
    # command_overrides 显式把 guild 组写 on：模拟「存量配置手写启用」——证明即便如此，
    # 生产装配门读生效值（force-off 恒 False）仍不接线 game-data（不经 features 直注）。
    cfg = parse_config({
        "servers": [{"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw", "timezone": "Asia/Tokyo"}],
        "routing": {"access_mode": "open", "default_server": ""}, "group_bindings": [],
        "polling": {}, "world": {"timezone": "Asia/Tokyo"}, "bases": {"enabled": True},
        "privacy": {"mode": "balanced"}, "history": {},
    }, {})
    cfg.permissions.command_overrides = {"guild": CO(enabled=True)}
    return cfg


async def _boot_production_container(tmp_path: Path):
    """生产装配路径（**不经 _wire_game_data**）：guild 写 on 但 force-off 生效
    → snapshot._guilds/_bases 恒 None。返回 (container, server, clock, snap)。"""
    clock = FakeClock(start=1_700_000_000)
    c = Container(_cfg_guild_on(), tmp_path, clock,
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **kw: _FakeSched())
    await c.start()
    server = c.config.servers[0]
    snap = c.snapshot_service()
    return c, server, clock, snap


async def _drive_game_data(snap, world, clock) -> None:
    # 载荷含 G-1 公会 + BaseCampPal + palbox；驱动 > confirmation_samples(3) 次：
    # 若装配在场，本序列会落 NEW_GUILD + NEW_BASE（见 pipeline_series_test）。
    gd = load_fixture("normal_world", "game-data")
    for _ in range(4):
        clock.advance(30)
        await snap.ingest_game_data(world, _ok(gd))


async def test_write_side_no_game_data_events_persisted(tmp_path: Path):
    """写侧：force-off 生产装配下驱动含公会/据点载荷的 ingest_game_data 多次 →
    events 表零 game-data 家族行，且据点/公会派生表零持久化。"""
    c, server, clock, snap = await _boot_production_container(tmp_path)
    try:
        # 装配缺席（生产门关着，非 _wire_game_data 补装）——这正是无事件落库的机制。
        assert snap._guilds is None and snap._bases is None

        world = await snap.ingest_info(server, _ok(load_fixture("normal_world", "info")))
        assert world is not None
        await snap.ingest_metrics(world, _ok(load_fixture("normal_world", "metrics")))
        await _drive_game_data(snap, world, clock)

        events = await c.repo.list_events(world.world_id, since=None, limit=200)
        offenders = [e for e in events if e.event_type in _GAME_DATA_EVENTS]
        assert offenders == [], f"force-off 下不应落 game-data 事件: {offenders}"

        # game-data 派生持久化亦缺席：据点/公会从未落库（写侧不产的硬保证）。
        assert await c.repo.list_guilds(world.world_id) == []
        assert await c.repo.list_bases(
            world.world_id, include_low=True, include_hidden=True
        ) == []
    finally:
        await c.stop()


async def test_assembly_layer_report_and_events_have_no_guild_base_content(tmp_path: Path):
    """装配层：guilds/bases 缺席 → daily DTO 无 base_events/新公会/新据点行、summary
    无「据点变化」；world events 查询无公会/据点类条目（非 game-data 内容照常渲染）。"""
    c, server, clock, snap = await _boot_production_container(tmp_path)
    try:
        world = await snap.ingest_info(server, _ok(load_fixture("normal_world", "info")))
        await snap.ingest_metrics(world, _ok(load_fixture("normal_world", "metrics")))
        await snap.ingest_players(world, _ok(load_fixture("normal_world", "players")))
        await _drive_game_data(snap, world, clock)

        report = await c.report.daily(world)
        # 正对照：非 game-data 记录（新玩家）照常渲染 → 证明报告机制在场，屏蔽是差分的。
        assert any("新玩家" in render_event(r) for r in report.records)
        # game-data 派生三处渲染面（今日纪录公会/据点、据点变化节、summary）全空：
        assert report.base_changes == []
        assert not any(("新公会" in render_event(r) or "新据点" in render_event(r)) for r in report.records)
        assert "据点变化" not in report.summary

        dtos = await c.query.events(world, today_only=False)
        # EventView.event_type 现为 EventType 枚举成员：护栏须以枚举成员集判定（非 .value 串集），
        # 否则枚举化后 `EventType in {str}` 恒 False，假绿架空屏蔽护栏。
        base_family = set(_GAME_DATA_EVENTS)
        assert not any(d.event_type in base_family for d in dtos)
    finally:
        await c.stop()
