from types import SimpleNamespace

import pytest

from palworld_terminal.application.admin_service import AdminService
from palworld_terminal.application.routing_service import RoutingError


class _FakeRepo:
    def __init__(self):
        self.audits = []

    async def get_current_world(self, server_id):
        return SimpleNamespace(world_id="w1")

    async def insert_audit(self, **kw):
        self.audits.append(kw)


class _FakeRouting:
    async def resolve(self, umo, override, is_group, *, for_write=False):
        return SimpleNamespace(
            server=SimpleNamespace(server_id="s1", name="Alpha"), error=None
        )


class _SingleRestrictedRouting:
    """忠实模拟 single+restricted+空名单：读路径(for_write=False)拒；写路径放行。

    验证写路径确实以 ``for_write=True`` 调 resolve——漏穿线则 for_write 默认 False，
    单模式非授权群被读名单拒 → server=None → admin_resolve_failed。
    """

    def __init__(self):
        self.calls: list[bool] = []

    async def resolve(self, umo, override, is_group, *, for_write=False):
        self.calls.append(for_write)
        if not for_write:
            # 契约诚实：Task 6 后 error 为 RoutingError 枚举（非已渲染串）+ error_params。
            return SimpleNamespace(
                server=None,
                error=RoutingError.SINGLE_NOT_AUTHORIZED,
                error_params={},
            )
        return SimpleNamespace(
            server=SimpleNamespace(server_id="s1", name="Alpha"),
            error=None,
            error_params={},
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
async def test_shutdown_sends_waittime_and_message():
    captured: dict = {}

    async def fetch(server_id, endpoint):
        return SimpleNamespace(ok=True, data=[])

    async def post(server_id, path, json_body):
        captured["path"] = path
        captured["body"] = json_body
        return SimpleNamespace(ok=True, status=200, error=None)

    svc = AdminService(
        routing=_FakeRouting(),
        fetch=fetch,
        post=post,
        repo=_FakeRepo(),
        salt=b"salt",
        clock=SimpleNamespace(now=lambda: 1000),
    )
    res = await svc.shutdown("p:1", "umo", True, 60, "维护")
    assert res.ok
    assert captured["path"] == "shutdown"
    assert captured["body"] == {"waittime": 60, "message": "维护"}
    a = svc._repo.audits[0]
    assert a["action"] == "shutdown" and a["success"] == 1


@pytest.mark.asyncio
async def test_shutdown_disconnect_treated_initiated():
    err = SimpleNamespace(ok=False, status=None, error="network error")
    svc = _svc(err)
    res = await svc.shutdown("p:1", "umo", True, 30, "")
    assert res.ok  # 断连=已发起（保留 initiated_ok_on_disconnect）
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


def _svc_fetch_fail():
    # /players 拉取失败(服务器不可达)：resp.ok=False。
    async def fetch(server_id, endpoint):
        return SimpleNamespace(ok=False, data=None, error="network error")

    async def post(server_id, path, json_body):
        return SimpleNamespace(ok=True, status=200, error=None)

    repo = _FakeRepo()
    svc = AdminService(
        routing=_FakeRouting(),
        fetch=fetch,
        post=post,
        repo=repo,
        salt=b"s",
        clock=SimpleNamespace(now=lambda: 1),
    )
    return svc


@pytest.mark.asyncio
async def test_resolve_target_unreachable_when_fetch_not_ok():
    # fetch 失败须与「无此玩家」区分：kind=unreachable(非 none)。
    svc = _svc_fetch_fail()
    t = await svc.resolve_target("s1", "Alice")
    assert t.kind == "unreachable"


@pytest.mark.asyncio
async def test_kick_unreachable_does_not_post_or_audit():
    # 服务器不可达：回不可达文案，不 post、不审计。
    posted: list = []
    svc = _svc_fetch_fail()

    async def spy_post(server_id, path, json_body):
        posted.append((path, json_body))
        return SimpleNamespace(ok=True, status=200, error=None)

    svc._post = spy_post
    res = await svc.kick("p:1", "umo", True, "Alice", "afk")
    assert not res.ok and res.message_key == "target_unreachable"
    assert svc._repo.audits == []  # 未发起：不审计
    assert posted == []            # 未发起：不 post


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


def _svc_single_restricted(routing, players=None):
    async def fetch(server_id, endpoint):
        return SimpleNamespace(ok=True, data={"players": players or []})

    async def post(server_id, path, json_body):
        return SimpleNamespace(ok=True, status=200, error=None)

    return AdminService(
        routing=routing,
        fetch=fetch,
        post=post,
        repo=_FakeRepo(),
        salt=b"s",
        clock=SimpleNamespace(now=lambda: 1),
    )


@pytest.mark.asyncio
async def test_single_restricted_announce_bypasses_allowlist():
    # _execute 写路径：单模式非授权群管理员 announce 仍解析到服务器执行（不被读名单拒）。
    routing = _SingleRestrictedRouting()
    svc = _svc_single_restricted(routing)
    res = await svc.announce("admin:1", "unlisted_group", True, "hello")
    assert res.message_key != "admin_resolve_failed"
    assert res.ok
    assert routing.calls == [True]  # 以 for_write=True 调 resolve


@pytest.mark.asyncio
async def test_single_restricted_kick_bypasses_allowlist():
    # _target_write 写路径：单模式非授权群 kick 也绕过读名单（覆盖第二处 resolve）。
    routing = _SingleRestrictedRouting()
    svc = _svc_single_restricted(routing, players=[{"name": "Alice", "userId": "steam_1"}])
    res = await svc.kick("admin:1", "unlisted_group", True, "Alice", "afk")
    assert res.message_key != "admin_resolve_failed"
    assert res.ok
    assert routing.calls[0] is True


@pytest.mark.asyncio
async def test_unban_uses_userid_directly_and_hashes():
    svc = _svc_players([])
    res = await svc.unban("p:1", "umo", True, "steam_9")
    assert res.ok
    a = svc._repo.audits[0]
    assert a["action"] == "unban" and a["target_name"] is None
    assert a["target_hash"] and a["target_hash"] != "steam_9"


# ---- spec §5#7：AdminResult.params 补 target_userid（+ 回执供数 content/seconds）----
# 仅用于聊天回执尾4/回显；审计仍只落 hash（上方 hash 断言不变）。


@pytest.mark.asyncio
async def test_announce_params_carry_content_and_empty_userid():
    ok = SimpleNamespace(ok=True, status=200, error=None)
    svc = _svc(ok)
    res = await svc.announce("p:1", "umo", True, "hello")
    assert res.params["content"] == "hello"      # 回显供数
    assert res.params["target_userid"] == ""      # 无目标命令
    assert res.params["target"] == ""


@pytest.mark.asyncio
async def test_shutdown_params_carry_seconds_and_message():
    ok = SimpleNamespace(ok=True, status=200, error=None)
    svc = _svc(ok)
    res = await svc.shutdown("p:1", "umo", True, 60, "维护")
    assert res.params["seconds"] == 60
    assert res.params["content"] == "维护"


@pytest.mark.asyncio
async def test_kick_params_carry_target_userid_for_tail4():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    res = await svc.kick("p:1", "umo", True, "Alice", "afk")
    assert res.ok
    assert res.params["target"] == "Alice"
    assert res.params["target_userid"] == "steam_1"  # 尾4 展示用（非明文入审计）


@pytest.mark.asyncio
async def test_unban_params_carry_userid_no_name():
    svc = _svc_players([])
    res = await svc.unban("p:1", "umo", True, "steam_76561198000001234")
    assert res.params["target"] == ""  # unban 无名字解析
    assert res.params["target_userid"] == "steam_76561198000001234"
