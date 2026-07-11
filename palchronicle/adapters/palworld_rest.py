"""aiohttp REST 客户端：BasicAuth、超时、脱敏错误（不含凭证/URL）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from palchronicle.config import ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import Clock

_ENDPOINT_PATH: dict[EndpointName, str] = {
    EndpointName.INFO: "info",
    EndpointName.METRICS: "metrics",
    EndpointName.PLAYERS: "players",
    EndpointName.SETTINGS: "settings",
    EndpointName.GAME_DATA: "game-data",
}


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
