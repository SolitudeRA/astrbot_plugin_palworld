from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import CharacterActor, GameDataSnapshot
from palchronicle.domain.enums import UnitType, ActionCategory


def _actor(unit_type, instance_id=None, trainer_instance_id=None, pal_class=None):
    return CharacterActor(
        unit_type=unit_type, instance_id=instance_id, nickname=None,
        trainer_instance_id=trainer_instance_id, trainer_nickname=None,
        player_userid=None, level=None, hp=None, max_hp=None,
        guild_id=None, guild_name=None, pal_class=pal_class,
        action=ActionCategory.IDLE, ai_action=ActionCategory.IDLE,
        x=None, y=None, z=None, is_active=True,
    )


def _gd(actors):
    return GameDataSnapshot(observed_at=1000, fps=60.0, average_fps=60.0,
                            characters=actors, palboxes=[], unknown_classes=[])


def test_links_otomo_to_owner():
    gd = _gd([
        _actor(UnitType.PLAYER, instance_id="I1"),
        _actor(UnitType.OTOMO, trainer_instance_id="I1", pal_class="Sheepball"),
    ])
    assert PlayerService.link_companions(gd) == {"I1": "Sheepball"}


def test_unlinkable_otomo_ignored():
    gd = _gd([
        _actor(UnitType.PLAYER, instance_id="I1"),
        _actor(UnitType.OTOMO, trainer_instance_id="I9", pal_class="Foxparks"),
    ])
    assert PlayerService.link_companions(gd) == {}


def test_first_otomo_wins_per_owner():
    gd = _gd([
        _actor(UnitType.PLAYER, instance_id="I1"),
        _actor(UnitType.OTOMO, trainer_instance_id="I1", pal_class="First"),
        _actor(UnitType.OTOMO, trainer_instance_id="I1", pal_class="Second"),
    ])
    assert PlayerService.link_companions(gd) == {"I1": "First"}


def test_no_players_empty():
    gd = _gd([_actor(UnitType.WILD, pal_class="Chikipi")])
    assert PlayerService.link_companions(gd) == {}
