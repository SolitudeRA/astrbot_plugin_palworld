"""aiohttp REST 客户端：BasicAuth、超时、脱敏错误（不含凭证/URL）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from ..config import ServerConfig
from ..domain.enums import EndpointName
from ..infrastructure.clock import Clock

_ENDPOINT_PATH: dict[EndpointName, str] = {
    EndpointName.INFO: "info",
    EndpointName.METRICS: "metrics",
    EndpointName.PLAYERS: "players",
    EndpointName.SETTINGS: "settings",
    EndpointName.GAME_DATA: "game-data",
}

# 写端点路径（独立于只读 _ENDPOINT_PATH，不进 EndpointName 轮询枚举）。
_ADMIN_PATH = frozenset({"announce", "save", "kick", "unban", "ban", "shutdown", "stop"})


@dataclass(slots=True)
class RestResponse:
    ok: bool
    status: int | None
    data: Any | None
    duration_ms: int
    payload_bytes: int
    error: str | None  # 已脱敏：不含凭证/URL/host


class PalworldRestClient:
    def __init__(self, server: ServerConfig, clock: Clock) -> None:
        self._server = server
        self._clock = clock
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch(self, endpoint: EndpointName) -> RestResponse:
        session = self._ensure_session()
        url = f"{self._server.base_url}/v1/api/{_ENDPOINT_PATH[endpoint]}"
        auth = aiohttp.BasicAuth(self._server.username, self._server.password)
        # verify_tls 仅对 https 有意义；http 时 ssl 参数被忽略。
        ssl_opt = None if self._server.verify_tls else False
        start = self._clock.monotonic()
        try:
            async with session.get(
                url,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=self._server.timeout),
                # aiohttp 标注不含 None，但运行时 None 等价于默认校验；保持现状不改行为
                ssl=ssl_opt,  # type: ignore[arg-type]
                headers=self._server.headers or None,  # 空 dict 传 None：零回归面
            ) as resp:
                body = await resp.read()
                duration_ms = int((self._clock.monotonic() - start) * 1000)
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return RestResponse(
                        ok=True, status=200, data=data,
                        duration_ms=duration_ms, payload_bytes=len(body), error=None,
                    )
                return RestResponse(
                    ok=False, status=resp.status, data=None,
                    duration_ms=duration_ms, payload_bytes=len(body),
                    error=f"http_status_{resp.status}",
                )
        except TimeoutError:
            return self._error_response(start, "request timeout")
        except aiohttp.ClientError:
            # 绝不带上 exc 文本（可能含 host/URL）；只报类别。
            return self._error_response(start, "network error")
        except Exception:  # noqa: BLE001 — 兜底，仍脱敏
            return self._error_response(start, "unexpected error")

    async def post(self, path: str, json_body: dict | None) -> RestResponse:
        session = self._ensure_session()
        url = f"{self._server.base_url}/v1/api/{path}"
        auth = aiohttp.BasicAuth(self._server.username, self._server.password)
        ssl_opt = None if self._server.verify_tls else False
        start = self._clock.monotonic()
        try:
            async with session.post(
                url,
                auth=auth,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=self._server.timeout),
                ssl=ssl_opt,  # type: ignore[arg-type]
                headers=self._server.headers or None,  # 空 dict 传 None：与 fetch 一致
            ) as resp:
                body = await resp.read()
                duration_ms = int((self._clock.monotonic() - start) * 1000)
                # 写端点常回空/非 JSON body（含 204）；2xx 即成功，不强制 json。
                if 200 <= resp.status < 300:
                    return RestResponse(
                        ok=True, status=resp.status, data=None,
                        duration_ms=duration_ms, payload_bytes=len(body), error=None,
                    )
                return RestResponse(
                    ok=False, status=resp.status, data=None,
                    duration_ms=duration_ms, payload_bytes=len(body),
                    error=f"http_status_{resp.status}",
                )
        except TimeoutError:
            return self._error_response(start, "request timeout")
        except aiohttp.ClientError:
            # stop/shutdown 断连会落此分支；本层如实报 not-ok，语义映射在 AdminService(T4)。
            return self._error_response(start, "network error")
        except Exception:  # noqa: BLE001 — 兜底，仍脱敏
            return self._error_response(start, "unexpected error")

    def _error_response(self, start: float, message: str) -> RestResponse:
        duration_ms = int((self._clock.monotonic() - start) * 1000)
        return RestResponse(
            ok=False, status=None, data=None,
            duration_ms=duration_ms, payload_bytes=0, error=message,
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
