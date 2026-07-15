# 有条件模式互转 + 转移引导（Phase 2A 后端）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为设置页提供**有条件、带引导、带二次确认**的 single↔multi 模式互转后端：显式子集授权迁移（move 语义、跨介质、切回不复活）、可选 server 级 DB purge、全程审计、孤儿数据清理入口——通过 5 个新 Repository 方法 + 4 个 web 端点实现。

**Architecture:** 复用既有 web_api 纯编排范式（副作用经参数注入、业务成败恒 HTTP 200、`payload['ok']` 区分）。破坏性转移是**单次后端原子编排**：全程持 `_save_lock`、迁移读先于 reload、single→multi 目标预绑先于清源、reload 失败即中止、post-reload move 清源 + 可选 purge、最外层审计（写异常独立隔离）。config 文件与 SQLite 无真 2PC——config 改动为主（失败即回滚、模式不变、DB 未动），post-reload DB 写失败不回滚已切模式、改为如实审计 + 可执行回执，孤儿清理端点兜底重试。

**Tech Stack:** Python 3.11、aiosqlite（`Database.write_tx`/`query`/`execute_write`）、asyncio.Lock、Quart（薄壳 Star 层）、pytest（`asyncio_mode=auto`）、ruff、mypy。前端留 Phase 2B、**本计划不写**。

## Global Constraints

以下为项目级铁律（spec §8 + MEMORY），逐字适用于**每个任务**：

- **版本号不变（保持 v0.9.7）**——不动任何版本源（`metadata.yaml`/`__init__.py`/`main.py` 注册串）、不改任何版本断言。
- **相对导入红线**：包内一律相对导入（`from ..config import ...` / `from .config_view import ...`）；绝不写 `from palworld_terminal...` 的包内绝对自导入（AstrBot 命名空间加载下运行时炸，测试环境掩盖；已有 `no_absolute_self_import_test.py` 防回归）。
- **Windows 测试命令**：`./.venv/Scripts/python.exe -m pytest`（单文件：`./.venv/Scripts/python.exe -m pytest tests/unit/<file>.py -v`）。
- **lint / 类型**：`ruff check .`（select = E/F/W/I/B/UP，**无 S 规则**，故硬编码表名的 f-string SQL 合规）；`mypy palworld_terminal`（mypy 只查 `palworld_terminal/`；仓库根 `main.py` **不在** mypy 范围，但 `palworld_terminal/presentation/web_api.py` 在范围内）。
- **提交不出现 Claude**：commit message 正文与尾行都不提 Claude、不加 Co-Authored-By（全局已设 `attribution.commit=""`）。
- **审计字段（本功能订正）**：`admin_id` **明文**存 `_current_username()`（Dashboard 登录用户名，非 hash）；`server_name` 列 `NOT NULL`（`migrations.py:248`），**绝不传 None**——multi→single 用保留台名 / single→multi 用绑定目标台名 / 皆无时用非空哨兵 `"mode_transfer"`（orphan 端点用 `"orphan_purge"`）。审计留存沿 `audit_retention_days` 折进现有 `prune`，本计划不新增留存逻辑。
- **purge 表清单以 `migrations.py` 建表为准**：12 张 world_id 键表 = `players` / `player_sessions` / `player_observations` / `guilds` / `palboxes` / `bases` / `base_observations` / `world_metrics` / `world_events` / `daily_aggregates` / `player_bindings` / `hidden_players`；外加 3 张 server_id 行表 `group_servers` / `worlds` / `servers`。**`unknown_classes` 是全局类字典、非 per-server、绝不碰**。
- **鉴权不加严**：四端点鉴权与 `config/save` 同级（`_has_identity`，Dashboard 登录）；未鉴权 → `_deny_unauthorized`。四端点不受 Phase 1 首次设置闸约束。
- **DB 事实（勘探确证，命门）**：多世界运行时授权真相在 DB `group_servers(allowed=1)`；config `group_bindings` 只是启动一次性 seed（`container.py:102`，seed-only 不覆盖运行时）；单世界授权在**顶层** config 键 `single_allowed_groups`（**非** `routing` 子键——`config.py:451` 读 `raw['single_allowed_groups']`，写进 `routing` 会过 schema 但 `parse_config` 永不读→静默丢失）。`world_mode` 在 `routing` 子键（`config.py:450`）。`_MAX_LIST = 200`（`config_view.py:55`）。

---

## Task 依赖顺序总览

Repository 五方法（T1–T4）→ 预览端点（T5）→ 转移编排核心（T6）→ 转移编排 purge 扩展（T7）→ 孤儿端点（T8）→ main.py 注册 + Star 薄壳 + 全后端终检（T9）。前端（模式切换控件 / 确认框 / 向导 / 孤儿入口）**留 Phase 2B**。

---

### Task 1: Repository 读方法 `list_allowed_bindings` + `list_orphan_server_ids`

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（在 `# ---- bindings / routing ----` 段内，`cleanup_orphan_bindings` 之后追加两个方法）
- Test: `tests/unit/repository_mode_transfer_test.py`（新建）

**Interfaces:**
- Consumes: `Database.query(sql, params) -> list[aiosqlite.Row]`（`database.py:75`）。
- Produces:
  - `async def list_allowed_bindings(self) -> list[tuple[str, str]]` —— 全表 `allowed=1` 的 `(umo, server_id)` 对（不聚合）。
  - `async def list_orphan_server_ids(self, valid_server_ids: set[str]) -> list[str]` —— `servers`∪`worlds`∪`group_servers` 的 distinct server_id 中不在 `valid_server_ids` 的，`sorted` 去重。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/repository_mode_transfer_test.py`：

```python
import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.config import ServerConfig
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


def _srv(name, enabled=True, password="pw", base_url="http://h:8212"):
    return ServerConfig(
        server_id=name, name=name, enabled=enabled,
        base_url=base_url, username="admin", password=password,
        timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_list_allowed_bindings_only_allowed_pairs(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")   # u1→a allowed+active
    await repo.set_active("u1", "b")   # u1→b allowed+active（active 唯一转到 b，a 仍 allowed=1）
    await repo.set_active("u2", "a")   # u2→a allowed
    await repo.revoke("u2", "a")       # u2 撤销（allowed 行删除）
    pairs = await repo.list_allowed_bindings()
    assert set(pairs) == {("u1", "a"), ("u1", "b")}
    # 跨 umo/跨 server 聚合由调用方做；本方法只返回原始对
    assert ("u2", "a") not in pairs


async def test_list_orphan_server_ids_excludes_valid(repo):
    await repo.sync_servers([_srv("a"), _srv("b"), _srv("ghost")])
    await repo.set_active("u1", "b")
    # ghost 在 servers 表但不在 valid → 孤儿；b 在 group_servers 但也在 valid → 非孤儿
    orphans = await repo.list_orphan_server_ids({"a", "b"})
    assert orphans == ["ghost"]


async def test_list_orphan_server_ids_empty_when_all_valid(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    assert await repo.list_orphan_server_ids({"a", "b"}) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -v`
Expected: FAIL —— `AttributeError: 'Repository' object has no attribute 'list_allowed_bindings'`。

- [ ] **Step 3: 实现两个方法**

在 `sqlite_repository.py` 的 `cleanup_orphan_bindings` 方法之后（`get_binding_active` 之前）插入：

```python
    async def list_allowed_bindings(self) -> list[tuple[str, str]]:
        """全表 allowed=1 的 (umo, server_id) 对（不聚合）。供预览端点按 umo 聚合，
        以及 multi→single 迁移的真实源集（distinct umo）与 migrate_umos ⊆ 源 校验。"""
        rows = await self._db.query(
            "SELECT umo, server_id FROM group_servers WHERE allowed=1"
        )
        return [(r[0], r[1]) for r in rows]

    async def list_orphan_server_ids(self, valid_server_ids: set[str]) -> list[str]:
        """DB 中出现（servers∪worlds∪group_servers）但不在 valid_server_ids 的
        server_id——供孤儿清理端点列待清台。UNION 去重、sorted 稳定序。"""
        rows = await self._db.query(
            "SELECT server_id FROM servers "
            "UNION SELECT server_id FROM worlds "
            "UNION SELECT server_id FROM group_servers"
        )
        seen = {r[0] for r in rows}
        return sorted(sid for sid in seen if sid not in valid_server_ids)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/sqlite_repository.py tests/unit/repository_mode_transfer_test.py
git commit -m "feat: Repository list_allowed_bindings + list_orphan_server_ids"
```

---

### Task 2: Repository `bind_umos_to_server`（active pin 二步写、one-active-per-umo）

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（`list_orphan_server_ids` 之后追加）
- Test: `tests/unit/repository_mode_transfer_test.py`（追加）

**Interfaces:**
- Consumes: `Database.write_tx()`（`database.py:64`，yield 连接、成功 commit、异常 rollback）；`self._clock.now() -> int`。
- Produces: `async def bind_umos_to_server(self, umos: list[str], server_id: str) -> None` —— 单 `write_tx` 内对每个 umo：`allowed=1` 恒置；该 umo 尚无任何 `active=1` 时把本行 `active` 升到 1，否则保持既有（不夺别台 active）。保 `get_binding_active` 依赖的每 umo ≤1 active。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/repository_mode_transfer_test.py` 追加：

```python
async def test_bind_umos_sets_allowed_and_active_when_no_prior(repo):
    await repo.sync_servers([_srv("a")])
    await repo.bind_umos_to_server(["u1", "u2"], "a")
    assert await repo.get_allowed("u1") == {"a"}
    assert await repo.get_allowed("u2") == {"a"}
    assert await repo.get_binding_active("u1") == "a"   # 无既有 active → 置 active=1
    assert await repo.get_binding_active("u2") == "a"


async def test_bind_umos_does_not_steal_existing_active(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "b")               # u1 既有 active 在别台 b
    await repo.bind_umos_to_server(["u1"], "a")     # 绑到 a
    assert await repo.get_allowed("u1") == {"a", "b"}   # allowed 累积
    assert await repo.get_binding_active("u1") == "b"   # 既有 active 不被夺
    # 断言每 umo active=1 行 ≤1
    rows = await repo._db.query(
        "SELECT COUNT(*) FROM group_servers WHERE umo='u1' AND active=1")
    assert rows[0][0] == 1


async def test_bind_umos_promotes_preexisting_inactive_row(repo):
    # active pin 边角：(umo,target) 行已存在且 active=0、该 umo 无其它 active →
    # bind 后本行 active 被置 1（不能只靠 ON CONFLICT SET allowed=1 漏置 active）。
    await repo.sync_servers([_srv("a")])
    # 造一个 allowed=1, active=0 的既存行（模拟 seed 早于绑定的历史场景）
    await repo._db.execute_write(
        "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES ('u1','a',1,0,1)")
    await repo.bind_umos_to_server(["u1"], "a")
    assert await repo.get_binding_active("u1") == "a"   # 升到 active=1


async def test_bind_umos_keeps_inactive_when_other_active_exists(repo):
    # (umo,target) 预存 active=0，但该 umo 别台已有 active → 保持 active=0、不夺。
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "b")   # 别台 active
    await repo._db.execute_write(
        "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES ('u1','a',1,0,1)")
    await repo.bind_umos_to_server(["u1"], "a")
    assert await repo.get_binding_active("u1") == "b"
    rows = await repo._db.query(
        "SELECT active FROM group_servers WHERE umo='u1' AND server_id='a'")
    assert rows[0][0] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -k bind_umos -v`
Expected: FAIL —— `AttributeError: ... 'bind_umos_to_server'`。

- [ ] **Step 3: 实现方法**

在 `list_orphan_server_ids` 之后插入：

```python
    async def bind_umos_to_server(self, umos: list[str], server_id: str) -> None:
        """批量把 umos 绑到 server_id：allowed=1 恒置；active pin——该 umo 尚无任何
        active 行时把本行 active 升到 1，否则保持既有（不夺别台 active）。镜像
        seed_bindings seed-only-active + set_active one-active-per-umo 不变量。"""
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            for umo in umos:
                cursor = await conn.execute(
                    "SELECT 1 FROM group_servers WHERE umo=? AND active=1 LIMIT 1",
                    (umo,),
                )
                has_active = await cursor.fetchone()
                await cursor.close()
                want_active = 0 if has_active else 1
                await conn.execute(
                    "INSERT INTO group_servers "
                    "(umo, server_id, allowed, active, updated_at) "
                    "VALUES (?, ?, 1, ?, ?) "
                    "ON CONFLICT(umo, server_id) DO UPDATE SET "
                    "  allowed=1, "
                    "  active=CASE WHEN ?=1 THEN 1 ELSE group_servers.active END, "
                    "  updated_at=excluded.updated_at",
                    (umo, server_id, want_active, now, want_active),
                )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/sqlite_repository.py tests/unit/repository_mode_transfer_test.py
git commit -m "feat: Repository bind_umos_to_server（active pin 二步写）"
```

---

### Task 3: Repository `clear_all_group_servers`

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（`bind_umos_to_server` 之后追加）
- Test: `tests/unit/repository_mode_transfer_test.py`（追加）

**Interfaces:**
- Consumes: `Database.write_tx()`。
- Produces: `async def clear_all_group_servers(self) -> int` —— `DELETE FROM group_servers` 全表，返回删除行数。

- [ ] **Step 1: 写失败测试**

追加：

```python
async def test_clear_all_group_servers_wipes_and_returns_count(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")
    await repo.set_active("u2", "b")
    # 无关表不受影响
    await repo._db.execute_write(
        "INSERT INTO worlds (world_id, server_id, worldguid, epoch) "
        "VALUES ('a:w', 'a', 'g', 0)")
    cleared = await repo.clear_all_group_servers()
    assert cleared == 2
    assert await repo.get_allowed("u1") == set()
    assert await repo.get_allowed("u2") == set()
    # worlds 未被误删
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds")
    assert rows[0][0] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -k clear_all -v`
Expected: FAIL —— `AttributeError: ... 'clear_all_group_servers'`。

- [ ] **Step 3: 实现方法**

```python
    async def clear_all_group_servers(self) -> int:
        """清空全部 DB group_servers（multi→single move 清源）。返回删除行数。"""
        async with self._db.write_tx() as conn:
            cursor = await conn.execute("DELETE FROM group_servers")
            return cursor.rowcount
```

- [ ] **Step 4: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -k clear_all -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/sqlite_repository.py tests/unit/repository_mode_transfer_test.py
git commit -m "feat: Repository clear_all_group_servers"
```

---

### Task 4: Repository `purge_server_data`（12 表 + 空 world_id 集短路 + 隔离，最险务必厚测）

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（`clear_all_group_servers` 之后追加）
- Test: `tests/unit/repository_mode_transfer_test.py`（追加）

**Interfaces:**
- Consumes: `Database.query` / `Database.write_tx`。
- Produces: `async def purge_server_data(self, server_id: str) -> dict[str, int]` —— 解析该 server 的 world_id 集（`SELECT world_id FROM worlds WHERE server_id=?`），单 `write_tx` 内逐表删 12 张 world_id 键表（**空集短路：跳过 12 表 DELETE、绝不发空 `IN ()`**；非空用参数化 `IN (?,?,…)`），再删 `group_servers`/`worlds`/`servers` 的 server_id 行。返回各表删除计数 dict。

- [ ] **Step 1: 写失败测试**

追加（含 12 表 seed、空集短路、隔离）：

```python
async def _seed_world_data(repo, server_id, world_id):
    """给 (server_id, world_id) 造齐 12 张 world_id 键表各 1 行 + servers/group_servers。

    servers/group_servers 用 INSERT OR IGNORE：转移 purge 测试里该 server 行可能已被
    harness 的 sync_servers 建过（PK 冲突），OR IGNORE 保持幂等；world_id 键表用全新
    world_id 无冲突、普通 INSERT。
    """
    await repo._db.execute_write(
        "INSERT OR IGNORE INTO servers (server_id, name, enabled) VALUES (?, ?, 1)",
        (server_id, server_id))
    await repo._db.execute_write(
        "INSERT INTO worlds (world_id, server_id, worldguid, epoch) VALUES (?, ?, 'g', 0)",
        (world_id, server_id))
    await repo._db.execute_write(
        "INSERT OR IGNORE INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES (?, ?, 1, 1, 1)", (f"umo-{server_id}", server_id))
    stmts = [
        ("INSERT INTO players (player_key, world_id) VALUES ('p', ?)", (world_id,)),
        ("INSERT INTO player_sessions (world_id, player_key, joined_at, last_confirmed_at, status) "
         "VALUES (?, 'p', 1, 1, 'active')", (world_id,)),
        ("INSERT INTO player_observations (world_id, player_key, observed_at) VALUES (?, 'p', 1)", (world_id,)),
        ("INSERT INTO guilds (guild_key, world_id) VALUES ('g', ?)", (world_id,)),
        ("INSERT INTO palboxes (palbox_key, world_id, position_cell) VALUES ('pb', ?, 'c')", (world_id,)),
        ("INSERT INTO bases (base_key, world_id, palbox_key, confidence) VALUES ('b', ?, 'pb', 'high')", (world_id,)),
        ("INSERT INTO base_observations (world_id, base_key, observed_at) VALUES (?, 'b', 1)", (world_id,)),
        ("INSERT INTO world_metrics (world_id, observed_at) VALUES (?, 1)", (world_id,)),
        ("INSERT INTO world_events (world_id, event_type, subject_type, occurred_at, confirmed_at, "
         "visibility, confidence, dedup_key) VALUES (?, 'e', 's', 1, 1, 'public', 'high', ?)",
         (world_id, f"dk-{world_id}")),
        ("INSERT INTO daily_aggregates (world_id, day, key, value_json) VALUES (?, 'd', 'k', '1')", (world_id,)),
        ("INSERT INTO player_bindings (platform_hash, world_id, player_key, created_at) "
         "VALUES ('ph', ?, 'p', 1)", (world_id,)),
        ("INSERT INTO hidden_players (world_id, player_key, hidden_by, created_at) "
         "VALUES (?, 'p', 'admin', 1)", (world_id,)),
    ]
    for sql, params in stmts:
        await repo._db.execute_write(sql, params)


_WORLD_TABLES = ["players", "player_sessions", "player_observations", "guilds",
                 "palboxes", "bases", "base_observations", "world_metrics",
                 "world_events", "daily_aggregates", "player_bindings", "hidden_players"]


async def test_purge_server_data_wipes_all_world_tables(repo):
    await _seed_world_data(repo, "a", "a:w")
    counts = await repo.purge_server_data("a")
    for t in _WORLD_TABLES:
        assert counts[t] == 1, t
        rows = await repo._db.query(f"SELECT COUNT(*) FROM {t}")
        assert rows[0][0] == 0, t
    for t in ("group_servers", "worlds", "servers"):
        assert counts[t] == 1, t
        rows = await repo._db.query(f"SELECT COUNT(*) FROM {t}")
        assert rows[0][0] == 0, t


async def test_purge_server_data_empty_world_set_short_circuits(repo):
    # 从未轮询台：servers 有行、worlds 无行 → world_id 集为空。
    # 绝不发空 IN ()（SQLite 语法错），只删三张 server 行、12 表零计数、write_tx 不整台回滚。
    await repo._db.execute_write(
        "INSERT INTO servers (server_id, name, enabled) VALUES ('a','a',1)")
    await repo._db.execute_write(
        "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES ('u','a',1,1,1)")
    counts = await repo.purge_server_data("a")   # 不抛 sqlite3.OperationalError
    for t in _WORLD_TABLES:
        assert counts[t] == 0
    assert counts["servers"] == 1 and counts["group_servers"] == 1
    rows = await repo._db.query("SELECT COUNT(*) FROM servers")
    assert rows[0][0] == 0   # 三张 server 行确被删


async def test_purge_server_data_isolates_other_server(repo):
    await _seed_world_data(repo, "a", "a:w")
    await _seed_world_data(repo, "b", "b:w")
    await repo.purge_server_data("a")
    # b 的数据一行不少
    for t in _WORLD_TABLES:
        rows = await repo._db.query(f"SELECT COUNT(*) FROM {t}")
        assert rows[0][0] == 1, t
    rows = await repo._db.query("SELECT server_id FROM servers")
    assert [r[0] for r in rows] == ["b"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -k purge -v`
Expected: FAIL —— `AttributeError: ... 'purge_server_data'`。

- [ ] **Step 3: 实现方法**

```python
    _PURGE_WORLD_TABLES = (
        "players", "player_sessions", "player_observations", "guilds",
        "palboxes", "bases", "base_observations", "world_metrics",
        "world_events", "daily_aggregates", "player_bindings", "hidden_players",
    )

    async def purge_server_data(self, server_id: str) -> dict[str, int]:
        """server 级 purge：解析该 server 的 world_id 集 → 逐表删 12 张 world_id 键表 +
        删 group_servers/worlds/servers 的 server_id 行。单台一个 write_tx（任一 DELETE
        抛错整台回滚）。空 world_id 集短路（跳过 12 表、绝不发空 IN ()）。返回各表计数。"""
        rows = await self._db.query(
            "SELECT world_id FROM worlds WHERE server_id=?", (server_id,)
        )
        world_ids = [r[0] for r in rows]
        counts: dict[str, int] = {}
        async with self._db.write_tx() as conn:
            if world_ids:
                placeholders = ",".join("?" for _ in world_ids)
                for table in self._PURGE_WORLD_TABLES:
                    cursor = await conn.execute(
                        f"DELETE FROM {table} WHERE world_id IN ({placeholders})",
                        tuple(world_ids),
                    )
                    counts[table] = cursor.rowcount
                    await cursor.close()
            else:
                for table in self._PURGE_WORLD_TABLES:
                    counts[table] = 0
            for table in ("group_servers", "worlds", "servers"):
                cursor = await conn.execute(
                    f"DELETE FROM {table} WHERE server_id=?", (server_id,)
                )
                counts[table] = cursor.rowcount
                await cursor.close()
        return counts
```

> f-string 仅内联硬编码常量表名（`_PURGE_WORLD_TABLES` / 三张 server 表），world_id 值走参数化 `IN (?,…)` 占位——无注入面；ruff 未启用 S 规则，合规。

- [ ] **Step 4: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/repository_mode_transfer_test.py -v`
Expected: PASS（全 Task 1–4 仓库测试通过）。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/sqlite_repository.py tests/unit/repository_mode_transfer_test.py
git commit -m "feat: Repository purge_server_data（12 表 + 空集短路 + 隔离）"
```

---

### Task 5: 预览端点 `handle_mode_transfer_preview`（GET，只读）

**Files:**
- Modify: `palworld_terminal/presentation/web_api.py`（新增 handler + 顶部补 import）
- Test: `tests/unit/web_api_mode_preview_test.py`（新建）

**Interfaces:**
- Consumes: `container.config.servers`（`ServerConfig`，有 `.server_id`/`.name`/`.ready`）；`container.repo.list_allowed_bindings()`（T1）；`container.config.routing.single_allowed_groups`（`AllowedGroupEntry`，有 `.umo`/`.note`）。
- Produces: `async def handle_mode_transfer_preview(container, restarting, target) -> tuple[int, dict]`：
  - `restarting or container is None` → `{ok:True, restarting:True}`。
  - `target=="single"`（multi→single）→ `{ok:True, ready_servers:[{server_id,name}], bindings:[{umo, server_ids:[...]}]}`。
  - `target=="multi"`（single→multi）→ `{ok:True, ready_servers:[{server_id,name}], allowed_groups:[{umo,note}]}`。
  - `target` 非法 → `{ok:False, error:"invalid_target"}`。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/web_api_mode_preview_test.py`：

```python
from palworld_terminal.presentation.web_api import handle_mode_transfer_preview


class _Srv:
    def __init__(self, name, ready=True):
        self.name = name
        self.server_id = name
        self.ready = ready


class _Entry:
    def __init__(self, umo, note=""):
        self.umo = umo
        self.note = note


class _Routing:
    def __init__(self, entries):
        self.single_allowed_groups = entries


class _Cfg:
    def __init__(self, servers, entries):
        self.servers = servers
        self.routing = _Routing(entries)


class _Repo:
    def __init__(self, pairs):
        self._pairs = pairs

    async def list_allowed_bindings(self):
        return self._pairs


class _Container:
    def __init__(self, servers, entries, pairs):
        self.config = _Cfg(servers, entries)
        self.repo = _Repo(pairs)


async def test_preview_restarting_empty():
    code, p = await handle_mode_transfer_preview(None, True, "single")
    assert code == 200 and p["restarting"] is True


async def test_preview_multi_to_single_aggregates_bindings():
    c = _Container([_Srv("a"), _Srv("b", ready=False)], [],
                   [("u1", "a"), ("u1", "b"), ("u2", "a")])
    code, p = await handle_mode_transfer_preview(c, False, "single")
    assert code == 200 and p["ok"] is True
    # 仅就绪台作保留台候选权威源
    assert p["ready_servers"] == [{"server_id": "a", "name": "a"}]
    agg = {b["umo"]: sorted(b["server_ids"]) for b in p["bindings"]}
    assert agg == {"u1": ["a", "b"], "u2": ["a"]}


async def test_preview_single_to_multi_returns_allowed_groups():
    c = _Container([_Srv("a")], [_Entry("u1", "note1"), _Entry("u2")], [])
    code, p = await handle_mode_transfer_preview(c, False, "multi")
    assert p["ok"] is True
    assert p["ready_servers"] == [{"server_id": "a", "name": "a"}]
    assert p["allowed_groups"] == [{"umo": "u1", "note": "note1"},
                                   {"umo": "u2", "note": ""}]


async def test_preview_invalid_target():
    c = _Container([_Srv("a")], [], [])
    code, p = await handle_mode_transfer_preview(c, False, "bogus")
    assert p["ok"] is False and p["error"] == "invalid_target"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_mode_preview_test.py -v`
Expected: FAIL —— `ImportError: cannot import name 'handle_mode_transfer_preview'`。

- [ ] **Step 3: 补 import + 实现 handler**

在 `web_api.py` 顶部 import 段（`from .config_view import ...` 那行）改为一并引入将来 T6/T8 也要用的名字，并加标准库 import：

```python
from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable, Mapping

from .config_view import _MAX_LIST, audit_rows, redact_config, status_rows, validate_and_backfill

_log = logging.getLogger("palworld_terminal.web_api")
_TRANSFER_ACTION = "mode_transfer"
_ORPHAN_ACTION = "orphan_purge"
```

在文件末尾追加 handler：

```python
async def handle_mode_transfer_preview(container, restarting, target) -> tuple[int, dict]:
    """转移前只读预览：回传服务端权威源（不信客户端凭空构造）。"""
    if restarting or container is None:
        return 200, {"ok": True, "restarting": True}
    ready = [{"server_id": s.server_id, "name": s.name}
             for s in container.config.servers if s.ready]
    if target == "single":
        pairs = await container.repo.list_allowed_bindings()
        agg: dict[str, list[str]] = {}
        for umo, sid in pairs:
            agg.setdefault(umo, []).append(sid)
        bindings = [{"umo": umo, "server_ids": sids} for umo, sids in agg.items()]
        return 200, {"ok": True, "ready_servers": ready, "bindings": bindings}
    if target == "multi":
        allowed_groups = [{"umo": e.umo, "note": e.note}
                          for e in container.config.routing.single_allowed_groups]
        return 200, {"ok": True, "ready_servers": ready, "allowed_groups": allowed_groups}
    return 200, {"ok": False, "error": "invalid_target", "detail": {}}
```

> `_MAX_LIST` / `copy` / `json` / `_log` / `_TRANSFER_ACTION` / `_ORPHAN_ACTION` 在本 Task 尚未被引用——它们供 T6/T8。为避免 T5 单独提交时 ruff 报 `F401 unused import`，**本 Task 只加 `import logging` 与 `_log`（预览无需 copy/json/_MAX_LIST）**。将 `copy` / `json` / `_MAX_LIST` / `_TRANSFER_ACTION` / `_ORPHAN_ACTION` 的引入**推迟到 T6/T8 各自 Task 内、与首个消费点同一提交**。即 T5 的 import 段实际写：
> ```python
> from __future__ import annotations
>
> import logging
> from collections.abc import Callable, Mapping
>
> from .config_view import audit_rows, redact_config, status_rows, validate_and_backfill
>
> _log = logging.getLogger("palworld_terminal.web_api")
> ```
> （`Callable` 已被 `handle_config_get` 等既有 handler 使用、`Mapping` 亦然，不属新增未用。）

- [ ] **Step 4: 跑测试确认通过 + 局部 lint**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_mode_preview_test.py -v`
Expected: PASS。
Run: `ruff check palworld_terminal/presentation/web_api.py`
Expected: `All checks passed!`（无未用 import）。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/web_api.py tests/unit/web_api_mode_preview_test.py
git commit -m "feat: mode/transfer/preview 只读预览端点"
```

---

### Task 6: 转移端点核心 `handle_mode_transfer`（single↔multi + multi→single 保留其余，无 DB purge）

> 这是 Task 6a（核心：single↔multi + multi→single 1 台/保留其余，无 purge）。Task 7 追加 purge。

**Files:**
- Modify: `palworld_terminal/presentation/web_api.py`（补 import：`copy`/`json`/`_MAX_LIST`/`_TRANSFER_ACTION`；新增 handler）
- Test: `tests/unit/web_api_mode_transfer_test.py`（新建，含共享测试 harness `_mk_container` / `_Harness`）

**Interfaces:**
- Consumes（注入回调）：
  - `get_raw: Callable[[], Mapping]` → 落盘真相 `self._raw_config`。
  - `get_container: Callable[[], Any]` → live 容器（reload 后返回新容器）；容器有 `.config`（`AppConfig`）、`.repo`（`Repository`）、`.routing`（`RoutingService`，有 `_ready_servers()`/`_ready_by_name(name)`）。
  - `busy_msg: Callable[[], str | None]` → `self._busy_msg()`。
  - `lock: asyncio.Lock` → `self._save_lock`。
  - `now: int` → 审计 ts（epoch 秒）。
  - `apply_and_restart: Callable[[dict], Awaitable[dict]]` → `self._apply_and_restart`（整键替换→save→parse→重建容器；失败即回滚返回 `{"ok":False,"error":...}`、不抛）。
  - `current_username: Callable[[], str | None]` → `self._current_username`（明文 admin_id）。
- Consumes（Repository，T1–T3）：`list_allowed_bindings()` / `bind_umos_to_server(umos, sid)` / `revoke(umo, sid)` / `clear_all_group_servers()` / `insert_audit(...)`。
- Produces: `async def handle_mode_transfer(body, *, get_raw, get_container, busy_msg, lock, now, apply_and_restart, current_username) -> tuple[int, dict]`。载荷 `{target_mode, surviving_server_id?, migrate_umos:list[str], purge_others:bool}`。业务成败恒 200。

- [ ] **Step 1: 写失败测试（建 harness + 核心断言）**

新建 `tests/unit/web_api_mode_transfer_test.py`。**该文件的 harness 供 Task 6 与 Task 7 共用**（Task 7 追加测试于同文件，复用 `_Harness`/`_mk`）：

```python
import asyncio
import copy

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.routing_service import RoutingService
from palworld_terminal.config import parse_config
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.web_api import handle_mode_transfer


def _srv_row(name, enabled=True, password="pw", base_url="http://h:8212"):
    return {"name": name, "enabled": enabled, "base_url": base_url,
            "username": "admin", "password": password, "password_env": "",
            "timeout": 10, "verify_tls": True, "timezone": ""}


def _base_raw(world_mode, servers, single_allowed=None, group_bindings=None):
    return {
        "servers": servers, "custom_headers": [],
        "group_bindings": group_bindings or [],
        "single_allowed_groups": single_allowed or [],
        "routing": {"access_mode": "restricted", "default_server": "",
                    "world_mode": world_mode, "setup_confirmed": True},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {},
    }


class _Container:
    def __init__(self, raw, repo):
        self.config = parse_config(raw, {})
        self.repo = repo
        self.routing = RoutingService(repo, self.config)


class _Harness:
    """真实 parse_config + 真实 Repository/DB；apply_and_restart 镜像
    main._apply_and_restart 的整键替换 + Container.start 的 DB 副作用
    （sync_servers → seed_bindings → cleanup_orphan_bindings）。"""

    def __init__(self, raw, repo):
        self.raw = raw
        self.repo = repo
        self.container = _Container(raw, repo)
        self.fail_reload = False
        self.reload_calls = 0

    def get_raw(self):
        return self.raw

    def get_container(self):
        return self.container

    def busy_msg(self):
        return None

    def current_username(self):
        return "dash_admin"

    async def apply_and_restart(self, candidate):
        self.reload_calls += 1
        if self.fail_reload:
            return {"ok": False, "error": "restart_failed_rolled_back", "detail": {}}
        for k, v in candidate.items():        # 整键替换（镜像 main.py:263-264）
            self.raw[k] = v
        self.container = _Container(self.raw, self.repo)
        cfg = self.container.config
        await self.repo.sync_servers(cfg.servers)
        await self.repo.seed_bindings(cfg.group_bindings)
        ready_ids = {s.server_id for s in cfg.servers if s.ready}
        await self.repo.cleanup_orphan_bindings(ready_ids)
        return {"ok": True, "warnings": {"skipped_servers": [], "skipped_headers": []}}


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def _mk(raw, repo):
    """初始化 harness：把首份 config 的 servers/seed 同步进 DB（模拟首次 start）。"""
    h = _Harness(raw, repo)
    cfg = h.container.config
    await repo.sync_servers(cfg.servers)
    await repo.seed_bindings(cfg.group_bindings)
    return h


async def _call(h, body):
    return await handle_mode_transfer(
        body, get_raw=h.get_raw, get_container=h.get_container,
        busy_msg=h.busy_msg, lock=asyncio.Lock(), now=1234,
        apply_and_restart=h.apply_and_restart, current_username=h.current_username)


# ---- 早退 ----
async def test_no_change_same_mode_not_audited(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")]), repo)
    code, p = await _call(h, {"target_mode": "single", "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "no_change"
    assert h.reload_calls == 0
    assert await repo.list_audit(10) == []      # 三类早退不审计


async def test_transfer_in_progress_when_lock_held(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")]), repo)
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_mode_transfer(
            {"target_mode": "multi", "migrate_umos": []},
            get_raw=h.get_raw, get_container=h.get_container, busy_msg=h.busy_msg,
            lock=lock, now=1, apply_and_restart=h.apply_and_restart,
            current_username=h.current_username)
        assert p["error"] == "transfer_in_progress"
    finally:
        lock.release()


# ---- single → multi ----
async def test_single_to_multi_prebinds_and_clears_source(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": "n"}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is True
    assert p["config"]["routing"]["world_mode"] == "multi"
    # move 清源：顶层 single_allowed_groups 清空
    assert p["config"]["single_allowed_groups"] == []
    # 预绑存活（reload 前绑、目标切 multi 后仍就绪）
    assert await repo.get_allowed("u1") == {"a"}
    # 持久化 round-trip：parse_config 真读到 world_mode=multi、名单已空
    cfg = parse_config(h.raw, {})
    assert cfg.routing.world_mode == "multi"
    assert cfg.routing.single_allowed_groups == []


async def test_single_to_multi_binds_effective_ready_server_not_index0(repo):
    # B2：servers[0] 非就绪、servers[1] 就绪 → 预绑到就绪台而非 servers[0]。
    h = await _mk(_base_raw("single",
                            [_srv_row("ghost", password=""), _srv_row("live")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is True
    assert await repo.get_allowed("u1") == {"live"}   # 绑到就绪台


async def test_single_to_multi_invalid_migrate_umos_rejected(repo):
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u_evil"]})
    assert p["ok"] is False and p["error"] == "invalid_migrate_umos"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "single"   # 零变更
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0     # 校验拒绝写审计


async def test_single_to_multi_no_ready_target_rejected(repo):
    h = await _mk(_base_raw("single", [_srv_row("a", password="")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    assert p["ok"] is False and p["error"] == "no_ready_target"


async def test_single_to_multi_prebind_failure_zero_change(repo):
    # M-a：预绑抛异常 → 拒 migrate_bind_failed、config 完全未变、best-effort 撤销、审计 success=0。
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    orig = repo.bind_umos_to_server

    async def boom(umos, sid):
        raise RuntimeError("db down")

    repo.bind_umos_to_server = boom
    try:
        code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    finally:
        repo.bind_umos_to_server = orig
    assert p["ok"] is False and p["error"] == "migrate_bind_failed"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "single"   # world_mode 仍 single
    assert parse_config(h.raw, {}).routing.single_allowed_groups[0].umo == "u1"  # 名单完整
    assert await repo.get_allowed("u1") == set()                    # 无残留


# ---- multi → single ----
async def test_multi_to_single_migrates_and_promotes_survivor(repo):
    h = await _mk(_base_raw("multi", [_srv_row("a"), _srv_row("b")]), repo)
    await repo.set_active("u1", "a")   # DB 授权源
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "b",
                              "migrate_umos": ["u1"]})
    assert p["ok"] is True
    assert p["config"]["routing"]["world_mode"] == "single"
    # 保留台归位 servers[0]
    assert p["config"]["servers"][0]["name"] == "b"
    # migrate_umos 并入顶层 single_allowed_groups（非 routing 下）
    sag = p["config"]["single_allowed_groups"]
    assert {e["umo"] for e in sag} == {"u1"}
    assert "single_allowed_groups" not in p["config"]["routing"]
    # M-d：group_bindings 种子清空
    assert p["config"]["group_bindings"] == []
    # post-reload clear_all_group_servers 生效
    assert await repo.list_allowed_bindings() == []
    # 持久化 round-trip
    cfg = parse_config(h.raw, {})
    assert cfg.routing.world_mode == "single"
    assert {e.umo for e in cfg.routing.single_allowed_groups} == {"u1"}


async def test_multi_to_single_invalid_surviving_zero_change(repo):
    # B1：surviving 不在就绪集 → 拒 invalid_surviving、零状态变更（config+DB 未动）。
    h = await _mk(_base_raw("multi", [_srv_row("a")]), repo)
    await repo.set_active("u1", "a")
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "nope",
                              "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "invalid_surviving"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "multi"
    assert await repo.get_allowed("u1") == {"a"}   # DB 未动
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_multi_to_single_no_ready_server_rejected(repo):
    h = await _mk(_base_raw("multi", [_srv_row("a", password="")]), repo)
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                              "migrate_umos": []})
    assert p["ok"] is False and p["error"] == "no_ready_server"


async def test_multi_to_single_over_limit_rejected(repo):
    # M-b：并入后 single_allowed_groups > 200 → 拒 too_many_groups、零状态变更、绝不截断。
    existing = [{"umo": f"g{i}", "note": ""} for i in range(199)]
    h = await _mk(_base_raw("multi", [_srv_row("a")], single_allowed=existing), repo)
    # DB 有两个可迁 umo（并入后 199+2=201 > 200）
    await repo.set_active("m1", "a")
    await repo.set_active("m2", "a")
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                              "migrate_umos": ["m1", "m2"]})
    assert p["ok"] is False and p["error"] == "too_many_groups"
    assert h.reload_calls == 0
    assert parse_config(h.raw, {}).routing.world_mode == "multi"   # 零变更
    assert await repo.get_allowed("m1") == {"a"}                   # DB 未动
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_multi_to_single_move_no_revive_on_switch_back(repo):
    # M2 + M-d：multi→single move（清 group_bindings 种子）后切回 multi，旧授权不复活。
    # 专测「config 原有 group_bindings 种子行」case：清种子后 seed_bindings 重播不复活。
    h = await _mk(_base_raw("multi", [_srv_row("a"), _srv_row("b")],
                            group_bindings=[{"umo": "u_old", "server": "a", "active": True}]),
                  repo)
    await repo.set_active("u_old", "a")
    # 切 single，不迁 u_old（migrate_umos 空）
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                              "migrate_umos": []})
    assert p["ok"] is True
    assert await repo.list_allowed_bindings() == []   # 清空
    # 切回 multi
    code, p = await _call(h, {"target_mode": "multi", "migrate_umos": []})
    assert p["ok"] is True
    # seed_bindings 重播不复活 u_old（种子已随清空）
    assert await repo.get_allowed("u_old") == set()


# ---- reload 失败 / 清源失败 / 审计异常 ----
async def test_reload_failure_aborts_post_reload_writes(repo):
    # M5：apply_and_restart 返回 ok:False → post-reload DB 写未跑 + config 回滚 + 审计 success=0。
    h = await _mk(_base_raw("multi", [_srv_row("a"), _srv_row("b")]), repo)
    await repo.set_active("u1", "a")
    h.fail_reload = True
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "b",
                              "migrate_umos": ["u1"]})
    assert p["ok"] is False and p["error"] == "restart_failed_rolled_back"
    # multi→single 方向 DB 完全未动（clear 未跑）
    assert await repo.get_allowed("u1") == {"a"}
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_clear_source_failure_still_switches_and_warns(repo):
    # M-f：clear_all_group_servers 抛错 → 模式仍切、审计 success=0 + cleared_group_servers=False、
    # 回执 ok:True + warnings、不 500。
    h = await _mk(_base_raw("multi", [_srv_row("a")]), repo)
    await repo.set_active("u1", "a")
    orig = repo.clear_all_group_servers

    async def boom():
        raise RuntimeError("locked")

    repo.clear_all_group_servers = boom
    try:
        code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "a",
                                  "migrate_umos": ["u1"]})
    finally:
        repo.clear_all_group_servers = orig
    assert code == 200 and p["ok"] is True
    assert p["warnings"].get("cleared_group_servers") is False
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 0


async def test_audit_write_failure_still_returns_200(repo):
    # M-e：insert_audit 抛错 → 端点仍 200 + 正确 ok/config、不吞已算好的成功 payload。
    h = await _mk(_base_raw("single", [_srv_row("a")],
                            single_allowed=[{"umo": "u1", "note": ""}]), repo)
    orig = repo.insert_audit

    async def boom(**kw):
        raise RuntimeError("audit locked")

    repo.insert_audit = boom
    try:
        code, p = await _call(h, {"target_mode": "multi", "migrate_umos": ["u1"]})
    finally:
        repo.insert_audit = orig
    assert code == 200 and p["ok"] is True
    assert p["config"]["routing"]["world_mode"] == "multi"


async def test_candidate_preserves_untouched_fields(repo):
    # M8：转移不静默重置 access_mode/default_server/setup_confirmed；保留台密码存活。
    raw = _base_raw("multi", [_srv_row("a"), _srv_row("b")])
    raw["routing"]["access_mode"] = "open"
    raw["routing"]["default_server"] = "a"
    h = await _mk(raw, repo)
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "b",
                              "migrate_umos": []})
    assert p["ok"] is True
    cfg = parse_config(h.raw, {})
    assert cfg.routing.access_mode.value == "open"
    assert cfg.routing.default_server == "a"
    assert cfg.routing.setup_confirmed is True
    survivor = next(s for s in cfg.servers if s.server_id == "b")
    assert survivor.password == "pw" and survivor.ready is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_mode_transfer_test.py -v`
Expected: FAIL —— `ImportError: cannot import name 'handle_mode_transfer'`。

- [ ] **Step 3: 补 import + 实现 handler（无 purge）**

在 `web_api.py` import 段补 `copy` / `json` / `_MAX_LIST`（与 `_TRANSFER_ACTION` 一并，这是它们的首个消费点），并在文件末尾追加 handler：

import 段更新为：

```python
from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable, Mapping

from .config_view import _MAX_LIST, audit_rows, redact_config, status_rows, validate_and_backfill

_log = logging.getLogger("palworld_terminal.web_api")
_TRANSFER_ACTION = "mode_transfer"
```

handler：

```python
async def handle_mode_transfer(
    body,
    *,
    get_raw,
    get_container,
    busy_msg,
    lock,
    now,
    apply_and_restart,
    current_username,
) -> tuple[int, dict]:
    """single↔multi 原子转移编排：全程持 lock、迁移读先于 reload、
    single→multi 目标预绑先于清源、reload 失败即中止、post-reload move 清源、
    最外层审计（写异常独立隔离）。业务成败恒 200。"""
    # ---- 步0：入口串行门（transfer_in_progress / busy / no_change 三类早退不审计）----
    if lock.locked():
        return 200, {"ok": False, "error": "transfer_in_progress", "detail": {}}
    async with lock:
        if busy_msg() is not None:
            return 200, {"ok": False, "error": "busy", "detail": {}}
        container = get_container()
        if container is None:
            return 200, {"ok": False, "error": "busy", "detail": {}}

        # ---- 步1：载荷 + 当前模式 ----
        target_mode = body.get("target_mode") if isinstance(body, Mapping) else None
        if target_mode not in ("single", "multi"):
            return 200, {"ok": False, "error": "invalid_target", "detail": {}}
        current_mode = container.config.routing.world_mode
        if target_mode == current_mode:
            return 200, {"ok": False, "error": "no_change", "detail": {}}

        migrate_raw = body.get("migrate_umos") if isinstance(body, Mapping) else None
        migrate_umos = [str(u) for u in migrate_raw] if isinstance(migrate_raw, list) else []
        surviving_server_id = (body.get("surviving_server_id")
                               if isinstance(body, Mapping) else None)

        # ---- 审计累加状态（步7 最外层写一条）----
        state: dict = {
            "from": current_mode, "to": target_mode,
            "surviving": surviving_server_id, "migrated": 0,
            "purged": {}, "failed_server_ids": [],
            "cleared_group_servers": None, "cleared_single_allowed": None,
        }
        server_name_hint = _TRANSFER_ACTION
        target_server_id: str | None = None

        async def _finalize(payload, *, success, error, server_name):
            # 审计写异常隔离（M-e）：独立 try/except 吞异常、绝不改动已算好的 200 回执
            try:
                c = get_container()
                if c is not None:
                    await c.repo.insert_audit(
                        ts=now, admin_id=str(current_username() or ""),
                        action=_TRANSFER_ACTION,
                        server_name=server_name or _TRANSFER_ACTION,
                        target_name=None, target_hash=None,
                        detail=json.dumps(state, ensure_ascii=False),
                        success=success, error=error,
                    )
            except Exception:  # noqa: BLE001
                _log.warning("mode_transfer 审计写入失败（已忽略）")
            return 200, payload

        # ---- 步2/3：校验 + 迁移读 + 目标预绑（全部先于 reload）----
        if target_mode == "single":
            ready = container.routing._ready_servers()
            if not ready:
                return await _finalize(
                    {"ok": False, "error": "no_ready_server", "detail": {}},
                    success=0, error="no_ready_server", server_name=server_name_hint)
            survivor = container.routing._ready_by_name(str(surviving_server_id or ""))
            if survivor is None:
                return await _finalize(
                    {"ok": False, "error": "invalid_surviving", "detail": {}},
                    success=0, error="invalid_surviving", server_name=server_name_hint)
            server_name_hint = survivor.name
            pairs = await container.repo.list_allowed_bindings()
            source_umos = {umo for umo, _ in pairs}
            if not set(migrate_umos).issubset(source_umos):
                return await _finalize(
                    {"ok": False, "error": "invalid_migrate_umos", "detail": {}},
                    success=0, error="invalid_migrate_umos", server_name=server_name_hint)
        else:  # single → multi
            source_umos = {e.umo for e in container.config.routing.single_allowed_groups}
            if not set(migrate_umos).issubset(source_umos):
                return await _finalize(
                    {"ok": False, "error": "invalid_migrate_umos", "detail": {}},
                    success=0, error="invalid_migrate_umos", server_name=server_name_hint)
            if migrate_umos:
                ready = container.routing._ready_servers()
                if not ready:
                    return await _finalize(
                        {"ok": False, "error": "no_ready_target", "detail": {}},
                        success=0, error="no_ready_target", server_name=server_name_hint)
                target_server_id = ready[0].server_id
                server_name_hint = ready[0].name
                try:  # reload 前用旧容器预绑（目标先于清源，M-a）
                    await container.repo.bind_umos_to_server(migrate_umos, target_server_id)
                except Exception:  # noqa: BLE001
                    for umo in migrate_umos:
                        try:
                            await container.repo.revoke(umo, target_server_id)
                        except Exception:  # noqa: BLE001
                            pass
                    return await _finalize(
                        {"ok": False, "error": "migrate_bind_failed", "detail": {}},
                        success=0, error="migrate_bind_failed", server_name=server_name_hint)

        # ---- 步4：候选构造（深拷贝完整 raw 原地改，绝不预改 self._raw_config）----
        candidate = copy.deepcopy(dict(get_raw()))
        routing_node = candidate.setdefault("routing", {})
        if not isinstance(routing_node, dict):
            routing_node = {}
            candidate["routing"] = routing_node
        routing_node["world_mode"] = target_mode

        if target_mode == "single":
            servers = candidate.get("servers")
            if isinstance(servers, list):
                idx = next(
                    (i for i, s in enumerate(servers)
                     if isinstance(s, dict) and s.get("name") == surviving_server_id),
                    None,
                )
                if idx is not None and idx != 0:
                    servers.insert(0, servers.pop(idx))
            sag = candidate.setdefault("single_allowed_groups", [])
            if not isinstance(sag, list):
                sag = []
                candidate["single_allowed_groups"] = sag
            existing = {str(e.get("umo")) for e in sag if isinstance(e, dict)}
            for umo in migrate_umos:
                if umo not in existing:
                    sag.append({"umo": umo, "note": "从多世界绑定迁移"})
                    existing.add(umo)
            if len(sag) > _MAX_LIST:   # 并入越限 fail-closed（M-b）；此刻尚未 reload、DB 未动
                return await _finalize(
                    {"ok": False, "error": "too_many_groups", "detail": {}},
                    success=0, error="too_many_groups", server_name=server_name_hint)
            state["migrated"] = len(migrate_umos)
            candidate["group_bindings"] = []   # 清 config 种子（M-d 彻底 move）
        else:  # single → multi
            candidate["single_allowed_groups"] = []   # move 清源（目标已在步3预绑）
            state["migrated"] = len(migrate_umos)
            state["cleared_single_allowed"] = True

        # ---- 步5：落库 + reload ----
        outcome = await apply_and_restart(candidate)
        if not outcome.get("ok"):   # reload 失败即中止（M5）：不做 post-reload DB 写
            if target_mode == "multi" and migrate_umos and target_server_id is not None:
                c = get_container()   # single→multi 预绑残留 best-effort 撤销（单模式无害）
                if c is not None:
                    for umo in migrate_umos:
                        try:
                            await c.repo.revoke(umo, target_server_id)
                        except Exception:  # noqa: BLE001
                            pass
            err = outcome.get("error", "restart_failed")
            return await _finalize(
                {"ok": False, "error": err, "detail": {}},
                success=0, error=err, server_name=server_name_hint)

        # ---- 步6：post-reload DB 写（用新容器 repo）----
        new_repo = get_container().repo
        clear_ok = True
        if target_mode == "single":
            try:   # multi→single move 清源（清空全表；M-f 失败处理）
                cleared = await new_repo.clear_all_group_servers()
                state["cleared_group_servers"] = True
                state["cleared_count"] = cleared
            except Exception:  # noqa: BLE001
                clear_ok = False
                state["cleared_group_servers"] = False
            # （purge 循环在 Task 7 追加于此）

        # ---- 步7/8：审计 + 返回 ----
        warnings: dict = {}
        if state["cleared_group_servers"] is False:
            warnings["cleared_group_servers"] = False
        if state["failed_server_ids"]:
            warnings["purge_failed"] = state["failed_server_ids"]
        payload = {
            "ok": True, "config": redact_config(get_raw()), "warnings": warnings,
            "summary": {"from": current_mode, "to": target_mode,
                        "surviving": surviving_server_id, "migrated": state["migrated"],
                        "purged": state["purged"],
                        "failed_server_ids": state["failed_server_ids"]},
        }
        success = 1 if clear_ok else 0
        error = (None if clear_ok
                 else "源介质（DB 群绑定）清理未尽，切回多世界前请人工核查残留")
        return await _finalize(payload, success=success, error=error,
                               server_name=server_name_hint)
```

- [ ] **Step 4: 跑测试确认通过 + 局部 lint/类型**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_mode_transfer_test.py -v`
Expected: PASS。
Run: `ruff check palworld_terminal/presentation/web_api.py && ./.venv/Scripts/python.exe -m mypy palworld_terminal/presentation/web_api.py`
Expected: ruff `All checks passed!`；mypy 无新 error（注入参数无标注=Any，沿既有 handler 风格）。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/web_api.py tests/unit/web_api_mode_transfer_test.py
git commit -m "feat: mode/transfer 转移编排核心（无 purge）"
```

---

### Task 7: 转移端点 purge 扩展（`purge_others` → 候选裁 servers + purge_set 循环）

**Files:**
- Modify: `palworld_terminal/presentation/web_api.py`（`handle_mode_transfer` 内三处：读 `purge_others`、候选构造 multi→single 分支加 purge_set 捕获 + servers 裁剪、步6 加 purge 循环）
- Test: `tests/unit/web_api_mode_transfer_test.py`（追加，复用 T6 的 `_Harness`/`_mk`）

**Interfaces:**
- Consumes: T4 `Repository.purge_server_data(server_id) -> dict[str,int]`；T6 handler 内 `state`/`server_name_hint`/`container`（转移前）。
- Produces: `handle_mode_transfer` 支持 `purge_others: bool`——multi→single 时 `purge_set = {转移前 config.servers 全部 server_id} − {surviving}`（含非就绪有数据台，M-c），候选 `servers` 仅留保留台行，post-reload 对每台 `purge_server_data`（单台 write_tx、失败记录续跑、success 仍 1）。

- [ ] **Step 1: 写失败测试（追加到 T6 文件）**

```python
async def test_multi_to_single_purge_others_deletes_and_isolates(repo):
    from tests.unit.repository_mode_transfer_test import _seed_world_data
    h = await _mk(_base_raw("multi", [_srv_row("keep"), _srv_row("gone")]), repo)
    await _seed_world_data(repo, "keep", "keep:w")
    await _seed_world_data(repo, "gone", "gone:w")
    await repo.set_active("u1", "keep")
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "keep",
                              "migrate_umos": ["u1"], "purge_others": True})
    assert p["ok"] is True
    # gone 台被真删（world 数据 + 三张 server 行）
    rows = await repo._db.query("SELECT COUNT(*) FROM players WHERE world_id='gone:w'")
    assert rows[0][0] == 0
    rows = await repo._db.query("SELECT server_id FROM servers ORDER BY server_id")
    assert [r[0] for r in rows] == ["keep"]
    # 保留台数据隔离（keep:w 世界数据仍在）
    rows = await repo._db.query("SELECT COUNT(*) FROM players WHERE world_id='keep:w'")
    assert rows[0][0] == 1
    # 候选 servers 仅留保留台
    assert [s["name"] for s in p["config"]["servers"]] == ["keep"]
    # 回执摘要含 purge 计数
    assert "gone" in p["summary"]["purged"]


async def test_multi_to_single_purges_non_ready_server_with_data(repo):
    # M-c：曾就绪现非就绪（清密码）但 DB 有 world 历史的非 surviving 台 → 被真删、不留孤儿。
    from tests.unit.repository_mode_transfer_test import _seed_world_data
    h = await _mk(_base_raw("multi", [_srv_row("keep"), _srv_row("ghost", password="")]),
                  repo)
    await _seed_world_data(repo, "keep", "keep:w")
    await _seed_world_data(repo, "ghost", "ghost:w")   # ghost 非就绪但有历史
    code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "keep",
                              "migrate_umos": [], "purge_others": True})
    assert p["ok"] is True
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds WHERE server_id='ghost'")
    assert rows[0][0] == 0   # ghost world 数据 + 行归零
    orphans = await repo.list_orphan_server_ids({"keep"})
    assert "ghost" not in orphans   # 不留孤儿


async def test_multi_to_single_purge_partial_failure_success_1(repo):
    # purge 部分失败 → 其余台仍清、审计 success=1 + failed_server_ids、回执 warnings。
    from tests.unit.repository_mode_transfer_test import _seed_world_data
    h = await _mk(_base_raw("multi", [_srv_row("keep"), _srv_row("bad")]), repo)
    await _seed_world_data(repo, "keep", "keep:w")
    await _seed_world_data(repo, "bad", "bad:w")
    orig = repo.purge_server_data

    async def selective(sid):
        if sid == "bad":
            raise RuntimeError("purge boom")
        return await orig(sid)

    repo.purge_server_data = selective
    try:
        code, p = await _call(h, {"target_mode": "single", "surviving_server_id": "keep",
                                  "migrate_umos": [], "purge_others": True})
    finally:
        repo.purge_server_data = orig
    assert p["ok"] is True
    assert p["warnings"]["purge_failed"] == ["bad"]
    audits = await repo.list_audit(10)
    assert audits and audits[0]["success"] == 1   # purge 部分失败仍 success=1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_mode_transfer_test.py -k purge -v`
Expected: FAIL —— purge_others 未生效：ghost/gone 台未被删（`servers` 仍含 keep+gone；`p["summary"]["purged"]` 空）。

- [ ] **Step 3: 三处 Edit 加入 purge 支持**

**Edit A —— 步1 读 `purge_others`**：把
```python
        surviving_server_id = (body.get("surviving_server_id")
                               if isinstance(body, Mapping) else None)
```
改为
```python
        surviving_server_id = (body.get("surviving_server_id")
                               if isinstance(body, Mapping) else None)
        purge_others = bool(body.get("purge_others")) if isinstance(body, Mapping) else False
        purge_set: set[str] = set()
```

**Edit B —— 候选构造 multi→single 分支：捕获 purge_set（转移前 config）+ 裁 servers**。把
```python
            state["migrated"] = len(migrate_umos)
            candidate["group_bindings"] = []   # 清 config 种子（M-d 彻底 move）
```
改为
```python
            state["migrated"] = len(migrate_umos)
            candidate["group_bindings"] = []   # 清 config 种子（M-d 彻底 move）
            if purge_others:
                # purge_set = 转移前 config 所有非 surviving 台（含非就绪有数据台，M-c）
                purge_set = {s.server_id for s in container.config.servers} - {
                    str(surviving_server_id)}
                survivor_row = next(
                    (s for s in candidate.get("servers", [])
                     if isinstance(s, dict) and s.get("name") == surviving_server_id),
                    None,
                )
                if survivor_row is not None:
                    candidate["servers"] = [survivor_row]
```

**Edit C —— 步6：在 clear 之后加 purge 循环**。把
```python
            except Exception:  # noqa: BLE001
                clear_ok = False
                state["cleared_group_servers"] = False
            # （purge 循环在 Task 7 追加于此）
```
改为
```python
            except Exception:  # noqa: BLE001
                clear_ok = False
                state["cleared_group_servers"] = False
            if purge_others and purge_set:   # 空集短路（Minor）
                for sid in sorted(purge_set):
                    try:
                        state["purged"][sid] = await new_repo.purge_server_data(sid)
                    except Exception:  # noqa: BLE001
                        state["failed_server_ids"].append(sid)   # 记录续跑、不回滚
```

> 注：purge 部分失败**不翻转 `clear_ok`/`success`**（spec 步7：purge 部分失败 success=1、失败台入 `failed_server_ids`/warnings）。`failed_server_ids` 非空时 T6 步7/8 已把它并进 `warnings["purge_failed"]` 与 `summary`。

- [ ] **Step 4: 跑测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_mode_transfer_test.py -v`
Expected: PASS（T6 + T7 全绿）。
Run: `ruff check palworld_terminal/presentation/web_api.py && ./.venv/Scripts/python.exe -m mypy palworld_terminal/presentation/web_api.py`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/web_api.py tests/unit/web_api_mode_transfer_test.py
git commit -m "feat: mode/transfer purge_others 扩展（purge_set + 隔离 + 部分失败续跑）"
```

---

### Task 8: 孤儿端点 `handle_orphans_list` + `handle_orphans_purge`（服务端重算、不信客户端）

**Files:**
- Modify: `palworld_terminal/presentation/web_api.py`（补 `_ORPHAN_ACTION`；新增两个 handler）
- Test: `tests/unit/web_api_orphans_test.py`（新建）

**Interfaces:**
- Consumes: `container.config.servers`；T1 `list_orphan_server_ids(valid)`；T4 `purge_server_data(sid)`；`insert_audit(...)`；注入 `get_container`/`busy_msg`/`lock`/`now`/`current_username`。
- Produces:
  - `async def handle_orphans_list(container, restarting) -> tuple[int, dict]`：`restarting or None` → `{ok:True, orphans:[], restarting:True}`；否则 `{ok:True, orphans: list_orphan_server_ids({config.servers 的 server_id})}`。
  - `async def handle_orphans_purge(body, *, get_container, busy_msg, lock, now, current_username) -> tuple[int, dict]`：持 `lock`、不自增 `_inflight`（`_inflight` 由 Star 层管、写端点不用）。**持锁后服务端现场重算孤儿集**；客户端传入 `server_ids` 仅作交集过滤，非孤儿 → rejected；空 targets 短路无审计；逐台单 write_tx、失败续跑；审计 `action="orphan_purge"`、写异常独立 try/except 吞掉。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/web_api_orphans_test.py`：

```python
import asyncio

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.web_api import handle_orphans_list, handle_orphans_purge
from tests.unit.repository_mode_transfer_test import _seed_world_data


class _Srv:
    def __init__(self, name):
        self.name = name
        self.server_id = name


class _Cfg:
    def __init__(self, servers):
        self.servers = servers


class _Container:
    def __init__(self, servers, repo):
        self.config = _Cfg(servers)
        self.repo = repo


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "o.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_orphans_list_reports_db_only_servers(repo):
    await _seed_world_data(repo, "live", "live:w")
    await _seed_world_data(repo, "ghost", "ghost:w")
    c = _Container([_Srv("live")], repo)   # config 只有 live
    code, p = await handle_orphans_list(c, False)
    assert p["ok"] is True and p["orphans"] == ["ghost"]


async def test_orphans_list_restarting():
    code, p = await handle_orphans_list(None, True)
    assert p["restarting"] is True and p["orphans"] == []


async def test_orphans_purge_removes_orphan(repo):
    await _seed_world_data(repo, "live", "live:w")
    await _seed_world_data(repo, "ghost", "ghost:w")
    c = _Container([_Srv("live")], repo)
    code, p = await handle_orphans_purge(
        {}, get_container=lambda: c, busy_msg=lambda: None,
        lock=asyncio.Lock(), now=1, current_username=lambda: "admin")
    assert p["ok"] is True and "ghost" in p["purged"]
    assert await repo.list_orphan_server_ids({"live"}) == []
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds WHERE server_id='ghost'")
    assert rows[0][0] == 0


async def test_orphans_purge_rejects_live_server_toctou(repo):
    # Blocker-O：客户端传入在册活台 → 服务端重算孤儿集不含它 → 不删、rejected。
    await _seed_world_data(repo, "live", "live:w")
    await _seed_world_data(repo, "ghost", "ghost:w")
    c = _Container([_Srv("live"), _Srv("ghost")], repo)   # 两台都在 config（无孤儿）
    code, p = await handle_orphans_purge(
        {"server_ids": ["live"]}, get_container=lambda: c, busy_msg=lambda: None,
        lock=asyncio.Lock(), now=1, current_username=lambda: "admin")
    assert p["ok"] is True
    assert p["rejected"] == ["live"] and p["purged"] == {}
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds WHERE server_id='live'")
    assert rows[0][0] == 1   # 活台数据未动


async def test_orphans_purge_empty_short_circuits(repo):
    await _seed_world_data(repo, "live", "live:w")
    c = _Container([_Srv("live")], repo)   # 无孤儿
    code, p = await handle_orphans_purge(
        {}, get_container=lambda: c, busy_msg=lambda: None,
        lock=asyncio.Lock(), now=1, current_username=lambda: "admin")
    assert p["ok"] is True and p["purged"] == {}
    assert await repo.list_audit(10) == []   # 空孤儿集短路、不审计


async def test_orphans_purge_busy_when_lock_held(repo):
    c = _Container([_Srv("live")], repo)
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_orphans_purge(
            {}, get_container=lambda: c, busy_msg=lambda: None,
            lock=lock, now=1, current_username=lambda: "admin")
        assert p["error"] == "purge_in_progress"
    finally:
        lock.release()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_orphans_test.py -v`
Expected: FAIL —— `ImportError: cannot import name 'handle_orphans_list'`。

- [ ] **Step 3: 补常量 + 实现两个 handler**

在 `web_api.py` 顶部（`_TRANSFER_ACTION` 旁）补：
```python
_ORPHAN_ACTION = "orphan_purge"
```

文件末尾追加：

```python
async def handle_orphans_list(container, restarting) -> tuple[int, dict]:
    """只读列 DB 残留但 config 已无的 server_id。"""
    if restarting or container is None:
        return 200, {"ok": True, "orphans": [], "restarting": True}
    valid = {s.server_id for s in container.config.servers}
    orphans = await container.repo.list_orphan_server_ids(valid)
    return 200, {"ok": True, "orphans": orphans}


async def handle_orphans_purge(
    body, *, get_container, busy_msg, lock, now, current_username
) -> tuple[int, dict]:
    """清理孤儿 server 数据。持 lock、不自增 _inflight。服务端现场重算孤儿集
    （不信客户端，Blocker-O）：客户端传入 server_ids 仅作交集过滤，非孤儿 → rejected。"""
    if lock.locked():
        return 200, {"ok": False, "error": "purge_in_progress", "detail": {}}
    async with lock:
        if busy_msg() is not None:
            return 200, {"ok": False, "error": "busy", "detail": {}}
        container = get_container()
        if container is None:
            return 200, {"ok": False, "error": "busy", "detail": {}}
        valid = {s.server_id for s in container.config.servers}
        orphans = set(await container.repo.list_orphan_server_ids(valid))
        requested = body.get("server_ids") if isinstance(body, Mapping) else None
        if isinstance(requested, list) and requested:
            targets = [str(s) for s in requested]
        else:
            targets = sorted(orphans)
        if not targets:   # 空孤儿集且无请求 → 短路无审计
            return 200, {"ok": True, "purged": {}, "rejected": [], "failed_server_ids": []}
        purged: dict[str, dict] = {}
        rejected: list[str] = []
        failed: list[str] = []
        for sid in targets:
            if sid not in orphans:   # TOCTOU 防线：活台/已非孤儿 → 拒
                rejected.append(sid)
                continue
            try:
                purged[sid] = await container.repo.purge_server_data(sid)
            except Exception:  # noqa: BLE001
                failed.append(sid)
        try:   # 审计写异常隔离（M-e 同规格）
            await container.repo.insert_audit(
                ts=now, admin_id=str(current_username() or ""), action=_ORPHAN_ACTION,
                server_name=(targets[0] if targets else _ORPHAN_ACTION),
                target_name=None, target_hash=None,
                detail=json.dumps({"purged": purged, "rejected": rejected,
                                   "failed": failed}, ensure_ascii=False),
                success=1 if not failed else 0,
                error=("purge_failed:" + ",".join(failed)) if failed else None,
            )
        except Exception:  # noqa: BLE001
            _log.warning("orphan_purge 审计写入失败（已忽略）")
        return 200, {"ok": True, "purged": purged, "rejected": rejected,
                     "failed_server_ids": failed}
```

- [ ] **Step 4: 跑测试确认通过 + 局部 lint/类型**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/web_api_orphans_test.py -v`
Expected: PASS。
Run: `ruff check palworld_terminal/presentation/web_api.py && ./.venv/Scripts/python.exe -m mypy palworld_terminal/presentation/web_api.py`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/web_api.py tests/unit/web_api_orphans_test.py
git commit -m "feat: mode/orphans 列/清端点（服务端重算、不信客户端）"
```

---

### Task 9: main.py 注册四端点 + 4 个 Star 薄壳 + 全后端终检

**Files:**
- Modify: `main.py`（`_register_web_api` 追加 4 行注册 + 新增 4 个 `_web_*` 薄壳方法）
- Test: `tests/unit/main_web_test.py`（追加注册断言）

**Interfaces:**
- Consumes: T5/T6/T7/T8 的四个 web_api handler；既有 `_has_identity`/`_deny_unauthorized`/`_busy_msg`/`_current_username`/`_apply_and_restart`/`_save_lock`/`_inflight`/`_idle`。
- Produces: 四条注册路由 `{p}/mode/transfer/preview`(GET) / `{p}/mode/transfer`(POST) / `{p}/mode/orphans`(GET) / `{p}/mode/orphans/purge`(POST)，各带鉴权兜底；只读端点走 `_inflight` 门闩、写端点只持 `_save_lock`。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/main_web_test.py` 的 `test_register_web_api_called_with_prefixed_routes` 追加断言（在其函数体末尾）：

```python
    assert "/astrbot_plugin_palworld/mode/transfer/preview" in routes
    assert "/astrbot_plugin_palworld/mode/transfer" in routes
    assert "/astrbot_plugin_palworld/mode/orphans" in routes
    assert "/astrbot_plugin_palworld/mode/orphans/purge" in routes
    methods = {r: m for r, m in ctx.registered}
    assert methods["/astrbot_plugin_palworld/mode/transfer/preview"] == ("GET",)
    assert methods["/astrbot_plugin_palworld/mode/transfer"] == ("POST",)
    assert methods["/astrbot_plugin_palworld/mode/orphans"] == ("GET",)
    assert methods["/astrbot_plugin_palworld/mode/orphans/purge"] == ("POST",)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/main_web_test.py::test_register_web_api_called_with_prefixed_routes -v`
Expected: FAIL —— `KeyError`/`AssertionError`（新路由未注册）。

- [ ] **Step 3: 注册 + 实现 4 个薄壳**

在 `main.py` `_register_web_api` 的 `audit/list` 注册行之后追加：

```python
        self._context.register_web_api(
            f"{p}/mode/transfer/preview", self._web_mode_transfer_preview, ["GET"],
            "模式转移预览(只读)")
        self._context.register_web_api(
            f"{p}/mode/transfer", self._web_mode_transfer, ["POST"], "模式转移(原子编排)")
        self._context.register_web_api(
            f"{p}/mode/orphans", self._web_orphans_list, ["GET"], "孤儿服务器数据列表(只读)")
        self._context.register_web_api(
            f"{p}/mode/orphans/purge", self._web_orphans_purge, ["POST"],
            "清理孤儿服务器数据")
```

在 `_web_config_save` 方法之后（`# ---- context helpers ----` 之前）追加四个薄壳：

```python
    async def _web_mode_transfer_preview(self):
        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        target = request.args.get("target", "single")
        self._inflight += 1   # 只读端点走在途门闩（镜像 _web_status/_web_audit）
        self._idle.clear()
        try:
            container = None if self._restarting else self._container
            _code, payload = await web_api.handle_mode_transfer_preview(
                container, self._restarting, target)
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        return jsonify(payload)

    async def _web_orphans_list(self):
        from quart import jsonify
        if not self._has_identity():
            return self._deny_unauthorized()
        self._inflight += 1
        self._idle.clear()
        try:
            container = None if self._restarting else self._container
            _code, payload = await web_api.handle_orphans_list(container, self._restarting)
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        return jsonify(payload)

    async def _web_mode_transfer(self):
        import time

        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        body = await request.get_json(silent=True)
        # 写端点：只持 _save_lock、绝不自增 _inflight（否则 _wait_quiescent 等自己白等）
        _code, payload = await web_api.handle_mode_transfer(
            body, get_raw=lambda: self._raw_config,
            get_container=lambda: self._container, busy_msg=self._busy_msg,
            lock=self._save_lock, now=int(time.time()),
            apply_and_restart=self._apply_and_restart,
            current_username=self._current_username)
        return jsonify(payload)

    async def _web_orphans_purge(self):
        import time

        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        body = await request.get_json(silent=True)
        _code, payload = await web_api.handle_orphans_purge(
            body, get_container=lambda: self._container, busy_msg=self._busy_msg,
            lock=self._save_lock, now=int(time.time()),
            current_username=self._current_username)
        return jsonify(payload)
```

> `now=int(time.time())`（wall-clock epoch，供审计 ts）——与 admin_service `self._clock.now()` 同语义；不用 `time.monotonic()`（那是 config/save 频率限制用）。

- [ ] **Step 4: 跑注册测试 + 全后端终检**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/main_web_test.py -v`
Expected: PASS。
Run（全库终检）：
```bash
./.venv/Scripts/python.exe -m pytest -q
ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal
```
Expected: pytest 全绿（既有 + 新增 ~30+ 测试全过）；ruff `All checks passed!`；mypy `Success`（42 files，本计划只在 web_api.py/sqlite_repository.py 加代码，均在范围内且无新 error）。

- [ ] **Step 5: 提交**

```bash
git add main.py tests/unit/main_web_test.py
git commit -m "feat: 注册 mode/transfer(/preview) + mode/orphans(/purge) 四端点 + Star 薄壳"
```

---

## Self-Review

### 1. Spec 覆盖（后端每节能指到某 task）

| Spec 节 | 覆盖 Task |
|---|---|
| §4.3 `list_allowed_bindings` / `list_orphan_server_ids` | T1 |
| §4.3 `bind_umos_to_server`（active pin 二步写、one-active-per-umo） | T2 |
| §4.3 `clear_all_group_servers` | T3 |
| §4.3 `purge_server_data`（12 表 + 空集短路 + write_tx + 隔离） | T4 |
| §3/§4.1.1 预览端点（multi→single bindings/ready、single→multi allowed_groups） | T5 |
| §4.1 步0–8 编排核心（持锁全程 / 校验 B1/B2 / single→multi 预绑先于清源 M-a / 深拷贝候选原地改 M8 / >200 拒 M-b / reload 失败中止 M5 / multi→single 清源 M-d/M-f / 审计最外层 + 写异常隔离 M-e/M6） | T6 |
| §4.1 步3/4/6 multi→single 多台 purge_set + servers 裁剪 + purge 循环（M-c、空集短路、部分失败续跑） | T7 |
| §4.4 孤儿列/清端点（服务端重算 Blocker-O、写端点持锁不自增 _inflight、空集短路） | T8 |
| §4.1 注册四端点 + 只读/写门闩差异 + 鉴权兜底 | T9 |
| §7 后端 Repository 断言（list/bind/purge/clear/orphan） | T1–T4 |
| §7 端点编排断言（config round-trip M7、候选保全 M8、DB 绑生效就绪台 B2、move round-trip 不复活 M2/M-d、B1 负测、M5 负测、预绑失败负测 M-a、越限负测 M-b、purge 部分失败、非就绪有数据台 purge M-c、clear 失败 M-f、审计写异常仍 200 M-e、空集短路、审计断言 M6、并发/busy） | T6/T7/T8（逐条落到具名测试） |
| §7 鉴权（`_has_identity`） | T9（薄壳 `_has_identity` 兜底；spec 已确认四端点与 config/save 同级鉴权，薄壳复用既有兜底路径） |
| §8 约束（版本不变 / 相对导入 / 审计字段明文 admin_id + 非空 server_name / purge 表清单） | Global Constraints + 各 Task 逐条落实 |

**无覆盖缺口**：前端（§5）+ 文档锚点（§8 README）按任务定义**属 Phase 2B，本计划有意不含**（parent 明示「只覆盖后端」）。

### 2. 占位扫描

全计划每个改代码 step 均给完整实码（无 TBD / 无「加适当错误处理」/ 无「类似上面」）；每个测试 step 给完整实测代码 + 运行命令 + 期望。T7 用三处 Edit 的完整 old_string/new_string 呈现对 T6 handler 的修改（非占位描述）。T6/T7 共享 harness 定义在同一测试文件 `web_api_mode_transfer_test.py`（T6 建、T7 追加），非「参见上文」的躲闪——T8/orphans 测试对 `_seed_world_data` 的复用走**显式 `from tests.unit.repository_mode_transfer_test import _seed_world_data`**（真实可导入，非占位）。

### 3. 类型一致（跨 Task 签名一致）

- `purge_server_data(server_id) -> dict[str,int]`：T4 定义、T7 步6 循环调用、T8 orphan purge 调用——签名/返回一致。
- `list_orphan_server_ids(valid_server_ids: set[str]) -> list[str]`：T1 定义、T8 list/purge 均调用——一致。
- `bind_umos_to_server(umos, server_id)` / `revoke(umo, server_id)`：T2 定义 / 既有；T6 预绑 + best-effort 撤销调用——一致。
- `clear_all_group_servers() -> int`：T3 定义、T6 步6 调用——一致。
- `list_allowed_bindings() -> list[tuple[str,str]]`：T1 定义、T5 预览聚合 + T6 multi→single 源集——一致。
- handler 注入契约：T6 `handle_mode_transfer(body, *, get_raw, get_container, busy_msg, lock, now, apply_and_restart, current_username)` 与 T9 薄壳 `_web_mode_transfer` 的注入一一对应；T8 `handle_orphans_purge(body, *, get_container, busy_msg, lock, now, current_username)`（无 get_raw/apply_and_restart）与 T9 `_web_orphans_purge` 对应——一致。
- 审计字段：全程 `admin_id=str(current_username() or "")` 明文、`server_name` 非空哨兵回退（`_TRANSFER_ACTION`/`_ORPHAN_ACTION`）、`ts=now`(int)——与 `Repository.insert_audit` 关键字签名逐一对齐。

**已修内联**：T5 首次引入 web_api import 时，把 `copy`/`json`/`_MAX_LIST`/`_TRANSFER_ACTION`/`_ORPHAN_ACTION` 的引入推迟到各自首个消费点（T6/T8），避免 T5 单独提交时 ruff `F401 unused import`——已在 T5 Step 3 注明最终 import 段写法。
