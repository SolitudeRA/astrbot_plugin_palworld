"""插件页面配置读写的同步纯函数：脱敏读 / 校验回填 / 状态行。

红线：password/value 明文与 env 值绝不出现在任何返回；回填按稳定
__row_id；错误只含字段路径不含值。全部无 IO/无 await，可脱离 AstrBot 单测。
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from urllib.parse import urlsplit

_LIST_SECTIONS = ("servers", "custom_headers", "group_bindings")
_ROW_ID_PREFIX = {"servers": "srv", "custom_headers": "hdr", "group_bindings": "bind"}

SENTINEL = "__unchanged__"

_TOP_KEYS = {
    "servers", "routing", "group_bindings", "custom_headers",
    "polling", "world", "bases", "privacy", "history",
}
_META_KEYS = {"__row_id", "__template_key", "password_set", "value_set"}
_MAX_LIST = 200
_MAX_STR = 8 * 1024
_MAX_BODY = 256 * 1024

# 路径化语义预校验规格：enum 白名单 + 数值字段类型
_ENUMS = {
    "routing.access_mode": {"restricted", "open"},
    "privacy.mode": {"strict", "balanced", "advanced"},
    "world.locale": {"zh-CN"},
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


def _num_convertible(val, kind: str) -> bool:
    try:
        (int if kind == "int" else float)(val)
        return True
    except (TypeError, ValueError):
        return False


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
    for section in ("routing", "polling", "world", "bases", "privacy", "history"):
        if section in body and not isinstance(body[section], Mapping):
            return _err("invalid_shape")

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
                if field in it and not _num_convertible(it[field], kind):
                    return _err("invalid_field", f"servers[{i}].{field}")
        elif isinstance(node, Mapping) and field in node:
            if not _num_convertible(node[field], kind):
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


def _host_changed(old_url: str, new_url: str) -> bool:
    o, n = urlsplit(old_url), urlsplit(new_url)
    return (o.scheme, o.hostname, o.port) != (n.scheme, n.hostname, n.port)


def _strip_meta(cand: dict) -> None:
    for section in _LIST_SECTIONS:
        for it in cand.get(section, []) or []:
            if isinstance(it, dict):
                for k in list(it):
                    if k in _META_KEYS:
                        it.pop(k, None)
