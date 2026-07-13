from contextlib import asynccontextmanager

import aiohttp

from palworld_terminal.adapters.palworld_rest import PalworldRestClient, RestResponse
from palworld_terminal.config import ServerConfig
from palworld_terminal.domain.enums import EndpointName
from palworld_terminal.infrastructure.clock import FakeClock


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://secret-host:8212", username="admin",
        password="topsecret", timeout=10, verify_tls=True, timezone="",
    )


class _FakeResp:
    def __init__(self, status, payload=None, body_bytes=b"{}"):
        self.status = status
        self._payload = payload if payload is not None else {}
        self._body = body_bytes

    async def json(self, content_type=None):
        return self._payload

    async def read(self):
        return self._body


class _FakeSession:
    """替换 aiohttp.ClientSession；按脚本返回响应或抛异常。"""

    def __init__(self, script):
        self._script = script
        self.requested_url = None
        self.requested_auth = None
        self.requested_headers = "UNSET"  # 哨兵：区分「传了 None」与「没传」
        self.closed = False

    @asynccontextmanager
    async def get(self, url, auth=None, timeout=None, ssl=None, headers=None):
        self.requested_url = url
        self.requested_auth = auth
        self.requested_headers = headers
        outcome = self._script
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    async def close(self):
        self.closed = True


async def test_fetch_success_200():
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(_FakeResp(200, {"days": 5}, b'{"days": 5}'))
    resp = await client.fetch(EndpointName.METRICS)
    assert isinstance(resp, RestResponse)
    assert resp.ok is True
    assert resp.status == 200
    assert resp.data == {"days": 5}
    assert resp.payload_bytes == len(b'{"days": 5}')
    assert resp.error is None


async def test_fetch_builds_correct_path_and_basic_auth():
    session = _FakeSession(_FakeResp(200, {}))
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = session
    await client.fetch(EndpointName.GAME_DATA)
    assert session.requested_url == "http://secret-host:8212/v1/api/game-data"
    assert isinstance(session.requested_auth, aiohttp.BasicAuth)


async def test_fetch_timeout_returns_sanitized_error():
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(TimeoutError())
    resp = await client.fetch(EndpointName.PLAYERS)
    assert resp.ok is False
    assert resp.status is None
    assert resp.data is None
    assert "timeout" in resp.error.lower()
    assert "topsecret" not in resp.error
    assert "secret-host" not in resp.error


async def test_fetch_401_marks_not_ok():
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(_FakeResp(401, {}, b""))
    resp = await client.fetch(EndpointName.INFO)
    assert resp.ok is False
    assert resp.status == 401
    assert resp.error is not None
    assert "topsecret" not in resp.error


async def test_fetch_network_error_sanitized():
    err = aiohttp.ClientConnectorError(
        connection_key=None, os_error=OSError("connect to secret-host failed")
    )
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(err)
    resp = await client.fetch(EndpointName.METRICS)
    assert resp.ok is False
    assert resp.error is not None
    assert "secret-host" not in resp.error
    assert "topsecret" not in resp.error


async def test_close_closes_session():
    client = PalworldRestClient(_server(), FakeClock(1000))
    # 让 fetch 走懒创建路径：首次 fetch 时才装配（fake）session。
    fake = _FakeSession(_FakeResp(200, {}))
    client._ensure_session = lambda: (
        setattr(client, "_session", fake) or fake
    )
    await client.fetch(EndpointName.INFO)
    assert client._session is fake

    await client.close()
    assert fake.closed is True
    assert client._session is None

    # 幂等：再次 close 不应抛异常。
    await client.close()
    assert client._session is None


async def test_json_decode_error_is_redacted():
    secret_detail = "Expecting value: line 3 column 7 at secret-host"

    class _BadJsonResp(_FakeResp):
        async def json(self, content_type=None):
            raise ValueError(secret_detail)

    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(_BadJsonResp(200, {}, b'{"broken"'))
    resp = await client.fetch(EndpointName.METRICS)
    assert resp.ok is False
    assert resp.error == "unexpected error"
    # 兜底分支绝不能泄露异常文本（可能含 host/内部细节）。
    assert secret_detail not in resp.error
    assert "secret-host" not in resp.error


async def test_fetch_sends_custom_headers():
    server = ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://secret-host:8212", username="admin",
        password="topsecret", timeout=10, verify_tls=True, timezone="",
        headers={"CF-Access-Client-Id": "abc", "X-Token": "t"},
    )
    session = _FakeSession(_FakeResp(200, {}))
    client = PalworldRestClient(server, FakeClock(1000))
    client._session = session
    await client.fetch(EndpointName.INFO)
    assert session.requested_headers == {"CF-Access-Client-Id": "abc", "X-Token": "t"}


async def test_fetch_without_custom_headers_passes_none():
    # headers 为空 dict 时必须传 None，保持现有请求完全不变（spec §4 零回归面）
    session = _FakeSession(_FakeResp(200, {}))
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = session
    await client.fetch(EndpointName.INFO)
    assert session.requested_headers is None
