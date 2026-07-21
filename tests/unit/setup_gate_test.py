from types import SimpleNamespace

import main
from palworld_terminal.presentation.locale import L
from palworld_terminal.shared.command_registry import FLAT_ACTIONS, PAL_REGISTERED


def _plugin(setup_confirmed: bool):
    # 绕过 __init__（其需 context）；只装 _setup_gate 依赖的 live 配置
    p = main.PalWorldTerminal.__new__(main.PalWorldTerminal)
    p._container = SimpleNamespace(
        config=SimpleNamespace(routing=SimpleNamespace(setup_confirmed=setup_confirmed)))
    return p


def test_setup_exempt_subset_of_flat_actions():
    assert main._SETUP_EXEMPT <= set(FLAT_ACTIONS)


def test_gate_allows_exempt_when_unconfirmed():
    p = _plugin(False)
    for w in main._SETUP_EXEMPT:
        assert p._setup_gate(w) is None


def test_gate_blocks_every_non_exempt_when_unconfirmed():
    p = _plugin(False)
    for w in set(PAL_REGISTERED) - main._SETUP_EXEMPT:
        assert p._setup_gate(w) == L("setup_required")


def test_gate_allows_all_when_confirmed():
    p = _plugin(True)
    for w in PAL_REGISTERED:
        assert p._setup_gate(w) is None
