from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RestResponse:
    ok: bool
    status: int | None
    data: Any | None
    duration_ms: int
    payload_bytes: int
    error: str | None  # 已脱敏：不含凭证/URL/host
