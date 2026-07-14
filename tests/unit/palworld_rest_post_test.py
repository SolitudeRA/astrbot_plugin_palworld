"""post() 写能力：2xx 成功判定容忍空/非 JSON body（含 204）；错误脱敏。"""
import aiohttp

from palworld_terminal.adapters.palworld_rest import PalworldRestClient, RestResponse
from palworld_terminal.config import ServerConfig
from palworld_terminal.infrastructure.clock import FakeClock


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://secret-host:8212", username="admin",
        password="topsecret", timeout=10, verify_tls=True, timezone="",
    )


class _FakeResp:
    def __init__(self, status, body=b"", json_exc=False):
        self.status = status
        self._body = body
        self._json_exc = json_exc

    async def read(self):
        return self._body

    async def json(self, content_type=None):
        if self._json_exc:
            raise ValueError("no json")
        return {"ok": True}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """替换 aiohttp.ClientSession；post 返回响应或（脚本为异常时）抛出。"""

    def __init__(self, outcome):
        self._outcome = outcome
        self.requested_url = None
        self.requested_auth = None
        self.requested_json = "UNSET"
        self.requested_headers = "UNSET"
        self.closed = False

    def post(self, url, auth=None, json=None, timeout=None, ssl=None, headers=None):
        self.requested_url = url
        self.requested_auth = auth
        self.requested_json = json
        self.requested_headers = headers
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def close(self):
        self.closed = True


def _client(outcome):
    c = PalworldRestClient(_server(), FakeClock(1000))
    c._session = _FakeSession(outcome)  # 注入 fake
    return c


async def test_post_200_empty_body_is_success():
    c = _client(_FakeResp(200, b""))
    r = await c.post("announce", {"message": "hi"})
    assert isinstance(r, RestResponse)
    assert r.ok is True
    assert r.status == 200
    assert r.data is None


async def test_post_204_is_success():
    c = _client(_FakeResp(204, b""))
    r = await c.post("save", None)
    assert r.ok is True
    assert r.status == 204


async def test_post_non_json_2xx_is_success():
    c = _client(_FakeResp(200, b"OK", json_exc=True))
    r = await c.post("stop", None)
    assert r.ok is True
    assert r.status == 200


async def test_post_error_status_not_ok():
    c = _client(_FakeResp(400, b"bad"))
    r = await c.post("kick", {"userid": "x"})
    assert r.ok is False
    assert r.status == 400
    assert r.error == "http_status_400"


async def test_post_builds_correct_path_and_basic_auth_and_json():
    c = _client(_FakeResp(200, b""))
    session = c._session
    await c.post("announce", {"message": "hi"})
    assert session.requested_url == "http://secret-host:8212/v1/api/announce"
    assert isinstance(session.requested_auth, aiohttp.BasicAuth)
    assert session.requested_json == {"message": "hi"}


async def test_post_timeout_returns_sanitized_error():
    c = _client(TimeoutError())
    r = await c.post("shutdown", None)
    assert r.ok is False
    assert r.status is None
    assert "timeout" in r.error.lower()
    assert "topsecret" not in r.error
    assert "secret-host" not in r.error


async def test_post_network_error_sanitized():
    err = aiohttp.ClientConnectorError(
        connection_key=None, os_error=OSError("connect to secret-host failed")
    )
    c = _client(err)
    r = await c.post("stop", None)
    assert r.ok is False
    assert r.error is not None
    assert "secret-host" not in r.error
    assert "topsecret" not in r.error


async def test_post_unexpected_error_redacted():
    c = _client(RuntimeError("boom at secret-host"))
    r = await c.post("ban", {"userid": "x"})
    assert r.ok is False
    assert r.error == "unexpected error"
    assert "secret-host" not in r.error


async def test_post_empty_headers_passes_none():
    c = _client(_FakeResp(200, b""))
    session = c._session
    await c.post("save", None)
    assert session.requested_headers is None
