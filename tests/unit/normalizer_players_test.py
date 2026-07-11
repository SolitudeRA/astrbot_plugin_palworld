from palchronicle.adapters.normalizer import normalize_players


def test_normalize_players_mixed_case_keys():
    raw = {
        "players": [
            {
                "UserId": "u-1", "PlayerId": "p-1", "Name": "Alice",
                "Level": "12", "Ping": "45.5", "BuildingCount": "3",
                "Ip": "10.0.0.5", "AccountName": "steam_alice",
            }
        ]
    }
    rows = normalize_players(raw, now=100)
    assert len(rows) == 1
    r = rows[0]
    assert r["userId"] == "u-1"
    assert r["playerId"] == "p-1"
    assert r["name"] == "Alice"
    assert r["level"] == 12
    assert r["ping"] == 45.5
    assert r["building_count"] == 3
    # 原始敏感字段仍保留(待脱敏)
    assert r["ip"] == "10.0.0.5"
    assert r["accountName"] == "steam_alice"


def test_normalize_players_missing_optional_fields():
    raw = {"players": [{"name": "Bob", "level": 1}]}
    rows = normalize_players(raw, now=100)
    r = rows[0]
    assert r["name"] == "Bob"
    assert r["level"] == 1
    assert r["userId"] is None
    assert r["playerId"] is None
    assert r["ping"] is None
    assert r["building_count"] == 0
    assert r["ip"] is None
    assert r["accountName"] is None


def test_normalize_players_empty_or_missing_list():
    assert normalize_players({}, now=1) == []
    assert normalize_players({"players": []}, now=1) == []


def test_normalize_players_top_level_list():
    # 有的实现直接返回顶层数组
    raw = [{"name": "Cara", "level": 5}]
    rows = normalize_players(raw, now=1)
    assert rows[0]["name"] == "Cara"
