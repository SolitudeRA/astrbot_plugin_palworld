from palchronicle.domain.enums import EventType, SessionStatus
from tests.fixtures.loader import load_fixture
from tests.integration.conftest import fail, ok


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


async def test_api_interrupt_does_not_falsely_close_session(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    before = await container.repo.list_open_sessions(world.world_id)
    assert len(before) == 2

    # /players 端点整体失败（非空快照缺人）→ 会话置 uncertain，不结束
    clock.advance(30)
    await snap.ingest_players(world, fail(status=None, error="timeout"))
    clock.advance(30)
    await snap.ingest_players(world, fail(status=None, error="timeout"))

    sessions = await container.repo.list_open_sessions(world.world_id)
    assert len(sessions) == 2  # 仍是开着的会话，未被误判为离线
    assert all(s.status == SessionStatus.UNCERTAIN for s in sessions)


async def test_uncertain_session_reused_on_recovery(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))

    open0 = await container.repo.list_open_sessions(world.world_id)
    joined_at_before = min(s.joined_at for s in open0)
    ids_before = {s.id for s in open0}

    # API 中断 → uncertain
    clock.advance(30)
    await snap.ingest_players(world, fail(error="timeout"))
    uncertain = await container.repo.list_open_sessions(world.world_id)
    assert all(s.status == SessionStatus.UNCERTAIN for s in uncertain)

    # 恢复：同玩家再现 → 复用原会话（不新建），joined_at 不变、id 不变、时长连续累加
    clock.advance(60)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    recovered = await container.repo.list_open_sessions(world.world_id)
    assert all(s.status == SessionStatus.ACTIVE for s in recovered)
    assert {s.id for s in recovered} == ids_before          # 复用同一批会话 id，无新建
    assert min(s.joined_at for s in recovered) == joined_at_before
    # 无悬空 uncertain：开着的会话总数仍为 2
    assert len(recovered) == 2
