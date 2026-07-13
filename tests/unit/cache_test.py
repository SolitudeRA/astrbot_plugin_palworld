from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock


def test_get_miss_returns_none():
    cache = TTLCache(FakeClock(1000))
    assert cache.get("absent") is None


def test_set_then_get_hit():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", {"v": 1}, ttl_seconds=15)
    assert cache.get("k") == {"v": 1}


def test_entry_expires_after_ttl():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", "val", ttl_seconds=15)
    clock.advance(14)
    assert cache.get("k") == "val"
    clock.advance(1)  # now == set_time + 15 → 恰好过期(>=)
    assert cache.get("k") is None


def test_set_overwrites_and_refreshes_ttl():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", "old", ttl_seconds=10)
    clock.advance(8)
    cache.set("k", "new", ttl_seconds=10)
    clock.advance(5)  # 距第二次 set 仅 5s，未过期
    assert cache.get("k") == "new"


def test_expired_key_is_none_not_raise():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", "v", ttl_seconds=5)
    clock.advance(100)
    assert cache.get("k") is None
