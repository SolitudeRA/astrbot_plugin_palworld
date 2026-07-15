import asyncio

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.web_api import handle_orphans_list, handle_orphans_purge
from tests.unit.repository_mode_transfer_test import _seed_world_data


class _Srv:
    def __init__(self, name):
        self.name = name
        self.server_id = name


class _Cfg:
    def __init__(self, servers):
        self.servers = servers


class _Container:
    def __init__(self, servers, repo):
        self.config = _Cfg(servers)
        self.repo = repo


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "o.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_orphans_list_reports_db_only_servers(repo):
    await _seed_world_data(repo, "live", "live:w")
    await _seed_world_data(repo, "ghost", "ghost:w")
    c = _Container([_Srv("live")], repo)   # config 只有 live
    code, p = await handle_orphans_list(c, False)
    assert p["ok"] is True and p["orphans"] == ["ghost"]


async def test_orphans_list_restarting():
    code, p = await handle_orphans_list(None, True)
    assert p["restarting"] is True and p["orphans"] == []


async def test_orphans_purge_removes_orphan(repo):
    await _seed_world_data(repo, "live", "live:w")
    await _seed_world_data(repo, "ghost", "ghost:w")
    c = _Container([_Srv("live")], repo)
    code, p = await handle_orphans_purge(
        {}, get_container=lambda: c, busy_msg=lambda: None,
        lock=asyncio.Lock(), now=1, current_username=lambda: "admin")
    assert p["ok"] is True and "ghost" in p["purged"]
    assert await repo.list_orphan_server_ids({"live"}) == []
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds WHERE server_id='ghost'")
    assert rows[0][0] == 0


async def test_orphans_purge_rejects_live_server_toctou(repo):
    # Blocker-O：客户端传入在册活台 → 服务端重算孤儿集不含它 → 不删、rejected。
    await _seed_world_data(repo, "live", "live:w")
    await _seed_world_data(repo, "ghost", "ghost:w")
    c = _Container([_Srv("live"), _Srv("ghost")], repo)   # 两台都在 config（无孤儿）
    code, p = await handle_orphans_purge(
        {"server_ids": ["live"]}, get_container=lambda: c, busy_msg=lambda: None,
        lock=asyncio.Lock(), now=1, current_username=lambda: "admin")
    assert p["ok"] is True
    assert p["rejected"] == ["live"] and p["purged"] == {}
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds WHERE server_id='live'")
    assert rows[0][0] == 1   # 活台数据未动


async def test_orphans_purge_empty_short_circuits(repo):
    await _seed_world_data(repo, "live", "live:w")
    c = _Container([_Srv("live")], repo)   # 无孤儿
    code, p = await handle_orphans_purge(
        {}, get_container=lambda: c, busy_msg=lambda: None,
        lock=asyncio.Lock(), now=1, current_username=lambda: "admin")
    assert p["ok"] is True and p["purged"] == {}
    assert await repo.list_audit(10) == []   # 空孤儿集短路、不审计


async def test_orphans_purge_busy_when_lock_held(repo):
    c = _Container([_Srv("live")], repo)
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_orphans_purge(
            {}, get_container=lambda: c, busy_msg=lambda: None,
            lock=lock, now=1, current_username=lambda: "admin")
        assert p["error"] == "purge_in_progress"
    finally:
        lock.release()
