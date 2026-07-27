"""公用 pytest fixtures。"""
import pytest

from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.presentation.locale import load_locale


@pytest.fixture(autouse=True)
def _reset_locale():
    """每个用例结束后复位到 zh-CN，防止装载 ja/en 的用例污染后续全局态。

    （当前测试套无 xdist 并行；全局 locale 态串扰由此兜底。）
    """
    yield
    load_locale("zh-CN")


@pytest.fixture
def fake_clock():
    return FakeClock(1_700_000_000)
