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
    world_mode: str = "multi"  # "single" | "multi"


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
class FeaturesConfig:
    report: bool
    events: bool
    guilds_bases: bool
    players: bool = False
    server_admin_basic: bool = False
    server_admin_danger: bool = False

    def enabled(self, name: str) -> bool:
        return {
            "core": True, "report": self.report,
            "events": self.events, "guilds_bases": self.guilds_bases,
            "players": self.players,
            "server_admin_basic": self.server_admin_basic,
            "server_admin_danger": self.server_admin_danger,
        }.get(name, False)


def _default_features() -> FeaturesConfig:
    return FeaturesConfig(report=True, events=True, guilds_bases=False)


@dataclass(slots=True)
class PlayersConfig:
    rank_top_n: int
    exclude_names: list[str]


def _default_players() -> PlayersConfig:
    return PlayersConfig(rank_top_n=5, exclude_names=[])


@dataclass(slots=True)
class AdminEntry:
    id: str
    note: str


@dataclass(slots=True)
class PermissionsConfig:
    admins: list[AdminEntry]
    admin_only_commands: list[str]
    # 命令串扁平→完整路径迁移后不再匹配 LOCKABLE_COMMANDS 的锁条目。保留在
    # admin_only_commands（不改锁行为）但在此登记，供启动告警（防静默失锁 = fail-open）。
    unknown_locks: list[str] = field(default_factory=list)


def _default_permissions() -> PermissionsConfig:
    return PermissionsConfig(admins=[], admin_only_commands=[])


# 命令门不可锁集(astrbot 命令串);与 command_registry.LOCKABLE_COMMANDS 一致,
# 此处内联以免 config 依赖 presentation 层。
# 服务器管控写命令(announce/save/kick/unban/ban/shutdown/stop)与 confirm 由
# feature 组 + 管理员名单双闸把守,绝不可再被 admin_only_commands 锁,故一并预置。
_NON_LOCKABLE = frozenset({
    "server", "whoami", "help", "confirm",
    "announce", "save", "kick", "unban", "ban", "shutdown", "stop",
})


@dataclass(slots=True)
class ServerAdminConfig:
    require_confirmation: bool
    confirmation_timeout: int
    audit_retention_days: int


def _default_server_admin() -> ServerAdminConfig:
    return ServerAdminConfig(
        require_confirmation=False, confirmation_timeout=30, audit_retention_days=180)


def _clamp_int(raw, default: int, lo: int, hi: int) -> int:
    """非法(非 int / None)回 default;合法但越界 → clamp 到 [lo, hi]。"""
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _parse_server_admin(raw: Mapping) -> ServerAdminConfig:
    sa = raw.get("server_admin", {}) or {}
    if not isinstance(sa, Mapping):
        sa = {}
    return ServerAdminConfig(
        require_confirmation=bool(sa.get("require_confirmation", False)),
        confirmation_timeout=_clamp_int(sa.get("confirmation_timeout", 30), 30, 5, 600),
        audit_retention_days=_clamp_int(sa.get("audit_retention_days", 180), 180, 1, 3650),
    )


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
    features: FeaturesConfig = field(default_factory=_default_features)
    players: PlayersConfig = field(default_factory=_default_players)
    permissions: PermissionsConfig = field(default_factory=_default_permissions)
    server_admin: ServerAdminConfig = field(default_factory=_default_server_admin)


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
            timeout=_as_int(item.get("timeout", 10), 10),
            verify_tls=bool(item.get("verify_tls", True)),
            timezone=str(item.get("timezone", "") or ""),
        )
        servers.append(server)
        if not password:
            skipped.append(SkippedServer(raw_name=raw_name, reason="no_credential"))
    return servers, skipped


def _as_int(v, default: int) -> int:
    """畸形持久化值(如手改配置文件)降级为默认,不炸启动。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _as_float(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _one_of(v, allowed: frozenset[str], default: str) -> str:
    """枚举白名单收口：非法/缺省值回落 default。"""
    s = str(v)
    return s if s in allowed else default


def _parse_bindings(raw: Mapping) -> list[BindingConfig]:
    out: list[BindingConfig] = []
    for item in raw.get("group_bindings", []) or []:
        umo = str(item.get("umo", "") or "").strip()
        server = str(item.get("server", "") or "").strip()
        if not umo or not server:
            continue
        out.append(BindingConfig(umo=umo, server=server, active=bool(item.get("active", True))))
    return out


def _parse_permissions(raw: Mapping) -> PermissionsConfig:
    admins: list[AdminEntry] = []
    seen: set[str] = set()
    for item in raw.get("permission_admins", []) or []:
        if not isinstance(item, Mapping):
            continue
        pid = str(item.get("id", "") or "").strip()
        if not pid or pid.endswith(":") or pid in seen:  # 空 id / 空账号段 / 重复
            continue
        seen.add(pid)
        admins.append(AdminEntry(id=pid, note=str(item.get("note", "") or "").strip()))
    raw_cmds = raw.get("admin_only_commands", [])
    cmds: list[str] = []
    unknown: list[str] = []
    if isinstance(raw_cmds, list):
        # 函数体内相对 import：避免 config↔presentation 循环依赖；command_registry
        # 不反向 import config，安全。（no_absolute_self_import 只禁绝对自导入前缀。）
        from .presentation.command_registry import LOCKABLE_COMMANDS
        cseen: set[str] = set()
        for c in raw_cmds:
            if not isinstance(c, str):
                continue
            name = c.strip()
            if not name or name in _NON_LOCKABLE or name in cseen:
                continue
            cseen.add(name)
            cmds.append(name)
            # 未知锁条目：保留在 cmds（不改现有锁行为）但登记告警，绝不静默吞。
            if name not in LOCKABLE_COMMANDS:
                unknown.append(name)
    return PermissionsConfig(admins=admins, admin_only_commands=cmds, unknown_locks=unknown)


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
    f = _obj(raw, "features")
    pl = _obj(raw, "players")
    features = FeaturesConfig(
        report=bool(f.get("report", True)),
        events=bool(f.get("events", True)),
        guilds_bases=bool(f.get("guilds_bases", False)),
        players=bool(f.get("players", False)),
        server_admin_basic=bool(f.get("server_admin_basic", False)),
        server_admin_danger=bool(f.get("server_admin_danger", False)),
    )
    return AppConfig(
        servers=servers,
        skipped=skipped,
        routing=RoutingConfig(
            access_mode=AccessMode(str(r.get("access_mode", "restricted") or "restricted")),
            default_server=str(r.get("default_server", "") or ""),
            world_mode=_one_of(r.get("world_mode", "multi"), frozenset({"single", "multi"}), "multi"),
        ),
        group_bindings=_parse_bindings(raw),
        polling=PollingConfig(
            metrics_seconds=_as_int(p.get("metrics_seconds", 30), 30),
            players_seconds=_as_int(p.get("players_seconds", 30), 30),
            info_seconds=_as_int(p.get("info_seconds", 600), 600),
            settings_seconds=_as_int(p.get("settings_seconds", 1800), 1800),
            game_data_seconds=_as_int(p.get("game_data_seconds", 120), 120),
            jitter_ratio=_as_float(p.get("jitter_ratio", 0.10), 0.10),
            max_concurrency=_as_int(p.get("max_concurrency", 6), 6),
        ),
        world=WorldConfig(
            timezone=str(w.get("timezone", "Asia/Tokyo") or "Asia/Tokyo"),
            locale=str(w.get("locale", "zh-CN") or "zh-CN"),
            fps_smooth=_as_int(w.get("fps_smooth", 50), 50),
            fps_moderate=_as_int(w.get("fps_moderate", 35), 35),
            fps_laggy=_as_int(w.get("fps_laggy", 20), 20),
        ),
        bases=BasesConfig(
            enabled=bool(b.get("enabled", True)),
            assignment_radius=_as_int(b.get("assignment_radius", 5000), 5000),
            ambiguity_ratio=_as_float(b.get("ambiguity_ratio", 0.20), 0.20),
            confirmation_samples=_as_int(b.get("confirmation_samples", 3), 3),
            position_grid_size=_as_int(b.get("position_grid_size", 2000), 2000),
            z_weight=_as_float(b.get("z_weight", 0.5), 0.5),
        ),
        privacy=PrivacyConfig(
            mode=str(pv.get("mode", "balanced") or "balanced"),
            public_exact_ping=bool(pv.get("public_exact_ping", False)),
            public_positions=bool(pv.get("public_positions", False)),
            ping_good_ms=_as_int(pv.get("ping_good_ms", 60), 60),
            ping_ok_ms=_as_int(pv.get("ping_ok_ms", 120), 120),
            uncertain_timeout=_as_int(pv.get("uncertain_timeout", 900), 900),
        ),
        history=HistoryConfig(
            raw_metrics_days=_as_int(h.get("raw_metrics_days", 7), 7),
            aggregate_days=_as_int(h.get("aggregate_days", 90), 90),
            session_days=_as_int(h.get("session_days", 365), 365),
            observation_days=_as_int(h.get("observation_days", 180), 180),
        ),
        skipped_headers=skipped_headers,
        features=features,
        players=PlayersConfig(
            rank_top_n=_as_int(pl.get("rank_top_n", 5), 5),
            exclude_names=[s.strip() for s in str(pl.get("exclude_names", "")).split(",") if s.strip()],
        ),
        permissions=_parse_permissions(raw),
        server_admin=_parse_server_admin(raw),
    )
