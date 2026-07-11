from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import BindingConfig, ServerConfig
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _server(name: str) -> ServerConfig:
    return ServerConfig(
        server_id=name, name=name, enabled=True, base_url="http://127.0.0.1:8212",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1000)
    r = Repository(db, clock)
    await r.sync_servers([_server("alpha"), _server("beta")])
    yield r
    await db.close()


async def test_set_active_makes_row_allowed_and_active(repo):
    await repo.set_active("umo1", "alpha")
    assert await repo.get_binding_active("umo1") == "alpha"
    assert await repo.get_allowed("umo1") == {"alpha"}


async def test_set_active_is_unique_per_umo(repo):
    await repo.set_active("umo1", "alpha")
    await repo.set_active("umo1", "beta")
    assert await repo.get_binding_active("umo1") == "beta"
    # alpha stays allowed but no longer active
    assert await repo.get_allowed("umo1") == {"alpha", "beta"}
    rows = await repo.list_group_servers("umo1")
    assert rows["alpha"] == (True, False)
    assert rows["beta"] == (True, True)


async def test_revoke_clears_allowed_and_active(repo):
    await repo.set_active("umo1", "alpha")
    await repo.revoke("umo1", "alpha")
    assert await repo.get_binding_active("umo1") is None
    assert await repo.get_allowed("umo1") == set()


async def test_seed_binding_does_not_override_runtime(repo):
    await repo.set_active("umo1", "beta")  # runtime choice
    await repo.seed_bindings([BindingConfig(umo="umo1", server="alpha", active=True)])
    # seed is INSERT OR IGNORE: existing rows untouched, beta still active
    assert await repo.get_binding_active("umo1") == "beta"


async def test_get_allowed_empty_for_unknown_umo(repo):
    assert await repo.get_allowed("nobody") == set()
    assert await repo.get_binding_active("nobody") is None
