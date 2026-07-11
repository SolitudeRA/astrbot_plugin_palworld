from pathlib import Path

from palchronicle.adapters import normalizer
from palchronicle.adapters.metadata_repository import MetadataRepository
from tests.fixtures.loader import load_fixture

META = MetadataRepository(Path(__file__).resolve().parents[2] / "metadata")
META.load()


def test_no_players_scenario_yields_empty_player_list():
    raw = load_fixture("no_players", "players")
    rows = normalizer.normalize_players(raw, now=1000)
    assert rows == []


def test_multi_guild_base_has_two_guilds_and_two_palboxes():
    raw = load_fixture("multi_guild_base", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    guild_ids = {a.guild_id for a in snap.characters if a.guild_id}
    assert len(guild_ids) >= 2
    assert len(snap.palboxes) >= 2


def test_missing_fields_game_data_does_not_crash_and_defaults_none():
    raw = load_fixture("missing_fields", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    # 一个 actor 缺 Level/HP/坐标：归一为 None 而非抛错
    assert any(a.level is None for a in snap.characters)
    assert any(a.x is None for a in snap.characters)


def test_unknown_class_registered_and_not_dropped():
    raw = load_fixture("unknown_class", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    assert snap.unknown_classes  # 至少登记一个未知 Class
    # 未知 Class 的 actor 仍保留在快照中，不丢整帧
    assert len(snap.characters) >= 1


def test_mixed_case_keys_players_still_parsed():
    raw = load_fixture("mixed_case_keys", "players")
    rows = normalizer.normalize_players(raw, now=1000)
    assert len(rows) == 1
    assert rows[0]["name"] == "CaseTest"
    assert rows[0]["userId"] == "steam_mixed"


def test_mixed_case_keys_isactive_string_bool_true():
    raw = load_fixture("mixed_case_keys", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    assert snap.characters[0].is_active is True
