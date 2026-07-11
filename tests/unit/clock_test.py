from palchronicle.infrastructure.clock import Clock, FakeClock, SystemClock


def test_fake_clock_now_and_set_and_advance():
    c = FakeClock(1000)
    assert c.now() == 1000
    c.advance(30)
    assert c.now() == 1030
    c.set(500)
    assert c.now() == 500


def test_fake_clock_monotonic_advances_with_advance_only():
    c = FakeClock(1000)
    m0 = c.monotonic()
    c.advance(5)
    assert c.monotonic() == m0 + 5.0
    # set 不回退单调时钟
    c.set(200)
    assert c.monotonic() == m0 + 5.0


def test_system_clock_is_a_clock_and_returns_int_now():
    c = SystemClock()
    assert isinstance(c.now(), int)
    assert isinstance(c.monotonic(), float)
    assert isinstance(c, Clock)


def test_fake_clock_is_a_clock():
    assert isinstance(FakeClock(0), Clock)
