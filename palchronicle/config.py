"""把 AstrBotConfig(dict) 解析为强类型配置数据类（spec §5.4 / 契约配置节）。"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .domain.enums import AccessMode

_ILLEGAL = (":", "@")


@dataclass(slots=True)
class ServerConfig:
    server_id: str
    name: str
    enabled: bool
    base_url: str
    username: str
    password: str
    timeout: int
    verify_tls: bool
    timezone: str

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.password) and bool(self.base_url)


@dataclass(slots=True)
class SkippedServer:
    raw_name: str
    reason: str  # "empty" / "duplicate" / "illegal_char" / "no_credential"


@dataclass(slots=True)
class BindingConfig:
    umo: str
    server: str
    active: bool


@dataclass(slots=True)
class RoutingConfig:
    access_mode: AccessMode
    default_server: str


@dataclass(slots=True)
class PollingConfig:
    metrics_seconds: int
    players_seconds: int
    info_seconds: int
    settings_seconds: int
    game_data_seconds: int
    jitter_ratio: float
    max_concurrency: int


@dataclass(slots=True)
class WorldConfig:
    timezone: str
    locale: str
    fps_smooth: int
    fps_moderate: int
    fps_laggy: int


@dataclass(slots=True)
class BasesConfig:
    enabled: bool
    assignment_radius: int
    ambiguity_ratio: float
    confirmation_samples: int
    position_grid_size: int
    z_weight: float


@dataclass(slots=True)
class PrivacyConfig:
    mode: str
    public_exact_ping: bool
    public_positions: bool
    ping_good_ms: int
    ping_ok_ms: int
    uncertain_timeout: int


@dataclass(slots=True)
class HistoryConfig:
    raw_metrics_days: int
    aggregate_days: int
    session_days: int
    observation_days: int


@dataclass(slots=True)
class AppConfig:
    servers: list[ServerConfig]
    skipped: list[SkippedServer]
    routing: RoutingConfig
    group_bindings: list[BindingConfig]
    polling: PollingConfig
    world: WorldConfig
    bases: BasesConfig
    privacy: PrivacyConfig
    history: HistoryConfig


def _obj(raw: Mapping, key: str) -> Mapping:
    val = raw.get(key)
    return val if isinstance(val, Mapping) else {}


def _resolve_password(item: Mapping, env: Mapping[str, str]) -> str:
    env_name = str(item.get("password_env", "") or "").strip()
    if env_name:
        from_env = env.get(env_name)
        if from_env:
            return from_env
    return str(item.get("password", "") or "")


def _parse_servers(
    raw: Mapping, env: Mapping[str, str]
) -> tuple[list[ServerConfig], list[SkippedServer]]:
    servers: list[ServerConfig] = []
    skipped: list[SkippedServer] = []
    seen: set[str] = set()
    for item in raw.get("servers", []) or []:
        raw_name = str(item.get("name", "") or "")
        name = raw_name.strip()
        if not name:
            skipped.append(SkippedServer(raw_name=raw_name, reason="empty"))
            continue
        if any(ch in name for ch in _ILLEGAL) or (name != raw_name) or (" " in name):
            skipped.append(SkippedServer(raw_name=raw_name, reason="illegal_char"))
            continue
        if name in seen:
            skipped.append(SkippedServer(raw_name=raw_name, reason="duplicate"))
            continue
        seen.add(name)
        password = _resolve_password(item, env)
        server = ServerConfig(
            server_id=name,
            name=name,
            enabled=bool(item.get("enabled", True)),
            base_url=str(item.get("base_url", "") or ""),
            username=str(item.get("username", "admin") or "admin"),
            password=password,
            timeout=int(item.get("timeout", 10)),
            verify_tls=bool(item.get("verify_tls", True)),
            timezone=str(item.get("timezone", "") or ""),
        )
        servers.append(server)
        if not password:
            skipped.append(SkippedServer(raw_name=raw_name, reason="no_credential"))
    return servers, skipped


def _parse_bindings(raw: Mapping) -> list[BindingConfig]:
    out: list[BindingConfig] = []
    for item in raw.get("group_bindings", []) or []:
        umo = str(item.get("umo", "") or "").strip()
        server = str(item.get("server", "") or "").strip()
        if not umo or not server:
            continue
        out.append(BindingConfig(umo=umo, server=server, active=bool(item.get("active", True))))
    return out


def parse_config(raw: Mapping, env: Mapping[str, str]) -> AppConfig:
    servers, skipped = _parse_servers(raw, env)
    r = _obj(raw, "routing")
    p = _obj(raw, "polling")
    w = _obj(raw, "world")
    b = _obj(raw, "bases")
    pv = _obj(raw, "privacy")
    h = _obj(raw, "history")
    return AppConfig(
        servers=servers,
        skipped=skipped,
        routing=RoutingConfig(
            access_mode=AccessMode(str(r.get("access_mode", "restricted") or "restricted")),
            default_server=str(r.get("default_server", "") or ""),
        ),
        group_bindings=_parse_bindings(raw),
        polling=PollingConfig(
            metrics_seconds=int(p.get("metrics_seconds", 30)),
            players_seconds=int(p.get("players_seconds", 30)),
            info_seconds=int(p.get("info_seconds", 600)),
            settings_seconds=int(p.get("settings_seconds", 1800)),
            game_data_seconds=int(p.get("game_data_seconds", 120)),
            jitter_ratio=float(p.get("jitter_ratio", 0.10)),
            max_concurrency=int(p.get("max_concurrency", 6)),
        ),
        world=WorldConfig(
            timezone=str(w.get("timezone", "Asia/Tokyo") or "Asia/Tokyo"),
            locale=str(w.get("locale", "zh-CN") or "zh-CN"),
            fps_smooth=int(w.get("fps_smooth", 50)),
            fps_moderate=int(w.get("fps_moderate", 35)),
            fps_laggy=int(w.get("fps_laggy", 20)),
        ),
        bases=BasesConfig(
            enabled=bool(b.get("enabled", True)),
            assignment_radius=int(b.get("assignment_radius", 5000)),
            ambiguity_ratio=float(b.get("ambiguity_ratio", 0.20)),
            confirmation_samples=int(b.get("confirmation_samples", 3)),
            position_grid_size=int(b.get("position_grid_size", 2000)),
            z_weight=float(b.get("z_weight", 0.5)),
        ),
        privacy=PrivacyConfig(
            mode=str(pv.get("mode", "balanced") or "balanced"),
            public_exact_ping=bool(pv.get("public_exact_ping", False)),
            public_positions=bool(pv.get("public_positions", False)),
            ping_good_ms=int(pv.get("ping_good_ms", 60)),
            ping_ok_ms=int(pv.get("ping_ok_ms", 120)),
            uncertain_timeout=int(pv.get("uncertain_timeout", 900)),
        ),
        history=HistoryConfig(
            raw_metrics_days=int(h.get("raw_metrics_days", 7)),
            aggregate_days=int(h.get("aggregate_days", 90)),
            session_days=int(h.get("session_days", 365)),
            observation_days=int(h.get("observation_days", 180)),
        ),
    )
