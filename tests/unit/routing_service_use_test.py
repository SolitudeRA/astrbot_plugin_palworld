from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.routing_service import (
    RoutingService,
    UnbindResult,
    UseResult,
)
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


def _server(name: str, ready: bool = True) -> ServerConfig:
    return ServerConfig(
        server_id=name, name=name, enabled=True, base_url="http://127.0.0.1:8212",
        username="admin", password="pw" if ready else "", timeout=10,
        verify_tls=True, timezone="",
    )


def _cfg(servers) -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    r = Repository(db, FakeClock(1000))
    await r.sync_servers([_server("alpha"), _server("beta")])
    yield r
    await db.close()


# ---- use → 结构化 UseResult{ok, server_id, replaced_active}（spec §5#8）----

async def test_use_unknown_server_returns_not_ok(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.use("umo1", "ghost")
    assert isinstance(res, UseResult)
    assert res.ok is False
    assert res.server_id is None
    assert res.replaced_active is None
    assert await repo.get_binding_active("umo1") is None


async def test_use_authorizes_and_activates(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.use("umo1", "alpha")
    assert res.ok is True
    assert res.server_id == "alpha"
    assert res.replaced_active is None  # 首次授权无旧活动
    assert await repo.get_binding_active("umo1") == "alpha"
    assert await repo.get_allowed("umo1") == {"alpha"}


async def test_use_switches_active_reports_replaced(repo):
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta")]))
    await svc.use("umo1", "alpha")
    res = await svc.use("umo1", "beta")
    assert res.ok is True
    assert res.server_id == "beta"
    assert res.replaced_active == "alpha"  # 旧活动被替换 → 填旧值
    assert await repo.get_binding_active("umo1") == "beta"


async def test_use_same_active_no_replaced(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    await svc.use("umo1", "alpha")
    res = await svc.use("umo1", "alpha")  # 重复授权同一台
    assert res.ok is True
    assert res.replaced_active is None  # 旧==新，不填 replaced


# ---- unbind → 结构化 UnbindResult{removed, was_active}（spec §5#8）----

async def test_unbind_removes_active_reports_was_active(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    await svc.use("umo1", "alpha")  # alpha 成活动
    res = await svc.unbind("umo1", "alpha")
    assert isinstance(res, UnbindResult)
    assert res.removed is True
    assert res.was_active is True
    assert await repo.get_binding_active("umo1") is None
    assert await repo.get_allowed("umo1") == set()


async def test_unbind_no_record_is_not_removed(repo):
    # 先查存在性：无授权记录 → removed=False（修幂等假成功）
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.unbind("umo1", "alpha")
    assert res.removed is False
    assert res.was_active is False


async def test_unbind_non_active_record(repo):
    # alpha 授权且活动，另授权 beta 后 alpha 变非活动；撤 alpha → removed 但非活动
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta")]))
    await svc.use("umo1", "alpha")
    await svc.use("umo1", "beta")  # beta 成活动，alpha 退为非活动
    res = await svc.unbind("umo1", "alpha")
    assert res.removed is True
    assert res.was_active is False


async def test_ready_servers_filters_unready(repo):
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta", ready=False)]))
    ids = [s.server_id for s in svc.ready_servers()]
    assert ids == ["alpha"]
