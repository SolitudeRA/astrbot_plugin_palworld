from types import SimpleNamespace

import pytest

from palworld_terminal.application.admin_service import AdminService


class _FakeRepo:
    def __init__(self):
        self.audits = []

    async def get_current_world(self, server_id):
        return SimpleNamespace(world_id="w1")

    async def insert_audit(self, **kw):
        self.audits.append(kw)


class _FakeRouting:
    async def resolve(self, umo, override, is_group):
        return SimpleNamespace(
            server=SimpleNamespace(server_id="s1", name="Alpha"), error=None
        )


def _svc(post_result):
    async def fetch(server_id, endpoint):
        return SimpleNamespace(ok=True, data=[])

    async def post(server_id, path, json_body):
        return post_result

    return AdminService(
        routing=_FakeRouting(),
        fetch=fetch,
        post=post,
        repo=_FakeRepo(),
        salt=b"salt",
        clock=SimpleNamespace(now=lambda: 1000),
    )


@pytest.mark.asyncio
async def test_announce_success_audits():
    ok = SimpleNamespace(ok=True, status=200, error=None)
    svc = _svc(ok)
    res = await svc.announce("p:1", "umo", True, "hello")  # admin_id 首参
    assert res.ok
    assert svc._repo.audits[0]["action"] == "announce"
    assert svc._repo.audits[0]["admin_id"] == "p:1"
    assert svc._repo.audits[0]["success"] == 1


@pytest.mark.asyncio
async def test_stop_disconnect_treated_initiated():
    err = SimpleNamespace(ok=False, status=None, error="network error")
    svc = _svc(err)
    res = await svc.stop("p:1", "umo", True)
    assert res.ok  # 断连=已发起
    assert svc._repo.audits[0]["success"] == 1


@pytest.mark.asyncio
async def test_save_http_error_audits_failure():
    err = SimpleNamespace(ok=False, status=500, error="http_status_500")
    svc = _svc(err)
    res = await svc.save("p:1", "umo", True)
    assert not res.ok
    assert svc._repo.audits[0]["success"] == 0


def _svc_players(players):
    async def fetch(server_id, endpoint):
        return SimpleNamespace(ok=True, data={"players": players})

    async def post(server_id, path, json_body):
        return SimpleNamespace(ok=True, status=200, error=None)

    return AdminService(
        routing=_FakeRouting(),
        fetch=fetch,
        post=post,
        repo=_FakeRepo(),
        salt=b"s",
        clock=SimpleNamespace(now=lambda: 1),
    )


@pytest.mark.asyncio
async def test_resolve_target_direct_userid():
    svc = _svc_players([])
    t = await svc.resolve_target("s1", "steam_76561198000000000")
    assert t.kind == "userid" and t.userid == "steam_76561198000000000"


@pytest.mark.asyncio
async def test_resolve_target_by_name_unique():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    t = await svc.resolve_target("s1", "Alice")
    assert t.kind == "unique" and t.userid == "steam_1"


@pytest.mark.asyncio
async def test_resolve_target_multi():
    svc = _svc_players(
        [{"name": "Bob", "userId": "steam_1"}, {"name": "Bob", "userId": "steam_2"}]
    )
    t = await svc.resolve_target("s1", "Bob")
    assert t.kind == "multi" and len(t.candidates) == 2


@pytest.mark.asyncio
async def test_resolve_target_none():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    t = await svc.resolve_target("s1", "Zed")
    assert t.kind == "none"


@pytest.mark.asyncio
async def test_kick_by_name_audits_hashed_target():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    res = await svc.kick("p:1", "umo", True, "Alice", "afk")
    assert res.ok
    a = svc._repo.audits[0]
    assert a["action"] == "kick" and a["target_name"] == "Alice"
    assert a["target_hash"] and a["target_hash"] != "steam_1"  # 只 hash 不明文


@pytest.mark.asyncio
async def test_kick_multi_does_not_post_or_audit():
    svc = _svc_players(
        [{"name": "Bob", "userId": "steam_1"}, {"name": "Bob", "userId": "steam_2"}]
    )
    res = await svc.kick("p:1", "umo", True, "Bob", "afk")
    assert not res.ok and res.message_key == "target_multi"
    assert svc._repo.audits == []  # 未发起：不 post、不审计


@pytest.mark.asyncio
async def test_kick_none_does_not_post_or_audit():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    res = await svc.kick("p:1", "umo", True, "Zed", "afk")
    assert not res.ok and res.message_key == "target_none"
    assert svc._repo.audits == []


@pytest.mark.asyncio
async def test_unban_uses_userid_directly_and_hashes():
    svc = _svc_players([])
    res = await svc.unban("p:1", "umo", True, "steam_9")
    assert res.ok
    a = svc._repo.audits[0]
    assert a["action"] == "unban" and a["target_name"] is None
    assert a["target_hash"] and a["target_hash"] != "steam_9"
