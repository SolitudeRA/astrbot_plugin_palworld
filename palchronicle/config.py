"""把 AstrBotConfig(dict) 解析为强类型配置数据类（spec §5.4 / 契约配置节）。"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .domain.enums import AccessMode

_ILLEGAL = (":", "@")
# RFC 9110 tchar；用 fullmatch（$ 会在末尾换行前匹配，是暗坑）
_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
# aiohttp 序列化期禁止集（除 TAB \x09 外的控制字符）；\r\n 注入在此一并封死
_HEADER_VALUE_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
# authorization: 与 BasicAuth auth= 共存 aiohttp 抛 ValueError
# host: 避免与 base_url 的 SNI/TLS 校验、连接复用键不一致
# content-length/transfer-encoding/connection: 报文框架头，GET 上只会破坏请求
# expect: 100-continue 会让 aiohttp 阻塞等待 100，网关不回则每次轮询空转到超时
_RESERVED_HEADERS = frozenset({
    "authorization", "host", "content-length", "transfer-encoding",
    "connection", "expect",
})


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
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.password) and bool(self.base_url)


@dataclass(slots=True)
class SkippedServer:
    raw_name: str
    reason: str  # "empty" / "duplicate" / "illegal_char" / "no_credential"


@dataclass(slots=True)
class SkippedHeader:
    raw_name: str  # 原始 name；绝不携带 value（脱敏红线）
    reason: str    # empty_name / illegal_name / reserved / empty_value / illegal_value


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
    skipped_headers: list[SkippedHeader] = field(default_factory=list)


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


def _resolve_header_value(item: Mapping, env: Mapping[str, str]) -> str:
    env_name = str(item.get("value_env", "") or "").strip()
    if env_name:
        from_env = env.get(env_name)
        if from_env:
            return from_env
    return str(item.get("value", "") or "")


def _parse_custom_headers(
    raw: Mapping, env: Mapping[str, str], server_names: list[str]
) -> tuple[dict[str, dict[str, str]], list[SkippedHeader]]:
    """返回 (server_name -> 最终请求头 dict, 跳过列表)。

    name/value 各 strip 一次后贯穿全部判定与落盘；header 名大小写不敏感
    去重、后者覆盖前者且保留后者大小写；作用域零匹配=零服务器（fail-closed）。
    """
    per_server: dict[str, dict[str, str]] = {n: {} for n in server_names}
    canon: dict[str, dict[str, str]] = {n: {} for n in server_names}  # lower -> 落盘名
    skipped: list[SkippedHeader] = []
    for item in raw.get("custom_headers", []) or []:
        raw_name = str(item.get("name", "") or "")
        name = raw_name.strip()
        if not name:
            skipped.append(SkippedHeader(raw_name=raw_name, reason="empty_name"))
            continue
        if not _HEADER_NAME_RE.fullmatch(name):
            skipped.append(SkippedHeader(raw_name=raw_name, reason="illegal_name"))
            continue
        lower = name.lower()
        if lower in _RESERVED_HEADERS:
            skipped.append(SkippedHeader(raw_name=raw_name, reason="reserved"))
            continue
        value = _resolve_header_value(item, env).strip()
        if not value:
            skipped.append(SkippedHeader(raw_name=raw_name, reason="empty_value"))
            continue
        if _HEADER_VALUE_ILLEGAL_RE.search(value):
            skipped.append(SkippedHeader(raw_name=raw_name, reason="illegal_value"))
            continue
        scope_raw = str(item.get("servers", "") or "").strip()
        if not scope_raw:
            targets = server_names  # 字段整体为空 = 所有服务器
        else:
            listed = [seg.strip() for seg in scope_raw.split(",")]
            # 非空但零有效段/零匹配 → 零服务器，绝不回退到全部
            targets = [n for n in listed if n and n in per_server]
        for n in targets:
            prev = canon[n].pop(lower, None)
            if prev is not None:
                per_server[n].pop(prev, None)
            canon[n][lower] = name
            per_server[n][name] = value
    return per_server, skipped


def parse_config(raw: Mapping, env: Mapping[str, str]) -> AppConfig:
    servers, skipped = _parse_servers(raw, env)
    header_map, skipped_headers = _parse_custom_headers(
        raw, env, [s.name for s in servers])
    for s in servers:
        s.headers = header_map[s.name]
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
        skipped_headers=skipped_headers,
    )
