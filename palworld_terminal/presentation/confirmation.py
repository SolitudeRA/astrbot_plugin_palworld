from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..infrastructure.clock import Clock


@dataclass(slots=True)
class PendingAction:
    command_str: str
    group: str
    payload: dict[str, Any]
    server_id: str
    umo: str
    expiry: float


class ConfirmationStore:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._pending: dict[str, PendingAction] = {}

    def put(self, sender_id: str, pending: PendingAction) -> None:
        self._pending[sender_id] = pending   # 单条覆盖

    def claim(self, sender_id: str) -> PendingAction | None:
        p = self._pending.pop(sender_id, None)   # 原子 pop：claim-then-execute
        if p is None or p.expiry <= self._clock.now():
            return None
        return p

    def clear_all(self) -> None:
        self._pending.clear()
