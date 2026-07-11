from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.player_service import PlayerService
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import ServerConfig
from palchronicle.domain.enums import SessionStatus
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (
        AppConfig,
        BasesConfig,
        HistoryConfig,
        PollingConfig,
        PrivacyConfig,
        RoutingConfig,
        WorldConfig,
    )
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock); svc.events = FakeEvents()
    return db, clock, repo, svc


def _row():
    return PlayerRow(userid="pk-a", player_id="p", name="Alice", level=5, ping=40.0, building_count=3)


async def test_mark_uncertain_does_not_close(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1050)
    await svc.mark_uncertain(_world())
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.status == SessionStatus.UNCERTAIN
    assert sess.joined_at == 1000
    assert sess.left_at is None
    await db.close()


async def test_uncertain_recovery_reuses_same_session(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    first = await repo.get_open_session("w1", "pk-a")
    # /players 中断 30s 后又中断，标 uncertain
    clock.set(1030); await svc.mark_uncertain(_world())
    # 恢复：同玩家再现
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, [_row()]))
    resumed = await repo.get_open_session("w1", "pk-a")
    assert resumed.id == first.id           # 复用同会话, 不新建
    assert resumed.status == SessionStatus.ACTIVE
    assert resumed.joined_at == 1000        # joined_at 不变
    assert resumed.observed_seconds == 45   # min(1060-1000, 45) 连续累计
    await db.close()


async def test_sweep_closes_stale_uncertain(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1010); await svc.mark_uncertain(_world())
    clock.set(1010 + 901)  # last_confirmed_at=1000, timeout 900
    await svc.sweep_uncertain(_world())
    assert await repo.get_open_session("w1", "pk-a") is None
    rows = await repo._db.query(
        "SELECT status, leave_reason FROM player_sessions WHERE player_key='pk-a'", ()
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    await db.close()


async def test_sweep_keeps_fresh_uncertain(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1010); await svc.mark_uncertain(_world())
    clock.set(1500)  # 500s < 900
    await svc.sweep_uncertain(_world())
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.status == SessionStatus.UNCERTAIN
    await db.close()


# ---- sweep_uncertain 运行时接线（经 SnapshotService 的真实采集路径）----

def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _info_resp(worldguid):
    return RestResponse(ok=True, status=200,
                        data={"Version": "0.3", "ServerName": "S", "WorldGuid": worldguid},
                        duration_ms=1, payload_bytes=1, error=None)


def _players_resp(names):
    data = {"players": [{"UserId": f"uid-{n}", "Name": n, "Level": 5,
                         "Ping": 40, "BuildingCount": 1} for n in names]}
    return RestResponse(ok=True, status=200, data=data,
                        duration_ms=1, payload_bytes=1, error=None)


def _fail_resp():
    return RestResponse(ok=False, status=None, data=None,
                        duration_ms=1, payload_bytes=0, error="timeout")


async def _mk_snapshot(tmp_path):
    db = Database(tmp_path / "snap.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    players = PlayerService(repo, b"0" * 32, _cfg(), clock); players.events = FakeEvents()
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=None, salt=b"0" * 32, cfg=_cfg(), clock=clock,
        players=players, guilds=None, bases=None, events=None,
    )
    return db, clock, repo, svc


async def test_players_recovery_sweeps_timed_out_uncertain(tmp_path):
    """§10.1 路径一: /players 失败置 uncertain, 端点恢复后未回归且超时的会话立即收敛。"""
    db, clock, repo, svc = await _mk_snapshot(tmp_path)
    world = await svc.ingest_info(_server(), _info_resp("G1"))
    await svc.ingest_players(world, _players_resp(["Alice", "Bob"]))
    # /players 端点失败 → 全部置 uncertain（last_confirmed_at 停在 1000）
    clock.set(1030)
    await svc.ingest_players(world, _fail_resp())
    # 端点恢复健康: Bob 回归, Alice 未回归且已超 uncertain_timeout(900)
    clock.set(1000 + 901)
    await svc.ingest_players(world, _players_resp(["Bob"]))

    alice = await repo.get_player_by_name(world.world_id, "Alice")
    bob = await repo.get_player_by_name(world.world_id, "Bob")
    assert await repo.get_open_session(world.world_id, alice.player_key) is None
    rows = await repo._db.query(
        "SELECT status, leave_reason, left_at FROM player_sessions WHERE player_key=?",
        (alice.player_key,),
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    assert rows[0]["left_at"] == 1901
    # 回归玩家恢复 active, 不被 sweep 波及
    bob_sess = await repo.get_open_session(world.world_id, bob.player_key)
    assert bob_sess.status == SessionStatus.ACTIVE
    await db.close()


async def test_stale_world_players_tick_does_not_resurrect_sessions(tmp_path):
    """竞态: PLAYERS 任务在 get_current_world 处拿到旧世界 A 后, INFO 任务完成
    A→B 切换; 恢复的 PLAYERS 任务以过期的 A 调 ingest_players(健康响应)。
    不得复活 A 的 uncertain 会话, 也不得把 A 从待收敛表丢掉。"""
    db, clock, repo, svc = await _mk_snapshot(tmp_path)
    world_a = await svc.ingest_info(_server(), _info_resp("G-A"))
    await svc.ingest_players(world_a, _players_resp(["Alice"]))
    stale = world_a  # PLAYERS 任务挂起期间持有的旧世界引用
    clock.set(1030)
    world_b = await svc.ingest_info(_server(), _info_resp("G-B"))
    assert world_b.world_id != world_a.world_id
    # 恢复的 PLAYERS 任务: 以过期 world 提交健康快照
    await svc.ingest_players(stale, _players_resp(["Alice"]))
    # (b) A 的会话不得被复活为 active
    rows = await repo._db.query(
        "SELECT status FROM player_sessions WHERE world_id=?", (world_a.world_id,))
    assert rows[0]["status"] == "uncertain"
    # (a) A 不得从待收敛表丢失
    assert [w.world_id for w in svc._prev_worlds["s1"]] == [world_a.world_id]
    # 收敛路径仍在: 超时后新世界 tick 关闭 A 的会话
    clock.set(1000 + 901)
    await svc.ingest_players(world_b, _players_resp([]))
    rows = await repo._db.query(
        "SELECT status, leave_reason, left_at FROM player_sessions WHERE world_id=?",
        (world_a.world_id,))
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    assert rows[0]["left_at"] == 1901
    assert svc._prev_worlds == {}
    await db.close()


async def test_world_regression_a_b_a_resumes_normal_path(tmp_path):
    """合法 A→B→A 回归: A 重新成为当前世界后, 会话由正常路径接管并复用。"""
    db, clock, repo, svc = await _mk_snapshot(tmp_path)
    world_a = await svc.ingest_info(_server(), _info_resp("G-A"))
    await svc.ingest_players(world_a, _players_resp(["Alice"]))
    first = await repo.list_open_sessions(world_a.world_id)
    clock.set(1030)
    await svc.ingest_info(_server(), _info_resp("G-B"))
    clock.set(1060)
    world_a2 = await svc.ingest_info(_server(), _info_resp("G-A"))
    assert world_a2.world_id == world_a.world_id
    clock.set(1090)
    await svc.ingest_players(world_a2, _players_resp(["Alice"]))
    resumed = await repo.list_open_sessions(world_a.world_id)
    assert len(resumed) == 1
    assert resumed[0].id == first[0].id           # 复用同会话, 不新建
    assert resumed[0].status == SessionStatus.ACTIVE
    assert resumed[0].joined_at == 1000
    # 回归世界从待收敛表移除 (B 无未决会话也被移除)
    assert svc._prev_worlds == {}
    await db.close()


async def test_restart_rebuilds_prev_worlds_from_db(tmp_path):
    """重启悬置: 换世界后、收敛完成前插件重启, _prev_worlds 内存态丢失。
    新实例的首个 info 须从 DB 重建待收敛集合, 保证旧世界会话仍能收敛。"""
    db, clock, repo, svc = await _mk_snapshot(tmp_path)
    world_a = await svc.ingest_info(_server(), _info_resp("G-A"))
    await svc.ingest_players(world_a, _players_resp(["Alice"]))
    clock.set(1030)
    await svc.ingest_info(_server(), _info_resp("G-B"))
    # 模拟重启: 同一 DB 上新建第二个 service 实例 (内存待收敛集合为空)
    players2 = PlayerService(repo, b"0" * 32, _cfg(), clock)
    players2.events = FakeEvents()
    svc2 = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=None, salt=b"0" * 32, cfg=_cfg(), clock=clock,
        players=players2, guilds=None, bases=None, events=None,
    )
    clock.set(1100)
    world_b2 = await svc2.ingest_info(_server(), _info_resp("G-B"))
    assert [w.world_id for w in svc2._prev_worlds["s1"]] == [world_a.world_id]
    # 幂等: 后续 info tick 不得重复记入同一世界
    clock.set(1200)
    await svc2.ingest_info(_server(), _info_resp("G-B"))
    assert [w.world_id for w in svc2._prev_worlds["s1"]] == [world_a.world_id]
    # 收敛: 超时后新世界 tick 关闭旧世界会话
    clock.set(1000 + 901)
    await svc2.ingest_players(world_b2, _players_resp([]))
    rows = await repo._db.query(
        "SELECT status, leave_reason, left_at FROM player_sessions WHERE world_id=?",
        (world_a.world_id,))
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    assert rows[0]["left_at"] == 1901
    assert svc2._prev_worlds == {}
    await db.close()


async def test_world_switch_sweeps_old_world_on_next_tick(tmp_path):
    """§10.1 路径二: worldguid 切换后, 新世界的 players tick 顺带收敛旧世界 uncertain 会话。"""
    db, clock, repo, svc = await _mk_snapshot(tmp_path)
    world_a = await svc.ingest_info(_server(), _info_resp("G-A"))
    await svc.ingest_players(world_a, _players_resp(["Alice"]))
    # 换世界: 旧世界会话置 uncertain, 此后旧世界再无 players 快照
    clock.set(1030)
    world_b = await svc.ingest_info(_server(), _info_resp("G-B"))
    assert world_b.world_id != world_a.world_id

    # 未超时: 新世界 tick 不收敛旧世界, prev 记录保留
    clock.set(1500)
    await svc.ingest_players(world_b, _players_resp([]))
    rows = await repo._db.query(
        "SELECT status FROM player_sessions WHERE world_id=?", (world_a.world_id,))
    assert rows[0]["status"] == "uncertain"
    assert "s1" in svc._prev_worlds

    # 超时后: 下一个新世界 tick 收敛旧世界为 closed/world_offline
    clock.set(1000 + 901)
    await svc.ingest_players(world_b, _players_resp([]))
    rows = await repo._db.query(
        "SELECT status, leave_reason, left_at FROM player_sessions WHERE world_id=?",
        (world_a.world_id,))
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    assert rows[0]["left_at"] == 1901
    # 旧世界已无未决会话 → 从 prev 表移除, 避免永久多余查询
    assert svc._prev_worlds == {}
    await db.close()
