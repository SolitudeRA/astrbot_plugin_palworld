"""插件页面配置读写的同步纯函数：脱敏读 / 校验回填 / 状态行。

红线：password/value 明文与 env 值绝不出现在任何返回；回填按稳定
__row_id；错误只含字段路径不含值。全部无 IO/无 await，可脱离 AstrBot 单测。
"""
from __future__ import annotations

import copy
from collections.abc import Mapping

_LIST_SECTIONS = ("servers", "custom_headers", "group_bindings")
_ROW_ID_PREFIX = {"servers": "srv", "custom_headers": "hdr", "group_bindings": "bind"}


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
