"""公用 pytest fixtures。"""
import pytest

from palworld_terminal.infrastructure.clock import FakeClock


@pytest.fixture
def fake_clock():
    return FakeClock(1_700_000_000)
