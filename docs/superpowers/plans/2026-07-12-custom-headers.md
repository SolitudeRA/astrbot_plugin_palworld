# 自定义 HTTP 请求头 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户在 AstrBot WebUI 用按钮添加/删除自定义 HTTP 请求头，随全部 REST 轮询请求发送，支持 value_env 敏感值与 servers 作用域限定。

**Architecture:** 解析期（`config.py`）完成全部校验/作用域过滤/去重，结果落到每个 `ServerConfig.headers`；请求层（`palworld_rest.py`）仅透传一个 `headers=` 参数；跳过条目记 `SkippedHeader` 并由 `Container.start()` 打一条脱敏 warning。规格：`docs/superpowers/specs/2026-07-11-custom-headers-design.md`（已对抗式复核，实现遇歧义以规格为准）。

**Tech Stack:** Python 3.11 dataclass(slots)、aiohttp、pytest（asyncio auto 模式）

## Global Constraints

- 测试命令一律用项目虚拟环境：`.venv/Scripts/python.exe -m pytest`（Windows；`python` 不在 PATH）
- **commit message 不得包含任何 AI/Claude 署名、提及或 Co-Authored-By 尾行**（用户硬性要求）
- 脱敏红线：header 的 value（含 env 解析后明文）绝不进入日志、错误信息、`SkippedHeader`、任何展示面；except 分支禁止记录异常对象文本
- `ServerConfig`/`AppConfig` 均为 `@dataclass(slots=True)` 且现有字段无默认值：新增字段必须 `field(default_factory=...)` 且排在**最后**，否则语法错误或既有位置参数构造点全崩
- name/value/servers 分段各 `strip()` 一次，此后所有步骤用同一 stripped 值
- 每个 Task 收尾跑全量 `.venv/Scripts/python.exe -m pytest -q` + `.venv/Scripts/python.exe -m ruff check .` + `.venv/Scripts/python.exe -m mypy`，三绿才 commit

---

### Task 1: config 解析层 — SkippedHeader / ServerConfig.headers / custom_headers 解析

**Files:**
- Modify: `palchronicle/config.py`
- Test: `tests/unit/config_headers_test.py`（新建）

**Interfaces:**
- Produces: `SkippedHeader(raw_name: str, reason: str)` dataclass；`ServerConfig.headers: dict[str, str]`（默认 `{}`）；`AppConfig.skipped_headers: list[SkippedHeader]`（默认 `[]`）；`parse_config` 行为扩展（签名不变）
- reason 取值：`"empty_name" | "illegal_name" | "reserved" | "empty_value" | "illegal_value"`（作用域零匹配**不是** skip，不产生 SkippedHeader）

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/config_headers_test.py`：

```python
"""custom_headers 解析：校验/作用域/去重/SkippedHeader（spec §3.2/§3.3/§6）。"""
from palchronicle.config import SkippedHeader, parse_config


def _raw(custom_headers=None):
    cfg = {"servers": [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "__template_key": "server"},
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "__template_key": "server"},
    ]}
    if custom_headers is not None:
        cfg["custom_headers"] = custom_headers
    return cfg


def _hdr(**kw):
    # 模拟 WebUI 保存形状：恒含 __template_key 附加键（解析必须忽略它）
    item = {"name": "", "value": "", "value_env": "", "servers": "",
            "__template_key": "header"}
    item.update(kw)
    return item


def _by_name(cfg):
    return {s.name: s for s in cfg.servers}


def test_no_custom_headers_key_backwards_compatible():
    cfg = parse_config(_raw(), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []


def test_custom_headers_none_value_backwards_compatible():
    raw = _raw()
    raw["custom_headers"] = None
    cfg = parse_config(raw, {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []


def test_value_env_wins_over_value():
    cfg = parse_config(
        _raw([_hdr(name="X-Token", value="plain", value_env="MY_TOKEN")]),
        {"MY_TOKEN": "from-env"},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-Token": "from-env"}


def test_value_env_missing_falls_back_to_value():
    cfg = parse_config(
        _raw([_hdr(name="X-Token", value="plain", value_env="ABSENT")]), {},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-Token": "plain"}


def test_both_value_sources_empty_skipped():
    cfg = parse_config(_raw([_hdr(name="X-Token")]), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == [SkippedHeader("X-Token", "empty_value")]


def test_value_stripped_before_send():
    cfg = parse_config(_raw([_hdr(name="X-Token", value="  tok  ")]), {})
    assert _by_name(cfg)["alpha"].headers == {"X-Token": "tok"}


def test_scope_empty_applies_to_all_servers():
    cfg = parse_config(_raw([_hdr(name="X-A", value="1")]), {})
    by = _by_name(cfg)
    assert by["alpha"].headers == {"X-A": "1"}
    assert by["beta"].headers == {"X-A": "1"}


def test_scope_limits_to_listed_servers():
    cfg = parse_config(
        _raw([_hdr(name="X-A", value="1", servers="alpha"),
              _hdr(name="X-B", value="2", servers=" alpha , beta ")]), {},
    )
    by = _by_name(cfg)
    assert by["alpha"].headers == {"X-A": "1", "X-B": "2"}
    assert by["beta"].headers == {"X-B": "2"}


def test_scope_all_empty_segments_means_zero_servers():
    # ",," 非空但切分后无有效段：fail-closed，绝不回退到全部（spec §3.2.5）
    cfg = parse_config(_raw([_hdr(name="X-A", value="1", servers=",,")]), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []  # 零作用域不是 skip


def test_scope_all_unknown_names_means_zero_servers():
    cfg = parse_config(_raw([_hdr(name="X-A", value="1", servers="typo")]), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []


def test_scope_is_case_sensitive():
    cfg = parse_config(_raw([_hdr(name="X-A", value="1", servers="Alpha")]), {})
    assert all(s.headers == {} for s in cfg.servers)


def test_reserved_headers_skipped_case_and_whitespace_insensitive():
    reserved = ["authorization", "Host", "CONTENT-LENGTH",
                "Transfer-Encoding", "connection", "Expect",
                " authorization", "AUTHORIZATION"]
    cfg = parse_config(
        _raw([_hdr(name=n, value="v") for n in reserved]), {},
    )
    assert all(s.headers == {} for s in cfg.servers)
    assert [h.reason for h in cfg.skipped_headers] == ["reserved"] * len(reserved)


def test_illegal_names_skipped():
    cfg = parse_config(
        _raw([_hdr(name="X Name", value="v"),
              _hdr(name="X:Name", value="v"),
              _hdr(name="标头", value="v"),
              _hdr(name="   ", value="v")]), {},
    )
    assert all(s.headers == {} for s in cfg.servers)
    assert [h.reason for h in cfg.skipped_headers] == [
        "illegal_name", "illegal_name", "illegal_name", "empty_name"]


def test_illegal_values_skipped_tab_allowed():
    cfg = parse_config(
        _raw([_hdr(name="X-A", value="bad\rv"),
              _hdr(name="X-B", value="bad\nv"),
              _hdr(name="X-C", value="bad\x00v"),
              _hdr(name="X-D", value="bad\x7fv"),
              _hdr(name="X-E", value="ok\tv")]), {},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-E": "ok\tv"}
    assert [h.reason for h in cfg.skipped_headers] == ["illegal_value"] * 4


def test_case_insensitive_dedup_later_wins_and_keeps_later_case():
    cfg = parse_config(
        _raw([_hdr(name="x-token", value="first"),
              _hdr(name="X-TOKEN", value="second")]), {},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-TOKEN": "second"}


def test_skipped_header_never_contains_value():
    cfg = parse_config(_raw([_hdr(name="bad name", value="s3cret")]), {})
    (h,) = cfg.skipped_headers
    assert h.raw_name == "bad name"
    assert "s3cret" not in h.raw_name and "s3cret" not in h.reason
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_headers_test.py -q`
Expected: 收集期 `ImportError: cannot import name 'SkippedHeader'`

- [ ] **Step 3: 实现 config.py**

`palchronicle/config.py` 修改（位置对照现有行号）：

顶部 import 区（第 4-7 行附近）加：

```python
import re
from dataclasses import dataclass, field
```

（原 `from dataclasses import dataclass` 改为上行；`import re` 按 isort 排普通段）

模块常量（`_ILLEGAL = (":", "@")` 之后）：

```python
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
```

dataclass 定义（`SkippedServer` 之后加；`ServerConfig` 尾部加字段）：

```python
@dataclass(slots=True)
class SkippedHeader:
    raw_name: str  # 原始 name；绝不携带 value（脱敏红线）
    reason: str    # empty_name / illegal_name / reserved / empty_value / illegal_value
```

`ServerConfig` 末尾（`timezone: str` 之后）追加：

```python
    headers: dict[str, str] = field(default_factory=dict)
```

`AppConfig` 末尾（`history: HistoryConfig` 之后）追加：

```python
    skipped_headers: list[SkippedHeader] = field(default_factory=list)
```

解析函数（`_parse_bindings` 之后加）：

```python
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
```

`parse_config` 接线（函数体开头 `servers, skipped = _parse_servers(raw, env)` 之后加）：

```python
    header_map, skipped_headers = _parse_custom_headers(
        raw, env, [s.name for s in servers])
    for s in servers:
        s.headers = header_map[s.name]
```

`AppConfig(...)` 构造末尾（`history=HistoryConfig(...)` 之后）加：

```python
        skipped_headers=skipped_headers,
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_headers_test.py -q`
Expected: 16 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿（既有测试对 ServerConfig 的 9 参位置构造因新字段带默认值不受影响）

- [ ] **Step 6: Commit**

```bash
git add palchronicle/config.py tests/unit/config_headers_test.py
git commit -m "feat(config): 解析 custom_headers 到 ServerConfig.headers（校验/作用域/去重/SkippedHeader）"
```

---

### Task 2: REST 客户端携带自定义请求头

**Files:**
- Modify: `palchronicle/adapters/palworld_rest.py:51-57`（`session.get` 调用）
- Modify: `tests/unit/palworld_rest_test.py`（`_FakeSession.get` 签名 + 2 个新测试）

**Interfaces:**
- Consumes: `ServerConfig.headers: dict[str, str]`（Task 1）
- Produces: `fetch` 对 5 端点统一携带 `headers=server.headers or None`

- [ ] **Step 1: 写失败测试**

`tests/unit/palworld_rest_test.py`：先更新 `_FakeSession`（第 32-51 行），`get` 增加 `headers` 参数并记录：

```python
class _FakeSession:
    """替换 aiohttp.ClientSession；按脚本返回响应或抛异常。"""

    def __init__(self, script):
        self._script = script
        self.requested_url = None
        self.requested_auth = None
        self.requested_headers = "UNSET"  # 哨兵：区分「传了 None」与「没传」
        self.closed = False

    @asynccontextmanager
    async def get(self, url, auth=None, timeout=None, ssl=None, headers=None):
        self.requested_url = url
        self.requested_auth = auth
        self.requested_headers = headers
        outcome = self._script
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    async def close(self):
        self.closed = True
```

文件末尾追加两个测试：

```python
async def test_fetch_sends_custom_headers():
    server = ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://secret-host:8212", username="admin",
        password="topsecret", timeout=10, verify_tls=True, timezone="",
        headers={"CF-Access-Client-Id": "abc", "X-Token": "t"},
    )
    session = _FakeSession(_FakeResp(200, {}))
    client = PalworldRestClient(server, FakeClock(1000))
    client._session = session
    await client.fetch(EndpointName.INFO)
    assert session.requested_headers == {"CF-Access-Client-Id": "abc", "X-Token": "t"}


async def test_fetch_without_custom_headers_passes_none():
    # headers 为空 dict 时必须传 None，保持现有请求完全不变（spec §4 零回归面）
    session = _FakeSession(_FakeResp(200, {}))
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = session
    await client.fetch(EndpointName.INFO)
    assert session.requested_headers is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/palworld_rest_test.py -q`
Expected: 两个新测试 FAIL（`requested_headers` 仍为 `"UNSET"`——fetch 未传 headers），既有测试 PASS

- [ ] **Step 3: 实现**

`palchronicle/adapters/palworld_rest.py` 的 `session.get(...)` 调用（第 51-57 行）加一行参数：

```python
            async with session.get(
                url,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=self._server.timeout),
                # aiohttp 标注不含 None，但运行时 None 等价于默认校验；保持现状不改行为
                ssl=ssl_opt,  # type: ignore[arg-type]
                headers=self._server.headers or None,  # 空 dict 传 None：零回归面
            ) as resp:
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/palworld_rest_test.py -q`
Expected: 全部 PASS（含既有 8 个）

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/adapters/palworld_rest.py tests/unit/palworld_rest_test.py
git commit -m "feat(rest): 轮询请求携带 ServerConfig.headers 自定义请求头"
```

---

### Task 3: Container 启动时对跳过条目记脱敏 warning

**Files:**
- Modify: `palchronicle/container.py`（`start()` 开头）
- Modify: `tests/unit/container_test.py`（2 个新测试）

**Interfaces:**
- Consumes: `AppConfig.skipped_headers: list[SkippedHeader]`（Task 1）
- Produces: 无对外接口；logger `palchronicle.container` 的 warning 行为

- [ ] **Step 1: 写失败测试**

`tests/unit/container_test.py`：import 区把 `SkippedHeader` 加入既有 `from palchronicle.config import (...)`；文件末尾追加：

```python
async def test_skipped_headers_logged_on_start_without_value(tmp_path: Path, caplog):
    cfg = _cfg([_server("alpha")])
    cfg.skipped_headers = [SkippedHeader("bad name", "illegal_name"),
                           SkippedHeader("Authorization", "reserved")]
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda *a, **k: _FakeScheduler())
    with caplog.at_level(logging.WARNING, logger="palchronicle.container"):
        await c.start()
    try:
        msgs = [r.getMessage() for r in caplog.records if "custom_headers" in r.getMessage()]
        assert len(msgs) == 1
        assert "bad name(illegal_name)" in msgs[0]
        assert "Authorization(reserved)" in msgs[0]
    finally:
        await c.stop()


async def test_no_skipped_headers_no_warning(tmp_path: Path, caplog):
    c = Container(_cfg([_server("alpha")]), tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda *a, **k: _FakeScheduler())
    with caplog.at_level(logging.WARNING, logger="palchronicle.container"):
        await c.start()
    try:
        assert not any("custom_headers" in r.getMessage() for r in caplog.records)
    finally:
        await c.stop()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/container_test.py -q`
Expected: `test_skipped_headers_logged_on_start_without_value` FAIL（无该日志），其余 PASS

- [ ] **Step 3: 实现**

`palchronicle/container.py` 的 `start()` 方法开头（`self._db = Database(...)` 之前）加：

```python
        if self._cfg.skipped_headers:
            # 只含 name+reason；value（可能是网关凭证）绝不入日志
            _log.warning(
                "custom_headers 跳过 %d 条: %s",
                len(self._cfg.skipped_headers),
                ", ".join(f"{h.raw_name}({h.reason})"
                          for h in self._cfg.skipped_headers),
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/container_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/container.py tests/unit/container_test.py
git commit -m "feat(container): 启动时对被跳过的 custom_headers 记脱敏 warning"
```

---

### Task 4: schema / README / requirements 同步

**Files:**
- Modify: `_conf_schema.json`（`group_bindings` 之后插入 `custom_headers` 键）
- Modify: `README.md`（`### history` 小节之后新增 `### custom_headers` 小节）
- Modify: `requirements.txt`（aiohttp 下界）
- Modify: `tests/unit/conf_schema_test.py`、`tests/unit/readme_test.py`

**Interfaces:**
- Consumes: 无代码依赖（纯配置/文档；schema 键名与 Task 1 解析的 `custom_headers`/`name`/`value`/`value_env`/`servers` 字段一一对应）

- [ ] **Step 1: 写失败测试**

`tests/unit/conf_schema_test.py`：`test_top_level_keys_present_and_types` 中 `assert s["group_bindings"]...` 之后加一行：

```python
    assert s["custom_headers"]["type"] == "template_list"
```

文件末尾追加：

```python
def test_custom_headers_template_items_and_defaults():
    s = load_schema()
    ch = s["custom_headers"]
    assert ch["default"] == []
    assert ch["templates"]["header"]["display_item"] == "name"
    items = ch["templates"]["header"]["items"]
    assert set(items) == {"name", "value", "value_env", "servers"}
    assert all(items[k]["default"] == "" for k in items)
```

`tests/unit/readme_test.py` 文件末尾追加：

```python
def test_readme_documents_custom_headers_section():
    for phrase in ("custom_headers", "value_env", "servers 留空",
                   "所有服务器", "重启 AstrBot"):
        assert phrase in README, f"README custom_headers 配置文档缺少: {phrase}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/conf_schema_test.py tests/unit/readme_test.py -q`
Expected: 新增断言 FAIL（KeyError: 'custom_headers' / README 缺关键词）

- [ ] **Step 3: 实现**

`_conf_schema.json`：在 `group_bindings` 键闭合后、`polling` 之前插入（注意 JSON 逗号）：

```json
  "custom_headers": {
    "type": "template_list",
    "description": "自定义 HTTP 请求头（随 REST 轮询请求发送）",
    "hint": "敏感值（如网关 Token）建议填环境变量名(value_env)而非明文；明文会落盘到 data/config/。含凭证的头务必用 servers 限定作用域：留空会发给所有已配置服务器（包括之后新增的）",
    "default": [],
    "templates": {
      "header": {
        "name": "请求头",
        "display_item": "name",
        "items": {
          "name": { "type": "string", "description": "Header 名（如 CF-Access-Client-Id）", "default": "" },
          "value": { "type": "string", "description": "Header 值（明文，与 value_env 二选一）", "default": "" },
          "value_env": { "type": "string", "description": "值的环境变量名（推荐，与 value 二选一）", "default": "" },
          "servers": { "type": "string", "description": "限定服务器 name，逗号分隔多个；留空=所有服务器", "default": "" }
        }
      }
    }
  },
```

`README.md`：`### history` 小节的表格之后追加：

```markdown
### custom_headers（自定义 HTTP 请求头）

随插件对 REST API 的所有轮询请求一并发送。适用于 REST API 经反向代理/网关暴露、需要额外鉴权头的场景（如 Cloudflare Access 的 `CF-Access-Client-Id` / `CF-Access-Client-Secret`）。在 WebUI 配置页按条目添加/删除。

| 字段 | 默认 | 说明 |
|------|------|------|
| `name` | 空 | Header 名（如 `CF-Access-Client-Id`） |
| `value` | 空 | Header 值（明文，与 `value_env` 二选一；明文会落盘到 data/config/） |
| `value_env` | 空 | 值的环境变量名（推荐存放敏感值，如网关 Token） |
| `servers` | 空 | 限定服务器 name，逗号分隔多个。**servers 留空 = 发给所有服务器**（包括之后新增的）——含凭证的头务必限定作用域 |

注意：

- `Authorization`、`Host`、`Expect`、`Content-Length`、`Transfer-Encoding`、`Connection` 为保留头，配置了也会被忽略（Basic Auth 由服务器条目的 username/password 负责）
- `value_env` / `password_env` 指向的环境变量变更后需**重启 AstrBot** 进程才能读到（WebUI 保存配置只热重载插件，环境变量是进程级的）
- 被跳过的无效条目会在插件启动日志中以 warning 提示（只含名字与原因，不含值）
```

`requirements.txt`：`aiohttp>=3.9` 改为 `aiohttp>=3.9.2`（3.9.2 含头部控制字符注入修复，作为解析层校验之外的纵深防御——spec §7）。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/conf_schema_test.py tests/unit/readme_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add _conf_schema.json README.md requirements.txt tests/unit/conf_schema_test.py tests/unit/readme_test.py
git commit -m "feat(schema): custom_headers 配置项 + README 文档 + aiohttp 下界 3.9.2"
```
