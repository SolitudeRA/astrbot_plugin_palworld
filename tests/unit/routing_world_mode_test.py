import logging
from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.routing_service import RoutingService
from palworld_terminal.config import (
    AllowedGroupEntry,
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


def _cfg(servers, access=AccessMode.RESTRICTED, default="", world_mode="multi",
         single_allowed_groups=None) -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(
            access_mode=access, default_server=default, world_mode=world_mode,
            single_allowed_groups=single_allowed_groups or []),
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


# ---- multi mode: current behaviour must be unchanged ----

async def test_multi_private_restricted_still_rejected(repo):
    """multi 现状回归：restricted 私聊仍被拒（single 分支不得误伤 multi）。"""
    svc = RoutingService(repo, _cfg([_server("alpha")], world_mode="multi"))
    res = await svc.resolve("umo1", override=None, is_group=False)
    assert res.server is None
    assert "私聊" in res.error


# ---- single mode: always resolves the unique ready server ----

async def test_single_private_chat_restricted_not_in_allowlist_denied(repo):
    """single+restricted：私聊 umo 不在授权名单 → 拒（error 非空）。"""
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.RESTRICTED, world_mode="single"))
    res = await svc.resolve("umo1", override=None, is_group=False)
    assert res.server is None
    assert res.error


async def test_single_ignores_override(repo):
    """single：忽略 @override（未就绪/未知服务器名也不报错，恒解析唯一）。"""
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.OPEN, world_mode="single"))
    res = await svc.resolve("umo1", override="ghost", is_group=True)
    assert res.error is None
    assert res.server.server_id == "alpha"


async def test_single_ignores_group_binding(repo):
    """single：忽略群绑定（哪怕 active 指向别处/已失效），恒解析唯一就绪服务器。"""
    await repo.set_active("umo1", "beta")  # 绑定 beta，但配置里只有 alpha 就绪
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.OPEN, world_mode="single"))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.error is None
    assert res.server.server_id == "alpha"


async def test_single_no_server_errors(repo):
    """single + 0 台就绪 → error「未配置服务器」。"""
    svc = RoutingService(repo, _cfg([], world_mode="single"))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None
    assert "尚未配置" in res.error


async def test_single_multiple_ready_uses_first_and_warns(repo, caplog):
    """single + >1 台 → 首台 + 记一次告警。"""
    svc = RoutingService(
        repo, _cfg([_server("alpha"), _server("beta")], access=AccessMode.OPEN,
                   world_mode="single"))
    with caplog.at_level(logging.WARNING, logger="palworld_terminal.routing"):
        res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.error is None
    assert res.server.server_id == "alpha"
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


# ---- single + restricted：授权名单门控（读路径，for_write 默认 False）----

async def test_single_restricted_umo_in_allowlist_resolves(repo):
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.RESTRICTED, world_mode="single",
                   single_allowed_groups=[AllowedGroupEntry("g1", "")]))
    res = await svc.resolve("g1", None, True)
    assert res.server is not None and res.error is None


async def test_single_restricted_umo_not_in_allowlist_denied(repo):
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.RESTRICTED, world_mode="single",
                   single_allowed_groups=[AllowedGroupEntry("g1", "")]))
    res = await svc.resolve("g2", None, True)
    assert res.server is None and res.error  # single_not_authorized


async def test_single_restricted_empty_allowlist_denies_all(repo):
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.RESTRICTED, world_mode="single",
                   single_allowed_groups=[]))
    res = await svc.resolve("g1", None, True)
    assert res.server is None  # fail-closed


async def test_single_open_ignores_allowlist(repo):
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.OPEN, world_mode="single",
                   single_allowed_groups=[]))
    res = await svc.resolve("g1", None, True)
    assert res.server is not None


async def test_single_restricted_for_write_bypasses_allowlist(repo):
    """single+restricted 安全核心:umo 不在读名单时,写命令 for_write=True 绕过读
    名单、解析到首台就绪服务器(admin 硬门在 main 层独立把守,不在此层);同一 umo
    读路径 for_write=False 仍被拒(single_not_authorized)。"""
    svc = RoutingService(
        repo, _cfg([_server("alpha")], access=AccessMode.RESTRICTED, world_mode="single",
                   single_allowed_groups=[AllowedGroupEntry("other", "")]))
    w = await svc.resolve("g1", None, True, for_write=True)
    assert w.server is not None and w.error is None
    assert w.server.server_id == "alpha"  # ready[0]
    r = await svc.resolve("g1", None, True, for_write=False)
    assert r.server is None and r.error  # single_not_authorized
