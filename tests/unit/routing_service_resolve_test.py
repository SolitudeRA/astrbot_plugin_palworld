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


def _cfg(servers, access=AccessMode.RESTRICTED, default="") -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=access, default_server=default),
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


async def test_override_unknown_server_errors(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override="ghost", is_group=True)
    assert res.server is None
    assert "不存在或未就绪" in res.error


async def test_override_requires_allowed_in_restricted(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override="alpha", is_group=True)
    assert res.server is None
    assert "未被授权" in res.error


async def test_override_after_authorization_succeeds(repo):
    await repo.set_active("umo1", "alpha")
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override="alpha", is_group=True)
    assert res.error is None
    assert res.server.server_id == "alpha"


async def test_active_binding_resolves(repo):
    await repo.set_active("umo1", "beta")
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta")]))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server.server_id == "beta"


async def test_dangling_active_falls_through_to_prompt(repo):
    # active points to a server that is no longer configured/ready
    await repo.set_active("umo1", "beta")
    svc = RoutingService(repo, _cfg([_server("alpha")]))  # beta removed
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None
    assert res.error is not None


async def test_disabled_server_not_used_as_default(repo):
    svc = RoutingService(repo, _cfg([_server("alpha", ready=False)], default="alpha"))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None


async def test_single_ready_server_open_mode(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")], access=AccessMode.OPEN))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server.server_id == "alpha"


async def test_default_server_open_mode(repo):
    svc = RoutingService(
        repo, _cfg([_server("alpha"), _server("beta")], access=AccessMode.OPEN, default="beta")
    )
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server.server_id == "beta"


async def test_private_chat_restricted_rejected(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override=None, is_group=False)
    assert res.server is None
    assert "私聊" in res.error


async def test_no_server_configured(repo):
    svc = RoutingService(repo, _cfg([], access=AccessMode.OPEN))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None
    assert "尚未配置" in res.error
