from palworld_terminal.config import PrivacyConfig
from palworld_terminal.domain.enums import ActionCategory, UnitType
from palworld_terminal.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    PalBoxActor,
)
from palworld_terminal.domain.privacy import hash_user_id, redact_game_data


def _cfg(mode="balanced") -> PrivacyConfig:
    return PrivacyConfig(
        mode=mode, public_exact_ping=False, public_positions=False,
        ping_good_ms=60, ping_ok_ms=120, uncertain_timeout=900,
    )


def _snap() -> GameDataSnapshot:
    player = CharacterActor(
        unit_type=UnitType.PLAYER, instance_id="i1", nickname="Alice",
        trainer_instance_id=None, trainer_nickname=None, player_userid="raw-uid",
        level=10, hp=90, max_hp=100, guild_id="g1", guild_name="G",
        pal_class=None, action=ActionCategory.IDLE, ai_action=ActionCategory.UNKNOWN,
        x=123.0, y=456.0, z=7.0, is_active=True,
    )
    palbox = PalBoxActor(guild_id="g1", guild_name="G", pal_class="PalBox", x=1.0, y=2.0, z=3.0)
    return GameDataSnapshot(
        observed_at=1, fps=60.0, average_fps=58.0, characters=[player],
        palboxes=[palbox], unknown_classes=[],
    )


def test_redact_game_data_hashes_player_userid():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "s1:guid:0", salt, _cfg("balanced"))
    c = out.characters[0]
    assert c.player_userid == hash_user_id(salt, "s1:guid:0", "raw-uid")
    assert c.player_userid != "raw-uid"


def test_redact_game_data_balanced_keeps_coords():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "w", salt, _cfg("balanced"))
    assert out.characters[0].x == 123.0
    assert len(out.palboxes) == 1
    assert out.palboxes[0].x == 1.0


def test_redact_game_data_strict_nulls_coords_and_drops_palboxes():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "w", salt, _cfg("strict"))
    c = out.characters[0]
    assert c.x is None and c.y is None and c.z is None
    assert out.palboxes == []
    # 身份仍脱敏
    assert c.player_userid == hash_user_id(salt, "w", "raw-uid")


def test_redact_game_data_none_userid_stays_none():
    salt = b"\x09" * 32
    snap = _snap()
    snap.characters[0].player_userid = None
    out = redact_game_data(snap, "w", salt, _cfg("balanced"))
    assert out.characters[0].player_userid is None


def test_redact_game_data_no_raw_userid_in_repr():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "w", salt, _cfg("balanced"))
    assert "raw-uid" not in repr(out)


def test_redact_game_data_preserves_in_game_clock_fields():
    # 逐字段重建须补拷游戏内时钟；否则到消费方前被静默重置为默认值。
    salt = b"\x09" * 32
    snap = _snap()
    snap.in_game_days = 590
    snap.in_game_time = "17:44"
    for mode in ("balanced", "strict"):
        out = redact_game_data(snap, "w", salt, _cfg(mode))
        assert out.in_game_days == 590
        assert out.in_game_time == "17:44"
