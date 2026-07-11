import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import LeaveReason, SessionStatus
from palchronicle.domain.models import PlayerSession
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


def _sess(status, **kw):
    base = dict(
        id=None, world_id="w1", player_key="pk1", joined_at=1000,
        last_confirmed_at=1000, left_at=None, observed_seconds=0,
        status=status, leave_reason=None,
    )
    base.update(kw)
    return PlayerSession(**base)


async def test_insert_returns_id_and_roundtrips(repo):
    sid = await repo.insert_session(_sess(SessionStatus.ACTIVE))
    assert isinstance(sid, int) and sid > 0
    got = await repo.get_open_session("w1", "pk1")
    assert got is not None
    assert got.id == sid
    assert got.status == SessionStatus.ACTIVE


async def test_get_open_prefers_active_over_uncertain(repo):
    await repo.insert_session(_sess(SessionStatus.UNCERTAIN, joined_at=900))
    active_id = await repo.insert_session(_sess(SessionStatus.ACTIVE, joined_at=1000))
    got = await repo.get_open_session("w1", "pk1")
    assert got.id == active_id
    assert got.status == SessionStatus.ACTIVE


async def test_get_open_falls_back_to_uncertain(repo):
    uid = await repo.insert_session(_sess(SessionStatus.UNCERTAIN))
    got = await repo.get_open_session("w1", "pk1")
    assert got.id == uid
    assert got.status == SessionStatus.UNCERTAIN


async def test_get_open_ignores_closed(repo):
    await repo.insert_session(_sess(SessionStatus.CLOSED, left_at=1500,
                                    leave_reason=LeaveReason.OBSERVED_TIMEOUT))
    assert await repo.get_open_session("w1", "pk1") is None


async def test_update_session_mutates(repo):
    sid = await repo.insert_session(_sess(SessionStatus.ACTIVE))
    got = await repo.get_open_session("w1", "pk1")
    got.observed_seconds = 120
    got.last_confirmed_at = 1120
    got.status = SessionStatus.CLOSED
    got.left_at = 1200
    got.leave_reason = LeaveReason.WORLD_OFFLINE
    await repo.update_session(got)
    assert await repo.get_open_session("w1", "pk1") is None
    rows = await repo._db.query(
        "SELECT observed_seconds, status, leave_reason FROM player_sessions WHERE id = ?",
        (sid,),
    )
    assert rows[0]["observed_seconds"] == 120
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"


async def test_list_open_sessions(repo):
    await repo.insert_session(_sess(SessionStatus.ACTIVE, player_key="a"))
    await repo.insert_session(_sess(SessionStatus.UNCERTAIN, player_key="b"))
    await repo.insert_session(_sess(SessionStatus.CLOSED, player_key="c", left_at=1))
    keys = {s.player_key for s in await repo.list_open_sessions("w1")}
    assert keys == {"a", "b"}
