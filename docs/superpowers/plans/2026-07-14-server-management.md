# 服务器管控实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给插件加全量 Palworld 服务器写操作（announce/save/kick/unban/ban/shutdown/stop）+ `/pal confirm` 二次确认 + 落库审计 + 前端只读审计页，全程仅授权管理员、默认关、可审计。

**Architecture:** 沿用现有分层 DDD。REST 客户端加 `post`；新 `AdminService`（写执行 + 名字解析 + 审计）；`ConfirmationStore`（可注入 clock 的 pending 状态机）；`Commands.admin_write` 中央写编排（门序 admin→feature→授权→目标→确认→执行+审计）；main.py `_guarded_admin` 单一 choke point + 8 handler + confirm handler；两个默认关 feature 组 + `server_admin` 配置段；前端 `AuditPanel` 只读页。

**Tech Stack:** Python 3.11+、AstrBot 插件框架、aiohttp、aiosqlite；前端 Vue3 + reka-ui + Vite；pytest / vitest。

## Global Constraints

- **依据 spec**：`docs/superpowers/specs/2026-07-14-server-management-design.md`（已过三视角对抗复核）。
- **git 提交不得出现任何 Claude / AI / 🤖 署名**（无 Co-Authored-By，正文不提及）。
- **包内 import 一律相对**，函数体内**绝不绝对自导入**（命名空间加载会炸，`no_absolute_self_import_test` 静态防回归）。
- **Windows 上 `python` 被拦截**，一律用 `./.venv/Scripts/python.exe` 跑 pytest / ruff / mypy。
- **门序铁律**：写命令 **admin 硬门先于 feature 门**；非管理员一律 `admin_required`（与组开关无关，防配置态泄漏）。8 写命令 + confirm 全部硬编码仅 `permission_admins` 名单成员，**不依赖**可选 `admin_only_commands`。
- **不可锁集**扩张为 `{server, whoami, help, confirm, announce, save, kick, unban, ban, shutdown, stop}`（12 项）；`config._NON_LOCKABLE` 与 `command_registry` 两处 + `command_names_test.py::test_lockable_excludes_non_lockable` 硬编码断言（3→12）必须同步。
- **feature 组两处**：`FeaturesConfig` 字段 **必须同步 `enabled()` 字典**，否则组恒 disabled 静默失效。
- **审计 hash**：`hash_user_id(salt, <目标服务器 current world_id>, 明文 userid)`，与观测侧同源；明文 userid 用完即弃、不落库、不进日志。
- **confirm 铁律**：claim-then-execute（先原子 pop 再 await）；执行前复检 danger 组仍启用 + 重跑目标授权；**config 热重载清 pending**；pending/超时判定持注入 clock（非 main.py）。
- **post() 成功判定**区别于 fetch：容忍空 body / 非 JSON / 2xx 含 204；stop/shutdown 断连按「已发起」。
- **前端改后必须** `cd frontend && npm run build`（内置 normalize-eol）并提交 `pages/settings/`；`verify-bundle` 从仓库根跑；CI no-drift 强制。审计页须新建 `AuditPanel.vue` + 改 `App.vue` 路由（现硬编码 `chapter==='status'`）。
- **改中文文案须同步 grep** `tests/unit/readme_test.py` 中文锚点（含现有 `不控制服务器`，改只读文案时同步）。
- **版本 `v0.8.7` → `v0.9.0`**，四源同步（metadata.yaml / main.py @register / `__init__.py` / README 徽章）。
- **子代理 model 一律 opus**。

## 文件结构总览

| 文件 | 职责 | Task |
|---|---|---|
| `palworld_terminal/config.py` | 两 feature 组 + `enabled()` + `ServerAdminConfig` + `_NON_LOCKABLE` 扩张 | T1 |
| `palworld_terminal/adapters/palworld_rest.py` | `post()` 写能力 + 写端点路径表 | T2 |
| `palworld_terminal/infrastructure/migrations.py`、`adapters/sqlite_repository.py` | `migration_0004` admin_audit + insert/list/prune | T3 |
| `palworld_terminal/application/admin_service.py`（新） | 写执行核心（announce/save/shutdown/stop）+ 审计 hash | T4 |
| 同上 | 名字解析 + kick/ban/unban | T5 |
| `palworld_terminal/presentation/confirmation.py`（新） | `ConfirmationStore` pending 状态机 | T6 |
| `palworld_terminal/presentation/commands.py`、`container.py` | `admin_write` 中央编排 + `confirm` + 装配 | T7 |
| `presentation/command_registry.py`、`main.py`、`presentation/formatters.py`、`container.py`、冒烟 | 注册 + `_guarded_admin` + 8 handler + help 隔离 + `_post` | T8 |
| `presentation/web_api.py`、`config_view.py`、`main.py` | 审计只读端点 + DTO + 路由 | T9 |
| `_conf_schema.json` | 两组 + server_admin schema | T10 |
| `frontend/src/lib/schema.ts`、`chapters.ts` | FEATURE 两组 + 审计章 | T11 |
| `frontend/src/components/SettingsPanel.vue` | 两组开关 + server_admin 段 | T12 |
| `frontend/src/components/AuditPanel.vue`（新）、`App.vue` | 审计只读页 + kind 路由 | T13 |
| `pages/settings/` | 重建产物 | T14 |
| `docs/*`、`README.md`、`readme_test.py`、版本四源、`App.vue` 副标题 | 文档 + 只读承诺迁移 + 版本 | T15 |

---

## Task 1: config.py —— 两 feature 组 + ServerAdminConfig + _NON_LOCKABLE 扩张

**Files:**
- Modify: `palworld_terminal/config.py`
- Test: `tests/unit/config_server_admin_test.py`（新建）

**Interfaces:**
- Produces: `FeaturesConfig.server_admin_basic/server_admin_danger: bool` + `enabled()` 认这两键；`ServerAdminConfig(require_confirmation: bool, confirmation_timeout: int, audit_retention_days: int)`；`AppConfig.server_admin: ServerAdminConfig`；`_NON_LOCKABLE` 扩张为 12 项。T4/T6/T7/T8/T10 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/config_server_admin_test.py`：

```python
from palworld_terminal.config import parse_config


def _base(**over):
    raw = {"servers": [], "routing": {}, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    raw.update(over)
    return parse_config(raw, {})


def test_feature_groups_default_off_and_enabled_dict_synced():
    cfg = _base()
    assert cfg.features.server_admin_basic is False
    assert cfg.features.server_admin_danger is False
    # enabled() 字典必须认这两键，否则组恒 disabled 静默失效
    assert cfg.features.enabled("server_admin_basic") is False
    cfg2 = _base(features={"server_admin_basic": True, "server_admin_danger": True})
    assert cfg2.features.enabled("server_admin_basic") is True
    assert cfg2.features.enabled("server_admin_danger") is True


def test_server_admin_defaults():
    sa = _base().server_admin
    assert sa.require_confirmation is False
    assert sa.confirmation_timeout == 30
    assert sa.audit_retention_days == 180


def test_server_admin_range_clamp():
    sa = _base(server_admin={"confirmation_timeout": 99999, "audit_retention_days": -5}).server_admin
    assert sa.confirmation_timeout == 600   # 上界 clamp [5,600]
    assert sa.audit_retention_days == 1     # 越界 clamp 到下界 [1,3650]


def test_server_admin_non_int_falls_back_default():
    sa = _base(server_admin={"confirmation_timeout": "oops"}).server_admin
    assert sa.confirmation_timeout == 30    # 非 int 回默认


def test_non_lockable_expanded_to_twelve():
    from palworld_terminal.config import _NON_LOCKABLE
    assert _NON_LOCKABLE == frozenset({
        "server", "whoami", "help", "confirm",
        "announce", "save", "kick", "unban", "ban", "shutdown", "stop",
    })
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_server_admin_test.py -v`
Expected: FAIL —— `AttributeError` / `_NON_LOCKABLE` 仍是 3 项。

- [ ] **Step 3: FeaturesConfig 加两组 + enabled() 同步**

`config.py` 的 `FeaturesConfig`（约 116-128）：字段区加 `server_admin_basic: bool = False`、`server_admin_danger: bool = False`；`enabled()` 的分派 dict 加两键 `"server_admin_basic": self.server_admin_basic, "server_admin_danger": self.server_admin_danger`。`_default_features`（约 131）保持默认 False（dataclass 默认已覆盖，确认解析处对齐）。

`parse_config` 的 features 解析段（约 356-361）加 `server_admin_basic=bool(f.get("server_admin_basic", False))`、`server_admin_danger=bool(f.get("server_admin_danger", False))`。

- [ ] **Step 4: ServerAdminConfig dataclass + parse**

在 `AppConfig` 之前加：

```python
@dataclass(slots=True)
class ServerAdminConfig:
    require_confirmation: bool
    confirmation_timeout: int
    audit_retention_days: int


def _default_server_admin() -> "ServerAdminConfig":
    return ServerAdminConfig(require_confirmation=False, confirmation_timeout=30, audit_retention_days=180)


def _clamp_int(raw, default: int, lo: int, hi: int) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _parse_server_admin(raw: Mapping) -> "ServerAdminConfig":
    sa = raw.get("server_admin", {}) or {}
    if not isinstance(sa, Mapping):
        sa = {}
    return ServerAdminConfig(
        require_confirmation=bool(sa.get("require_confirmation", False)),
        confirmation_timeout=_clamp_int(sa.get("confirmation_timeout", 30), 30, 5, 600),
        audit_retention_days=_clamp_int(sa.get("audit_retention_days", 180), 180, 1, 3650),
    )
```

注：`_clamp_int` 语义——非法（非 int / None）回 `default`；合法但越界 → clamp 到 `[lo, hi]`。故 `confirmation_timeout="oops"`→30、`=99999`→600；`audit_retention_days=-5`→clamp 到下界 1。与 Step 1 测试一致。

- [ ] **Step 5: AppConfig 加字段 + 接线**

`AppConfig` 的 `players` 之后加 `server_admin: ServerAdminConfig = field(default_factory=_default_server_admin)`；`parse_config` 的 `return AppConfig(...)` 加 `server_admin=_parse_server_admin(raw),`。

- [ ] **Step 6: _NON_LOCKABLE 扩张**

`config.py` 的 `_NON_LOCKABLE`（约 163）改为：

```python
_NON_LOCKABLE = frozenset({
    "server", "whoami", "help", "confirm",
    "announce", "save", "kick", "unban", "ban", "shutdown", "stop",
})
```

- [ ] **Step 7: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_server_admin_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS（注：`config_permissions_test` 若断言 `_NON_LOCKABLE` 旧值会红——同步更新其断言到 12 项）。

- [ ] **Step 8: 提交**

```bash
git add palworld_terminal/config.py tests/unit/config_server_admin_test.py tests/unit/config_permissions_test.py
git commit -m "feat(config): server_admin 两组+配置段 + _NON_LOCKABLE 扩张 12 项"
```

---

## Task 2: palworld_rest.py —— post() 写能力

**Files:**
- Modify: `palworld_terminal/adapters/palworld_rest.py`
- Test: `tests/unit/palworld_rest_post_test.py`（新建）

**Interfaces:**
- Produces: `PalworldRestClient.post(self, path: str, json_body: dict | None) -> RestResponse`；成功判定容忍空/非 JSON/2xx 含 204；`_ADMIN_PATH` 写端点常量。T4 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/palworld_rest_post_test.py`（用 aiohttp 的 test server 或 monkeypatch session.post；照 `palworld_rest` 现有测试风格——先查 `tests/unit/` 是否已有 rest 测试范式复用其 fake）：

```python
import pytest

from palworld_terminal.adapters.palworld_rest import PalworldRestClient, RestResponse
from palworld_terminal.config import ServerConfig
from palworld_terminal.infrastructure.clock import SystemClock


class _FakeResp:
    def __init__(self, status, body=b"", json_exc=False):
        self.status = status
        self._body = body
        self._json_exc = json_exc
    async def read(self): return self._body
    async def json(self, content_type=None):
        if self._json_exc:
            raise ValueError("no json")
        return {"ok": True}
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class _FakeSession:
    def __init__(self, resp): self._resp = resp; self.closed = False
    def post(self, *a, **k): return self._resp
    async def close(self): self.closed = True


def _client(resp):
    srv = ServerConfig(server_id="s", name="s", base_url="http://x", username="u",
                       password="p", timeout=5, verify_tls=True, headers={}, ready=True)
    c = PalworldRestClient(srv, SystemClock())
    c._session = _FakeSession(resp)  # 注入
    return c


@pytest.mark.asyncio
async def test_post_200_empty_body_is_success():
    c = _client(_FakeResp(200, b""))
    r = await c.post("announce", {"message": "hi"})
    assert r.ok and r.status == 200


@pytest.mark.asyncio
async def test_post_204_is_success():
    c = _client(_FakeResp(204, b""))
    r = await c.post("save", None)
    assert r.ok


@pytest.mark.asyncio
async def test_post_non_json_2xx_is_success():
    c = _client(_FakeResp(200, b"OK", json_exc=True))
    r = await c.post("stop", None)
    assert r.ok


@pytest.mark.asyncio
async def test_post_error_status_not_ok():
    c = _client(_FakeResp(400, b"bad"))
    r = await c.post("kick", {"userid": "x"})
    assert not r.ok and r.status == 400
```

（若 `ServerConfig` 构造参数与上不符，先读 `config.py::ServerConfig` 对齐字段名/顺序。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/palworld_rest_post_test.py -v`
Expected: FAIL —— `AttributeError: 'PalworldRestClient' object has no attribute 'post'`

- [ ] **Step 3: 加写端点表 + post()**

`palworld_rest.py` 模块顶部加：

```python
# 写端点路径（独立于只读 _ENDPOINT_PATH，不进 EndpointName 轮询枚举）
_ADMIN_PATH = frozenset({"announce", "save", "kick", "unban", "ban", "shutdown", "stop"})
```

`PalworldRestClient` 内加（复用 fetch 的 auth/headers/timeout/脱敏骨架，但成功判定不同）：

```python
    async def post(self, path: str, json_body: dict | None) -> RestResponse:
        session = self._ensure_session()
        url = f"{self._server.base_url}/v1/api/{path}"
        auth = aiohttp.BasicAuth(self._server.username, self._server.password)
        ssl_opt = None if self._server.verify_tls else False
        start = self._clock.monotonic()
        try:
            async with session.post(
                url, auth=auth, json=json_body,
                timeout=aiohttp.ClientTimeout(total=self._server.timeout),
                ssl=ssl_opt,  # type: ignore[arg-type]
                headers=self._server.headers or None,
            ) as resp:
                body = await resp.read()
                duration_ms = int((self._clock.monotonic() - start) * 1000)
                # 成功判定：2xx 即成功，不强制 json（写端点常回空/非 JSON body）
                if 200 <= resp.status < 300:
                    return RestResponse(ok=True, status=resp.status, data=None,
                                        duration_ms=duration_ms, payload_bytes=len(body), error=None)
                return RestResponse(ok=False, status=resp.status, data=None,
                                    duration_ms=duration_ms, payload_bytes=len(body),
                                    error=f"http_status_{resp.status}")
        except TimeoutError:
            return self._error_response(start, "request timeout")
        except aiohttp.ClientError:
            return self._error_response(start, "network error")
        except Exception:  # noqa: BLE001
            return self._error_response(start, "unexpected error")
```

注：`stop`/`shutdown` 服务器断连会落 `aiohttp.ClientError`→"network error"，命令层将其按「已发起」处理（见 T4）。本层如实返回 not-ok，语义映射在 AdminService。

- [ ] **Step 4: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/palworld_rest_post_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/palworld_rest.py tests/unit/palworld_rest_post_test.py
git commit -m "feat(rest): post() 写能力（2xx 成功判定容忍空/非 JSON body）"
```

---

## Task 3: migration_0004 + 审计 Repository

**Files:**
- Modify: `palworld_terminal/infrastructure/migrations.py`、`palworld_terminal/adapters/sqlite_repository.py`
- Test: `tests/unit/audit_repository_test.py`（新建）、`tests/unit/migrations_test.py`（确认动态断言不破）

**Interfaces:**
- Produces: `admin_audit` 表；`Repository.insert_audit(ts, admin_id, action, server_name, target_name, target_hash, detail, success, error) -> None`；`Repository.list_audit(limit) -> list[dict]`（倒序）；`Repository.prune_audit(before_ts) -> int`；**并把审计清理折进现有 `Repository.prune`**（保持与历史留存同一入口）。T4/T9 消费。

**留存现状说明（诚实标注，非本任务缺陷）**：现有 `Repository.prune(history, now)`（`sqlite_repository.py:244`）**全仓无运行时调用点**——历史留存本身即「潜伏未接线」。故审计留存折进同一 `prune` 方法保持一致（`prune` 何时被真正调度是既有项目遗留，不在本功能范围）。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/audit_repository_test.py`（照现有 repo 测试如 `tests/unit/` 里 sqlite_repository 相关测试的建库/迁移范式；先读一个现有 repo 测试对齐 fixture）：

```python
import pytest

# 复用现有 in-memory / tmp DB fixture 范式（先读现有 repo 测试）
async def test_insert_and_list_desc(audit_repo):
    await audit_repo.insert_audit(ts=100, admin_id="p:1", action="kick", server_name="s",
                                  target_name="Alice", target_hash="ab12", detail="", success=1, error=None)
    await audit_repo.insert_audit(ts=200, admin_id="p:1", action="stop", server_name="s",
                                  target_name=None, target_hash=None, detail="", success=1, error=None)
    rows = await audit_repo.list_audit(limit=10)
    assert [r["ts"] for r in rows] == [200, 100]   # 倒序
    assert rows[0]["action"] == "stop"


async def test_list_limit(audit_repo):
    for i in range(5):
        await audit_repo.insert_audit(ts=i, admin_id="p:1", action="save", server_name="s",
                                      target_name=None, target_hash=None, detail="", success=1, error=None)
    assert len(await audit_repo.list_audit(limit=2)) == 2


async def test_prune(audit_repo):
    await audit_repo.insert_audit(ts=10, admin_id="p:1", action="save", server_name="s",
                                  target_name=None, target_hash=None, detail="", success=1, error=None)
    await audit_repo.insert_audit(ts=100, admin_id="p:1", action="save", server_name="s",
                                  target_name=None, target_hash=None, detail="", success=1, error=None)
    deleted = await audit_repo.prune_audit(before_ts=50)
    assert deleted == 1
    assert [r["ts"] for r in await audit_repo.list_audit(limit=10)] == [100]
```

（`audit_repo` fixture 照现有 repo 测试建一个迁移到最新的临时 DB 的 Repository 实例。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/audit_repository_test.py -v`
Expected: FAIL（无 insert_audit / 表不存在）

- [ ] **Step 3: migration_0004**

`migrations.py`：现链止于 `migration_0003`（约 :241）。加：

```python
def migration_0004(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            admin_id TEXT NOT NULL,
            action TEXT NOT NULL,
            server_name TEXT NOT NULL,
            target_name TEXT,
            target_hash TEXT,
            detail TEXT,
            success INTEGER NOT NULL,
            error TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_ts ON admin_audit(ts DESC)")
```

并把 `migration_0004` 追加进 `MIGRATIONS` 列表（照 0003 追加方式）。

- [ ] **Step 4: Repository 三方法**

`sqlite_repository.py` 加（照现有 async execute/fetch 范式）：

```python
    async def insert_audit(self, *, ts, admin_id, action, server_name,
                           target_name, target_hash, detail, success, error) -> None:
        await self._db.execute(
            "INSERT INTO admin_audit (ts, admin_id, action, server_name, target_name, "
            "target_hash, detail, success, error) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, admin_id, action, server_name, target_name, target_hash, detail, success, error),
        )
        await self._db.commit()

    async def list_audit(self, limit: int) -> list[dict]:
        cur = await self._db.execute(
            "SELECT ts, admin_id, action, server_name, target_name, target_hash, "
            "detail, success, error FROM admin_audit ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        cols = ["ts", "admin_id", "action", "server_name", "target_name",
                "target_hash", "detail", "success", "error"]
        return [dict(zip(cols, r)) for r in rows]

    async def prune_audit(self, before_ts: int) -> int:
        cur = await self._db.execute("DELETE FROM admin_audit WHERE ts < ?", (before_ts,))
        await self._db.commit()
        return cur.rowcount
```

（若 `self._db` 访问器名不同，读现有方法对齐——现有 `prune` 用 `async with self._db.write_tx() as conn`，insert/list 若用 `execute_write`/`query` 照现有范式；`dict(zip(...))` 若与现有 row→dict 风格不符照现有方式。）

**折进现有 `prune`**：`Repository.prune` 签名扩为 `prune(self, history: HistoryConfig, now: int, audit_retention_days: int)`，在 `write_tx` 块内加：

```python
            await conn.execute(
                "DELETE FROM admin_audit WHERE ts < ?",
                (now - audit_retention_days * _SECONDS_PER_DAY,),
            )
```

并**更新现有** `tests/unit/repository_world_prune_test.py`（:84/:102/:117）的 `prune(...)` 调用加第三参 `audit_retention_days=180`（避免签名变更挂旧测试）。

- [ ] **Step 5: 运行确认通过 + 全库回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/audit_repository_test.py tests/unit/migrations_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS（`migrations_test` 用 `len(MIGRATIONS)` 动态断言，+0004 安全）

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/infrastructure/migrations.py palworld_terminal/adapters/sqlite_repository.py tests/unit/audit_repository_test.py tests/unit/repository_world_prune_test.py
git commit -m "feat(db): migration_0004 admin_audit + insert/list/prune（折进 retention）"
```

---

## Task 4: AdminService 核心 —— 无目标写 + 审计 hash

**Files:**
- Create: `palworld_terminal/application/admin_service.py`
- Test: `tests/unit/admin_service_test.py`（新建）

**Interfaces:**
- Consumes: `RoutingService.resolve`（T 现有）；`post` 回调；`Repository.insert_audit`（T3）；`salt`；`Clock`；`hash_user_id`（privacy_filter）。
- Produces: `AdminService(routing, fetch, post, repo, salt, clock)`；`async def announce(umo, is_group, message) -> AdminResult`；`save/shutdown/stop` 同族；`AdminResult(ok: bool, message_key: str, params: dict)`。目标类命令 T5 补。

**Interface 细节（钉死，供 T5/T7 对齐）**：
- `fetch(server_id, endpoint) -> RestResponse`、`post(server_id, path, json_body) -> RestResponse`（按 server_id 路由的回调，非直接持 client）。
- 每个方法内：`resolve` 目标服务器 → 取 `world_id`（`repo.get_current_world(server_id)`）→ `post` → `insert_audit`（成败都落；target_hash 用 world_id 命名空间）→ 返回 `AdminResult`。
- 断连（post 返回 not-ok 且 error 是 "network error"）对 `stop`/`shutdown` 视为「已发起」：`ok=True, message_key="admin_shutdown_initiated"`，仍落审计 success=1。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/admin_service_test.py`：

```python
from types import SimpleNamespace

import pytest

from palworld_terminal.application.admin_service import AdminService


class _FakeRepo:
    def __init__(self): self.audits = []
    async def get_current_world(self, server_id): return SimpleNamespace(world_id="w1")
    async def insert_audit(self, **kw): self.audits.append(kw)


class _FakeRouting:
    async def resolve(self, umo, override, is_group):
        return SimpleNamespace(ok=True, server=SimpleNamespace(server_id="s1", name="Alpha"), message=None)


def _svc(post_result):
    async def fetch(server_id, endpoint): return SimpleNamespace(ok=True, data=[])
    async def post(server_id, path, json_body): return post_result
    return AdminService(routing=_FakeRouting(), fetch=fetch, post=post,
                        repo=_FakeRepo(), salt=b"salt", clock=SimpleNamespace(now=lambda: 1000))


@pytest.mark.asyncio
async def test_announce_success_audits():
    ok = SimpleNamespace(ok=True, status=200, error=None)
    svc = _svc(ok)
    res = await svc.announce("p:1", "umo", True, "hello")   # admin_id 首参
    assert res.ok
    assert svc._repo.audits[0]["action"] == "announce"
    assert svc._repo.audits[0]["admin_id"] == "p:1"
    assert svc._repo.audits[0]["success"] == 1


@pytest.mark.asyncio
async def test_stop_disconnect_treated_initiated():
    err = SimpleNamespace(ok=False, status=None, error="network error")
    svc = _svc(err)
    res = await svc.stop("p:1", "umo", True)
    assert res.ok  # 断连=已发起
    assert svc._repo.audits[0]["success"] == 1


@pytest.mark.asyncio
async def test_save_http_error_audits_failure():
    err = SimpleNamespace(ok=False, status=500, error="http_status_500")
    svc = _svc(err)
    res = await svc.save("p:1", "umo", True)
    assert not res.ok
    assert svc._repo.audits[0]["success"] == 0
```

（`clock.now` 用 lambda 简化；真实 `Clock` 有 `now()` 方法——AdminService 内调 `self._clock.now()`。所有 public 方法 **`admin_id` 为首参**：`announce(admin_id, umo, is_group, message)`、`save/stop/shutdown(admin_id, umo, is_group[, ...])`。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/admin_service_test.py -v`
Expected: FAIL —— 模块不存在

- [ ] **Step 3: 建 admin_service.py（核心 + 无目标方法）**

新建，含 `AdminResult` dataclass + `AdminService`。核心私有 `_execute(umo, is_group, action, path, json_body, target_name=None, target_userid=None, detail="", initiated_ok_on_disconnect=False)`：resolve→world→post→审计→AdminResult。announce/save/shutdown/stop 调 `_execute`。**相对导入**：`from ..adapters.privacy_filter import hash_user_id`（先确认函数名/签名 `hash_user_id(salt, world_id, userid)`）。target_hash = `hash_user_id(self._salt, world_id, target_userid)` 仅当有 target_userid。审计 error 取 post_result.error。

关键片段：

```python
    async def _execute(self, admin_id, umo, is_group, *, action, path, json_body,
                       target_name=None, target_userid=None, detail="",
                       initiated_ok_on_disconnect=False):
        r = await self._routing.resolve(umo, None, is_group)
        if not r.ok:
            return AdminResult(ok=False, message_key="server_unknown", params={})
        server = r.server
        world = await self._repo.get_current_world(server.server_id)
        world_id = world.world_id if world is not None else ""
        resp = await self._post(server.server_id, path, json_body)
        ok = resp.ok or (initiated_ok_on_disconnect and resp.error == "network error")
        target_hash = (hash_user_id(self._salt, world_id, target_userid)
                       if target_userid else None)
        await self._repo.insert_audit(
            ts=self._clock.now(), admin_id=admin_id, action=action,
            server_name=server.name, target_name=target_name, target_hash=target_hash,
            detail=detail, success=1 if ok else 0,
            error=None if ok else resp.error,
        )
        return AdminResult(ok=ok, message_key=("admin_ok" if ok else "admin_failed"),
                           params={"server": server.name, "target": target_name or "",
                                   "error": resp.error or ""})
```

announce/save/shutdown/stop 各调 `_execute(admin_id, umo, is_group, action=..., path=..., json_body=...)`；`stop`/`shutdown` 传 `initiated_ok_on_disconnect=True`。例：

```python
    async def announce(self, admin_id, umo, is_group, message):
        return await self._execute(admin_id, umo, is_group, action="announce",
                                   path="announce", json_body={"message": message})

    async def stop(self, admin_id, umo, is_group):
        return await self._execute(admin_id, umo, is_group, action="stop",
                                   path="stop", json_body=None, initiated_ok_on_disconnect=True)
```

注：`admin_id` 是各 public 方法与 `_execute` 的**首参**（非实例态），T7 每次调用传入；`insert_audit(admin_id=admin_id, ...)`。避免实例级 `_current_admin` 竞态。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/admin_service_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/admin_service.py tests/unit/admin_service_test.py
git commit -m "feat(admin): AdminService 核心（announce/save/shutdown/stop + 审计 world_id hash）"
```

---

## Task 5: AdminService 目标解析 —— kick/ban/unban

**Files:**
- Modify: `palworld_terminal/application/admin_service.py`
- Test: `tests/unit/admin_service_test.py`（扩）

**Interfaces:**
- Produces: `async def resolve_target(server_id, token) -> TargetResult`（`TargetResult(kind: "userid"|"unique"|"multi"|"none", userid, name, candidates)`）；`async def kick(admin_id, umo, is_group, token, reason)`、`ban(...)`、`unban(admin_id, umo, is_group, userid)`。T7 消费。

- [ ] **Step 1: 写失败测试**

`admin_service_test.py` 加：

```python
def _svc_players(players):
    async def fetch(server_id, endpoint):
        return SimpleNamespace(ok=True, data={"players": players})
    async def post(server_id, path, json_body):
        return SimpleNamespace(ok=True, status=200, error=None)
    return AdminService(routing=_FakeRouting(), fetch=fetch, post=post,
                        repo=_FakeRepo(), salt=b"s", clock=SimpleNamespace(now=lambda: 1))


@pytest.mark.asyncio
async def test_resolve_target_direct_userid():
    svc = _svc_players([])
    t = await svc.resolve_target("s1", "steam_76561198000000000")
    assert t.kind == "userid" and t.userid == "steam_76561198000000000"


@pytest.mark.asyncio
async def test_resolve_target_by_name_unique():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    t = await svc.resolve_target("s1", "Alice")
    assert t.kind == "unique" and t.userid == "steam_1"


@pytest.mark.asyncio
async def test_resolve_target_multi():
    svc = _svc_players([{"name": "Bob", "userId": "steam_1"}, {"name": "Bob", "userId": "steam_2"}])
    t = await svc.resolve_target("s1", "Bob")
    assert t.kind == "multi" and len(t.candidates) == 2


@pytest.mark.asyncio
async def test_resolve_target_none():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    t = await svc.resolve_target("s1", "Zed")
    assert t.kind == "none"


@pytest.mark.asyncio
async def test_kick_by_name_audits_hashed_target():
    svc = _svc_players([{"name": "Alice", "userId": "steam_1"}])
    res = await svc.kick("p:1", "umo", True, "Alice", "afk")
    assert res.ok
    a = svc._repo.audits[0]
    assert a["action"] == "kick" and a["target_name"] == "Alice"
    assert a["target_hash"] and a["target_hash"] != "steam_1"   # 只 hash 不明文
```

（`/players` 响应结构 `{"players": [...]}` 与真实字段名 `userId` 须与 `privacy_filter.py:56` 对齐——先确认原始响应键。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/admin_service_test.py -k resolve_target -v`
Expected: FAIL

- [ ] **Step 3: 实现 resolve_target + kick/ban/unban**

`_USERID_PREFIXES = ("steam_",)`（钉死可识别前缀；文档说明冲突边界）。`resolve_target`：token 以前缀开头→`userid`；否则 `fetch(server_id, EndpointName.PLAYERS)` 取原始 `players`，按 `name` 精确匹配聚 `userId`；0/1/多→none/unique/multi。kick/ban 先 `resolve_target`，multi/none 直接返回对应 message_key（不 post、不审计）；unique/userid→`_execute(action, "kick", {"userid": uid, "message": reason}, target_name, uid, detail=reason)`。unban 直接 `_execute("unban", {"userid": userid})`（无名字解析）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/admin_service_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/admin_service.py tests/unit/admin_service_test.py
git commit -m "feat(admin): 目标解析（名字实时匹配/直传 userid）+ kick/ban/unban"
```

---

## Task 6: ConfirmationStore —— pending 状态机

**Files:**
- Create: `palworld_terminal/presentation/confirmation.py`
- Test: `tests/unit/confirmation_store_test.py`（新建）

**Interfaces:**
- Consumes: `Clock`。
- Produces: `PendingAction(command_str, group, exec_coro_factory 或 描述参数, server_id, umo, expiry)`；`ConfirmationStore(clock)`：`put(sender_id, pending)`、`claim(sender_id) -> PendingAction | None`（原子 pop + 过期判定）、`clear_all()`。T7 消费。

- [ ] **Step 1: 写失败测试**

```python
from types import SimpleNamespace

from palworld_terminal.presentation.confirmation import ConfirmationStore, PendingAction


class _Clock:
    def __init__(self, t): self.t = t
    def now(self): return self.t


def _p(expiry): return PendingAction(command_str="stop", group="server_admin_danger",
                                     payload={}, server_id="s", umo="u", expiry=expiry)


def test_put_and_claim():
    clk = _Clock(0)
    s = ConfirmationStore(clk)
    s.put("a", _p(expiry=100))
    got = s.claim("a")
    assert got is not None and got.command_str == "stop"


def test_claim_is_pop_no_double():
    s = ConfirmationStore(_Clock(0))
    s.put("a", _p(expiry=100))
    assert s.claim("a") is not None
    assert s.claim("a") is None   # 第二次拿不到（claim-then-execute 防双执行）


def test_claim_expired_returns_none():
    clk = _Clock(0)
    s = ConfirmationStore(clk)
    s.put("a", _p(expiry=50))
    clk.t = 60
    assert s.claim("a") is None


def test_overwrite_single_pending():
    s = ConfirmationStore(_Clock(0))
    s.put("a", _p(expiry=100))
    s.put("a", PendingAction(command_str="ban", group="server_admin_danger",
                             payload={}, server_id="s", umo="u", expiry=100))
    assert s.claim("a").command_str == "ban"


def test_clear_all():
    s = ConfirmationStore(_Clock(0))
    s.put("a", _p(expiry=100))
    s.clear_all()
    assert s.claim("a") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/confirmation_store_test.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..infrastructure.clock import Clock


@dataclass(slots=True)
class PendingAction:
    command_str: str
    group: str
    payload: dict[str, Any]
    server_id: str
    umo: str
    expiry: float


class ConfirmationStore:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._pending: dict[str, PendingAction] = {}

    def put(self, sender_id: str, pending: PendingAction) -> None:
        self._pending[sender_id] = pending   # 单条覆盖

    def claim(self, sender_id: str) -> PendingAction | None:
        p = self._pending.pop(sender_id, None)   # 原子 pop：claim-then-execute
        if p is None or p.expiry <= self._clock.now():
            return None
        return p

    def clear_all(self) -> None:
        self._pending.clear()
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/confirmation_store_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/confirmation.py tests/unit/confirmation_store_test.py
git commit -m "feat(confirm): ConfirmationStore pending 状态机（claim-then-execute + 注入 clock）"
```

---

## Task 7: Commands.admin_write 中央编排 + confirm + 装配

**Files:**
- Modify: `palworld_terminal/presentation/commands.py`、`palworld_terminal/container.py`
- Test: `tests/unit/commands_admin_write_test.py`（新建）

**Interfaces:**
- Consumes: `AdminService`（T4/T5）、`ConfirmationStore`（T6）、`self._cfg`、`self._clock`、`is_plugin_admin`。
- Produces: `Commands.admin_write(command_str, group, admin_id, umo, is_group, arg_str, is_admin) -> str`；`Commands.confirm(admin_id, umo, is_group, is_admin) -> str`（confirm 自身也过 admin 硬门）。T8 消费。Commands 构造签名 +`admin_service`、`confirmations`（`ConfirmationStore`）。

**门序（铁律，测试锁定）**：admin_write 内 **先** `if not is_admin: return L("admin_required")`（先于 feature）→ `if not features.enabled(group): return L("feature_disabled")` → 参数/目标解析 → danger+require_confirmation 分支存 pending 回预览 / 否则执行 → 返回消息（AdminResult→`L(result.message_key, **result.params)`）。confirm 内 **先** `if not is_admin: return L("admin_required")` → `claim`（None→`admin_no_pending`）→ 复检（`features.enabled(p.group)` + 重跑 `routing.resolve` 授权，任一失败→`admin_confirm_stale`）→ 按 payload 调 admin_service 执行 → 回显 `admin_confirm_done`。

- [ ] **Step 1: 写失败测试**

`tests/unit/commands_admin_write_test.py`：构造 Commands（注入 fake admin_service/confirmations/cfg），断言：
- 非管理员发任意写（组开/组关都）→ `admin_required`（门序：admin 先于 feature）。
- 管理员 + 组关 → `feature_disabled`。
- 管理员 + basic 组开 + announce → 直接执行（调 admin_service.announce）。
- 管理员 + danger 组开 + require_confirmation=False + stop → 直接执行。
- 管理员 + danger + require_confirmation=True + stop → 存 pending 回预览（不执行）；随后 confirm → 执行。
- confirm 无 pending → 「无待确认」。
- confirm 复检：pending 存在但 danger 组已关 → 丢弃回「已失效」。

（用 SimpleNamespace fake：admin_service 的方法记录调用；confirmations 用真 ConfirmationStore + 注入 _Clock。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_admin_write_test.py -v`
Expected: FAIL —— 无 admin_write

- [ ] **Step 3: 实现 admin_write + confirm**

`commands.py` 加两方法。admin_write 用 `command_str`→对应 admin_service 方法的分派表（announce/save/kick/unban/ban/shutdown/stop）。danger 集合 `{"ban","shutdown","stop"}`。执行分支：danger ∧ `self._cfg.server_admin.require_confirmation` → 构造 `PendingAction`（payload 存已解析参数）put，回 `L("admin_confirm_preview", ...)`；否则调 admin_service 方法直执，回其 message。参数解析（arg_str→目标/理由/秒数）用 `server_arg.parse_arg` 取尾 @server override 与剩余串（注意 §3 已知限制）。confirm：`claim`→None 回 `L("admin_no_pending")`；复检 `features.enabled(p.group)` 假 → 回 `L("admin_confirm_stale")`；重跑 `routing.resolve` 授权失败 → `admin_confirm_stale`；过则按 payload 调 admin_service 对应方法，回显 `L("admin_confirm_done", ...)`。

locale.py 加对应文案键（admin_required 已存；新增 feature_disabled 若无、admin_confirm_preview/done/stale/no_pending/admin_ok/admin_failed/target_multi/target_none 等）。

- [ ] **Step 4: 装配（container.py）**

`container.py`：构造 `AdminService`（传 routing、`_fetch`/新 `_post`、repo、salt、clock）+ `ConfirmationStore(clock)`；把二者注入 `Commands` 构造（更新 Commands `__init__` 签名 + 所有现有构造点，含测试 helper）。`_post` 回调照 `_fetch`（:158）——按 server_id 找 `_rest_clients[server_id].post(...)`。**注**：更新所有直接构造 `Commands(...)` 的测试（如 permission 的 `commands_permissions_test`）传新参（可传 None + 相关测试不触发写路径）。

- [ ] **Step 5: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_admin_write_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/presentation/commands.py palworld_terminal/presentation/locale.py palworld_terminal/container.py tests/unit/commands_admin_write_test.py
git commit -m "feat(cmd): admin_write 中央编排 + confirm 复检 + AdminService/ConfirmationStore 装配"
```

---

## Task 8: 注册 + main.py _guarded_admin + 8 handler + help 隔离 + 冒烟

**Files:**
- Modify: `presentation/command_registry.py`、`main.py`、`presentation/formatters.py`、`container.py`（若 _post 未在 T7 落）、`tests/unit/command_names_test.py`、`tests/unit/namespace_runtime_smoke_test.py`
- Test: 上述 + `tests/unit/formatters_admin_help_test.py`（新建）

**Interfaces:**
- Consumes: `Commands.admin_write`/`confirm`（T7）。
- Produces: 8 `@pal.command` handler + `confirm` handler 全过 `_guarded_admin`；help 对 server_admin_* 命令加 admin 门；PAL_COMMAND_STRINGS +8（含 confirm，共 26）。

- [ ] **Step 1: registry 三表 + command_names 硬编码断言更新（先红）**

`command_registry.py`：`COMMANDS` 加 `("announce","server_admin_basic")`…`("stop","server_admin_danger")` 7 项 + `("confirm","core")`；`HELP_LINE` 加 8 条（confirm 含）；`PAL_COMMAND_STRINGS` 加 8 串（announce/save/kick/unban/ban/shutdown/stop/confirm）。
`command_names_test.py::test_lockable_excludes_non_lockable`（:22-25）硬编码集合从 `{"server","whoami","help"}` 改到 11 项全集 `{server,whoami,help,confirm,announce,save,kick,unban,ban,shutdown,stop}`。

**恢复 T1 的桥接（关键）**：T1 因提前扩张 `config._NON_LOCKABLE` 而把 PR#18 的 `test_non_lockable_matches_registry_complement` 放宽成「子集检查 + 硬钉 8 预注册写命令」。本任务注册 8 写命令进 `PAL_COMMAND_STRINGS` + registry 非锁集扩张到 11 后，registry 侧与 config._NON_LOCKABLE 全等成立——**须把该测试收缩钉子（8→0）恢复为原全等断言** `config._NON_LOCKABLE == frozenset(PAL_COMMAND_STRINGS) − set(LOCKABLE_COMMANDS)`。注：registry 的 `LOCKABLE_COMMANDS` 定义（现 `PAL_COMMAND_STRINGS − {server,whoami,help}`）也须改为减 11 项非锁集（与 config._NON_LOCKABLE 同集），否则写命令会落进 LOCKABLE。

- [ ] **Step 2: help 角色隔离测试（先红）**

新建 `tests/unit/formatters_admin_help_test.py`：断言 `format_help` 在 `server_admin_basic` 启用但 `is_admin=False` 时**不含** `/pal kick`/`/pal ban`；`is_admin=True` 时含；`HELP_LINE["confirm"]` 不 KeyError。

- [ ] **Step 3: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_names_test.py tests/unit/formatters_admin_help_test.py -v`
Expected: FAIL（注册串不匹配 main.py / help 泄漏写命令）

- [ ] **Step 4: main.py _guarded_admin + 8 handler + confirm handler**

`main.py`：加 `_guarded_admin(event, command_str, call)`——照 `_guarded_cmd`（:152）的 inflight/busy 骨架，但**不做 admin_denied**（门在 admin_write 内），仅 busy+inflight 包裹 `call`。8 写 handler 各：

```python
    @pal.command("kick")
    async def kick(self, event):
        yield event.plain_result(await self._guarded_admin(event, "kick", lambda c: c.commands.admin_write(
            "kick", "server_admin_basic", self._sender_id(event), self._umo(event),
            self._is_group(event), self._admin_arg(event), c.commands.is_plugin_admin(self._sender_id(event)))))
```

（`self._admin_arg(event)` = 去掉命令词后的原始参数串；照现有 `_msg`/`server_arg` 取法。）confirm handler 走 `_guarded`（core、无 admin 门参数——但 confirm 内部仍 admin 硬门：admin_write 不管 confirm，confirm 方法自身开头 `if not is_admin` 判，故 handler 传 is_admin）。实际 confirm 也要 admin 门：

```python
    @pal.command("confirm")
    async def confirm(self, event):
        yield event.plain_result(await self._guarded(lambda c: c.commands.confirm(
            self._sender_id(event), self._umo(event), self._is_group(event),
            c.commands.is_plugin_admin(self._sender_id(event)))))
```

（confirm 方法签名加 is_admin，开头 `if not is_admin: return L("admin_required")`。）
`_apply_and_restart`（:179）成功分支末尾加 `self._container.commands.confirmations.clear_all()`（或经 Commands 暴露 `clear_pending()`）——config 热重载清 pending。
改 `@register(...)` 描述串去「(只读)」+ 版本（版本留 T15 统一，但描述串可现在改或 T15；建议 T15 统一改版本，本任务只加命令）。

- [ ] **Step 5: format_help 隔离**

`formatters.py::format_help`（:132-141）：遍历 COMMANDS 时，对 `group in {"server_admin_basic","server_admin_danger"}` 的命令加 `and is_admin` 条件（enabled 且 is_admin 才 append）。confirm（core）是否仅 admin 显示：一并加 `name=="confirm" → 需 is_admin`（confirm 对非管理员无意义）。

- [ ] **Step 6: 冒烟脚手架**

`namespace_runtime_smoke_test.py`：`_FakeRest`（:20）加 `async def post(self, *a, **k)` 返回 ok stub + `async def fetch/get` 若 AdminService 名字解析需要（种在线玩家）；features 种子（:77）加 `server_admin_basic: True, server_admin_danger: True`；`calls` 清单加 8 写命令（confirm 单独，danger 用 require_confirmation=False 直执避免 pending）；docstring 命令数 18→26。种一个 `permission_admins` 管理员匹配冒烟 sender，令写命令过 admin 门。

- [ ] **Step 7: 运行确认通过 + 全套 + mypy**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_names_test.py tests/unit/formatters_admin_help_test.py tests/unit/namespace_runtime_smoke_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS（26 命令注册 == PAL_COMMAND_STRINGS；help 隔离；冒烟走到写命令深分支）

- [ ] **Step 8: 提交**

```bash
git add palworld_terminal/presentation/command_registry.py main.py palworld_terminal/presentation/formatters.py palworld_terminal/container.py tests/unit/command_names_test.py tests/unit/formatters_admin_help_test.py tests/unit/namespace_runtime_smoke_test.py
git commit -m "feat(main): _guarded_admin 中央写门 + 8 handler + confirm + help 角色隔离"
```

---

## Task 9: 审计只读 web 端点 + 前端 DTO

**Files:**
- Modify: `presentation/web_api.py`、`presentation/config_view.py`、`main.py`
- Test: `tests/unit/web_api_audit_test.py`（新建）

**Interfaces:**
- Produces: `web_api.handle_audit_list(container, limit) -> tuple[int, dict]`；`config_view.audit_rows(rows) -> list[dict]`（DTO 整形）；main.py 注册 `/audit/list` 路由（门闩内 + guard + limit clamp）。T13 前端消费。

- [ ] **Step 1: 写失败测试**

`tests/unit/web_api_audit_test.py`：fake container.repo.list_audit 返回若干行，断言 `handle_audit_list` 返回 `{"ok": True, "audits": [...]}` 倒序、限 limit；container None/restarting → `{"ok": True, "audits": [], "restarting": True}`。config_view.audit_rows 整形（ts→可读、success→bool、target 组合 name+hash 尾段）。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_audit_test.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

`web_api.py` 加 `handle_audit_list`（照 `handle_status_overview` :14）：restarting/None → 空；否则 `rows = await container.repo.list_audit(limit)`，`return 200, {"ok": True, "audits": audit_rows(rows)}`。`config_view.py` 加 `audit_rows`。`main.py`：`register_web_api` 加 `/audit/list` GET，handler 在 `_inflight`/`_idle` 门闩内（照 `_web_status` :270），`limit = clamp(int(request.args.get("limit", 100)), 1, 500)`，`_has_identity`/`g.username` 鉴权。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_audit_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/web_api.py palworld_terminal/presentation/config_view.py main.py tests/unit/web_api_audit_test.py
git commit -m "feat(web): 审计只读端点 handle_audit_list + DTO + 路由（门闩/clamp）"
```

---

## Task 10: _conf_schema.json —— 两组 + server_admin

**Files:**
- Modify: `_conf_schema.json`
- Test: `tests/unit/conf_schema_test.py`（扩）

- [ ] **Step 1: 写失败测试**

```python
def test_server_admin_schema_present():
    import json
    from pathlib import Path
    s = json.loads((Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text(encoding="utf-8"))
    assert s["features"]["items"]["server_admin_basic"]["type"] == "bool"
    assert s["features"]["items"]["server_admin_danger"]["type"] == "bool"
    assert s["server_admin"]["type"] == "object"
    items = s["server_admin"]["items"]
    assert items["require_confirmation"]["type"] == "bool"
    assert items["confirmation_timeout"]["default"] == 30
    assert items["audit_retention_days"]["default"] == 180
```

- [ ] **Step 2: 运行确认失败** — `KeyError`

- [ ] **Step 3: 加 schema**

`_conf_schema.json`：`features.items` 加两 bool（默认 false，描述含安全告警「服务器写操作，仅授权管理员可用，默认关」）；顶层加 `server_admin` object（三字段 + 描述含 stop 丢档/OPEN 爆炸半径/审计留存告知）。

- [ ] **Step 4: 运行确认通过** + `./.venv/Scripts/python.exe -m pytest -q`

- [ ] **Step 5: 提交**

```bash
git add _conf_schema.json tests/unit/conf_schema_test.py
git commit -m "feat(schema): server_admin 两组 + 配置段（含安全告警）"
```

---

## Task 11: 前端 schema.ts + chapters.ts —— FEATURE 两组 + 审计章

**Files:**
- Modify: `frontend/src/lib/schema.ts`、`frontend/src/lib/chapters.ts`
- Test: `frontend/src/lib/*.test.ts`（扩）

**Interfaces:**
- Produces: `schema.ts` FEATURE 段两组；`chapters.ts` 加审计只读章（`kind` 区分）+ server_admin 配置块归属。T12/T13 消费。

- [ ] **Step 1: 写失败测试**（vitest）：断言 FEATURE 含 server_admin_basic/danger；CHAPTERS 含 `id:'audit'` 且 `kind` 标只读。

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm run test:run && cd ..`

- [ ] **Step 3: 实现**

`schema.ts` FEATURE 段加两组（label「服务器管控·基础/危险」）。`chapters.ts` `CHAPTERS` 加 `{ id: 'audit', label: '审计', group: '观测', kind: 'audit', blocks: [] }`（`kind` 新值 `'audit'`；若 kind 类型是联合需扩），server_admin 配置项归入功能分组章或新管控段。

- [ ] **Step 4: 运行确认通过** `cd frontend && npm run test:run && npm run typecheck && cd ..`

- [ ] **Step 5: 提交**

```bash
git add frontend/src/lib/schema.ts frontend/src/lib/chapters.ts frontend/src/lib/*.test.ts
git commit -m "feat(fe): FEATURE 两组 + 审计只读章定义"
```

---

## Task 12: 前端 SettingsPanel —— 两组开关 + server_admin 段

**Files:**
- Modify: `frontend/src/components/SettingsPanel.vue`、`frontend/src/lib/collect.ts`
- Test: `frontend/src/components/SettingsPanel.test.ts`、`collect.test.ts`（扩）

- [ ] **Step 1: 写失败测试**：功能分组章渲染两新开关；server_admin 段（require_confirmation 开关 + confirmation_timeout 数字 + audit_retention_days 数字）；collect 往返含 server_admin。

- [ ] **Step 2: 运行确认失败** `cd frontend && npm run test:run && cd ..`

- [ ] **Step 3: 实现**：SettingsPanel features 段加两 toggle（照现有 features 开关）；加 server_admin 配置块（照现有 object 段如 polling/history）；`collect.ts` `collectBody` 加 `server_admin`（照现有 object 收集）+ `SettingsState` 加字段 + applyConfig `?? {}` 缺键容错。**不得用 v-html**。

- [ ] **Step 4: 运行确认通过** `cd frontend && npm run test:run && npm run typecheck && cd .. && ./.venv/Scripts/python.exe -m pytest tests/unit/frontend_source_test.py -v`

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SettingsPanel.vue frontend/src/lib/collect.ts frontend/src/components/SettingsPanel.test.ts frontend/src/lib/collect.test.ts
git commit -m "feat(fe): 设置页两组开关 + server_admin 配置段"
```

---

## Task 13: 前端 AuditPanel.vue + App.vue kind 路由

**Files:**
- Create: `frontend/src/components/AuditPanel.vue`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/components/AuditPanel.test.ts`（新建）、`frontend/src/App.test.ts`（扩）

**Interfaces:**
- Consumes: `/audit/list` 端点（T9）。
- Produces: `AuditPanel`（自 fetch 审计、只读表、空态）；`App.vue` 按 `kind` 路由到 AuditPanel（现硬编码 `chapter==='status'` 二分改造）。

- [ ] **Step 1: 写失败测试**：AuditPanel mount → fetch mock 返回行 → 渲染表（时间/管理员/动作/目标/服务器/结果）；空数组 → 「暂无管理操作记录」。App.test：chapter=audit → 渲染 AuditPanel（非 SettingsPanel/StatusPanel）。

- [ ] **Step 2: 运行确认失败** `cd frontend && npm run test:run && cd ..`

- [ ] **Step 3: 实现 AuditPanel.vue**：照 `StatusPanel.vue` 的 fetch + 只读渲染范式，但 fetch `/audit/list`、渲染通用表。**不得用 v-html**（目标名用 `{{ }}` 插值）。

- [ ] **Step 4: App.vue 路由改**：现 `App.vue:54-55` `SettingsPanel v-show="chapter!=='status'"` / `StatusPanel v-if="chapter==='status'"`。改为按当前章的 `kind` 分派：status→StatusPanel、audit→AuditPanel、其余→SettingsPanel（保持 SettingsPanel 对非只读章 v-show 以留状态）。用 chapters 查当前章 kind 的 computed。

- [ ] **Step 5: 运行确认通过 + 源码红线** `cd frontend && npm run test:run && npm run typecheck && cd .. && ./.venv/Scripts/python.exe -m pytest tests/unit/frontend_source_test.py -v`

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/AuditPanel.vue frontend/src/App.vue frontend/src/components/AuditPanel.test.ts frontend/src/App.test.ts
git commit -m "feat(fe): AuditPanel 只读审计页 + App.vue 按 kind 路由"
```

---

## Task 14: 重建前端产物

**Files:** Modify `pages/settings/`

- [ ] **Step 1: 构建** `cd frontend && npm run build && cd ..`
- [ ] **Step 2: verify-bundle** `node frontend/scripts/verify-bundle.mjs`（恰 1 JS）
- [ ] **Step 3: no-drift 自检** `git add pages/settings && git status --short pages/settings`（有 index.js/style.css 变更）
- [ ] **Step 4: 全套回归** `cd frontend && npm run test:run && cd .. && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
- [ ] **Step 5: 提交**

```bash
git add pages/settings
git commit -m "build(fe): 服务器管控设置页/审计页单文件产物"
```

---

## Task 15: 文档 + 只读承诺迁移 + 版本 v0.9.0

**Files:**
- Modify: `docs/commands.md`、`docs/configuration.md`、`README.md`、`frontend/src/App.vue`（副标题）、`tests/unit/readme_test.py`、`metadata.yaml`、`main.py`、`palworld_terminal/__init__.py`、`palworld_terminal/adapters/palworld_rest.py`（docstring）、`tests/unit/phase1_smoke_test.py`、`tests/unit/skeleton_test.py`

**注**：App.vue 副标题改动须在 T13 后（T14 build 前）落，否则产物不含——**若 T13/T14 已定稿**，本任务改 App.vue 副标题须**再 build 一次并提交产物**（或把副标题改并入 T13）。**决策**：把 App.vue 副标题从「只读」改到本任务，本任务末尾**重跑 build + 提交产物**。

- [ ] **Step 1: readme_test 锚点 + 版本断言（先红）**

`readme_test.py`：现锚点 `"不控制服务器"`（:15）改为新只读→受控写表述的锚点（如 `"受控写"`、`"仅授权管理员"`）；命令表加 `/pal announce`…`/pal confirm`；新增权限/审计说明锚点。`phase1_smoke_test.py`/`skeleton_test.py` 版本 `0.8.7`→`0.9.0`。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py -v`
Expected: FAIL

- [ ] **Step 3: 文档改写**

- `docs/commands.md`：加 8 写命令 + confirm（标 basic/danger、管理员专属、danger 二次确认、stop 丢档告警）；新增「服务器管控」节（三层安全模型 + 审计）。
- `docs/configuration.md`：加 `server_admin_basic/danger` 两组 + `server_admin` 段（require_confirmation/confirmation_timeout/audit_retention_days）+ 安全告知（OPEN 爆炸半径、stop 丢档、审计留存/PII、名字解析绕过隐私过滤对管理员合理）。
- `README.md`：定位从「只读」改「受控写」；特性加「服务器管控（默认关/仅管理员/审计）」；安全节加 OPEN 爆炸半径；命令计数（18→26）；版本徽章 v0.9.0。
- `palworld_rest.py`、`__init__.py` docstring 去「只读」绝对表述。

- [ ] **Step 4: 版本四源 + App.vue 副标题**

`metadata.yaml` v0.9.0；`main.py @register` 版本 + 描述串去「(只读)」；`__init__.py __version__="0.9.0"`；`App.vue` 副标题「Palworld 服务器监测 · 只读」→「Palworld 服务器监测与管控」。

- [ ] **Step 5: 重跑 build（因 App.vue 改）+ 运行确认通过 + grep 无残留**

Run:
```bash
cd frontend && npm run build && cd ..
node frontend/scripts/verify-bundle.mjs
./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py -v
./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/
```
Expected: PASS（grep 确认无 `v0.8.7` 残留于版本源、无遗留「只读」绝对承诺）

- [ ] **Step 6: 提交**

```bash
git add docs/commands.md docs/configuration.md README.md frontend/src/App.vue pages/settings tests/unit/readme_test.py metadata.yaml main.py palworld_terminal/__init__.py palworld_terminal/adapters/palworld_rest.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py
git commit -m "docs+chore: 服务器管控文档/只读承诺迁移/安全告知 + 版本 v0.9.0"
```

---

## 收尾：整体验证

- [ ] **全套 + lint + mypy + 前端 + no-drift**

Run:
```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
cd frontend && npm run test:run && npm run build && cd ..
node frontend/scripts/verify-bundle.mjs
git diff --exit-code -- pages/settings
```
Expected: 全绿；no-drift 无差异。

- [ ] **安全关键路径单独复核**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_admin_write_test.py tests/unit/confirmation_store_test.py tests/unit/command_names_test.py tests/unit/formatters_admin_help_test.py tests/unit/namespace_runtime_smoke_test.py tests/unit/no_absolute_self_import_test.py -v`
Expected: PASS —— 门序 admin 先于 feature、claim-then-execute、confirm 复检、help 隔离、命令锚定、无绝对自导入。
