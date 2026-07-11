from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.infrastructure.clock import FakeClock


class FakePlayers:
    def __init__(self):
        self.applied = []
        self.uncertain = []
    async def apply_players(self, world, snap): self.applied.append((world, snap))
    async def mark_uncertain(self, world): self.uncertain.append(world)


class FakeNormalizer:
    @staticmethod
    def normalize_players(raw, now):
        return [{"userId": "u1", "name": "Alice", "level": 5, "ping": 40.0,
                 "building_count": 3}]


class FakePrivacy:
    @staticmethod
    def redact_players(rows, world_id, salt, cfg, observed_at=0):
        return PlayersSnapshot(observed_at=1000,
                               players=[PlayerRow("hpk", "u1", "Alice", 5, None, 3)])


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (
        AppConfig,
        BasesConfig,
        HistoryConfig,
        PollingConfig,
        PrivacyConfig,
        RoutingConfig,
        WorldConfig,
    )
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


def _svc(players):
    return SnapshotService(
        repo=None, normalizer_mod=FakeNormalizer, privacy_mod=FakePrivacy,
        meta=None, salt=b"0" * 32, cfg=_cfg(), clock=FakeClock(1000),
        players=players, guilds=None, bases=None, events=None,
    )


async def test_ok_response_applies_players():
    players = FakePlayers(); svc = _svc(players)
    resp = RestResponse(ok=True, status=200, data={"players": []},
                        duration_ms=1, payload_bytes=2, error=None)
    await svc.ingest_players(_world(), resp)
    assert len(players.applied) == 1
    assert players.applied[0][1].players[0].name == "Alice"
    assert players.uncertain == []


async def test_failed_response_marks_uncertain():
    players = FakePlayers(); svc = _svc(players)
    resp = RestResponse(ok=False, status=None, data=None,
                        duration_ms=1, payload_bytes=0, error="timeout")
    await svc.ingest_players(_world(), resp)
    assert players.applied == []
    assert players.uncertain == [_world()]
