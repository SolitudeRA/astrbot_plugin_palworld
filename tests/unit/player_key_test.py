import hashlib
import hmac

from palchronicle.application.player_service import PlayerService, _resolve_identity
from palchronicle.domain.enums import IdConfidence
from palchronicle.domain.models import PlayerRow

SALT = b"0" * 32


def _expected(world_id, raw):
    return hmac.new(SALT, f"{world_id}:{raw}".encode(), hashlib.sha256).hexdigest()


def test_player_key_matches_hmac():
    assert PlayerService.player_key(SALT, "w1", "user-123") == _expected("w1", "user-123")


def test_player_key_stable_across_calls():
    a = PlayerService.player_key(SALT, "w1", "user-123")
    b = PlayerService.player_key(SALT, "w1", "user-123")
    assert a == b


def test_player_key_world_scoped():
    assert PlayerService.player_key(SALT, "w1", "u") != PlayerService.player_key(SALT, "w2", "u")


def test_resolve_prefers_hashed_userid_high():
    row = PlayerRow(userid="ALREADYHASHED", player_id="pid", name="Alice",
                    level=1, ping=None, building_count=0)
    key, conf = _resolve_identity(row, SALT, "w1")
    assert key == "ALREADYHASHED"
    assert conf == IdConfidence.HIGH


def test_resolve_falls_back_to_player_id_high():
    row = PlayerRow(userid=None, player_id="pid-9", name="Alice",
                    level=1, ping=None, building_count=0)
    key, conf = _resolve_identity(row, SALT, "w1")
    assert key == _expected("w1", "pid-9")
    assert conf == IdConfidence.HIGH


def test_resolve_falls_back_to_name_low():
    row = PlayerRow(userid=None, player_id=None, name="Alice",
                    level=1, ping=None, building_count=0)
    key, conf = _resolve_identity(row, SALT, "w1")
    assert key == _expected("w1", "alice")
    assert conf == IdConfidence.LOW
