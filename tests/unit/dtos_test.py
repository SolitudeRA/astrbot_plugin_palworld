from palworld_terminal.domain.enums import Confidence, PingBucket
from palworld_terminal.presentation.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventDTO,
    GuildDetailDTO,
    GuildDTO,
    OnlineDTO,
    OnlinePlayerRow,
    RulesDTO,
    RuleSection,
    ServerStatusRow,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
)


def test_status_dto_fields():
    dto = StatusDTO(
        server_name="alpha", world_name="Palpagos", world_day=42,
        online=3, max_players=32, basecamp_count=5, fps=58.0, frame_time=17.2,
        smoothness_label="流畅", players=[("Neo", 21, "good")],
        peak_online_today=7, updated_at=1000, degraded=False, last_ok=1000,
    )
    assert dto.world_day == 42
    assert dto.players[0] == ("Neo", 21, "good")


def test_online_dto_uses_ping_bucket():
    row = OnlinePlayerRow(name="Neo", level=21, ping_bucket=PingBucket.GOOD, online_seconds=3600)
    dto = OnlineDTO(rows=[row], updated_at=1000, degraded=False)
    assert dto.rows[0].ping_bucket is PingBucket.GOOD


def test_base_detail_carries_confidence():
    dto = BaseDetailDTO(
        display_name="Noema-2", guild_name="Noema", confidence=Confidence.HIGH,
        palbox_count=1, worker_count=8, active_count=6, average_level=17.5,
        average_hp_ratio=0.9, action_distribution={"working": 6, "idle": 2},
        activity_score=82.5, health_score=90.0,
    )
    assert dto.confidence is Confidence.HIGH


def test_remaining_dtos_construct():
    WorldSummaryDTO(
        world_day=1, online=0, max_players=32, players=0, otomo=0, base_pal=0, wild=0,
        npc=0, palbox=0, guilds=0, basecamp_count=0,
        wild_top=[WildTopRow(name="Lamball", count=4)], available=True,
    )
    RulesDTO(
        sections=[RuleSection(title="倍率", items=[("经验", "1.0x")])],
        available=True, privacy_note=None, updated_at=1000,
    )
    GuildDTO(name="Noema", observed_members=4, palbox=2, base_pals=10, active_7d=3)
    GuildDetailDTO(
        name="Noema", first_seen_at=1, last_seen_at=2, observed_members=4,
        active_today=2, active_week=3, palbox=2, base_pals=10, average_level=15.0,
        base_event_lines=["据点新增：Noema-2"],
    )
    BaseDTO(index=1, display_name="Noema-1", guild_name="Noema",
            confidence=Confidence.MEDIUM, worker_count=5)
    EventDTO(occurred_at=1000, event_type="new_player", summary="新玩家加入")
    ServerStatusRow(name="alpha", ready=True, online=True, allowed=True, active=True)
