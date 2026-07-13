from palworld_terminal.adapters.privacy_filter import hash_user_id, redact_players
from palworld_terminal.config import PrivacyConfig


def _cfg() -> PrivacyConfig:
    return PrivacyConfig(
        mode="balanced", public_exact_ping=False, public_positions=False,
        ping_good_ms=60, ping_ok_ms=120, uncertain_timeout=900,
    )


def _rows():
    return [
        {
            "userId": "u-1", "playerId": "p-1", "name": "Alice", "level": 12,
            "ping": 45.5, "building_count": 3, "ip": "10.0.0.5",
            "accountName": "steam_alice",
        },
        {
            "userId": None, "playerId": None, "name": "Bob", "level": 1,
            "ping": None, "building_count": 0, "ip": "192.168.1.9",
            "accountName": "steam_bob",
        },
    ]


def test_redact_players_removes_ip_and_account_and_hashes_id():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "s1:guid:0", salt, _cfg(), observed_at=999)
    assert snap.observed_at == 999
    assert len(snap.players) == 2
    a = snap.players[0]
    assert a.name == "Alice"
    assert a.level == 12
    assert a.building_count == 3
    assert a.ping == 45.5  # 内存渲染保留
    # userId 被替换为 hash, 无原始 id
    assert a.userid == hash_user_id(salt, "s1:guid:0", "u-1")
    assert a.userid != "u-1"
    # 脱敏后的 PlayerRow 无 ip/accountName 属性(dataclass 无此字段)
    assert not hasattr(a, "ip")
    assert not hasattr(a, "accountName")


def test_redact_players_none_id_stays_none():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "w", salt, _cfg())
    b = snap.players[1]
    assert b.userid is None
    assert b.player_id is None
    assert b.name == "Bob"


def test_redact_players_playerid_hashed_when_present():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "w", salt, _cfg())
    a = snap.players[0]
    assert a.player_id == hash_user_id(salt, "w", "p-1")


def test_redact_players_no_raw_ip_in_output_repr():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "w", salt, _cfg())
    text = repr(snap)
    assert "10.0.0.5" not in text
    assert "192.168.1.9" not in text
    assert "steam_alice" not in text
    assert "u-1" not in text
