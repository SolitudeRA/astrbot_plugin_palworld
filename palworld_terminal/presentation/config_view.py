"""插件页面配置读写的同步纯函数：脱敏读 / 校验回填 / 状态行。

红线：password/value 明文与 env 值绝不出现在任何返回；回填按稳定
__row_id；错误只含字段路径不含值。全部无 IO/无 await，可脱离 AstrBot 单测。
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit

from ..shared.command_permissions import COMMAND_META
from ..shared.command_registry import DISPATCH

_LIST_SECTIONS = ("servers", "custom_headers", "group_bindings", "permission_admins",
                  "command_permissions", "single_allowed_groups")
_ROW_ID_PREFIX = {"servers": "srv", "custom_headers": "hdr", "group_bindings": "bind",
                  "permission_admins": "adm", "command_permissions": "cmd",
                  "single_allowed_groups": "sag"}

# command_permissions 行校验：command 须为完整路径（COMMAND_META）或组名（DISPATCH），
# enabled/admin_only 三态 ∈ {inherit,on,off}（与 config._TRISTATE 键全等）。
_VALID_COMMAND_KEYS = set(COMMAND_META) | set(DISPATCH)
_CMD_PERM_TRISTATE = frozenset({"inherit", "on", "off"})

SENTINEL = "__unchanged__"

# 每个列表节允许落盘的键（对照 _conf_schema.json 模板）；此外的键（含前端回传的
# __row_id/password_set/value_set/__template_key 与任何未知键）一律在落盘前剔除。
_SECTION_KEYS = {
    "servers": {"name", "enabled", "base_url", "username", "password",
                "password_env", "timeout", "verify_tls", "timezone"},
    "custom_headers": {"name", "value", "value_env", "servers"},
    "group_bindings": {"umo", "server", "active"},
    "permission_admins": {"id", "note"},
    "command_permissions": {"command", "enabled", "admin_only"},
    "single_allowed_groups": {"umo", "note"},
}

_TOP_KEYS = {
    "servers", "routing", "group_bindings", "custom_headers",
    "polling", "world", "bases", "privacy", "history", "players",
    "presentation", "permission_admins", "command_permissions", "server_admin",
    "single_allowed_groups",
}

# server_admin 的两个带界 int 字段（范围须与 config.py::_parse_server_admin 一致）；
# 带上下界故不走 _NUM_FIELDS（仅判非负），改用独立形状校验。
_SERVER_ADMIN_INT_BOUNDS = {
    "confirmation_timeout": (5, 600),
    "audit_retention_days": (1, 3650),
}
_MAX_LIST = 200
_MAX_STR = 8 * 1024
_MAX_BODY = 256 * 1024

# 路径化语义预校验规格：enum 白名单 + 数值字段类型
_ENUMS = {
    "routing.access_mode": {"restricted", "open"},
    "routing.world_mode": {"multi", "single"},
    "privacy.mode": {"strict", "balanced", "advanced"},
    "world.locale": {"zh-CN"},
    "presentation.me_card_theme": {"light", "dark", "auto"},
}
# (section, field) -> "int" | "float"；section=None 表示顶层 object 节
_NUM_FIELDS = {
    ("servers", "timeout"): "int",
    ("polling", "metrics_seconds"): "int", ("polling", "players_seconds"): "int",
    ("polling", "info_seconds"): "int", ("polling", "settings_seconds"): "int",
    ("polling", "game_data_seconds"): "int", ("polling", "max_concurrency"): "int",
    ("polling", "jitter_ratio"): "float",
    ("world", "fps_smooth"): "int", ("world", "fps_moderate"): "int",
    ("world", "fps_laggy"): "int",
    ("bases", "assignment_radius"): "int", ("bases", "confirmation_samples"): "int",
    ("bases", "position_grid_size"): "int",
    ("bases", "ambiguity_ratio"): "float", ("bases", "z_weight"): "float",
    ("privacy", "ping_good_ms"): "int", ("privacy", "ping_ok_ms"): "int",
    ("privacy", "uncertain_timeout"): "int",
    ("history", "raw_metrics_days"): "int", ("history", "aggregate_days"): "int",
    ("history", "session_days"): "int", ("history", "observation_days"): "int",
    ("players", "rank_top_n"): "int",
    ("players", "list_fold_limit"): "int",
}


def redact_config(raw: Mapping) -> dict:
    """返回可安全下发给页面的配置副本：明文脱敏、注入稳定 __row_id。"""
    out = copy.deepcopy(dict(raw))
    for section in _LIST_SECTIONS:
        items = out.get(section)
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item["__row_id"] = f"{_ROW_ID_PREFIX[section]}-{i}"
        if section == "servers":
            for item in items:
                if isinstance(item, dict):
                    pw = str(item.get("password", "") or "")
                    env = str(item.get("password_env", "") or "")
                    item["password"] = ""
                    item["password_set"] = bool(pw) or bool(env)
        if section == "custom_headers":
            for item in items:
                if isinstance(item, dict):
                    val = str(item.get("value", "") or "")
                    env = str(item.get("value_env", "") or "")
                    item["value"] = ""
                    item["value_set"] = bool(val) or bool(env)
    return out


def _err(code: str, path: str | None = None) -> tuple[bool, dict]:
    detail: dict = {}
    if path is not None:
        detail["path"] = path
    return False, {"error": code, "detail": detail}


def _num_valid(val, kind: str) -> bool:
    # bool 是 int 子类，int(True)=1 会被误当合法数值——显式排除
    if isinstance(val, bool):
        return False
    try:
        num = (int if kind == "int" else float)(val)
    except (TypeError, ValueError):
        return False
    # 拒绝 NaN/inf（float("nan"/"inf") 本身合法但会污染下游）与负数
    # （本表所有配置项语义均非负：秒数/半径/次数/比例/天数等）
    if not math.isfinite(num) or num < 0:
        return False
    return True


def _index_old(old_raw, section: str) -> dict:
    """old_raw 的某列表节按 __row_id 规则（srv-i/hdr-i/bind-i）建索引。

    old_raw 是未经 redact 的原始配置（无 __row_id），故这里按位置重建同款 id。
    """
    prefix = _ROW_ID_PREFIX[section]
    items = old_raw.get(section) or []
    return {f"{prefix}-{i}": it for i, it in enumerate(items)
            if isinstance(it, dict)}


def validate_and_backfill(body, old_raw, env):
    if not isinstance(body, Mapping):
        return _err("invalid_shape")
    if len(str(body)) > _MAX_BODY:
        return _err("too_large")
    if not set(body).issubset(_TOP_KEYS):
        return _err("invalid_shape")

    # 形状/类型 + 体积（列表节逐项须 dict）
    for section in _LIST_SECTIONS:
        items = body.get(section, [])
        if not isinstance(items, list):
            return _err("invalid_shape")
        if len(items) > _MAX_LIST:
            return _err("too_large")
        for it in items:
            if not isinstance(it, dict):
                return _err("invalid_shape")
            for v in it.values():
                if isinstance(v, str) and len(v) > _MAX_STR:
                    return _err("too_large")
    for section in ("routing", "polling", "world", "bases", "privacy", "history",
                    "players", "presentation", "server_admin"):
        if section in body and not isinstance(body[section], Mapping):
            return _err("invalid_shape")

    # command_permissions 行校验：command ∈ COMMAND_META∪DISPATCH（完整路径或组名），
    # enabled/admin_only 若存在须三态；非法即拒（与 servers/permission_admins 行校验同规格，
    # 非静默）。行「必为 dict / str 上限」已由上面的列表节循环保证。
    for i, row in enumerate(body.get("command_permissions", [])):
        cmd = row.get("command")
        if not isinstance(cmd, str) or cmd not in _VALID_COMMAND_KEYS:
            return _err("invalid_field", f"command_permissions[{i}].command")
        for axis in ("enabled", "admin_only"):
            if axis in row and row[axis] not in _CMD_PERM_TRISTATE:
                return _err("invalid_field", f"command_permissions[{i}].{axis}")

    # routing.setup_confirmed：首次引导确认闸（bool），存在且非 bool → invalid_shape
    # （镜像 server_admin.require_confirmation 守卫；routing object-ness 已由上面 tuple 保证）。
    rt = body.get("routing")
    if isinstance(rt, Mapping):
        sc = rt.get("setup_confirmed")
        if sc is not None and not isinstance(sc, bool):
            return _err("invalid_shape", "routing.setup_confirmed")

    # server_admin：object 三字段（require_confirmation:bool + 两个带界 int），
    # 类型错/越界 → invalid_shape（object-ness 已由上面的 tuple 保证）。
    sa = body.get("server_admin")
    if isinstance(sa, Mapping):
        rc = sa.get("require_confirmation")
        if rc is not None and not isinstance(rc, bool):
            return _err("invalid_shape", "server_admin.require_confirmation")
        for field, (lo, hi) in _SERVER_ADMIN_INT_BOUNDS.items():
            if field in sa:
                v = sa[field]
                # bool 是 int 子类须显式排除；仅接受界内 int（页面已 coerce 成数值）
                if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
                    return _err("invalid_shape", f"server_admin.{field}")

    # 路径化语义预校验（enum 白名单）
    for path, allowed in _ENUMS.items():
        sect, field = path.split(".")
        node = body.get(sect)
        if isinstance(node, Mapping) and field in node:
            if node[field] not in allowed:
                return _err("invalid_field", path)
    # 数值字段可转性
    for (sect, field), kind in _NUM_FIELDS.items():
        node = body.get(sect)
        if sect == "servers":
            for i, it in enumerate(body.get("servers", [])):
                if field in it and not _num_valid(it[field], kind):
                    return _err("invalid_field", f"servers[{i}].{field}")
        elif isinstance(node, Mapping) and field in node:
            if not _num_valid(node[field], kind):
                return _err("invalid_field", f"{sect}.{field}")

    # 哨兵回填 + 凭证重定向 + 剥离元键
    old_servers = _index_old(old_raw, "servers")
    old_headers = _index_old(old_raw, "custom_headers")
    cand = copy.deepcopy(dict(body))

    for i, s in enumerate(cand.get("servers", [])):
        rid = s.get("__row_id")
        old = old_servers.get(rid) if rid else None
        if s.get("password") == SENTINEL:
            if old is None:
                return _err("invalid_field", f"servers[{i}].password")
            if _host_changed(old.get("base_url", ""), s.get("base_url", "")):
                return _err("credential_redirect", f"servers[{i}].password")
            s["password"] = str(old.get("password", "") or "")
    for i, h in enumerate(cand.get("custom_headers", [])):
        rid = h.get("__row_id")
        old = old_headers.get(rid) if rid else None
        if h.get("value") == SENTINEL:
            if old is None:
                return _err("invalid_field", f"custom_headers[{i}].value")
            h["value"] = str(old.get("value", "") or "")

    _strip_meta(cand)
    return True, cand


def _host_changed(old_url, new_url) -> bool:
    # 非字符串 base_url 归一化为 ""，避免 urlsplit 抛 TypeError 冒泡成 500
    o = urlsplit(old_url if isinstance(old_url, str) else "")
    n = urlsplit(new_url if isinstance(new_url, str) else "")
    return (o.scheme, o.hostname, o.port) != (n.scheme, n.hostname, n.port)


def _strip_meta(cand: dict) -> None:
    # 逐项键白名单：只保留 schema 允许的键，其余（元键 + 任意未知键）落盘前剔除
    for section in _LIST_SECTIONS:
        allowed = _SECTION_KEYS[section]
        for it in cand.get(section, []) or []:
            if isinstance(it, dict):
                for k in list(it):
                    if k not in allowed:
                        it.pop(k, None)


def status_rows(entries: list) -> list[dict]:
    """把 (name, ready, StatusDTO|None) 组装为白名单状态行。"""
    rows: list[dict] = []
    for name, ready, dto in entries:
        if dto is None:
            rows.append({"name": name, "ready": ready})
            continue
        row = {
            # 白名单仅世界级数据,不含 players 个体列表(隐私面不扩)
            "name": name, "ready": ready, "online": dto.online,
            "max_players": dto.max_players, "fps": dto.fps,
            "smoothness_label": dto.smoothness_label,
            "world_day": dto.world_day, "peak_online_today": dto.peak_online_today,
            "basecamp_count": dto.basecamp_count, "updated_at": dto.updated_at,
            "degraded": dto.degraded, "last_ok": dto.last_ok,
        }
        # 详细区仅下发给 ready 且非 degraded 的行(装配层未产出 detail 时静默跳过);
        # 仍是世界级白名单,不含任何玩家个体数据。
        detail = getattr(dto, "detail", None)
        if ready and not dto.degraded and detail is not None:
            row["detail"] = {
                "version": detail.version,
                "description": detail.description,
                "uptime_seconds": detail.uptime_seconds,
                "frametime_ms": detail.frametime_ms,
                "address": detail.address,
                "rules": detail.rules,
            }
        rows.append(row)
    return rows


_AUDIT_HASH_TAIL = 6  # target_hash 是 64 位 HMAC-SHA256 hex，只露末段辅助去歧义


def _fmt_audit_ts(ts) -> str:
    """epoch → 可读 UTC 字符串；非法/缺失 ts 归为空串（不冒泡成 500）。"""
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _audit_target(name, target_hash) -> str:
    """角色名 + hash 尾段组合。绝不回显完整 hash 或明文 userid。

    name+tail→'Alice#abcdef'；仅 name→'Alice'；仅 hash（unban by userid）→
    '#abcdef'；皆无（announce/save 等无目标写命令）→ ''。
    """
    tail = target_hash[-_AUDIT_HASH_TAIL:] if isinstance(target_hash, str) and target_hash else ""
    nm = name if isinstance(name, str) and name else ""
    if nm and tail:
        return f"{nm}#{tail}"
    if nm:
        return nm
    if tail:
        return f"#{tail}"
    return ""


def audit_rows(rows: list) -> list[dict]:
    """把仓库审计行（list_audit 的 9 列 dict，已 ts DESC）整形为白名单行。

    红线：target 只露角色名 + hash 末段，绝不含完整 hash / 明文 userid / 凭证。
    """
    out: list[dict] = []
    for r in rows:
        ts = r.get("ts")
        out.append({
            "ts": ts,                                  # 原始 epoch，供前端排序/本地化
            "time": _fmt_audit_ts(ts),                 # 可读 UTC
            "action": r.get("action"),
            "server": r.get("server_name"),
            "admin": r.get("admin_id"),
            "target": _audit_target(r.get("target_name"), r.get("target_hash")),
            "success": bool(r.get("success")),
            "error": r.get("error"),
        })
    return out
