"""可注入时钟。SystemClock 生产用；FakeClock 测试确定性用。"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> int:
        """当前 epoch 秒（UTC）。"""
        ...

    def monotonic(self) -> float:
        """单调秒（用于测量耗时/背压，不受系统时钟回拨影响）。"""
        ...


class SystemClock:
    def now(self) -> int:
        return int(time.time())

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    def __init__(self, start: int) -> None:
        self._t = start
        self._mono = 0.0

    def now(self) -> int:
        return self._t

    def monotonic(self) -> float:
        return self._mono

    def advance(self, secs: int) -> None:
        self._t += secs
        self._mono += float(secs)

    def set(self, t: int) -> None:
        self._t = t
