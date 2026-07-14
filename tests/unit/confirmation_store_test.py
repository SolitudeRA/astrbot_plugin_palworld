from palworld_terminal.presentation.confirmation import ConfirmationStore, PendingAction


class _Clock:
    def __init__(self, t): self.t = t
    def now(self): return self.t


def _p(expiry): return PendingAction(command_str="stop", group="server_admin_danger",
                                     payload={}, server_id="s", umo="u", expiry=expiry)


def test_put_and_claim():
    clk = _Clock(0)
    s = ConfirmationStore(clk)
    s.put("a", _p(expiry=100))
    got = s.claim("a")
    assert got is not None and got.command_str == "stop"


def test_claim_is_pop_no_double():
    s = ConfirmationStore(_Clock(0))
    s.put("a", _p(expiry=100))
    assert s.claim("a") is not None
    assert s.claim("a") is None   # 第二次拿不到（claim-then-execute 防双执行）


def test_claim_expired_returns_none():
    clk = _Clock(0)
    s = ConfirmationStore(clk)
    s.put("a", _p(expiry=50))
    clk.t = 60
    assert s.claim("a") is None


def test_overwrite_single_pending():
    s = ConfirmationStore(_Clock(0))
    s.put("a", _p(expiry=100))
    s.put("a", PendingAction(command_str="ban", group="server_admin_danger",
                             payload={}, server_id="s", umo="u", expiry=100))
    assert s.claim("a").command_str == "ban"


def test_clear_all():
    s = ConfirmationStore(_Clock(0))
    s.put("a", _p(expiry=100))
    s.clear_all()
    assert s.claim("a") is None
