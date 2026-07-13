from palworld_terminal.adapters.privacy_filter import (
    bucketize_ping,
    hash_user_id,
    quantize_cell,
)
from palworld_terminal.config import PrivacyConfig
from palworld_terminal.domain.enums import PingBucket


def _cfg(good=60, ok=120) -> PrivacyConfig:
    return PrivacyConfig(
        mode="balanced", public_exact_ping=False, public_positions=False,
        ping_good_ms=good, ping_ok_ms=ok, uncertain_timeout=900,
    )


def test_hash_user_id_is_stable_and_deterministic():
    salt = b"\x01" * 32
    h1 = hash_user_id(salt, "s1:guid:0", "user-abc")
    h2 = hash_user_id(salt, "s1:guid:0", "user-abc")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    assert all(ch in "0123456789abcdef" for ch in h1)


def test_hash_user_id_differs_by_world_and_id_and_salt():
    salt = b"\x01" * 32
    other_salt = b"\x02" * 32
    base = hash_user_id(salt, "s1:guid:0", "user-abc")
    assert hash_user_id(salt, "s2:guid:0", "user-abc") != base
    assert hash_user_id(salt, "s1:guid:0", "user-xyz") != base
    assert hash_user_id(other_salt, "s1:guid:0", "user-abc") != base


def test_hash_user_id_no_raw_id_residue():
    salt = b"\x01" * 32
    raw = "SuperSecretUserId12345"
    h = hash_user_id(salt, "w", raw)
    assert raw not in h
    assert raw.lower() not in h


def test_bucketize_ping_boundaries():
    cfg = _cfg(good=60, ok=120)
    assert bucketize_ping(60.0, cfg) is PingBucket.GOOD    # == good 阈值 → GOOD
    assert bucketize_ping(59.9, cfg) is PingBucket.GOOD
    assert bucketize_ping(60.1, cfg) is PingBucket.OK
    assert bucketize_ping(120.0, cfg) is PingBucket.OK     # == ok 阈值 → OK
    assert bucketize_ping(120.1, cfg) is PingBucket.HIGH
    assert bucketize_ping(None, cfg) is PingBucket.UNKNOWN


def test_quantize_cell_floor_division():
    assert quantize_cell(100.0, 200.0, 5.0, grid=2000) == "0:0:0"
    assert quantize_cell(2001.0, 4000.0, -1.0, grid=2000) == "1:2:-1"
    assert quantize_cell(-1.0, -2001.0, 0.0, grid=2000) == "-1:-2:0"
