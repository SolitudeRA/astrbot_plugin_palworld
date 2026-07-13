from palworld_terminal.application.base_service import BaseService
from palworld_terminal.domain.models import GameDataSnapshot, PalBox, PalBoxActor, World
from palworld_terminal.infrastructure.clock import FakeClock


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palworld_terminal.config import BasesConfig
    return BasesConfig(True, 5000, 0.2, 3, 2000, 0.5)


def _gd(boxes):
    return GameDataSnapshot(1000, 60.0, 60.0, [], boxes, [])


def _svc():
    return BaseService(repo=None, cfg=_cfg(), clock=FakeClock(1000), salt=b"0" * 32)


def test_new_palbox_when_no_existing():
    svc = _svc()
    gd = _gd([PalBoxActor("G1", None, "Box", 100.0, 200.0, 0.0)])
    matched = svc._match_palboxes(_world(), gd, existing=[])
    assert 0 in matched
    # cell = floor(100/2000)=0, 0, 0
    assert matched[0].position_cell == "0:0:0"


def test_drift_within_grid_reuses_existing():
    svc = _svc()
    gk = svc._guild_key("w1", "G1")
    existing = [PalBox(BaseService.palbox_key("w1", gk, "0:0:0"), "w1", gk,
                       "0:0:0", 900, 900, "active")]
    # 漂移到 x=500 仍在同格 floor(500/2000)=0
    gd = _gd([PalBoxActor("G1", None, "Box", 500.0, 300.0, 0.0)])
    matched = svc._match_palboxes(_world(), gd, existing=existing)
    assert matched[0].palbox_key == existing[0].palbox_key  # 复用, 不新建


def test_far_move_creates_new_palbox():
    svc = _svc()
    gk = svc._guild_key("w1", "G1")
    existing = [PalBox(BaseService.palbox_key("w1", gk, "0:0:0"), "w1", gk,
                       "0:0:0", 900, 900, "active")]
    gd = _gd([PalBoxActor("G1", None, "Box", 9000.0, 9000.0, 0.0)])  # 远处
    matched = svc._match_palboxes(_world(), gd, existing=existing)
    assert matched[0].palbox_key != existing[0].palbox_key
