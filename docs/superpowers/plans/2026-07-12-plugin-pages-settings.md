# 插件页面（设置 + 状态）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让插件通过 AstrBot Plugin Pages 在 WebUI 侧栏提供设置编辑与只读状态面板，保存后自重启容器生效。

**Architecture:** 同步纯函数模块 `config_view.py`（脱敏读/校验回填/状态行）承载全部逻辑与红线，可脱离 AstrBot 单测；`web_api.py` 做 async 编排（副作用注入）；`main.py` 注册三条 HTTP 路由、持有重启标志并守卫聊天命令；`pages/settings/` 原生 JS 前端经 bridge 调用。规格：`docs/superpowers/specs/2026-07-12-plugin-pages-settings-design.md`（已三视角对抗式复核，遇歧义以规格为准）。

**Tech Stack:** Python 3.11、Quart 兼容风格 handler、aiohttp、原生 JS ES Modules、pytest（asyncio auto）

## Global Constraints

- 测试命令用 `.venv/Scripts/python.exe -m pytest`（裸 `python` 不可用）；收尾三绿：`pytest -q` + `ruff check .` + `mypy`
- **commit message 不含任何 AI/Claude 署名、提及或 Co-Authored-By 尾行**（用户硬性要求）
- **错误通道**：所有预期内结果（成功与业务失败）一律 **HTTP 200 + JSON**，用 `ok` 字段区分；响应体顶层键**禁止**用 `status` 或 `data`（平台保留键）
- **脱敏红线**：password/value 明文、env 值绝不进任何响应/错误/日志/DOM；禁止 `str(exc)` 出站；禁止记录回填后的候选配置（含明文）
- **凭证重定向防护**：server `base_url` 的 scheme/host 变更且秘密为哨兵 → 拒绝复用旧秘密
- **回填按稳定 `__row_id`**（服务端注入），不按 name/索引
- **哨兵保留字**：`"__unchanged__"` = 保留旧秘密
- **XSS**：前端所有配置派生/游戏服务器派生字符串用 `textContent`/`createTextNode`，严禁 `innerHTML` 拼接
- `metadata.yaml` 版本声明不变（`>=4.10.4`）；`hasattr(context,"register_web_api")` 仅作 stub 护栏，不作版本判断
- 上限常量：`MIN_SAVE_INTERVAL=5`（秒）、body ≤ 256 KiB、每列表 ≤ 200 项、每字符串 ≤ 8 KiB

## 现有接口速览（实现者据此接线，勿臆造）

- `parse_config(raw: Mapping, env: Mapping) -> AppConfig`（`palchronicle/config.py`）；宽容语义，产出 `AppConfig.skipped`（`SkippedServer(raw_name,reason)`）、`skipped_headers`（`SkippedHeader(raw_name,reason)`）
- `_conf_schema.json` 顶层键：`servers`(template_list)、`routing`、`group_bindings`(template_list)、`custom_headers`(template_list)、`polling`、`world`、`bases`、`privacy`、`history`
- `ServerConfig` 字段：server_id,name,enabled,base_url,username,password,timeout,verify_tls,timezone,headers
- `Container`（`palchronicle/container.py`）：`await start()` / `await stop()`（stop 各步有 None 检查但**无 try/finally**——本计划 Task 5 会加固）；暴露 `container.config`(AppConfig)、`container.query`(QueryService)、`container.repo`(Repository)
- `QueryService.status(world: World) -> StatusDTO`；`StatusDTO` 有 `online:int, smoothness_label:str, degraded:bool, last_ok:int|None`（`palchronicle/presentation/dtos.py`）
- `Repository.get_current_world(server_id) -> World | None`
- `main.py`：`PalChronicle(Star)` 持有 `self._raw_config`（AstrBotConfig）、`self._container`；`initialize()` 里 `parse_config(self._raw_config, os.environ)` → `Container(...).start()`；14 个 `@pal.command` 处理器均直接 `self._container.commands.xxx(...)`（**无 None 检查**）

---

### Task 1: config_view.redact_config — 脱敏读 + 稳定 row_id

**Files:**
- Create: `palchronicle/presentation/config_view.py`
- Test: `tests/unit/config_view_redact_test.py`

**Interfaces:**
- Produces: `redact_config(raw: Mapping) -> dict`。深拷贝 raw；对 `servers`/`custom_headers`/`group_bindings` 每项注入 `__row_id`（形如 `"srv-0"`/`"hdr-0"`/`"bind-0"`，列表内唯一）；`servers[i].password`→`""`+`password_set`(bool(password)∨bool(password_env))；`custom_headers[i].value`→`""`+`value_set`(bool(value)∨bool(value_env))；env **名**保留、env **值**不读。返回结构含 `password_env`/`value_env` 原文（名非密）。

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/config_view_redact_test.py`：

```python
"""config/get 脱敏读：明文绝不出站、稳定 row_id、env 名可回显值不读。"""
from palchronicle.presentation.config_view import redact_config


def _raw():
    return {
        "servers": [
            {"name": "alpha", "base_url": "http://h:8212", "username": "admin",
             "password": "topsecret", "password_env": ""},
            {"name": "beta", "base_url": "http://h:8213", "username": "admin",
             "password": "", "password_env": "BETA_PW"},
        ],
        "custom_headers": [
            {"name": "X-Token", "value": "hdrsecret", "value_env": "", "servers": ""},
            {"name": "X-Env", "value": "", "value_env": "TOK_ENV", "servers": "alpha"},
        ],
        "group_bindings": [{"umo": "u1", "server": "alpha", "active": True}],
        "routing": {"access_mode": "restricted", "default_server": ""},
    }


def test_password_plaintext_never_in_output():
    out = redact_config(_raw())
    import json
    blob = json.dumps(out)
    assert "topsecret" not in blob
    assert "hdrsecret" not in blob
    assert out["servers"][0]["password"] == ""
    assert out["custom_headers"][0]["value"] == ""


def test_password_set_flag_true_for_plaintext_and_env():
    out = redact_config(_raw())
    assert out["servers"][0]["password_set"] is True   # 明文
    assert out["servers"][1]["password_set"] is True   # env-only
    assert out["custom_headers"][0]["value_set"] is True
    assert out["custom_headers"][1]["value_set"] is True


def test_password_set_false_when_both_empty():
    raw = _raw()
    raw["servers"][0]["password"] = ""
    raw["servers"][0]["password_env"] = ""
    out = redact_config(raw)
    assert out["servers"][0]["password_set"] is False


def test_env_name_kept_value_not_read(monkeypatch):
    monkeypatch.setenv("BETA_PW", "env-plaintext")
    out = redact_config(_raw())
    import json
    assert "env-plaintext" not in json.dumps(out)
    assert out["servers"][1]["password_env"] == "BETA_PW"


def test_row_ids_injected_and_unique():
    out = redact_config(_raw())
    assert [s["__row_id"] for s in out["servers"]] == ["srv-0", "srv-1"]
    assert [h["__row_id"] for h in out["custom_headers"]] == ["hdr-0", "hdr-1"]
    assert out["group_bindings"][0]["__row_id"] == "bind-0"


def test_does_not_mutate_input():
    raw = _raw()
    redact_config(raw)
    assert raw["servers"][0]["password"] == "topsecret"  # 原对象不被改
    assert "__row_id" not in raw["servers"][0]


def test_non_list_sections_passthrough():
    out = redact_config(_raw())
    assert out["routing"] == {"access_mode": "restricted", "default_server": ""}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_view_redact_test.py -q`
Expected: `ModuleNotFoundError: No module named 'palchronicle.presentation.config_view'`

- [ ] **Step 3: 实现 redact_config**

创建 `palchronicle/presentation/config_view.py`：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_view_redact_test.py -q`
Expected: 7 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/config_view.py tests/unit/config_view_redact_test.py
git commit -m "feat(config-view): 脱敏读配置（明文不出站、稳定 row_id、env 名可回显）"
```

---

### Task 2: config_view.validate_and_backfill — 校验/回填/凭证重定向防护

**Files:**
- Modify: `palchronicle/presentation/config_view.py`
- Test: `tests/unit/config_view_validate_test.py`

**Interfaces:**
- Consumes: 无（纯函数，参照 Task 1 同文件）
- Produces: `validate_and_backfill(body: Mapping, old_raw: Mapping, env: Mapping) -> tuple[bool, dict]`。成功 `(True, candidate)`：candidate 是可落盘的完整配置 dict，已剥离全部 schema 外键（`__row_id`/`__template_key`/`password_set`/`value_set`）、哨兵已回填。失败 `(False, err)`：`err = {"error": <code>, "detail": {...}}`，code ∈ `invalid_shape|too_large|invalid_field|credential_redirect`，detail 仅含字段路径不含值。哨兵回填按 `__row_id` 匹配 old_raw（old_raw 由 `redact_config` 之前的原始配置提供）。**导出常量**：`SENTINEL = "__unchanged__"`。
- 校验用到的 schema 顶层键集合与 enum 白名单在本任务内定义为模块常量。

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/config_view_validate_test.py`：

```python
"""config/save 校验与哨仓回填：形状/类型/白名单/体积/语义/哨兵/凭证重定向。"""
from palchronicle.presentation.config_view import SENTINEL, validate_and_backfill


def _old():
    return {
        "servers": [
            {"name": "alpha", "base_url": "http://h:8212", "username": "admin",
             "password": "oldpw", "password_env": "", "timeout": 10,
             "enabled": True, "verify_tls": True, "timezone": ""},
        ],
        "custom_headers": [
            {"name": "X-Token", "value": "oldtok", "value_env": "", "servers": ""},
        ],
        "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {"metrics_seconds": 30},
        "world": {"fps_smooth": 50},
        "bases": {}, "privacy": {"mode": "balanced"}, "history": {},
    }


def _body(**over):
    # 模拟页面回传：带 __row_id，敏感字段用哨兵
    b = {
        "servers": [{"__row_id": "srv-0", "name": "alpha",
                     "base_url": "http://h:8212", "username": "admin",
                     "password": SENTINEL, "password_env": "", "timeout": 10,
                     "enabled": True, "verify_tls": True, "timezone": "",
                     "password_set": True}],
        "custom_headers": [{"__row_id": "hdr-0", "name": "X-Token",
                            "value": SENTINEL, "value_env": "", "servers": "",
                            "value_set": True}],
        "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {"metrics_seconds": 30}, "world": {"fps_smooth": 50},
        "bases": {}, "privacy": {"mode": "balanced"}, "history": {},
    }
    b.update(over)
    return b


def test_sentinel_backfills_old_secret_and_strips_meta_keys():
    ok, cand = validate_and_backfill(_body(), _old(), {})
    assert ok is True
    s = cand["servers"][0]
    assert s["password"] == "oldpw"        # 哨兵回填旧值
    assert "__row_id" not in s and "password_set" not in s  # 元键剥离
    assert cand["custom_headers"][0]["value"] == "oldtok"


def test_explicit_new_value_overrides():
    body = _body()
    body["servers"][0]["password"] = "newpw"
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == "newpw"


def test_explicit_empty_clears_secret():
    body = _body()
    body["servers"][0]["password"] = ""
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == ""


def test_new_row_with_sentinel_rejected():
    body = _body()
    body["servers"][0]["__row_id"] = "srv-99"  # 无匹配
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "servers[0].password"


def test_reorder_or_delete_matches_by_row_id_not_index():
    # 页面删掉了原 hdr-0，新增一条排在前面；旧 hdr-0 滑到索引 1 仍按 id 回填
    body = _body()
    body["custom_headers"] = [
        {"__row_id": None, "name": "X-New", "value": "brand", "value_env": "",
         "servers": "", "value_set": False},
        {"__row_id": "hdr-0", "name": "X-Token", "value": SENTINEL,
         "value_env": "", "servers": "", "value_set": True},
    ]
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok
    assert cand["custom_headers"][0]["value"] == "brand"
    assert cand["custom_headers"][1]["value"] == "oldtok"  # 按 id 不错绑


def test_credential_redirect_blocked_on_base_url_host_change():
    body = _body()
    body["servers"][0]["base_url"] = "http://attacker.example:8212"  # host 变
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "credential_redirect"
    assert err["detail"]["path"] == "servers[0].password"


def test_base_url_path_only_change_with_sentinel_ok():
    body = _body()
    body["servers"][0]["base_url"] = "http://h:8212/prefix"  # host 不变
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == "oldpw"


def test_top_level_unknown_key_rejected():
    body = _body(evil="x")
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"


def test_list_item_not_dict_rejected_no_crash():
    body = _body()
    body["servers"] = [123]
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"


def test_enum_invalid_value_rejected_path_only_no_value():
    body = _body()
    body["routing"]["access_mode"] = "wideopen"
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "routing.access_mode"
    assert "wideopen" not in str(err)   # 非法值绝不出现在错误里


def test_int_field_not_convertible_rejected_path_only():
    body = _body()
    body["servers"][0]["timeout"] = "abc"
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "servers[0].timeout"
    assert "abc" not in str(err)


def test_body_too_large_rejected():
    body = _body()
    body["custom_headers"] = [
        {"__row_id": None, "name": f"X-{i}", "value": "v", "value_env": "",
         "servers": "", "value_set": False} for i in range(201)
    ]
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "too_large"


def test_unmatched_server_name_sentinel_rejected():
    # 改名 alpha→alpha2 且密码哨兵：__row_id 仍匹配旧条目，但用户想保留旧密码
    # 合法（id 匹配）；此用例验证「无 id 匹配才拒」已由 test_new_row 覆盖，
    # 这里验证改名但 id 命中时按 id 正常回填
    body = _body()
    body["servers"][0]["name"] = "alpha2"
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == "oldpw"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_view_validate_test.py -q`
Expected: `ImportError: cannot import name 'SENTINEL'`

- [ ] **Step 3: 实现 validate_and_backfill**

在 `palchronicle/presentation/config_view.py` 追加：

```python
from urllib.parse import urlsplit

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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_view_validate_test.py -q`
Expected: 13 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/config_view.py tests/unit/config_view_validate_test.py
git commit -m "feat(config-view): 保存校验与哨兵回填（形状/语义/凭证重定向/元键剥离）"
```

---

### Task 3: config_view.status_rows — 状态行白名单

**Files:**
- Modify: `palchronicle/presentation/config_view.py`
- Test: `tests/unit/config_view_status_test.py`

**Interfaces:**
- Produces: `status_rows(entries: list) -> list[dict]`。入参每项是 `(name: str, ready: bool, dto)`，`dto` 为 `StatusDTO` 或 `None`。dto 非 None → `{name, ready, online, smoothness_label, degraded, last_ok}`；dto None → `{name, ready}` 骨架行。白名单输出，**绝不**含 base_url/password/umo。

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/config_view_status_test.py`：

```python
"""status/overview 行组装：实名字段 + 白名单 + world=None 骨架。"""
from palchronicle.presentation.config_view import status_rows
from palchronicle.presentation.dtos import StatusDTO


def _dto():
    return StatusDTO(
        server_name="alpha", world_name="alpha", world_day=3, online=5,
        max_players=32, basecamp_count=2, fps=55.0, frame_time=18.0,
        smoothness_label="流畅", players=[], peak_online_today=7,
        updated_at=1000, degraded=False, last_ok=999,
    )


def test_ready_server_row_whitelisted_fields():
    rows = status_rows([("alpha", True, _dto())])
    assert rows == [{
        "name": "alpha", "ready": True, "online": 5,
        "smoothness_label": "流畅", "degraded": False, "last_ok": 999,
    }]


def test_no_world_yields_skeleton():
    rows = status_rows([("beta", False, None)])
    assert rows == [{"name": "beta", "ready": False}]


def test_no_leak_of_sensitive_keys():
    rows = status_rows([("alpha", True, _dto())])
    for row in rows:
        assert not {"base_url", "password", "umo", "players"} & set(row)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_view_status_test.py -q`
Expected: `ImportError: cannot import name 'status_rows'`

- [ ] **Step 3: 实现 status_rows**

在 `palchronicle/presentation/config_view.py` 追加：

```python
def status_rows(entries: list) -> list[dict]:
    """把 (name, ready, StatusDTO|None) 组装为白名单状态行。"""
    rows: list[dict] = []
    for name, ready, dto in entries:
        if dto is None:
            rows.append({"name": name, "ready": ready})
            continue
        rows.append({
            "name": name, "ready": ready, "online": dto.online,
            "smoothness_label": dto.smoothness_label,
            "degraded": dto.degraded, "last_ok": dto.last_ok,
        })
    return rows
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_view_status_test.py -q`
Expected: 3 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/config_view.py tests/unit/config_view_status_test.py
git commit -m "feat(config-view): status_rows 白名单状态行（实名字段 + world=None 骨架）"
```

---

### Task 4: web_api — config_get + status_overview 编排

**Files:**
- Create: `palchronicle/presentation/web_api.py`
- Test: `tests/unit/web_api_read_test.py`

**Interfaces:**
- Consumes: `redact_config`（Task 1）、`status_rows`（Task 3）
- Produces:
  - `async def handle_config_get(get_raw) -> tuple[int, dict]`：`get_raw()` 返回当前 raw 配置 Mapping；返回 `(200, {"ok": True, "config": <redacted>, "page_version": 1})`
  - `async def handle_status_overview(container, restarting: bool) -> tuple[int, dict]`：`restarting` 或 `container is None` → `(200, {"ok": True, "servers": [], "restarting": True})`；否则遍历 `container.config.servers`，对每个 `s` 用 `await container.repo.get_current_world(s.server_id)` 取 world，world 非 None 再 `await container.query.status(world)` 取 dto（None 则骨架），返回 `(200, {"ok": True, "servers": status_rows(entries)})`
- 两个 handler 均返回 `(status_code, payload)` 二元组，HTTP 状态恒 200（Quart 壳负责 jsonify）

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/web_api_read_test.py`：

```python
"""config/get 与 status/overview 编排：脱敏下发、重启窗口、按服务器组装。"""
from palchronicle.presentation.web_api import handle_config_get, handle_status_overview
from palchronicle.presentation.dtos import StatusDTO


async def test_config_get_returns_redacted():
    raw = {"servers": [{"name": "a", "password": "secret", "password_env": "",
                        "base_url": "http://h", "username": "admin"}]}
    code, payload = await handle_config_get(lambda: raw)
    assert code == 200 and payload["ok"] is True
    import json
    assert "secret" not in json.dumps(payload)
    assert payload["config"]["servers"][0]["__row_id"] == "srv-0"
    assert payload["page_version"] == 1


class _Server:
    def __init__(self, name):
        self.name = name
        self.server_id = name
        self.ready = True


class _Repo:
    def __init__(self, worlds):
        self._worlds = worlds

    async def get_current_world(self, sid):
        return self._worlds.get(sid)


class _Query:
    def __init__(self, dto):
        self._dto = dto

    async def status(self, world):
        return self._dto


class _Cfg:
    def __init__(self, servers):
        self.servers = servers


class _Container:
    def __init__(self, servers, worlds, dto):
        self.config = _Cfg(servers)
        self.repo = _Repo(worlds)
        self.query = _Query(dto)


def _dto():
    return StatusDTO(server_name="a", world_name="a", world_day=1, online=4,
                     max_players=32, basecamp_count=0, fps=55.0, frame_time=18.0,
                     smoothness_label="流畅", players=[], peak_online_today=4,
                     updated_at=1, degraded=False, last_ok=9)


async def test_status_overview_restarting_returns_empty():
    code, payload = await handle_status_overview(None, restarting=True)
    assert code == 200 and payload["restarting"] is True and payload["servers"] == []


async def test_status_overview_none_container():
    code, payload = await handle_status_overview(None, restarting=False)
    assert payload["restarting"] is True and payload["servers"] == []


async def test_status_overview_assembles_rows():
    c = _Container([_Server("a")], {"a": object()}, _dto())
    code, payload = await handle_status_overview(c, restarting=False)
    assert code == 200 and payload["ok"] is True
    assert payload["servers"] == [{"name": "a", "ready": True, "online": 4,
                                   "smoothness_label": "流畅", "degraded": False,
                                   "last_ok": 9}]


async def test_status_overview_world_none_skeleton():
    c = _Container([_Server("a")], {}, _dto())  # 无 world
    code, payload = await handle_status_overview(c, restarting=False)
    assert payload["servers"] == [{"name": "a", "ready": True}]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/web_api_read_test.py -q`
Expected: `ModuleNotFoundError: No module named 'palchronicle.presentation.web_api'`

- [ ] **Step 3: 实现**

创建 `palchronicle/presentation/web_api.py`：

```python
"""插件页面 HTTP 端点的 async 编排：副作用（save/stop/start/锁）经参数注入，
返回 (status_code, payload)。业务成败一律 HTTP 200，用 payload['ok'] 区分。"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from .config_view import redact_config, status_rows


async def handle_config_get(get_raw: Callable[[], Mapping]) -> tuple[int, dict]:
    return 200, {"ok": True, "config": redact_config(get_raw()), "page_version": 1}


async def handle_status_overview(container, restarting: bool) -> tuple[int, dict]:
    if restarting or container is None:
        return 200, {"ok": True, "servers": [], "restarting": True}
    entries = []
    for s in container.config.servers:
        world = await container.repo.get_current_world(s.server_id)
        dto = await container.query.status(world) if world is not None else None
        entries.append((s.name, s.ready, dto))
    return 200, {"ok": True, "servers": status_rows(entries)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/web_api_read_test.py -q`
Expected: 5 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/web_api.py tests/unit/web_api_read_test.py
git commit -m "feat(web-api): config/get 与 status/overview 编排（脱敏下发/重启窗口/按服务器组装）"
```

---

### Task 5: web_api — config_save 编排（锁/频率/重启/回滚）

**Files:**
- Modify: `palchronicle/presentation/web_api.py`
- Test: `tests/unit/web_api_save_test.py`

**Interfaces:**
- Consumes: `validate_and_backfill`（Task 2）
- Produces：

```python
async def handle_config_save(
    body, *, old_raw, env, lock, now, last_save_ts,
    apply_and_restart, min_interval=5,
) -> tuple[int, dict]
```

  - `lock`: `asyncio.Lock`（注入，避免模块全局污染测试）
  - `now`: float（当前单调时刻，注入便于测试）
  - `last_save_ts`: float | None（上次成功保存时刻，注入）
  - `apply_and_restart(candidate) -> Awaitable[dict]`：注入的落盘+重启回调，成功返回 `{"ok": True, "warnings": {...}}`，失败返回 `{"ok": False, "error": <code>}`（回调内部负责深拷贝旧配置、先 stop 失败容器、回滚——见下方 main.py Task 6 的 `_apply_and_restart`）。web_api 只负责锁/频率/校验的编排，不碰容器细节
  - 返回值第二元素总带 `ok`；成功时还带 `warnings` 与更新后的 `saved_ts`（供 main.py 记 last_save_ts）
- 语义：
  1. `lock.locked()` → `(200, {"ok": False, "error": "save_in_progress"})`
  2. `last_save_ts` 非 None 且 `now - last_save_ts < min_interval` → `too_frequent`
  3. `async with lock:` 内 `validate_and_backfill`，失败原样返回 err（补 `ok: False`）
  4. 成功 → `await apply_and_restart(candidate)`；把结果透传，成功时附 `saved_ts: now`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/web_api_save_test.py`：

```python
"""config/save 编排：锁 409、频率限制、校验失败、重启回调透传。"""
import asyncio

from palchronicle.presentation.web_api import handle_config_save

_OLD = {
    "servers": [{"name": "a", "base_url": "http://h", "username": "admin",
                 "password": "oldpw", "password_env": "", "timeout": 10,
                 "enabled": True, "verify_tls": True, "timezone": ""}],
    "custom_headers": [], "group_bindings": [],
    "routing": {"access_mode": "restricted", "default_server": ""},
    "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
    "history": {},
}


def _body():
    return {
        "servers": [{"__row_id": "srv-0", "name": "a", "base_url": "http://h",
                     "username": "admin", "password": "__unchanged__",
                     "password_env": "", "timeout": 10, "enabled": True,
                     "verify_tls": True, "timezone": "", "password_set": True}],
        "custom_headers": [], "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {},
    }


async def _ok_restart(cand):
    return {"ok": True, "warnings": {"skipped_servers": [], "skipped_headers": []}}


async def test_lock_busy_returns_save_in_progress():
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_config_save(
            _body(), old_raw=_OLD, env={}, lock=lock, now=100.0,
            last_save_ts=None, apply_and_restart=_ok_restart)
        assert code == 200 and p["error"] == "save_in_progress"
    finally:
        lock.release()


async def test_too_frequent():
    code, p = await handle_config_save(
        _body(), old_raw=_OLD, env={}, lock=asyncio.Lock(), now=102.0,
        last_save_ts=100.0, apply_and_restart=_ok_restart)
    assert p["error"] == "too_frequent"


async def test_validation_failure_does_not_restart():
    called = False

    async def spy(cand):
        nonlocal called
        called = True
        return {"ok": True}

    body = _body()
    body["routing"]["access_mode"] = "bad"
    code, p = await handle_config_save(
        body, old_raw=_OLD, env={}, lock=asyncio.Lock(), now=200.0,
        last_save_ts=None, apply_and_restart=spy)
    assert p["ok"] is False and p["error"] == "invalid_field"
    assert called is False   # 校验失败不触发重启


async def test_success_passes_warnings_and_saved_ts():
    code, p = await handle_config_save(
        _body(), old_raw=_OLD, env={}, lock=asyncio.Lock(), now=300.0,
        last_save_ts=None, apply_and_restart=_ok_restart)
    assert code == 200 and p["ok"] is True
    assert p["saved_ts"] == 300.0
    assert p["warnings"] == {"skipped_servers": [], "skipped_headers": []}


async def test_lock_released_after_success():
    lock = asyncio.Lock()
    await handle_config_save(_body(), old_raw=_OLD, env={}, lock=lock, now=1.0,
                             last_save_ts=None, apply_and_restart=_ok_restart)
    assert not lock.locked()   # async with 已释放


async def test_restart_failure_propagated():
    async def boom(cand):
        return {"ok": False, "error": "restart_failed_rolled_back"}

    code, p = await handle_config_save(
        _body(), old_raw=_OLD, env={}, lock=asyncio.Lock(), now=400.0,
        last_save_ts=None, apply_and_restart=boom)
    assert p["ok"] is False and p["error"] == "restart_failed_rolled_back"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/web_api_save_test.py -q`
Expected: `ImportError: cannot import name 'handle_config_save'`

- [ ] **Step 3: 实现**

在 `palchronicle/presentation/web_api.py` 追加（顶部 import 补 `validate_and_backfill`）：

```python
# 顶部 import 改为：
# from .config_view import redact_config, status_rows, validate_and_backfill

async def handle_config_save(
    body, *, old_raw, env, lock, now, last_save_ts,
    apply_and_restart, min_interval: float = 5,
) -> tuple[int, dict]:
    if lock.locked():
        return 200, {"ok": False, "error": "save_in_progress", "detail": {}}
    if last_save_ts is not None and now - last_save_ts < min_interval:
        return 200, {"ok": False, "error": "too_frequent", "detail": {}}
    async with lock:
        ok, result = validate_and_backfill(body, old_raw, env)
        if not ok:
            return 200, {"ok": False, **result}
        outcome = await apply_and_restart(result)
        if not outcome.get("ok"):
            return 200, outcome
        return 200, {"ok": True, "warnings": outcome.get("warnings", {}),
                     "saved_ts": now}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/web_api_save_test.py -q`
Expected: 6 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/web_api.py tests/unit/web_api_save_test.py
git commit -m "feat(web-api): config/save 编排（并发锁/频率限制/校验/重启回调透传）"
```

---

### Task 6: Container.stop 加固 + main.py 接线（注册/重启回调/命令守卫）

**Files:**
- Modify: `palchronicle/container.py`（`stop()` 加 try/finally）
- Modify: `main.py`（注册路由、重启状态、`_apply_and_restart`、Quart 壳、14 命令守卫）
- Test: `tests/unit/container_stop_test.py`、`tests/unit/main_web_test.py`

**Interfaces:**
- Consumes: `web_api.handle_config_get/handle_config_save/handle_status_overview`（Task 4/5）
- Produces:
  - `Container.stop()` 异常安全：即便 scheduler/client 关闭抛错，`db.close()` 仍执行且 `_db=None`
  - `main.py` `PalChronicle`：新增 `self._restarting`(bool)、`self._save_lock`(asyncio.Lock)、`self._last_save_ts`(float|None)、`self._busy_msg()->str|None`、`async _apply_and_restart(candidate)->dict`、`_build_container(cfg)->Container`（工厂，便于测试注入）
  - 14 个 `@pal.command` 处理器开头统一 `if (m := self._busy_msg()): yield event.plain_result(m); return`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/container_stop_test.py`：

```python
"""Container.stop 异常安全：client.close 抛错也必须关闭 DB。"""
from pathlib import Path

from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.container import Container
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock


def _cfg():
    return AppConfig(
        servers=[ServerConfig("a", "a", True, "http://127.0.0.1:8212", "admin",
                              "pw", 10, True, "")],
        skipped=[], routing=RoutingConfig(AccessMode.RESTRICTED, ""),
        group_bindings=[], polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


class _BoomRest:
    async def close(self):
        raise RuntimeError("close failed")


class _FakeSched:
    async def start(self): ...
    async def stop(self): ...


async def test_stop_closes_db_even_if_client_close_raises(tmp_path: Path):
    c = Container(_cfg(), tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _BoomRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    # client.close 抛错，但 db 仍应被关闭并置空
    try:
        await c.stop()
    except RuntimeError:
        pass
    assert c._db is None
```

创建 `tests/unit/main_web_test.py`：

```python
"""main.py 插件页面接线：命令守卫在重启窗口拦截、web api handler 注册。"""
from pathlib import Path


class _FakeContext:
    def __init__(self):
        self.registered = []

    def register_web_api(self, route, handler, methods, desc):
        self.registered.append((route, tuple(methods)))


class _Event:
    unified_msg_origin = "u1"
    message_str = ""
    role = "admin"

    def plain_result(self, text):
        return text

    def is_private_chat(self):
        return False


async def _collect(agen):
    out = []
    async for x in agen:
        out.append(x)
    return out


def _raw():
    return {
        "servers": [], "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {},
    }


async def test_command_guarded_during_restart():
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    plugin._restarting = True
    out = await _collect(plugin.status(_Event()))
    assert len(out) == 1 and "重载" in out[0]  # 未触达 None 容器


async def test_command_guarded_when_container_none():
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    plugin._container = None
    plugin._restarting = False
    out = await _collect(plugin.online(_Event()))
    assert len(out) == 1 and "重载" in out[0]


def test_register_web_api_called_with_prefixed_routes():
    import main as main_mod
    ctx = _FakeContext()
    plugin = main_mod.PalChronicle(ctx, _raw())
    plugin._register_web_api()
    routes = {r for r, _ in ctx.registered}
    assert "/astrbot_plugin_palword/config/get" in routes
    assert "/astrbot_plugin_palword/config/save" in routes
    assert "/astrbot_plugin_palword/status/overview" in routes


def test_no_register_when_context_lacks_method():
    import main as main_mod

    class _Bare:
        pass

    plugin = main_mod.PalChronicle(_Bare(), _raw())
    # 不应抛异常（stub 护栏）
    plugin._maybe_register_web_api()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/container_stop_test.py tests/unit/main_web_test.py -q`
Expected: container_stop 断言失败（`_db` 未置 None）；main_web 报 `AttributeError`（`_restarting`/`_register_web_api` 不存在）

- [ ] **Step 3a: 加固 Container.stop**

`palchronicle/container.py` 的 `stop()`（现约 150-158 行）替换为：

```python
    async def stop(self) -> None:
        try:
            if self._scheduler is not None:
                await self._scheduler.stop()
            for client in self._rest_clients.values():
                await client.close()
            self._rest_clients.clear()
        finally:
            if self._db is not None:
                await self._db.close()
                self._db = None
```

- [ ] **Step 3b: main.py 接线**

`main.py` 顶部 import 补 `import asyncio`、`import copy` 与
`from palchronicle.presentation import web_api`。

`__init__` 末尾补状态：

```python
        self._restarting = False
        self._save_lock = asyncio.Lock()
        self._last_save_ts: float | None = None
```

`initialize()` 末尾（`await self._container.start()` 之后）补：

```python
        self._maybe_register_web_api()
```

新增方法（放在 `terminate` 之后、命令区之前）：

```python
    def _maybe_register_web_api(self) -> None:
        # hasattr 仅作测试 stub 护栏，不是版本判断（真实 AstrBot 恒有此方法）
        if hasattr(self._context, "register_web_api"):
            self._register_web_api()

    def _register_web_api(self) -> None:
        p = "/astrbot_plugin_palword"
        self._context.register_web_api(
            f"{p}/config/get", self._web_config_get, ["GET"], "读取插件配置(脱敏)")
        self._context.register_web_api(
            f"{p}/config/save", self._web_config_save, ["POST"], "保存插件配置并重启")
        self._context.register_web_api(
            f"{p}/status/overview", self._web_status, ["GET"], "服务器状态概览")

    def _busy_msg(self) -> str | None:
        if self._restarting or self._container is None:
            return "插件正在重载配置，请稍后重试"
        return None

    def _build_container(self, cfg):
        return Container(cfg, _resolve_data_dir(), SystemClock())

    async def _apply_and_restart(self, candidate: dict) -> dict:
        old_raw = copy.deepcopy(dict(self._raw_config))
        self._restarting = True
        try:
            for k, v in candidate.items():
                self._raw_config[k] = v
            if hasattr(self._raw_config, "save_config"):
                self._raw_config.save_config()
            new_cfg = parse_config(self._raw_config, os.environ)
            if self._container is not None:
                await self._container.stop()
            new_container = self._build_container(new_cfg)
            await new_container.start()
            self._container = new_container
            return {"ok": True, "warnings": {
                "skipped_servers": [{"raw_name": s.raw_name, "reason": s.reason}
                                    for s in new_cfg.skipped],
                "skipped_headers": [{"raw_name": h.raw_name, "reason": h.reason}
                                    for h in new_cfg.skipped_headers],
            }}
        except Exception:  # noqa: BLE001 — 脱敏：不外传异常文本
            return await self._rollback(old_raw)
        finally:
            self._restarting = False

    async def _rollback(self, old_raw: dict) -> dict:
        try:
            # 先回收可能半启动的新容器
            if self._container is not None:
                try:
                    await self._container.stop()
                except Exception:  # noqa: BLE001
                    pass
            for k in list(self._raw_config.keys()):
                self._raw_config[k] = old_raw.get(k)
            if hasattr(self._raw_config, "save_config"):
                self._raw_config.save_config()
            old_cfg = parse_config(self._raw_config, os.environ)
            restored = self._build_container(old_cfg)
            await restored.start()
            self._container = restored
            return {"ok": False, "error": "restart_failed_rolled_back", "detail": {}}
        except Exception:  # noqa: BLE001
            self._container = None
            return {"ok": False, "error": "restart_failed", "detail": {}}

    # ---- Quart 薄壳：解包 request → web_api → jsonify（业务成败恒 HTTP 200）----
    async def _web_config_get(self):
        from quart import jsonify
        _code, payload = await web_api.handle_config_get(lambda: self._raw_config)
        return jsonify(payload)

    async def _web_status(self):
        from quart import jsonify
        _code, payload = await web_api.handle_status_overview(
            self._container, self._restarting)
        return jsonify(payload)

    async def _web_config_save(self):
        import time

        from quart import jsonify, request
        body = await request.get_json(silent=True)
        _code, payload = await web_api.handle_config_save(
            body, old_raw=self._raw_config, env=os.environ,
            lock=self._save_lock, now=time.monotonic(),
            last_save_ts=self._last_save_ts,
            apply_and_restart=self._apply_and_restart)
        if payload.get("ok") and "saved_ts" in payload:
            self._last_save_ts = payload.pop("saved_ts")
        return jsonify(payload)
```

14 个命令处理器（`status`/`online`/`world`/`rules`/`guilds`/`guild`/`bases`/
`base`/`events`/`today`/`servers`/`use`/`unbind`，以及 `help`）每个函数体首行插入
守卫。以 `status` 为例：

```python
    @pal.command("status")
    async def status(self, event):
        if (m := self._busy_msg()):
            yield event.plain_result(m)
            return
        yield event.plain_result(
            await self._container.commands.status(self._umo(event), self._msg(event), self._is_group(event))
        )
```

`help` 同样是 async generator（`yield`）且调用 `self._container.commands.help(...)`，
故同款插入首行 `_busy_msg()` 守卫。其余 12 个命令逐一插入首行守卫。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/container_stop_test.py tests/unit/main_web_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿（既有 main_test 的 initialize/terminate 不受影响——`_FakeContext` 无 `register_web_api` 故走护栏跳过）

- [ ] **Step 6: Commit**

```bash
git add palchronicle/container.py main.py tests/unit/container_stop_test.py tests/unit/main_web_test.py
git commit -m "feat(main): 注册插件页面端点 + 自重启容器（回滚/命令守卫）；Container.stop 异常安全"
```

---

### Task 7: 前端页面 pages/settings/

**Files:**
- Create: `pages/settings/index.html`、`pages/settings/app.js`、`pages/settings/settings.js`、`pages/settings/status.js`、`pages/settings/style.css`
- Test: `tests/unit/pages_static_test.py`

**Interfaces:**
- Consumes: bridge 端点 `config/get`、`config/save`、`status/overview`（Task 4/5 契约）
- Produces: 静态页面资源（AstrBot ≥4.24.1 自动扫描 `pages/settings/index.html`）

**范围说明（YAGNI + 避免清空 bug）**：设置表单可视化编辑 **servers** 与
**custom_headers** 两个含敏感字段/需增删的列表（两者的 password/value 走哨兵
逻辑——**custom_headers 的 value 被 config/get 脱敏为 `""`，若不带哨兵原样回传
会被后端判为「清空」，故必须建卡片走哨兵**）。routing/polling/world/bases/
privacy/history 等无敏感字段的 object 节本期**原样透传保留原值**（不在此页做可视化
编辑，用户仍可用 AstrBot 原生 schema 配置页编辑它们——官方定位互补）；group_bindings
原样透传（其 `__row_id` 由后端剥离）。

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/pages_static_test.py`：

```python
"""插件页面静态结构：文件齐全、脚本为 module、无 innerHTML/明文回显。"""
import re
from pathlib import Path

PAGES = Path(__file__).resolve().parents[2] / "pages" / "settings"


def test_index_and_assets_exist():
    for f in ("index.html", "app.js", "settings.js", "status.js", "style.css"):
        assert (PAGES / f).exists(), f"缺少 {f}"


def test_scripts_are_module_type():
    html = (PAGES / "index.html").read_text(encoding="utf-8")
    for m in re.findall(r"<script\b[^>]*>", html):
        if "src=" in m:
            assert 'type="module"' in m, f"外部脚本须为 module: {m}"


def test_no_innerhtml_in_js():
    # XSS 红线：外部/配置派生字符串一律 textContent，禁止 innerHTML 赋值
    for f in ("app.js", "settings.js", "status.js"):
        src = (PAGES / f).read_text(encoding="utf-8")
        assert ".innerHTML" not in src, f"{f} 不得使用 innerHTML"


def test_sentinel_constant_present():
    src = (PAGES / "settings.js").read_text(encoding="utf-8")
    assert "__unchanged__" in src  # 哨兵保留字用于未改动的敏感字段


def test_custom_headers_handled_to_avoid_clearing():
    # custom_headers.value 被 config/get 脱敏为空；settings.js 必须显式处理
    # （建卡片走哨兵），否则原样回传会清空所有请求头值
    src = (PAGES / "settings.js").read_text(encoding="utf-8")
    assert "custom_headers" in src
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/pages_static_test.py -q`
Expected: `test_index_and_assets_exist` FAIL（文件不存在）

- [ ] **Step 3: 实现页面**

创建 `pages/settings/index.html`：

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="./style.css">
  <title>PalChronicle 设置</title>
</head>
<body>
  <nav class="tabs">
    <button id="tab-settings" class="active">设置</button>
    <button id="tab-status">状态</button>
  </nav>
  <main>
    <section id="panel-settings"></section>
    <section id="panel-status" hidden></section>
  </main>
  <div id="toast" hidden></div>
  <script type="module" src="./app.js"></script>
</body>
</html>
```

创建 `pages/settings/style.css`：

```css
:root { --bg:#fff; --fg:#222; --card:#f5f5f5; --accent:#3b82f6; }
[data-theme="dark"] { --bg:#1e1e1e; --fg:#e5e5e5; --card:#2a2a2a; --accent:#60a5fa; }
body { background:var(--bg); color:var(--fg); font-family:system-ui,sans-serif; margin:0; padding:1rem; }
.tabs button { background:none; border:none; color:var(--fg); font-size:1rem; padding:.5rem 1rem; cursor:pointer; opacity:.6; }
.tabs button.active { opacity:1; border-bottom:2px solid var(--accent); }
.card { background:var(--card); border-radius:8px; padding:1rem; margin:.5rem 0; }
label { display:block; margin:.4rem 0 .1rem; font-size:.85rem; opacity:.8; }
input, select { width:100%; box-sizing:border-box; padding:.4rem; }
button.primary { background:var(--accent); color:#fff; border:none; border-radius:6px; padding:.5rem 1rem; cursor:pointer; }
#toast { position:fixed; bottom:1rem; left:50%; transform:translateX(-50%); background:var(--card); padding:.6rem 1rem; border-radius:6px; }
```

创建 `pages/settings/app.js`：

```js
// 入口：bridge 就绪 → tab 路由 → 挂载设置/状态模块。
// 主题由 SDK 依 isDark 自动维护 <html data-theme>，此处不重复设置。
import { mountSettings } from "./settings.js";
import { mountStatus } from "./status.js";

const bridge = window.AstrBotPluginPage;

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;            // textContent：不注入 HTML
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 3000);
}

function setupTabs() {
  const ts = document.getElementById("tab-settings");
  const tt = document.getElementById("tab-status");
  const ps = document.getElementById("panel-settings");
  const pt = document.getElementById("panel-status");
  ts.onclick = () => { ts.classList.add("active"); tt.classList.remove("active"); ps.hidden = false; pt.hidden = true; };
  tt.onclick = () => { tt.classList.add("active"); ts.classList.remove("active"); pt.hidden = false; ps.hidden = true; mountStatus(bridge, pt, toast); };
}

async function main() {
  if (bridge && bridge.ready) { await bridge.ready(); }
  setupTabs();
  mountSettings(bridge, document.getElementById("panel-settings"), toast);
}

main();
```

创建 `pages/settings/settings.js`：

```js
// 设置表单：拉取脱敏配置 → 渲染可增删卡片与分组 → 收集提交。
// 一切外部字符串经 textContent/value 写入，绝不用 innerHTML。
const SENTINEL = "__unchanged__";

function el(tag, props = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") n.textContent = v;         // 安全文本
    else if (k === "value") n.value = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) n.appendChild(c);
  return n;
}

function field(label, value, opts = {}) {
  const wrap = el("div");
  wrap.appendChild(el("label", { text: label }));
  const input = el("input", { value: value ?? "" });
  if (opts.type) input.type = opts.type;
  if (opts.placeholder) input.placeholder = opts.placeholder;
  if (opts.dataset) input.dataset.key = opts.dataset;
  wrap.appendChild(input);
  return { wrap, input };
}

function serverCard(s) {
  const card = el("div", { class: "card" });
  card.dataset.rowId = s.__row_id ?? "";
  const inputs = {};
  for (const key of ["name", "base_url", "username", "timeout", "timezone", "password_env"]) {
    const f = field(key, s[key]);
    inputs[key] = f.input; card.appendChild(f.wrap);
  }
  // 密码：不预填明文；据 password_set 显示占位
  const pf = field("password", "", {
    type: "password",
    placeholder: s.password_set ? "已设置（留空保持不变）" : "未设置",
  });
  inputs.password = pf.input; card.appendChild(pf.wrap);
  card._collect = () => {
    const out = { __row_id: card.dataset.rowId || null };
    for (const [k, inp] of Object.entries(inputs)) {
      if (k === "password") out.password = inp.value === "" ? SENTINEL : inp.value;
      else if (k === "timeout") out.timeout = inp.value;
      else out[k] = inp.value;
    }
    return out;
  };
  return card;
}

function headerCard(h) {
  const card = el("div", { class: "card" });
  card.dataset.rowId = h.__row_id ?? "";
  const inputs = {};
  for (const key of ["name", "value_env", "servers"]) {
    const f = field(key, h[key]);
    inputs[key] = f.input; card.appendChild(f.wrap);
  }
  // 值：不预填明文；据 value_set 显示占位；空输入=保留旧值（哨兵）
  const vf = field("value", "", {
    type: "password",
    placeholder: h.value_set ? "已设置（留空保持不变）" : "未设置",
  });
  inputs.value = vf.input; card.appendChild(vf.wrap);
  card._collect = () => {
    const out = { __row_id: card.dataset.rowId || null };
    for (const [k, inp] of Object.entries(inputs)) {
      if (k === "value") out.value = inp.value === "" ? SENTINEL : inp.value;
      else out[k] = inp.value;
    }
    return out;
  };
  return card;
}

export async function mountSettings(bridge, root, toast) {
  root.replaceChildren();
  let cfg;
  try { const r = await bridge.apiGet("config/get"); cfg = r.config; }
  catch (e) { toast("读取配置失败"); return; }

  const serversWrap = el("div");
  (cfg.servers || []).forEach(s => serversWrap.appendChild(serverCard(s)));
  root.appendChild(el("h3", { text: "服务器" }));
  root.appendChild(serversWrap);

  const headersWrap = el("div");
  (cfg.custom_headers || []).forEach(h => headersWrap.appendChild(headerCard(h)));
  root.appendChild(el("h3", { text: "自定义请求头" }));
  root.appendChild(headersWrap);

  const save = el("button", { class: "primary", text: "保存并重载" });
  save.onclick = async () => {
    // 其余节（routing/polling/... group_bindings）原样透传保留原值；
    // servers/custom_headers 用收集值（含哨兵），避免脱敏空值被判为清空
    const body = { ...cfg };
    body.servers = Array.from(serversWrap.children).map(c => c._collect());
    body.custom_headers = Array.from(headersWrap.children).map(c => c._collect());
    delete body.__row_id;
    try {
      const res = await bridge.apiPost("config/save", body);
      if (res.ok) {
        const w = res.warnings || {};
        const skips = [...(w.skipped_servers || []), ...(w.skipped_headers || [])];
        toast(skips.length ? `已保存（${skips.length} 条被跳过）` : "已保存并重载");
      } else {
        toast(errorText(res));
      }
    } catch (e) { toast("保存失败"); }
  };
  root.appendChild(save);
}

function errorText(res) {
  const path = res.detail && res.detail.path ? `：${res.detail.path}` : "";
  const map = {
    save_in_progress: "保存进行中，请稍候",
    too_frequent: "保存过于频繁，请稍候再试",
    too_large: "配置过大",
    invalid_shape: "配置结构不合法",
    invalid_field: "字段不合法",
    credential_redirect: "修改了服务器地址，请重新输入该服务器密码",
    restart_failed_rolled_back: "重载失败，已回滚到旧配置",
    restart_failed: "重载失败且回滚失败，请检查后台",
  };
  return (map[res.error] || "保存失败") + path;
}
```

创建 `pages/settings/status.js`：

```js
// 状态面板：拉取只读状态 → 卡片渲染 → 手动刷新。全部 textContent。
export async function mountStatus(bridge, root, toast) {
  root.replaceChildren();
  const refresh = document.createElement("button");
  refresh.className = "primary";
  refresh.textContent = "刷新";
  const list = document.createElement("div");
  root.appendChild(refresh);
  root.appendChild(list);

  async function load() {
    list.replaceChildren();
    let data;
    try { data = await bridge.apiGet("status/overview"); }
    catch (e) { toast("读取状态失败"); return; }
    if (data.restarting) {
      const p = document.createElement("p");
      p.textContent = "插件正在重载配置…";
      list.appendChild(p);
      setTimeout(load, 3000);
      return;
    }
    for (const row of data.servers) {
      const card = document.createElement("div");
      card.className = "card";
      const title = document.createElement("strong");
      title.textContent = row.name;              // 服务器名：textContent 防 XSS
      card.appendChild(title);
      const line = document.createElement("div");
      if (!row.ready) line.textContent = "未就绪";
      else line.textContent = `在线 ${row.online} · ${row.smoothness_label}` +
        (row.degraded ? " · 数据缺失" : "");
      card.appendChild(line);
      list.appendChild(card);
    }
  }
  refresh.onclick = load;
  load();
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/pages_static_test.py -q`
Expected: 5 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add pages/settings tests/unit/pages_static_test.py
git commit -m "feat(pages): 插件页面设置/状态前端（原生 JS，textContent 防 XSS）"
```

---

### Task 8: README + metadata 文档同步

**Files:**
- Modify: `README.md`（新增「插件页面」小节）
- Test: `tests/unit/readme_test.py`

**Interfaces:**
- Consumes: 无（纯文档）

- [ ] **Step 1: 写失败测试**

`tests/unit/readme_test.py` 文件末尾追加：

```python
def test_readme_documents_plugin_page_section():
    for phrase in ("插件页面", "4.24.1", "4.25.3", "__unchanged__", "重载"):
        assert phrase in README, f"README 插件页面文档缺少: {phrase}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -q`
Expected: `test_readme_documents_plugin_page_section` FAIL

- [ ] **Step 3: 实现**

`README.md` 的 `### custom_headers` 小节之后追加：

```markdown
### 插件页面（WebUI 设置与状态）

AstrBot ≥ 4.24.1 支持插件自定义 WebUI 页面。安装本插件后，可在插件详情页
（≥4.24.1）或左侧栏「插件页面」分组（≥4.25.3）打开「PalChronicle 设置」页，
可视化编辑服务器/路由等配置，并查看各服务器只读状态面板。低于 4.24.1 的
AstrBot 不显示该页面，插件其余功能不受影响。

- **保存即重载**：页面保存配置后插件会自动重启内部容器使其生效，重载期间
  轮询短暂中断（在线时长统计有极小缺口），聊天命令会临时提示「正在重载」
- **敏感字段**：密码、自定义请求头值等敏感项在页面上不回显明文，显示为
  「已设置（留空保持不变）」；留空提交即保留旧值（内部用保留字
  `__unchanged__` 表示未改动）。若修改了某服务器的地址（base_url），出于
  安全必须重新输入该服务器密码，避免旧凭证被发往新地址
- **鉴权**：页面请求经 AstrBot Dashboard 登录态转发，未登录无法访问
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add README.md tests/unit/readme_test.py
git commit -m "docs(readme): 插件页面设置/状态使用说明"
```

---

## 实现期须实测的平台事实（规格 §5 鉴权纵深，非本计划自动化任务）

以下由实现者在接入真实 AstrBot 时手动验证并记录，**不阻塞**上述任务的单测交付，
但合并前必须确认：

1. 未登录直接请求三端点应 401：按版本用正确 URL（v4.26+ `/api/v1/plugins/extensions/astrbot_plugin_palword/config/get`；4.24–4.25 `/api/plug/astrbot_plugin_palword/config/get`）。判据是「缺 JWT 得 401」，注意未匹配路由平台返回 200+`status:error` 而非 404
2. CSRF：确认 AstrBot 对插件 POST 是否强制 same-origin/token；若不强制，需在 handler 追加来源校验（后续任务）
3. `bridge.ready()` 在部署的 AstrBot 版本上返回的上下文是否含 `isDark`（<4.25.3 无，主题跟随不可用属预期）
