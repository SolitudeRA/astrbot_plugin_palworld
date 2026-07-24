"""Repository 端口协议（ISP 分离，application 依赖倒置的抽象边界）。

按调用方职责分成 4 个 `Protocol`：读（query/report/name_resolver）、写（event）、
路由（routing）、审计（admin）。每个方法签名逐字复制自
`adapters/sqlite_repository.py` 对应 public 方法——`Repository` 结构化满足全部 4
端口（无需继承/声明），mypy 在各 service 标注处对 container 传入的 Repository 实例
自动校验。本模块只依赖 domain（models）+ typing——不 import adapters。
"""
from __future__ import annotations

from typing import Protocol

from ..domain.models import (
    Base,
    BaseObservation,
    Guild,
    ObservedSpecies,
    PlayerIdentity,
    PlayerObservation,
    PlayerSession,
    World,
    WorldEvent,
    WorldMetric,
)


class ReadRepositoryPort(Protocol):
    """读端口：query_service / report_service / name_resolver 消费。"""

    async def climb_levels(
        self, world_id: str, window_start: int
    ) -> list[tuple[str, int, int, bool]]: ...

    async def get_hidden_keys(self, world_id: str) -> set[str]: ...

    async def get_open_session(
        self, world_id: str, player_key: str
    ) -> PlayerSession | None: ...

    async def get_player(
        self, world_id: str, player_key: str
    ) -> PlayerIdentity | None: ...

    async def get_player_by_name(
        self, world_id: str, name: str
    ) -> PlayerIdentity | None: ...

    async def latest_base_observation(
        self, world_id: str, base_key: str
    ) -> BaseObservation | None: ...

    async def latest_metric(self, world_id: str) -> WorldMetric | None: ...

    async def latest_observation(
        self, world_id: str, player_key: str
    ) -> PlayerObservation | None: ...

    async def list_bases(
        self, world_id: str, include_low: bool = False,
        include_hidden: bool = False,
    ) -> list[Base]: ...

    async def list_events(
        self, world_id: str, since: int | None = None, limit: int = 20,
        offset: int = 0,
    ) -> list[WorldEvent]: ...

    async def list_guilds(self, world_id: str) -> list[Guild]: ...

    async def list_open_sessions(self, world_id: str) -> list[PlayerSession]: ...

    async def list_players_by_level(self, world_id: str) -> list[PlayerIdentity]: ...

    async def list_players_by_name(self, world_id: str, name: str) -> list[str]: ...

    async def observed_species(self) -> list[ObservedSpecies]: ...

    async def peak_online(self, world_id: str, since: int | None = None) -> int: ...

    async def sessions_in_day(
        self, world_id: str, start_ts: int, end_ts: int
    ) -> list[PlayerSession]: ...

    async def total_durations(self, world_id: str) -> dict[str, int]: ...

    async def world_day_bounds(
        self, world_id: str, start: int, end: int
    ) -> tuple[int, int] | None: ...


class WriteRepositoryPort(Protocol):
    """写端口：event_service 消费（peak_online 为 online_record 基线判定所需读）。"""

    async def insert_event(self, e: WorldEvent) -> bool: ...

    async def peak_online(self, world_id: str, since: int | None = None) -> int: ...

    async def upsert_observed_species(
        self, species_class: str, species_name: str, element: str,
        now: int, first_seen_name: str | None,
    ) -> None: ...


class RoutingRepositoryPort(Protocol):
    """路由端口：routing_service 消费。"""

    async def get_allowed(self, umo: str) -> set[str]: ...

    async def get_binding_active(self, umo: str) -> str | None: ...

    async def list_group_servers(self, umo: str) -> dict[str, tuple[bool, bool]]: ...

    async def revoke(self, umo: str, server_id: str) -> None: ...

    async def set_active(self, umo: str, server_id: str) -> None: ...


class AuditRepositoryPort(Protocol):
    """审计端口：admin_service 消费。"""

    async def get_current_world(self, server_id: str) -> World | None: ...

    async def insert_audit(
        self, *, ts: int, admin_id: str, action: str, server_name: str,
        target_name: str | None, target_hash: str | None, detail: str | None,
        success: int, error: str | None,
    ) -> None: ...
