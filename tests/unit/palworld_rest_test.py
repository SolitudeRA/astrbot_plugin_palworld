import asyncio
from contextlib import asynccontextmanager

import aiohttp
import pytest

from palchronicle.adapters.palworld_rest import PalworldRestClient, RestResponse
from palchronicle.config import ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock


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

    @asynccontextmanager
    async def get(self, url, auth=None, timeout=None, ssl=None):
        self.requested_url = url
        self.requested_auth = auth
        outcome = self._script
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    async def close(self):
        pass


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
    client._session = _FakeSession(asyncio.TimeoutError())
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
