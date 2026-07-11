import json

import pytest

from tests.fixtures.loader import fixtures_root, load_fixture, load_series


def test_fixtures_root_points_to_fixtures_dir():
    root = fixtures_root()
    assert root.name == "fixtures"
    assert (root / "loader.py").is_file()


def test_load_fixture_normal_world_info_has_worldguid():
    info = load_fixture("normal_world", "info")
    assert isinstance(info, dict)
    assert "worldguid" in {k.lower() for k in info}


def test_load_fixture_normal_world_players_is_list_payload():
    players = load_fixture("normal_world", "players")
    # /players 响应体是 {"players": [...]}
    assert "players" in {k.lower() for k in players}
    plist = next(v for k, v in players.items() if k.lower() == "players")
    assert isinstance(plist, list) and len(plist) >= 1


def test_load_fixture_missing_scenario_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fixture("does_not_exist", "info")


def test_load_series_sorted_by_tick():
    # api_interrupt_recovery 场景在 Task 6.3 创建；此处先断言排序契约用 normal_world 兜底
    root = fixtures_root()
    series_path = root / "normal_world" / "series.json"
    series_path.write_text(
        json.dumps(
            [
                {"tick": 2, "endpoint": "players", "payload": {"players": []}},
                {"tick": 1, "endpoint": "metrics", "payload": {"fps": 60}},
            ]
        ),
        encoding="utf-8",
    )
    try:
        series = load_series("normal_world")
        assert [f["tick"] for f in series] == [1, 2]
    finally:
        series_path.unlink()
