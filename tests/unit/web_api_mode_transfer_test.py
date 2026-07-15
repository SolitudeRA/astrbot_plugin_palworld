import asyncio

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.routing_service import RoutingService
from palworld_terminal.config import parse_config
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.web_api import handle_mode_transfer


def _srv_row(name, enabled=True, password="pw", base_url="http://h:8212"):
    return {"name": name, "enabled": enabled, "base_url": base_url,
            "username": "admin", "password": password, "password_env": "",
            "timeout": 10, "verify_tls": True, "timezone": ""}


def _base_raw(world_mode, servers, single_allowed=None, group_bindings=None):
    return {
        "servers": servers, "custom_headers": [],
        "group_bindings": group_bindings or [],
        "single_allowed_groups": single_allowed or [],
        "routing": {"access_mode": "restricted", "default_server": "",
                    "world_mode": world_mode, "setup_confirmed": True},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {},
    }


class _Container:
    def __init__(self, raw, repo):
        self.config = parse_config(raw, {})
        self.repo = repo
        self.routing = RoutingService(repo, self.config)


class _Harness:
    """真实 parse_config + 真实 Repository/DB；apply_and_restart 镜像
    main._apply_and_restart 的整键替换 + Container.start 的 DB 副作用
    （sync_servers → seed_bindings → cleanup_orphan_bindings）。"""

    def __init__(self, raw, repo):
        self.raw = raw
        self.repo = repo
        self.container = _Container(raw, repo)
        self.fail_reload = False
        self.reload_calls = 0

    def get_raw(self):
        return self.raw

    def get_container(self):
        return self.container

    def busy_msg(self):
        return None

    def current_username(self):
        return "dash_admin"

    async def apply_and_restart(self, candidate):
        self.reload_calls += 1
        if self.fail_reload:
            return {"ok": False, "error": "restart_failed_rolled_back", "detail": {}}
        for k, v in candidate.items():        # 整键替换（镜像 main.py:263-264）
            self.raw[k] = v
        self.container = _Container(self.raw, self.repo)
        cfg = self.container.config
        await self.repo.sync_servers(cfg.servers)
        await self.repo.seed_bindings(cfg.group_bindings)
        ready_ids = {s.server_id for s in cfg.servers if s.ready}
        await self.repo.cleanup_orphan_bindings(ready_ids)
        return {"ok": True, "warnings": {"skipped_servers": [], "skipped_headers": []}}


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def _mk(raw, repo):
    """初始化 harness：把首份 config 的 servers/seed 同步进 DB（模拟首次 start）。"""
    h = _Harness(raw, repo)
    cfg = h.container.config
    await repo.sync_servers(cfg.servers)
    await repo.seed_bindings(cfg.group_bindings)
    return h


async def _call(h, body):
    return await handle_mode_transfer(
        body, get_raw=h.get_raw, get_container=h.get_container,
        busy_msg=h.busy_msg, lock=asyncio.Lock(), now=1234,
        apply_and_restart=h.apply_and_restart, current_username=h.current_username)


# ---- 早退 ----
async def test_no_change_same_mode_not_audited(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")]), repo)
    code, p = await _call(h, {"target_mode": "single", "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "no_change"
    assert h.reload_calls == 0
    assert await repo.list_audit(10) == []      # 三类早退不审计


async def test_transfer_in_progress_when_lock_held(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")]), repo)
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_mode_transfer(
            {"target_mode": "multi", "migrate_umos": []},
            get_raw=h.get_raw, get_container=h.get_container, busy_msg=h.busy_msg,
            lock=lock, now=1, apply_and_restart=h.apply_and_restart,
            current_username=h.current_username)
        assert p["error"] == "transfer_in_progress"
    finally:
        lock.release()


# ---- single → multi ----
async def test_single_to_multi_prebinds_and_clears_source(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": "n"}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is True
    assert p["config"]["routing"]["world_mode"] == "multi"
    # move 清源：顶层 single_allowed_groups 清空
    assert p["config"]["single_allowed_groups"] == []
    # 预绑存活（reload 前绑、目标切 multi 后仍就绪）
    assert await repo.get_allowed("u1") == {"a"}
    # 持久化 round-trip：parse_config 真读到 world_mode=multi、名单已空
    cfg = parse_config(h.raw, {})
    assert cfg.routing.world_mode == "multi"
    assert cfg.routing.single_allowed_groups == []


async def test_single_to_multi_binds_effective_ready_server_not_index0(repo):
    # B2：servers[0] 非就绪、servers[1] 就绪 → 预绑到就绪台而非 servers[0]。
    h = await _mk(_base_raw("single",
                            [_srv_row("ghost", password=""), _srv_row("live")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is True
    assert await repo.get_allowed("u1") == {"live"}   # 绑到就绪台


async def test_single_to_multi_invalid_migrate_umos_rejected(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u_evil"]})
    assert p["ok"] is False and p["error"] == "invalid_migrate_umos"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "single"   # 零变更
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0     # 校验拒绝写审计


async def test_single_to_multi_no_ready_target_rejected(repo):
    h = await _mk(_base_raw("single", [_srv_row("a", password="")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is False and p["error"] == "no_ready_target"


async def test_single_to_multi_prebind_failure_zero_change(repo):
    # M-a：预绑抛异常 → 拒 migrate_bind_failed、config 完全未变、best-effort 撤销、审计 success=0。
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    orig = repo.bind_umos_to_server

    async def boom(umos, sid):
        raise RuntimeError("db down")

    repo.bind_umos_to_server = boom
    try:
        code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    finally:
        repo.bind_umos_to_server = orig
    assert p["ok"] is False and p["error"] == "migrate_bind_failed"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "single"   # world_mode 仍 single
    assert parse_config(h.raw, {}).routing.single_allowed_groups[0].umo == "u1"  # 名单完整
    assert await repo.get_allowed("u1") == set()                    # 无残留


# ---- multi → single ----
async def test_multi_to_single_migrates_and_promotes_survivor(repo):
    h = await _mk(_base_raw("multi", [_srv_row("a"), _srv_row("b")]), repo)
    await repo.set_active("u1", "a")   # DB 授权源
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "b",
                              "migrate_umos": ["u1"]})
    assert p["ok"] is True
    assert p["config"]["routing"]["world_mode"] == "single"
    # 保留台归位 servers[0]
    assert p["config"]["servers"][0]["name"] == "b"
    # migrate_umos 并入顶层 single_allowed_groups（非 routing 下）
    sag = p["config"]["single_allowed_groups"]
    assert {e["umo"] for e in sag} == {"u1"}
    assert "single_allowed_groups" not in p["config"]["routing"]
    # M-d：group_bindings 种子清空
    assert p["config"]["group_bindings"] == []
    # post-reload clear_all_group_servers 生效
    assert await repo.list_allowed_bindings() == []
    # 持久化 round-trip
    cfg = parse_config(h.raw, {})
    assert cfg.routing.world_mode == "single"
    assert {e.umo for e in cfg.routing.single_allowed_groups} == {"u1"}


async def test_multi_to_single_invalid_surviving_zero_change(repo):
    # B1：surviving 不在就绪集 → 拒 invalid_surviving、零状态变更（config+DB 未动）。
    h = await _mk(_base_raw("multi", [_srv_row("a")]), repo)
    await repo.set_active("u1", "a")
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "nope",
                              "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "invalid_surviving"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "multi"
    assert await repo.get_allowed("u1") == {"a"}   # DB 未动
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_multi_to_single_no_ready_server_rejected(repo):
    h = await _mk(_base_raw("multi", [_srv_row("a", password="")]), repo)
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                              "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "no_ready_server"


async def test_multi_to_single_over_limit_rejected(repo):
    # M-b：并入后 single_allowed_groups > 200 → 拒 too_many_groups、零状态变更、绝不截断。
    existing = [{"umo": f"g{i}", "note": ""} for i in range(199)]
    h = await _mk(_base_raw("multi", [_srv_row("a")], single_allowed=existing), repo)
    # DB 有两个可迁 umo（并入后 199+2=201 > 200）
    await repo.set_active("m1", "a")
    await repo.set_active("m2", "a")
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                              "migrate_umos": ["m1", "m2"]})
    assert p["ok"] is False and p["error"] == "too_many_groups"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "multi"   # 零变更
    assert await repo.get_allowed("m1") == {"a"}                   # DB 未动
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_multi_to_single_move_no_revive_on_switch_back(repo):
    # M2 + M-d：multi→single move（清 group_bindings 种子）后切回 multi，旧授权不复活。
    # 专测「config 原有 group_bindings 种子行」case：清种子后 seed_bindings 重播不复活。
    h = await _mk(_base_raw("multi", [_srv_row("a"), _srv_row("b")],
                            group_bindings=[{"umo": "u_old", "server": "a", "active": True}]),
                  repo)
    await repo.set_active("u_old", "a")
    # 切 single，不迁 u_old（migrate_umos 空）
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                              "migrate_umos": []})
    assert p["ok"] is True
    assert await repo.list_allowed_bindings() == []   # 清空
    # 切回 multi
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": []})
    assert p["ok"] is True
    # seed_bindings 重播不复活 u_old（种子已随清空）
    assert await repo.get_allowed("u_old") == set()


# ---- reload 失败 / 清源失败 / 审计异常 ----
async def test_reload_failure_aborts_post_reload_writes(repo):
    # M5：apply_and_restart 返回 ok:False → post-reload DB 写未跑 + config 回滚 + 审计 success=0。
    h = await _mk(_base_raw("multi", [_srv_row("a"), _srv_row("b")]), repo)
    await repo.set_active("u1", "a")
    h.fail_reload = True
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "b",
                              "migrate_umos": ["u1"]})
    assert p["ok"] is False and p["error"] == "restart_failed_rolled_back"
    # multi→single 方向 DB 完全未动（clear 未跑）
    assert await repo.get_allowed("u1") == {"a"}
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_clear_source_failure_still_switches_and_warns(repo):
    # M-f：clear_all_group_servers 抛错 → 模式仍切、审计 success=0 + cleared_group_servers=False、
    # 回执 ok:True + warnings、不 500。
    h = await _mk(_base_raw("multi", [_srv_row("a")]), repo)
    await repo.set_active("u1", "a")
    orig = repo.clear_all_group_servers

    async def boom():
        raise RuntimeError("locked")

    repo.clear_all_group_servers = boom
    try:
        code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                                  "migrate_umos": ["u1"]})
    finally:
        repo.clear_all_group_servers = orig
    assert code == 200 and p["ok"] is True
    assert p["warnings"].get("cleared_group_servers") is False
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_audit_write_failure_still_returns_200(repo):
    # M-e：insert_audit 抛错 → 端点仍 200 + 正确 ok/config、不吞已算好的成功 payload。
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    orig = repo.insert_audit

    async def boom(**kw):
        raise RuntimeError("audit locked")

    repo.insert_audit = boom
    try:
        code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    finally:
        repo.insert_audit = orig
    assert code == 200 and p["ok"] is True
    assert p["config"]["routing"]["world_mode"] == "multi"


async def test_single_to_multi_reload_failure_revokes_prebind(repo):
    # M5（single→multi 方向）：预绑先于 reload，reload 失败即中止 → best-effort 撤销预绑、
    # config 回滚（仍 single）、审计 success=0。补齐唯一未测的编排安全分支。
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    h.fail_reload = True
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is False and p["error"] == "restart_failed_rolled_back"
    # 预绑已撤销：DB 无残留绑定
    assert await repo.get_allowed("u1") == set()
    # 零 config 变更：world_mode 仍 single
    assert parse_config(h.raw, {}).routing.world_mode == "single"
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_invalid_target_not_audited(repo):
    # invalid_target 是非审计早退：不写审计、不触发 reload。
    h = await _mk(_base_raw("single", [_srv_row("a")]), repo)
    code, p = await _call(h, {"target_mode": "bogus", "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "invalid_target"
    assert h.reload_calls == 0
    assert await repo.list_audit(10) == []


async def test_candidate_preserves_untouched_fields(repo):
    # M8：转移不静默重置 access_mode/default_server/setup_confirmed；保留台密码存活。
    raw = _base_raw("multi", [_srv_row("a"), _srv_row("b")])
    raw["routing"]["access_mode"] = "open"
    raw["routing"]["default_server"] = "a"
    h = await _mk(raw, repo)
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "b",
                              "migrate_umos": []})
    assert p["ok"] is True
    cfg = parse_config(h.raw, {})
    assert cfg.routing.access_mode.value == "open"
    assert cfg.routing.default_server == "a"
    assert cfg.routing.setup_confirmed is True
    survivor = next(s for s in cfg.servers if s.server_id == "b")
    assert survivor.password == "pw" and survivor.ready is True
