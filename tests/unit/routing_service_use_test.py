from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.routing_service import RoutingService
from palchronicle.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


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


async def test_use_unknown_server_returns_error(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    msg = await svc.use("umo1", "ghost")
    assert "不存在或未就绪" in msg
    assert await repo.get_binding_active("umo1") is None


async def test_use_authorizes_and_activates(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    msg = await svc.use("umo1", "alpha")
    assert "alpha" in msg
    assert await repo.get_binding_active("umo1") == "alpha"
    assert await repo.get_allowed("umo1") == {"alpha"}


async def test_use_switches_active_uniquely(repo):
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta")]))
    await svc.use("umo1", "alpha")
    await svc.use("umo1", "beta")
    assert await repo.get_binding_active("umo1") == "beta"


async def test_unbind_revokes(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    await svc.use("umo1", "alpha")
    msg = await svc.unbind("umo1", "alpha")
    assert "alpha" in msg
    assert await repo.get_binding_active("umo1") is None
    assert await repo.get_allowed("umo1") == set()


async def test_ready_servers_filters_unready(repo):
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta", ready=False)]))
    ids = [s.server_id for s in svc.ready_servers()]
    assert ids == ["alpha"]
