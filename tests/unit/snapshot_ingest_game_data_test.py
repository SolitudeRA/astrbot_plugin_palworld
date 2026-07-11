from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.domain.models import GameDataSnapshot, World
from palchronicle.infrastructure.clock import FakeClock


def _gd():
    return GameDataSnapshot(1000, 60.0, 60.0, [], [], [])


class FakeNormalizer:
    calls = []

    @staticmethod
    def normalize_game_data(raw, now, meta):
        FakeNormalizer.calls.append(("norm", now))
        return _gd()


class FakePrivacy:
    calls = []

    @staticmethod
    def redact_game_data(snap, world_id, salt, cfg):
        FakePrivacy.calls.append(("redact", world_id))
        return snap


class FakeGuilds:
    def __init__(self):
        self.applied = []

    async def apply(self, world, gd):
        self.applied.append(gd)
        return []


class FakeBases:
    def __init__(self):
        self.applied = []

    async def apply(self, world, gd):
        self.applied.append(gd)
        return ["UPD"]  # 占位 update


class FakeEvents:
    def __init__(self):
        self.base_events_calls = []

    async def base_events(self, world, updates):
        self.base_events_calls.append(updates)


def _world():
    return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


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


def _svc(guilds, bases, events):
    FakeNormalizer.calls = []
    FakePrivacy.calls = []
    return SnapshotService(
        repo=None, normalizer_mod=FakeNormalizer, privacy_mod=FakePrivacy,
        meta=None, salt=b"0" * 32, cfg=_cfg(), clock=FakeClock(1000),
        players=None, guilds=guilds, bases=bases, events=events,
    )


async def test_ok_runs_pipeline_and_calls_services():
    guilds, bases, events = FakeGuilds(), FakeBases(), FakeEvents()
    svc = _svc(guilds, bases, events)
    resp = RestResponse(True, 200, {"actors": []}, 1, 2, None)
    await svc.ingest_game_data(_world(), resp)
    assert FakeNormalizer.calls and FakePrivacy.calls   # to_thread 纯计算被走
    assert len(guilds.applied) == 1
    assert len(bases.applied) == 1
    assert events.base_events_calls == [["UPD"]]


async def test_failed_response_is_noop():
    guilds, bases, events = FakeGuilds(), FakeBases(), FakeEvents()
    svc = _svc(guilds, bases, events)
    resp = RestResponse(False, None, None, 1, 0, "timeout")
    await svc.ingest_game_data(_world(), resp)
    assert guilds.applied == [] and bases.applied == []
    assert events.base_events_calls == []
