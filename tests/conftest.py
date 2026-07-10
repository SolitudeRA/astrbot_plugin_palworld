"""公用 pytest fixtures。

Task 1.4 交付真正的 palchronicle.infrastructure.clock.FakeClock 后，
本文件的 fake_clock 会切换为 import 该实现；在此之前用等价的内联时钟占位，
保证同一确定性语义（起始 epoch 1_700_000_000、advance/set）。
"""
import pytest


class _InlineClock:
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


@pytest.fixture
def fake_clock():
    return _InlineClock(1_700_000_000)
