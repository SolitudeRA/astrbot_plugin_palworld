# players 组（玩家个体功能）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个默认关闭的 `players` 功能组，提供玩家个体维度查询（排行榜 `rank`、逐人档案 `player`、我的档案 `me`、自助绑定 `bind`），全部复用 `core` 已采集数据、隐私默认收敛。

**Architecture:** 复用 `core` 的 PLAYERS 端点已落库的 `players`/`player_sessions`/`player_observations` 表——不新增 REST 端点、不改轮询。读逻辑扩入 `QueryService`（不新建服务，避免与写侧 `PlayerService` 撞名）；`me`/`bind`/`hide` 的 DB 读写由 `Commands` 经 `self._repo` 直连，新表由 `migration_0003` 建。设置页是自研 Vue、读硬编码 `OBJECT_SECTIONS`——后端 schema 与前端 `schema.ts` 必须同步。

**Tech Stack:** Python 3.12 + aiosqlite（六边形分层）；pytest（`asyncio_mode=auto`，`*_test.py`）；前端 Vue3 + Vitest。

## Global Constraints

- **只读**：绝不写 Palworld 服务器；所有「写」仅落本插件 DB（`player_bindings`/`hidden_players`）与配置。
- **隐私**：玩家标识一律经 `hash_user_id(salt, world_id, raw)` HMAC；平台账号 id **不明文落库**；精简字段；strict 更保守；opt-out 无静默失效。
- **命令惯例**：`/pal <sub>`，`sub` 名 = `Commands` 方法名 = `COMMANDS` 命令名 = `HELP_LINE` 键，**四者逐字一致**（`_gated` 用 `fn.__name__` 反查 `COMMAND_GROUP`）。
- **默认关**：`features.players` 默认 `False`，三处（`_conf_schema.json` default / `config.py` / `enabled()`）一致。
- **组隔离**：玩家隐藏仅在 `players` 组内生效，不改 core 的 `/pal online`、`/pal status`。
- **时长榜仅今日**：`daily_aggregates` 无写入器，无历史聚合源。
- **等级榜含离线玩家、所有模式一致**（产品决策）；strict 只砍时长榜、不砍等级榜。
- **冒充暂不处理**（产品决策）：自助 `bind` 无归属校验，接受为已知项；`hidden_by` 审计字段照建但本轮不消费。
- **提交不含任何 Claude/AI 署名**（无 Co-Authored-By、正文不提 Claude）。
- 每个 SDD 子任务用 opus。

**权威接口签名（跨任务引用，逐字）：**
- `Repository.upsert_binding(platform_hash: str, world_id: str, player_key: str) -> None`
- `Repository.get_binding(platform_hash: str, world_id: str) -> str | None`
- `Repository.set_hidden(world_id: str, player_key: str, hidden_by: str) -> None`
- `Repository.unset_hidden(world_id: str, player_key: str) -> None`
- `Repository.get_hidden_keys(world_id: str) -> set[str]`
- `Repository.list_players_by_name(world_id: str, name: str) -> list[str]`
- `Repository.list_players_by_level(world_id: str) -> list[PlayerIdentity]`
- `report_service.day_bounds(cfg: AppConfig, world: World, now: int, day: str | None = None) -> tuple[str, int, int]`（模块级）
- `QueryService.load_excluded_keys(world: World) -> set[str]`
- `QueryService.rank(world: World) -> RankBoardsDTO`
- `QueryService.player_profile(world: World, name: str) -> PlayerProfileDTO | None`
- `PlayerProfileDTO(name: str, level: int, online: bool, online_seconds: int)`
- `RankBoardsDTO(time_rows: list[tuple[str, int]], level_rows: list[tuple[str, int]])`
- `format_player(dto: PlayerProfileDTO, *, strict: bool) -> str`
- `format_rank(dto: RankBoardsDTO, *, which: str, strict: bool) -> str`
- `PalChronicle._sender_id(event) -> str`（返回 `f"{platform_name}:{sender_id}"`）
- `FeaturesConfig.players: bool = False`；`PlayersConfig(rank_top_n: int, exclude_names: list[str])`；`AppConfig.players: PlayersConfig`

---

### Task 1: `features.players` 开关

**Files:**
- Modify: `palchronicle/config.py`（`FeaturesConfig` / `_default_features` / `parse_config`）
- Modify: `_conf_schema.json`（`features.items` 加 `players`）
- Test: `tests/unit/config_features_test.py`、`tests/unit/conf_schema_test.py`

**Interfaces:**
- Produces: `FeaturesConfig.players: bool = False`；`FeaturesConfig.enabled("players")`；schema `features.items.players.default == false`。

- [ ] **Step 1: 写失败测试**（追加到 `tests/unit/config_features_test.py` 末尾）

```python
def test_features_players_default_off():
    f = parse_config(_raw(), {}).features
    assert f.players is False


def test_features_players_enabled_helper():
    f = FeaturesConfig(report=True, events=True, guilds_bases=False, players=True)
    assert f.enabled("players") is True
    assert FeaturesConfig(report=True, events=True, guilds_bases=False).enabled("players") is False


def test_features_players_explicit_on():
    f = parse_config(_raw({"players": True}), {}).features
    assert f.players is True
```

追加到 `tests/unit/conf_schema_test.py::test_features_section` 末尾一行：

```python
    assert items["players"]["default"] is False
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/config_features_test.py tests/unit/conf_schema_test.py -v`
Expected: FAIL（`players` 属性不存在 / schema 无 `players` 键）

- [ ] **Step 3: 实现**

`palchronicle/config.py` 的 `FeaturesConfig` 改为（`players` 带默认值，故现存 positional/keyword 构造不破）：

```python
@dataclass(slots=True)
class FeaturesConfig:
    report: bool
    events: bool
    guilds_bases: bool
    players: bool = False

    def enabled(self, name: str) -> bool:
        return {
            "core": True, "report": self.report,
            "events": self.events, "guilds_bases": self.guilds_bases,
            "players": self.players,
        }.get(name, False)
```

`parse_config` 的 `features = FeaturesConfig(...)` 段加一行：

```python
    features = FeaturesConfig(
        report=bool(f.get("report", True)),
        events=bool(f.get("events", True)),
        guilds_bases=bool(f.get("guilds_bases", False)),
        players=bool(f.get("players", False)),
    )
```

`_conf_schema.json` 的 `"features"."items"` 里，`guilds_bases` 之后加：

```json
      "guilds_bases": { "type": "bool", "description": "公会与据点（依赖服务器开放 /game-data；Palworld 1.0 专用服务器暂不支持，默认关）", "default": false },
      "players": { "type": "bool", "description": "玩家个体查询（排行/档案/自助绑定；默认关，含个体隐私考量）", "default": false }
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/unit/config_features_test.py tests/unit/conf_schema_test.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palchronicle/config.py _conf_schema.json tests/unit/config_features_test.py tests/unit/conf_schema_test.py
git commit -m "feat(config): 新增 features.players 开关（默认关）"
```

---

### Task 2: `PlayersConfig` 配置节 + config_view 校验

**Files:**
- Modify: `palchronicle/config.py`（`PlayersConfig` / `_default_players` / `AppConfig.players` / `parse_config`）
- Modify: `_conf_schema.json`（顶层 `players` object 节）
- Modify: `palchronicle/presentation/config_view.py`（`_TOP_KEYS` / 形状校验元组 / `_NUM_FIELDS`）
- Test: `tests/unit/players_config_test.py`（新建）、`tests/unit/config_view_validate_test.py`

**Interfaces:**
- Consumes: 无
- Produces: `PlayersConfig(rank_top_n: int, exclude_names: list[str])`；`AppConfig.players`；`exclude_names` 由逗号分隔字符串解析成 `list[str]`（去空白、丢空项）。

- [ ] **Step 1: 写失败测试** `tests/unit/players_config_test.py`（新建）

```python
"""players 配置节解析：rank_top_n 默认、exclude_names 逗号分隔（spec §7）。"""
from palchronicle.config import PlayersConfig, parse_config


def _raw(players=None):
    cfg = {"servers": [], "routing": {"access_mode": "open", "default_server": ""},
           "group_bindings": [], "polling": {}, "world": {}, "bases": {},
           "privacy": {"mode": "balanced"}, "history": {}}
    if players is not None:
        cfg["players"] = players
    return cfg


def test_players_defaults_when_absent():
    p = parse_config(_raw()).players
    assert p.rank_top_n == 5
    assert p.exclude_names == []


def test_players_rank_top_n_override():
    assert parse_config(_raw({"rank_top_n": 10})).players.rank_top_n == 10


def test_exclude_names_comma_split_and_trim():
    p = parse_config(_raw({"exclude_names": " Alice , Bob ,,Carol "})).players
    assert p.exclude_names == ["Alice", "Bob", "Carol"]


def test_players_config_is_dataclass():
    p = PlayersConfig(rank_top_n=3, exclude_names=["x"])
    assert p.rank_top_n == 3 and p.exclude_names == ["x"]
```

注意 `parse_config` 签名是 `parse_config(raw, env)`；上面用 `parse_config(_raw())` 会缺 `env`。改测试统一 `parse_config(_raw(), {})`（照 `config_features_test.py`）。

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/players_config_test.py -v`
Expected: FAIL（`PlayersConfig` 不存在 / `AppConfig` 无 `players`）

- [ ] **Step 3: 实现**

`palchronicle/config.py`：在 `FeaturesConfig`/`_default_features` 附近加 `PlayersConfig` 与工厂：

```python
@dataclass(slots=True)
class PlayersConfig:
    rank_top_n: int
    exclude_names: list[str]


def _default_players() -> PlayersConfig:
    return PlayersConfig(rank_top_n=5, exclude_names=[])
```

`AppConfig` 末尾加带默认字段（放在 `features` 之后，二者都有默认工厂）：

```python
    features: FeaturesConfig = field(default_factory=_default_features)
    players: PlayersConfig = field(default_factory=_default_players)
```

`parse_config`：在 `f = _obj(raw, "features")` 之后加 `pl = _obj(raw, "players")`；在 `return AppConfig(...)` 里 `features=features,` 之后加：

```python
        features=features,
        players=PlayersConfig(
            rank_top_n=int(pl.get("rank_top_n", 5)),
            exclude_names=[s.strip() for s in str(pl.get("exclude_names", "")).split(",") if s.strip()],
        ),
    )
```

`_conf_schema.json`：在 `"features"` 节（文件最后一节）之后、结尾 `}` 之前，加逗号并追加：

```json
  ,
  "players": {
    "type": "object",
    "description": "玩家个体查询参数（features.players 开启时生效）",
    "items": {
      "rank_top_n": { "type": "int", "description": "排行榜显示人数", "default": 5 },
      "exclude_names": { "type": "string", "description": "排除出榜/查询的玩家名（逗号分隔）", "default": "" }
    }
  }
```

`palchronicle/presentation/config_view.py`：`_TOP_KEYS` 加 `"players"`：

```python
_TOP_KEYS = {
    "servers", "routing", "group_bindings", "custom_headers",
    "polling", "world", "bases", "privacy", "history", "features", "players",
}
```

`validate_and_backfill` 里 object 节形状校验元组加 `"players"`（这是与 `_TOP_KEYS` **独立**的第二处，漏改则 `players` 非 Mapping 时不被拦）：

```python
    for section in ("routing", "polling", "world", "bases", "privacy", "history", "features", "players"):
        if section in body and not isinstance(body[section], Mapping):
            return _err("invalid_shape")
```

`_NUM_FIELDS` 加一项：

```python
    ("players", "rank_top_n"): "int",
```

- [ ] **Step 4: 写 config_view 校验测试**（追加到 `tests/unit/config_view_validate_test.py`；照该文件既有 `_body()`/passthrough 范式，补 `players` 节透传与 `rank_top_n` 非法值）

```python
def test_players_section_passthrough_unstripped():
    body = _body()
    body["players"] = {"rank_top_n": 8, "exclude_names": "Alice,Bob"}
    out = validate_and_backfill(body, _OLD, {})
    assert out["ok"] is True
    assert out["config"]["players"] == {"rank_top_n": 8, "exclude_names": "Alice,Bob"}


def test_players_rank_top_n_rejects_negative():
    body = _body()
    body["players"] = {"rank_top_n": -1, "exclude_names": ""}
    out = validate_and_backfill(body, _OLD, {})
    assert out["ok"] is False and out["error"] == "invalid_field"
```

> 实现者：`_body()` / `_OLD` 是该测试文件既有辅助（构造合法请求体与 old_raw）。若命名不同，对齐文件内既有 passthrough 用例（如 `test_features_section_accepted_and_passthrough_unstripped`）的辅助名。

- [ ] **Step 5: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/players_config_test.py tests/unit/config_view_validate_test.py -v`
Expected: PASS

```bash
git add palchronicle/config.py _conf_schema.json palchronicle/presentation/config_view.py tests/unit/players_config_test.py tests/unit/config_view_validate_test.py
git commit -m "feat(config): 新增 players 配置节（rank_top_n/exclude_names）与 config_view 校验"
```

---

### Task 3: 前端 players 节（`schema.ts` + 三个锁定测试）

**Files:**
- Modify: `frontend/src/lib/schema.ts`（`features.fields` 加 `players`；新增 `players` object 节）
- Test: `frontend/src/lib/schema.test.ts`、`frontend/src/lib/collect.test.ts`、`frontend/src/components/SettingsPanel.test.ts`

**Interfaces:**
- Consumes: Task 1/2 的 `_conf_schema.json`（前端 `schema.test.ts` 会与之比对，须先完成）。

- [ ] **Step 1: 改锁定测试到目标态（先让它们红）**

`frontend/src/lib/schema.test.ts` 的「恰为 7 个 object 节」断言改为 8 节（追加 `players`）：

```typescript
  it('OBJECT_SECTIONS 恰为 8 个 object 节（不含 servers/custom_headers/group_bindings）', () => {
    expect(OBJECT_SECTIONS.map((s) => s.key)).toEqual(
      ['routing', 'polling', 'world', 'bases', 'privacy', 'history', 'features', 'players'])
  })
```

`frontend/src/lib/collect.test.ts`：`baseState().sections` 里 `features` 加 `players: false`，并新增 `players` 节；`TOP_KEYS` 数组加 `'players'`：

```typescript
    features: { report: true, events: true, guilds_bases: false, players: false },
    players: { rank_top_n: 5, exclude_names: '' },
```
```typescript
const TOP_KEYS = ['servers', 'routing', 'group_bindings', 'custom_headers',
  'polling', 'world', 'bases', 'privacy', 'history', 'features', 'players']
```

`frontend/src/components/SettingsPanel.test.ts`：`cfg().config` 的 `features` 加 `players: false`，加 `players` 节；用例名「9 节」→「10 节」，并断言渲染出玩家个体标题：

```typescript
  features: { report: true, events: true, guilds_bases: false, players: false },
  players: { rank_top_n: 5, exclude_names: '' },
```
```typescript
  it('加载后渲染 10 节（含 features 分组标题）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mount(SettingsPanel); await flushPromises()
    expect(w.text()).toContain('功能分组开关')
    expect(w.text()).toContain('玩家个体')
    expect(w.text()).toContain('保存并重载')
  })
```

- [ ] **Step 2: 运行验证失败**

Run: `cd frontend && npx vitest run src/lib/schema.test.ts src/lib/collect.test.ts src/components/SettingsPanel.test.ts`
Expected: FAIL（`OBJECT_SECTIONS` 仍 7 节、无 players 节、无「玩家个体」标题）

- [ ] **Step 3: 实现** `frontend/src/lib/schema.ts`

`OBJECT_SECTIONS` 的 `features` 节 `fields` 追加 `players` 开关：

```typescript
  { key: 'features', title: '功能分组开关', fields: [
    { key: 'report', type: 'bool', label: '日报/在线统计', default: true },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false },
    { key: 'players', type: 'bool', label: '玩家个体查询', default: false },
  ]},
```

`OBJECT_SECTIONS` 数组末尾（`features` 节之后）追加新节：

```typescript
  { key: 'players', title: '玩家个体', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'exclude_names', type: 'string', label: '排除名单（逗号分隔）', default: '' },
  ]},
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `cd frontend && npx vitest run src/lib/schema.test.ts src/lib/collect.test.ts src/components/SettingsPanel.test.ts`
Expected: PASS（`schema.test.ts` 的「字段集完全一致」也需 `_conf_schema.json` 已含 players——Task 1/2 已保证）

```bash
git add frontend/src/lib/schema.ts frontend/src/lib/schema.test.ts frontend/src/lib/collect.test.ts frontend/src/components/SettingsPanel.test.ts
git commit -m "feat(frontend): 设置页新增 players 开关与玩家个体配置节"
```

---

### Task 4: `migration_0003` 建两张新表

**Files:**
- Modify: `palchronicle/infrastructure/migrations.py`（`_MIGRATION_0003_SQL` / `migration_0003` / `MIGRATIONS`）
- Test: `tests/unit/migrations_players_test.py`（新建）

**Interfaces:**
- Produces: 表 `player_bindings(platform_hash, world_id, player_key, created_at, PK(platform_hash, world_id))`、`hidden_players(world_id, player_key, hidden_by, created_at, PK(world_id, player_key))`；`user_version` 升至 3。

- [ ] **Step 1: 写失败测试** `tests/unit/migrations_players_test.py`

```python
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _cols(db, table):
    rows = await db.query(f"PRAGMA table_info({table})")
    return {r[1] for r in rows}


async def test_migration_0003_creates_tables(tmp_path):
    db = Database(tmp_path / "m.db")
    await db.open()
    await apply_migrations(db)
    assert await _cols(db, "player_bindings") == {"platform_hash", "world_id", "player_key", "created_at"}
    assert await _cols(db, "hidden_players") == {"world_id", "player_key", "hidden_by", "created_at"}
    ver = await db.query("PRAGMA user_version")
    assert int(ver[0][0]) == 3
    await db.close()


async def test_migration_idempotent(tmp_path):
    db = Database(tmp_path / "m.db")
    await db.open()
    await apply_migrations(db)
    await apply_migrations(db)  # 第二次不应报错
    ver = await db.query("PRAGMA user_version")
    assert int(ver[0][0]) == 3
    await db.close()
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/migrations_players_test.py -v`
Expected: FAIL（表不存在 / `user_version==2`）

- [ ] **Step 3: 实现** `palchronicle/infrastructure/migrations.py`（在 `MIGRATIONS` 列表定义之前加）

```python
_MIGRATION_0003_SQL = [
    """
    CREATE TABLE IF NOT EXISTS player_bindings (
        platform_hash TEXT NOT NULL,
        world_id      TEXT NOT NULL,
        player_key    TEXT NOT NULL,
        created_at    INTEGER NOT NULL,
        PRIMARY KEY (platform_hash, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hidden_players (
        world_id   TEXT NOT NULL,
        player_key TEXT NOT NULL,
        hidden_by  TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (world_id, player_key)
    )
    """,
]


async def migration_0003(conn: aiosqlite.Connection) -> None:
    for stmt in _MIGRATION_0003_SQL:
        await conn.execute(stmt)
```

`MIGRATIONS` 列表追加 `migration_0003`：

```python
MIGRATIONS: list[Callable[[aiosqlite.Connection], Awaitable[None]]] = [
    migration_0001,
    migration_0002,
    migration_0003,
]
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/migrations_players_test.py -v`
Expected: PASS

```bash
git add palchronicle/infrastructure/migrations.py tests/unit/migrations_players_test.py
git commit -m "feat(db): migration_0003 建 player_bindings/hidden_players 两表"
```

---

### Task 5: repo 绑定/隐藏 CRUD

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`（5 个方法）
- Test: `tests/unit/repository_players_binding_test.py`（新建）

**Interfaces:**
- Consumes: Task 4 的两张表。
- Produces: `upsert_binding` / `get_binding` / `set_hidden` / `unset_hidden` / `get_hidden_keys`（签名见 Global Constraints）。

- [ ] **Step 1: 写失败测试** `tests/unit/repository_players_binding_test.py`

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_bind_and_get(repo):
    await repo.upsert_binding("phash", "w1", "k1")
    assert await repo.get_binding("phash", "w1") == "k1"
    assert await repo.get_binding("phash", "w2") is None
    assert await repo.get_binding("other", "w1") is None


async def test_bind_last_writer_wins(repo):
    await repo.upsert_binding("phash", "w1", "k1")
    await repo.upsert_binding("phash", "w1", "k2")
    assert await repo.get_binding("phash", "w1") == "k2"


async def test_hidden_set_get_unset(repo):
    await repo.set_hidden("w1", "k1", "phash")
    await repo.set_hidden("w1", "k2", "phash")
    assert await repo.get_hidden_keys("w1") == {"k1", "k2"}
    assert await repo.get_hidden_keys("w2") == set()
    await repo.unset_hidden("w1", "k1")
    assert await repo.get_hidden_keys("w1") == {"k2"}
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/repository_players_binding_test.py -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现**（追加到 `Repository` 类，照 `set_active`/`revoke`/`get_allowed` 范式）

```python
    async def upsert_binding(self, platform_hash: str, world_id: str, player_key: str) -> None:
        now = self._clock.now()
        await self._db.execute_write(
            "INSERT INTO player_bindings (platform_hash, world_id, player_key, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(platform_hash, world_id) DO UPDATE SET "
            "player_key=excluded.player_key, created_at=excluded.created_at",
            (platform_hash, world_id, player_key, now),
        )

    async def get_binding(self, platform_hash: str, world_id: str) -> str | None:
        rows = await self._db.query(
            "SELECT player_key FROM player_bindings WHERE platform_hash=? AND world_id=?",
            (platform_hash, world_id),
        )
        return rows[0][0] if rows else None

    async def set_hidden(self, world_id: str, player_key: str, hidden_by: str) -> None:
        now = self._clock.now()
        await self._db.execute_write(
            "INSERT INTO hidden_players (world_id, player_key, hidden_by, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(world_id, player_key) DO UPDATE SET "
            "hidden_by=excluded.hidden_by, created_at=excluded.created_at",
            (world_id, player_key, hidden_by, now),
        )

    async def unset_hidden(self, world_id: str, player_key: str) -> None:
        await self._db.execute_write(
            "DELETE FROM hidden_players WHERE world_id=? AND player_key=?",
            (world_id, player_key),
        )

    async def get_hidden_keys(self, world_id: str) -> set[str]:
        rows = await self._db.query(
            "SELECT player_key FROM hidden_players WHERE world_id=?", (world_id,)
        )
        return {r[0] for r in rows}
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/repository_players_binding_test.py -v`
Expected: PASS

```bash
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_players_binding_test.py
git commit -m "feat(repo): 玩家绑定/隐藏 CRUD（upsert_binding/get_binding/set_hidden/unset_hidden/get_hidden_keys）"
```

---

### Task 6: repo 枚举方法（排除名单 + 等级榜）

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`（`list_players_by_name` / `list_players_by_level`）
- Test: `tests/unit/repository_players_enum_test.py`（新建）

**Interfaces:**
- Produces: `list_players_by_name(world_id, name) -> list[str]`（该名全部 `player_key`）；`list_players_by_level(world_id) -> list[PlayerIdentity]`（滤 NULL 等级/名，按 `latest_level DESC, last_seen_at DESC`）。

- [ ] **Step 1: 写失败测试** `tests/unit/repository_players_enum_test.py`

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _add_player(repo, key, world, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, ?, ?, 0, ?, ?, NULL, 'high')",
        (key, world, name, last_seen, level),
    )


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_list_players_by_name_returns_all_matches(repo):
    await _add_player(repo, "k1", "w1", "Alice", 10, 100)
    await _add_player(repo, "k2", "w1", "Alice", 8, 200)   # 同名不同 key（HIGH/LOW）
    await _add_player(repo, "k3", "w1", "Bob", 5, 100)
    keys = set(await repo.list_players_by_name("w1", "Alice"))
    assert keys == {"k1", "k2"}
    assert await repo.list_players_by_name("w1", "Nobody") == []


async def test_list_players_by_level_orders_and_filters(repo):
    await _add_player(repo, "k1", "w1", "Alice", 10, 100)
    await _add_player(repo, "k2", "w1", "Bob", 20, 100)
    await repo._db.execute_write(  # 无等级/无名的脏行——须被滤除
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES ('k3', 'w1', NULL, 0, 100, NULL, NULL, 'low')", ())
    ranked = await repo.list_players_by_level("w1")
    assert [p.latest_name for p in ranked] == ["Bob", "Alice"]
    assert all(p.latest_level is not None for p in ranked)
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/repository_players_enum_test.py -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现**（追加到 `Repository`；`list_players_by_level` 照 `get_player` 的 `PlayerIdentity` 反序列化）

```python
    async def list_players_by_name(self, world_id: str, name: str) -> list[str]:
        rows = await self._db.query(
            "SELECT player_key FROM players WHERE world_id=? AND latest_name=?",
            (world_id, name),
        )
        return [r[0] for r in rows]

    async def list_players_by_level(self, world_id: str) -> list[PlayerIdentity]:
        rows = await self._db.query(
            "SELECT player_key, world_id, latest_name, first_seen_at, last_seen_at,"
            " latest_level, latest_guild_key, id_confidence"
            " FROM players"
            " WHERE world_id=? AND latest_level IS NOT NULL AND latest_name IS NOT NULL"
            " ORDER BY latest_level DESC, last_seen_at DESC",
            (world_id,),
        )
        return [
            PlayerIdentity(
                player_key=r["player_key"], world_id=r["world_id"],
                latest_name=r["latest_name"], first_seen_at=r["first_seen_at"],
                last_seen_at=r["last_seen_at"], latest_level=r["latest_level"],
                latest_guild_key=r["latest_guild_key"],
                id_confidence=IdConfidence(r["id_confidence"]),
            )
            for r in rows
        ]
```

> `PlayerIdentity` 与 `IdConfidence` 已在本文件顶部 import（`get_player` 已用）。

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/repository_players_enum_test.py -v`
Expected: PASS

```bash
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_players_enum_test.py
git commit -m "feat(repo): list_players_by_name（全匹配 key）/ list_players_by_level（等级榜枚举）"
```

---

### Task 7: `day_bounds` 抽取为共享函数

**Files:**
- Modify: `palchronicle/application/report_service.py`（新增模块级 `day_bounds`，`_day_bounds` 委托）
- Test: `tests/unit/day_bounds_test.py`（新建）；`tests/unit/report_service_test.py`（回归，保持通过）

**Interfaces:**
- Produces: `day_bounds(cfg, world, now, day=None) -> tuple[str, int, int]`（per-server tz → world tz，用 `timedelta(days=1)` 正确处理 DST）。`ReportService._day_bounds` 行为不变（委托）。

- [ ] **Step 1: 写失败测试** `tests/unit/day_bounds_test.py`

```python
from types import SimpleNamespace

from palchronicle.application.report_service import day_bounds
from palchronicle.domain.models import World

_W = World(world_id="w:g:0", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)


def _cfg(server_tz="", world_tz="Asia/Tokyo"):
    return SimpleNamespace(
        servers=[SimpleNamespace(server_id="w", timezone=server_tz)],
        world=SimpleNamespace(timezone=world_tz),
    )


def test_day_bounds_is_24h_and_midnight_aligned():
    # Asia/Tokyo 无 DST：一天恰 86400s，start 对齐本地午夜
    day, start, end = day_bounds(_cfg(), _W, 1_700_000_000)
    assert end - start == 86400
    assert day == "2023-11-15"  # 2023-11-15 09:33:20 JST 所在自然日


def test_per_server_tz_overrides_world_tz():
    # server tz 优先于全局 tz
    _, s_utc, _ = day_bounds(_cfg(server_tz="UTC", world_tz="Asia/Tokyo"), _W, 1_700_000_000)
    _, s_jst, _ = day_bounds(_cfg(server_tz="", world_tz="Asia/Tokyo"), _W, 1_700_000_000)
    assert s_utc != s_jst  # 不同时区午夜起点不同
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/day_bounds_test.py -v`
Expected: FAIL（`day_bounds` 不是模块级函数）

- [ ] **Step 3: 实现** `palchronicle/application/report_service.py`

模块级新增（放在 `ReportService` 类定义之前，import 段之后；`ZoneInfo`/`datetime`/`timedelta` 已 import）：

```python
def day_bounds(
    cfg: AppConfig, world: World, now: int, day: str | None = None
) -> tuple[str, int, int]:
    """自然日 [start, end) 边界（秒）。tz：per-server timezone 优先，回退 world tz。
    用 timedelta(days=1) 而非 +86400，正确处理 DST 的 23/25 小时日。"""
    server_tz = ""
    for s in cfg.servers:
        if s.server_id == world.server_id:
            server_tz = s.timezone
            break
    tz = ZoneInfo(server_tz or cfg.world.timezone)
    if day is None:
        local = datetime.fromtimestamp(now, tz)
        day = local.strftime("%Y-%m-%d")
    y, m, d = (int(x) for x in day.split("-"))
    start_local = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return day, int(start_local.timestamp()), int(end_local.timestamp())
```

`ReportService._day_bounds` 改为委托（保持类内签名不变）：

```python
    def _day_bounds(self, world: World, day: str | None) -> tuple[str, int, int]:
        return day_bounds(self._cfg, world, self._clock.now(), day)
```

若 `ReportService._tz` 此后无其它调用方（grep `self._tz(` 确认），删除它；否则保留。

- [ ] **Step 4: 运行验证通过（含 report 回归）+ 提交**

Run: `python -m pytest tests/unit/day_bounds_test.py tests/unit/report_service_test.py -v`
Expected: PASS（`report_service_test` 不回归——`daily` 的「今日」口径不变）

```bash
git add palchronicle/application/report_service.py tests/unit/day_bounds_test.py
git commit -m "refactor(report): 抽取模块级 day_bounds 供 rank 与 daily 共用（统一今日口径/修 DST）"
```

---

### Task 8: `QueryService` 玩家读逻辑（DTO + 排除面 + rank + player）

**Files:**
- Modify: `palchronicle/application/query_service.py`（DTO、`load_excluded_keys`、`rank`、`player_profile`）
- Test: `tests/unit/query_service_players_test.py`（新建）

**Interfaces:**
- Consumes: Task 5/6 repo 方法、Task 7 `day_bounds`、`cfg.players`/`cfg.privacy`。
- Produces: `PlayerProfileDTO`、`RankBoardsDTO`、`load_excluded_keys`、`rank`、`player_profile`（签名见 Global Constraints）。

- [ ] **Step 1: 写失败测试** `tests/unit/query_service_players_test.py`

```python
from types import SimpleNamespace

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.domain.enums import SessionStatus
from palchronicle.domain.models import World
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)


def _cfg(top_n=5, exclude=None, mode="balanced"):
    return SimpleNamespace(
        players=SimpleNamespace(rank_top_n=top_n, exclude_names=exclude or []),
        privacy=SimpleNamespace(mode=mode),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )


@pytest.fixture
async def env(tmp_path):
    db = Database(tmp_path / "q.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1_700_000_000)
    repo = Repository(db, clock)
    yield repo, clock
    await db.close()


def _qs(repo, clock, cfg):
    return QueryService(repo, TTLCache(clock), cfg, None, clock, {}, world_cache={}, report=None)


async def _add_player(repo, key, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, 'w1', ?, 0, ?, ?, NULL, 'high')", (key, name, last_seen, level))


async def _add_session(repo, key, joined, seconds, status="active"):
    await repo._db.execute_write(
        "INSERT INTO player_sessions (world_id, player_key, joined_at, "
        "last_confirmed_at, left_at, observed_seconds, status, leave_reason) "
        "VALUES ('w1', ?, ?, ?, NULL, ?, ?, NULL)",
        (key, joined, joined, seconds, status))


async def test_rank_level_board_desc_and_dedup(env):
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 30, 100)
    await _add_player(repo, "k2", "Bob", 20, 100)
    await _add_player(repo, "k3", "Alice", 25, 200)  # 同名第二 key → 去重
    dto = await _qs(repo, clock, _cfg()).rank(_W)
    assert dto.level_rows == [("Alice", 30), ("Bob", 20)]


async def test_rank_time_board_sums_and_top_n(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now); await _add_player(repo, "k2", "Bob", 1, now)
    await _add_session(repo, "k1", now, 3600); await _add_session(repo, "k1", now, 600)
    await _add_session(repo, "k2", now, 1800)
    dto = await _qs(repo, clock, _cfg(top_n=1)).rank(_W)
    assert dto.time_rows == [("Alice", 4200)]  # 3600+600 求和、Top1


async def test_excluded_names_and_hidden_filtered_from_rank(env):
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 30, 100)
    await _add_player(repo, "k2", "Bob", 20, 100)
    await repo.set_hidden("w1", "k2", "phash")           # Bob 自助隐藏
    dto = await _qs(repo, clock, _cfg(exclude=["Alice"])).rank(_W)  # Alice 排除名单
    assert dto.level_rows == []                          # 两人都被过滤


async def test_player_profile_online_and_not_found(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 12, now)
    await _add_session(repo, "k1", now, 900)
    dto = await _qs(repo, clock, _cfg()).player_profile(_W, "Alice")
    assert dto.name == "Alice" and dto.level == 12 and dto.online is True and dto.online_seconds == 900
    assert await _qs(repo, clock, _cfg()).player_profile(_W, "Ghost") is None


async def test_player_profile_hidden_returns_none(env):
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 12, 100)
    await repo.set_hidden("w1", "k1", "phash")
    assert await _qs(repo, clock, _cfg()).player_profile(_W, "Alice") is None
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/query_service_players_test.py -v`
Expected: FAIL（`rank`/`player_profile`/DTO 不存在）

> 若 `TTLCache` 导入路径不对，grep `class TTLCache` 对齐真实模块（container 里 `cache = TTLCache(self._clock)`）。

- [ ] **Step 3: 实现** `palchronicle/application/query_service.py`

文件顶部 import 段加：

```python
from dataclasses import dataclass
from palchronicle.application.report_service import day_bounds
```

DTO（放在模块其它 DTO 附近，如 `OnlineDTO` 定义处）：

```python
@dataclass(slots=True)
class PlayerProfileDTO:
    name: str
    level: int
    online: bool
    online_seconds: int


@dataclass(slots=True)
class RankBoardsDTO:
    time_rows: list[tuple[str, int]]   # (name, seconds)
    level_rows: list[tuple[str, int]]  # (name, level)
```

`QueryService` 加方法：

```python
    async def load_excluded_keys(self, world: World) -> set[str]:
        keys: set[str] = set()
        for name in self._cfg.players.exclude_names:
            for key in await self._repo.list_players_by_name(world.world_id, name):
                keys.add(key)
        keys |= await self._repo.get_hidden_keys(world.world_id)
        return keys

    async def rank(self, world: World) -> RankBoardsDTO:
        excluded = await self.load_excluded_keys(world)
        n = self._cfg.players.rank_top_n

        _day, start, end = day_bounds(self._cfg, world, self._clock.now())
        sessions = await self._repo.sessions_in_day(world.world_id, start, end)
        totals: dict[str, int] = {}
        for s in sessions:
            if s.player_key in excluded:
                continue
            totals[s.player_key] = totals.get(s.player_key, 0) + s.observed_seconds
        top_time = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
        time_rows: list[tuple[str, int]] = []
        for key, secs in top_time:
            ident = await self._repo.get_player(world.world_id, key)
            time_rows.append((ident.latest_name if ident is not None else key[:8], secs))

        players = await self._repo.list_players_by_level(world.world_id)
        level_rows: list[tuple[str, int]] = []
        seen: set[str] = set()
        for p in players:
            if p.player_key in excluded or p.latest_name in seen:
                continue
            seen.add(p.latest_name)
            level_rows.append((p.latest_name, p.latest_level))
            if len(level_rows) >= n:
                break

        return RankBoardsDTO(time_rows=time_rows, level_rows=level_rows)

    async def player_profile(self, world: World, name: str) -> PlayerProfileDTO | None:
        ident = await self._repo.get_player_by_name(world.world_id, name)
        if ident is None:
            return None
        excluded = await self.load_excluded_keys(world)
        if ident.player_key in excluded:
            return None
        session = await self._repo.get_open_session(world.world_id, ident.player_key)
        return PlayerProfileDTO(
            name=ident.latest_name, level=ident.latest_level,
            online=session is not None,
            online_seconds=session.observed_seconds if session is not None else 0,
        )
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/query_service_players_test.py -v`
Expected: PASS

```bash
git add palchronicle/application/query_service.py tests/unit/query_service_players_test.py
git commit -m "feat(query): rank 双榜 + player_profile + load_excluded_keys（排除名单∪自助隐藏）"
```

---

### Task 9: `_sender_id` helper（平台复合身份）

**Files:**
- Modify: `main.py`（`PalChronicle._sender_id`）
- Test: `tests/unit/sender_id_test.py`（新建）

**Interfaces:**
- Produces: `PalChronicle._sender_id(event) -> str`，返回 `f"{platform_name}:{sender_id}"`。

> **Spike（先做）**：grep AstrBot 依赖确认 `AstrMessageEvent` 上取平台名与发送者 id 的真实方法。复核已确认 `event.get_sender_id()` 存在且返回平台内 id；平台名用 `event.get_platform_name()`。若属性名不同，以实测为准调整下面实现与测试的 fake，并在提交信息注明。

- [ ] **Step 1: 写失败测试** `tests/unit/sender_id_test.py`

```python
from main import PalChronicle


class _FakeEvent:
    def __init__(self, platform, sender):
        self._p, self._s = platform, sender
    def get_platform_name(self):
        return self._p
    def get_sender_id(self):
        return self._s


def test_sender_id_is_platform_scoped_composite():
    assert PalChronicle._sender_id(_FakeEvent("aiocqhttp", "12345")) == "aiocqhttp:12345"


def test_sender_id_distinguishes_same_number_across_platforms():
    a = PalChronicle._sender_id(_FakeEvent("aiocqhttp", "12345"))
    b = PalChronicle._sender_id(_FakeEvent("telegram", "12345"))
    assert a != b
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/sender_id_test.py -v`
Expected: FAIL（`_sender_id` 不存在）

- [ ] **Step 3: 实现** `main.py`（在 `_umo`/`_is_admin` 等 context helper 附近）

```python
    @staticmethod
    def _sender_id(event) -> str:
        # 平台复合身份：单平台 sender id 跨平台会碰撞（QQ 12345 与 Telegram 12345），
        # 故与平台名组合成全局唯一。用作绑定主键的原始输入（落库前再 HMAC）。
        platform = getattr(event, "get_platform_name", lambda: "")() or ""
        sender = getattr(event, "get_sender_id", lambda: "")() or ""
        return f"{platform}:{sender}"
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/sender_id_test.py -v`
Expected: PASS

```bash
git add main.py tests/unit/sender_id_test.py
git commit -m "feat(main): _sender_id 平台复合身份 helper（防跨平台碰撞）"
```

---

### Task 10: `rank` 命令（注册 + Commands + formatter + main + locale）

**Files:**
- Modify: `palchronicle/presentation/command_registry.py`（`COMMANDS`/`HELP_LINE` 加 `rank`）
- Modify: `palchronicle/presentation/commands.py`（`Commands.rank`）
- Modify: `palchronicle/presentation/formatters.py`（`format_rank`）
- Modify: `palchronicle/presentation/locale.py`（`rank_empty`/`rank_time_strict`）
- Modify: `main.py`（`@pal.command("rank")` 薄壳）
- Test: `tests/unit/format_rank_test.py`、`tests/unit/commands_rank_test.py`（新建）

**Interfaces:**
- Consumes: `QueryService.rank`、`RankBoardsDTO`、`_fmt_duration`。
- Produces: `format_rank(dto, *, which, strict)`；命令 `rank` 归 `players` 组。

- [ ] **Step 1: 写失败测试** `tests/unit/format_rank_test.py`

```python
from palchronicle.application.query_service import RankBoardsDTO
from palchronicle.presentation.formatters import format_rank


def _dto():
    return RankBoardsDTO(time_rows=[("Alice", 4200), ("Bob", 1800)],
                         level_rows=[("Bob", 30), ("Alice", 25)])


def test_format_both_boards():
    out = format_rank(_dto(), which="both", strict=False)
    assert "今日在线时长榜" in out and "· Alice 1小时10分" in out
    assert "等级榜" in out and "· Bob Lv30" in out


def test_format_time_only():
    out = format_rank(_dto(), which="time", strict=False)
    assert "今日在线时长榜" in out and "等级榜" not in out


def test_strict_hides_time_board():
    out = format_rank(_dto(), which="both", strict=True)
    assert "今日在线时长榜" not in out and "等级榜" in out


def test_empty_boards_message():
    out = format_rank(RankBoardsDTO([], []), which="both", strict=False)
    assert out == "本服务器暂无玩家排行数据。"
```

`tests/unit/commands_rank_test.py`（命令层：gating + 参数分派；用轻量 stub）：

```python
from types import SimpleNamespace

import pytest

from palchronicle.application.query_service import RankBoardsDTO
from palchronicle.presentation.commands import Commands


class _Query:
    async def rank(self, world):
        return RankBoardsDTO(time_rows=[("A", 60)], level_rows=[("A", 9)])


def _cmds(mode="balanced", players_on=True):
    features = SimpleNamespace(enabled=lambda g: players_on if g == "players" else True)
    cfg = SimpleNamespace(features=features, privacy=SimpleNamespace(mode=mode))
    c = Commands(routing=None, query=_Query(), repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))
    async def _rw(umo, msg, sub, is_group):
        return SimpleNamespace(world_id="w1", server_id="w"), SimpleNamespace(name=msg, server_override=None), None
    c._resolve_world = _rw
    return c


async def test_rank_gated_off_returns_feature_disabled():
    out = await _cmds(players_on=False).rank("u", "", True)
    assert out == "该功能未开放：当前配置或服务器不支持。"


async def test_rank_time_in_strict_returns_notice():
    out = await _cmds(mode="strict").rank("u", "time", True)
    assert "strict" in out or "停用" in out


async def test_rank_default_shows_boards():
    out = await _cmds().rank("u", "", True)
    assert "等级榜" in out
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/format_rank_test.py tests/unit/commands_rank_test.py -v`
Expected: FAIL（`format_rank`/`Commands.rank` 不存在；`COMMAND_GROUP["rank"]` KeyError）

- [ ] **Step 3: 实现**

`command_registry.py`：`COMMANDS` 加 `("rank", "players")`；`HELP_LINE` 加 `"rank": "/pal rank [time|level]  排行榜"`。

`locale.py` 的 `MESSAGES` 加：

```python
    "rank_empty": "本服务器暂无玩家排行数据。",
    "rank_time_strict": "时长榜在 strict 隐私模式下停用。",
    "player_not_found": "未找到玩家「{name}」。",
    "me_unbound": "你还没绑定玩家，请用 /pal bind <玩家名> 绑定。",
    "me_hidden": "已将你从玩家排行/查询中隐藏。用 /pal me show 可恢复。",
    "me_shown": "已恢复你在玩家排行/查询中的可见性。",
    "bind_ok": "已绑定到玩家「{name}」。",
    "bind_not_found": "未找到玩家「{name}」，无法绑定。",
    "player_usage": "用法：/pal player <玩家名>",
    "bind_usage": "用法：/pal bind <玩家名>",
```

> 本任务只需 `rank_empty`/`rank_time_strict`（其余键 Task 11/12 用；一并加入不影响，避免多次改文件）。

`formatters.py` 加 `format_rank`（`_fmt_duration` 同文件已定义；`RankBoardsDTO` 从 query_service import）：

```python
from palchronicle.application.query_service import RankBoardsDTO


def format_rank(dto: RankBoardsDTO, *, which: str, strict: bool) -> str:
    blocks: list[str] = []
    if which in ("both", "time") and not strict and dto.time_rows:
        lines = ["今日在线时长榜："]
        for name, secs in dto.time_rows:
            lines.append(f"· {name} {_fmt_duration(secs)}")
        blocks.append("\n".join(lines))
    if which in ("both", "level") and dto.level_rows:
        lines = ["等级榜："]
        for name, level in dto.level_rows:
            lines.append(f"· {name} Lv{level}")
        blocks.append("\n".join(lines))
    if not blocks:
        return L("rank_empty")
    return "\n\n".join(blocks)
```

> 若 `formatters.py` 顶部 import query_service 造成循环导入（query_service 反过来 import formatters？grep 确认），则将 `format_rank` 的 `RankBoardsDTO` 改为 `TYPE_CHECKING` 惰性注解、运行时不 import。

`commands.py` 加 `Commands.rank`（照 `guild` 的 `@_gated` + `_resolve_world` 范式）：

```python
    @_gated
    async def rank(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "rank", is_group)
        if err is not None:
            return err
        strict = self._cfg.privacy.mode == "strict"
        which = arg.name.strip().lower()
        if which not in ("time", "level"):
            which = "both"
        if which == "time" and strict:
            return L("rank_time_strict")
        dto = await self._query.rank(world)
        return format_rank(dto, which=which, strict=strict)
```

> `commands.py` 顶部确保 `from palchronicle.presentation.formatters import format_rank`（与既有 `format_guild` 等同处 import）。

`main.py` 加薄壳（照 `status`）：

```python
    @pal.command("rank")
    async def rank(self, event):
        if (m := self._busy_msg()):
            yield event.plain_result(m)
            return
        yield event.plain_result(
            await self._container.commands.rank(self._umo(event), self._msg(event), self._is_group(event))
        )
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/format_rank_test.py tests/unit/commands_rank_test.py -v`
Expected: PASS

```bash
git add palchronicle/presentation/command_registry.py palchronicle/presentation/commands.py palchronicle/presentation/formatters.py palchronicle/presentation/locale.py main.py tests/unit/format_rank_test.py tests/unit/commands_rank_test.py
git commit -m "feat(cmd): /pal rank 时长今日榜+等级榜（strict 砍时长榜、排除面过滤）"
```

---

### Task 11: `player` 命令 + `format_player`

**Files:**
- Modify: `command_registry.py`（`player`）、`commands.py`（`Commands.player`）、`formatters.py`（`format_player`）、`main.py`（薄壳）
- Test: `tests/unit/format_player_test.py`、`tests/unit/commands_player_test.py`（新建）

**Interfaces:**
- Consumes: `QueryService.player_profile`、`PlayerProfileDTO`。
- Produces: `format_player(dto, *, strict)`（player 与 me 共用的单一 strict 裁剪点）。

- [ ] **Step 1: 写失败测试** `tests/unit/format_player_test.py`

```python
from palchronicle.application.query_service import PlayerProfileDTO
from palchronicle.presentation.formatters import format_player


def test_online_shows_level_status_duration():
    out = format_player(PlayerProfileDTO("Alice", 12, True, 3600), strict=False)
    assert "Alice" in out and "Lv12" in out and "在线" in out and "1小时0分" in out


def test_offline_hides_duration():
    out = format_player(PlayerProfileDTO("Alice", 12, False, 0), strict=False)
    assert "离线" in out and "小时" not in out and "分" not in out


def test_strict_hides_duration_even_online():
    out = format_player(PlayerProfileDTO("Alice", 12, True, 3600), strict=True)
    assert "Lv12" in out and "在线" in out and "小时" not in out
```

`tests/unit/commands_player_test.py`：

```python
from types import SimpleNamespace

from palchronicle.application.query_service import PlayerProfileDTO
from palchronicle.presentation.commands import Commands


class _Query:
    def __init__(self, dto):
        self._dto = dto
    async def player_profile(self, world, name):
        return self._dto


def _cmds(dto, mode="balanced"):
    features = SimpleNamespace(enabled=lambda g: True)
    cfg = SimpleNamespace(features=features, privacy=SimpleNamespace(mode=mode))
    c = Commands(routing=None, query=_Query(dto), repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))
    async def _rw(umo, msg, sub, is_group):
        return SimpleNamespace(world_id="w1"), SimpleNamespace(name=msg, server_override=None), None
    c._resolve_world = _rw
    return c


async def test_player_found():
    out = await _cmds(PlayerProfileDTO("Alice", 12, True, 900)).player("u", "Alice", True)
    assert "Alice" in out and "Lv12" in out


async def test_player_not_found():
    out = await _cmds(None).player("u", "Ghost", True)
    assert out == "未找到玩家「Ghost」。"


async def test_player_empty_name_usage():
    out = await _cmds(None).player("u", "", True)
    assert "用法" in out
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/format_player_test.py tests/unit/commands_player_test.py -v`
Expected: FAIL

- [ ] **Step 3: 实现**

`command_registry.py`：`COMMANDS` 加 `("player", "players")`；`HELP_LINE` 加 `"player": "/pal player <玩家名>  玩家查询"`。

`formatters.py` 加：

```python
from palchronicle.application.query_service import PlayerProfileDTO


def format_player(dto: PlayerProfileDTO, *, strict: bool) -> str:
    lines = [f"玩家 {dto.name}", f"· 等级 Lv{dto.level}",
             f"· 状态 {'在线' if dto.online else '离线'}"]
    if not strict and dto.online:
        lines.append(f"· 本次在线 {_fmt_duration(dto.online_seconds)}")
    return "\n".join(lines)
```

`commands.py` 加：

```python
    @_gated
    async def player(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "player", is_group)
        if err is not None:
            return err
        if not arg.name:
            return L("player_usage")
        dto = await self._query.player_profile(world, arg.name)
        if dto is None:
            return L("player_not_found", name=arg.name)
        return format_player(dto, strict=self._cfg.privacy.mode == "strict")
```

`main.py` 加 `@pal.command("player")` 薄壳（照 `rank`）。`commands.py` import 补 `format_player`。

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/format_player_test.py tests/unit/commands_player_test.py -v`
Expected: PASS

```bash
git add palchronicle/presentation/command_registry.py palchronicle/presentation/commands.py palchronicle/presentation/formatters.py main.py tests/unit/format_player_test.py tests/unit/commands_player_test.py
git commit -m "feat(cmd): /pal player 逐人查（精简字段、strict 砍时长、被隐藏者回 not_found）"
```

---

### Task 12: `me` + `bind` 命令（绑定/隐藏，平台哈希落库）

**Files:**
- Modify: `command_registry.py`（`me`/`bind`）、`commands.py`（`Commands.__init__` 加 `salt`、`me`、`bind`）、`container.py`（`Commands(...)` 传 `salt`）、`main.py`（`me`/`bind` 薄壳，传 `_sender_id`）
- Test: `tests/unit/commands_me_bind_test.py`（新建）

**Interfaces:**
- Consumes: `hash_user_id`、repo binding/hidden 方法、`QueryService.load_excluded_keys`、`_sender_id`、`format_player`。
- Produces: `Commands.__init__(..., salt: bytes = b"")`；`Commands.me(umo, message_str, is_group, sender_id)`；`Commands.bind(umo, message_str, is_group, sender_id)`。

- [ ] **Step 1: 写失败测试** `tests/unit/commands_me_bind_test.py`

```python
from types import SimpleNamespace

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.domain.models import World
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.presentation.commands import Commands

_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)
_SALT = b"x" * 32


def _cfg(exclude=None, mode="balanced"):
    return SimpleNamespace(
        features=SimpleNamespace(enabled=lambda g: True),
        privacy=SimpleNamespace(mode=mode),
        players=SimpleNamespace(rank_top_n=5, exclude_names=exclude or []),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )


@pytest.fixture
async def cmds_env(tmp_path):
    db = Database(tmp_path / "c.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1_700_000_000)
    repo = Repository(db, clock)

    def build(cfg):
        query = QueryService(repo, TTLCache(clock), cfg, None, clock, {}, world_cache={}, report=None)
        c = Commands(routing=None, query=query, repo=repo, cfg=cfg, clock=clock, salt=_SALT)
        async def _rw(umo, msg, sub, is_group):
            from palchronicle.presentation.server_arg import parse_arg
            return _W, parse_arg(msg, sub), None
        c._resolve_world = _rw
        return c
    yield repo, build
    await db.close()


async def _add_player(repo, key, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, 'w1', ?, 0, ?, ?, NULL, 'high')", (key, name, last_seen, level))


async def test_bind_then_me_shows_self(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    assert "已绑定" in await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.me("u", "me", True, "aiocqhttp:1")
    assert "Alice" in out and "Lv12" in out


async def test_me_unbound(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).me("u", "me", True, "aiocqhttp:9")
    assert "还没绑定" in out


async def test_bind_not_found(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).bind("u", "bind Ghost", True, "aiocqhttp:1")
    assert "未找到玩家" in out


async def test_bind_to_excluded_returns_not_found(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    await repo.set_hidden("w1", "k1", "byhash")           # Alice 被隐藏
    out = await build(_cfg()).bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "未找到玩家" in out                             # 存在性收敛


async def test_me_hide_then_excluded_from_rank(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 30, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "隐藏" in await c.me("u", "me hide", True, "aiocqhttp:1")
    dto = await c._query.rank(_W)
    assert dto.level_rows == []                            # Alice 自助隐藏后不出榜
    assert "恢复" in await c.me("u", "me show", True, "aiocqhttp:1")
    dto2 = await c._query.rank(_W)
    assert dto2.level_rows == [("Alice", 30)]
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/commands_me_bind_test.py -v`
Expected: FAIL（`me`/`bind` 不存在；`Commands` 无 `salt` 参数）

- [ ] **Step 3: 实现**

`command_registry.py`：`COMMANDS` 加 `("me", "players")`、`("bind", "players")`；`HELP_LINE` 加 `"me": "/pal me [hide|show]  我的信息"`、`"bind": "/pal bind <玩家名>  绑定我的玩家"`。

`commands.py`：顶部加 `from palchronicle.adapters.privacy_filter import hash_user_id`。`Commands.__init__` 末尾加 `salt` 参数（带默认，不破现存关键字构造）：

```python
    def __init__(self, routing, query, repo, cfg, clock, salt: bytes = b"") -> None:
        self._routing = routing
        self._query = query
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt
```

加 `me`/`bind` 方法：

```python
    @_gated
    async def bind(self, umo, message_str, is_group, sender_id) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "bind", is_group)
        if err is not None:
            return err
        if not arg.name:
            return L("bind_usage")
        ident = await self._repo.get_player_by_name(world.world_id, arg.name)
        if ident is None:
            return L("bind_not_found", name=arg.name)
        excluded = await self._query.load_excluded_keys(world)
        if ident.player_key in excluded:
            return L("bind_not_found", name=arg.name)   # 存在性收敛：被隐藏者不泄露存在
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        await self._repo.upsert_binding(phash, world.world_id, ident.player_key)
        return L("bind_ok", name=ident.latest_name)

    @_gated
    async def me(self, umo, message_str, is_group, sender_id) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "me", is_group)
        if err is not None:
            return err
        phash = hash_user_id(self._salt, world.world_id, sender_id)
        player_key = await self._repo.get_binding(phash, world.world_id)
        if player_key is None:
            return L("me_unbound")
        sub = arg.name.strip().lower()
        if sub == "hide":
            await self._repo.set_hidden(world.world_id, player_key, phash)
            return L("me_hidden")
        if sub == "show":
            await self._repo.unset_hidden(world.world_id, player_key)
            return L("me_shown")
        ident = await self._repo.get_player(world.world_id, player_key)
        if ident is None:
            return L("me_unbound")
        session = await self._repo.get_open_session(world.world_id, player_key)
        from palchronicle.application.query_service import PlayerProfileDTO
        dto = PlayerProfileDTO(
            name=ident.latest_name, level=ident.latest_level,
            online=session is not None,
            online_seconds=session.observed_seconds if session is not None else 0,
        )
        return format_player(dto, strict=self._cfg.privacy.mode == "strict")
```

> `me` 默认分支不经 `load_excluded_keys`——本人始终可看自己。

`container.py`：`Commands(...)` 构造改为传 `salt`（该函数作用域内 `salt = load_or_create_salt(self._data_dir)` 已存在）：

```python
        self.commands = Commands(self.routing, self.query, repo, self._cfg, self._clock, salt)
```

`main.py`：加 `me`/`bind` 薄壳，**多传 `self._sender_id(event)`**：

```python
    @pal.command("me")
    async def me(self, event):
        if (m := self._busy_msg()):
            yield event.plain_result(m)
            return
        yield event.plain_result(
            await self._container.commands.me(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event))
        )

    @pal.command("bind")
    async def bind(self, event):
        if (m := self._busy_msg()):
            yield event.plain_result(m)
            return
        yield event.plain_result(
            await self._container.commands.bind(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event))
        )
```

- [ ] **Step 4: 运行验证通过 + 提交**

Run: `python -m pytest tests/unit/commands_me_bind_test.py -v`
Expected: PASS

```bash
git add palchronicle/presentation/command_registry.py palchronicle/presentation/commands.py palchronicle/container.py main.py tests/unit/commands_me_bind_test.py
git commit -m "feat(cmd): /pal me（含 hide/show）+ /pal bind（平台哈希落库、存在性收敛）"
```

---

### Task 13: OFF 语义端到端 + README 文档

**Files:**
- Test: `tests/unit/players_group_off_test.py`（新建）
- Modify: `README.md`（命令表 + 功能组矩阵加 `players` 行）；`tests/unit/readme_test.py`（补断言）

**Interfaces:**
- Consumes: 全部前置任务。

- [ ] **Step 1: 写失败测试** `tests/unit/players_group_off_test.py`（照 `guilds_bases` OFF 现成范式：关组→四命令回 feature_disabled + help 不列）

```python
from types import SimpleNamespace

from palchronicle.presentation.commands import Commands
from palchronicle.presentation.formatters import format_help
from palchronicle.config import FeaturesConfig


def _cmds(players_on):
    features = FeaturesConfig(report=True, events=True, guilds_bases=False, players=players_on)
    cfg = SimpleNamespace(features=features, privacy=SimpleNamespace(mode="balanced"))
    return Commands(routing=None, query=None, repo=None, cfg=cfg, clock=SimpleNamespace(now=lambda: 0))


async def test_players_commands_gated_off():
    c = _cmds(players_on=False)
    for coro in (c.rank("u", "", True), c.player("u", "Alice", True),
                 c.me("u", "", True, "p:1"), c.bind("u", "Alice", True, "p:1")):
        assert await coro == "该功能未开放：当前配置或服务器不支持。"


def test_help_hides_players_when_off():
    off = format_help(None, False, FeaturesConfig(report=True, events=True, guilds_bases=False, players=False))
    on = format_help(None, False, FeaturesConfig(report=True, events=True, guilds_bases=False, players=True))
    assert "/pal rank" not in off and "/pal player" not in off
    assert "/pal rank" in on and "/pal bind" in on
```

`tests/unit/readme_test.py` 追加：

```python
def test_readme_documents_players_group():
    for phrase in ("/pal rank", "/pal player", "/pal me", "/pal bind", "players"):
        assert phrase in README, f"README 缺少 players 组说明: {phrase}"
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/unit/players_group_off_test.py tests/unit/readme_test.py -v`
Expected: FAIL（gating 已实现则前者可能过；README 断言必失败）

- [ ] **Step 3: 实现** —— 更新 `README.md`

命令详细表加四行（照既有表格列）：`/pal rank [time|level]`（players / 排行榜：今日时长+等级）、`/pal player <玩家名>`（players / 逐人查）、`/pal me [hide|show]`（players / 我的档案+自助隐藏）、`/pal bind <玩家名>`（players / 绑定平台账号↔玩家）。功能组矩阵加一行 `players`：默认**关**；关闭时命令 help 隐藏、调用回「未开放」；说明「玩家个体查询，含隐私考量；时长榜仅今日、等级榜含离线全体；strict 更保守；支持管理员排除名单与自助 /pal me hide」。

- [ ] **Step 4: 运行验证通过 + 全量回归 + 提交**

Run: `python -m pytest tests/ -q` 与 `cd frontend && npx vitest run`
Expected: PASS（全绿）

```bash
git add tests/unit/players_group_off_test.py README.md tests/unit/readme_test.py
git commit -m "test(players): OFF 语义端到端 + README 命令表/功能组矩阵补 players 行"
```

---

## 收尾（整分支终审前）

- 全量 `python -m pytest tests/ -q` + `cd frontend && npx vitest run` 双绿。
- 人工核对隐私三态在 rank/player/me 均生效；`_sender_id` 复合身份实测（Spike）已落实。
- **已知偏离（spec §6 孤儿清理）**：本批不实现 `player_bindings`/`hidden_players` 的孤儿 prune。世界重置后旧行 world-scoped、永不匹配当前查询、无泄露，spec §9.5 已登记为「低频、可接受」；prune 需一条「枚举当前全部 world_id」的路径，超出本批范围，留作 follow-up。整分支终审时确认此偏离可接受。

## Self-Review（写完计划后自查）

**Spec coverage：** §4 四命令→Task 10/11/12；§5 隐私（默认关 T1、排除∪隐藏 T8、strict 单点 format_player T11、组隔离=不碰 core）；§6 两表→T4/5、平台哈希→T12；§7 配置→T1/2、config_view 两处→T2、前端→T3；§9 风险 1(时长今日,T8 day_bounds)/2(复合 sender_id,T9)/3(list_players_by_name 全匹配,T6/T8)/4(griefing 接受,文档)/5(world-scoped,已登记偏离)/6(单一 load_excluded_keys,T8)/7(schema default,T2)/8(双写,T1)；§10 测试→各任务 + T13 OFF 端到端 + 前端锁定测试 T3。

**Placeholder scan：** 无 TBD；每个改动步骤含完整代码或精确编辑点。两处「grep 确认」（`_tz` 是否还有调用方 T7、`TTLCache`/循环导入路径）是既有代码对齐指令、非逻辑占位。

**Type consistency：** `RankBoardsDTO`/`PlayerProfileDTO` 定义于 T8、被 T10/11/12 消费，字段名一致；`format_rank(dto,*,which,strict)`/`format_player(dto,*,strict)` 全程一致；repo 方法签名与 Global Constraints 逐字一致；`Commands.__init__` 加 `salt` 带默认，container 位置传参已更新（T12）。
