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
