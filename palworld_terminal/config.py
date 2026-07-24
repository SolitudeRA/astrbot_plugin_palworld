"""把 AstrBotConfig(dict) 解析为强类型配置数据类（spec §5.4 / 契约配置节）。"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .domain.enums import AccessMode
from .domain.privacy import PrivacyConfig
from .shared.command_permissions import (
    COMMAND_META,
    CommandOverride,
    admin_configurable,
    admin_forced_true,
    enable_configurable,
)
from .shared.command_registry import DISPATCH

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
    world_mode: str = "single"  # "single" | "multi"
    single_allowed_groups: list[AllowedGroupEntry] = field(default_factory=list)
    setup_confirmed: bool = False  # 首次模式确认标志；随 routing 往返；靠 AstrBot 回填→新装恒 False


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
class HistoryConfig:
    raw_metrics_days: int
    aggregate_days: int
    session_days: int
    observation_days: int


@dataclass(slots=True)
class PlayersConfig:
    rank_top_n: int
    exclude_names: list[str]
    list_fold_limit: int = 7


def _default_players() -> PlayersConfig:
    return PlayersConfig(rank_top_n=5, exclude_names=[], list_fold_limit=7)


@dataclass(slots=True)
class PresentationConfig:
    me_card_theme: str = "light"  # {light, dark, auto}；auto 按服务器本地时钟昼夜


def _default_presentation() -> PresentationConfig:
    return PresentationConfig(me_card_theme="light")


@dataclass(slots=True)
class AdminEntry:
    id: str
    note: str


@dataclass(slots=True)
class AllowedGroupEntry:
    umo: str
    note: str


@dataclass(slots=True)
class PermissionsConfig:
    admins: list[AdminEntry]
    command_overrides: dict[str, CommandOverride]
    # command_permissions 三态行清洗时的非法登记（未知命令 / 轴违规），供启动告警。
    invalid_command_keys: list[str] = field(default_factory=list)


def _default_permissions() -> PermissionsConfig:
    return PermissionsConfig(admins=[], command_overrides={})


# 命令门不可锁集(完整路径);与 command_registry._NON_LOCKABLE 全等,
# 此处内联以免 config 依赖 presentation 层。
# server 各写子动作 + link 各子动作 + 元命令(help/whoami/whereami/confirm)
# 各有内置权限语义,command_permissions 的 admin_only 轴对其无效,故一并预置。
_NON_LOCKABLE = frozenset({
    "server announce", "server save", "server kick", "server unban",
    "server ban", "server shutdown", "server stop",
    "link list", "link add", "link remove",
    "help", "whoami", "whereami", "confirm",
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
    players: PlayersConfig = field(default_factory=_default_players)
    presentation: PresentationConfig = field(default_factory=_default_presentation)
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


def _clamp_rank_top_n(raw) -> int:
    """rank_top_n 榜长 clamp（spec §2.7）：合法区间 1–50；0/负/畸形回默认 5、
    超上限截到 50。注意 0/负是「回默认」而非「clamp 到下界」。"""
    v = _as_int(raw, 5)
    if v < 1:
        return 5
    return min(v, 50)


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


_TRISTATE = {"inherit": None, "on": True, "off": False}


def _parse_single_allowed_groups(raw: Mapping) -> list[AllowedGroupEntry]:
    out: list[AllowedGroupEntry] = []
    seen: set[str] = set()
    for item in raw.get("single_allowed_groups", []) or []:
        if not isinstance(item, Mapping):
            continue
        umo = str(item.get("umo", "") or "").strip()
        if not umo or umo in seen:
            continue
        seen.add(umo)
        out.append(AllowedGroupEntry(umo=umo, note=str(item.get("note", "") or "").strip()))
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

    valid_group_keys = set(DISPATCH.keys())
    overrides: dict[str, dict] = {}
    invalid: list[str] = []
    for row in raw.get("command_permissions", []) or []:
        if not isinstance(row, Mapping):
            continue
        cmd = str(row.get("command", "") or "").strip()
        if not cmd:
            continue
        is_group = cmd in valid_group_keys
        is_path = cmd in COMMAND_META
        if not is_group and not is_path:
            invalid.append(cmd)                       # 未知命令，登记不静默
            continue
        en = _TRISTATE.get(str(row.get("enabled", "inherit")), None)
        ao = _TRISTATE.get(str(row.get("admin_only", "inherit")), None)
        rec = overrides.setdefault(cmd, {})
        if en is not None:
            if is_group or enable_configurable(cmd):
                rec["enabled"] = en
            else:
                invalid.append(f"{cmd}:enabled")       # 轴违规登记（F3）
        if ao is not None:
            if is_group or (admin_configurable(cmd) and not admin_forced_true(cmd)):
                rec["admin_only"] = ao
            else:
                invalid.append(f"{cmd}:admin_only")     # 轴违规登记（F3）
    frozen = {
        k: CommandOverride(enabled=v.get("enabled"), admin_only=v.get("admin_only"))
        for k, v in overrides.items() if v            # 空覆盖行（两轴 inherit）不产 override
    }

    return PermissionsConfig(
        admins=admins, command_overrides=frozen, invalid_command_keys=invalid,
    )


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
    pl = _obj(raw, "players")
    pr = _obj(raw, "presentation")
    permissions = _parse_permissions(raw)
    return AppConfig(
        servers=servers,
        skipped=skipped,
        routing=RoutingConfig(
            access_mode=AccessMode(str(r.get("access_mode", "restricted") or "restricted")),
            default_server=str(r.get("default_server", "") or ""),
            world_mode=_one_of(r.get("world_mode", "single"), frozenset({"single", "multi"}), "single"),
            single_allowed_groups=_parse_single_allowed_groups(raw),
            setup_confirmed=(r.get("setup_confirmed") is True),
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
        players=PlayersConfig(
            rank_top_n=_clamp_rank_top_n(pl.get("rank_top_n", 5)),
            exclude_names=[s.strip() for s in str(pl.get("exclude_names", "")).split(",") if s.strip()],
            # 折叠上限：clamp ≥1，畸形回默认 7（spec §2.7 / §5#10）。
            list_fold_limit=max(1, _as_int(pl.get("list_fold_limit", 7), 7)),
        ),
        presentation=PresentationConfig(
            me_card_theme=_one_of(
                pr.get("me_card_theme", "light"),
                frozenset({"light", "dark", "auto"}), "light"),
        ),
        permissions=permissions,
        server_admin=_parse_server_admin(raw),
    )
