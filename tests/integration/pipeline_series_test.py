from palchronicle.domain.enums import EventType, SessionStatus
from tests.fixtures.loader import load_fixture
from tests.integration.conftest import ok


async def _boot_world(snap, server, clock):
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    assert world is not None
    await snap.ingest_metrics(world, ok(load_fixture("normal_world", "metrics")))
    return world


async def test_session_online_then_offline(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)

    # 两个玩家在线
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    sessions = await container.repo.list_open_sessions(world.world_id)
    assert len(sessions) == 2
    assert all(s.status == SessionStatus.ACTIVE for s in sessions)

    # 连续两个健康快照缺失 → 关闭会话
    clock.advance(30)
    await snap.ingest_players(world, ok({"players": []}))
    clock.advance(30)
    await snap.ingest_players(world, ok({"players": []}))
    open_after = await container.repo.list_open_sessions(world.world_id)
    assert open_after == []


async def test_level_up_confirmed_event(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))

    # Akari 从 21 升到 23，连续两次观察确认
    up = {"players": [{"userId": "steam_00001", "playerId": "PID-1", "name": "Akari",
                       "level": 23, "ping": 44.0, "building_count": 12}]}
    clock.advance(30)
    await snap.ingest_players(world, ok(up))
    clock.advance(30)
    await snap.ingest_players(world, ok(up))

    events = await container.repo.list_events(world.world_id, since=None, limit=50)
    level_ups = [e for e in events if e.event_type == EventType.PLAYER_LEVEL_UP]
    assert len(level_ups) == 1
    assert level_ups[0].payload["new"] == 23


async def test_world_day_milestone_event(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)

    # metrics.days 从 42 跨过 100 里程碑
    m = load_fixture("normal_world", "metrics")
    m99 = {**m, "days": 99}
    m101 = {**m, "days": 101}
    await snap.ingest_metrics(world, ok(m99))
    await snap.ingest_metrics(world, ok(m101))

    events = await container.repo.list_events(world.world_id, since=None, limit=50)
    milestones = [e for e in events if e.event_type == EventType.WORLD_DAY_MILESTONE]
    assert len(milestones) == 1
    assert milestones[0].payload["milestone"] == 100
