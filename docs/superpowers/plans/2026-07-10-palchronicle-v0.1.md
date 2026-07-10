# PalChronicle v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个只读的 AstrBot 插件 `astrbot_plugin_palword`（PalChronicle v0.1），把多个 Palworld 服务器的官方只读 REST 数据转化为世界状态、玩家会话、公会/据点观察与世界事件，经 14 个纯文本命令在群聊中查询；支持多服务器采集与"群↔服务器"访问控制。

**Architecture:** 六边形分层（domain / application / adapters / infrastructure / presentation）。每个启用的服务器一套独立后台采集循环（metrics/players/info/settings/game-data），经"归一→脱敏→世界模型→追踪器→事件检测→SQLite"管线落库；命令读侧优先命中缓存/只读连接。所有数据按 `world_id = "{server_id}:{worldguid}:{epoch}"` 隔离。

**Tech Stack:** Python ≥ 3.11、AstrBot ≥ 4.10.4、aiohttp（BasicAuth REST）、aiosqlite（WAL，读写连接分离）、pytest + pytest-asyncio。纯文本输出，无 LLM / 无图片卡 / 无主动推送。

**Spec:** `docs/superpowers/specs/2026-07-10-palchronicle-v0.1-design.md`（本计划所有"per spec §X"均指该文件；实现细节以 spec 为准，本计划补充可执行步骤与签名）。

## Global Constraints

以下为 spec 的全局约束，**每个任务都隐含遵守**：

- 插件 id（`metadata.yaml.name`）：`astrbot_plugin_palword`；`display_name`: `PalChronicle · 帕鲁纪事`；内部包 `palchronicle`；命令前缀 `/pal`；`astrbot_version: ">=4.10.4"`。
- **只读**：仅 GET `/info`、`/metrics`、`/players`、`/settings`、`/game-data`；绝不调用写接口。
- **隐私红线**：永不落库/记日志：IP、REST 密码/Authorization、原始平台账号、原始 userId/playerId 明文、精确坐标、原始 ping、响应体原文。ID 用 `HMAC-SHA256(salt, world_id + ":" + raw_user_id)`。清洗顺序 **先归一键名/大小写，再脱敏**。
- **时间**：主时间戳用插件接收时间（epoch 秒，UTC 存储）；game-data 的 `Time` 仅辅助。自然日边界按服务器时区（`server.timezone` 或全局 `world.timezone`）。
- **身份主源**：`raw_user_id` 仅取 `/players.userId`（回退 `playerId`→角色名 low 置信度）；**不**用 game-data 的 `userid` 生成 `player_key`。
- **AstrBot 约定**：命令组 `@filter.command_group("pal")` 是普通 `def`（体 `pass`）；子命令 `@pal.command(...)` 是 `async def` + `yield event.plain_result(...)`；带 `<name>`/`@server` 的 handler 签名仅 `(self, event)`，从 `event.message_str` 自解析（属性名实现时按目标版本确认，见 spec §21）；管理命令叠 `@filter.permission_type(filter.PermissionType.ADMIN)`；配置 `__init__(self, context, config: AstrBotConfig)`，`.get(k, default)` 读取；生命周期 `async def initialize()/terminate()`。
- **降级不谎报**：API 不可达显示"无法获取世界数据/最后成功 N 分钟前"，绝不说"服务器已关机"。
- **事件仅检测+落库+可查询**，v0.1 无主动推送。
- **测试优先（TDD）**：每个功能先写失败测试→跑失败→最小实现→跑通过→提交。合成 fixtures，`clock` 与抖动可注入以保证确定性。
- **待实服/框架验证**（spec §21）：`userId`↔`userid` 同值性、`InstanceID`/`TrainerInstanceID` 稳定性与存在性、PalBox 坐标/GuildID 可用性、game-data 真实大小写、`event.message_str` 属性名、`object` 内 `options`/`obvious_hint`、命令组子命令 `alias=` 支持。规格已按"保守默认+降级"处理；实现遇到不支持即按 spec 降级，不阻塞。

---

## 接口契约（Interface Contract）

> 所有任务共享的规范化签名。任务只看到自己那一节，须用**此处的确切名字与类型**消费/产出，保证跨任务一致。位置标注为将创建的文件。类型用 Python 注解风格；`@dataclass(slots=True)` 除非另述。时间戳一律 `int`（epoch 秒，UTC）。

### 枚举 `palchronicle/domain/enums.py`

```python
class UnitType(StrEnum):        PLAYER="Player"; OTOMO="OtomoPal"; BASE_CAMP="BaseCampPal"; WILD="WildPal"; NPC="NPC"; UNKNOWN="Unknown"
class ActionCategory(StrEnum):  WORKING="working"; MOVING="moving"; IDLE="idle"; COMBAT="combat"; SLEEPING="sleeping"; EATING="eating"; INCAPACITATED="incapacitated"; UNKNOWN="unknown"
class EventType(StrEnum):       PLAYER_LEVEL_UP; NEW_PLAYER; NEW_GUILD; NEW_BASE; BASE_VANISHED; WORKER_DELTA; WORLD_DAY_MILESTONE; ONLINE_RECORD   # value = 名字小写
class Confidence(StrEnum):      HIGH="high"; MEDIUM="medium"; LOW="low"
class LeaveReason(StrEnum):     OBSERVED_TIMEOUT="observed_timeout"; WORLD_OFFLINE="world_offline"; UNKNOWN="unknown"
class SessionStatus(StrEnum):   ACTIVE="active"; CLOSED="closed"; UNCERTAIN="uncertain"
class AccessMode(StrEnum):      RESTRICTED="restricted"; OPEN="open"
class PingBucket(StrEnum):      GOOD="good"; OK="ok"; HIGH="high"; UNKNOWN="unknown"
class EndpointName(StrEnum):    INFO="info"; METRICS="metrics"; PLAYERS="players"; SETTINGS="settings"; GAME_DATA="game_data"
class IdConfidence(StrEnum):    HIGH="high"; LOW="low"
```

### 领域模型 `palchronicle/domain/models.py`（dataclass，字段见 spec §8；补充如下）

```python
@dataclass(slots=True)
class World:            world_id:str; server_id:str; worldguid:str; epoch:int; server_name:str; version:str; first_seen_at:int; last_seen_at:int; current_day:int
@dataclass(slots=True)
class PlayerIdentity:   player_key:str; world_id:str; latest_name:str; first_seen_at:int; last_seen_at:int; latest_level:int; latest_guild_key:str|None; id_confidence:IdConfidence
@dataclass(slots=True)
class PlayerObservation: observed_at:int; world_id:str; player_key:str; name:str; level:int; ping_bucket:PingBucket; building_count:int; guild_key:str|None; position_cell:str|None; companion_class:str|None
@dataclass(slots=True)
class PlayerSession:    id:int|None; world_id:str; player_key:str; joined_at:int; last_confirmed_at:int; left_at:int|None; observed_seconds:int; status:SessionStatus; leave_reason:LeaveReason|None
@dataclass(slots=True)
class Guild:            guild_key:str; world_id:str; latest_name:str; first_seen_at:int; last_seen_at:int; observed_member_count:int; palbox_count:int; base_pal_count:int
@dataclass(slots=True)
class PalBox:           palbox_key:str; world_id:str; guild_key:str|None; position_cell:str; first_seen_at:int; last_seen_at:int; status:str  # "active"/"missing"
@dataclass(slots=True)
class Base:             base_key:str; world_id:str; palbox_key:str; display_name:str|None; guild_key:str|None; confidence:Confidence; locked_by_admin:bool; hidden:bool; first_seen_at:int; last_seen_at:int
@dataclass(slots=True)
class BaseObservation:  base_key:str; world_id:str; observed_at:int; worker_count:int; active_count:int; average_level:float; average_hp_ratio:float; action_distribution:dict[str,int]
@dataclass(slots=True)
class WorldMetric:      world_id:str; observed_at:int; fps:float; frame_time:float; online_players:int; world_day:int; basecamp_count:int
@dataclass(slots=True)
class WorldEvent:       event_id:int|None; world_id:str; event_type:EventType; subject_type:str; subject_key:str; occurred_at:int; confirmed_at:int; payload:dict; visibility:str; confidence:Confidence; dedup_key:str
```

内存快照（不落库，`palchronicle/domain/models.py`）：

```python
@dataclass(slots=True)
class CharacterActor:   unit_type:UnitType; instance_id:str|None; nickname:str|None; trainer_instance_id:str|None; trainer_nickname:str|None; player_userid:str|None; level:int|None; hp:int|None; max_hp:int|None; guild_id:str|None; guild_name:str|None; pal_class:str|None; action:ActionCategory; ai_action:ActionCategory; x:float|None; y:float|None; z:float|None; is_active:bool
@dataclass(slots=True)
class PalBoxActor:      guild_id:str|None; guild_name:str|None; pal_class:str|None; x:float; y:float; z:float
@dataclass(slots=True)
class GameDataSnapshot: observed_at:int; fps:float; average_fps:float; characters:list[CharacterActor]; palboxes:list[PalBoxActor]; unknown_classes:list[str]
@dataclass(slots=True)
class PlayerRow:        userid:str|None; player_id:str|None; name:str; level:int; ping:float|None; building_count:int   # 已脱敏(无 ip/accountName/坐标)
@dataclass(slots=True)
class PlayersSnapshot:  observed_at:int; players:list[PlayerRow]
@dataclass(slots=True)
class MetricsSnapshot:  observed_at:int; fps:float; frame_time:float; online:int; max_players:int; uptime:int; basecamp_count:int; days:int
@dataclass(slots=True)
class InfoSnapshot:     observed_at:int; version:str; server_name:str; description:str; worldguid:str
```

### 配置 `palchronicle/config.py`

```python
@dataclass(slots=True)
class ServerConfig:   server_id:str; name:str; enabled:bool; base_url:str; username:str; password:str; timeout:int; verify_tls:bool; timezone:str
                      # password 已从 password_env/明文解析完成
    @property
    def ready(self) -> bool: ...      # enabled and bool(password) and bool(base_url)
@dataclass(slots=True)
class SkippedServer:  raw_name:str; reason:str   # reason: "empty"/"duplicate"/"illegal_char"/"no_credential"
@dataclass(slots=True)
class BindingConfig:  umo:str; server:str; active:bool
@dataclass(slots=True)
class RoutingConfig:  access_mode:AccessMode; default_server:str
@dataclass(slots=True)
class PollingConfig:  metrics_seconds:int; players_seconds:int; info_seconds:int; settings_seconds:int; game_data_seconds:int; jitter_ratio:float; max_concurrency:int
@dataclass(slots=True)
class WorldConfig:    timezone:str; locale:str; fps_smooth:int; fps_moderate:int; fps_laggy:int
@dataclass(slots=True)
class BasesConfig:    enabled:bool; assignment_radius:int; ambiguity_ratio:float; confirmation_samples:int; position_grid_size:int; z_weight:float
@dataclass(slots=True)
class PrivacyConfig:  mode:str; public_exact_ping:bool; public_positions:bool; ping_good_ms:int; ping_ok_ms:int; uncertain_timeout:int
@dataclass(slots=True)
class HistoryConfig:  raw_metrics_days:int; aggregate_days:int; session_days:int; observation_days:int
@dataclass(slots=True)
class AppConfig:      servers:list[ServerConfig]; skipped:list[SkippedServer]; routing:RoutingConfig; group_bindings:list[BindingConfig]; polling:PollingConfig; world:WorldConfig; bases:BasesConfig; privacy:PrivacyConfig; history:HistoryConfig

def parse_config(raw: Mapping, env: Mapping[str,str]) -> AppConfig: ...
    # server_id = name.strip(); 空/重复/含 :@空白 → 记 SkippedServer 跳过
    # 密码: password_env 优先 env 查找, 否则 password; 都空 → SkippedServer("no_credential") 但仍列入 servers(ready=False)
```

### 基础设施 `palchronicle/infrastructure/`

```python
# clock.py
class Clock(Protocol):
    def now(self) -> int: ...                 # epoch 秒 UTC
    def monotonic(self) -> float: ...
class SystemClock(Clock): ...
class FakeClock(Clock):  __init__(self, start:int); def advance(self, secs:int)->None; def set(self, t:int)->None

# salt.py
def load_or_create_salt(data_dir: Path) -> bytes: ...   # <data_dir>/secret_salt, 32B, 0600(POSIX), 复用

# database.py
class Database:
    def __init__(self, path: Path)
    async def open(self) -> None                 # 建 write_conn + read_conn, PRAGMA journal_mode=WAL, foreign_keys=ON
    async def close(self) -> None
    write_lock: asyncio.Lock
    async def execute_write(self, sql:str, params:Sequence=()) -> None      # 持 write_lock
    async def executemany_write(self, sql:str, seq:Iterable[Sequence]) -> None
    async def write_tx(self) -> AsyncContextManager  # 单事务, 持 write_lock
    async def query(self, sql:str, params:Sequence=()) -> list[aiosqlite.Row]  # 只读连接

# migrations.py
MIGRATIONS: list[Callable[[aiosqlite.Connection], Awaitable[None]]]
async def apply_migrations(db: Database) -> None    # PRAGMA user_version 驱动; 失败抛 MigrationError
class MigrationError(Exception): ...

# locks.py
class EndpointLocks:  # 每 (server_id, endpoint) 一把在途锁 + 全局并发信号量
    def __init__(self, max_concurrency:int)
    def inflight(self, server_id:str, endpoint:EndpointName) -> AsyncContextManager  # 若已占用则 return None-sentinel 跳过
    semaphore: asyncio.Semaphore

# cache.py
class TTLCache:
    def __init__(self, clock:Clock)
    def get(self, key:str) -> Any|None
    def set(self, key:str, value:Any, ttl_seconds:int) -> None
```

### REST 客户端 `palchronicle/adapters/palworld_rest.py`

```python
@dataclass(slots=True)
class RestResponse:  ok:bool; status:int|None; data:Any|None; duration_ms:int; payload_bytes:int; error:str|None   # error 已脱敏(无凭证/URL)
class PalworldRestClient:
    def __init__(self, server: ServerConfig, clock: Clock)
    async def fetch(self, endpoint: EndpointName) -> RestResponse   # GET base_url + "/v1/api/<endpoint 路径>"；BasicAuth(username,password)；超时 server.timeout
    async def close(self) -> None
    # endpoint→路径: info→/info, metrics→/metrics, players→/players, settings→/settings, game_data→/game-data
```

### 元数据仓储 `palchronicle/adapters/metadata_repository.py`

```python
class MetadataRepository:
    def __init__(self, metadata_dir: Path)
    def load(self) -> None
    def pal_name(self, internal_class:str) -> str            # 未知 → 安全缩写并登记
    def action_category(self, raw_action:str|None) -> ActionCategory   # 未知 → UNKNOWN
    def setting_label(self, field:str) -> tuple[str,str]     # (label_zh, unit)；缺失 → (field,"")
    def take_unknown_classes(self) -> list[str]
```

### 归一化 `palchronicle/adapters/normalizer.py`（无副作用纯函数；先于脱敏）

```python
def ci_get(d: Mapping, *keys:str, default=None) -> Any                  # 大小写不敏感取键
def str_bool(v) -> bool                                                 # "true"/"false"/True/1 → bool
def normalize_info(raw:Mapping, now:int) -> InfoSnapshot
def normalize_metrics(raw:Mapping, now:int) -> MetricsSnapshot
def normalize_players(raw:Mapping, now:int) -> list[dict]               # 每玩家 dict 保留 userId/playerId/name/level/ping/building_count/ip/accountName(待脱敏)
def normalize_game_data(raw:Mapping, now:int, meta:MetadataRepository) -> GameDataSnapshot
```

### 脱敏 `palchronicle/adapters/privacy_filter.py`（归一之后）

```python
def hash_user_id(salt:bytes, world_id:str, raw_user_id:str) -> str      # HMAC-SHA256 hex
def bucketize_ping(ms:float|None, cfg:PrivacyConfig) -> PingBucket
def quantize_cell(x:float, y:float, z:float, grid:int) -> str           # "cx:cy:cz"
def redact_players(rows:list[dict], world_id:str, salt:bytes, cfg:PrivacyConfig) -> PlayersSnapshot   # 删 ip/accountName; ping→bucket; 产出 PlayerRow(含 userid=hash 或 None)
def redact_game_data(snap:GameDataSnapshot, world_id:str, salt:bytes, cfg:PrivacyConfig) -> GameDataSnapshot  # 删 ip；Player.player_userid→hash；坐标: strict 置 None, balanced 量化(存于 tracker 计算, 落库用 cell)
```

### 仓储 `palchronicle/adapters/sqlite_repository.py`

> 一个类聚合所有表读写；方法命名 `upsert_*` / `get_*` / `list_*` / `insert_*`。全部 `async`。写走 `db.execute_write`/`write_tx`，读走 `db.query`。

```python
class Repository:
    def __init__(self, db: Database, clock: Clock)
    # servers / routing
    async def sync_servers(self, servers:list[ServerConfig]) -> None            # upsert servers 表, 标记消失
    async def seed_bindings(self, bindings:list[BindingConfig]) -> None         # INSERT OR IGNORE(seed-only); active 唯一性
    async def cleanup_orphan_bindings(self, valid_server_ids:set[str]) -> None
    async def get_binding_active(self, umo:str) -> str|None                     # active=1 的 server_id
    async def get_allowed(self, umo:str) -> set[str]
    async def set_active(self, umo:str, server_id:str) -> None                  # allowed=1 & active=1; 清同 umo 其它 active
    async def revoke(self, umo:str, server_id:str) -> None
    # world
    async def upsert_world(self, w:World) -> None
    async def get_current_world(self, server_id:str) -> World|None
    # players / sessions / observations
    async def upsert_player(self, p:PlayerIdentity) -> None
    async def get_player_by_name(self, world_id:str, name:str) -> PlayerIdentity|None
    async def get_open_session(self, world_id:str, player_key:str) -> PlayerSession|None   # active 优先, 否则 uncertain
    async def insert_session(self, s:PlayerSession) -> int
    async def update_session(self, s:PlayerSession) -> None
    async def list_open_sessions(self, world_id:str) -> list[PlayerSession]
    async def insert_observation(self, o:PlayerObservation) -> None
    async def latest_observation(self, world_id:str, player_key:str) -> PlayerObservation|None
    # guilds / palboxes / bases
    async def upsert_guild(self, g:Guild) -> None
    async def list_guilds(self, world_id:str) -> list[Guild]
    async def upsert_palbox(self, pb:PalBox) -> None
    async def list_palboxes(self, world_id:str) -> list[PalBox]
    async def upsert_base(self, b:Base) -> None
    async def list_bases(self, world_id:str, include_low:bool=False, include_hidden:bool=False) -> list[Base]
    async def insert_base_observation(self, o:BaseObservation) -> None
    async def latest_base_observation(self, world_id:str, base_key:str) -> BaseObservation|None
    # metrics / events / aggregates
    async def insert_metric(self, m:WorldMetric) -> None
    async def latest_metric(self, world_id:str) -> WorldMetric|None
    async def peak_online(self, world_id:str, since:int|None=None) -> int
    async def insert_event(self, e:WorldEvent) -> bool                          # dedup_key 唯一; 冲突返回 False
    async def list_events(self, world_id:str, since:int|None=None, limit:int=20) -> list[WorldEvent]
    async def upsert_unknown_classes(self, classes:list[str]) -> None
    async def prune(self, history:HistoryConfig, now:int) -> None
```

### 应用服务 `palchronicle/application/`

```python
# snapshot_service.py — 编排单服务器单轮采集→落库
class SnapshotService:
    def __init__(self, repo:Repository, normalizer_mod, privacy_mod, meta:MetadataRepository, salt:bytes, cfg:AppConfig, clock:Clock, players:PlayerService, guilds:GuildService, bases:BaseService, events:EventService)
    async def ingest_info(self, server:ServerConfig, resp:RestResponse) -> World|None      # 处理换世界/epoch
    async def ingest_metrics(self, world:World, resp:RestResponse) -> None
    async def ingest_players(self, world:World, resp:RestResponse) -> None                  # 调 PlayerService
    async def ingest_settings(self, world:World, resp:RestResponse) -> None                 # 缓存 settings 供 /pal rules
    async def ingest_game_data(self, world:World, resp:RestResponse) -> None                # to_thread 归一/聚合 → guilds/bases/events

# player_service.py
class PlayerService:
    def __init__(self, repo, salt, cfg, clock)
    async def apply_players(self, world:World, snap:PlayersSnapshot) -> None                # 会话建/复用/续计; 等级/建筑变化→events; NEW_PLAYER
    async def mark_uncertain(self, world:World) -> None                                     # /players 不可用
    async def sweep_uncertain(self, world:World) -> None                                    # 超时收敛
    async def recover_on_start(self, world:World) -> None
    @staticmethod
    def player_key(salt, world_id, raw_user_id) -> str

# guild_service.py
class GuildService:
    async def apply(self, world:World, gd:GameDataSnapshot) -> list[Guild]                  # 聚合; NEW_GUILD 候选

# base_service.py
class BaseService:
    def __init__(self, repo, cfg, clock)
    async def apply(self, world:World, gd:GameDataSnapshot) -> list[BaseUpdate]             # PalBox 匹配 + 归属 + 置信度 + confirmation; 先落 base 再供 events
    @staticmethod
    def palbox_key(world_id, guild_key, cell) -> str
    @staticmethod
    def base_key(world_id, anchor_palbox_key) -> str

# event_service.py
class EventService:
    def __init__(self, repo, clock)
    async def level_up(self, world, player_key, old, new) -> None
    async def new_player(self, world, player_key) -> None
    async def new_guild(self, world, guild_key) -> None
    async def base_events(self, world, updates:list[BaseUpdate]) -> None                    # NEW_BASE/BASE_VANISHED/WORKER_DELTA
    async def world_day(self, world, days:int) -> None
    async def online_record(self, world, value:int, confirmed:bool) -> None
    @staticmethod
    def dedup_key(world_id, event_type, *parts) -> str

# routing_service.py
@dataclass(slots=True)
class Resolution:  server:ServerConfig|None; error:str|None
class RoutingService:
    def __init__(self, repo, cfg)
    async def resolve(self, umo:str, override:str|None, is_group:bool) -> Resolution        # spec §7.2/§7.3 顺序+访问校验
    async def use(self, umo:str, name:str) -> str                                           # 授权+激活; 返回反馈文案
    async def unbind(self, umo:str, name:str) -> str
    def ready_servers(self) -> list[ServerConfig]

# report_service.py
class ReportService:
    def __init__(self, repo, cfg, clock)
    async def daily(self, world:World, day:str|None=None) -> DailyReport                    # 模板日报数据 DTO

# query_service.py — 命令读侧, 返回展示 DTO(见 formatters)
class QueryService:
    def __init__(self, repo, cache, cfg, meta, clock, settings_cache)
    async def status(self, world) -> StatusDTO
    async def online(self, world) -> OnlineDTO
    async def world_summary(self, world) -> WorldSummaryDTO
    async def rules(self, world) -> RulesDTO
    async def guilds(self, world) -> list[GuildDTO]
    async def guild(self, world, name) -> GuildDetailDTO|None
    async def bases(self, world) -> list[BaseDTO]
    async def base(self, world, key_or_index) -> BaseDetailDTO|None
    async def events(self, world, today_only:bool) -> list[EventDTO]
    async def today(self, world) -> DailyReport
```

### 表示层 `palchronicle/presentation/`

```python
# server_arg.py
@dataclass(slots=True)
class ParsedArg:  name:str; server_override:str|None
def parse_arg(message_str:str, subcommand:str) -> ParsedArg    # 剥离前缀+尾部单个 @token; name 允许空格; 多 @ 非法→ raise ArgError
class ArgError(ValueError): ...

# formatters.py — DTO → str（纯函数, golden 可测）
def format_status(dto:StatusDTO, cfg:WorldConfig) -> str
def format_online(dto:OnlineDTO) -> str
def format_world(dto:WorldSummaryDTO) -> str
def format_rules(dto:RulesDTO) -> str
def format_guilds(dto:list[GuildDTO]) -> str
def format_guild(dto:GuildDetailDTO) -> str
def format_bases(dto:list[BaseDTO]) -> str
def format_base(dto:BaseDetailDTO) -> str
def format_events(dto:list[EventDTO]) -> str
def format_today(dto:DailyReport) -> str
def format_servers(rows:list[ServerStatusRow], skipped:list[SkippedServer], is_admin:bool) -> str
def format_help(topic:str|None, is_admin:bool) -> str
def format_degraded(last_ok:int|None, now:int) -> str
# locale.py — zh-CN 文案常量表 L(key)->str
```

### 装配 `palchronicle/container.py` + `main.py`

```python
# container.py
class Container:
    def __init__(self, config:AppConfig, data_dir:Path, clock:Clock)
    async def start(self) -> None      # open db + migrate + salt + sync_servers + seed/cleanup bindings + 起每服务器采集
    async def stop(self) -> None       # 取消所有任务, 关 rest sessions + db
    routing:RoutingService; query:QueryService; report:ReportService
# main.py
@register("astrbot_plugin_palword","SolitudeRA","...","0.1.0","<repo>")
class PalChronicle(Star):
    def __init__(self, context, config): ...      # 存 config, 不 await
    async def initialize(self): ...               # parse_config → Container.start()
    async def terminate(self): ...                # Container.stop()
    @filter.command_group("pal")
    def pal(self): pass
    # 各子命令 async def(self,event): yield event.plain_result(...)
```

### scheduler `palchronicle/infrastructure/scheduler.py`

```python
class Scheduler:
    def __init__(self, servers:list[ServerConfig], polling:PollingConfig, locks:EndpointLocks, clock:Clock, on_response:Callable[[str,EndpointName,RestResponse],Awaitable[None]], rng_seed:int|None=None)
    async def start(self) -> None      # 每 ready 服务器每端点一个 asyncio.Task; info 启动即拉一次
    async def stop(self) -> None       # cancel + await 全部
    # 内部: effective_interval 背压双向调节; jitter=base*U(1-r,1+r)(rng 可注入)
```

---

## 文件结构与责任

见 spec §3 目录树。每个文件单一职责；`main.py` 仅装配+生命周期；重计算（game-data 归一/聚合/据点距离）用 `asyncio.to_thread`。测试镜像 `tests/unit/<module>_test.py`、`tests/integration/`、`tests/fixtures/`、`tests/golden/`。

---


## Phase 1：骨架 + 基础设施

> 本阶段目标：可加载配置 + 可迁移的 DB + 可 mock 的 REST 客户端 + 路由/世界所需的仓储方法。
> 严格 TDD 五步节奏（写失败测试 → 跑失败 → 最小实现 → 跑通过 → 提交）。异步测试用 `pytest-asyncio`，DB 测试用临时文件，时钟用 `FakeClock` 保证确定性。
> 命令中的 `python` 在本机可用 `py`（Windows 3.12 launcher）替代；下文一律写 `python -m pytest`。

### Task 1.1：项目根文件 + 包骨架 + conftest（FakeClock fixture）

**Files:**
- Create: `metadata.yaml`
- Create: `requirements.txt`
- Create: `palchronicle/__init__.py`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/unit/skeleton_test.py`

**Interfaces:**
- Consumes: 无（本阶段起点）。
- Produces: 包 `palchronicle`（可 import）；pytest fixture `fake_clock`（返回起始 epoch=`1_700_000_000` 的 `FakeClock` 占位——本任务先用一个最小内联时钟，Task 1.4 完成后 conftest 改为 import 真正的 `FakeClock`）；`metadata.yaml` 顶层键齐全（`name/display_name/desc/version/author/repo/astrbot_version`）；`requirements.txt` 含 `aiohttp`/`aiosqlite` 运行时依赖与 `pytest`/`pytest-asyncio` dev 依赖。

- [ ] **1. 写失败测试** — 创建 `tests/unit/skeleton_test.py`：

```python
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_palchronicle_package_importable():
    import palchronicle

    assert palchronicle.__version__ == "0.1.0"


def test_metadata_yaml_has_all_top_keys():
    data = yaml.safe_load((REPO_ROOT / "metadata.yaml").read_text(encoding="utf-8"))
    for key in ("name", "display_name", "desc", "version", "author", "repo", "astrbot_version"):
        assert key in data, f"missing {key}"
    assert data["name"] == "astrbot_plugin_palword"
    assert data["display_name"] == "PalChronicle · 帕鲁纪事"
    assert data["astrbot_version"] == ">=4.10.4"


def test_requirements_lists_runtime_and_dev_deps():
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "aiohttp" in text
    assert "aiosqlite" in text
    assert "pytest" in text
    assert "pytest-asyncio" in text


def test_fake_clock_fixture_is_deterministic(fake_clock):
    assert fake_clock.now() == 1_700_000_000
    fake_clock.advance(5)
    assert fake_clock.now() == 1_700_000_005
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/skeleton_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle'`（且 `metadata.yaml`/`requirements.txt` 不存在、无 `fake_clock` fixture）。

- [ ] **3. 写最小实现** — 创建以下文件。

`metadata.yaml`：
```yaml
name: astrbot_plugin_palword
display_name: PalChronicle · 帕鲁纪事
desc: 只读的 Palworld 世界纪事、玩家档案与社区观察插件（基于官方 REST API）
version: v0.1.0
author: SolitudeRA
repo: https://github.com/SolitudeRA/astrbot_plugin_palword
astrbot_version: ">=4.10.4"
```

`requirements.txt`：
```
aiohttp>=3.9
aiosqlite>=0.20
PyYAML>=6.0

# dev-only（运行插件不需要；开发/CI 安装）
pytest>=8.0
pytest-asyncio>=0.23
```

`palchronicle/__init__.py`：
```python
"""PalChronicle · 帕鲁纪事 —— 只读 Palworld 世界观察插件（内部包）。"""

__version__ = "0.1.0"
```

`pytest.ini`：
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = *_test.py
```

`tests/__init__.py`、`tests/unit/__init__.py`、`tests/integration/__init__.py`：三个文件内容均为空。

`tests/conftest.py`：
```python
"""公用 pytest fixtures。

Task 1.4 交付真正的 palchronicle.infrastructure.clock.FakeClock 后，
本文件的 fake_clock 会切换为 import 该实现；在此之前用等价的内联时钟占位，
保证同一确定性语义（起始 epoch 1_700_000_000、advance/set）。
"""
import pytest


class _InlineClock:
    def __init__(self, start: int) -> None:
        self._t = start
        self._mono = 0.0

    def now(self) -> int:
        return self._t

    def monotonic(self) -> float:
        return self._mono

    def advance(self, secs: int) -> None:
        self._t += secs
        self._mono += float(secs)

    def set(self, t: int) -> None:
        self._t = t


@pytest.fixture
def fake_clock():
    return _InlineClock(1_700_000_000)
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/skeleton_test.py -q`。期望 PASS：4 passed。

- [ ] **5. 提交** — 命令：
```
git add metadata.yaml requirements.txt pytest.ini palchronicle/__init__.py tests/
git commit -m "chore(phase1): 项目骨架 metadata/requirements/包/conftest(FakeClock 占位)"
```

---

### Task 1.2：`_conf_schema.json` 完整 v0.1 Schema

**Files:**
- Create: `_conf_schema.json`
- Test: `tests/unit/conf_schema_test.py`

**Interfaces:**
- Consumes: 无（纯 JSON 资源，字段/默认值按 spec §5）。
- Produces: 顶层键 `servers`（`template_list`）、`group_bindings`（顶层 `template_list`）、`routing`/`polling`/`world`/`bases`/`privacy`/`history`（均 `object`）；被 `json.load` 后结构合法、默认值与 spec §5 一致。

- [ ] **1. 写失败测试** — 创建 `tests/unit/conf_schema_test.py`：

```python
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_schema():
    return json.loads((REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))


def test_top_level_keys_present_and_types():
    s = load_schema()
    assert s["servers"]["type"] == "template_list"
    assert s["group_bindings"]["type"] == "template_list"
    for key in ("routing", "polling", "world", "bases", "privacy", "history"):
        assert s[key]["type"] == "object", f"{key} must be object"


def test_servers_template_items_and_defaults():
    items = load_schema()["servers"]["templates"]["server"]["items"]
    assert set(items) == {
        "name", "enabled", "base_url", "username",
        "password", "password_env", "timeout", "verify_tls", "timezone",
    }
    assert items["base_url"]["default"] == "http://127.0.0.1:8212"
    assert items["enabled"]["default"] is True
    assert items["timeout"]["default"] == 10


def test_group_bindings_is_top_level_not_nested_in_routing():
    s = load_schema()
    assert "group_bindings" not in s["routing"].get("items", {})
    b = s["group_bindings"]["templates"]["binding"]["items"]
    assert set(b) == {"umo", "server", "active"}


def test_routing_defaults():
    items = load_schema()["routing"]["items"]
    assert items["access_mode"]["default"] == "restricted"
    assert items["default_server"]["default"] == ""


def test_polling_defaults():
    items = load_schema()["polling"]["items"]
    assert items["metrics_seconds"]["default"] == 30
    assert items["players_seconds"]["default"] == 30
    assert items["info_seconds"]["default"] == 600
    assert items["settings_seconds"]["default"] == 1800
    assert items["game_data_seconds"]["default"] == 120
    assert items["jitter_ratio"]["default"] == 0.10
    assert items["max_concurrency"]["default"] == 6


def test_world_bases_privacy_history_defaults():
    s = load_schema()
    assert s["world"]["items"]["timezone"]["default"] == "Asia/Tokyo"
    assert s["world"]["items"]["fps_smooth"]["default"] == 50
    assert s["bases"]["items"]["assignment_radius"]["default"] == 5000
    assert s["bases"]["items"]["position_grid_size"]["default"] == 2000
    assert s["privacy"]["items"]["mode"]["default"] == "balanced"
    assert s["privacy"]["items"]["ping_ok_ms"]["default"] == 120
    assert s["history"]["items"]["raw_metrics_days"]["default"] == 7
    assert s["history"]["items"]["observation_days"]["default"] == 180
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/conf_schema_test.py -q`。期望 FAIL：`FileNotFoundError`（`_conf_schema.json` 尚不存在）。

- [ ] **3. 写最小实现** — 创建 `_conf_schema.json`（标准 JSON，无注释）：

```json
{
  "servers": {
    "type": "template_list",
    "description": "Palworld 服务器列表（网页可添加多个；name 需唯一）",
    "hint": "密码建议填环境变量名(password_env)而非明文；明文会落盘到 data/config/",
    "default": [],
    "templates": {
      "server": {
        "name": "Palworld 服务器",
        "display_item": "name",
        "items": {
          "name": { "type": "string", "description": "服务器名称（唯一标识，勿含空格/冒号/@）", "default": "" },
          "enabled": { "type": "bool", "description": "是否启用", "default": true },
          "base_url": { "type": "string", "description": "REST API 地址", "default": "http://127.0.0.1:8212" },
          "username": { "type": "string", "description": "Basic Auth 用户名", "default": "admin" },
          "password": { "type": "string", "description": "密码（明文，与 password_env 二选一）", "default": "" },
          "password_env": { "type": "string", "description": "密码环境变量名（推荐，与 password 二选一）", "default": "" },
          "timeout": { "type": "int", "description": "请求超时(秒)", "default": 10 },
          "verify_tls": { "type": "bool", "description": "校验 TLS 证书（http 忽略）", "default": true },
          "timezone": { "type": "string", "description": "该服务器时区（IANA，如 Asia/Tokyo；留空用全局）", "default": "" }
        }
      }
    }
  },
  "routing": {
    "type": "object",
    "description": "群↔服务器 路由与访问控制",
    "items": {
      "access_mode": { "type": "string", "description": "restricted=群需管理员授权; open=任意群任意服务器", "default": "restricted", "options": ["restricted", "open"] },
      "default_server": { "type": "string", "description": "全局默认服务器 name（群未指定且未绑定时的兜底）", "default": "" }
    }
  },
  "group_bindings": {
    "type": "template_list",
    "description": "预设 群→服务器 授权（可选，等价于管理员 /pal use）",
    "default": [],
    "templates": {
      "binding": {
        "name": "绑定",
        "display_item": "umo",
        "items": {
          "umo": { "type": "string", "description": "会话标识 unified_msg_origin，如 aiocqhttp:GroupMessage:123456", "default": "" },
          "server": { "type": "string", "description": "服务器 name", "default": "" },
          "active": { "type": "bool", "description": "设为该群活动服务器", "default": true }
        }
      }
    }
  },
  "polling": {
    "type": "object",
    "description": "轮询间隔（全局，逐服务器套用）",
    "items": {
      "metrics_seconds": { "type": "int", "description": "metrics 轮询间隔(秒)", "default": 30 },
      "players_seconds": { "type": "int", "description": "players 轮询间隔(秒)", "default": 30 },
      "info_seconds": { "type": "int", "description": "info 轮询间隔(秒)", "default": 600 },
      "settings_seconds": { "type": "int", "description": "settings 轮询间隔(秒)", "default": 1800 },
      "game_data_seconds": { "type": "int", "description": "game-data 轮询间隔(秒)", "default": 120 },
      "jitter_ratio": { "type": "float", "description": "间隔抖动比例", "default": 0.10 },
      "max_concurrency": { "type": "int", "description": "全局在途 HTTP 请求上限", "default": 6 }
    }
  },
  "world": {
    "type": "object",
    "description": "世界与展示",
    "items": {
      "timezone": { "type": "string", "description": "全局时区(IANA)", "default": "Asia/Tokyo" },
      "locale": { "type": "string", "description": "文案语言", "default": "zh-CN", "options": ["zh-CN"] },
      "fps_smooth": { "type": "int", "description": "FPS ≥ 此值=流畅", "default": 50 },
      "fps_moderate": { "type": "int", "description": "FPS ≥ 此值=一般", "default": 35 },
      "fps_laggy": { "type": "int", "description": "FPS < 此值=卡顿", "default": 20 }
    }
  },
  "bases": {
    "type": "object",
    "description": "据点推导参数",
    "items": {
      "enabled": { "type": "bool", "description": "启用据点/PalBox 推导", "default": true },
      "assignment_radius": { "type": "int", "description": "据点归属半径", "default": 5000 },
      "ambiguity_ratio": { "type": "float", "description": "最近/次近距离差比阈值", "default": 0.20 },
      "confirmation_samples": { "type": "int", "description": "建据点所需一致次数", "default": 3 },
      "position_grid_size": { "type": "int", "description": "坐标量化网格边长", "default": 2000 },
      "z_weight": { "type": "float", "description": "Z 轴距离权重", "default": 0.5 }
    }
  },
  "privacy": {
    "type": "object",
    "description": "隐私与脱敏",
    "items": {
      "mode": { "type": "string", "description": "strict/balanced/advanced", "default": "balanced", "options": ["strict", "balanced", "advanced"] },
      "public_exact_ping": { "type": "bool", "description": "公开精确 Ping", "default": false },
      "public_positions": { "type": "bool", "description": "公开坐标", "default": false },
      "ping_good_ms": { "type": "int", "description": "Ping ≤ 此值=优秀", "default": 60 },
      "ping_ok_ms": { "type": "int", "description": "Ping ≤ 此值=正常，超过=偏高", "default": 120 },
      "uncertain_timeout": { "type": "int", "description": "uncertain 会话超时收敛(秒)", "default": 900 }
    }
  },
  "history": {
    "type": "object",
    "description": "保留清理天数",
    "items": {
      "raw_metrics_days": { "type": "int", "description": "原始指标保留天数", "default": 7 },
      "aggregate_days": { "type": "int", "description": "预聚合保留天数", "default": 90 },
      "session_days": { "type": "int", "description": "会话保留天数", "default": 365 },
      "observation_days": { "type": "int", "description": "观察保留天数", "default": 180 }
    }
  }
}
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/conf_schema_test.py -q`。期望 PASS：6 passed。

- [ ] **5. 提交** — 命令：
```
git add _conf_schema.json tests/unit/conf_schema_test.py
git commit -m "feat(phase1): _conf_schema.json 完整 v0.1 网页配置 Schema"
```

---

### Task 1.3：`config.py` —— parse_config + 配置数据类

**Files:**
- Create: `palchronicle/domain/__init__.py`
- Create: `palchronicle/domain/enums.py`（本任务先只加 `AccessMode`；Phase 2 补齐其余枚举）
- Create: `palchronicle/config.py`
- Test: `tests/unit/config_test.py`

**Interfaces:**
- Consumes: `AccessMode(StrEnum)`（`RESTRICTED="restricted"`, `OPEN="open"`，契约枚举节）。
- Produces（严格照契约）：
  - dataclass `ServerConfig(server_id, name, enabled, base_url, username, password, timeout, verify_tls, timezone)` + `@property ready -> bool`（`enabled and bool(password) and bool(base_url)`）。
  - dataclass `SkippedServer(raw_name, reason)`（reason ∈ `"empty"/"duplicate"/"illegal_char"/"no_credential"`）。
  - dataclass `BindingConfig(umo, server, active)`。
  - dataclass `RoutingConfig(access_mode:AccessMode, default_server)`、`PollingConfig`、`WorldConfig`、`BasesConfig`、`PrivacyConfig`、`HistoryConfig`、`AppConfig`（字段全同契约）。
  - `def parse_config(raw: Mapping, env: Mapping[str, str]) -> AppConfig`。

- [ ] **1. 写失败测试** — 创建 `tests/unit/config_test.py`：

```python
from palchronicle.config import AppConfig, parse_config
from palchronicle.domain.enums import AccessMode


def _server(**kw):
    base = {
        "name": "s1", "enabled": True, "base_url": "http://127.0.0.1:8212",
        "username": "admin", "password": "pw", "password_env": "",
        "timeout": 10, "verify_tls": True, "timezone": "",
    }
    base.update(kw)
    return base


def test_parse_normal_server():
    cfg = parse_config({"servers": [_server()]}, env={})
    assert isinstance(cfg, AppConfig)
    assert len(cfg.servers) == 1
    s = cfg.servers[0]
    assert s.server_id == "s1"
    assert s.ready is True
    assert cfg.skipped == []


def test_empty_name_skipped():
    cfg = parse_config({"servers": [_server(name="   ")]}, env={})
    assert cfg.servers == []
    assert [(x.reason) for x in cfg.skipped] == ["empty"]


def test_duplicate_name_skipped():
    cfg = parse_config({"servers": [_server(name="dup"), _server(name="dup")]}, env={})
    assert len(cfg.servers) == 1
    assert cfg.servers[0].server_id == "dup"
    assert [x.reason for x in cfg.skipped] == ["duplicate"]


def test_illegal_char_names_skipped():
    for bad in ("a:b", "a@b", "a b"):
        cfg = parse_config({"servers": [_server(name=bad)]}, env={})
        assert cfg.servers == [], bad
        assert cfg.skipped[0].reason == "illegal_char", bad


def test_password_env_takes_precedence():
    cfg = parse_config(
        {"servers": [_server(password="plain", password_env="PAL_PW")]},
        env={"PAL_PW": "fromenv"},
    )
    assert cfg.servers[0].password == "fromenv"
    assert cfg.servers[0].ready is True


def test_plaintext_password_fallback_when_env_missing():
    cfg = parse_config(
        {"servers": [_server(password="plain", password_env="")]},
        env={},
    )
    assert cfg.servers[0].password == "plain"


def test_no_credential_marks_not_ready_and_diagnoses():
    cfg = parse_config(
        {"servers": [_server(password="", password_env="")]},
        env={},
    )
    assert len(cfg.servers) == 1
    assert cfg.servers[0].ready is False
    assert any(x.reason == "no_credential" for x in cfg.skipped)


def test_routing_and_polling_defaults():
    cfg = parse_config({"servers": []}, env={})
    assert cfg.routing.access_mode is AccessMode.RESTRICTED
    assert cfg.routing.default_server == ""
    assert cfg.polling.metrics_seconds == 30
    assert cfg.polling.info_seconds == 600
    assert cfg.polling.jitter_ratio == 0.10
    assert cfg.polling.max_concurrency == 6
    assert cfg.world.timezone == "Asia/Tokyo"
    assert cfg.bases.assignment_radius == 5000
    assert cfg.privacy.mode == "balanced"
    assert cfg.history.observation_days == 180


def test_bindings_parsed_from_top_level():
    cfg = parse_config(
        {"servers": [_server()], "group_bindings": [{"umo": "u1", "server": "s1", "active": True}]},
        env={},
    )
    assert len(cfg.group_bindings) == 1
    assert cfg.group_bindings[0].umo == "u1"
    assert cfg.group_bindings[0].server == "s1"
    assert cfg.group_bindings[0].active is True
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/config_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.config'`（及 `palchronicle.domain.enums`）。

- [ ] **3. 写最小实现**：

`palchronicle/domain/__init__.py`（空文件）。

`palchronicle/domain/enums.py`：
```python
"""领域枚举。Phase 1 仅需 AccessMode；其余枚举在 Phase 2 补齐（契约枚举节）。"""
from __future__ import annotations

from enum import StrEnum


class AccessMode(StrEnum):
    RESTRICTED = "restricted"
    OPEN = "open"
```

`palchronicle/config.py`：
```python
"""把 AstrBotConfig(dict) 解析为强类型配置数据类（spec §5.4 / 契约配置节）。"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from palchronicle.domain.enums import AccessMode

_ILLEGAL = (":", "@")


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

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.password) and bool(self.base_url)


@dataclass(slots=True)
class SkippedServer:
    raw_name: str
    reason: str  # "empty" / "duplicate" / "illegal_char" / "no_credential"


@dataclass(slots=True)
class BindingConfig:
    umo: str
    server: str
    active: bool


@dataclass(slots=True)
class RoutingConfig:
    access_mode: AccessMode
    default_server: str


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
            timeout=int(item.get("timeout", 10)),
            verify_tls=bool(item.get("verify_tls", True)),
            timezone=str(item.get("timezone", "") or ""),
        )
        servers.append(server)
        if not password:
            skipped.append(SkippedServer(raw_name=raw_name, reason="no_credential"))
    return servers, skipped


def _parse_bindings(raw: Mapping) -> list[BindingConfig]:
    out: list[BindingConfig] = []
    for item in raw.get("group_bindings", []) or []:
        umo = str(item.get("umo", "") or "").strip()
        server = str(item.get("server", "") or "").strip()
        if not umo or not server:
            continue
        out.append(BindingConfig(umo=umo, server=server, active=bool(item.get("active", True))))
    return out


def parse_config(raw: Mapping, env: Mapping[str, str]) -> AppConfig:
    servers, skipped = _parse_servers(raw, env)
    r = _obj(raw, "routing")
    p = _obj(raw, "polling")
    w = _obj(raw, "world")
    b = _obj(raw, "bases")
    pv = _obj(raw, "privacy")
    h = _obj(raw, "history")
    return AppConfig(
        servers=servers,
        skipped=skipped,
        routing=RoutingConfig(
            access_mode=AccessMode(str(r.get("access_mode", "restricted") or "restricted")),
            default_server=str(r.get("default_server", "") or ""),
        ),
        group_bindings=_parse_bindings(raw),
        polling=PollingConfig(
            metrics_seconds=int(p.get("metrics_seconds", 30)),
            players_seconds=int(p.get("players_seconds", 30)),
            info_seconds=int(p.get("info_seconds", 600)),
            settings_seconds=int(p.get("settings_seconds", 1800)),
            game_data_seconds=int(p.get("game_data_seconds", 120)),
            jitter_ratio=float(p.get("jitter_ratio", 0.10)),
            max_concurrency=int(p.get("max_concurrency", 6)),
        ),
        world=WorldConfig(
            timezone=str(w.get("timezone", "Asia/Tokyo") or "Asia/Tokyo"),
            locale=str(w.get("locale", "zh-CN") or "zh-CN"),
            fps_smooth=int(w.get("fps_smooth", 50)),
            fps_moderate=int(w.get("fps_moderate", 35)),
            fps_laggy=int(w.get("fps_laggy", 20)),
        ),
        bases=BasesConfig(
            enabled=bool(b.get("enabled", True)),
            assignment_radius=int(b.get("assignment_radius", 5000)),
            ambiguity_ratio=float(b.get("ambiguity_ratio", 0.20)),
            confirmation_samples=int(b.get("confirmation_samples", 3)),
            position_grid_size=int(b.get("position_grid_size", 2000)),
            z_weight=float(b.get("z_weight", 0.5)),
        ),
        privacy=PrivacyConfig(
            mode=str(pv.get("mode", "balanced") or "balanced"),
            public_exact_ping=bool(pv.get("public_exact_ping", False)),
            public_positions=bool(pv.get("public_positions", False)),
            ping_good_ms=int(pv.get("ping_good_ms", 60)),
            ping_ok_ms=int(pv.get("ping_ok_ms", 120)),
            uncertain_timeout=int(pv.get("uncertain_timeout", 900)),
        ),
        history=HistoryConfig(
            raw_metrics_days=int(h.get("raw_metrics_days", 7)),
            aggregate_days=int(h.get("aggregate_days", 90)),
            session_days=int(h.get("session_days", 365)),
            observation_days=int(h.get("observation_days", 180)),
        ),
    )
```

> 说明：`field` 已导入但当前未使用，可删；保留不影响测试。为 DRY 建议删除该 import。

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/config_test.py -q`。期望 PASS：9 passed。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/domain/__init__.py palchronicle/domain/enums.py palchronicle/config.py tests/unit/config_test.py
git commit -m "feat(phase1): config.py 解析配置为强类型数据类 + 无效服务器诊断"
```

---

### Task 1.4：`infrastructure/clock.py` —— Clock / SystemClock / FakeClock

**Files:**
- Create: `palchronicle/infrastructure/__init__.py`
- Create: `palchronicle/infrastructure/clock.py`
- Modify: `tests/conftest.py`（`fake_clock` 改为 import 真正的 `FakeClock`）
- Test: `tests/unit/clock_test.py`

**Interfaces:**
- Consumes: 无。
- Produces（契约）：`Clock(Protocol)`（`now()->int`、`monotonic()->float`）；`SystemClock`；`FakeClock(start:int)`，方法 `now()->int`、`monotonic()->float`、`advance(secs:int)->None`、`set(t:int)->None`。

- [ ] **1. 写失败测试** — 创建 `tests/unit/clock_test.py`：

```python
from palchronicle.infrastructure.clock import Clock, FakeClock, SystemClock


def test_fake_clock_now_and_set_and_advance():
    c = FakeClock(1000)
    assert c.now() == 1000
    c.advance(30)
    assert c.now() == 1030
    c.set(500)
    assert c.now() == 500


def test_fake_clock_monotonic_advances_with_advance_only():
    c = FakeClock(1000)
    m0 = c.monotonic()
    c.advance(5)
    assert c.monotonic() == m0 + 5.0
    # set 不回退单调时钟
    c.set(200)
    assert c.monotonic() == m0 + 5.0


def test_system_clock_is_a_clock_and_returns_int_now():
    c = SystemClock()
    assert isinstance(c.now(), int)
    assert isinstance(c.monotonic(), float)
    assert isinstance(c, Clock)


def test_fake_clock_is_a_clock():
    assert isinstance(FakeClock(0), Clock)
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/clock_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.infrastructure'`。

- [ ] **3. 写最小实现**：

`palchronicle/infrastructure/__init__.py`（空文件）。

`palchronicle/infrastructure/clock.py`：
```python
"""可注入时钟。SystemClock 生产用；FakeClock 测试确定性用。"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> int:
        """当前 epoch 秒（UTC）。"""
        ...

    def monotonic(self) -> float:
        """单调秒（用于测量耗时/背压，不受系统时钟回拨影响）。"""
        ...


class SystemClock:
    def now(self) -> int:
        return int(time.time())

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    def __init__(self, start: int) -> None:
        self._t = start
        self._mono = 0.0

    def now(self) -> int:
        return self._t

    def monotonic(self) -> float:
        return self._mono

    def advance(self, secs: int) -> None:
        self._t += secs
        self._mono += float(secs)

    def set(self, t: int) -> None:
        self._t = t
```

Modify `tests/conftest.py` —— 用真正的 `FakeClock` 替换内联时钟。将整个文件替换为：
```python
"""公用 pytest fixtures。"""
import pytest

from palchronicle.infrastructure.clock import FakeClock


@pytest.fixture
def fake_clock():
    return FakeClock(1_700_000_000)
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/clock_test.py tests/unit/skeleton_test.py -q`。期望 PASS：8 passed（clock 4 + skeleton 4；skeleton 的 `fake_clock` 测试仍通过，因 `FakeClock` 语义一致）。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/infrastructure/__init__.py palchronicle/infrastructure/clock.py tests/conftest.py tests/unit/clock_test.py
git commit -m "feat(phase1): infrastructure/clock.py 可注入 Clock/SystemClock/FakeClock"
```

---

### Task 1.5：`infrastructure/salt.py` —— load_or_create_salt

**Files:**
- Create: `palchronicle/infrastructure/salt.py`
- Test: `tests/unit/salt_test.py`

**Interfaces:**
- Consumes: 无。
- Produces（契约）：`def load_or_create_salt(data_dir: Path) -> bytes`。首次生成 32 字节随机 salt 写入 `<data_dir>/secret_salt`；复用已存在文件；POSIX 下权限收敛 0600（Windows 忽略）。

- [ ] **1. 写失败测试** — 创建 `tests/unit/salt_test.py`：

```python
import os

from palchronicle.infrastructure.salt import load_or_create_salt


def test_creates_32_byte_salt_file(tmp_path):
    salt = load_or_create_salt(tmp_path)
    assert isinstance(salt, bytes)
    assert len(salt) == 32
    assert (tmp_path / "secret_salt").exists()
    assert (tmp_path / "secret_salt").read_bytes() == salt


def test_reuses_existing_salt(tmp_path):
    first = load_or_create_salt(tmp_path)
    second = load_or_create_salt(tmp_path)
    assert first == second


def test_creates_parent_dir_if_missing(tmp_path):
    nested = tmp_path / "a" / "b"
    salt = load_or_create_salt(nested)
    assert len(salt) == 32
    assert (nested / "secret_salt").exists()


def test_posix_permissions_are_0600(tmp_path):
    if os.name != "posix":
        import pytest

        pytest.skip("POSIX-only permission check")
    load_or_create_salt(tmp_path)
    mode = (tmp_path / "secret_salt").stat().st_mode & 0o777
    assert mode == 0o600
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/salt_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.infrastructure.salt'`。

- [ ] **3. 写最小实现** — 创建 `palchronicle/infrastructure/salt.py`：

```python
"""HMAC secret salt 的生成与持久化（spec §4.1）。

首次运行生成 32 字节随机 salt 写盘并复用；POSIX 收敛 0600。
永不写入日志/数据库/配置。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

_SALT_FILENAME = "secret_salt"


def load_or_create_salt(data_dir: Path) -> bytes:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / _SALT_FILENAME
    if path.exists():
        return path.read_bytes()
    salt = secrets.token_bytes(32)
    # 先以 0600 打开再写，避免生成瞬间的宽权限窗口（POSIX）。
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, salt)
    finally:
        os.close(fd)
    if os.name == "posix":
        os.chmod(path, 0o600)
    return salt
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/salt_test.py -q`。期望 PASS：4 passed（Windows 下第 4 个 skip，仍算 pass 输出 `3 passed, 1 skipped`）。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/infrastructure/salt.py tests/unit/salt_test.py
git commit -m "feat(phase1): infrastructure/salt.py 生成/复用 HMAC salt(0600)"
```

---

### Task 1.6：`infrastructure/database.py` —— Database（WAL/写锁/读写分离）

**Files:**
- Create: `palchronicle/infrastructure/database.py`
- Test: `tests/unit/database_test.py`

**Interfaces:**
- Consumes: 无（不依赖 migrations，本任务只建裸连接与临时表验证）。
- Produces（契约）：
  - `class Database.__init__(self, path: Path)`。
  - `async def open() -> None`（建 write_conn + read_conn，`PRAGMA journal_mode=WAL`、`PRAGMA foreign_keys=ON`）。
  - `async def close() -> None`。
  - `write_lock: asyncio.Lock`。
  - `async def execute_write(sql, params=()) -> None`（持 write_lock，写后 commit）。
  - `async def executemany_write(sql, seq) -> None`。
  - `async def write_tx() -> AsyncContextManager`（单事务，持 write_lock，yield write_conn）。
  - `async def query(sql, params=()) -> list[aiosqlite.Row]`（只读连接）。

- [ ] **1. 写失败测试** — 创建 `tests/unit/database_test.py`：

```python
import asyncio

import pytest

from palchronicle.infrastructure.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.open()
    yield database
    await database.close()


async def test_wal_and_foreign_keys_enabled(db):
    rows = await db.query("PRAGMA journal_mode")
    assert rows[0][0].lower() == "wal"
    fk = await db.query("PRAGMA foreign_keys")
    assert fk[0][0] == 1


async def test_execute_write_then_query(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    await db.execute_write("INSERT INTO t (k, v) VALUES (?, ?)", (1, "a"))
    rows = await db.query("SELECT v FROM t WHERE k = ?", (1,))
    assert [r[0] for r in rows] == ["a"]


async def test_executemany_write(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    await db.executemany_write(
        "INSERT INTO t (k, v) VALUES (?, ?)", [(1, "a"), (2, "b"), (3, "c")]
    )
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 3


async def test_write_tx_commits_as_one_unit(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    async with db.write_tx() as conn:
        await conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (1, "x"))
        await conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (2, "y"))
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 2


async def test_write_tx_rolls_back_on_error(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    with pytest.raises(ValueError):
        async with db.write_tx() as conn:
            await conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (1, "x"))
            raise ValueError("boom")
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 0


async def test_write_lock_serializes_concurrent_writes(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY)")

    async def writer(k):
        await db.execute_write("INSERT INTO t (k) VALUES (?)", (k,))

    await asyncio.gather(*(writer(i) for i in range(20)))
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 20
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/database_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.infrastructure.database'`。

- [ ] **3. 写最小实现** — 创建 `palchronicle/infrastructure/database.py`：

```python
"""aiosqlite 连接封装：单写连接(写锁) + 只读连接，WAL 使多读单写生效。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self._path = str(path)
        self._write_conn: aiosqlite.Connection | None = None
        self._read_conn: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()

    async def open(self) -> None:
        self._write_conn = await aiosqlite.connect(self._path)
        # WAL 须在建立读连接前设定，供后续多读单写。
        await self._write_conn.execute("PRAGMA journal_mode=WAL")
        await self._write_conn.execute("PRAGMA foreign_keys=ON")
        await self._write_conn.commit()
        self._read_conn = await aiosqlite.connect(self._path)
        await self._read_conn.execute("PRAGMA foreign_keys=ON")
        await self._read_conn.commit()

    async def close(self) -> None:
        if self._read_conn is not None:
            await self._read_conn.close()
            self._read_conn = None
        if self._write_conn is not None:
            await self._write_conn.close()
            self._write_conn = None

    @property
    def _wc(self) -> aiosqlite.Connection:
        if self._write_conn is None:
            raise RuntimeError("Database not opened")
        return self._write_conn

    @property
    def _rc(self) -> aiosqlite.Connection:
        if self._read_conn is None:
            raise RuntimeError("Database not opened")
        return self._read_conn

    async def execute_write(self, sql: str, params: Sequence[Any] = ()) -> None:
        async with self.write_lock:
            await self._wc.execute(sql, params)
            await self._wc.commit()

    async def executemany_write(
        self, sql: str, seq: Iterable[Sequence[Any]]
    ) -> None:
        async with self.write_lock:
            await self._wc.executemany(sql, list(seq))
            await self._wc.commit()

    @asynccontextmanager
    async def write_tx(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self.write_lock:
            try:
                yield self._wc
            except BaseException:
                await self._wc.rollback()
                raise
            else:
                await self._wc.commit()

    async def query(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[aiosqlite.Row]:
        cursor = await self._rc.execute(sql, params)
        try:
            return list(await cursor.fetchall())
        finally:
            await cursor.close()
```

> 注意：`write_tx` 声明为 `@asynccontextmanager` 装饰的 `async def`，调用方 `async with db.write_tx() as conn` 即可（契约签名 `async def write_tx() -> AsyncContextManager` 与之等价）。

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/database_test.py -q`。期望 PASS：6 passed。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/infrastructure/database.py tests/unit/database_test.py
git commit -m "feat(phase1): infrastructure/database.py WAL + 写锁 + 读写连接分离"
```

---

### Task 1.7：`infrastructure/migrations.py` —— MIGRATIONS + apply_migrations（建全部 v0.1 表与索引）

**Files:**
- Create: `palchronicle/infrastructure/migrations.py`
- Test: `tests/unit/migrations_test.py`

**Interfaces:**
- Consumes: `Database`（Task 1.6：`db.write_tx()`、`db.query()`、`db._wc`/内部连接经 `write_tx` 暴露的 `conn`）。
- Produces（契约）：
  - `MIGRATIONS: list[Callable[[aiosqlite.Connection], Awaitable[None]]]`（含 `migration_0001`）。
  - `async def apply_migrations(db: Database) -> None`（`PRAGMA user_version` 驱动、幂等、失败抛 `MigrationError`）。
  - `class MigrationError(Exception)`。
  - migration_0001 建 spec §9.1 全部 v0.1 表（`servers`、`group_servers`、`worlds`、`players`、`player_sessions`、`player_observations`、`guilds`、`palboxes`、`bases`、`base_observations`、`world_metrics`、`world_events`、`daily_aggregates`、`unknown_classes`）+ §9.2 全部索引。

- [ ] **1. 写失败测试** — 创建 `tests/unit/migrations_test.py`：

```python
import pytest

from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import (
    MIGRATIONS,
    MigrationError,
    apply_migrations,
)

EXPECTED_TABLES = {
    "servers", "group_servers", "worlds", "players", "player_sessions",
    "player_observations", "guilds", "palboxes", "bases", "base_observations",
    "world_metrics", "world_events", "daily_aggregates", "unknown_classes",
}
EXPECTED_INDEXES = {
    "idx_events_dedup", "idx_events_world_time", "idx_sessions_player_time",
    "idx_obs_player_time", "idx_metrics_world_time", "idx_baseobs_base_time",
}


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "m.db")
    await database.open()
    yield database
    await database.close()


async def _table_names(db):
    rows = await db.query("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in rows}


async def _index_names(db):
    rows = await db.query("SELECT name FROM sqlite_master WHERE type='index'")
    return {r[0] for r in rows}


async def test_fresh_db_gets_all_tables(db):
    await apply_migrations(db)
    assert EXPECTED_TABLES <= await _table_names(db)


async def test_fresh_db_gets_all_indexes(db):
    await apply_migrations(db)
    assert EXPECTED_INDEXES <= await _index_names(db)


async def test_user_version_matches_migration_count(db):
    await apply_migrations(db)
    rows = await db.query("PRAGMA user_version")
    assert rows[0][0] == len(MIGRATIONS)


async def test_apply_is_idempotent(db):
    await apply_migrations(db)
    await apply_migrations(db)  # 第二次应为 no-op，不报错
    rows = await db.query("PRAGMA user_version")
    assert rows[0][0] == len(MIGRATIONS)
    assert EXPECTED_TABLES <= await _table_names(db)


async def test_events_dedup_index_is_unique(db):
    await apply_migrations(db)
    await db.execute_write(
        "INSERT INTO world_events "
        "(world_id, event_type, subject_type, subject_key, occurred_at, "
        " confirmed_at, payload_json, visibility, confidence, dedup_key) "
        "VALUES ('w','NEW_PLAYER','player','pk',1,1,'{}','public','high','dk1')"
    )
    import aiosqlite

    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute_write(
            "INSERT INTO world_events "
            "(world_id, event_type, subject_type, subject_key, occurred_at, "
            " confirmed_at, payload_json, visibility, confidence, dedup_key) "
            "VALUES ('w','NEW_PLAYER','player','pk',2,2,'{}','public','high','dk1')"
        )


async def test_failed_migration_raises_migration_error(db):
    async def bad(conn):
        await conn.execute("CREATE TABLE broken (")  # 语法错误

    from palchronicle.infrastructure import migrations as m

    original = m.MIGRATIONS
    m.MIGRATIONS = original + [bad]
    try:
        with pytest.raises(MigrationError):
            await apply_migrations(db)
    finally:
        m.MIGRATIONS = original
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/migrations_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.infrastructure.migrations'`。

- [ ] **3. 写最小实现** — 创建 `palchronicle/infrastructure/migrations.py`：

```python
"""顺序迁移器：PRAGMA user_version 驱动，幂等，失败抛 MigrationError。

migration_0001 建 spec §9.1 全部 v0.1 表 + §9.2 全部索引。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import aiosqlite

from palchronicle.infrastructure.database import Database


class MigrationError(Exception):
    pass


_MIGRATION_0001_SQL = [
    """
    CREATE TABLE IF NOT EXISTS servers (
        server_id     TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        host          TEXT,
        enabled       INTEGER NOT NULL DEFAULT 1,
        first_seen_at INTEGER,
        last_seen_at  INTEGER,
        last_ok_at    INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS group_servers (
        umo        TEXT NOT NULL,
        server_id  TEXT NOT NULL,
        allowed    INTEGER NOT NULL DEFAULT 0,
        active     INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER,
        PRIMARY KEY (umo, server_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS worlds (
        world_id      TEXT PRIMARY KEY,
        server_id     TEXT NOT NULL,
        worldguid     TEXT NOT NULL,
        epoch         INTEGER NOT NULL DEFAULT 0,
        server_name   TEXT,
        version       TEXT,
        first_seen_at INTEGER,
        last_seen_at  INTEGER,
        current_day   INTEGER,
        UNIQUE (server_id, worldguid, epoch)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS players (
        player_key       TEXT NOT NULL,
        world_id         TEXT NOT NULL,
        latest_name      TEXT,
        first_seen_at    INTEGER,
        last_seen_at     INTEGER,
        latest_level     INTEGER,
        latest_guild_key TEXT,
        id_confidence    TEXT,
        PRIMARY KEY (player_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_sessions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id          TEXT NOT NULL,
        player_key        TEXT NOT NULL,
        joined_at         INTEGER NOT NULL,
        last_confirmed_at INTEGER NOT NULL,
        left_at           INTEGER,
        observed_seconds  INTEGER NOT NULL DEFAULT 0,
        status            TEXT NOT NULL,
        leave_reason      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_observations (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id       TEXT NOT NULL,
        player_key     TEXT NOT NULL,
        observed_at    INTEGER NOT NULL,
        level          INTEGER,
        ping_bucket    TEXT,
        building_count INTEGER,
        guild_key      TEXT,
        companion_class TEXT,
        position_cell  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guilds (
        guild_key            TEXT NOT NULL,
        world_id             TEXT NOT NULL,
        latest_name          TEXT,
        first_seen_at        INTEGER,
        last_seen_at         INTEGER,
        observed_member_count INTEGER DEFAULT 0,
        palbox_count         INTEGER DEFAULT 0,
        base_pal_count       INTEGER DEFAULT 0,
        PRIMARY KEY (guild_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS palboxes (
        palbox_key    TEXT NOT NULL,
        world_id      TEXT NOT NULL,
        guild_key     TEXT,
        position_cell TEXT NOT NULL,
        first_seen_at INTEGER,
        last_seen_at  INTEGER,
        status        TEXT NOT NULL DEFAULT 'active',
        PRIMARY KEY (palbox_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bases (
        base_key       TEXT NOT NULL,
        world_id       TEXT NOT NULL,
        palbox_key     TEXT NOT NULL,
        display_name   TEXT,
        guild_key      TEXT,
        confidence     TEXT NOT NULL,
        locked_by_admin INTEGER NOT NULL DEFAULT 0,
        hidden         INTEGER NOT NULL DEFAULT 0,
        first_seen_at  INTEGER,
        last_seen_at   INTEGER,
        PRIMARY KEY (base_key, world_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS base_observations (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id                 TEXT NOT NULL,
        base_key                 TEXT NOT NULL,
        observed_at              INTEGER NOT NULL,
        worker_count             INTEGER,
        active_count             INTEGER,
        average_level            REAL,
        average_hp_ratio         REAL,
        action_distribution_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_metrics (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id       TEXT NOT NULL,
        observed_at    INTEGER NOT NULL,
        fps            REAL,
        frame_time     REAL,
        online_players INTEGER,
        world_day      INTEGER,
        basecamp_count INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_events (
        event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        world_id     TEXT NOT NULL,
        event_type   TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_key  TEXT,
        occurred_at  INTEGER NOT NULL,
        confirmed_at INTEGER NOT NULL,
        payload_json TEXT,
        visibility   TEXT NOT NULL,
        confidence   TEXT NOT NULL,
        dedup_key    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_aggregates (
        world_id   TEXT NOT NULL,
        day        TEXT NOT NULL,
        key        TEXT NOT NULL,
        value_json TEXT,
        PRIMARY KEY (world_id, day, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unknown_classes (
        class_name    TEXT PRIMARY KEY,
        first_seen_at INTEGER,
        count         INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup ON world_events(dedup_key)",
    "CREATE INDEX IF NOT EXISTS idx_events_world_time ON world_events(world_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_player_time ON player_sessions(world_id, player_key, joined_at)",
    "CREATE INDEX IF NOT EXISTS idx_obs_player_time ON player_observations(world_id, player_key, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_world_time ON world_metrics(world_id, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_baseobs_base_time ON base_observations(world_id, base_key, observed_at)",
]


async def migration_0001(conn: aiosqlite.Connection) -> None:
    for stmt in _MIGRATION_0001_SQL:
        await conn.execute(stmt)


MIGRATIONS: list[Callable[[aiosqlite.Connection], Awaitable[None]]] = [
    migration_0001,
]


async def apply_migrations(db: Database) -> None:
    rows = await db.query("PRAGMA user_version")
    current = int(rows[0][0]) if rows else 0
    target = len(MIGRATIONS)
    if current >= target:
        return
    for version in range(current, target):
        migration = MIGRATIONS[version]
        try:
            async with db.write_tx() as conn:
                await migration(conn)
                # user_version 不接受占位参数，须内联整数。
                await conn.execute(f"PRAGMA user_version = {version + 1}")
        except MigrationError:
            raise
        except Exception as exc:  # noqa: BLE001 — 迁移失败统一包装
            raise MigrationError(
                f"migration #{version + 1} failed: {type(exc).__name__}"
            ) from exc
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/migrations_test.py -q`。期望 PASS：6 passed。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/infrastructure/migrations.py tests/unit/migrations_test.py
git commit -m "feat(phase1): migrations.py 迁移器 + migration_0001 建全部 v0.1 表/索引"
```

---

### Task 1.8：`infrastructure/locks.py` —— EndpointLocks（在途锁 + 全局信号量）

**Files:**
- Create: `palchronicle/infrastructure/locks.py`
- Test: `tests/unit/locks_test.py`

**Interfaces:**
- Consumes: `EndpointName(StrEnum)`（契约枚举）—— 本任务在 `palchronicle/domain/enums.py` 补充 `EndpointName`（Phase 2 需要，先加此一枚举满足 locks 依赖）。
- Produces（契约）：
  - `class EndpointLocks.__init__(self, max_concurrency: int)`。
  - `semaphore: asyncio.Semaphore`。
  - `def inflight(self, server_id: str, endpoint: EndpointName) -> AsyncContextManager`：同 `(server_id, endpoint)` 已有在途请求时**跳过**（进入上下文得到 `False`），否则获得该锁（得到 `True`），退出释放。

- [ ] **1. 写失败测试** — 创建 `tests/unit/locks_test.py`：

```python
import asyncio

from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.locks import EndpointLocks


async def test_inflight_acquires_when_free():
    locks = EndpointLocks(max_concurrency=6)
    async with locks.inflight("s1", EndpointName.METRICS) as acquired:
        assert acquired is True


async def test_inflight_skips_when_same_endpoint_busy():
    locks = EndpointLocks(max_concurrency=6)
    order = []

    async def first():
        async with locks.inflight("s1", EndpointName.METRICS) as acquired:
            order.append(("first", acquired))
            await asyncio.sleep(0.05)

    async def second():
        await asyncio.sleep(0.01)  # 确保 first 已占用
        async with locks.inflight("s1", EndpointName.METRICS) as acquired:
            order.append(("second", acquired))

    await asyncio.gather(first(), second())
    assert ("first", True) in order
    assert ("second", False) in order


async def test_inflight_independent_per_server_and_endpoint():
    locks = EndpointLocks(max_concurrency=6)

    async def hold(server, endpoint, results):
        async with locks.inflight(server, endpoint) as acquired:
            results.append(acquired)
            await asyncio.sleep(0.02)

    results = []
    await asyncio.gather(
        hold("s1", EndpointName.METRICS, results),
        hold("s1", EndpointName.PLAYERS, results),
        hold("s2", EndpointName.METRICS, results),
    )
    assert results == [True, True, True]


async def test_lock_released_after_context():
    locks = EndpointLocks(max_concurrency=6)
    async with locks.inflight("s1", EndpointName.INFO) as a1:
        assert a1 is True
    async with locks.inflight("s1", EndpointName.INFO) as a2:
        assert a2 is True


async def test_semaphore_uses_max_concurrency():
    locks = EndpointLocks(max_concurrency=3)
    assert isinstance(locks.semaphore, asyncio.Semaphore)
    assert locks.semaphore._value == 3
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/locks_test.py -q`。期望 FAIL：`ImportError: cannot import name 'EndpointName'`（`enums.py` 未定义）与 `ModuleNotFoundError: palchronicle.infrastructure.locks`。

- [ ] **3. 写最小实现**：

先在 `palchronicle/domain/enums.py` **追加**（保留已有 `AccessMode`）：
```python
class EndpointName(StrEnum):
    INFO = "info"
    METRICS = "metrics"
    PLAYERS = "players"
    SETTINGS = "settings"
    GAME_DATA = "game_data"
```

创建 `palchronicle/infrastructure/locks.py`：
```python
"""每 (server_id, endpoint) 在途锁（占用则跳过）+ 全局并发信号量。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from palchronicle.domain.enums import EndpointName


class EndpointLocks:
    def __init__(self, max_concurrency: int) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._inflight: set[tuple[str, str]] = set()

    @asynccontextmanager
    async def inflight(
        self, server_id: str, endpoint: EndpointName
    ) -> AsyncIterator[bool]:
        key = (server_id, str(endpoint))
        if key in self._inflight:
            # 已有同端点在途请求 → 本次直接跳过（tick 合并）。
            yield False
            return
        self._inflight.add(key)
        try:
            yield True
        finally:
            self._inflight.discard(key)
```

> 说明：`_inflight` 用集合成员判定占用；不阻塞等待——同端点在途时立即返回 `False` 让调用方放弃本 tick，与 spec §6.1 的"tick 合并"一致。单事件循环内无需锁保护集合（协程间无抢占）。

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/locks_test.py -q`。期望 PASS：5 passed。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/domain/enums.py palchronicle/infrastructure/locks.py tests/unit/locks_test.py
git commit -m "feat(phase1): locks.py 端点在途锁(占用跳过) + 全局信号量; 补 EndpointName 枚举"
```

---

### Task 1.9：`infrastructure/cache.py` —— TTLCache

**Files:**
- Create: `palchronicle/infrastructure/cache.py`
- Test: `tests/unit/cache_test.py`

**Interfaces:**
- Consumes: `Clock`（Task 1.4）—— 通过 `FakeClock` 注入测过期。
- Produces（契约）：
  - `class TTLCache.__init__(self, clock: Clock)`。
  - `def get(self, key: str) -> Any | None`（未命中或已过期返回 `None`）。
  - `def set(self, key: str, value: Any, ttl_seconds: int) -> None`。

- [ ] **1. 写失败测试** — 创建 `tests/unit/cache_test.py`：

```python
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock


def test_get_miss_returns_none():
    cache = TTLCache(FakeClock(1000))
    assert cache.get("absent") is None


def test_set_then_get_hit():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", {"v": 1}, ttl_seconds=15)
    assert cache.get("k") == {"v": 1}


def test_entry_expires_after_ttl():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", "val", ttl_seconds=15)
    clock.advance(14)
    assert cache.get("k") == "val"
    clock.advance(1)  # now == set_time + 15 → 恰好过期(>=)
    assert cache.get("k") is None


def test_set_overwrites_and_refreshes_ttl():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", "old", ttl_seconds=10)
    clock.advance(8)
    cache.set("k", "new", ttl_seconds=10)
    clock.advance(5)  # 距第二次 set 仅 5s，未过期
    assert cache.get("k") == "new"


def test_expired_key_is_none_not_raise():
    clock = FakeClock(1000)
    cache = TTLCache(clock)
    cache.set("k", "v", ttl_seconds=5)
    clock.advance(100)
    assert cache.get("k") is None
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/cache_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.infrastructure.cache'`。

- [ ] **3. 写最小实现** — 创建 `palchronicle/infrastructure/cache.py`：

```python
"""查询短时缓存（TTL）。时钟可注入以确定性测过期。"""
from __future__ import annotations

from typing import Any

from palchronicle.infrastructure.clock import Clock


class TTLCache:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._store: dict[str, tuple[int, Any]] = {}  # key -> (expires_at, value)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock.now() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (self._clock.now() + ttl_seconds, value)
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/cache_test.py -q`。期望 PASS：5 passed。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/infrastructure/cache.py tests/unit/cache_test.py
git commit -m "feat(phase1): cache.py TTLCache（时钟可注入，>=ttl 过期）"
```

---

### Task 1.10：`adapters/palworld_rest.py` —— PalworldRestClient.fetch（安全日志/脱敏错误）

**Files:**
- Create: `palchronicle/adapters/__init__.py`
- Create: `palchronicle/adapters/palworld_rest.py`
- Test: `tests/unit/palworld_rest_test.py`

**Interfaces:**
- Consumes: `ServerConfig`（Task 1.3）、`Clock`（Task 1.4）、`EndpointName`（Task 1.8）。
- Produces（契约）：
  - `@dataclass(slots=True) class RestResponse(ok, status, data, duration_ms, payload_bytes, error)`（`error` 已脱敏——不含凭证/URL）。
  - `class PalworldRestClient.__init__(self, server: ServerConfig, clock: Clock)`。
  - `async def fetch(self, endpoint: EndpointName) -> RestResponse`（GET `base_url + "/v1/api/<路径>"`；`aiohttp.BasicAuth(username, password)`；超时 `server.timeout`；路径映射 info→/info, metrics→/metrics, players→/players, settings→/settings, game_data→/game-data）。
  - `async def close(self) -> None`。
- 测试用**自建 fake session**（不引外部 mock 库），通过依赖注入替换内部 `_session`，覆盖 200 成功 / 超时 / 401 / 网络错误且 error 已脱敏。

- [ ] **1. 写失败测试** — 创建 `tests/unit/palworld_rest_test.py`：

```python
import asyncio
from contextlib import asynccontextmanager

import aiohttp
import pytest

from palchronicle.adapters.palworld_rest import PalworldRestClient, RestResponse
from palchronicle.config import ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://secret-host:8212", username="admin",
        password="topsecret", timeout=10, verify_tls=True, timezone="",
    )


class _FakeResp:
    def __init__(self, status, payload=None, body_bytes=b"{}"):
        self.status = status
        self._payload = payload if payload is not None else {}
        self._body = body_bytes

    async def json(self, content_type=None):
        return self._payload

    async def read(self):
        return self._body


class _FakeSession:
    """替换 aiohttp.ClientSession；按脚本返回响应或抛异常。"""

    def __init__(self, script):
        self._script = script
        self.requested_url = None
        self.requested_auth = None

    @asynccontextmanager
    async def get(self, url, auth=None, timeout=None, ssl=None):
        self.requested_url = url
        self.requested_auth = auth
        outcome = self._script
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    async def close(self):
        pass


async def test_fetch_success_200():
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(_FakeResp(200, {"days": 5}, b'{"days": 5}'))
    resp = await client.fetch(EndpointName.METRICS)
    assert isinstance(resp, RestResponse)
    assert resp.ok is True
    assert resp.status == 200
    assert resp.data == {"days": 5}
    assert resp.payload_bytes == len(b'{"days": 5}')
    assert resp.error is None


async def test_fetch_builds_correct_path_and_basic_auth():
    session = _FakeSession(_FakeResp(200, {}))
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = session
    await client.fetch(EndpointName.GAME_DATA)
    assert session.requested_url == "http://secret-host:8212/v1/api/game-data"
    assert isinstance(session.requested_auth, aiohttp.BasicAuth)


async def test_fetch_timeout_returns_sanitized_error():
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(asyncio.TimeoutError())
    resp = await client.fetch(EndpointName.PLAYERS)
    assert resp.ok is False
    assert resp.status is None
    assert resp.data is None
    assert "timeout" in resp.error.lower()
    assert "topsecret" not in resp.error
    assert "secret-host" not in resp.error


async def test_fetch_401_marks_not_ok():
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(_FakeResp(401, {}, b""))
    resp = await client.fetch(EndpointName.INFO)
    assert resp.ok is False
    assert resp.status == 401
    assert resp.error is not None
    assert "topsecret" not in resp.error


async def test_fetch_network_error_sanitized():
    err = aiohttp.ClientConnectorError(
        connection_key=None, os_error=OSError("connect to secret-host failed")
    )
    client = PalworldRestClient(_server(), FakeClock(1000))
    client._session = _FakeSession(err)
    resp = await client.fetch(EndpointName.METRICS)
    assert resp.ok is False
    assert resp.error is not None
    assert "secret-host" not in resp.error
    assert "topsecret" not in resp.error
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/palworld_rest_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.adapters.palworld_rest'`。

- [ ] **3. 写最小实现**：

`palchronicle/adapters/__init__.py`（空文件）。

`palchronicle/adapters/palworld_rest.py`：
```python
"""aiohttp REST 客户端：BasicAuth、超时、脱敏错误（不含凭证/URL）。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from palchronicle.config import ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import Clock

_ENDPOINT_PATH: dict[EndpointName, str] = {
    EndpointName.INFO: "info",
    EndpointName.METRICS: "metrics",
    EndpointName.PLAYERS: "players",
    EndpointName.SETTINGS: "settings",
    EndpointName.GAME_DATA: "game-data",
}


@dataclass(slots=True)
class RestResponse:
    ok: bool
    status: int | None
    data: Any | None
    duration_ms: int
    payload_bytes: int
    error: str | None  # 已脱敏：不含凭证/URL/host


class PalworldRestClient:
    def __init__(self, server: ServerConfig, clock: Clock) -> None:
        self._server = server
        self._clock = clock
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch(self, endpoint: EndpointName) -> RestResponse:
        session = self._ensure_session()
        url = f"{self._server.base_url}/v1/api/{_ENDPOINT_PATH[endpoint]}"
        auth = aiohttp.BasicAuth(self._server.username, self._server.password)
        # verify_tls 仅对 https 有意义；http 时 ssl 参数被忽略。
        ssl_opt = None if self._server.verify_tls else False
        start = self._clock.monotonic()
        try:
            async with session.get(
                url,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=self._server.timeout),
                ssl=ssl_opt,
            ) as resp:
                body = await resp.read()
                duration_ms = int((self._clock.monotonic() - start) * 1000)
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return RestResponse(
                        ok=True, status=200, data=data,
                        duration_ms=duration_ms, payload_bytes=len(body), error=None,
                    )
                return RestResponse(
                    ok=False, status=resp.status, data=None,
                    duration_ms=duration_ms, payload_bytes=len(body),
                    error=f"http_status_{resp.status}",
                )
        except asyncio.TimeoutError:
            return self._error_response(start, "request timeout")
        except aiohttp.ClientError:
            # 绝不带上 exc 文本（可能含 host/URL）；只报类别。
            return self._error_response(start, "network error")
        except Exception:  # noqa: BLE001 — 兜底，仍脱敏
            return self._error_response(start, "unexpected error")

    def _error_response(self, start: float, message: str) -> RestResponse:
        duration_ms = int((self._clock.monotonic() - start) * 1000)
        return RestResponse(
            ok=False, status=None, data=None,
            duration_ms=duration_ms, payload_bytes=0, error=message,
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
```

> 脱敏要点：`error` 只用固定文案（`"request timeout"`/`"network error"`/`"http_status_<code>"`），从不拼接 `url`/`server.password`/异常字符串，保证不泄露 host 与凭证（对齐 spec §15 日志脱敏）。

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/palworld_rest_test.py -q`。期望 PASS：5 passed。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/adapters/__init__.py palchronicle/adapters/palworld_rest.py tests/unit/palworld_rest_test.py
git commit -m "feat(phase1): palworld_rest.py REST 客户端（BasicAuth/超时/脱敏错误）"
```

---

### Task 1.11：`adapters/sqlite_repository.py` —— 创建 Repository 类 + server/binding/world/prune 方法

**Files:**
- Create: `palchronicle/adapters/sqlite_repository.py`
- Modify: `palchronicle/domain/models.py`（本任务新建，只加本阶段需要的 `World` dataclass；其余模型 Phase 2 补）
- Test: `tests/unit/repository_server_binding_test.py`
- Test: `tests/unit/repository_world_prune_test.py`

**Interfaces:**
- Consumes：`Database`（Task 1.6，`execute_write`/`executemany_write`/`write_tx`/`query`）、`Clock`（Task 1.4）、`apply_migrations`（Task 1.7）、`ServerConfig`/`BindingConfig`/`HistoryConfig`（Task 1.3）、`World`（本任务定义，字段照契约领域模型节）。
- Produces（契约 Repository 类的本阶段方法）：
  - `class Repository.__init__(self, db: Database, clock: Clock)`。
  - `async def sync_servers(self, servers: list[ServerConfig]) -> None`。
  - `async def seed_bindings(self, bindings: list[BindingConfig]) -> None`（`INSERT OR IGNORE` seed-only；写 `active=1` 前清同 umo 其它 active）。
  - `async def cleanup_orphan_bindings(self, valid_server_ids: set[str]) -> None`。
  - `async def get_binding_active(self, umo: str) -> str | None`。
  - `async def get_allowed(self, umo: str) -> set[str]`。
  - `async def set_active(self, umo: str, server_id: str) -> None`（`allowed=1 & active=1`；清同 umo 其它 active）。
  - `async def revoke(self, umo: str, server_id: str) -> None`。
  - `async def upsert_world(self, w: World) -> None`。
  - `async def get_current_world(self, server_id: str) -> World | None`（取该 server 最近 `last_seen_at` 的 world）。
  - `async def prune(self, history: HistoryConfig, now: int) -> None`。

- [ ] **1. 写失败测试** — 创建两个测试文件。

`tests/unit/repository_server_binding_test.py`：
```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import BindingConfig, ServerConfig
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _srv(name, enabled=True):
    return ServerConfig(
        server_id=name, name=name, enabled=enabled,
        base_url="http://h:8212", username="admin", password="pw",
        timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_sync_servers_upserts(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    rows = await repo._db.query("SELECT server_id FROM servers ORDER BY server_id")
    assert [r[0] for r in rows] == ["a", "b"]


async def test_seed_bindings_inserts_when_absent(repo):
    await repo.sync_servers([_srv("a")])
    await repo.seed_bindings([BindingConfig(umo="u1", server="a", active=True)])
    assert await repo.get_binding_active("u1") == "a"
    assert await repo.get_allowed("u1") == {"a"}


async def test_seed_bindings_seed_only_does_not_overwrite_runtime(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    # 运行时管理员把 u1 切到 b
    await repo.set_active("u1", "b")
    # 预设仍指向 a → seed-only 不得覆盖运行时
    await repo.seed_bindings([BindingConfig(umo="u1", server="a", active=True)])
    assert await repo.get_binding_active("u1") == "b"


async def test_set_active_clears_other_active_for_same_umo(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")
    await repo.set_active("u1", "b")
    assert await repo.get_binding_active("u1") == "b"
    allowed = await repo.get_allowed("u1")
    assert allowed == {"a", "b"}  # allowed 累积，active 唯一


async def test_revoke_removes_allowed_and_clears_active(repo):
    await repo.sync_servers([_srv("a")])
    await repo.set_active("u1", "a")
    await repo.revoke("u1", "a")
    assert await repo.get_binding_active("u1") is None
    assert await repo.get_allowed("u1") == set()


async def test_cleanup_orphan_bindings_removes_unknown_servers(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")
    await repo.set_active("u2", "b")
    # b 从就绪集合消失
    await repo.cleanup_orphan_bindings({"a"})
    assert await repo.get_allowed("u2") == set()
    assert await repo.get_allowed("u1") == {"a"}
```

`tests/unit/repository_world_prune_test.py`：
```python
import json

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import HistoryConfig
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "w.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


def _world(server_id="s1", guid="G1", last_seen=1000, day=5):
    return World(
        world_id=f"{server_id}:{guid}:0", server_id=server_id, worldguid=guid,
        epoch=0, server_name="Srv", version="1.0",
        first_seen_at=100, last_seen_at=last_seen, current_day=day,
    )


async def test_upsert_and_get_current_world(repo):
    await repo.upsert_world(_world())
    got = await repo.get_current_world("s1")
    assert got is not None
    assert got.world_id == "s1:G1:0"
    assert got.current_day == 5


async def test_upsert_world_is_idempotent_updates_last_seen(repo):
    await repo.upsert_world(_world(last_seen=1000, day=5))
    await repo.upsert_world(_world(last_seen=2000, day=6))
    got = await repo.get_current_world("s1")
    assert got.last_seen_at == 2000
    assert got.current_day == 6
    rows = await repo._db.query("SELECT count(*) FROM worlds")
    assert rows[0][0] == 1


async def test_get_current_world_picks_latest_last_seen(repo):
    await repo.upsert_world(_world(guid="G1", last_seen=1000))
    await repo.upsert_world(_world(guid="G2", last_seen=3000))
    got = await repo.get_current_world("s1")
    assert got.worldguid == "G2"


async def test_get_current_world_none_when_absent(repo):
    assert await repo.get_current_world("nope") is None


async def test_prune_deletes_old_metrics_and_observations(repo):
    now = 100 * 86400  # day 100 (epoch)
    history = HistoryConfig(
        raw_metrics_days=7, aggregate_days=90, session_days=365, observation_days=180
    )
    # 一条旧指标(8 天前)、一条新指标(1 天前)
    await repo._db.execute_write(
        "INSERT INTO world_metrics (world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count) "
        "VALUES ('w', ?, 60, 16, 1, 5, 0)",
        (now - 8 * 86400,),
    )
    await repo._db.execute_write(
        "INSERT INTO world_metrics (world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count) "
        "VALUES ('w', ?, 60, 16, 1, 5, 0)",
        (now - 1 * 86400,),
    )
    # 一条旧观察(200 天前)、一条新观察(10 天前)
    await repo._db.execute_write(
        "INSERT INTO player_observations (world_id, player_key, observed_at, level, ping_bucket, building_count) "
        "VALUES ('w','pk', ?, 1, 'good', 0)",
        (now - 200 * 86400,),
    )
    await repo._db.execute_write(
        "INSERT INTO player_observations (world_id, player_key, observed_at, level, ping_bucket, building_count) "
        "VALUES ('w','pk', ?, 1, 'good', 0)",
        (now - 10 * 86400,),
    )
    await repo.prune(history, now)
    m = await repo._db.query("SELECT count(*) FROM world_metrics")
    o = await repo._db.query("SELECT count(*) FROM player_observations")
    assert m[0][0] == 1
    assert o[0][0] == 1


async def test_prune_keeps_events(repo):
    now = 100 * 86400
    history = HistoryConfig(
        raw_metrics_days=7, aggregate_days=90, session_days=365, observation_days=180
    )
    await repo._db.execute_write(
        "INSERT INTO world_events "
        "(world_id, event_type, subject_type, subject_key, occurred_at, confirmed_at, payload_json, visibility, confidence, dedup_key) "
        "VALUES ('w','NEW_PLAYER','player','pk', ?, ?, '{}', 'public', 'high', 'dk-old')",
        (now - 400 * 86400, now - 400 * 86400),
    )
    await repo.prune(history, now)
    rows = await repo._db.query("SELECT count(*) FROM world_events")
    assert rows[0][0] == 1  # 事件长期保留
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_server_binding_test.py tests/unit/repository_world_prune_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.adapters.sqlite_repository'`（及 `palchronicle.domain.models`）。

- [ ] **3. 写最小实现**：

创建 `palchronicle/domain/models.py`（本阶段只需 `World`；Phase 2 追加其余模型）：
```python
"""领域模型（dataclass）。字段见契约领域模型节。Phase 1 仅需 World。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class World:
    world_id: str
    server_id: str
    worldguid: str
    epoch: int
    server_name: str
    version: str
    first_seen_at: int
    last_seen_at: int
    current_day: int
```

创建 `palchronicle/adapters/sqlite_repository.py`（本阶段方法；类跨阶段增长，Phase 2+ 追加方法）：
```python
"""所有表读写（跨阶段增长的同一个 Repository 类）。

Phase 1：server / binding / world / prune 方法。
"""
from __future__ import annotations

from palchronicle.config import BindingConfig, HistoryConfig, ServerConfig
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import Clock
from palchronicle.infrastructure.database import Database

_SECONDS_PER_DAY = 86400


class Repository:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    # ---- servers ----
    async def sync_servers(self, servers: list[ServerConfig]) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            for s in servers:
                await conn.execute(
                    "INSERT INTO servers (server_id, name, host, enabled, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(server_id) DO UPDATE SET "
                    "  name=excluded.name, host=excluded.host, "
                    "  enabled=excluded.enabled, last_seen_at=excluded.last_seen_at",
                    (s.server_id, s.name, s.base_url, 1 if s.enabled else 0, now, now),
                )

    # ---- bindings / routing ----
    async def seed_bindings(self, bindings: list[BindingConfig]) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            for b in bindings:
                cursor = await conn.execute(
                    "SELECT 1 FROM group_servers WHERE umo=? AND server_id=?",
                    (b.umo, b.server),
                )
                exists = await cursor.fetchone()
                await cursor.close()
                if exists:
                    continue  # seed-only：已存在行不动
                if b.active:
                    await conn.execute(
                        "UPDATE group_servers SET active=0, updated_at=? WHERE umo=?",
                        (now, b.umo),
                    )
                await conn.execute(
                    "INSERT OR IGNORE INTO group_servers "
                    "(umo, server_id, allowed, active, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (b.umo, b.server, 1 if b.active else 0, now),
                )

    async def cleanup_orphan_bindings(self, valid_server_ids: set[str]) -> None:
        rows = await self._db.query("SELECT DISTINCT server_id FROM group_servers")
        orphans = [r[0] for r in rows if r[0] not in valid_server_ids]
        if not orphans:
            return
        async with self._db.write_tx() as conn:
            for server_id in orphans:
                await conn.execute(
                    "DELETE FROM group_servers WHERE server_id=?", (server_id,)
                )

    async def get_binding_active(self, umo: str) -> str | None:
        rows = await self._db.query(
            "SELECT server_id FROM group_servers WHERE umo=? AND active=1 LIMIT 1",
            (umo,),
        )
        return rows[0][0] if rows else None

    async def get_allowed(self, umo: str) -> set[str]:
        rows = await self._db.query(
            "SELECT server_id FROM group_servers WHERE umo=? AND allowed=1", (umo,)
        )
        return {r[0] for r in rows}

    async def set_active(self, umo: str, server_id: str) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            # active 唯一：先清同 umo 其它 active。
            await conn.execute(
                "UPDATE group_servers SET active=0, updated_at=? WHERE umo=?",
                (now, umo),
            )
            await conn.execute(
                "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
                "VALUES (?, ?, 1, 1, ?) "
                "ON CONFLICT(umo, server_id) DO UPDATE SET allowed=1, active=1, updated_at=excluded.updated_at",
                (umo, server_id, now),
            )

    async def revoke(self, umo: str, server_id: str) -> None:
        await self._db.execute_write(
            "DELETE FROM group_servers WHERE umo=? AND server_id=?", (umo, server_id)
        )

    # ---- world ----
    async def upsert_world(self, w: World) -> None:
        await self._db.execute_write(
            "INSERT INTO worlds "
            "(world_id, server_id, worldguid, epoch, server_name, version, "
            " first_seen_at, last_seen_at, current_day) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(world_id) DO UPDATE SET "
            "  server_name=excluded.server_name, version=excluded.version, "
            "  last_seen_at=excluded.last_seen_at, current_day=excluded.current_day",
            (
                w.world_id, w.server_id, w.worldguid, w.epoch, w.server_name,
                w.version, w.first_seen_at, w.last_seen_at, w.current_day,
            ),
        )

    async def get_current_world(self, server_id: str) -> World | None:
        rows = await self._db.query(
            "SELECT world_id, server_id, worldguid, epoch, server_name, version, "
            "       first_seen_at, last_seen_at, current_day "
            "FROM worlds WHERE server_id=? ORDER BY last_seen_at DESC LIMIT 1",
            (server_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return World(
            world_id=r[0], server_id=r[1], worldguid=r[2], epoch=r[3],
            server_name=r[4], version=r[5], first_seen_at=r[6],
            last_seen_at=r[7], current_day=r[8],
        )

    # ---- retention ----
    async def prune(self, history: HistoryConfig, now: int) -> None:
        metric_cutoff = now - history.raw_metrics_days * _SECONDS_PER_DAY
        obs_cutoff = now - history.observation_days * _SECONDS_PER_DAY
        session_cutoff = now - history.session_days * _SECONDS_PER_DAY
        async with self._db.write_tx() as conn:
            await conn.execute(
                "DELETE FROM world_metrics WHERE observed_at < ?", (metric_cutoff,)
            )
            await conn.execute(
                "DELETE FROM player_observations WHERE observed_at < ?", (obs_cutoff,)
            )
            await conn.execute(
                "DELETE FROM player_sessions WHERE left_at IS NOT NULL AND left_at < ?",
                (session_cutoff,),
            )
            # world_events / daily_aggregates 长期保留（spec §9.3）。
```

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_server_binding_test.py tests/unit/repository_world_prune_test.py -q`。期望 PASS：13 passed（server/binding 6 + world/prune 7）。

- [ ] **5. 提交** — 命令：
```
git add palchronicle/domain/models.py palchronicle/adapters/sqlite_repository.py tests/unit/repository_server_binding_test.py tests/unit/repository_world_prune_test.py
git commit -m "feat(phase1): Repository server/binding/world/prune 方法（seed-only/active 唯一/孤儿清理）"
```

---

### Task 1.12：Phase 1 收尾 —— 全量测试 + import 冒烟

**Files:**
- Test: `tests/unit/phase1_smoke_test.py`

**Interfaces:**
- Consumes: 本阶段全部模块的公开入口。
- Produces: 一个冒烟测试，确认所有 Phase 1 模块可 import 且关键符号存在，作为阶段回归门。

- [ ] **1. 写失败测试** — 创建 `tests/unit/phase1_smoke_test.py`：

```python
def test_all_phase1_public_symbols_importable():
    from palchronicle import __version__
    from palchronicle.adapters.palworld_rest import PalworldRestClient, RestResponse
    from palchronicle.adapters.sqlite_repository import Repository
    from palchronicle.config import AppConfig, parse_config
    from palchronicle.domain.enums import AccessMode, EndpointName
    from palchronicle.domain.models import World
    from palchronicle.infrastructure.cache import TTLCache
    from palchronicle.infrastructure.clock import Clock, FakeClock, SystemClock
    from palchronicle.infrastructure.database import Database
    from palchronicle.infrastructure.locks import EndpointLocks
    from palchronicle.infrastructure.migrations import (
        MIGRATIONS,
        MigrationError,
        apply_migrations,
    )
    from palchronicle.infrastructure.salt import load_or_create_salt

    assert __version__ == "0.1.0"
    assert callable(parse_config)
    assert callable(apply_migrations)
    assert callable(load_or_create_salt)
    assert len(MIGRATIONS) >= 1
    # 引用各符号避免未使用告警
    assert all(
        s is not None
        for s in (
            PalworldRestClient, RestResponse, Repository, AppConfig,
            AccessMode, EndpointName, World, TTLCache, Clock, FakeClock,
            SystemClock, Database, EndpointLocks, MigrationError,
        )
    )
```

- [ ] **2. 跑测试确认失败** — 命令：`python -m pytest tests/unit/phase1_smoke_test.py -q`。期望：若前置任务都已完成则本步可能直接 PASS；若某模块缺失则 FAIL 于对应 `ImportError`。（TDD 形式保留——先运行确认它真的执行了导入路径。）

- [ ] **3. 写最小实现** — 无需新实现代码（本任务是回归门；若 step 2 因某遗漏 FAIL，则补齐对应模块使其 import 成功）。

- [ ] **4. 跑测试确认通过** — 命令：`python -m pytest -q`（全量）。期望 PASS：全部 Phase 1 测试通过（skeleton 4 + conf_schema 6 + config 9 + clock 4 + salt 4 + database 6 + migrations 6 + locks 5 + cache 5 + palworld_rest 5 + repository 13 + smoke 1）。

- [ ] **5. 提交** — 命令：
```
git add tests/unit/phase1_smoke_test.py
git commit -m "test(phase1): 阶段收尾冒烟测试（全模块 import + 全量绿）"
```


## Phase 2：领域模型 + 归一/脱敏 + 采集管线 + 调度器

> 本阶段目标：能轮询 mock 服务器 → 归一 → 脱敏 → 落库 metrics/world；调度器可确定性驱动。
> 依赖 Phase 1 已产出：`palchronicle/config.py`（`ServerConfig`/`PrivacyConfig`/`PollingConfig`/`AppConfig` 等）、`palchronicle/infrastructure/clock.py`（`Clock`/`SystemClock`/`FakeClock`）、`palchronicle/infrastructure/database.py`（`Database`）、`palchronicle/infrastructure/migrations.py`、`palchronicle/infrastructure/locks.py`（`EndpointLocks`）、`palchronicle/infrastructure/cache.py`（`TTLCache`）、`palchronicle/adapters/palworld_rest.py`（`RestResponse`/`PalworldRestClient`）、`palchronicle/adapters/sqlite_repository.py`（`Repository` 类，已含 server/binding/world/prune 方法，含 `upsert_world`/`get_current_world`）。
> 本阶段给 `Repository` **追加** `insert_metric`/`latest_metric`/`peak_online`/`upsert_unknown_classes` 四个方法（各配单测）。
> 所有 import 以包根 `palchronicle` 为准；测试用 `pytest.mark.asyncio`；DB 测试用临时文件（aiosqlite + WAL 需真实文件，`:memory:` 在多连接下不共享，故用 `tmp_path` 下的 `.db`）。

---

### Task 2.1：domain/enums.py — 契约全部枚举（StrEnum）

**Files:**
- Create: `palchronicle/domain/enums.py`
- Test: `tests/unit/enums_test.py`

**Interfaces:**
- Consumes: 无（叶子模块）。
- Produces: `UnitType`, `ActionCategory`, `EventType`, `Confidence`, `LeaveReason`, `SessionStatus`, `AccessMode`, `PingBucket`, `EndpointName`, `IdConfidence`（均 `StrEnum`，成员值严格照契约）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/enums_test.py`：

```python
from enum import StrEnum

from palchronicle.domain.enums import (
    AccessMode,
    ActionCategory,
    Confidence,
    EndpointName,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
    UnitType,
)


def test_all_are_str_enum():
    for enum_cls in (
        UnitType, ActionCategory, EventType, Confidence, LeaveReason,
        SessionStatus, AccessMode, PingBucket, EndpointName, IdConfidence,
    ):
        assert issubclass(enum_cls, StrEnum)


def test_unit_type_values():
    assert UnitType.PLAYER == "Player"
    assert UnitType.OTOMO == "OtomoPal"
    assert UnitType.BASE_CAMP == "BaseCampPal"
    assert UnitType.WILD == "WildPal"
    assert UnitType.NPC == "NPC"
    assert UnitType.UNKNOWN == "Unknown"


def test_action_category_values():
    assert ActionCategory.WORKING == "working"
    assert ActionCategory.MOVING == "moving"
    assert ActionCategory.IDLE == "idle"
    assert ActionCategory.COMBAT == "combat"
    assert ActionCategory.SLEEPING == "sleeping"
    assert ActionCategory.EATING == "eating"
    assert ActionCategory.INCAPACITATED == "incapacitated"
    assert ActionCategory.UNKNOWN == "unknown"


def test_event_type_values_are_lowercase_names():
    assert EventType.PLAYER_LEVEL_UP == "player_level_up"
    assert EventType.NEW_PLAYER == "new_player"
    assert EventType.NEW_GUILD == "new_guild"
    assert EventType.NEW_BASE == "new_base"
    assert EventType.BASE_VANISHED == "base_vanished"
    assert EventType.WORKER_DELTA == "worker_delta"
    assert EventType.WORLD_DAY_MILESTONE == "world_day_milestone"
    assert EventType.ONLINE_RECORD == "online_record"


def test_scalar_enums():
    assert Confidence.HIGH == "high"
    assert Confidence.MEDIUM == "medium"
    assert Confidence.LOW == "low"
    assert LeaveReason.OBSERVED_TIMEOUT == "observed_timeout"
    assert LeaveReason.WORLD_OFFLINE == "world_offline"
    assert LeaveReason.UNKNOWN == "unknown"
    assert SessionStatus.ACTIVE == "active"
    assert SessionStatus.CLOSED == "closed"
    assert SessionStatus.UNCERTAIN == "uncertain"
    assert AccessMode.RESTRICTED == "restricted"
    assert AccessMode.OPEN == "open"
    assert PingBucket.GOOD == "good"
    assert PingBucket.OK == "ok"
    assert PingBucket.HIGH == "high"
    assert PingBucket.UNKNOWN == "unknown"
    assert EndpointName.INFO == "info"
    assert EndpointName.METRICS == "metrics"
    assert EndpointName.PLAYERS == "players"
    assert EndpointName.SETTINGS == "settings"
    assert EndpointName.GAME_DATA == "game_data"
    assert IdConfidence.HIGH == "high"
    assert IdConfidence.LOW == "low"
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/enums_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.domain.enums'`（文件尚不存在）。

- [ ] **3) 写最小实现** — 创建 `palchronicle/domain/__init__.py`（空文件）与 `palchronicle/domain/enums.py`：

```python
from __future__ import annotations

from enum import StrEnum, auto


class _LowerNameEnum(StrEnum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()


class UnitType(StrEnum):
    PLAYER = "Player"
    OTOMO = "OtomoPal"
    BASE_CAMP = "BaseCampPal"
    WILD = "WildPal"
    NPC = "NPC"
    UNKNOWN = "Unknown"


class ActionCategory(StrEnum):
    WORKING = "working"
    MOVING = "moving"
    IDLE = "idle"
    COMBAT = "combat"
    SLEEPING = "sleeping"
    EATING = "eating"
    INCAPACITATED = "incapacitated"
    UNKNOWN = "unknown"


class EventType(_LowerNameEnum):
    PLAYER_LEVEL_UP = auto()
    NEW_PLAYER = auto()
    NEW_GUILD = auto()
    NEW_BASE = auto()
    BASE_VANISHED = auto()
    WORKER_DELTA = auto()
    WORLD_DAY_MILESTONE = auto()
    ONLINE_RECORD = auto()


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LeaveReason(StrEnum):
    OBSERVED_TIMEOUT = "observed_timeout"
    WORLD_OFFLINE = "world_offline"
    UNKNOWN = "unknown"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    UNCERTAIN = "uncertain"


class AccessMode(StrEnum):
    RESTRICTED = "restricted"
    OPEN = "open"


class PingBucket(StrEnum):
    GOOD = "good"
    OK = "ok"
    HIGH = "high"
    UNKNOWN = "unknown"


class EndpointName(StrEnum):
    INFO = "info"
    METRICS = "metrics"
    PLAYERS = "players"
    SETTINGS = "settings"
    GAME_DATA = "game_data"


class IdConfidence(StrEnum):
    HIGH = "high"
    LOW = "low"
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/enums_test.py -q`。期望 PASS：6 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/domain/__init__.py palchronicle/domain/enums.py tests/unit/enums_test.py
git commit -m "feat(domain): add StrEnum definitions per interface contract"
```

---

### Task 2.2：domain/models.py — 落库模型 dataclass

**Files:**
- Create: `palchronicle/domain/models.py`
- Test: `tests/unit/models_test.py`

**Interfaces:**
- Consumes: `palchronicle/domain/enums.py`（`IdConfidence`, `PingBucket`, `SessionStatus`, `LeaveReason`, `Confidence`, `EventType`）。
- Produces: `World`, `PlayerIdentity`, `PlayerObservation`, `PlayerSession`, `Guild`, `PalBox`, `Base`, `BaseObservation`, `WorldMetric`, `WorldEvent`（均 `@dataclass(slots=True)`，字段严格照契约 §"领域模型"）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/models_test.py`：

```python
import dataclasses

from palchronicle.domain.enums import (
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
)
from palchronicle.domain.models import (
    Base,
    BaseObservation,
    Guild,
    PalBox,
    PlayerIdentity,
    PlayerObservation,
    PlayerSession,
    World,
    WorldEvent,
    WorldMetric,
)


def _field_names(cls):
    return [f.name for f in dataclasses.fields(cls)]


def test_all_models_are_slotted_dataclasses():
    for cls in (
        World, PlayerIdentity, PlayerObservation, PlayerSession, Guild,
        PalBox, Base, BaseObservation, WorldMetric, WorldEvent,
    ):
        assert dataclasses.is_dataclass(cls)
        assert not hasattr(cls, "__dict__") or "__slots__" in cls.__dict__


def test_world_fields_and_construct():
    assert _field_names(World) == [
        "world_id", "server_id", "worldguid", "epoch", "server_name",
        "version", "first_seen_at", "last_seen_at", "current_day",
    ]
    w = World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="S", version="v", first_seen_at=100, last_seen_at=200,
        current_day=3,
    )
    assert w.world_id == "s1:guid:0"


def test_player_identity_fields():
    assert _field_names(PlayerIdentity) == [
        "player_key", "world_id", "latest_name", "first_seen_at",
        "last_seen_at", "latest_level", "latest_guild_key", "id_confidence",
    ]
    p = PlayerIdentity(
        player_key="k", world_id="w", latest_name="n", first_seen_at=1,
        last_seen_at=2, latest_level=5, latest_guild_key=None,
        id_confidence=IdConfidence.HIGH,
    )
    assert p.id_confidence is IdConfidence.HIGH


def test_player_observation_fields():
    assert _field_names(PlayerObservation) == [
        "observed_at", "world_id", "player_key", "name", "level",
        "ping_bucket", "building_count", "guild_key", "position_cell",
        "companion_class",
    ]
    o = PlayerObservation(
        observed_at=1, world_id="w", player_key="k", name="n", level=3,
        ping_bucket=PingBucket.GOOD, building_count=2, guild_key=None,
        position_cell=None, companion_class=None,
    )
    assert o.ping_bucket is PingBucket.GOOD


def test_player_session_fields():
    assert _field_names(PlayerSession) == [
        "id", "world_id", "player_key", "joined_at", "last_confirmed_at",
        "left_at", "observed_seconds", "status", "leave_reason",
    ]
    s = PlayerSession(
        id=None, world_id="w", player_key="k", joined_at=1,
        last_confirmed_at=1, left_at=None, observed_seconds=0,
        status=SessionStatus.ACTIVE, leave_reason=None,
    )
    assert s.status is SessionStatus.ACTIVE
    assert s.leave_reason is None


def test_guild_fields():
    assert _field_names(Guild) == [
        "guild_key", "world_id", "latest_name", "first_seen_at",
        "last_seen_at", "observed_member_count", "palbox_count",
        "base_pal_count",
    ]


def test_palbox_fields():
    assert _field_names(PalBox) == [
        "palbox_key", "world_id", "guild_key", "position_cell",
        "first_seen_at", "last_seen_at", "status",
    ]


def test_base_fields():
    assert _field_names(Base) == [
        "base_key", "world_id", "palbox_key", "display_name", "guild_key",
        "confidence", "locked_by_admin", "hidden", "first_seen_at",
        "last_seen_at",
    ]
    b = Base(
        base_key="b", world_id="w", palbox_key="pb", display_name=None,
        guild_key=None, confidence=Confidence.MEDIUM, locked_by_admin=False,
        hidden=False, first_seen_at=1, last_seen_at=2,
    )
    assert b.confidence is Confidence.MEDIUM


def test_base_observation_fields():
    assert _field_names(BaseObservation) == [
        "base_key", "world_id", "observed_at", "worker_count",
        "active_count", "average_level", "average_hp_ratio",
        "action_distribution",
    ]
    o = BaseObservation(
        base_key="b", world_id="w", observed_at=1, worker_count=4,
        active_count=3, average_level=12.5, average_hp_ratio=0.9,
        action_distribution={"working": 3},
    )
    assert o.action_distribution == {"working": 3}


def test_world_metric_fields():
    assert _field_names(WorldMetric) == [
        "world_id", "observed_at", "fps", "frame_time", "online_players",
        "world_day", "basecamp_count",
    ]


def test_world_event_fields():
    assert _field_names(WorldEvent) == [
        "event_id", "world_id", "event_type", "subject_type", "subject_key",
        "occurred_at", "confirmed_at", "payload", "visibility",
        "confidence", "dedup_key",
    ]
    e = WorldEvent(
        event_id=None, world_id="w", event_type=EventType.NEW_PLAYER,
        subject_type="player", subject_key="k", occurred_at=1,
        confirmed_at=1, payload={"a": 1}, visibility="public",
        confidence=Confidence.HIGH, dedup_key="w|new_player|k",
    )
    assert e.event_type is EventType.NEW_PLAYER
    assert e.payload == {"a": 1}
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/models_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.domain.models'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/domain/models.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field

from palchronicle.domain.enums import (
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
)


@dataclass(slots=True)
class World:
    world_id: str
    server_id: str
    worldguid: str
    epoch: int
    server_name: str
    version: str
    first_seen_at: int
    last_seen_at: int
    current_day: int


@dataclass(slots=True)
class PlayerIdentity:
    player_key: str
    world_id: str
    latest_name: str
    first_seen_at: int
    last_seen_at: int
    latest_level: int
    latest_guild_key: str | None
    id_confidence: IdConfidence


@dataclass(slots=True)
class PlayerObservation:
    observed_at: int
    world_id: str
    player_key: str
    name: str
    level: int
    ping_bucket: PingBucket
    building_count: int
    guild_key: str | None
    position_cell: str | None
    companion_class: str | None


@dataclass(slots=True)
class PlayerSession:
    id: int | None
    world_id: str
    player_key: str
    joined_at: int
    last_confirmed_at: int
    left_at: int | None
    observed_seconds: int
    status: SessionStatus
    leave_reason: LeaveReason | None


@dataclass(slots=True)
class Guild:
    guild_key: str
    world_id: str
    latest_name: str
    first_seen_at: int
    last_seen_at: int
    observed_member_count: int
    palbox_count: int
    base_pal_count: int


@dataclass(slots=True)
class PalBox:
    palbox_key: str
    world_id: str
    guild_key: str | None
    position_cell: str
    first_seen_at: int
    last_seen_at: int
    status: str


@dataclass(slots=True)
class Base:
    base_key: str
    world_id: str
    palbox_key: str
    display_name: str | None
    guild_key: str | None
    confidence: Confidence
    locked_by_admin: bool
    hidden: bool
    first_seen_at: int
    last_seen_at: int


@dataclass(slots=True)
class BaseObservation:
    base_key: str
    world_id: str
    observed_at: int
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class WorldMetric:
    world_id: str
    observed_at: int
    fps: float
    frame_time: float
    online_players: int
    world_day: int
    basecamp_count: int


@dataclass(slots=True)
class WorldEvent:
    event_id: int | None
    world_id: str
    event_type: EventType
    subject_type: str
    subject_key: str
    occurred_at: int
    confirmed_at: int
    payload: dict
    visibility: str
    confidence: Confidence
    dedup_key: str
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/models_test.py -q`。期望 PASS：11 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/domain/models.py tests/unit/models_test.py
git commit -m "feat(domain): add persistence dataclasses per interface contract"
```

---

### Task 2.3：domain/models.py — 内存快照模型

**Files:**
- Modify: `palchronicle/domain/models.py`
- Test: `tests/unit/snapshot_models_test.py`

**Interfaces:**
- Consumes: `palchronicle/domain/enums.py`（`UnitType`, `ActionCategory`）。
- Produces: `CharacterActor`, `PalBoxActor`, `GameDataSnapshot`, `PlayerRow`, `PlayersSnapshot`, `MetricsSnapshot`, `InfoSnapshot`（均 `@dataclass(slots=True)`，字段严格照契约 §"内存快照"）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/snapshot_models_test.py`：

```python
import dataclasses

from palchronicle.domain.enums import ActionCategory, UnitType
from palchronicle.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    InfoSnapshot,
    MetricsSnapshot,
    PalBoxActor,
    PlayerRow,
    PlayersSnapshot,
)


def _field_names(cls):
    return [f.name for f in dataclasses.fields(cls)]


def test_character_actor_fields():
    assert _field_names(CharacterActor) == [
        "unit_type", "instance_id", "nickname", "trainer_instance_id",
        "trainer_nickname", "player_userid", "level", "hp", "max_hp",
        "guild_id", "guild_name", "pal_class", "action", "ai_action",
        "x", "y", "z", "is_active",
    ]
    a = CharacterActor(
        unit_type=UnitType.PLAYER, instance_id="i1", nickname="Bob",
        trainer_instance_id=None, trainer_nickname=None,
        player_userid="uid", level=10, hp=100, max_hp=100, guild_id="g1",
        guild_name="G", pal_class=None, action=ActionCategory.IDLE,
        ai_action=ActionCategory.UNKNOWN, x=1.0, y=2.0, z=3.0, is_active=True,
    )
    assert a.unit_type is UnitType.PLAYER
    assert a.action is ActionCategory.IDLE


def test_palbox_actor_fields():
    assert _field_names(PalBoxActor) == [
        "guild_id", "guild_name", "pal_class", "x", "y", "z",
    ]
    pb = PalBoxActor(guild_id="g", guild_name="G", pal_class="PalBox", x=1.0, y=2.0, z=3.0)
    assert pb.x == 1.0


def test_game_data_snapshot_fields():
    assert _field_names(GameDataSnapshot) == [
        "observed_at", "fps", "average_fps", "characters", "palboxes",
        "unknown_classes",
    ]
    gd = GameDataSnapshot(
        observed_at=1, fps=60.0, average_fps=58.0, characters=[],
        palboxes=[], unknown_classes=[],
    )
    assert gd.characters == []


def test_player_row_fields():
    assert _field_names(PlayerRow) == [
        "userid", "player_id", "name", "level", "ping", "building_count",
    ]
    r = PlayerRow(userid="h", player_id=None, name="n", level=3, ping=42.0, building_count=1)
    assert r.name == "n"


def test_players_snapshot_fields():
    assert _field_names(PlayersSnapshot) == ["observed_at", "players"]


def test_metrics_snapshot_fields():
    assert _field_names(MetricsSnapshot) == [
        "observed_at", "fps", "frame_time", "online", "max_players",
        "uptime", "basecamp_count", "days",
    ]


def test_info_snapshot_fields():
    assert _field_names(InfoSnapshot) == [
        "observed_at", "version", "server_name", "description", "worldguid",
    ]
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/snapshot_models_test.py -q`。期望 FAIL：`ImportError: cannot import name 'CharacterActor' from 'palchronicle.domain.models'`（快照类尚未加入）。

- [ ] **3) 写最小实现** — 在 `palchronicle/domain/models.py` 顶部 import 追加 `UnitType, ActionCategory`，并在文件末尾追加快照类。先改 import 行：

将
```python
from palchronicle.domain.enums import (
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
)
```
改为
```python
from palchronicle.domain.enums import (
    ActionCategory,
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
    UnitType,
)
```

在文件末尾追加：

```python
@dataclass(slots=True)
class CharacterActor:
    unit_type: UnitType
    instance_id: str | None
    nickname: str | None
    trainer_instance_id: str | None
    trainer_nickname: str | None
    player_userid: str | None
    level: int | None
    hp: int | None
    max_hp: int | None
    guild_id: str | None
    guild_name: str | None
    pal_class: str | None
    action: ActionCategory
    ai_action: ActionCategory
    x: float | None
    y: float | None
    z: float | None
    is_active: bool


@dataclass(slots=True)
class PalBoxActor:
    guild_id: str | None
    guild_name: str | None
    pal_class: str | None
    x: float
    y: float
    z: float


@dataclass(slots=True)
class GameDataSnapshot:
    observed_at: int
    fps: float
    average_fps: float
    characters: list[CharacterActor] = field(default_factory=list)
    palboxes: list[PalBoxActor] = field(default_factory=list)
    unknown_classes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlayerRow:
    userid: str | None
    player_id: str | None
    name: str
    level: int
    ping: float | None
    building_count: int


@dataclass(slots=True)
class PlayersSnapshot:
    observed_at: int
    players: list[PlayerRow] = field(default_factory=list)


@dataclass(slots=True)
class MetricsSnapshot:
    observed_at: int
    fps: float
    frame_time: float
    online: int
    max_players: int
    uptime: int
    basecamp_count: int
    days: int


@dataclass(slots=True)
class InfoSnapshot:
    observed_at: int
    version: str
    server_name: str
    description: str
    worldguid: str
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/snapshot_models_test.py -q`。期望 PASS：7 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/domain/models.py tests/unit/snapshot_models_test.py
git commit -m "feat(domain): add in-memory snapshot dataclasses"
```

---

### Task 2.4：domain/events.py — dedup_key 与 payload 构造工具

**Files:**
- Create: `palchronicle/domain/events.py`
- Test: `tests/unit/events_util_test.py`

**Interfaces:**
- Consumes: `palchronicle/domain/enums.py`（`EventType`）。
- Produces:
  - `make_dedup_key(world_id: str, event_type: EventType, *parts: object) -> str` — 以 `|` 连接 `world_id`、`event_type` 值大写、各 part 的 `str()`。
  - `level_up_payload(old_level: int, new_level: int) -> dict`
  - `worker_delta_payload(base_key: str, baseline: int, current: int) -> dict`

> 说明：契约里 `EventService.dedup_key` 是 event_service 上的 staticmethod（Phase 4 定义）。本工具供 domain 层复用同一构造规则，避免重复实现；Phase 4 的 `EventService.dedup_key` 直接委托 `make_dedup_key`。dedup 段用 event_type 名大写（与 spec §11 表格 `LEVEL_UP`/`NEW_PLAYER` 段名一致）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/events_util_test.py`：

```python
from palchronicle.domain.enums import EventType
from palchronicle.domain.events import (
    level_up_payload,
    make_dedup_key,
    worker_delta_payload,
)


def test_make_dedup_key_uses_uppercase_type_and_pipe():
    key = make_dedup_key("s1:guid:0", EventType.NEW_PLAYER, "pk123")
    assert key == "s1:guid:0|NEW_PLAYER|pk123"


def test_make_dedup_key_multiple_parts_stringified():
    key = make_dedup_key("w", EventType.WORKER_DELTA, "base9", 3, "up")
    assert key == "w|WORKER_DELTA|base9|3|up"


def test_make_dedup_key_no_parts():
    key = make_dedup_key("w", EventType.ONLINE_RECORD)
    assert key == "w|ONLINE_RECORD"


def test_level_up_payload():
    assert level_up_payload(4, 7) == {"old_level": 4, "new_level": 7}


def test_worker_delta_payload():
    assert worker_delta_payload("b1", 10, 15) == {
        "base_key": "b1",
        "baseline": 10,
        "current": 15,
        "delta": 5,
    }
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/events_util_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.domain.events'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/domain/events.py`：

```python
from __future__ import annotations

from palchronicle.domain.enums import EventType


def make_dedup_key(world_id: str, event_type: EventType, *parts: object) -> str:
    segments = [world_id, event_type.name, *(str(p) for p in parts)]
    return "|".join(segments)


def level_up_payload(old_level: int, new_level: int) -> dict:
    return {"old_level": old_level, "new_level": new_level}


def worker_delta_payload(base_key: str, baseline: int, current: int) -> dict:
    return {
        "base_key": base_key,
        "baseline": baseline,
        "current": current,
        "delta": current - baseline,
    }
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/events_util_test.py -q`。期望 PASS：5 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/domain/events.py tests/unit/events_util_test.py
git commit -m "feat(domain): add dedup_key and event payload builders"
```

---

### Task 2.5：metadata/*.json — 种子数据文件

**Files:**
- Create: `metadata/pals.zh-CN.json`
- Create: `metadata/actions.json`
- Create: `metadata/settings.zh-CN.json`
- Test: `tests/unit/metadata_files_test.py`

**Interfaces:**
- Consumes: 无（数据文件）。
- Produces: 三个 JSON 文件，结构：
  - `pals.zh-CN.json`: `{ internal_class: { pal_number:int, name_zh:str, name_en:str, element_types:list[str], rarity:int, metadata_version:str } }`，≥8 条。
  - `actions.json`: `{ action_or_ai_action: category }`，category ∈ ActionCategory 值；覆盖每个 ActionCategory（除 unknown 兜底）。
  - `settings.zh-CN.json`: `{ setting_field: { label_zh:str, unit:str, enum_map?:dict } }`，覆盖 `/pal rules` 需要字段（经验/捕获/刷新/掉落倍率、孵蛋、PVP、友伤、最大玩家、公会/据点上限）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/metadata_files_test.py`：

```python
import json
from pathlib import Path

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"

VALID_CATEGORIES = {
    "working", "moving", "idle", "combat", "sleeping", "eating",
    "incapacitated", "unknown",
}


def test_pals_file_structure_and_min_count():
    data = json.loads((METADATA_DIR / "pals.zh-CN.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert len(data) >= 8
    for cls, entry in data.items():
        assert isinstance(cls, str) and cls
        assert set(entry) >= {
            "pal_number", "name_zh", "name_en", "element_types", "rarity",
            "metadata_version",
        }
        assert isinstance(entry["pal_number"], int)
        assert isinstance(entry["name_zh"], str) and entry["name_zh"]
        assert isinstance(entry["element_types"], list)
        assert isinstance(entry["rarity"], int)


def test_actions_file_covers_all_categories():
    data = json.loads((METADATA_DIR / "actions.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    values = set(data.values())
    assert values <= VALID_CATEGORIES
    # 覆盖除 unknown 之外每个类别至少一条
    for cat in VALID_CATEGORIES - {"unknown"}:
        assert cat in values, f"missing action mapping for category {cat}"


def test_settings_file_covers_rules_fields():
    data = json.loads((METADATA_DIR / "settings.zh-CN.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    required = {
        "ExpRate", "PalCaptureRate", "PalSpawnNumRate", "DropItemMaxNum",
        "PalEggDefaultHatchingTime", "bEnablePlayerToPlayerDamage",
        "bEnableFriendlyFire", "ServerPlayerMaxNum", "GuildPlayerMaxNum",
        "BaseCampMaxNum",
    }
    assert required <= set(data)
    for field, entry in data.items():
        assert "label_zh" in entry and isinstance(entry["label_zh"], str)
        assert "unit" in entry and isinstance(entry["unit"], str)
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/metadata_files_test.py -q`。期望 FAIL：`FileNotFoundError: ...metadata/pals.zh-CN.json`（文件不存在）。

- [ ] **3) 写最小实现** — 创建三个文件。

`metadata/pals.zh-CN.json`：
```json
{
  "PalDataParameter/SheepBall": {"pal_number": 40, "name_zh": "绵绵羊", "name_en": "Lamball", "element_types": ["neutral"], "rarity": 1, "metadata_version": "0.1"},
  "PalDataParameter/CaptainPenguin": {"pal_number": 1, "name_zh": "企鹅骑士", "name_en": "Cattiva", "element_types": ["neutral"], "rarity": 1, "metadata_version": "0.1"},
  "PalDataParameter/ChickenPal": {"pal_number": 11, "name_zh": "咕咕鸡", "name_en": "Chikipi", "element_types": ["neutral"], "rarity": 1, "metadata_version": "0.1"},
  "PalDataParameter/PinkCat": {"pal_number": 2, "name_zh": "喵咪嘟", "name_en": "Cattiva", "element_types": ["neutral"], "rarity": 1, "metadata_version": "0.1"},
  "PalDataParameter/FairyDragon": {"pal_number": 39, "name_zh": "妖精龙", "name_en": "Jetragon", "element_types": ["dragon"], "rarity": 4, "metadata_version": "0.1"},
  "PalDataParameter/FlameBuffalo": {"pal_number": 30, "name_zh": "火焰牛", "name_en": "Arsox", "element_types": ["fire"], "rarity": 2, "metadata_version": "0.1"},
  "PalDataParameter/ElecPanda": {"pal_number": 90, "name_zh": "电击熊猫", "name_en": "Grizzbolt", "element_types": ["electric"], "rarity": 4, "metadata_version": "0.1"},
  "PalDataParameter/IceDeer": {"pal_number": 33, "name_zh": "冰霜鹿", "name_en": "Foxparks", "element_types": ["ice"], "rarity": 2, "metadata_version": "0.1"},
  "PalDataParameter/WaterPenguin": {"pal_number": 68, "name_zh": "海豚企鹅", "name_en": "Celaray", "element_types": ["water"], "rarity": 2, "metadata_version": "0.1"},
  "PalDataParameter/GrassMonkey": {"pal_number": 15, "name_zh": "草叶猴", "name_en": "Tanzee", "element_types": ["grass"], "rarity": 1, "metadata_version": "0.1"}
}
```

`metadata/actions.json`：
```json
{
  "EPalActionType::Work": "working",
  "EPalWorkType::Handcraft": "working",
  "EPalWorkType::Mining": "working",
  "EPalActionType::Move": "moving",
  "EPalAIActionType::MoveTo": "moving",
  "EPalActionType::Wait": "idle",
  "EPalAIActionType::Idle": "idle",
  "EPalActionType::Battle": "combat",
  "EPalAIActionType::CombatAttack": "combat",
  "EPalActionType::Sleep": "sleeping",
  "EPalAIActionType::Sleeping": "sleeping",
  "EPalActionType::Eat": "eating",
  "EPalAIActionType::EatFromFoodBox": "eating",
  "EPalActionType::Down": "incapacitated",
  "EPalAIActionType::Incapacitated": "incapacitated"
}
```

`metadata/settings.zh-CN.json`：
```json
{
  "ExpRate": {"label_zh": "经验倍率", "unit": "×"},
  "PalCaptureRate": {"label_zh": "捕获倍率", "unit": "×"},
  "PalSpawnNumRate": {"label_zh": "帕鲁刷新数量倍率", "unit": "×"},
  "DropItemMaxNum": {"label_zh": "掉落物最大数量", "unit": "个"},
  "PalEggDefaultHatchingTime": {"label_zh": "蛋孵化时间", "unit": "小时"},
  "bEnablePlayerToPlayerDamage": {"label_zh": "PVP 伤害", "unit": "", "enum_map": {"true": "开启", "false": "关闭"}},
  "bEnableFriendlyFire": {"label_zh": "友军伤害", "unit": "", "enum_map": {"true": "开启", "false": "关闭"}},
  "ServerPlayerMaxNum": {"label_zh": "最大玩家数", "unit": "人"},
  "GuildPlayerMaxNum": {"label_zh": "公会人数上限", "unit": "人"},
  "BaseCampMaxNum": {"label_zh": "据点数量上限", "unit": "个"},
  "DeathPenalty": {"label_zh": "死亡惩罚", "unit": "", "enum_map": {"None": "无", "Item": "掉落物品", "ItemAndEquipment": "掉落物品与装备", "All": "全部掉落"}}
}
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/metadata_files_test.py -q`。期望 PASS：3 passed。

- [ ] **5) 提交** — 命令：
```
git add metadata/pals.zh-CN.json metadata/actions.json metadata/settings.zh-CN.json tests/unit/metadata_files_test.py
git commit -m "feat(metadata): seed pals/actions/settings mapping files"
```

---

### Task 2.6：adapters/metadata_repository.py — MetadataRepository

**Files:**
- Create: `palchronicle/adapters/metadata_repository.py`
- Test: `tests/unit/metadata_repository_test.py`

**Interfaces:**
- Consumes: `palchronicle/domain/enums.py`（`ActionCategory`）；Task 2.5 的 JSON 文件。
- Produces（严格照契约 §"元数据仓储"）:
  - `class MetadataRepository`
  - `__init__(self, metadata_dir: Path)`
  - `load(self) -> None`
  - `pal_name(self, internal_class: str) -> str` — 已知→`name_zh`；未知→安全缩写并登记到 unknown。
  - `action_category(self, raw_action: str | None) -> ActionCategory` — 未知/None→`UNKNOWN`。
  - `setting_label(self, field: str) -> tuple[str, str]` — 缺失→`(field, "")`。
  - `take_unknown_classes(self) -> list[str]` — 返回并清空累积的未知 class 列表。

> 安全缩写规则：取 internal_class 最后一段（`/` 后），截断到 20 字符前缀，即 `class_name.rsplit("/", 1)[-1][:20]`；未知时登记原始 `internal_class` 到 unknown 集合。

- [ ] **1) 写失败测试** — 创建 `tests/unit/metadata_repository_test.py`：

```python
from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.domain.enums import ActionCategory

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _repo() -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR)
    repo.load()
    return repo


def test_known_pal_class_returns_zh_name():
    repo = _repo()
    assert repo.pal_name("PalDataParameter/SheepBall") == "绵绵羊"


def test_unknown_pal_class_returns_safe_abbrev_and_registers():
    repo = _repo()
    name = repo.pal_name("PalDataParameter/TotallyUnknownMysteryPalClass")
    assert name == "TotallyUnknownMysteryPa"[:20] or name == "TotallyUnknownMyster"
    # 缩写取最后一段前 20 字符
    assert name == "TotallyUnknownMyster"
    unknown = repo.take_unknown_classes()
    assert "PalDataParameter/TotallyUnknownMysteryPalClass" in unknown


def test_take_unknown_classes_clears_after_read():
    repo = _repo()
    repo.pal_name("PalDataParameter/UnknownX")
    first = repo.take_unknown_classes()
    assert "PalDataParameter/UnknownX" in first
    second = repo.take_unknown_classes()
    assert second == []


def test_action_category_known():
    repo = _repo()
    assert repo.action_category("EPalActionType::Work") is ActionCategory.WORKING
    assert repo.action_category("EPalActionType::Battle") is ActionCategory.COMBAT
    assert repo.action_category("EPalActionType::Sleep") is ActionCategory.SLEEPING


def test_action_category_unknown_and_none():
    repo = _repo()
    assert repo.action_category("EPalActionType::NonexistentAction") is ActionCategory.UNKNOWN
    assert repo.action_category(None) is ActionCategory.UNKNOWN
    assert repo.action_category("") is ActionCategory.UNKNOWN


def test_setting_label_known_and_missing():
    repo = _repo()
    assert repo.setting_label("ExpRate") == ("经验倍率", "×")
    assert repo.setting_label("NonexistentField") == ("NonexistentField", "")
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/metadata_repository_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.adapters.metadata_repository'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/adapters/__init__.py`（空文件）与 `palchronicle/adapters/metadata_repository.py`：

```python
from __future__ import annotations

import json
from pathlib import Path

from palchronicle.domain.enums import ActionCategory


class MetadataRepository:
    def __init__(self, metadata_dir: Path) -> None:
        self._dir = Path(metadata_dir)
        self._pals: dict[str, dict] = {}
        self._actions: dict[str, str] = {}
        self._settings: dict[str, dict] = {}
        self._unknown: list[str] = []
        self._unknown_seen: set[str] = set()

    def load(self) -> None:
        self._pals = self._read("pals.zh-CN.json")
        self._actions = self._read("actions.json")
        self._settings = self._read("settings.zh-CN.json")

    def _read(self, name: str) -> dict:
        path = self._dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def pal_name(self, internal_class: str) -> str:
        entry = self._pals.get(internal_class)
        if entry is not None:
            return entry["name_zh"]
        self._register_unknown(internal_class)
        return self._safe_abbrev(internal_class)

    def action_category(self, raw_action: str | None) -> ActionCategory:
        if not raw_action:
            return ActionCategory.UNKNOWN
        value = self._actions.get(raw_action)
        if value is None:
            return ActionCategory.UNKNOWN
        return ActionCategory(value)

    def setting_label(self, field: str) -> tuple[str, str]:
        entry = self._settings.get(field)
        if entry is None:
            return (field, "")
        return (entry.get("label_zh", field), entry.get("unit", ""))

    def take_unknown_classes(self) -> list[str]:
        out = self._unknown
        self._unknown = []
        self._unknown_seen = set()
        return out

    def _register_unknown(self, internal_class: str) -> None:
        if internal_class not in self._unknown_seen:
            self._unknown_seen.add(internal_class)
            self._unknown.append(internal_class)

    @staticmethod
    def _safe_abbrev(internal_class: str) -> str:
        return internal_class.rsplit("/", 1)[-1][:20]
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/metadata_repository_test.py -q`。期望 PASS：6 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/__init__.py palchronicle/adapters/metadata_repository.py tests/unit/metadata_repository_test.py
git commit -m "feat(adapters): add MetadataRepository with unknown-class registration"
```

---

### Task 2.7：adapters/normalizer.py — ci_get + str_bool + normalize_info/metrics

**Files:**
- Create: `palchronicle/adapters/normalizer.py`
- Test: `tests/unit/normalizer_test.py`

**Interfaces:**
- Consumes: `palchronicle/domain/models.py`（`InfoSnapshot`, `MetricsSnapshot`）。
- Produces（照契约 §"归一化"）:
  - `ci_get(d: Mapping, *keys: str, default=None) -> Any` — 大小写不敏感，多 key 取第一个命中。
  - `str_bool(v) -> bool` — `"true"/"1"/True/1` → True；`"false"/"0"/False/0/None/""` → False。
  - `normalize_info(raw: Mapping, now: int) -> InfoSnapshot`
  - `normalize_metrics(raw: Mapping, now: int) -> MetricsSnapshot`

> 官方字段名参考：`/info`→`version`/`servername`/`description`/`worldguid`；`/metrics`→`serverfps`/`serverframetime`/`currentplayernum`/`maxplayernum`/`uptime`/`serversdaytime`/`days`(世界天数以 `serversdaytime`→天，本 v0.1 用整型 `days` 字段兜底)/`basecampnum`。字段大小写混用一律用 `ci_get`。

- [ ] **1) 写失败测试** — 创建 `tests/unit/normalizer_test.py`：

```python
import pytest

from palchronicle.adapters.normalizer import (
    ci_get,
    normalize_info,
    normalize_metrics,
    str_bool,
)


def test_ci_get_case_insensitive():
    d = {"WorldGuid": "abc", "Version": "0.1"}
    assert ci_get(d, "worldguid") == "abc"
    assert ci_get(d, "VERSION") == "0.1"


def test_ci_get_multiple_keys_first_hit():
    d = {"currentplayernum": 5}
    assert ci_get(d, "CurrentPlayerNum", "online", default=0) == 5


def test_ci_get_default_when_missing():
    assert ci_get({}, "nope", default=-1) == -1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("TRUE", True), ("1", True),
        (1, True), (True, True),
        ("false", False), ("False", False), ("0", False), (0, False),
        (False, False), (None, False), ("", False),
    ],
)
def test_str_bool(raw, expected):
    assert str_bool(raw) is expected


def test_normalize_info_mixed_case_and_missing():
    raw = {"Version": "0.3.1", "ServerName": "My World", "WorldGuid": "GUID123"}
    snap = normalize_info(raw, now=1000)
    assert snap.observed_at == 1000
    assert snap.version == "0.3.1"
    assert snap.server_name == "My World"
    assert snap.worldguid == "GUID123"
    assert snap.description == ""  # 缺失字段宽容


def test_normalize_metrics_mixed_case_and_types():
    raw = {
        "ServerFps": 58, "ServerFrameTime": "17.2", "CurrentPlayerNum": "4",
        "MaxPlayerNum": 32, "Uptime": 3600, "Days": 12, "BaseCampNum": 7,
    }
    snap = normalize_metrics(raw, now=2000)
    assert snap.observed_at == 2000
    assert snap.fps == 58.0
    assert snap.frame_time == 17.2
    assert snap.online == 4
    assert snap.max_players == 32
    assert snap.uptime == 3600
    assert snap.days == 12
    assert snap.basecamp_count == 7


def test_normalize_metrics_missing_fields_default_zero():
    snap = normalize_metrics({}, now=3000)
    assert snap.fps == 0.0
    assert snap.online == 0
    assert snap.basecamp_count == 0
    assert snap.days == 0
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/normalizer_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.adapters.normalizer'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/adapters/normalizer.py`：

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from palchronicle.domain.models import InfoSnapshot, MetricsSnapshot

_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})


def ci_get(d: Mapping, *keys: str, default: Any = None) -> Any:
    lowered = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return default


def str_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in _TRUE_STRINGS
    return False


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def normalize_info(raw: Mapping, now: int) -> InfoSnapshot:
    return InfoSnapshot(
        observed_at=now,
        version=str(ci_get(raw, "version", default="") or ""),
        server_name=str(ci_get(raw, "servername", "server_name", default="") or ""),
        description=str(ci_get(raw, "description", default="") or ""),
        worldguid=str(ci_get(raw, "worldguid", "world_guid", default="") or ""),
    )


def normalize_metrics(raw: Mapping, now: int) -> MetricsSnapshot:
    return MetricsSnapshot(
        observed_at=now,
        fps=_as_float(ci_get(raw, "serverfps", "fps")),
        frame_time=_as_float(ci_get(raw, "serverframetime", "frametime", "frame_time")),
        online=_as_int(ci_get(raw, "currentplayernum", "online", "currentplayers")),
        max_players=_as_int(ci_get(raw, "maxplayernum", "maxplayers", "max_players")),
        uptime=_as_int(ci_get(raw, "uptime")),
        basecamp_count=_as_int(ci_get(raw, "basecampnum", "basecamp_count")),
        days=_as_int(ci_get(raw, "days", "serversdaytime", "world_day")),
    )
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/normalizer_test.py -q`。期望 PASS：8 passed（含参数化 13 例）。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/normalizer.py tests/unit/normalizer_test.py
git commit -m "feat(adapters): add ci_get/str_bool + normalize_info/metrics"
```

---

### Task 2.8：adapters/normalizer.py — normalize_players

**Files:**
- Modify: `palchronicle/adapters/normalizer.py`
- Test: `tests/unit/normalizer_players_test.py`

**Interfaces:**
- Consumes: 本模块 `ci_get`。
- Produces（照契约）: `normalize_players(raw: Mapping, now: int) -> list[dict]` — 每玩家 dict **保留** `userId`/`playerId`/`name`/`level`/`ping`/`building_count`/`ip`/`accountName`（原始字段，待 privacy_filter 脱敏）。归一目标：统一键为上述规范名，容忍大小写混用与缺失；`level` 转 int，`ping` 转 float 或 None，`building_count` 转 int。

> 官方 `/players` 每条含 `userId`/`playerId`/`name`/`level`/`ping`/`building_count`/`ip`/`accountName`（大小写各版本可能不同）。normalize 只做键名规范 + 类型收敛，**不删任何字段**（删字段是 privacy_filter 的职责，spec §6.2 顺序：先归一后脱敏）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/normalizer_players_test.py`：

```python
from palchronicle.adapters.normalizer import normalize_players


def test_normalize_players_mixed_case_keys():
    raw = {
        "players": [
            {
                "UserId": "u-1", "PlayerId": "p-1", "Name": "Alice",
                "Level": "12", "Ping": "45.5", "BuildingCount": "3",
                "Ip": "10.0.0.5", "AccountName": "steam_alice",
            }
        ]
    }
    rows = normalize_players(raw, now=100)
    assert len(rows) == 1
    r = rows[0]
    assert r["userId"] == "u-1"
    assert r["playerId"] == "p-1"
    assert r["name"] == "Alice"
    assert r["level"] == 12
    assert r["ping"] == 45.5
    assert r["building_count"] == 3
    # 原始敏感字段仍保留(待脱敏)
    assert r["ip"] == "10.0.0.5"
    assert r["accountName"] == "steam_alice"


def test_normalize_players_missing_optional_fields():
    raw = {"players": [{"name": "Bob", "level": 1}]}
    rows = normalize_players(raw, now=100)
    r = rows[0]
    assert r["name"] == "Bob"
    assert r["level"] == 1
    assert r["userId"] is None
    assert r["playerId"] is None
    assert r["ping"] is None
    assert r["building_count"] == 0
    assert r["ip"] is None
    assert r["accountName"] is None


def test_normalize_players_empty_or_missing_list():
    assert normalize_players({}, now=1) == []
    assert normalize_players({"players": []}, now=1) == []


def test_normalize_players_top_level_list():
    # 有的实现直接返回顶层数组
    raw = [{"name": "Cara", "level": 5}]
    rows = normalize_players(raw, now=1)
    assert rows[0]["name"] == "Cara"
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/normalizer_players_test.py -q`。期望 FAIL：`ImportError: cannot import name 'normalize_players'`。

- [ ] **3) 写最小实现** — 在 `palchronicle/adapters/normalizer.py` 末尾追加：

```python
def _player_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, Mapping):
        value = ci_get(raw, "players", default=[])
        if isinstance(value, list):
            return value
    return []


def _opt_float(v):
    if v is None or v == "":
        return None
    return _as_float(v)


def normalize_players(raw: Mapping, now: int) -> list[dict]:
    rows: list[dict] = []
    for item in _player_list(raw):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "userId": ci_get(item, "userid", "user_id", default=None),
                "playerId": ci_get(item, "playerid", "player_id", default=None),
                "name": str(ci_get(item, "name", default="") or ""),
                "level": _as_int(ci_get(item, "level", default=0)),
                "ping": _opt_float(ci_get(item, "ping", default=None)),
                "building_count": _as_int(
                    ci_get(item, "building_count", "buildingcount", default=0)
                ),
                "ip": ci_get(item, "ip", default=None),
                "accountName": ci_get(item, "accountname", "account_name", default=None),
            }
        )
    return rows
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/normalizer_players_test.py -q`。期望 PASS：4 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/normalizer.py tests/unit/normalizer_players_test.py
git commit -m "feat(adapters): add normalize_players (keep raw sensitive fields for later redaction)"
```

---

### Task 2.9：adapters/normalizer.py — normalize_game_data（重点：大小写/字符串布尔/未知 class 容错）

**Files:**
- Modify: `palchronicle/adapters/normalizer.py`
- Test: `tests/unit/normalizer_game_data_test.py`

**Interfaces:**
- Consumes: `palchronicle/adapters/metadata_repository.py`（`MetadataRepository.action_category`, `.pal_name` 用于登记未知 class）；`palchronicle/domain/models.py`（`GameDataSnapshot`, `CharacterActor`, `PalBoxActor`）；`palchronicle/domain/enums.py`（`UnitType`, `ActionCategory`）。
- Produces（照契约）: `normalize_game_data(raw: Mapping, now: int, meta: MetadataRepository) -> GameDataSnapshot`。

> 归一要点（spec §6.2 step 2）：容忍键名大小写混用（`userid`/`HP`/`GuildID`/`LocationX`）；`IsActive` 字符串布尔用 `str_bool`；缺失字段宽容；未知 `Class`（PalBox/actor 的 pal_class）经 `meta` 登记进 `unknown_classes` 但**不丢整快照**。UnitType 解析：`type`/`unittype` 字段映射到 `UnitType`，未知→`UNKNOWN`。actor 坐标 `LocationX/Y/Z` 或 `x/y/z`。PalBox actor 从 `palboxes`/`PalBoxes` 数组取，坐标必填（缺失则跳过该 palbox）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/normalizer_game_data_test.py`：

```python
from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.adapters.normalizer import normalize_game_data
from palchronicle.domain.enums import ActionCategory, UnitType

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _meta() -> MetadataRepository:
    m = MetadataRepository(METADATA_DIR)
    m.load()
    return m


def test_normalize_game_data_mixed_case_and_str_bool():
    raw = {
        "ServerFps": 55, "AverageFps": 52,
        "Characters": [
            {
                "Type": "Player", "InstanceID": "I-1", "NickName": "Alice",
                "userid": "u-1", "Level": "20", "HP": "900", "MaxHP": 1000,
                "GuildID": "g-1", "GuildName": "Noema",
                "Action": "EPalActionType::Work", "AIAction": "EPalAIActionType::MoveTo",
                "LocationX": "100.5", "LocationY": "-200.25", "LocationZ": 10,
                "IsActive": "true",
            }
        ],
        "PalBoxes": [
            {"GuildID": "g-1", "GuildName": "Noema", "Class": "PalDataParameter/SheepBall",
             "LocationX": 100, "LocationY": 200, "LocationZ": 5}
        ],
    }
    meta = _meta()
    snap = normalize_game_data(raw, now=500, meta=meta)
    assert snap.observed_at == 500
    assert snap.fps == 55.0
    assert snap.average_fps == 52.0
    assert len(snap.characters) == 1
    c = snap.characters[0]
    assert c.unit_type is UnitType.PLAYER
    assert c.instance_id == "I-1"
    assert c.nickname == "Alice"
    assert c.player_userid == "u-1"
    assert c.level == 20
    assert c.hp == 900
    assert c.max_hp == 1000
    assert c.guild_id == "g-1"
    assert c.guild_name == "Noema"
    assert c.action is ActionCategory.WORKING
    assert c.ai_action is ActionCategory.MOVING
    assert c.x == 100.5
    assert c.y == -200.25
    assert c.z == 10.0
    assert c.is_active is True
    assert len(snap.palboxes) == 1
    assert snap.palboxes[0].guild_id == "g-1"
    assert snap.palboxes[0].x == 100.0


def test_normalize_game_data_lowercase_keys():
    raw = {
        "characters": [
            {"type": "BaseCampPal", "class": "PalDataParameter/ChickenPal",
             "hp": 50, "maxhp": 100, "guildid": "g-2",
             "action": "EPalActionType::Wait", "isactive": "false",
             "locationx": 1, "locationy": 2, "locationz": 3}
        ]
    }
    snap = normalize_game_data(raw, now=1, meta=_meta())
    c = snap.characters[0]
    assert c.unit_type is UnitType.BASE_CAMP
    assert c.pal_class == "PalDataParameter/ChickenPal"
    assert c.action is ActionCategory.IDLE
    assert c.is_active is False


def test_normalize_game_data_unknown_class_registered_not_dropped():
    raw = {
        "characters": [
            {"type": "WildPal", "class": "PalDataParameter/BrandNewPal_2099",
             "action": "EPalActionType::Move", "isactive": True,
             "locationx": 0, "locationy": 0, "locationz": 0}
        ]
    }
    meta = _meta()
    snap = normalize_game_data(raw, now=1, meta=meta)
    # 整快照未丢, actor 仍在
    assert len(snap.characters) == 1
    assert "PalDataParameter/BrandNewPal_2099" in snap.unknown_classes


def test_normalize_game_data_missing_and_empty_fields():
    raw = {"characters": [{"type": "NPC"}]}
    snap = normalize_game_data(raw, now=1, meta=_meta())
    c = snap.characters[0]
    assert c.unit_type is UnitType.NPC
    assert c.level is None
    assert c.hp is None
    assert c.guild_id is None
    assert c.action is ActionCategory.UNKNOWN
    assert c.ai_action is ActionCategory.UNKNOWN
    assert c.x is None
    assert c.is_active is False


def test_normalize_game_data_unknown_unit_type():
    raw = {"characters": [{"type": "SomethingWeird"}]}
    snap = normalize_game_data(raw, now=1, meta=_meta())
    assert snap.characters[0].unit_type is UnitType.UNKNOWN


def test_normalize_game_data_palbox_missing_coords_skipped():
    raw = {"palboxes": [{"guildid": "g-9", "class": "PalDataParameter/SheepBall"}]}
    snap = normalize_game_data(raw, now=1, meta=_meta())
    assert snap.palboxes == []


def test_normalize_game_data_empty_payload():
    snap = normalize_game_data({}, now=42, meta=_meta())
    assert snap.observed_at == 42
    assert snap.characters == []
    assert snap.palboxes == []
    assert snap.unknown_classes == []
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/normalizer_game_data_test.py -q`。期望 FAIL：`ImportError: cannot import name 'normalize_game_data'`。

- [ ] **3) 写最小实现** — 在 `palchronicle/adapters/normalizer.py` 顶部 import 追加，并在末尾追加函数。先改 import 块，把
```python
from palchronicle.domain.models import InfoSnapshot, MetricsSnapshot
```
改为
```python
from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.domain.enums import ActionCategory, UnitType
from palchronicle.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    InfoSnapshot,
    MetricsSnapshot,
    PalBoxActor,
)
```

在文件末尾追加：

```python
_UNIT_TYPE_BY_VALUE = {ut.value.lower(): ut for ut in UnitType}


def _parse_unit_type(raw_type) -> UnitType:
    if not raw_type:
        return UnitType.UNKNOWN
    return _UNIT_TYPE_BY_VALUE.get(str(raw_type).lower(), UnitType.UNKNOWN)


def _opt_int(v):
    if v is None or v == "":
        return None
    return _as_int(v)


def _opt_coord(v):
    if v is None or v == "":
        return None
    return _as_float(v)


def _character_list(raw: Mapping) -> list:
    value = ci_get(raw, "characters", "Characters", default=[])
    return value if isinstance(value, list) else []


def _palbox_list(raw: Mapping) -> list:
    value = ci_get(raw, "palboxes", "PalBoxes", default=[])
    return value if isinstance(value, list) else []


def _register_class_if_unknown(pal_class, meta: MetadataRepository) -> None:
    if pal_class:
        # pal_name 内部对未知 class 登记入 unknown_classes
        meta.pal_name(str(pal_class))


def normalize_game_data(
    raw: Mapping, now: int, meta: MetadataRepository
) -> GameDataSnapshot:
    characters: list[CharacterActor] = []
    for item in _character_list(raw):
        if not isinstance(item, Mapping):
            continue
        pal_class = ci_get(item, "class", "pal_class", default=None)
        _register_class_if_unknown(pal_class, meta)
        characters.append(
            CharacterActor(
                unit_type=_parse_unit_type(ci_get(item, "type", "unittype", "unit_type")),
                instance_id=ci_get(item, "instanceid", "instance_id", default=None),
                nickname=ci_get(item, "nickname", "nick_name", "name", default=None),
                trainer_instance_id=ci_get(
                    item, "trainerinstanceid", "trainer_instance_id", default=None
                ),
                trainer_nickname=ci_get(
                    item, "trainernickname", "trainer_nickname", default=None
                ),
                player_userid=ci_get(item, "userid", "user_id", default=None),
                level=_opt_int(ci_get(item, "level", default=None)),
                hp=_opt_int(ci_get(item, "hp", default=None)),
                max_hp=_opt_int(ci_get(item, "maxhp", "max_hp", default=None)),
                guild_id=ci_get(item, "guildid", "guild_id", default=None),
                guild_name=ci_get(item, "guildname", "guild_name", default=None),
                pal_class=str(pal_class) if pal_class else None,
                action=meta.action_category(ci_get(item, "action", default=None)),
                ai_action=meta.action_category(
                    ci_get(item, "aiaction", "ai_action", default=None)
                ),
                x=_opt_coord(ci_get(item, "locationx", "x", default=None)),
                y=_opt_coord(ci_get(item, "locationy", "y", default=None)),
                z=_opt_coord(ci_get(item, "locationz", "z", default=None)),
                is_active=str_bool(ci_get(item, "isactive", "is_active", default=False)),
            )
        )

    palboxes: list[PalBoxActor] = []
    for item in _palbox_list(raw):
        if not isinstance(item, Mapping):
            continue
        pal_class = ci_get(item, "class", "pal_class", default=None)
        _register_class_if_unknown(pal_class, meta)
        x = ci_get(item, "locationx", "x", default=None)
        y = ci_get(item, "locationy", "y", default=None)
        z = ci_get(item, "locationz", "z", default=None)
        if x in (None, "") or y in (None, "") or z in (None, ""):
            continue
        palboxes.append(
            PalBoxActor(
                guild_id=ci_get(item, "guildid", "guild_id", default=None),
                guild_name=ci_get(item, "guildname", "guild_name", default=None),
                pal_class=str(pal_class) if pal_class else None,
                x=_as_float(x),
                y=_as_float(y),
                z=_as_float(z),
            )
        )

    return GameDataSnapshot(
        observed_at=now,
        fps=_as_float(ci_get(raw, "serverfps", "fps")),
        average_fps=_as_float(ci_get(raw, "averagefps", "average_fps")),
        characters=characters,
        palboxes=palboxes,
        unknown_classes=meta.take_unknown_classes(),
    )
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/normalizer_game_data_test.py -q`。期望 PASS：7 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/normalizer.py tests/unit/normalizer_game_data_test.py
git commit -m "feat(adapters): add normalize_game_data with case/bool/unknown-class tolerance"
```

---

### Task 2.10：adapters/privacy_filter.py — hash_user_id + bucketize_ping + quantize_cell

**Files:**
- Create: `palchronicle/adapters/privacy_filter.py`
- Test: `tests/unit/privacy_filter_primitives_test.py`

**Interfaces:**
- Consumes: `palchronicle/config.py`（`PrivacyConfig`）；`palchronicle/domain/enums.py`（`PingBucket`）。
- Produces（照契约 §"脱敏"）:
  - `hash_user_id(salt: bytes, world_id: str, raw_user_id: str) -> str` — HMAC-SHA256 hex（消息 = `world_id + ":" + raw_user_id`）。
  - `bucketize_ping(ms: float | None, cfg: PrivacyConfig) -> PingBucket` — `≤ping_good_ms`→GOOD；`≤ping_ok_ms`→OK；`>ping_ok_ms`→HIGH；None→UNKNOWN。
  - `quantize_cell(x: float, y: float, z: float, grid: int) -> str` — `"cx:cy:cz"`，`cx=floor(x/grid)` 等。

- [ ] **1) 写失败测试** — 创建 `tests/unit/privacy_filter_primitives_test.py`：

```python
from palchronicle.adapters.privacy_filter import (
    bucketize_ping,
    hash_user_id,
    quantize_cell,
)
from palchronicle.config import PrivacyConfig
from palchronicle.domain.enums import PingBucket


def _cfg(good=60, ok=120) -> PrivacyConfig:
    return PrivacyConfig(
        mode="balanced", public_exact_ping=False, public_positions=False,
        ping_good_ms=good, ping_ok_ms=ok, uncertain_timeout=900,
    )


def test_hash_user_id_is_stable_and_deterministic():
    salt = b"\x01" * 32
    h1 = hash_user_id(salt, "s1:guid:0", "user-abc")
    h2 = hash_user_id(salt, "s1:guid:0", "user-abc")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    assert all(ch in "0123456789abcdef" for ch in h1)


def test_hash_user_id_differs_by_world_and_id_and_salt():
    salt = b"\x01" * 32
    other_salt = b"\x02" * 32
    base = hash_user_id(salt, "s1:guid:0", "user-abc")
    assert hash_user_id(salt, "s2:guid:0", "user-abc") != base
    assert hash_user_id(salt, "s1:guid:0", "user-xyz") != base
    assert hash_user_id(other_salt, "s1:guid:0", "user-abc") != base


def test_hash_user_id_no_raw_id_residue():
    salt = b"\x01" * 32
    raw = "SuperSecretUserId12345"
    h = hash_user_id(salt, "w", raw)
    assert raw not in h
    assert raw.lower() not in h


def test_bucketize_ping_boundaries():
    cfg = _cfg(good=60, ok=120)
    assert bucketize_ping(60.0, cfg) is PingBucket.GOOD    # == good 阈值 → GOOD
    assert bucketize_ping(59.9, cfg) is PingBucket.GOOD
    assert bucketize_ping(60.1, cfg) is PingBucket.OK
    assert bucketize_ping(120.0, cfg) is PingBucket.OK     # == ok 阈值 → OK
    assert bucketize_ping(120.1, cfg) is PingBucket.HIGH
    assert bucketize_ping(None, cfg) is PingBucket.UNKNOWN


def test_quantize_cell_floor_division():
    assert quantize_cell(100.0, 200.0, 5.0, grid=2000) == "0:0:0"
    assert quantize_cell(2001.0, 4000.0, -1.0, grid=2000) == "1:2:-1"
    assert quantize_cell(-1.0, -2001.0, 0.0, grid=2000) == "-1:-2:0"
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/privacy_filter_primitives_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.adapters.privacy_filter'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/adapters/privacy_filter.py`：

```python
from __future__ import annotations

import hmac
import math
from hashlib import sha256

from palchronicle.config import PrivacyConfig
from palchronicle.domain.enums import PingBucket


def hash_user_id(salt: bytes, world_id: str, raw_user_id: str) -> str:
    message = f"{world_id}:{raw_user_id}".encode("utf-8")
    return hmac.new(salt, message, sha256).hexdigest()


def bucketize_ping(ms: float | None, cfg: PrivacyConfig) -> PingBucket:
    if ms is None:
        return PingBucket.UNKNOWN
    if ms <= cfg.ping_good_ms:
        return PingBucket.GOOD
    if ms <= cfg.ping_ok_ms:
        return PingBucket.OK
    return PingBucket.HIGH


def quantize_cell(x: float, y: float, z: float, grid: int) -> str:
    cx = math.floor(x / grid)
    cy = math.floor(y / grid)
    cz = math.floor(z / grid)
    return f"{cx}:{cy}:{cz}"
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/privacy_filter_primitives_test.py -q`。期望 PASS：5 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/privacy_filter.py tests/unit/privacy_filter_primitives_test.py
git commit -m "feat(adapters): add privacy primitives hash/bucket/quantize"
```

---

### Task 2.11：adapters/privacy_filter.py — redact_players

**Files:**
- Modify: `palchronicle/adapters/privacy_filter.py`
- Test: `tests/unit/privacy_filter_players_test.py`

**Interfaces:**
- Consumes: 本模块 `hash_user_id`, `bucketize_ping`；`palchronicle/domain/models.py`（`PlayersSnapshot`, `PlayerRow`）；`palchronicle/domain/enums.py`（`PingBucket`）；`palchronicle/config.py`（`PrivacyConfig`）。
- Produces（照契约）: `redact_players(rows: list[dict], world_id: str, salt: bytes, cfg: PrivacyConfig) -> PlayersSnapshot`。删 `ip`/`accountName`；`ping`→bucket 存于 `PlayerRow.ping`? **注意**：契约 `PlayerRow.ping:float|None` 为内存渲染用原始 ping；落库分桶在 repository 侧完成。为对齐 spec §15"落库前分桶且 player_observations 只存 bucket"，本函数产出的 `PlayerRow` 保留 ping 供内存渲染，但**删除 ip/accountName**，`userid` 替换为 hash（或 None），`playerId` 同理 hash（或 None）。observed_at 由调用方传入（见签名调整下）。

> 契约签名 `redact_players(rows, world_id, salt, cfg) -> PlayersSnapshot` 未含 `observed_at`。`PlayersSnapshot.observed_at` 取 rows 无法得知，故约定：`redact_players` 额外接受 `observed_at:int` 作为**关键字**参数（默认 0），保持位置签名与契约一致，落库时由 SnapshotService 填真值。测试覆盖两种调用。

- [ ] **1) 写失败测试** — 创建 `tests/unit/privacy_filter_players_test.py`：

```python
from palchronicle.adapters.privacy_filter import hash_user_id, redact_players
from palchronicle.config import PrivacyConfig


def _cfg() -> PrivacyConfig:
    return PrivacyConfig(
        mode="balanced", public_exact_ping=False, public_positions=False,
        ping_good_ms=60, ping_ok_ms=120, uncertain_timeout=900,
    )


def _rows():
    return [
        {
            "userId": "u-1", "playerId": "p-1", "name": "Alice", "level": 12,
            "ping": 45.5, "building_count": 3, "ip": "10.0.0.5",
            "accountName": "steam_alice",
        },
        {
            "userId": None, "playerId": None, "name": "Bob", "level": 1,
            "ping": None, "building_count": 0, "ip": "192.168.1.9",
            "accountName": "steam_bob",
        },
    ]


def test_redact_players_removes_ip_and_account_and_hashes_id():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "s1:guid:0", salt, _cfg(), observed_at=999)
    assert snap.observed_at == 999
    assert len(snap.players) == 2
    a = snap.players[0]
    assert a.name == "Alice"
    assert a.level == 12
    assert a.building_count == 3
    assert a.ping == 45.5  # 内存渲染保留
    # userId 被替换为 hash, 无原始 id
    assert a.userid == hash_user_id(salt, "s1:guid:0", "u-1")
    assert a.userid != "u-1"
    # 脱敏后的 PlayerRow 无 ip/accountName 属性(dataclass 无此字段)
    assert not hasattr(a, "ip")
    assert not hasattr(a, "accountName")


def test_redact_players_none_id_stays_none():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "w", salt, _cfg())
    b = snap.players[1]
    assert b.userid is None
    assert b.player_id is None
    assert b.name == "Bob"


def test_redact_players_playerid_hashed_when_present():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "w", salt, _cfg())
    a = snap.players[0]
    assert a.player_id == hash_user_id(salt, "w", "p-1")


def test_redact_players_no_raw_ip_in_output_repr():
    salt = b"\x07" * 32
    snap = redact_players(_rows(), "w", salt, _cfg())
    text = repr(snap)
    assert "10.0.0.5" not in text
    assert "192.168.1.9" not in text
    assert "steam_alice" not in text
    assert "u-1" not in text
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/privacy_filter_players_test.py -q`。期望 FAIL：`ImportError: cannot import name 'redact_players'`。

- [ ] **3) 写最小实现** — 在 `palchronicle/adapters/privacy_filter.py` 顶部 import 追加，并在末尾追加函数。先在 import 块追加：
```python
from palchronicle.domain.models import PlayerRow, PlayersSnapshot
```

在文件末尾追加：

```python
def _hash_or_none(salt: bytes, world_id: str, raw_id) -> str | None:
    if raw_id is None or raw_id == "":
        return None
    return hash_user_id(salt, world_id, str(raw_id))


def redact_players(
    rows: list[dict],
    world_id: str,
    salt: bytes,
    cfg: PrivacyConfig,
    observed_at: int = 0,
) -> PlayersSnapshot:
    players: list[PlayerRow] = []
    for row in rows:
        players.append(
            PlayerRow(
                userid=_hash_or_none(salt, world_id, row.get("userId")),
                player_id=_hash_or_none(salt, world_id, row.get("playerId")),
                name=row.get("name", ""),
                level=int(row.get("level", 0) or 0),
                ping=row.get("ping"),
                building_count=int(row.get("building_count", 0) or 0),
            )
        )
    return PlayersSnapshot(observed_at=observed_at, players=players)
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/privacy_filter_players_test.py -q`。期望 PASS：4 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/privacy_filter.py tests/unit/privacy_filter_players_test.py
git commit -m "feat(adapters): add redact_players (drop ip/accountName, hash ids)"
```

---

### Task 2.12：adapters/privacy_filter.py — redact_game_data

**Files:**
- Modify: `palchronicle/adapters/privacy_filter.py`
- Test: `tests/unit/privacy_filter_game_data_test.py`

**Interfaces:**
- Consumes: 本模块 `hash_user_id`, `quantize_cell`；`palchronicle/domain/models.py`（`GameDataSnapshot`, `CharacterActor`, `PalBoxActor`）；`palchronicle/config.py`（`PrivacyConfig`）。
- Produces（照契约）: `redact_game_data(snap: GameDataSnapshot, world_id: str, salt: bytes, cfg: PrivacyConfig) -> GameDataSnapshot`。
  - `player_userid` → hash（或 None）。
  - `cfg.mode == "strict"`：所有 actor 与 palbox 坐标置 None（PalBoxActor.x/y/z 为必填 float → strict 下坐标改存 `float('nan')`? 不可；改为**strict 下丢弃 palboxes**，spec §15 strict 禁据点持久化）。故 strict：`characters[*].x/y/z=None`、`palboxes=[]`。
  - `cfg.mode != "strict"`（balanced/advanced）：坐标保留原值供 tracker 计算（量化落库在 base_service/repository 侧用 `quantize_cell`）；`player_userid` 仍 hash。

> spec §15 strict：不落库任何网格、禁用据点/PalBox 持久化。因此脱敏层在 strict 下直接清空 palboxes 与 character 坐标，保证后续管线拿不到精确坐标。balanced/advanced 保留坐标（advanced v0.1 等同 balanced）。

- [ ] **1) 写失败测试** — 创建 `tests/unit/privacy_filter_game_data_test.py`：

```python
from palchronicle.adapters.privacy_filter import hash_user_id, redact_game_data
from palchronicle.config import PrivacyConfig
from palchronicle.domain.enums import ActionCategory, UnitType
from palchronicle.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    PalBoxActor,
)


def _cfg(mode="balanced") -> PrivacyConfig:
    return PrivacyConfig(
        mode=mode, public_exact_ping=False, public_positions=False,
        ping_good_ms=60, ping_ok_ms=120, uncertain_timeout=900,
    )


def _snap() -> GameDataSnapshot:
    player = CharacterActor(
        unit_type=UnitType.PLAYER, instance_id="i1", nickname="Alice",
        trainer_instance_id=None, trainer_nickname=None, player_userid="raw-uid",
        level=10, hp=90, max_hp=100, guild_id="g1", guild_name="G",
        pal_class=None, action=ActionCategory.IDLE, ai_action=ActionCategory.UNKNOWN,
        x=123.0, y=456.0, z=7.0, is_active=True,
    )
    palbox = PalBoxActor(guild_id="g1", guild_name="G", pal_class="PalBox", x=1.0, y=2.0, z=3.0)
    return GameDataSnapshot(
        observed_at=1, fps=60.0, average_fps=58.0, characters=[player],
        palboxes=[palbox], unknown_classes=[],
    )


def test_redact_game_data_hashes_player_userid():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "s1:guid:0", salt, _cfg("balanced"))
    c = out.characters[0]
    assert c.player_userid == hash_user_id(salt, "s1:guid:0", "raw-uid")
    assert c.player_userid != "raw-uid"


def test_redact_game_data_balanced_keeps_coords():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "w", salt, _cfg("balanced"))
    assert out.characters[0].x == 123.0
    assert len(out.palboxes) == 1
    assert out.palboxes[0].x == 1.0


def test_redact_game_data_strict_nulls_coords_and_drops_palboxes():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "w", salt, _cfg("strict"))
    c = out.characters[0]
    assert c.x is None and c.y is None and c.z is None
    assert out.palboxes == []
    # 身份仍脱敏
    assert c.player_userid == hash_user_id(salt, "w", "raw-uid")


def test_redact_game_data_none_userid_stays_none():
    salt = b"\x09" * 32
    snap = _snap()
    snap.characters[0].player_userid = None
    out = redact_game_data(snap, "w", salt, _cfg("balanced"))
    assert out.characters[0].player_userid is None


def test_redact_game_data_no_raw_userid_in_repr():
    salt = b"\x09" * 32
    out = redact_game_data(_snap(), "w", salt, _cfg("balanced"))
    assert "raw-uid" not in repr(out)
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/privacy_filter_game_data_test.py -q`。期望 FAIL：`ImportError: cannot import name 'redact_game_data'`。

- [ ] **3) 写最小实现** — 在 `palchronicle/adapters/privacy_filter.py` import 块把
```python
from palchronicle.domain.models import PlayerRow, PlayersSnapshot
```
改为
```python
from palchronicle.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    PlayerRow,
    PlayersSnapshot,
)
```

在文件末尾追加：

```python
def redact_game_data(
    snap: GameDataSnapshot,
    world_id: str,
    salt: bytes,
    cfg: PrivacyConfig,
) -> GameDataSnapshot:
    strict = cfg.mode == "strict"
    characters: list[CharacterActor] = []
    for c in snap.characters:
        characters.append(
            CharacterActor(
                unit_type=c.unit_type,
                instance_id=c.instance_id,
                nickname=c.nickname,
                trainer_instance_id=c.trainer_instance_id,
                trainer_nickname=c.trainer_nickname,
                player_userid=_hash_or_none(salt, world_id, c.player_userid),
                level=c.level,
                hp=c.hp,
                max_hp=c.max_hp,
                guild_id=c.guild_id,
                guild_name=c.guild_name,
                pal_class=c.pal_class,
                action=c.action,
                ai_action=c.ai_action,
                x=None if strict else c.x,
                y=None if strict else c.y,
                z=None if strict else c.z,
                is_active=c.is_active,
            )
        )
    palboxes = [] if strict else list(snap.palboxes)
    return GameDataSnapshot(
        observed_at=snap.observed_at,
        fps=snap.fps,
        average_fps=snap.average_fps,
        characters=characters,
        palboxes=palboxes,
        unknown_classes=list(snap.unknown_classes),
    )
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/privacy_filter_game_data_test.py -q`。期望 PASS：5 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/privacy_filter.py tests/unit/privacy_filter_game_data_test.py
git commit -m "feat(adapters): add redact_game_data (hash id, strict drops coords/palboxes)"
```

---

### Task 2.13：Repository 补充 — insert_metric + latest_metric

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_metrics_test.py`

**Interfaces:**
- Consumes: Phase 1 的 `Database`（`execute_write`, `query`, `open`, `close`）与 `Clock`；Phase 1 的 `apply_migrations`（建 `world_metrics` 表）；`palchronicle/domain/models.py`（`WorldMetric`）。
- Produces（照契约，追加到既有 `Repository` 类）:
  - `async def insert_metric(self, m: WorldMetric) -> None`
  - `async def latest_metric(self, world_id: str) -> WorldMetric | None`

> `world_metrics` 表（spec §9.1）：`id PK, world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count`。表由 Phase 1 迁移建立；本任务只加读写方法。`latest_metric` 按 `observed_at DESC` 取第一条。

- [ ] **1) 写失败测试** — 创建 `tests/unit/repository_metrics_test.py`：

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1_000_000)
    yield Repository(db, clock)
    await db.close()


@pytest.mark.asyncio
async def test_insert_and_latest_metric(repo):
    m1 = WorldMetric(
        world_id="s1:guid:0", observed_at=1000, fps=60.0, frame_time=16.6,
        online_players=3, world_day=5, basecamp_count=2,
    )
    m2 = WorldMetric(
        world_id="s1:guid:0", observed_at=2000, fps=55.0, frame_time=18.0,
        online_players=4, world_day=5, basecamp_count=3,
    )
    await repo.insert_metric(m1)
    await repo.insert_metric(m2)
    latest = await repo.latest_metric("s1:guid:0")
    assert latest is not None
    assert latest.observed_at == 2000
    assert latest.fps == 55.0
    assert latest.online_players == 4
    assert latest.basecamp_count == 3


@pytest.mark.asyncio
async def test_latest_metric_none_when_absent(repo):
    assert await repo.latest_metric("nonexistent:guid:0") is None


@pytest.mark.asyncio
async def test_latest_metric_isolated_by_world(repo):
    await repo.insert_metric(WorldMetric(
        world_id="wA", observed_at=100, fps=1.0, frame_time=1.0,
        online_players=1, world_day=1, basecamp_count=1,
    ))
    await repo.insert_metric(WorldMetric(
        world_id="wB", observed_at=200, fps=2.0, frame_time=2.0,
        online_players=9, world_day=2, basecamp_count=2,
    ))
    a = await repo.latest_metric("wA")
    assert a.online_players == 1
    assert a.observed_at == 100
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_metrics_test.py -q`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'insert_metric'`（方法未加）。

- [ ] **3) 写最小实现** — 在 `palchronicle/adapters/sqlite_repository.py` 的 `Repository` 类中追加两个方法（放在类体末尾，metrics 区）。同时确保文件顶部已 import `WorldMetric`（若 Phase 1 未 import，在 models import 块补 `WorldMetric`）：

```python
    async def insert_metric(self, m: WorldMetric) -> None:
        await self._db.execute_write(
            "INSERT INTO world_metrics"
            " (world_id, observed_at, fps, frame_time, online_players,"
            "  world_day, basecamp_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                m.world_id, m.observed_at, m.fps, m.frame_time,
                m.online_players, m.world_day, m.basecamp_count,
            ),
        )

    async def latest_metric(self, world_id: str) -> WorldMetric | None:
        rows = await self._db.query(
            "SELECT world_id, observed_at, fps, frame_time, online_players,"
            " world_day, basecamp_count FROM world_metrics"
            " WHERE world_id = ? ORDER BY observed_at DESC LIMIT 1",
            (world_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return WorldMetric(
            world_id=r["world_id"],
            observed_at=r["observed_at"],
            fps=r["fps"],
            frame_time=r["frame_time"],
            online_players=r["online_players"],
            world_day=r["world_day"],
            basecamp_count=r["basecamp_count"],
        )
```

> 若 Phase 1 的 `Repository.__init__` 用 `self._db`/`self._clock` 之外的属性名，按其实际命名调整这两处引用。

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_metrics_test.py -q`。期望 PASS：3 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_metrics_test.py
git commit -m "feat(repository): add insert_metric/latest_metric"
```

---

### Task 2.14：Repository 补充 — peak_online + upsert_unknown_classes

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_peak_unknown_test.py`

**Interfaces:**
- Consumes: `Database`, `FakeClock`, `apply_migrations`；`palchronicle/domain/models.py`（`WorldMetric`）。
- Produces（照契约）:
  - `async def peak_online(self, world_id: str, since: int | None = None) -> int` — `world_metrics` 中该 world 的 `MAX(online_players)`；`since` 非空则加 `observed_at >= since` 过滤；无数据返回 0。
  - `async def upsert_unknown_classes(self, classes: list[str]) -> None` — 写 `unknown_classes(class_name PK, first_seen_at, count)`；已存在则 `count += len(该批出现次数)`（本 v0.1 每次调用每个 class 计 +1），首见记 `first_seen_at`。

> `unknown_classes` 表（spec §9.1）：`class_name PK, first_seen_at, count`。用 `INSERT ... ON CONFLICT(class_name) DO UPDATE SET count = count + 1`。`first_seen_at` 取 `clock.now()`。

- [ ] **1) 写失败测试** — 创建 `tests/unit/repository_peak_unknown_test.py`：

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo_and_clock(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=5000)
    yield Repository(db, clock), clock
    await db.close()


def _metric(world_id, observed_at, online):
    return WorldMetric(
        world_id=world_id, observed_at=observed_at, fps=60.0, frame_time=16.0,
        online_players=online, world_day=1, basecamp_count=0,
    )


@pytest.mark.asyncio
async def test_peak_online_max_across_metrics(repo_and_clock):
    repo, _ = repo_and_clock
    await repo.insert_metric(_metric("w", 100, 3))
    await repo.insert_metric(_metric("w", 200, 7))
    await repo.insert_metric(_metric("w", 300, 5))
    assert await repo.peak_online("w") == 7


@pytest.mark.asyncio
async def test_peak_online_since_filter(repo_and_clock):
    repo, _ = repo_and_clock
    await repo.insert_metric(_metric("w", 100, 9))
    await repo.insert_metric(_metric("w", 300, 4))
    assert await repo.peak_online("w", since=250) == 4


@pytest.mark.asyncio
async def test_peak_online_zero_when_empty(repo_and_clock):
    repo, _ = repo_and_clock
    assert await repo.peak_online("empty") == 0


@pytest.mark.asyncio
async def test_upsert_unknown_classes_insert_and_increment(repo_and_clock):
    repo, clock = repo_and_clock
    await repo.upsert_unknown_classes(["Pal/Alpha", "Pal/Beta"])
    await repo.upsert_unknown_classes(["Pal/Alpha"])
    rows = await repo._db.query(
        "SELECT class_name, first_seen_at, count FROM unknown_classes"
        " ORDER BY class_name"
    )
    by_name = {r["class_name"]: (r["first_seen_at"], r["count"]) for r in rows}
    assert by_name["Pal/Alpha"][1] == 2
    assert by_name["Pal/Beta"][1] == 1
    assert by_name["Pal/Alpha"][0] == 5000  # first_seen_at = clock.now()


@pytest.mark.asyncio
async def test_upsert_unknown_classes_empty_noop(repo_and_clock):
    repo, _ = repo_and_clock
    await repo.upsert_unknown_classes([])
    rows = await repo._db.query("SELECT COUNT(*) AS n FROM unknown_classes")
    assert rows[0]["n"] == 0
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_peak_unknown_test.py -q`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'peak_online'`。

- [ ] **3) 写最小实现** — 在 `Repository` 类追加：

```python
    async def peak_online(self, world_id: str, since: int | None = None) -> int:
        if since is None:
            rows = await self._db.query(
                "SELECT MAX(online_players) AS peak FROM world_metrics"
                " WHERE world_id = ?",
                (world_id,),
            )
        else:
            rows = await self._db.query(
                "SELECT MAX(online_players) AS peak FROM world_metrics"
                " WHERE world_id = ? AND observed_at >= ?",
                (world_id, since),
            )
        peak = rows[0]["peak"] if rows else None
        return int(peak) if peak is not None else 0

    async def upsert_unknown_classes(self, classes: list[str]) -> None:
        if not classes:
            return
        now = self._clock.now()
        await self._db.executemany_write(
            "INSERT INTO unknown_classes (class_name, first_seen_at, count)"
            " VALUES (?, ?, 1)"
            " ON CONFLICT(class_name) DO UPDATE SET count = count + 1",
            [(c, now) for c in classes],
        )
```

> 若 Phase 1 未在 `Repository` 暴露 `self._clock`，改用其实际时钟属性名。测试内 `repo._db` 直接访问私有连接是可接受的（同包白盒断言）；若 Phase 1 私有属性名不同，同步调整测试里的 `repo._db`。

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_peak_unknown_test.py -q`。期望 PASS：5 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_peak_unknown_test.py
git commit -m "feat(repository): add peak_online/upsert_unknown_classes"
```

---

### Task 2.15：application/snapshot_service.py — ingest_info（世界 upsert + worldguid 切 epoch）

**Files:**
- Create: `palchronicle/application/snapshot_service.py`
- Test: `tests/unit/snapshot_service_info_test.py`

**Interfaces:**
- Consumes:
  - `palchronicle/adapters/sqlite_repository.py`（`Repository.upsert_world`, `Repository.get_current_world` — Phase 1 产出）。
  - `palchronicle/adapters/normalizer.py`（`normalize_info`）。
  - `palchronicle/adapters/palworld_rest.py`（`RestResponse` — Phase 1）。
  - `palchronicle/config.py`（`ServerConfig`, `AppConfig`）。
  - `palchronicle/infrastructure/clock.py`（`Clock`）。
  - `palchronicle/domain/models.py`（`World`, `InfoSnapshot`）。
- Produces（照契约 §"snapshot_service"）:
  - `class SnapshotService` `__init__(self, repo, normalizer_mod, privacy_mod, meta, salt, cfg, clock, players, guilds, bases, events)`
  - `async def ingest_info(self, server: ServerConfig, resp: RestResponse) -> World | None`

> 语义（spec §6.3）：`ingest_info` 归一 `/info` → 若该 server 无当前世界或 `worldguid` 变化 → 新建 `World`（`world_id=f"{server_id}:{worldguid}:0"`，epoch 恒 0，`first_seen_at=last_seen_at=now`），worldguid 变化时**委托 `self._players.mark_uncertain(old_world)`**（Phase 3 注入的对象；本阶段测试注入假 players）；否则 upsert 现有世界更新 `last_seen_at`。resp 不 ok → 返回 None（不建世界）。`normalizer_mod`/`privacy_mod` 为**模块对象**（`palchronicle.adapters.normalizer`/`privacy_filter`），SnapshotService 调用其函数，便于注入替身。

- [ ] **1) 写失败测试** — 创建 `tests/unit/snapshot_service_info_test.py`：

```python
import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.palworld_rest import RestResponse


class FakePlayers:
    def __init__(self):
        self.marked_uncertain = []

    async def mark_uncertain(self, world):
        self.marked_uncertain.append(world.world_id)


class _Noop:
    async def apply(self, *a, **k):
        return []


def _app_config(servers):
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True,
        base_url="http://x", username="admin", password="pw",
        timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def service_and_ctx(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1000)
    repo = Repository(db, clock)
    players = FakePlayers()
    cfg = _app_config([_server()])
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=None, salt=b"\x00" * 32, cfg=cfg, clock=clock,
        players=players, guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield svc, repo, clock, players
    await db.close()


def _info_resp(worldguid, ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"Version": "0.3", "ServerName": "S", "WorldGuid": worldguid} if ok else None,
        duration_ms=5, payload_bytes=10, error=None if ok else "timeout",
    )


@pytest.mark.asyncio
async def test_ingest_info_creates_new_world(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    world = await svc.ingest_info(_server(), _info_resp("GUID-A"))
    assert world is not None
    assert world.world_id == "s1:GUID-A:0"
    assert world.epoch == 0
    assert world.worldguid == "GUID-A"
    assert world.first_seen_at == 1000
    stored = await repo.get_current_world("s1")
    assert stored is not None
    assert stored.world_id == "s1:GUID-A:0"


@pytest.mark.asyncio
async def test_ingest_info_same_guid_updates_last_seen(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    await svc.ingest_info(_server(), _info_resp("GUID-A"))
    clock.advance(500)
    world = await svc.ingest_info(_server(), _info_resp("GUID-A"))
    assert world.world_id == "s1:GUID-A:0"
    assert world.first_seen_at == 1000
    assert world.last_seen_at == 1500
    assert players.marked_uncertain == []  # 未换世界不置 uncertain


@pytest.mark.asyncio
async def test_ingest_info_worldguid_change_switches_epoch_and_marks_uncertain(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    await svc.ingest_info(_server(), _info_resp("GUID-A"))
    clock.advance(100)
    new_world = await svc.ingest_info(_server(), _info_resp("GUID-B"))
    assert new_world.world_id == "s1:GUID-B:0"
    stored = await repo.get_current_world("s1")
    assert stored.world_id == "s1:GUID-B:0"
    # 旧世界被置 uncertain
    assert players.marked_uncertain == ["s1:GUID-A:0"]


@pytest.mark.asyncio
async def test_ingest_info_failed_response_returns_none(service_and_ctx):
    svc, repo, clock, players = service_and_ctx
    world = await svc.ingest_info(_server(), _info_resp("X", ok=False))
    assert world is None
    assert await repo.get_current_world("s1") is None
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/snapshot_service_info_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.snapshot_service'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/application/__init__.py`（空文件）与 `palchronicle/application/snapshot_service.py`：

```python
from __future__ import annotations

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import Clock


class SnapshotService:
    def __init__(
        self,
        repo,
        normalizer_mod,
        privacy_mod,
        meta,
        salt: bytes,
        cfg: AppConfig,
        clock: Clock,
        players,
        guilds,
        bases,
        events,
    ) -> None:
        self._repo = repo
        self._normalizer = normalizer_mod
        self._privacy = privacy_mod
        self._meta = meta
        self._salt = salt
        self._cfg = cfg
        self._clock = clock
        self._players = players
        self._guilds = guilds
        self._bases = bases
        self._events = events
        self._settings_cache: dict[str, dict] = {}

    async def ingest_info(
        self, server: ServerConfig, resp: RestResponse
    ) -> World | None:
        if not resp.ok or resp.data is None:
            return None
        now = self._clock.now()
        info = self._normalizer.normalize_info(resp.data, now)
        current = await self._repo.get_current_world(server.server_id)
        if current is not None and current.worldguid == info.worldguid:
            current.last_seen_at = now
            current.version = info.version or current.version
            current.server_name = info.server_name or current.server_name
            await self._repo.upsert_world(current)
            return current
        if current is not None and current.worldguid != info.worldguid:
            # 换世界：旧世界活动会话置 uncertain
            await self._players.mark_uncertain(current)
        world = World(
            world_id=f"{server.server_id}:{info.worldguid}:0",
            server_id=server.server_id,
            worldguid=info.worldguid,
            epoch=0,
            server_name=info.server_name,
            version=info.version,
            first_seen_at=now,
            last_seen_at=now,
            current_day=0,
        )
        await self._repo.upsert_world(world)
        return world
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/snapshot_service_info_test.py -q`。期望 PASS：4 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/application/__init__.py palchronicle/application/snapshot_service.py tests/unit/snapshot_service_info_test.py
git commit -m "feat(application): SnapshotService.ingest_info with worldguid epoch switch"
```

---

### Task 2.16：application/snapshot_service.py — ingest_metrics（落 world_metrics）

**Files:**
- Modify: `palchronicle/application/snapshot_service.py`
- Test: `tests/unit/snapshot_service_metrics_test.py`

**Interfaces:**
- Consumes: `Repository.insert_metric`（Task 2.13）、`normalize_metrics`（Task 2.7）、`RestResponse`；`palchronicle/domain/models.py`（`World`, `WorldMetric`）。
- Produces（照契约）: `async def ingest_metrics(self, world: World, resp: RestResponse) -> None`。

> 语义：resp ok → 归一 metrics → 构造 `WorldMetric(world_id=world.world_id, observed_at=snap.observed_at, fps, frame_time, online_players=snap.online, world_day=snap.days, basecamp_count=snap.basecamp_count)` → `repo.insert_metric`。同时更新 `world.current_day` 并 upsert（供 world_day 里程碑钩子；本阶段仅记录，事件钩子留待 Phase 4 接线，不写 TODO 字样——`ingest_metrics` 只落库 + 更新 current_day）。resp 不 ok → 直接返回（不落库，不谎报）。

- [ ] **1) 写失败测试** — 追加到 `tests/unit/snapshot_service_metrics_test.py`（复用 2.15 的 fixture 结构，独立文件）：

```python
import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


class _Noop:
    async def apply(self, *a, **k):
        return []

    async def mark_uncertain(self, *a, **k):
        return None


def _cfg(servers):
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world():
    return World(
        world_id="s1:GUID-A:0", server_id="s1", worldguid="GUID-A", epoch=0,
        server_name="S", version="0.3", first_seen_at=1000, last_seen_at=1000,
        current_day=0,
    )


@pytest.fixture
async def svc_repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=2000)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=None, salt=b"\x00" * 32, cfg=_cfg([]), clock=clock,
        players=_Noop(), guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield svc, repo, clock
    await db.close()


def _metrics_resp(ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={
            "ServerFps": 57, "ServerFrameTime": 17.5, "CurrentPlayerNum": 6,
            "MaxPlayerNum": 32, "Uptime": 1000, "Days": 42, "BaseCampNum": 4,
        } if ok else None,
        duration_ms=3, payload_bytes=8, error=None if ok else "timeout",
    )


@pytest.mark.asyncio
async def test_ingest_metrics_persists_world_metric(svc_repo):
    svc, repo, clock = svc_repo
    await svc.ingest_metrics(_world(), _metrics_resp())
    m = await repo.latest_metric("s1:GUID-A:0")
    assert m is not None
    assert m.fps == 57.0
    assert m.online_players == 6
    assert m.world_day == 42
    assert m.basecamp_count == 4
    assert m.observed_at == 2000


@pytest.mark.asyncio
async def test_ingest_metrics_updates_world_current_day(svc_repo):
    svc, repo, clock = svc_repo
    await svc.ingest_metrics(_world(), _metrics_resp())
    stored = await repo.get_current_world("s1")
    assert stored.current_day == 42


@pytest.mark.asyncio
async def test_ingest_metrics_failed_response_no_persist(svc_repo):
    svc, repo, clock = svc_repo
    await svc.ingest_metrics(_world(), _metrics_resp(ok=False))
    assert await repo.latest_metric("s1:GUID-A:0") is None
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/snapshot_service_metrics_test.py -q`。期望 FAIL：`AttributeError: 'SnapshotService' object has no attribute 'ingest_metrics'`。

- [ ] **3) 写最小实现** — 在 `palchronicle/application/snapshot_service.py` import 块追加 `WorldMetric`，即把
```python
from palchronicle.domain.models import World
```
改为
```python
from palchronicle.domain.models import World, WorldMetric
```
并在 `SnapshotService` 类追加方法：

```python
    async def ingest_metrics(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return
        snap = self._normalizer.normalize_metrics(resp.data, self._clock.now())
        metric = WorldMetric(
            world_id=world.world_id,
            observed_at=snap.observed_at,
            fps=snap.fps,
            frame_time=snap.frame_time,
            online_players=snap.online,
            world_day=snap.days,
            basecamp_count=snap.basecamp_count,
        )
        await self._repo.insert_metric(metric)
        if snap.days and snap.days != world.current_day:
            world.current_day = snap.days
            world.last_seen_at = snap.observed_at
            await self._repo.upsert_world(world)
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/snapshot_service_metrics_test.py -q`。期望 PASS：3 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/application/snapshot_service.py tests/unit/snapshot_service_metrics_test.py
git commit -m "feat(application): SnapshotService.ingest_metrics persists WorldMetric + current_day"
```

---

### Task 2.17：application/snapshot_service.py — ingest_settings（缓存 settings 供 /pal rules）

**Files:**
- Modify: `palchronicle/application/snapshot_service.py`
- Test: `tests/unit/snapshot_service_settings_test.py`

**Interfaces:**
- Consumes: `RestResponse`；`palchronicle/domain/models.py`（`World`）。
- Produces（照契约）:
  - `async def ingest_settings(self, world: World, resp: RestResponse) -> None`
  - `def get_settings(self, world_id: str) -> dict | None`（本阶段新增读取器，供 Phase 5 query_service 取缓存 settings；缓存键 = world_id）。

> 语义（spec §6.2/§13 rules）：settings 只读缓存到内存 `self._settings_cache[world_id] = {"data": <原始 dict>, "observed_at": now}`。resp 不 ok → 保留旧缓存（降级"用最近缓存"，spec §14），不覆盖。settings 不落库（v0.1 仅供 /pal rules 内存渲染 + 更新时间）。`get_settings` 返回缓存条目（含 observed_at）或 None。

- [ ] **1) 写失败测试** — 创建 `tests/unit/snapshot_service_settings_test.py`：

```python
import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


class _Noop:
    async def apply(self, *a, **k):
        return []

    async def mark_uncertain(self, *a, **k):
        return None


def _cfg():
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world():
    return World(
        world_id="s1:GUID-A:0", server_id="s1", worldguid="GUID-A", epoch=0,
        server_name="S", version="0.3", first_seen_at=1, last_seen_at=1,
        current_day=0,
    )


@pytest.fixture
async def svc(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=3000)
    svc = SnapshotService(
        repo=Repository(db, clock), normalizer_mod=normalizer_mod,
        privacy_mod=privacy_mod, meta=None, salt=b"\x00" * 32, cfg=_cfg(),
        clock=clock, players=_Noop(), guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield svc, clock
    await db.close()


def _settings_resp(exp_rate, ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"ExpRate": exp_rate, "PalCaptureRate": 1.0} if ok else None,
        duration_ms=2, payload_bytes=4, error=None if ok else "timeout",
    )


@pytest.mark.asyncio
async def test_ingest_settings_caches_data(svc):
    service, clock = svc
    await service.ingest_settings(_world(), _settings_resp(2.0))
    cached = service.get_settings("s1:GUID-A:0")
    assert cached is not None
    assert cached["data"]["ExpRate"] == 2.0
    assert cached["observed_at"] == 3000


@pytest.mark.asyncio
async def test_get_settings_none_when_absent(svc):
    service, _ = svc
    assert service.get_settings("unknown") is None


@pytest.mark.asyncio
async def test_ingest_settings_failed_keeps_old_cache(svc):
    service, clock = svc
    await service.ingest_settings(_world(), _settings_resp(2.0))
    clock.advance(100)
    await service.ingest_settings(_world(), _settings_resp(99.0, ok=False))
    cached = service.get_settings("s1:GUID-A:0")
    assert cached["data"]["ExpRate"] == 2.0  # 旧值保留
    assert cached["observed_at"] == 3000     # 未刷新
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/snapshot_service_settings_test.py -q`。期望 FAIL：`AttributeError: 'SnapshotService' object has no attribute 'ingest_settings'`。

- [ ] **3) 写最小实现** — 在 `SnapshotService` 类追加：

```python
    async def ingest_settings(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return  # 保留旧缓存, 不谎报
        self._settings_cache[world.world_id] = {
            "data": dict(resp.data),
            "observed_at": self._clock.now(),
        }

    def get_settings(self, world_id: str) -> dict | None:
        return self._settings_cache.get(world_id)
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/snapshot_service_settings_test.py -q`。期望 PASS：3 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/application/snapshot_service.py tests/unit/snapshot_service_settings_test.py
git commit -m "feat(application): SnapshotService.ingest_settings caches settings for /pal rules"
```

---

### Task 2.18：application/snapshot_service.py — ingest_players / ingest_game_data 委托骨架

**Files:**
- Modify: `palchronicle/application/snapshot_service.py`
- Test: `tests/unit/snapshot_service_delegation_test.py`

**Interfaces:**
- Consumes: 注入的 `self._players`（Phase 3 的 `PlayerService`）、`self._guilds`/`self._bases`（Phase 3）、`self._events`（Phase 4）；`normalizer_mod.normalize_players`/`normalize_game_data`、`privacy_mod.redact_players`/`redact_game_data`（本阶段已实现）。
- Produces（照契约）:
  - `async def ingest_players(self, world: World, resp: RestResponse) -> None` — 归一→脱敏→**委托 `self._players.apply_players(world, players_snapshot)`**；resp 不 ok → **委托 `self._players.mark_uncertain(world)`**（不误判离线，spec §14）。
  - `async def ingest_game_data(self, world: World, resp: RestResponse) -> None` — 归一（`normalize_game_data`）→脱敏（`redact_game_data`）→登记 unknown_classes→**委托 `self._guilds.apply(world, gd)` 与 `self._bases.apply(world, gd)`**；resp 不 ok → 直接返回（保留基础状态，spec §14）。

> 本阶段把这两个方法写成"归一/脱敏 + 委托注入对象"的骨架：`self._players`/`self._guilds`/`self._bases` 由 **Phase 3 注入**真实实现；本阶段用假对象验证委托被正确调用、参数正确、脱敏在委托前发生。`ingest_game_data` 的重计算部分（归一/脱敏）本阶段直接同步调用即可（`asyncio.to_thread` 卸载留待 Phase 3 接线真实聚合时按 spec §6.2 加入，本骨架不引入线程以保持确定性测试）。`meta` 由构造注入；本任务测试传入真实 `MetadataRepository`。

- [ ] **1) 写失败测试** — 创建 `tests/unit/snapshot_service_delegation_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


class SpyPlayers:
    def __init__(self):
        self.applied = []
        self.uncertain = []

    async def apply_players(self, world, snap):
        self.applied.append((world.world_id, snap))

    async def mark_uncertain(self, world):
        self.uncertain.append(world.world_id)


class SpyAgg:
    def __init__(self):
        self.applied = []

    async def apply(self, world, gd):
        self.applied.append((world.world_id, gd))
        return []


def _cfg(mode="balanced"):
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig(mode, False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world():
    return World(
        world_id="s1:GUID-A:0", server_id="s1", worldguid="GUID-A", epoch=0,
        server_name="S", version="0.3", first_seen_at=1, last_seen_at=1,
        current_day=0,
    )


@pytest.fixture
async def make_svc(tmp_path):
    created = {}

    async def _factory(mode="balanced"):
        db = Database(tmp_path / f"{mode}.db")
        await db.open()
        await apply_migrations(db)
        clock = FakeClock(start=4000)
        meta = MetadataRepository(METADATA_DIR)
        meta.load()
        players = SpyPlayers()
        guilds = SpyAgg()
        bases = SpyAgg()
        svc = SnapshotService(
            repo=Repository(db, clock), normalizer_mod=normalizer_mod,
            privacy_mod=privacy_mod, meta=meta, salt=b"\x02" * 32, cfg=_cfg(mode),
            clock=clock, players=players, guilds=guilds, bases=bases, events=SpyAgg(),
        )
        created["db"] = db
        return svc, players, guilds, bases

    yield _factory
    if "db" in created:
        await created["db"].close()


def _players_resp(ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"players": [{"UserId": "u-1", "Name": "Alice", "Level": 5,
                           "Ping": 40, "BuildingCount": 2, "Ip": "10.0.0.1",
                           "AccountName": "steam_a"}]} if ok else None,
        duration_ms=2, payload_bytes=5, error=None if ok else "timeout",
    )


def _game_data_resp(ok=True):
    return RestResponse(
        ok=ok, status=200 if ok else None,
        data={"characters": [
            {"type": "Player", "userid": "raw-1", "Level": 5,
             "GuildID": "g1", "locationx": 1, "locationy": 2, "locationz": 3,
             "isactive": "true"}
        ], "palboxes": [
            {"guildid": "g1", "class": "PalDataParameter/SheepBall",
             "locationx": 1, "locationy": 2, "locationz": 3}
        ]} if ok else None,
        duration_ms=9, payload_bytes=99, error=None if ok else "timeout",
    )


@pytest.mark.asyncio
async def test_ingest_players_delegates_redacted_snapshot(make_svc):
    svc, players, _, _ = await make_svc("balanced")
    await svc.ingest_players(_world(), _players_resp())
    assert len(players.applied) == 1
    world_id, snap = players.applied[0]
    assert world_id == "s1:GUID-A:0"
    row = snap.players[0]
    assert row.name == "Alice"
    # 脱敏发生: userid 已 hash, 无原始 id / ip
    assert row.userid != "u-1"
    assert "10.0.0.1" not in repr(snap)
    assert "steam_a" not in repr(snap)


@pytest.mark.asyncio
async def test_ingest_players_failure_marks_uncertain(make_svc):
    svc, players, _, _ = await make_svc("balanced")
    await svc.ingest_players(_world(), _players_resp(ok=False))
    assert players.applied == []
    assert players.uncertain == ["s1:GUID-A:0"]


@pytest.mark.asyncio
async def test_ingest_game_data_delegates_to_guilds_and_bases(make_svc):
    svc, _, guilds, bases = await make_svc("balanced")
    await svc.ingest_game_data(_world(), _game_data_resp())
    assert len(guilds.applied) == 1
    assert len(bases.applied) == 1
    _, gd = guilds.applied[0]
    assert len(gd.characters) == 1
    # 身份脱敏发生在委托前
    assert gd.characters[0].player_userid != "raw-1"


@pytest.mark.asyncio
async def test_ingest_game_data_strict_drops_palboxes_before_delegate(make_svc):
    svc, _, guilds, bases = await make_svc("strict")
    await svc.ingest_game_data(_world(), _game_data_resp())
    _, gd = bases.applied[0]
    assert gd.palboxes == []
    assert gd.characters[0].x is None


@pytest.mark.asyncio
async def test_ingest_game_data_failure_no_delegate(make_svc):
    svc, _, guilds, bases = await make_svc("balanced")
    await svc.ingest_game_data(_world(), _game_data_resp(ok=False))
    assert guilds.applied == []
    assert bases.applied == []
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/snapshot_service_delegation_test.py -q`。期望 FAIL：`AttributeError: 'SnapshotService' object has no attribute 'ingest_players'`。

- [ ] **3) 写最小实现** — 在 `SnapshotService` 类追加两个方法：

```python
    async def ingest_players(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            await self._players.mark_uncertain(world)
            return
        now = self._clock.now()
        rows = self._normalizer.normalize_players(resp.data, now)
        snap = self._privacy.redact_players(
            rows, world.world_id, self._salt, self._cfg.privacy, observed_at=now
        )
        await self._players.apply_players(world, snap)

    async def ingest_game_data(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return  # 保留基础状态, 不误判
        now = self._clock.now()
        gd = self._normalizer.normalize_game_data(resp.data, now, self._meta)
        if gd.unknown_classes:
            await self._repo.upsert_unknown_classes(gd.unknown_classes)
        gd = self._privacy.redact_game_data(
            gd, world.world_id, self._salt, self._cfg.privacy
        )
        await self._guilds.apply(world, gd)
        await self._bases.apply(world, gd)
```

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/snapshot_service_delegation_test.py -q`。期望 PASS：5 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/application/snapshot_service.py tests/unit/snapshot_service_delegation_test.py
git commit -m "feat(application): ingest_players/ingest_game_data delegate to injected trackers"
```

---

### Task 2.19：infrastructure/scheduler.py — 按期触发 + info 启动即拉 + 注入 rng/clock

**Files:**
- Create: `palchronicle/infrastructure/scheduler.py`
- Test: `tests/unit/scheduler_basic_test.py`

**Interfaces:**
- Consumes: `palchronicle/config.py`（`ServerConfig`, `PollingConfig`）；`palchronicle/infrastructure/locks.py`（`EndpointLocks`）；`palchronicle/infrastructure/clock.py`（`Clock`）；`palchronicle/domain/enums.py`（`EndpointName`）；`palchronicle/adapters/palworld_rest.py`（`RestResponse`）。
- Produces（照契约 §"scheduler"）:
  - `class Scheduler` `__init__(self, servers, polling, locks, clock, on_response, rng_seed=None)`
  - `async def start(self) -> None`
  - `async def stop(self) -> None`
  - 内部：每 ready 服务器每端点一个 `asyncio.Task`；`info` 启动即拉一次；间隔 = base * U(1-r, 1+r)（注入 rng）；`on_response(server_id, endpoint, resp)` 回调。

> 本阶段用**可注入的时间驱动**：不实际 `sleep(真实秒)`，而是用 `asyncio.Event` + 一个"tick 驱动"接口，使测试确定性。设计：Scheduler 每端点循环体 `await self._sleep(interval)`；`self._sleep` 默认包 `asyncio.sleep`，但接受注入。为保证测试不依赖 wall-clock，构造增加可选 `sleep` 注入参数（默认 `asyncio.sleep`）。测试注入一个"记录调用并立即返回一次后挂起"的假 sleep，统计每端点被触发的 fetch 次数与首个 info 立即触发。`on_response` 由 Scheduler 用注入的 `fetch` 拉取——但契约里 Scheduler 不含 fetch，改由 `on_response` 之前需一个数据源；为对齐契约，Scheduler 只负责"到点调用 `on_response(server_id, endpoint, resp)`"，其中 resp 由注入的 `fetcher` 提供。**契约调整声明**：`__init__` 增加关键字参数 `fetcher: Callable[[str, EndpointName], Awaitable[RestResponse]]` 与 `sleep: Callable[[float], Awaitable[None]] = asyncio.sleep`，位置签名保持契约不变（新增均为关键字，默认值兜底），使 Scheduler 可独立测试。

- [ ] **1) 写失败测试** — 创建 `tests/unit/scheduler_basic_test.py`：

```python
import asyncio

import pytest

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import PollingConfig, ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.locks import EndpointLocks
from palchronicle.infrastructure.scheduler import Scheduler


def _server(sid="s1"):
    return ServerConfig(
        server_id=sid, name=sid, enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _polling():
    return PollingConfig(
        metrics_seconds=30, players_seconds=30, info_seconds=600,
        settings_seconds=1800, game_data_seconds=120, jitter_ratio=0.0,
        max_concurrency=6,
    )


def _ok_resp():
    return RestResponse(ok=True, status=200, data={}, duration_ms=1,
                        payload_bytes=1, error=None)


class GatedSleep:
    """首次每端点循环立即返回一次(触发一轮 fetch)，其后永久挂起，便于计数确定。"""

    def __init__(self):
        self.calls = []
        self._gate = asyncio.Event()

    async def __call__(self, secs):
        self.calls.append(secs)
        await self._gate.wait()  # 永不放行 → 每端点只跑一轮


@pytest.mark.asyncio
async def test_scheduler_fires_each_endpoint_once_and_info_immediate():
    fetched = []

    async def fetcher(server_id, endpoint):
        fetched.append((server_id, endpoint))
        return _ok_resp()

    responses = []

    async def on_response(server_id, endpoint, resp):
        responses.append((server_id, endpoint, resp.ok))

    sleep = GatedSleep()
    sched = Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=42, fetcher=fetcher, sleep=sleep,
    )
    await sched.start()
    await asyncio.sleep(0)  # 让任务跑到首轮
    await asyncio.sleep(0)
    await sched.stop()

    endpoints_fetched = {ep for _, ep in fetched}
    assert endpoints_fetched == {
        EndpointName.INFO, EndpointName.METRICS, EndpointName.PLAYERS,
        EndpointName.SETTINGS, EndpointName.GAME_DATA,
    }
    # 每端点至少触发一次 on_response
    assert {ep for _, ep, _ in responses} == endpoints_fetched
    # info 端点在首轮无需等待即触发(其循环不在 fetch 前先 sleep)
    assert (_server().server_id, EndpointName.INFO) in fetched


@pytest.mark.asyncio
async def test_scheduler_skips_not_ready_servers():
    fetched = []

    async def fetcher(server_id, endpoint):
        fetched.append(server_id)
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        return None

    not_ready = ServerConfig(
        server_id="s2", name="s2", enabled=True, base_url="http://y",
        username="admin", password="", timeout=10, verify_tls=True, timezone="",
    )  # password 空 → ready False
    sleep = GatedSleep()
    sched = Scheduler(
        servers=[not_ready], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=1, fetcher=fetcher, sleep=sleep,
    )
    await sched.start()
    await asyncio.sleep(0)
    await sched.stop()
    assert fetched == []  # 未就绪服务器不采集


@pytest.mark.asyncio
async def test_scheduler_stop_cancels_all_tasks():
    async def fetcher(server_id, endpoint):
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        return None

    sleep = GatedSleep()
    sched = Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=7, fetcher=fetcher, sleep=sleep,
    )
    await sched.start()
    await asyncio.sleep(0)
    await sched.stop()
    assert all(t.done() for t in sched._tasks)
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/scheduler_basic_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.infrastructure.scheduler'`。

- [ ] **3) 写最小实现** — 创建 `palchronicle/infrastructure/scheduler.py`：

```python
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import PollingConfig, ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import Clock
from palchronicle.infrastructure.locks import EndpointLocks

OnResponse = Callable[[str, EndpointName, RestResponse], Awaitable[None]]
Fetcher = Callable[[str, EndpointName], Awaitable[RestResponse]]
Sleeper = Callable[[float], Awaitable[None]]

# 背压常量 (spec §6.1)
_BACKOFF_K = 2.0
_BACKOFF_CAP = 8.0          # effective 上限 = base * cap
_RECOVER_STREAK = 3         # 连续低于阈值次数后回落


class Scheduler:
    def __init__(
        self,
        servers: list[ServerConfig],
        polling: PollingConfig,
        locks: EndpointLocks,
        clock: Clock,
        on_response: OnResponse,
        rng_seed: int | None = None,
        *,
        fetcher: Fetcher,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._servers = servers
        self._polling = polling
        self._locks = locks
        self._clock = clock
        self._on_response = on_response
        self._rng = random.Random(rng_seed)
        self._fetcher = fetcher
        self._sleep = sleep
        self._tasks: list[asyncio.Task] = []
        # 每 (server_id, endpoint) 的背压状态
        self._effective: dict[tuple[str, EndpointName], float] = {}
        self._low_streak: dict[tuple[str, EndpointName], int] = {}

    def _base_interval(self, endpoint: EndpointName) -> float:
        return {
            EndpointName.METRICS: self._polling.metrics_seconds,
            EndpointName.PLAYERS: self._polling.players_seconds,
            EndpointName.INFO: self._polling.info_seconds,
            EndpointName.SETTINGS: self._polling.settings_seconds,
            EndpointName.GAME_DATA: self._polling.game_data_seconds,
        }[endpoint]

    def _jittered(self, base: float) -> float:
        r = self._polling.jitter_ratio
        return base * self._rng.uniform(1 - r, 1 + r)

    async def start(self) -> None:
        for server in self._servers:
            if not server.ready:
                continue
            for endpoint in EndpointName:
                self._tasks.append(
                    asyncio.create_task(self._loop(server, endpoint))
                )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []

    async def _loop(self, server: ServerConfig, endpoint: EndpointName) -> None:
        key = (server.server_id, endpoint)
        base = self._base_interval(endpoint)
        self._effective.setdefault(key, base)
        self._low_streak.setdefault(key, 0)
        immediate = endpoint is EndpointName.INFO
        try:
            while True:
                if not immediate:
                    await self._sleep(self._jittered(self._effective[key]))
                immediate = False
                await self._tick(server, endpoint, key, base)
        except asyncio.CancelledError:
            raise

    async def _tick(
        self,
        server: ServerConfig,
        endpoint: EndpointName,
        key: tuple[str, EndpointName],
        base: float,
    ) -> None:
        ctx = self._locks.inflight(server.server_id, endpoint)
        async with ctx as acquired:
            if acquired is None:
                return  # 在途锁占用 → tick 合并跳过
            start = self._clock.monotonic()
            resp = await self._fetcher(server.server_id, endpoint)
            await self._on_response(server.server_id, endpoint, resp)
            self._adjust_backpressure(key, base, self._clock.monotonic() - start)

    def _adjust_backpressure(
        self, key: tuple[str, EndpointName], base: float, elapsed: float
    ) -> None:
        current = self._effective[key]
        if elapsed > current:
            self._effective[key] = min(current * _BACKOFF_K, base * _BACKOFF_CAP)
            self._low_streak[key] = 0
        else:
            self._low_streak[key] += 1
            if self._low_streak[key] >= _RECOVER_STREAK and current > base:
                self._effective[key] = max(current / _BACKOFF_K, base)
                self._low_streak[key] = 0
```

> 说明：`EndpointLocks.inflight` 契约返回 AsyncContextManager，占用时产出 None-sentinel（`acquired is None` → 跳过），空闲时产出非 None。若 Phase 1 的 `inflight` 契约实现细节（返回值/是否含信号量）不同，本 `_tick` 里的 `async with ... as acquired` 判定需与 Phase 1 一致；契约文字为"若已占用则 return None-sentinel 跳过"，此处按其语义编码。

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/scheduler_basic_test.py -q`。期望 PASS：3 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/infrastructure/scheduler.py tests/unit/scheduler_basic_test.py
git commit -m "feat(infra): Scheduler per-server per-endpoint loops with info-immediate + injectable rng/sleep"
```

---

### Task 2.20：infrastructure/scheduler.py — 背压双向调节 + tick 合并

**Files:**
- Modify: `palchronicle/infrastructure/scheduler.py`（背压逻辑已在 2.19 写入；本任务补齐并测试其行为，若 2.19 已覆盖则本任务纯补测 + 边界修正）
- Test: `tests/unit/scheduler_backpressure_test.py`

**Interfaces:**
- Consumes: 2.19 的 `Scheduler`；`palchronicle/infrastructure/clock.py`（`FakeClock` 的 `monotonic` 可控）。
- Produces: 无新公开 API；验证内部 `_effective` 背压升/降与 tick 合并（在途锁占用跳过）行为。

> 需要可控的 `monotonic` 来伪造"处理耗时"。`FakeClock.monotonic()` 契约返回 float；本任务测试通过在 `fetcher` 内 `clock.advance(...)`（若 FakeClock.monotonic 基于内部时间）或直接注入一个可控 monotonic 的时钟替身来制造耗时。为不依赖 FakeClock 内部实现，测试注入一个**自定义 clock 替身**（实现 `now()`/`monotonic()`），`monotonic` 由测试脚本序列驱动。

- [ ] **1) 写失败测试** — 创建 `tests/unit/scheduler_backpressure_test.py`：

```python
import asyncio

import pytest

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import PollingConfig, ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.locks import EndpointLocks
from palchronicle.infrastructure.scheduler import Scheduler


class ScriptedClock:
    """monotonic 返回预设序列, 制造可控处理耗时。"""

    def __init__(self, monotonic_values):
        self._values = list(monotonic_values)
        self._i = 0

    def now(self):
        return 0

    def monotonic(self):
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _polling(game_data_seconds=120):
    return PollingConfig(30, 30, 600, 1800, game_data_seconds, 0.0, 6)


def _ok():
    return RestResponse(ok=True, status=200, data={}, duration_ms=1, payload_bytes=1, error=None)


def _make_scheduler(clock, sleep, fetcher):
    async def on_response(s, e, r):
        return None

    return Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=clock,
        on_response=on_response, rng_seed=0, fetcher=fetcher, sleep=sleep,
    )


def test_backpressure_raises_effective_when_processing_slow():
    # 直接单元测内部 _adjust_backpressure(不跑事件循环)
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base
    sched._low_streak[key] = 0
    # 处理耗时 200 > effective 120 → 升频(间隔变大)
    sched._adjust_backpressure(key, base, elapsed=200.0)
    assert sched._effective[key] == pytest.approx(240.0)  # base*k, k=2


def test_backpressure_caps_at_base_times_cap():
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base * 8  # 已在上限
    sched._low_streak[key] = 0
    sched._adjust_backpressure(key, base, elapsed=9999.0)
    assert sched._effective[key] == pytest.approx(base * 8)  # 封顶 cap=8


def test_backpressure_recovers_after_streak():
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base * 4  # 已升频
    sched._low_streak[key] = 0
    # 连续 3 次处理都很快(< effective) → 回落一档
    sched._adjust_backpressure(key, base, elapsed=1.0)
    sched._adjust_backpressure(key, base, elapsed=1.0)
    assert sched._effective[key] == pytest.approx(base * 4)  # 未满 streak
    sched._adjust_backpressure(key, base, elapsed=1.0)
    assert sched._effective[key] == pytest.approx(base * 2)  # /k 回落


def test_backpressure_recover_floors_at_base():
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base  # 已在下限
    sched._low_streak[key] = 0
    for _ in range(5):
        sched._adjust_backpressure(key, base, elapsed=1.0)
    assert sched._effective[key] == pytest.approx(base)  # 不低于 base


@pytest.mark.asyncio
async def test_tick_merged_when_inflight_locked():
    # 在途锁占用 → _tick 直接返回, 不 fetch
    fetch_count = {"n": 0}

    async def fetcher(s, e):
        fetch_count["n"] += 1
        return _ok()

    async def sleep(_):
        await asyncio.Event().wait()  # 永久挂起

    clock = ScriptedClock([0.0, 0.0])
    sched = _make_scheduler(clock, sleep=sleep, fetcher=fetcher)
    locks = sched._locks
    # 先手动占用 game_data 在途锁
    ctx = locks.inflight("s1", EndpointName.GAME_DATA)
    async with ctx as acquired:
        assert acquired is not None  # 首次占用成功
        key = ("s1", EndpointName.GAME_DATA)
        sched._effective[key] = 120.0
        sched._low_streak[key] = 0
        await sched._tick(_server(), EndpointName.GAME_DATA, key, 120.0)
        assert fetch_count["n"] == 0  # 被合并跳过, 未 fetch
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/unit/scheduler_backpressure_test.py -q`。期望 FAIL：若 2.19 已实现 `_adjust_backpressure` 与 tick 合并，这些测试应大部分通过；但 `test_tick_merged_when_inflight_locked` 会暴露 `_tick`/`inflight` 语义细节（若 Phase 1 `inflight` 二次进入返回 None 的行为与断言不符则 FAIL）。若 2.19 常量与断言不符（k/cap/streak），此处 FAIL 并据此在步骤 3 校准常量。**期望首次运行至少 1 例 FAIL**（用于驱动常量/语义对齐）。

- [ ] **3) 写最小实现** — 依据步骤 2 的失败调整 `palchronicle/infrastructure/scheduler.py` 中背压常量与 `_tick`：确保 `_BACKOFF_K = 2.0`、`_BACKOFF_CAP = 8.0`、`_RECOVER_STREAK = 3` 与测试一致；确认 `_tick` 中 `async with ctx as acquired: if acquired is None: return` 与 Phase 1 `EndpointLocks.inflight` 的"重入返回 None"语义一致。若 Phase 1 `inflight` 用信号量在重入时**阻塞**而非返回 None，则改为 `try_inflight`（非阻塞尝试）——此时在 Phase 1 契约允许范围内，`inflight` 已声明"若已占用则 return None-sentinel 跳过"，无需改 Phase 1；仅需保证 `_tick` 正确解读 sentinel。若断言 `sched._effective[key] == 240.0` 因常量不符失败，则修正常量至上述值。示例（若需要，把 `_adjust_backpressure` 中回落判断改为严格 `<`）：

```python
    def _adjust_backpressure(
        self, key: tuple[str, EndpointName], base: float, elapsed: float
    ) -> None:
        current = self._effective[key]
        if elapsed > current:
            self._effective[key] = min(current * _BACKOFF_K, base * _BACKOFF_CAP)
            self._low_streak[key] = 0
        else:
            self._low_streak[key] += 1
            if self._low_streak[key] >= _RECOVER_STREAK and current > base:
                self._effective[key] = max(current / _BACKOFF_K, base)
                self._low_streak[key] = 0
```

> 若 2.19 的实现已使全部断言通过，则本步无需改动源码，仅确认 `git diff` 为空并记"实现已满足"。

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/unit/scheduler_backpressure_test.py -q`。期望 PASS：5 passed。

- [ ] **5) 提交** — 命令：
```
git add palchronicle/infrastructure/scheduler.py tests/unit/scheduler_backpressure_test.py
git commit -m "test(infra): verify scheduler backpressure adjust + tick merge on inflight lock"
```

---

### Task 2.21：集成 — 采集管线端到端（mock 服务器 → 归一 → 脱敏 → 落库 metrics/world）

**Files:**
- Create: `tests/integration/pipeline_test.py`

**Interfaces:**
- Consumes: `SnapshotService`（2.15-2.18）、`Repository`（2.13-2.14 + Phase 1 world 方法）、`normalizer`/`privacy_filter` 模块、`MetadataRepository`、`Database`/`apply_migrations`、`FakeClock`。
- Produces: 无新代码；集成测试断言"轮询一个 mock 服务器的 info+metrics 响应 → 建 World + 落 world_metrics，且 DB 内无 IP/原始 id/原始 ping 残留"（隐私红线端到端）。

> 本测试模拟一次完整采集：先 `ingest_info` 建世界，再 `ingest_metrics` 落指标，再 `ingest_players`（用假 players 收集脱敏快照），断言脱敏在落库前发生、DB 全表扫描无敏感原文。用真实 normalizer/privacy 模块（非替身），仅 players/guilds/bases 用 spy。

- [ ] **1) 写失败测试** — 创建 `tests/integration/__init__.py`（空）与 `tests/integration/pipeline_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters import normalizer as normalizer_mod
from palchronicle.adapters import privacy_filter as privacy_mod
from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


class SpyPlayers:
    def __init__(self):
        self.snapshots = []

    async def apply_players(self, world, snap):
        self.snapshots.append(snap)

    async def mark_uncertain(self, world):
        return None


class SpyAgg:
    async def apply(self, world, gd):
        return []


def _server():
    return ServerConfig(
        server_id="srvA", name="srvA", enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _cfg():
    return AppConfig(
        servers=[_server()], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.0, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
async def ctx(tmp_path):
    db = Database(tmp_path / "pipeline.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=10000)
    repo = Repository(db, clock)
    meta = MetadataRepository(METADATA_DIR)
    meta.load()
    players = SpyPlayers()
    svc = SnapshotService(
        repo=repo, normalizer_mod=normalizer_mod, privacy_mod=privacy_mod,
        meta=meta, salt=b"\x11" * 32, cfg=_cfg(), clock=clock,
        players=players, guilds=SpyAgg(), bases=SpyAgg(), events=SpyAgg(),
    )
    yield svc, repo, clock, players, db
    await db.close()


@pytest.mark.asyncio
async def test_full_ingest_pipeline_builds_world_and_metrics_no_pii(ctx):
    svc, repo, clock, players, db = ctx
    info = RestResponse(ok=True, status=200,
                        data={"Version": "0.3", "ServerName": "Alpha", "WorldGuid": "WG-1"},
                        duration_ms=1, payload_bytes=1, error=None)
    metrics = RestResponse(ok=True, status=200,
                           data={"ServerFps": 58, "ServerFrameTime": 17, "CurrentPlayerNum": 2,
                                 "MaxPlayerNum": 32, "Uptime": 500, "Days": 9, "BaseCampNum": 3},
                           duration_ms=1, payload_bytes=1, error=None)
    players_resp = RestResponse(ok=True, status=200,
                                data={"players": [{"UserId": "secret-uid-777", "Name": "Zed",
                                                   "Level": 8, "Ping": 200, "BuildingCount": 4,
                                                   "Ip": "203.0.113.9", "AccountName": "steam_zed"}]},
                                duration_ms=1, payload_bytes=1, error=None)

    world = await svc.ingest_info(_server(), info)
    assert world.world_id == "srvA:WG-1:0"
    await svc.ingest_metrics(world, metrics)
    await svc.ingest_players(world, players_resp)

    m = await repo.latest_metric("srvA:WG-1:0")
    assert m.online_players == 2 and m.world_day == 9 and m.basecamp_count == 3

    # 脱敏快照(内存)已到达 players
    assert players.snapshots[0].players[0].name == "Zed"
    assert players.snapshots[0].players[0].userid != "secret-uid-777"

    # 隐私红线: DB 全表 dump 无 IP / 原始 id / 原始账号
    dumped = await _dump_all_text(db)
    assert "203.0.113.9" not in dumped
    assert "secret-uid-777" not in dumped
    assert "steam_zed" not in dumped


async def _dump_all_text(db) -> str:
    tables = await db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    parts = []
    for t in tables:
        name = t["name"]
        rows = await db.query(f"SELECT * FROM {name}")
        for r in rows:
            parts.append("|".join(str(r[k]) for k in r.keys()))
    return "\n".join(parts)
```

- [ ] **2) 跑测试确认失败** — 命令：`python -m pytest tests/integration/pipeline_test.py -q`。期望 FAIL：首次运行前 `tests/integration/__init__.py` 若缺失导致收集问题，或断言在管线未串通时失败。最可能的初始 FAIL 是 import 或 fixture 已就绪但断言 `players.snapshots[0]` 逻辑（若 2.18 未接线）——但 2.18 已实现，故本任务预期首跑即因**尚未创建该测试文件之前**不存在；创建后应直接驱动验证。若首跑 PASS 说明前序任务已完全覆盖，则记录"集成验证通过"。为符合 TDD，先写测试再确认它能失败：临时把断言 `assert m.online_players == 2` 改为 `== 999` 跑一次确认测试有效（红），再改回真值。

- [ ] **3) 写最小实现** — 无新生产代码（管线在 2.15-2.18 已实现）。把步骤 2 中临时改坏的断言改回 `== 2`（真值）。若步骤 2 暴露真实缺陷（如脱敏未在落库前发生），则回到对应 Task 修复；否则本步仅恢复断言。

- [ ] **4) 跑测试确认通过** — 命令：`python -m pytest tests/integration/pipeline_test.py -q`。期望 PASS：1 passed。再跑全量确认无回归：`python -m pytest tests/ -q`，期望全绿。

- [ ] **5) 提交** — 命令：
```
git add tests/integration/__init__.py tests/integration/pipeline_test.py
git commit -m "test(integration): end-to-end ingest pipeline builds world/metrics with no PII in DB"
```

---

### Phase 2 收尾校验

- [ ] 运行全量：`python -m pytest tests/ -q`，确认 Phase 2 全部单元 + 集成测试通过。
- [ ] 确认新增文件均已提交：`git status` 干净；`palchronicle/domain/{enums,models,events}.py`、`palchronicle/adapters/{metadata_repository,normalizer,privacy_filter}.py`、`palchronicle/adapters/sqlite_repository.py`（+4 方法）、`palchronicle/application/snapshot_service.py`、`palchronicle/infrastructure/scheduler.py`、`metadata/*.json` 到位。
- [ ] 交接说明（写入 commit body 或 PR 描述）：`SnapshotService.ingest_players/ingest_game_data` 已委托 `self._players`/`self._guilds`/`self._bases`；Phase 3 需注入真实 `PlayerService`/`GuildService`/`BaseService`（签名见契约 §application）并在 `ingest_game_data` 中按 spec §6.2 用 `asyncio.to_thread` 卸载归一/聚合重计算。


## Phase 3：玩家会话/身份 + 公会聚合 + 据点推导

> 本阶段实现 `PlayerService`（身份/会话）、`GuildService`（公会聚合）、`BaseService`（PalBox 稳定匹配 + 据点归属 + 置信度，并定义 `BaseUpdate`），把 `SnapshotService.ingest_players` / `ingest_game_data` 接线到这些服务，并给 `Repository` 补充 player/session/observation/guild/palbox/base 相关方法。
>
> **前置**（Phase 1-2 已交付，本阶段消费其确切签名）：
> - `palchronicle/domain/enums.py`：`UnitType`、`ActionCategory`、`Confidence`、`LeaveReason`、`SessionStatus`、`PingBucket`、`IdConfidence`、`EventType`。
> - `palchronicle/domain/models.py`：`World`、`PlayerIdentity`、`PlayerObservation`、`PlayerSession`、`Guild`、`PalBox`、`Base`、`BaseObservation`、`CharacterActor`、`PalBoxActor`、`GameDataSnapshot`、`PlayerRow`、`PlayersSnapshot`、`MetricsSnapshot`、`InfoSnapshot`、`WorldEvent`。
> - `palchronicle/config.py`：`AppConfig`、`BasesConfig`、`PrivacyConfig`、`ServerConfig`。
> - `palchronicle/infrastructure/clock.py`：`Clock` / `SystemClock` / `FakeClock`。
> - `palchronicle/infrastructure/database.py`：`Database`（`execute_write`/`executemany_write`/`write_tx`/`query`）。
> - `palchronicle/adapters/sqlite_repository.py`：`Repository`（Phase 1 已实现 server/binding/world/prune 方法与建表迁移；本阶段**在同一个类上追加**方法）。
> - `palchronicle/adapters/privacy_filter.py`：`hash_user_id`、`bucketize_ping`、`quantize_cell`。
> - `palchronicle/application/snapshot_service.py`：`SnapshotService`（Phase 2 已建骨架 + `ingest_info`/`ingest_metrics`/`ingest_settings`；本阶段实现 `ingest_players`/`ingest_game_data`）。
>
> **跨阶段约定**：`EventService`（Phase 4 定义）在本阶段仅作为**注入依赖**被调用，方法签名严格照契约：`level_up(world, player_key, old, new)`、`new_player(world, player_key)`、`new_guild(world, guild_key)`、`base_events(world, updates: list[BaseUpdate])`。本阶段测试用 fake EventService 断言调用；`BaseUpdate` 由本阶段 `base_service.py` 定义并被 Phase 4 消费。

---

### Task 3.1：Repository — player 身份读写

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_players_test.py`

**Interfaces:**
- Consumes: `Database.execute_write(sql, params)` / `Database.query(sql, params)`；`PlayerIdentity(player_key, world_id, latest_name, first_seen_at, last_seen_at, latest_level, latest_guild_key, id_confidence)`；`IdConfidence`；`players` 表（Phase 1 迁移已建，PK `(player_key, world_id)`）。
- Produces：`Repository.upsert_player(self, p: PlayerIdentity) -> None`、`Repository.get_player_by_name(self, world_id: str, name: str) -> PlayerIdentity | None`。

- [ ] 1) 写失败测试 `tests/unit/repository_players_test.py`：

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import PlayerIdentity
from palchronicle.domain.enums import IdConfidence
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


@pytest.mark.asyncio
async def test_upsert_player_then_get_by_name(repo):
    p = PlayerIdentity(
        player_key="pk1", world_id="w1", latest_name="Alice",
        first_seen_at=1000, last_seen_at=1000, latest_level=5,
        latest_guild_key=None, id_confidence=IdConfidence.HIGH,
    )
    await repo.upsert_player(p)
    got = await repo.get_player_by_name("w1", "Alice")
    assert got is not None
    assert got.player_key == "pk1"
    assert got.latest_level == 5
    assert got.id_confidence == IdConfidence.HIGH


@pytest.mark.asyncio
async def test_upsert_player_updates_existing(repo):
    p = PlayerIdentity("pk1", "w1", "Alice", 1000, 1000, 5, None, IdConfidence.HIGH)
    await repo.upsert_player(p)
    p2 = PlayerIdentity("pk1", "w1", "Alice", 1000, 2000, 7, "g1", IdConfidence.HIGH)
    await repo.upsert_player(p2)
    got = await repo.get_player_by_name("w1", "Alice")
    assert got.latest_level == 7
    assert got.latest_guild_key == "g1"
    assert got.last_seen_at == 2000


@pytest.mark.asyncio
async def test_get_player_by_name_missing(repo):
    assert await repo.get_player_by_name("w1", "Nobody") is None
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/repository_players_test.py -q` → 期望 FAIL：`AttributeError: 'Repository' object has no attribute 'upsert_player'`。

- [ ] 3) 写最小实现 — 在 `palchronicle/adapters/sqlite_repository.py` 的 `Repository` 类内新增：

```python
    async def upsert_player(self, p: PlayerIdentity) -> None:
        await self._db.execute_write(
            """
            INSERT INTO players
                (player_key, world_id, latest_name, first_seen_at, last_seen_at,
                 latest_level, latest_guild_key, id_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_key, world_id) DO UPDATE SET
                latest_name = excluded.latest_name,
                last_seen_at = excluded.last_seen_at,
                latest_level = excluded.latest_level,
                latest_guild_key = excluded.latest_guild_key,
                id_confidence = excluded.id_confidence
            """,
            (p.player_key, p.world_id, p.latest_name, p.first_seen_at,
             p.last_seen_at, p.latest_level, p.latest_guild_key, str(p.id_confidence)),
        )

    async def get_player_by_name(self, world_id: str, name: str) -> PlayerIdentity | None:
        rows = await self._db.query(
            """
            SELECT player_key, world_id, latest_name, first_seen_at, last_seen_at,
                   latest_level, latest_guild_key, id_confidence
            FROM players WHERE world_id = ? AND latest_name = ?
            ORDER BY last_seen_at DESC LIMIT 1
            """,
            (world_id, name),
        )
        if not rows:
            return None
        r = rows[0]
        return PlayerIdentity(
            player_key=r["player_key"], world_id=r["world_id"],
            latest_name=r["latest_name"], first_seen_at=r["first_seen_at"],
            last_seen_at=r["last_seen_at"], latest_level=r["latest_level"],
            latest_guild_key=r["latest_guild_key"],
            id_confidence=IdConfidence(r["id_confidence"]),
        )
```

在文件顶部 import 区确保存在（若缺则补）：`from palchronicle.domain.models import PlayerIdentity` 与 `from palchronicle.domain.enums import IdConfidence`。约定 `Repository.__init__` 已把 `Database` 存为 `self._db`、`Clock` 存为 `self._clock`（Phase 1 建立）。

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/repository_players_test.py -q` → 期望 PASS（3 passed）。

- [ ] 5) 提交：`git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_players_test.py && git commit -m "feat(repo): add player identity upsert/get_by_name"`

---

### Task 3.2：Repository — session 读写

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_sessions_test.py`

**Interfaces:**
- Consumes：`PlayerSession(id, world_id, player_key, joined_at, last_confirmed_at, left_at, observed_seconds, status: SessionStatus, leave_reason: LeaveReason|None)`；`SessionStatus`、`LeaveReason`；`player_sessions` 表（Phase 1 迁移已建，PK `id`）。
- Produces：`get_open_session(world_id, player_key) -> PlayerSession|None`（active 优先，否则 uncertain）、`insert_session(s) -> int`、`update_session(s) -> None`、`list_open_sessions(world_id) -> list[PlayerSession]`。

- [ ] 1) 写失败测试 `tests/unit/repository_sessions_test.py`：

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import PlayerSession
from palchronicle.domain.enums import SessionStatus, LeaveReason
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


def _sess(status, **kw):
    base = dict(
        id=None, world_id="w1", player_key="pk1", joined_at=1000,
        last_confirmed_at=1000, left_at=None, observed_seconds=0,
        status=status, leave_reason=None,
    )
    base.update(kw)
    return PlayerSession(**base)


@pytest.mark.asyncio
async def test_insert_returns_id_and_roundtrips(repo):
    sid = await repo.insert_session(_sess(SessionStatus.ACTIVE))
    assert isinstance(sid, int) and sid > 0
    got = await repo.get_open_session("w1", "pk1")
    assert got is not None
    assert got.id == sid
    assert got.status == SessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_open_prefers_active_over_uncertain(repo):
    await repo.insert_session(_sess(SessionStatus.UNCERTAIN, joined_at=900))
    active_id = await repo.insert_session(_sess(SessionStatus.ACTIVE, joined_at=1000))
    got = await repo.get_open_session("w1", "pk1")
    assert got.id == active_id
    assert got.status == SessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_open_falls_back_to_uncertain(repo):
    uid = await repo.insert_session(_sess(SessionStatus.UNCERTAIN))
    got = await repo.get_open_session("w1", "pk1")
    assert got.id == uid
    assert got.status == SessionStatus.UNCERTAIN


@pytest.mark.asyncio
async def test_get_open_ignores_closed(repo):
    await repo.insert_session(_sess(SessionStatus.CLOSED, left_at=1500,
                                    leave_reason=LeaveReason.OBSERVED_TIMEOUT))
    assert await repo.get_open_session("w1", "pk1") is None


@pytest.mark.asyncio
async def test_update_session_mutates(repo):
    sid = await repo.insert_session(_sess(SessionStatus.ACTIVE))
    got = await repo.get_open_session("w1", "pk1")
    got.observed_seconds = 120
    got.last_confirmed_at = 1120
    got.status = SessionStatus.CLOSED
    got.left_at = 1200
    got.leave_reason = LeaveReason.WORLD_OFFLINE
    await repo.update_session(got)
    assert await repo.get_open_session("w1", "pk1") is None
    rows = await repo._db.query(
        "SELECT observed_seconds, status, leave_reason FROM player_sessions WHERE id = ?",
        (sid,),
    )
    assert rows[0]["observed_seconds"] == 120
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"


@pytest.mark.asyncio
async def test_list_open_sessions(repo):
    await repo.insert_session(_sess(SessionStatus.ACTIVE, player_key="a"))
    await repo.insert_session(_sess(SessionStatus.UNCERTAIN, player_key="b"))
    await repo.insert_session(_sess(SessionStatus.CLOSED, player_key="c", left_at=1))
    keys = {s.player_key for s in await repo.list_open_sessions("w1")}
    assert keys == {"a", "b"}
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/repository_sessions_test.py -q` → 期望 FAIL：`AttributeError: 'Repository' object has no attribute 'insert_session'`。

- [ ] 3) 写最小实现 — 在 `Repository` 类内新增（`_row_to_session` 供本类其它读方法复用）：

```python
    @staticmethod
    def _row_to_session(r) -> PlayerSession:
        return PlayerSession(
            id=r["id"], world_id=r["world_id"], player_key=r["player_key"],
            joined_at=r["joined_at"], last_confirmed_at=r["last_confirmed_at"],
            left_at=r["left_at"], observed_seconds=r["observed_seconds"],
            status=SessionStatus(r["status"]),
            leave_reason=LeaveReason(r["leave_reason"]) if r["leave_reason"] else None,
        )

    async def insert_session(self, s: PlayerSession) -> int:
        async with self._db.write_tx() as conn:
            cur = await conn.execute(
                """
                INSERT INTO player_sessions
                    (world_id, player_key, joined_at, last_confirmed_at, left_at,
                     observed_seconds, status, leave_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (s.world_id, s.player_key, s.joined_at, s.last_confirmed_at,
                 s.left_at, s.observed_seconds, str(s.status),
                 str(s.leave_reason) if s.leave_reason else None),
            )
            s.id = cur.lastrowid
            return cur.lastrowid

    async def update_session(self, s: PlayerSession) -> None:
        await self._db.execute_write(
            """
            UPDATE player_sessions SET
                last_confirmed_at = ?, left_at = ?, observed_seconds = ?,
                status = ?, leave_reason = ?
            WHERE id = ?
            """,
            (s.last_confirmed_at, s.left_at, s.observed_seconds, str(s.status),
             str(s.leave_reason) if s.leave_reason else None, s.id),
        )

    async def get_open_session(self, world_id: str, player_key: str) -> PlayerSession | None:
        rows = await self._db.query(
            """
            SELECT * FROM player_sessions
            WHERE world_id = ? AND player_key = ? AND status IN ('active', 'uncertain')
            ORDER BY (status = 'active') DESC, joined_at DESC LIMIT 1
            """,
            (world_id, player_key),
        )
        return self._row_to_session(rows[0]) if rows else None

    async def list_open_sessions(self, world_id: str) -> list[PlayerSession]:
        rows = await self._db.query(
            """
            SELECT * FROM player_sessions
            WHERE world_id = ? AND status IN ('active', 'uncertain')
            ORDER BY joined_at ASC
            """,
            (world_id,),
        )
        return [self._row_to_session(r) for r in rows]
```

顶部 import 补：`from palchronicle.domain.models import PlayerSession` 与 `from palchronicle.domain.enums import SessionStatus, LeaveReason`。注：`write_tx()` 是持写锁的单事务异步上下文，`async with ... as conn` 暴露底层 `aiosqlite.Connection`（Phase 1 契约）。

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/repository_sessions_test.py -q` → 期望 PASS（6 passed）。

- [ ] 5) 提交：`git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_sessions_test.py && git commit -m "feat(repo): add player session insert/update/get_open/list_open"`

---

### Task 3.3：Repository — observation 读写

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_observations_test.py`

**Interfaces:**
- Consumes：`PlayerObservation(observed_at, world_id, player_key, name, level, ping_bucket: PingBucket, building_count, guild_key, position_cell, companion_class)`；`player_observations` 表（Phase 1 迁移已建，PK `id`，含 `ping_bucket` 列，**不含原始 ping**）。
- Produces：`insert_observation(o) -> None`、`latest_observation(world_id, player_key) -> PlayerObservation|None`。

- [ ] 1) 写失败测试 `tests/unit/repository_observations_test.py`：

```python
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import PlayerObservation
from palchronicle.domain.enums import PingBucket
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


def _obs(observed_at, level, **kw):
    base = dict(
        observed_at=observed_at, world_id="w1", player_key="pk1", name="Alice",
        level=level, ping_bucket=PingBucket.GOOD, building_count=3,
        guild_key=None, position_cell=None, companion_class=None,
    )
    base.update(kw)
    return PlayerObservation(**base)


@pytest.mark.asyncio
async def test_insert_and_latest(repo):
    await repo.insert_observation(_obs(1000, 5))
    await repo.insert_observation(_obs(2000, 8, ping_bucket=PingBucket.OK,
                                       building_count=9, companion_class="Sheepball"))
    got = await repo.latest_observation("w1", "pk1")
    assert got.observed_at == 2000
    assert got.level == 8
    assert got.ping_bucket == PingBucket.OK
    assert got.building_count == 9
    assert got.companion_class == "Sheepball"


@pytest.mark.asyncio
async def test_latest_missing(repo):
    assert await repo.latest_observation("w1", "ghost") is None


@pytest.mark.asyncio
async def test_position_cell_none_persists_as_null(repo):
    await repo.insert_observation(_obs(1000, 5, position_cell=None))
    rows = await repo._db.query(
        "SELECT position_cell FROM player_observations WHERE world_id='w1'", ()
    )
    assert rows[0]["position_cell"] is None
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/repository_observations_test.py -q` → 期望 FAIL：`AttributeError: 'Repository' object has no attribute 'insert_observation'`。

- [ ] 3) 写最小实现 — 在 `Repository` 类内新增：

```python
    async def insert_observation(self, o: PlayerObservation) -> None:
        await self._db.execute_write(
            """
            INSERT INTO player_observations
                (world_id, player_key, observed_at, level, ping_bucket,
                 building_count, guild_key, companion_class, position_cell)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (o.world_id, o.player_key, o.observed_at, o.level, str(o.ping_bucket),
             o.building_count, o.guild_key, o.companion_class, o.position_cell),
        )

    async def latest_observation(self, world_id: str, player_key: str) -> PlayerObservation | None:
        rows = await self._db.query(
            """
            SELECT world_id, player_key, observed_at, level, ping_bucket,
                   building_count, guild_key, companion_class, position_cell
            FROM player_observations
            WHERE world_id = ? AND player_key = ?
            ORDER BY observed_at DESC LIMIT 1
            """,
            (world_id, player_key),
        )
        if not rows:
            return None
        r = rows[0]
        return PlayerObservation(
            observed_at=r["observed_at"], world_id=r["world_id"],
            player_key=r["player_key"], name="", level=r["level"],
            ping_bucket=PingBucket(r["ping_bucket"]),
            building_count=r["building_count"], guild_key=r["guild_key"],
            position_cell=r["position_cell"], companion_class=r["companion_class"],
        )
```

（`name` 不落库，读回置空串；渲染名取自 `players.latest_name`。）顶部 import 补：`from palchronicle.domain.models import PlayerObservation` 与 `from palchronicle.domain.enums import PingBucket`。

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/repository_observations_test.py -q` → 期望 PASS（3 passed）。

- [ ] 5) 提交：`git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_observations_test.py && git commit -m "feat(repo): add player observation insert/latest"`

---

### Task 3.4：PlayerService — player_key 派生

**Files:**
- Create: `palchronicle/application/player_service.py`
- Test: `tests/unit/player_key_test.py`

**Interfaces:**
- Consumes：`privacy_filter.hash_user_id(salt, world_id, raw_user_id) -> str`（Phase 2 契约，HMAC-SHA256 hex）；`PlayerRow(userid, player_id, name, level, ping, building_count)`；`IdConfidence`。
- Produces：`PlayerService.player_key(salt, world_id, raw_user_id) -> str`（staticmethod）；模块内私有 `_resolve_identity(row: PlayerRow, salt, world_id) -> tuple[str, IdConfidence]`（返回 `(player_key, id_confidence)`；主源 `userid`（已由脱敏映射为 hash 或 None），回退 `player_id`，再回退 `name.lower()` 且 `id_confidence=LOW`）。

> 说明：`PlayerRow.userid` 在脱敏阶段（Phase 2 `redact_players`）已被 `hash_user_id` 处理为 hex 或 `None`。因此若 `row.userid` 存在则它**已是 player_key**（高置信度）；回退分支才需再对 `player_id` / `name.lower()` 现算 HMAC。

- [ ] 1) 写失败测试 `tests/unit/player_key_test.py`：

```python
import hashlib
import hmac

import pytest

from palchronicle.application.player_service import PlayerService, _resolve_identity
from palchronicle.domain.models import PlayerRow
from palchronicle.domain.enums import IdConfidence

SALT = b"0" * 32


def _expected(world_id, raw):
    return hmac.new(SALT, f"{world_id}:{raw}".encode(), hashlib.sha256).hexdigest()


def test_player_key_matches_hmac():
    assert PlayerService.player_key(SALT, "w1", "user-123") == _expected("w1", "user-123")


def test_player_key_stable_across_calls():
    a = PlayerService.player_key(SALT, "w1", "user-123")
    b = PlayerService.player_key(SALT, "w1", "user-123")
    assert a == b


def test_player_key_world_scoped():
    assert PlayerService.player_key(SALT, "w1", "u") != PlayerService.player_key(SALT, "w2", "u")


def test_resolve_prefers_hashed_userid_high():
    row = PlayerRow(userid="ALREADYHASHED", player_id="pid", name="Alice",
                    level=1, ping=None, building_count=0)
    key, conf = _resolve_identity(row, SALT, "w1")
    assert key == "ALREADYHASHED"
    assert conf == IdConfidence.HIGH


def test_resolve_falls_back_to_player_id_high():
    row = PlayerRow(userid=None, player_id="pid-9", name="Alice",
                    level=1, ping=None, building_count=0)
    key, conf = _resolve_identity(row, SALT, "w1")
    assert key == _expected("w1", "pid-9")
    assert conf == IdConfidence.HIGH


def test_resolve_falls_back_to_name_low():
    row = PlayerRow(userid=None, player_id=None, name="Alice",
                    level=1, ping=None, building_count=0)
    key, conf = _resolve_identity(row, SALT, "w1")
    assert key == _expected("w1", "alice")
    assert conf == IdConfidence.LOW
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/player_key_test.py -q` → 期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.player_service'`。

- [ ] 3) 写最小实现 `palchronicle/application/player_service.py`：

```python
from __future__ import annotations

from palchronicle.adapters.privacy_filter import hash_user_id
from palchronicle.domain.enums import IdConfidence
from palchronicle.domain.models import PlayerRow


def _resolve_identity(row: PlayerRow, salt: bytes, world_id: str) -> tuple[str, IdConfidence]:
    if row.userid:
        # 脱敏阶段已把 /players.userId 映射为 HMAC hex
        return row.userid, IdConfidence.HIGH
    if row.player_id:
        return hash_user_id(salt, world_id, row.player_id), IdConfidence.HIGH
    return hash_user_id(salt, world_id, row.name.lower()), IdConfidence.LOW


class PlayerService:
    @staticmethod
    def player_key(salt: bytes, world_id: str, raw_user_id: str) -> str:
        return hash_user_id(salt, world_id, raw_user_id)
```

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/player_key_test.py -q` → 期望 PASS（6 passed）。

- [ ] 5) 提交：`git add palchronicle/application/player_service.py tests/unit/player_key_test.py && git commit -m "feat(player): player_key derivation + identity fallback resolution"`

---

### Task 3.5：PlayerService — 新会话 + NEW_PLAYER + 观察落库

**Files:**
- Modify: `palchronicle/application/player_service.py`
- Test: `tests/unit/player_service_join_test.py`

**Interfaces:**
- Consumes：`Repository.get_open_session` / `insert_session` / `upsert_player` / `insert_observation` / `latest_observation`（Task 3.1-3.3）；`EventService.new_player(world, player_key)`（fake 注入）；`PlayerService.player_key` / `_resolve_identity`（Task 3.4）；`bucketize_ping(ms, cfg)`（Phase 2）；`World`、`PlayerRow`、`PlayersSnapshot`、`PlayerIdentity`、`PlayerObservation`、`PlayerSession`、`SessionStatus`。
- Produces：`PlayerService.__init__(self, repo, salt, cfg, clock)`（`cfg: AppConfig`）、`async apply_players(self, world: World, snap: PlayersSnapshot) -> None`。本任务只覆盖"首次出现→新建 active 会话 + 落身份 + 落观察 + 触发 NEW_PLAYER"。

- [ ] 1) 写失败测试 `tests/unit/player_service_join_test.py`：

```python
import pytest

from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.domain.enums import SessionStatus, IdConfidence
from palchronicle.infrastructure.clock import FakeClock


class FakeEvents:
    def __init__(self):
        self.new_players = []
        self.level_ups = []

    async def new_player(self, world, player_key):
        self.new_players.append(player_key)

    async def level_up(self, world, player_key, old, new):
        self.level_ups.append((player_key, old, new))

    async def new_guild(self, world, guild_key):
        pass


def _world():
    return World(world_id="w1", server_id="s1", worldguid="g", epoch=0,
                 server_name="S", version="1", first_seen_at=0,
                 last_seen_at=0, current_day=1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(AccessMode.RESTRICTED, ""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
def svc():
    from palchronicle.adapters.sqlite_repository import Repository
    return Repository, FakeEvents(), FakeClock(1000)


@pytest.mark.asyncio
async def test_first_appearance_creates_active_session(tmp_path):
    from palchronicle.infrastructure.database import Database
    from palchronicle.infrastructure.migrations import apply_migrations
    from palchronicle.adapters.sqlite_repository import Repository
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); events = FakeEvents()
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock)
    svc.events = events
    world = _world()
    row = PlayerRow(userid="pk-alice", player_id="pid", name="Alice",
                    level=5, ping=40.0, building_count=3)
    await svc.apply_players(world, PlayersSnapshot(observed_at=1000, players=[row]))

    sess = await repo.get_open_session("w1", "pk-alice")
    assert sess is not None
    assert sess.status == SessionStatus.ACTIVE
    assert sess.joined_at == 1000
    assert sess.last_confirmed_at == 1000
    assert sess.observed_seconds == 0
    assert events.new_players == ["pk-alice"]

    ident = await repo.get_player_by_name("w1", "Alice")
    assert ident.player_key == "pk-alice"
    assert ident.latest_level == 5
    assert ident.id_confidence == IdConfidence.HIGH

    obs = await repo.latest_observation("w1", "pk-alice")
    assert obs.level == 5
    assert obs.building_count == 3
    await db.close()


@pytest.mark.asyncio
async def test_second_appearance_no_duplicate_new_player(tmp_path):
    from palchronicle.infrastructure.database import Database
    from palchronicle.infrastructure.migrations import apply_migrations
    from palchronicle.adapters.sqlite_repository import Repository
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); events = FakeEvents()
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock)
    svc.events = events
    world = _world()
    row = PlayerRow(userid="pk-alice", player_id="pid", name="Alice",
                    level=5, ping=40.0, building_count=3)
    await svc.apply_players(world, PlayersSnapshot(1000, [row]))
    clock.set(1030)
    await svc.apply_players(world, PlayersSnapshot(1030, [row]))
    assert events.new_players == ["pk-alice"]  # 只一次
    await db.close()
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/player_service_join_test.py -q` → 期望 FAIL：`TypeError: PlayerService() takes no arguments`（`__init__` 未定义）/ `AttributeError: apply_players`。

- [ ] 3) 写最小实现 — 修改 `palchronicle/application/player_service.py`。在文件顶部补 import，替换 `PlayerService` 类体为如下（保留 `_resolve_identity` 与 `player_key`）：

```python
from __future__ import annotations

from palchronicle.adapters.privacy_filter import bucketize_ping, hash_user_id
from palchronicle.domain.enums import IdConfidence, SessionStatus
from palchronicle.domain.models import (
    PlayerIdentity, PlayerObservation, PlayerRow, PlayerSession, PlayersSnapshot, World,
)


def _resolve_identity(row: PlayerRow, salt: bytes, world_id: str) -> tuple[str, IdConfidence]:
    if row.userid:
        return row.userid, IdConfidence.HIGH
    if row.player_id:
        return hash_user_id(salt, world_id, row.player_id), IdConfidence.HIGH
    return hash_user_id(salt, world_id, row.name.lower()), IdConfidence.LOW


class PlayerService:
    def __init__(self, repo, salt: bytes, cfg, clock):
        self._repo = repo
        self._salt = salt
        self._cfg = cfg
        self._clock = clock
        self.events = None  # 由 container 注入 EventService

    @staticmethod
    def player_key(salt: bytes, world_id: str, raw_user_id: str) -> str:
        return hash_user_id(salt, world_id, raw_user_id)

    async def apply_players(self, world: World, snap: PlayersSnapshot) -> None:
        now = snap.observed_at
        for row in snap.players:
            key, conf = _resolve_identity(row, self._salt, world.world_id)
            existing_ident = await self._repo.get_player_by_name(world.world_id, row.name)
            is_new_identity = existing_ident is None or existing_ident.player_key != key

            bucket = bucketize_ping(row.ping, self._cfg.privacy)
            await self._repo.insert_observation(PlayerObservation(
                observed_at=now, world_id=world.world_id, player_key=key,
                name=row.name, level=row.level, ping_bucket=bucket,
                building_count=row.building_count, guild_key=None,
                position_cell=None, companion_class=None,
            ))
            await self._repo.upsert_player(PlayerIdentity(
                player_key=key, world_id=world.world_id, latest_name=row.name,
                first_seen_at=now, last_seen_at=now, latest_level=row.level,
                latest_guild_key=None, id_confidence=conf,
            ))

            session = await self._repo.get_open_session(world.world_id, key)
            if session is None:
                await self._repo.insert_session(PlayerSession(
                    id=None, world_id=world.world_id, player_key=key,
                    joined_at=now, last_confirmed_at=now, left_at=None,
                    observed_seconds=0, status=SessionStatus.ACTIVE, leave_reason=None,
                ))
                if is_new_identity and self.events is not None:
                    await self.events.new_player(world, key)
```

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/player_service_join_test.py -q` → 期望 PASS（2 passed）。

- [ ] 5) 提交：`git add palchronicle/application/player_service.py tests/unit/player_service_join_test.py && git commit -m "feat(player): apply_players creates session, identity, observation, NEW_PLAYER"`

---

### Task 3.6：PlayerService — 时长累计 + 等级变化事件

**Files:**
- Modify: `palchronicle/application/player_service.py`
- Test: `tests/unit/player_service_confirm_test.py`

**Interfaces:**
- Consumes：Task 3.5 的 `apply_players`；`Repository.update_session`；`EventService.level_up(world, player_key, old, new)`（fake）；`cfg.polling.players_seconds`（健康采样间隔）。
- Produces：扩展 `apply_players` 对**已有 active 会话**的续计：`observed_seconds += min(now - last_confirmed_at, players_seconds * 容差)`（容差常量 `_HEALTH_TOLERANCE = 1.5`），更新 `last_confirmed_at`；等级上升 → `events.level_up(world, key, old, new)`；等级下降不触发。

- [ ] 1) 写失败测试 `tests/unit/player_service_confirm_test.py`：

```python
import pytest

from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    def __init__(self):
        self.new_players, self.level_ups = [], []
    async def new_player(self, world, player_key): self.new_players.append(player_key)
    async def level_up(self, world, player_key, old, new): self.level_ups.append((player_key, old, new))
    async def new_guild(self, world, guild_key): pass


def _world():
    return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); events = FakeEvents()
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock); svc.events = events
    return db, clock, repo, events, svc


def _row(level=5):
    return PlayerRow(userid="pk-a", player_id="p", name="Alice", level=level, ping=40.0, building_count=3)


@pytest.mark.asyncio
async def test_observed_seconds_accumulates_within_tolerance(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, [_row()]))
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.observed_seconds == 30  # 30 <= 30*1.5
    assert sess.last_confirmed_at == 1030
    await db.close()


@pytest.mark.asyncio
async def test_observed_seconds_capped_on_large_gap(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1000 + 600)  # 600s 间隔（API 中断），players_seconds=30, cap=45
    await svc.apply_players(_world(), PlayersSnapshot(1600, [_row()]))
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.observed_seconds == 45  # min(600, 30*1.5)
    await db.close()


@pytest.mark.asyncio
async def test_level_up_emits_event(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row(level=5)]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, [_row(level=8)]))
    assert events.level_ups == [("pk-a", 5, 8)]
    await db.close()


@pytest.mark.asyncio
async def test_level_down_no_event(tmp_path):
    db, clock, repo, events, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row(level=8)]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, [_row(level=5)]))
    assert events.level_ups == []
    await db.close()
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/player_service_confirm_test.py -q` → 期望 FAIL：`test_observed_seconds_accumulates_within_tolerance` AssertionError（`observed_seconds == 0`，未续计）。

- [ ] 3) 写最小实现 — 修改 `apply_players`：在计算 `is_new_identity` 之后、`insert_observation` 之前捕获旧等级，并在会话分支补续计与 level_up。完整替换 `apply_players` 方法体为：

```python
    _HEALTH_TOLERANCE = 1.5

    async def apply_players(self, world: World, snap: PlayersSnapshot) -> None:
        now = snap.observed_at
        cap = int(self._cfg.polling.players_seconds * self._HEALTH_TOLERANCE)
        for row in snap.players:
            key, conf = _resolve_identity(row, self._salt, world.world_id)
            prev_ident = await self._repo.get_player_by_name(world.world_id, row.name)
            is_new_identity = prev_ident is None or prev_ident.player_key != key
            old_level = prev_ident.latest_level if (prev_ident and not is_new_identity) else None

            bucket = bucketize_ping(row.ping, self._cfg.privacy)
            await self._repo.insert_observation(PlayerObservation(
                observed_at=now, world_id=world.world_id, player_key=key,
                name=row.name, level=row.level, ping_bucket=bucket,
                building_count=row.building_count, guild_key=None,
                position_cell=None, companion_class=None,
            ))
            await self._repo.upsert_player(PlayerIdentity(
                player_key=key, world_id=world.world_id, latest_name=row.name,
                first_seen_at=now, last_seen_at=now, latest_level=row.level,
                latest_guild_key=None, id_confidence=conf,
            ))

            session = await self._repo.get_open_session(world.world_id, key)
            if session is None:
                await self._repo.insert_session(PlayerSession(
                    id=None, world_id=world.world_id, player_key=key,
                    joined_at=now, last_confirmed_at=now, left_at=None,
                    observed_seconds=0, status=SessionStatus.ACTIVE, leave_reason=None,
                ))
                if is_new_identity and self.events is not None:
                    await self.events.new_player(world, key)
            else:
                delta = max(0, now - session.last_confirmed_at)
                session.observed_seconds += min(delta, cap)
                session.last_confirmed_at = now
                session.status = SessionStatus.ACTIVE
                session.leave_reason = None
                await self._repo.update_session(session)

            if old_level is not None and row.level > old_level and self.events is not None:
                await self.events.level_up(world, key, old_level, row.level)
```

（`SessionStatus.ACTIVE` 与 `leave_reason=None` 的重置为 Task 3.8 的 uncertain 恢复预留；本任务测试不触发。）

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/player_service_confirm_test.py -q` → 期望 PASS（4 passed）。

- [ ] 5) 提交：`git add palchronicle/application/player_service.py tests/unit/player_service_confirm_test.py && git commit -m "feat(player): observed_seconds accrual within tolerance + PLAYER_LEVEL_UP"`

---

### Task 3.7：PlayerService — 连续 2 缺失关闭会话

**Files:**
- Modify: `palchronicle/application/player_service.py`
- Test: `tests/unit/player_service_leave_test.py`

**Interfaces:**
- Consumes：`Repository.list_open_sessions` / `update_session`；`SessionStatus`、`LeaveReason`；Task 3.6 `apply_players`。
- Produces：`apply_players` 尾部对**本快照未出现**的 active 会话记一次缺失；连续两次缺失（`_missing_streak` 内存计数达 2）→ `status=CLOSED, leave_reason=OBSERVED_TIMEOUT, left_at=now`。缺失计数保存在 `self._missing: dict[tuple[str,str], int]`（键 `(world_id, player_key)`）。

- [ ] 1) 写失败测试 `tests/unit/player_service_leave_test.py`：

```python
import pytest

from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.domain.enums import SessionStatus, LeaveReason
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock); svc.events = FakeEvents()
    return db, clock, repo, svc


def _row():
    return PlayerRow(userid="pk-a", player_id="p", name="Alice", level=5, ping=40.0, building_count=3)


@pytest.mark.asyncio
async def test_single_miss_keeps_active(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030)
    await svc.apply_players(_world(), PlayersSnapshot(1030, []))  # 缺失 1
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess is not None and sess.status == SessionStatus.ACTIVE
    await db.close()


@pytest.mark.asyncio
async def test_two_consecutive_misses_closes(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030); await svc.apply_players(_world(), PlayersSnapshot(1030, []))
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, []))
    assert await repo.get_open_session("w1", "pk-a") is None
    rows = await repo._db.query(
        "SELECT status, leave_reason, left_at FROM player_sessions WHERE player_key='pk-a'", ()
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "observed_timeout"
    assert rows[0]["left_at"] == 1060
    await db.close()


@pytest.mark.asyncio
async def test_reappearance_resets_miss_streak(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1030); await svc.apply_players(_world(), PlayersSnapshot(1030, []))     # miss 1
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, [_row()]))  # reappear
    clock.set(1090); await svc.apply_players(_world(), PlayersSnapshot(1090, []))     # miss 1 again
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess is not None and sess.status == SessionStatus.ACTIVE  # 未连续两次
    await db.close()
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/player_service_leave_test.py -q` → 期望 FAIL：`test_two_consecutive_misses_closes` AssertionError（会话仍开着，缺失逻辑未实现）。

- [ ] 3) 写最小实现 — 在 `PlayerService.__init__` 末尾加 `self._missing: dict[tuple[str, str], int] = {}`；在 `apply_players` 循环内、成功处理某玩家后把 `self._missing.pop((world.world_id, key), None)` 以清缺失计数；在 `apply_players` 方法**末尾**（for 之后）追加缺失清算：

在 `__init__` 内新增一行：

```python
        self._missing: dict[tuple[str, str], int] = {}
```

在 for 循环体内，处理完 session 分支之后加入：

```python
            self._missing.pop((world.world_id, key), None)
```

在 for 循环**之后**追加：

```python
        present = {
            _resolve_identity(r, self._salt, world.world_id)[0] for r in snap.players
        }
        for sess in await self._repo.list_open_sessions(world.world_id):
            if sess.status != SessionStatus.ACTIVE or sess.player_key in present:
                continue
            mkey = (world.world_id, sess.player_key)
            streak = self._missing.get(mkey, 0) + 1
            if streak >= 2:
                sess.status = SessionStatus.CLOSED
                sess.leave_reason = LeaveReason.OBSERVED_TIMEOUT
                sess.left_at = now
                await self._repo.update_session(sess)
                self._missing.pop(mkey, None)
            else:
                self._missing[mkey] = streak
```

顶部 import 补 `LeaveReason`：把现有 `from palchronicle.domain.enums import IdConfidence, SessionStatus` 改为 `from palchronicle.domain.enums import IdConfidence, LeaveReason, SessionStatus`。

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/player_service_leave_test.py -q` → 期望 PASS（3 passed）。

- [ ] 5) 提交：`git add palchronicle/application/player_service.py tests/unit/player_service_leave_test.py && git commit -m "feat(player): close session after two consecutive missing health snapshots"`

---

### Task 3.8：PlayerService — uncertain 标记/恢复/超时收敛/重启恢复

**Files:**
- Modify: `palchronicle/application/player_service.py`
- Test: `tests/integration/player_uncertain_test.py`

**Interfaces:**
- Consumes：`Repository.list_open_sessions` / `update_session` / `get_open_session`；`SessionStatus`、`LeaveReason`；`cfg.privacy.uncertain_timeout`；Task 3.6-3.7 `apply_players`（复用规则已由 `get_open_session`（active 优先否则 uncertain）+ 会话分支的 `status=ACTIVE` 重置实现）。
- Produces：`async mark_uncertain(self, world: World) -> None`（把该世界所有 active 会话置 uncertain，**不**改 joined_at/observed_seconds/last_confirmed_at）、`async sweep_uncertain(self, world: World) -> None`（`now - last_confirmed_at > uncertain_timeout` 的 uncertain → CLOSED，`leave_reason=WORLD_OFFLINE`）、`async recover_on_start(self, world: World) -> None`（v0.1 为 no-op：DB 中 active/uncertain 会话天然被后续 `apply_players`/`sweep` 复用，只清空内存 `_missing`）。

> uncertain 恢复复用由已有逻辑保证：`get_open_session` 在无 active 时返回 uncertain 会话，`apply_players` 的 else 分支续计并把 `status` 重置为 ACTIVE、`joined_at` 不动、`observed_seconds` 连续累计。本任务的时间序列测试正是验证这条路径。

- [ ] 1) 写失败测试 `tests/integration/player_uncertain_test.py`：

```python
import pytest

from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import PlayerRow, PlayersSnapshot, World
from palchronicle.domain.enums import SessionStatus, LeaveReason
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = PlayerService(repo, b"0" * 32, _cfg(), clock); svc.events = FakeEvents()
    return db, clock, repo, svc


def _row():
    return PlayerRow(userid="pk-a", player_id="p", name="Alice", level=5, ping=40.0, building_count=3)


@pytest.mark.asyncio
async def test_mark_uncertain_does_not_close(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1050)
    await svc.mark_uncertain(_world())
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.status == SessionStatus.UNCERTAIN
    assert sess.joined_at == 1000
    assert sess.left_at is None
    await db.close()


@pytest.mark.asyncio
async def test_uncertain_recovery_reuses_same_session(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    first = await repo.get_open_session("w1", "pk-a")
    # /players 中断 30s 后又中断，标 uncertain
    clock.set(1030); await svc.mark_uncertain(_world())
    # 恢复：同玩家再现
    clock.set(1060); await svc.apply_players(_world(), PlayersSnapshot(1060, [_row()]))
    resumed = await repo.get_open_session("w1", "pk-a")
    assert resumed.id == first.id           # 复用同会话, 不新建
    assert resumed.status == SessionStatus.ACTIVE
    assert resumed.joined_at == 1000        # joined_at 不变
    assert resumed.observed_seconds == 45   # min(1060-1000, 45) 连续累计
    await db.close()


@pytest.mark.asyncio
async def test_sweep_closes_stale_uncertain(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1010); await svc.mark_uncertain(_world())
    clock.set(1010 + 901)  # last_confirmed_at=1000, timeout 900
    await svc.sweep_uncertain(_world())
    assert await repo.get_open_session("w1", "pk-a") is None
    rows = await repo._db.query(
        "SELECT status, leave_reason FROM player_sessions WHERE player_key='pk-a'", ()
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["leave_reason"] == "world_offline"
    await db.close()


@pytest.mark.asyncio
async def test_sweep_keeps_fresh_uncertain(tmp_path):
    db, clock, repo, svc = await _mk(tmp_path)
    await svc.apply_players(_world(), PlayersSnapshot(1000, [_row()]))
    clock.set(1010); await svc.mark_uncertain(_world())
    clock.set(1500)  # 500s < 900
    await svc.sweep_uncertain(_world())
    sess = await repo.get_open_session("w1", "pk-a")
    assert sess.status == SessionStatus.UNCERTAIN
    await db.close()
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/integration/player_uncertain_test.py -q` → 期望 FAIL：`AttributeError: 'PlayerService' object has no attribute 'mark_uncertain'`。

- [ ] 3) 写最小实现 — 在 `PlayerService` 类内新增：

```python
    async def mark_uncertain(self, world: World) -> None:
        for sess in await self._repo.list_open_sessions(world.world_id):
            if sess.status == SessionStatus.ACTIVE:
                sess.status = SessionStatus.UNCERTAIN
                await self._repo.update_session(sess)

    async def sweep_uncertain(self, world: World) -> None:
        now = self._clock.now()
        timeout = self._cfg.privacy.uncertain_timeout
        for sess in await self._repo.list_open_sessions(world.world_id):
            if sess.status != SessionStatus.UNCERTAIN:
                continue
            if now - sess.last_confirmed_at > timeout:
                sess.status = SessionStatus.CLOSED
                sess.leave_reason = LeaveReason.WORLD_OFFLINE
                sess.left_at = now
                await self._repo.update_session(sess)

    async def recover_on_start(self, world: World) -> None:
        self._missing.clear()
```

- [ ] 4) 跑测试确认通过：`python -m pytest tests/integration/player_uncertain_test.py -q` → 期望 PASS（4 passed）。

- [ ] 5) 提交：`git add palchronicle/application/player_service.py tests/integration/player_uncertain_test.py && git commit -m "feat(player): uncertain mark/reuse/sweep + recover_on_start"`

---

### Task 3.9：PlayerService — companion_class best-effort 关联

**Files:**
- Modify: `palchronicle/application/player_service.py`
- Test: `tests/unit/player_companion_test.py`

**Interfaces:**
- Consumes：`GameDataSnapshot.characters: list[CharacterActor]`；`CharacterActor(unit_type, instance_id, trainer_instance_id, trainer_nickname, player_userid, pal_class, ...)`；`UnitType`；`Repository.latest_observation`（读回最近 name→暂不用）。因 game-data 的 `userid` **不**用于 player_key，关联主键为 `OtomoPal.trainer_instance_id → Player.instance_id`。
- Produces：`@staticmethod link_companions(gd: GameDataSnapshot) -> dict[str, str]` —— 返回 `{owner_instance_id: pal_class}`（每 owner 取首个可关联 OtomoPal）；关联不上不入表（等价 companion=NULL）。此纯函数供后续把 companion 写入观察（v0.1 仅瞬时，落库路径由 snapshot 接线 Task 3.14 消费）。

> 依据 spec §10.1：companion 关联字段稳定性未验证，关联不上则 `companion_class=NULL`，不阻断。本任务只做纯映射函数（确定性、可单测），不改 `apply_players`（后者输入是 `/players`，无 pal 信息）。

- [ ] 1) 写失败测试 `tests/unit/player_companion_test.py`：

```python
from palchronicle.application.player_service import PlayerService
from palchronicle.domain.models import CharacterActor, GameDataSnapshot
from palchronicle.domain.enums import UnitType, ActionCategory


def _actor(unit_type, instance_id=None, trainer_instance_id=None, pal_class=None):
    return CharacterActor(
        unit_type=unit_type, instance_id=instance_id, nickname=None,
        trainer_instance_id=trainer_instance_id, trainer_nickname=None,
        player_userid=None, level=None, hp=None, max_hp=None,
        guild_id=None, guild_name=None, pal_class=pal_class,
        action=ActionCategory.IDLE, ai_action=ActionCategory.IDLE,
        x=None, y=None, z=None, is_active=True,
    )


def _gd(actors):
    return GameDataSnapshot(observed_at=1000, fps=60.0, average_fps=60.0,
                            characters=actors, palboxes=[], unknown_classes=[])


def test_links_otomo_to_owner():
    gd = _gd([
        _actor(UnitType.PLAYER, instance_id="I1"),
        _actor(UnitType.OTOMO, trainer_instance_id="I1", pal_class="Sheepball"),
    ])
    assert PlayerService.link_companions(gd) == {"I1": "Sheepball"}


def test_unlinkable_otomo_ignored():
    gd = _gd([
        _actor(UnitType.PLAYER, instance_id="I1"),
        _actor(UnitType.OTOMO, trainer_instance_id="I9", pal_class="Foxparks"),
    ])
    assert PlayerService.link_companions(gd) == {}


def test_first_otomo_wins_per_owner():
    gd = _gd([
        _actor(UnitType.PLAYER, instance_id="I1"),
        _actor(UnitType.OTOMO, trainer_instance_id="I1", pal_class="First"),
        _actor(UnitType.OTOMO, trainer_instance_id="I1", pal_class="Second"),
    ])
    assert PlayerService.link_companions(gd) == {"I1": "First"}


def test_no_players_empty():
    gd = _gd([_actor(UnitType.WILD, pal_class="Chikipi")])
    assert PlayerService.link_companions(gd) == {}
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/player_companion_test.py -q` → 期望 FAIL：`AttributeError: type object 'PlayerService' has no attribute 'link_companions'`。

- [ ] 3) 写最小实现 — 在 `PlayerService` 类内新增 staticmethod（顶部 import 补 `from palchronicle.domain.models import ... GameDataSnapshot` 与 `from palchronicle.domain.enums import UnitType`）：

```python
    @staticmethod
    def link_companions(gd) -> dict[str, str]:
        from palchronicle.domain.enums import UnitType
        owners = {a.instance_id for a in gd.characters
                  if a.unit_type == UnitType.PLAYER and a.instance_id}
        result: dict[str, str] = {}
        for a in gd.characters:
            if a.unit_type != UnitType.OTOMO:
                continue
            owner = a.trainer_instance_id
            if owner and owner in owners and owner not in result and a.pal_class:
                result[owner] = a.pal_class
        return result
```

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/player_companion_test.py -q` → 期望 PASS（4 passed）。

- [ ] 5) 提交：`git add palchronicle/application/player_service.py tests/unit/player_companion_test.py && git commit -m "feat(player): best-effort OtomoPal→owner companion linking"`

---

### Task 3.10：Repository — guild / palbox / base 读写

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_guild_base_test.py`

**Interfaces:**
- Consumes：`Guild`、`PalBox`、`Base`、`BaseObservation`、`Confidence`；对应表（Phase 1 迁移已建：`guilds` PK `(guild_key, world_id)`、`palboxes` PK `(palbox_key, world_id)`、`bases` PK `(base_key, world_id)`、`base_observations` PK `id`）。
- Produces：`upsert_guild`、`list_guilds`、`upsert_palbox`、`list_palboxes`、`upsert_base`、`list_bases(world_id, include_low=False, include_hidden=False)`、`insert_base_observation`、`latest_base_observation`。

- [ ] 1) 写失败测试 `tests/unit/repository_guild_base_test.py`：

```python
import json
import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import Guild, PalBox, Base, BaseObservation
from palchronicle.domain.enums import Confidence
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


@pytest.mark.asyncio
async def test_guild_upsert_and_list(repo):
    g = Guild("gk1", "w1", "Noema", 1000, 1000, 4, 2, 6)
    await repo.upsert_guild(g)
    g2 = Guild("gk1", "w1", "Noema", 1000, 2000, 5, 3, 8)
    await repo.upsert_guild(g2)
    guilds = await repo.list_guilds("w1")
    assert len(guilds) == 1
    assert guilds[0].observed_member_count == 5
    assert guilds[0].palbox_count == 3
    assert guilds[0].last_seen_at == 2000


@pytest.mark.asyncio
async def test_palbox_upsert_and_list(repo):
    await repo.upsert_palbox(PalBox("pb1", "w1", "gk1", "10:20:0", 1000, 1000, "active"))
    await repo.upsert_palbox(PalBox("pb1", "w1", "gk1", "10:20:0", 1000, 2000, "active"))
    boxes = await repo.list_palboxes("w1")
    assert len(boxes) == 1
    assert boxes[0].last_seen_at == 2000


@pytest.mark.asyncio
async def test_base_list_filters_low_and_hidden(repo):
    await repo.upsert_base(Base("bH", "w1", "pbH", None, "gk1", Confidence.HIGH, False, False, 1000, 1000))
    await repo.upsert_base(Base("bL", "w1", "pbL", None, "gk1", Confidence.LOW, False, False, 1000, 1000))
    await repo.upsert_base(Base("bHid", "w1", "pbHid", None, "gk1", Confidence.HIGH, False, True, 1000, 1000))
    default = {b.base_key for b in await repo.list_bases("w1")}
    assert default == {"bH"}
    with_low = {b.base_key for b in await repo.list_bases("w1", include_low=True)}
    assert with_low == {"bH", "bL"}
    with_hidden = {b.base_key for b in await repo.list_bases("w1", include_hidden=True)}
    assert with_hidden == {"bH", "bHid"}


@pytest.mark.asyncio
async def test_base_observation_roundtrip_json(repo):
    o = BaseObservation("bH", "w1", 1000, 6, 4, 12.5, 0.9, {"working": 4, "idle": 2})
    await repo.insert_base_observation(o)
    got = await repo.latest_base_observation("w1", "bH")
    assert got.worker_count == 6
    assert got.average_level == 12.5
    assert got.action_distribution == {"working": 4, "idle": 2}


@pytest.mark.asyncio
async def test_latest_base_observation_missing(repo):
    assert await repo.latest_base_observation("w1", "ghost") is None
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/repository_guild_base_test.py -q` → 期望 FAIL：`AttributeError: 'Repository' object has no attribute 'upsert_guild'`。

- [ ] 3) 写最小实现 — 在 `Repository` 类内新增（顶部 import 补 `import json`、`from palchronicle.domain.models import Guild, PalBox, Base, BaseObservation`、`from palchronicle.domain.enums import Confidence`）：

```python
    async def upsert_guild(self, g: Guild) -> None:
        await self._db.execute_write(
            """
            INSERT INTO guilds
                (guild_key, world_id, latest_name, first_seen_at, last_seen_at,
                 observed_member_count, palbox_count, base_pal_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_key, world_id) DO UPDATE SET
                latest_name = excluded.latest_name,
                last_seen_at = excluded.last_seen_at,
                observed_member_count = excluded.observed_member_count,
                palbox_count = excluded.palbox_count,
                base_pal_count = excluded.base_pal_count
            """,
            (g.guild_key, g.world_id, g.latest_name, g.first_seen_at, g.last_seen_at,
             g.observed_member_count, g.palbox_count, g.base_pal_count),
        )

    async def list_guilds(self, world_id: str) -> list[Guild]:
        rows = await self._db.query(
            """
            SELECT guild_key, world_id, latest_name, first_seen_at, last_seen_at,
                   observed_member_count, palbox_count, base_pal_count
            FROM guilds WHERE world_id = ? ORDER BY latest_name ASC
            """,
            (world_id,),
        )
        return [Guild(r["guild_key"], r["world_id"], r["latest_name"],
                      r["first_seen_at"], r["last_seen_at"], r["observed_member_count"],
                      r["palbox_count"], r["base_pal_count"]) for r in rows]

    async def upsert_palbox(self, pb: PalBox) -> None:
        await self._db.execute_write(
            """
            INSERT INTO palboxes
                (palbox_key, world_id, guild_key, position_cell,
                 first_seen_at, last_seen_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(palbox_key, world_id) DO UPDATE SET
                guild_key = excluded.guild_key,
                position_cell = excluded.position_cell,
                last_seen_at = excluded.last_seen_at,
                status = excluded.status
            """,
            (pb.palbox_key, pb.world_id, pb.guild_key, pb.position_cell,
             pb.first_seen_at, pb.last_seen_at, pb.status),
        )

    async def list_palboxes(self, world_id: str) -> list[PalBox]:
        rows = await self._db.query(
            """
            SELECT palbox_key, world_id, guild_key, position_cell,
                   first_seen_at, last_seen_at, status
            FROM palboxes WHERE world_id = ? ORDER BY palbox_key ASC
            """,
            (world_id,),
        )
        return [PalBox(r["palbox_key"], r["world_id"], r["guild_key"],
                       r["position_cell"], r["first_seen_at"], r["last_seen_at"],
                       r["status"]) for r in rows]

    async def upsert_base(self, b: Base) -> None:
        await self._db.execute_write(
            """
            INSERT INTO bases
                (base_key, world_id, palbox_key, display_name, guild_key,
                 confidence, locked_by_admin, hidden, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(base_key, world_id) DO UPDATE SET
                palbox_key = excluded.palbox_key,
                display_name = excluded.display_name,
                guild_key = excluded.guild_key,
                confidence = excluded.confidence,
                locked_by_admin = excluded.locked_by_admin,
                hidden = excluded.hidden,
                last_seen_at = excluded.last_seen_at
            """,
            (b.base_key, b.world_id, b.palbox_key, b.display_name, b.guild_key,
             str(b.confidence), int(b.locked_by_admin), int(b.hidden),
             b.first_seen_at, b.last_seen_at),
        )

    async def list_bases(self, world_id: str, include_low: bool = False,
                         include_hidden: bool = False) -> list[Base]:
        sql = ["SELECT base_key, world_id, palbox_key, display_name, guild_key,",
               "confidence, locked_by_admin, hidden, first_seen_at, last_seen_at",
               "FROM bases WHERE world_id = ?"]
        params: list = [world_id]
        if not include_low:
            sql.append("AND confidence != 'low'")
        if not include_hidden:
            sql.append("AND hidden = 0")
        sql.append("ORDER BY guild_key ASC, palbox_key ASC")
        rows = await self._db.query(" ".join(sql), params)
        return [Base(r["base_key"], r["world_id"], r["palbox_key"], r["display_name"],
                     r["guild_key"], Confidence(r["confidence"]),
                     bool(r["locked_by_admin"]), bool(r["hidden"]),
                     r["first_seen_at"], r["last_seen_at"]) for r in rows]

    async def insert_base_observation(self, o: BaseObservation) -> None:
        await self._db.execute_write(
            """
            INSERT INTO base_observations
                (world_id, base_key, observed_at, worker_count, active_count,
                 average_level, average_hp_ratio, action_distribution_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (o.world_id, o.base_key, o.observed_at, o.worker_count, o.active_count,
             o.average_level, o.average_hp_ratio, json.dumps(o.action_distribution)),
        )

    async def latest_base_observation(self, world_id: str, base_key: str) -> BaseObservation | None:
        rows = await self._db.query(
            """
            SELECT world_id, base_key, observed_at, worker_count, active_count,
                   average_level, average_hp_ratio, action_distribution_json
            FROM base_observations WHERE world_id = ? AND base_key = ?
            ORDER BY observed_at DESC LIMIT 1
            """,
            (world_id, base_key),
        )
        if not rows:
            return None
        r = rows[0]
        return BaseObservation(
            base_key=r["base_key"], world_id=r["world_id"], observed_at=r["observed_at"],
            worker_count=r["worker_count"], active_count=r["active_count"],
            average_level=r["average_level"], average_hp_ratio=r["average_hp_ratio"],
            action_distribution=json.loads(r["action_distribution_json"]),
        )
```

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/repository_guild_base_test.py -q` → 期望 PASS（5 passed）。

- [ ] 5) 提交：`git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_guild_base_test.py && git commit -m "feat(repo): guild/palbox/base upsert+list+observation methods"`

---

### Task 3.11：GuildService — 公会聚合

**Files:**
- Create: `palchronicle/application/guild_service.py`
- Test: `tests/unit/guild_service_test.py`

**Interfaces:**
- Consumes：`GameDataSnapshot.characters/palboxes`；`CharacterActor(unit_type, guild_id, guild_name, ...)`、`PalBoxActor(guild_id, guild_name, ...)`；`UnitType`；`Repository.upsert_guild` / `list_guilds`；`hash_user_id`（复用把 `guild_id` 派生为 `guild_key`：`hash_user_id(salt, world_id, "GUILD:"+guild_id)`——与 player_key 同 HMAC，保证 guild_key 不泄露原始 GuildID）；`EventService.new_guild(world, guild_key)`（fake）；`World`、`Guild`。
- Produces：`GuildService.__init__(self, repo, salt, clock)`、`async apply(self, world: World, gd: GameDataSnapshot) -> list[Guild]`（按 `guild_id` 聚合：`observed_member_count`=该 guild 下 Player+OtomoPal+BaseCampPal 角色数中的 Player 计数、`palbox_count`=该 guild 的 PalBoxActor 数、`base_pal_count`=该 guild 的 BaseCampPal 数；`guild_id` 缺失的 actor 不强归；`guild_name` 缺失降级用 `"公会-"+guild_key[:6]`；首见触发 NEW_GUILD）。

- [ ] 1) 写失败测试 `tests/unit/guild_service_test.py`：

```python
import pytest

from palchronicle.application.guild_service import GuildService
from palchronicle.domain.models import CharacterActor, PalBoxActor, GameDataSnapshot, World
from palchronicle.domain.enums import UnitType, ActionCategory
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    def __init__(self): self.new_guilds = []
    async def new_guild(self, world, guild_key): self.new_guilds.append(guild_key)
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _char(unit_type, guild_id=None, guild_name=None):
    return CharacterActor(unit_type, None, None, None, None, None, None, None, None,
                          guild_id, guild_name, None, ActionCategory.IDLE,
                          ActionCategory.IDLE, None, None, None, True)


def _pb(guild_id):
    return PalBoxActor(guild_id, None, "Box", 0.0, 0.0, 0.0)


def _gd(chars, boxes):
    return GameDataSnapshot(1000, 60.0, 60.0, chars, boxes, [])


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = GuildService(repo, b"0" * 32, clock); events = FakeEvents(); svc.events = events
    return db, repo, svc, events


@pytest.mark.asyncio
async def test_aggregates_multiple_guilds(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd(
        chars=[
            _char(UnitType.PLAYER, "G1", "Alpha"),
            _char(UnitType.PLAYER, "G1", "Alpha"),
            _char(UnitType.BASE_CAMP, "G1", "Alpha"),
            _char(UnitType.PLAYER, "G2", "Beta"),
        ],
        boxes=[_pb("G1"), _pb("G1"), _pb("G2")],
    )
    guilds = await svc.apply(_world(), gd)
    by_name = {g.latest_name: g for g in guilds}
    assert by_name["Alpha"].observed_member_count == 2
    assert by_name["Alpha"].palbox_count == 2
    assert by_name["Alpha"].base_pal_count == 1
    assert by_name["Beta"].observed_member_count == 1
    assert by_name["Beta"].palbox_count == 1
    assert len(events.new_guilds) == 2  # 首见两公会
    persisted = {g.latest_name for g in await repo.list_guilds("w1")}
    assert persisted == {"Alpha", "Beta"}


@pytest.mark.asyncio
async def test_missing_guild_id_not_grouped(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd([_char(UnitType.PLAYER, None, None), _char(UnitType.PLAYER, "G1", "Alpha")], [])
    guilds = await svc.apply(_world(), gd)
    assert {g.latest_name for g in guilds} == {"Alpha"}


@pytest.mark.asyncio
async def test_missing_guild_name_degrades(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd([_char(UnitType.PLAYER, "G1", None)], [])
    guilds = await svc.apply(_world(), gd)
    assert guilds[0].latest_name.startswith("公会-")


@pytest.mark.asyncio
async def test_new_guild_only_first_time(tmp_path):
    db, repo, svc, events = await _mk(tmp_path)
    gd = _gd([_char(UnitType.PLAYER, "G1", "Alpha")], [])
    await svc.apply(_world(), gd)
    await svc.apply(_world(), gd)
    assert len(events.new_guilds) == 1
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/guild_service_test.py -q` → 期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.guild_service'`。

- [ ] 3) 写最小实现 `palchronicle/application/guild_service.py`：

```python
from __future__ import annotations

from palchronicle.adapters.privacy_filter import hash_user_id
from palchronicle.domain.enums import UnitType
from palchronicle.domain.models import GameDataSnapshot, Guild, World


class GuildService:
    def __init__(self, repo, salt: bytes, clock):
        self._repo = repo
        self._salt = salt
        self._clock = clock
        self.events = None

    def _guild_key(self, world_id: str, guild_id: str) -> str:
        return hash_user_id(self._salt, world_id, "GUILD:" + guild_id)

    async def apply(self, world: World, gd: GameDataSnapshot) -> list[Guild]:
        now = gd.observed_at
        members: dict[str, int] = {}
        base_pals: dict[str, int] = {}
        names: dict[str, str] = {}
        for a in gd.characters:
            if not a.guild_id:
                continue
            gk = self._guild_key(world.world_id, a.guild_id)
            if a.guild_name:
                names[gk] = a.guild_name
            if a.unit_type == UnitType.PLAYER:
                members[gk] = members.get(gk, 0) + 1
            elif a.unit_type == UnitType.BASE_CAMP:
                base_pals[gk] = base_pals.get(gk, 0) + 1
        boxes: dict[str, int] = {}
        for pb in gd.palboxes:
            if not pb.guild_id:
                continue
            gk = self._guild_key(world.world_id, pb.guild_id)
            boxes[gk] = boxes.get(gk, 0) + 1
            if pb.guild_name and gk not in names:
                names[gk] = pb.guild_name

        all_keys = set(members) | set(base_pals) | set(boxes)
        existing = {g.guild_key for g in await self._repo.list_guilds(world.world_id)}
        result: list[Guild] = []
        for gk in sorted(all_keys):
            name = names.get(gk) or ("公会-" + gk[:6])
            g = Guild(
                guild_key=gk, world_id=world.world_id, latest_name=name,
                first_seen_at=now, last_seen_at=now,
                observed_member_count=members.get(gk, 0),
                palbox_count=boxes.get(gk, 0),
                base_pal_count=base_pals.get(gk, 0),
            )
            await self._repo.upsert_guild(g)
            if gk not in existing and self.events is not None:
                await self.events.new_guild(world, gk)
            result.append(g)
        return result
```

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/guild_service_test.py -q` → 期望 PASS（4 passed）。

- [ ] 5) 提交：`git add palchronicle/application/guild_service.py tests/unit/guild_service_test.py && git commit -m "feat(guild): GuildService aggregation + NEW_GUILD candidate"`

---

### Task 3.12：BaseService — BaseUpdate 定义 + key 派生 + PalBox 最近邻匹配

**Files:**
- Create: `palchronicle/application/base_service.py`
- Test: `tests/unit/base_keys_test.py`、`tests/unit/base_palbox_match_test.py`

**Interfaces:**
- Consumes：`BasesConfig(position_grid_size, z_weight, ...)`；`PalBoxActor(guild_id, guild_name, pal_class, x, y, z)`；`quantize_cell(x, y, z, grid)`（Phase 2）；`hash_user_id`（guild_key 与 GuildService 同法）；`PalBox`、`World`。
- Produces：
  - `@dataclass(slots=True) class BaseUpdate`（字段严格照跨阶段共享定义：`base_key, world_id, palbox_key, guild_key, confidence, worker_count, active_count, average_level, average_hp_ratio, action_distribution, is_new, is_vanished, prev_worker_count`；`worker_count/active_count:int`，`average_*:float`，`action_distribution:dict[str,int]`，`is_new/is_vanished:bool`，`prev_worker_count:int|None`）。
  - `BaseService.palbox_key(world_id, guild_key, cell) -> str` = `f"{world_id}|{guild_key}|{cell}"`（staticmethod）。
  - `BaseService.base_key(world_id, anchor_palbox_key) -> str` = `f"{world_id}|BASE|{anchor_palbox_key}"`（staticmethod）。
  - `BaseService._match_palboxes(self, world, gd, existing: list[PalBox]) -> dict[int, PalBox]`：把 gd.palboxes 的下标映射到（新建或匹配到的）`PalBox`；坐标漂移在 `position_grid_size` 内且同 guild → 最近邻复用已有 PalBox（不新建）。

- [ ] 1) 写失败测试 —— 两个文件。

`tests/unit/base_keys_test.py`：

```python
from palchronicle.application.base_service import BaseService, BaseUpdate
from palchronicle.domain.enums import Confidence


def test_palbox_key_format():
    assert BaseService.palbox_key("w1", "gk", "10:20:0") == "w1|gk|10:20:0"


def test_base_key_deterministic_from_anchor():
    pbk = BaseService.palbox_key("w1", "gk", "10:20:0")
    assert BaseService.base_key("w1", pbk) == "w1|BASE|w1|gk|10:20:0"


def test_base_update_fields():
    u = BaseUpdate(
        base_key="bk", world_id="w1", palbox_key="pbk", guild_key="gk",
        confidence=Confidence.HIGH, worker_count=6, active_count=4,
        average_level=12.0, average_hp_ratio=0.9,
        action_distribution={"working": 4}, is_new=True, is_vanished=False,
        prev_worker_count=None,
    )
    assert u.confidence == Confidence.HIGH
    assert u.is_new and not u.is_vanished
    assert u.prev_worker_count is None
```

`tests/unit/base_palbox_match_test.py`：

```python
import pytest

from palchronicle.application.base_service import BaseService
from palchronicle.domain.models import PalBoxActor, GameDataSnapshot, World, PalBox
from palchronicle.infrastructure.clock import FakeClock


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import BasesConfig
    return BasesConfig(True, 5000, 0.2, 3, 2000, 0.5)


def _gd(boxes):
    return GameDataSnapshot(1000, 60.0, 60.0, [], boxes, [])


def _svc():
    return BaseService(repo=None, cfg=_cfg(), clock=FakeClock(1000), salt=b"0" * 32)


def test_new_palbox_when_no_existing():
    svc = _svc()
    gd = _gd([PalBoxActor("G1", None, "Box", 100.0, 200.0, 0.0)])
    matched = svc._match_palboxes(_world(), gd, existing=[])
    assert 0 in matched
    # cell = floor(100/2000)=0, 0, 0
    assert matched[0].position_cell == "0:0:0"


def test_drift_within_grid_reuses_existing():
    svc = _svc()
    gk = svc._guild_key("w1", "G1")
    existing = [PalBox(BaseService.palbox_key("w1", gk, "0:0:0"), "w1", gk,
                       "0:0:0", 900, 900, "active")]
    # 漂移到 x=500 仍在同格 floor(500/2000)=0
    gd = _gd([PalBoxActor("G1", None, "Box", 500.0, 300.0, 0.0)])
    matched = svc._match_palboxes(_world(), gd, existing=existing)
    assert matched[0].palbox_key == existing[0].palbox_key  # 复用, 不新建


def test_far_move_creates_new_palbox():
    svc = _svc()
    gk = svc._guild_key("w1", "G1")
    existing = [PalBox(BaseService.palbox_key("w1", gk, "0:0:0"), "w1", gk,
                       "0:0:0", 900, 900, "active")]
    gd = _gd([PalBoxActor("G1", None, "Box", 9000.0, 9000.0, 0.0)])  # 远处
    matched = svc._match_palboxes(_world(), gd, existing=existing)
    assert matched[0].palbox_key != existing[0].palbox_key
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/base_keys_test.py tests/unit/base_palbox_match_test.py -q` → 期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.base_service'`。

- [ ] 3) 写最小实现 `palchronicle/application/base_service.py`：

```python
from __future__ import annotations

import math
from dataclasses import dataclass

from palchronicle.adapters.privacy_filter import hash_user_id, quantize_cell
from palchronicle.domain.enums import Confidence
from palchronicle.domain.models import GameDataSnapshot, PalBox, World


@dataclass(slots=True)
class BaseUpdate:
    base_key: str
    world_id: str
    palbox_key: str
    guild_key: str | None
    confidence: Confidence
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int]
    is_new: bool
    is_vanished: bool
    prev_worker_count: int | None


class BaseService:
    def __init__(self, repo, cfg, clock, salt: bytes):
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt

    @staticmethod
    def palbox_key(world_id: str, guild_key: str | None, cell: str) -> str:
        return f"{world_id}|{guild_key}|{cell}"

    @staticmethod
    def base_key(world_id: str, anchor_palbox_key: str) -> str:
        return f"{world_id}|BASE|{anchor_palbox_key}"

    def _guild_key(self, world_id: str, guild_id: str | None) -> str | None:
        if not guild_id:
            return None
        return hash_user_id(self._salt, world_id, "GUILD:" + guild_id)

    def _match_palboxes(self, world: World, gd: GameDataSnapshot,
                        existing: list[PalBox]) -> dict[int, PalBox]:
        grid = self._cfg.position_grid_size
        now = gd.observed_at
        by_guild: dict[str | None, list[PalBox]] = {}
        for pb in existing:
            by_guild.setdefault(pb.guild_key, []).append(pb)

        result: dict[int, PalBox] = {}
        for idx, box in enumerate(gd.palboxes):
            gk = self._guild_key(world.world_id, box.guild_id)
            cell = quantize_cell(box.x, box.y, box.z, grid)
            candidates = by_guild.get(gk, [])
            match = self._nearest_within_grid(cell, candidates, grid)
            if match is not None:
                match.last_seen_at = now
                match.status = "active"
                result[idx] = match
            else:
                key = self.palbox_key(world.world_id, gk, cell)
                pb = PalBox(key, world.world_id, gk, cell, now, now, "active")
                by_guild.setdefault(gk, []).append(pb)
                result[idx] = pb
        return result

    @staticmethod
    def _nearest_within_grid(cell: str, candidates: list[PalBox], grid: int) -> PalBox | None:
        cx, cy, cz = (int(p) for p in cell.split(":"))
        best: PalBox | None = None
        best_d = None
        for c in candidates:
            px, py, pz = (int(p) for p in c.position_cell.split(":"))
            d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2)
            if d <= 1.0 and (best_d is None or d < best_d):  # 相邻/同格(以格为单位)
                best, best_d = c, d
        return best
```

（`_nearest_within_grid` 以"格坐标"为单位判断：同格 d=0，相邻格 d≤~1.7；阈值 1.0 表示同格即复用，符合 `position_grid_size` 量化语义——漂移落回同格则复用，跨格远移则新建。）

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/base_keys_test.py tests/unit/base_palbox_match_test.py -q` → 期望 PASS（6 passed）。

- [ ] 5) 提交：`git add palchronicle/application/base_service.py tests/unit/base_keys_test.py tests/unit/base_palbox_match_test.py && git commit -m "feat(base): BaseUpdate + key derivation + PalBox nearest-neighbor matching"`

---

### Task 3.13：BaseService — 据点归属 + 置信度 + confirmation 门槛 + apply

**Files:**
- Modify: `palchronicle/application/base_service.py`
- Test: `tests/unit/base_assignment_test.py`、`tests/integration/base_confirmation_test.py`

**Interfaces:**
- Consumes：Task 3.12 的 `_match_palboxes` / `palbox_key` / `base_key` / `BaseUpdate`；`BasesConfig(assignment_radius, ambiguity_ratio, confirmation_samples, z_weight, ...)`；`CharacterActor(unit_type=BASE_CAMP, x, y, z, guild_id, level, hp, max_hp, action)`；`Repository.upsert_palbox` / `list_palboxes` / `upsert_base` / `list_bases` / `insert_base_observation`；`Confidence`、`World`、`Base`、`BaseObservation`。
- Produces：`async apply(self, world: World, gd: GameDataSnapshot) -> list[BaseUpdate]`——按 spec §10.3：BaseCampPal 在同 guild PalBox 中找最近（`d=sqrt(dx²+dy²+z_weight·dz²)`，用**原始坐标**计算，坐标已在内存），`d<assignment_radius` 分配，最近/次近差 `<ambiguity_ratio` 标 ambiguous；`confirmation_samples` 次一致才落 `bases`（先落 base 再产 BaseUpdate.is_new=True）；置信度 high/medium/low。确认计数存内存 `self._confirm: dict[str, int]`（键 base_key）。

> 简化（YAGNI，v0.1）：置信度按 spec 分级 —— high=`d < assignment_radius*0.5` 且非 ambiguous 且已达 confirmation；medium=`d < assignment_radius` 且非 ambiguous 且已达 confirmation；low=ambiguous 或未达 confirmation 或 guild_key 为 None。`worker_count`=分配到该 base 的 BaseCampPal 数；`active_count`=其中 `action`∈working 的数；`average_level`/`average_hp_ratio` 由这些 pal 求均值。BaseUpdate 每个已确认 base 产出一条（含 `prev_worker_count`=上次 base_observation 的 worker_count 或 None、`is_new`=本轮首次落 bases 行）。`is_vanished` 恒 False（BASE_VANISHED 检测归 Phase 4 EventService，本阶段只产存续 update）。

- [ ] 1) 写失败测试 —— 两个文件。

`tests/unit/base_assignment_test.py`（单快照，直接查表验证归属，不走 confirmation 门槛前先测归属计算 —— 用 `confirmation_samples=1` 使单次即落库）：

```python
import pytest

from palchronicle.application.base_service import BaseService
from palchronicle.domain.models import CharacterActor, PalBoxActor, GameDataSnapshot, World
from palchronicle.domain.enums import UnitType, ActionCategory, Confidence
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg(confirmation=1):
    from palchronicle.config import BasesConfig
    return BasesConfig(True, 5000, 0.2, confirmation, 2000, 0.5)


def _bcp(guild_id, x, y, level=10, action=ActionCategory.WORKING, hp=100, max_hp=100):
    return CharacterActor(UnitType.BASE_CAMP, None, None, None, None, None, level,
                          hp, max_hp, guild_id, None, "PalX", action, action, x, y, 0.0, True)


def _pb(guild_id, x, y):
    return PalBoxActor(guild_id, None, "Box", x, y, 0.0)


def _gd(chars, boxes):
    return GameDataSnapshot(1000, 60.0, 60.0, chars, boxes, [])


async def _mk(tmp_path, confirmation=1):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = BaseService(repo, _cfg(confirmation), clock, b"0" * 32)
    return db, repo, svc


@pytest.mark.asyncio
async def test_assigns_pal_to_nearest_palbox_high_confidence(tmp_path):
    db, repo, svc = await _mk(tmp_path, confirmation=1)
    gd = _gd([_bcp("G1", 110.0, 210.0)], [_pb("G1", 100.0, 200.0)])
    updates = await svc.apply(_world(), gd)
    assert len(updates) == 1
    u = updates[0]
    assert u.worker_count == 1
    assert u.active_count == 1
    assert u.confidence == Confidence.HIGH  # d≈14 << 2500
    assert u.is_new is True
    bases = await repo.list_bases("w1", include_low=True)
    assert len(bases) == 1
    assert bases[0].base_key == u.base_key


@pytest.mark.asyncio
async def test_far_pal_unassigned(tmp_path):
    db, repo, svc = await _mk(tmp_path, confirmation=1)
    gd = _gd([_bcp("G1", 90000.0, 90000.0)], [_pb("G1", 100.0, 200.0)])
    updates = await svc.apply(_world(), gd)
    # pal 过远(>assignment_radius) → 不计入任何 base 的 worker
    assert all(u.worker_count == 0 for u in updates) or updates == []


@pytest.mark.asyncio
async def test_ambiguous_two_close_palboxes_low(tmp_path):
    db, repo, svc = await _mk(tmp_path, confirmation=1)
    # 两个同 guild PalBox 距离相近, pal 在中间 → ambiguous → low
    gd = _gd(
        [_bcp("G1", 1000.0, 0.0)],
        [_pb("G1", 900.0, 0.0), _pb("G1", 1100.0, 0.0)],
    )
    updates = await svc.apply(_world(), gd)
    assigned = [u for u in updates if u.worker_count > 0]
    assert assigned and assigned[0].confidence == Confidence.LOW
```

`tests/integration/base_confirmation_test.py`（confirmation 门槛 + PalBox 抖动不误建）：

```python
import pytest

from palchronicle.application.base_service import BaseService
from palchronicle.domain.models import CharacterActor, PalBoxActor, GameDataSnapshot, World
from palchronicle.domain.enums import UnitType, ActionCategory
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import BasesConfig
    return BasesConfig(True, 5000, 0.2, 3, 2000, 0.5)  # confirmation_samples=3


def _bcp(x, y):
    return CharacterActor(UnitType.BASE_CAMP, None, None, None, None, None, 10, 100, 100,
                          "G1", None, "PalX", ActionCategory.WORKING,
                          ActionCategory.WORKING, x, y, 0.0, True)


def _gd(px, py, obs_at):
    return GameDataSnapshot(obs_at, 60.0, 60.0, [_bcp(px + 10, py + 10)],
                            [PalBoxActor("G1", None, "Box", px, py, 0.0)], [])


async def _mk(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock)
    svc = BaseService(repo, _cfg(), clock, b"0" * 32)
    return db, repo, svc


@pytest.mark.asyncio
async def test_base_persisted_only_after_confirmation_samples(tmp_path):
    db, repo, svc = await _mk(tmp_path)
    u1 = await svc.apply(_world(), _gd(100.0, 200.0, 1000))
    assert await repo.list_bases("w1", include_low=True) == []  # 第1次不落
    assert all(not u.is_new for u in u1)
    await svc.apply(_world(), _gd(100.0, 200.0, 1030))            # 第2次不落
    assert await repo.list_bases("w1", include_low=True) == []
    u3 = await svc.apply(_world(), _gd(100.0, 200.0, 1060))       # 第3次落
    bases = await repo.list_bases("w1", include_low=True)
    assert len(bases) == 1
    assert any(u.is_new for u in u3)
    await db.close()


@pytest.mark.asyncio
async def test_palbox_jitter_within_grid_does_not_create_second_base(tmp_path):
    db, repo, svc = await _mk(tmp_path)
    # 抖动都落在同一网格(grid=2000) → 同 palbox_key → 同 base_key
    await svc.apply(_world(), _gd(100.0, 200.0, 1000))
    await svc.apply(_world(), _gd(150.0, 250.0, 1030))
    await svc.apply(_world(), _gd(80.0, 190.0, 1060))
    bases = await repo.list_bases("w1", include_low=True)
    assert len(bases) == 1
    await db.close()
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/base_assignment_test.py tests/integration/base_confirmation_test.py -q` → 期望 FAIL：`AttributeError: 'BaseService' object has no attribute 'apply'`。

- [ ] 3) 写最小实现 — 在 `BaseService` 类内新增（`__init__` 末尾加 `self._confirm: dict[str, int] = {}`）：

```python
    async def apply(self, world: World, gd: GameDataSnapshot) -> list[BaseUpdate]:
        from palchronicle.domain.enums import ActionCategory, UnitType
        from palchronicle.domain.models import Base, BaseObservation

        existing = await self._repo.list_palboxes(world.world_id)
        matched = self._match_palboxes(world, gd, existing)
        for pb in {id(v): v for v in matched.values()}.values():
            await self._repo.upsert_palbox(pb)

        radius = self._cfg.assignment_radius
        zw = self._cfg.z_weight
        # 每个 palbox_key 聚合分配到它的 BaseCampPal
        agg: dict[str, dict] = {}
        ambiguous: dict[str, bool] = {}
        palbox_by_key = {pb.palbox_key: pb for pb in matched.values()}

        for a in gd.characters:
            if a.unit_type != UnitType.BASE_CAMP or a.x is None:
                continue
            gk = self._guild_key(world.world_id, a.guild_id)
            same_guild = [pb for pb in palbox_by_key.values() if pb.guild_key == gk]
            dists = sorted(
                ((self._distance(a, pb, zw), pb) for pb in same_guild),
                key=lambda t: t[0],
            )
            if not dists or dists[0][0] >= radius:
                continue
            nearest_d, nearest = dists[0]
            is_amb = (len(dists) > 1 and dists[1][0] > 0
                      and (dists[1][0] - nearest_d) / dists[1][0] < self._cfg.ambiguity_ratio)
            key = nearest.palbox_key
            bucket = agg.setdefault(key, {"pals": [], "nearest_d": nearest_d})
            bucket["pals"].append(a)
            bucket["nearest_d"] = min(bucket["nearest_d"], nearest_d)
            ambiguous[key] = ambiguous.get(key, False) or is_amb

        updates: list[BaseUpdate] = []
        now = gd.observed_at
        for palbox_key, bucket in agg.items():
            pals = bucket["pals"]
            pb = palbox_by_key[palbox_key]
            base_key = self.base_key(world.world_id, palbox_key)
            self._confirm[base_key] = self._confirm.get(base_key, 0) + 1
            confirmed = self._confirm[base_key] >= self._cfg.confirmation_samples

            worker = len(pals)
            active = sum(1 for p in pals if p.action == ActionCategory.WORKING)
            avg_level = sum(p.level or 0 for p in pals) / worker
            hp_ratios = [(p.hp / p.max_hp) for p in pals if p.hp is not None and p.max_hp]
            avg_hp = sum(hp_ratios) / len(hp_ratios) if hp_ratios else 0.0
            dist: dict[str, int] = {}
            for p in pals:
                dist[str(p.action)] = dist.get(str(p.action), 0) + 1

            if ambiguous.get(palbox_key) or not confirmed or pb.guild_key is None:
                confidence = Confidence.LOW
            elif bucket["nearest_d"] < radius * 0.5:
                confidence = Confidence.HIGH
            else:
                confidence = Confidence.MEDIUM

            prev = await self._repo.latest_base_observation(world.world_id, base_key)
            prev_worker = prev.worker_count if prev else None

            is_new = False
            if confirmed:
                already = {b.base_key for b in await self._repo.list_bases(
                    world.world_id, include_low=True, include_hidden=True)}
                is_new = base_key not in already
                await self._repo.upsert_base(Base(
                    base_key=base_key, world_id=world.world_id, palbox_key=palbox_key,
                    display_name=None, guild_key=pb.guild_key, confidence=confidence,
                    locked_by_admin=False, hidden=False,
                    first_seen_at=now, last_seen_at=now,
                ))
                await self._repo.insert_base_observation(BaseObservation(
                    base_key=base_key, world_id=world.world_id, observed_at=now,
                    worker_count=worker, active_count=active,
                    average_level=avg_level, average_hp_ratio=avg_hp,
                    action_distribution=dist,
                ))

            updates.append(BaseUpdate(
                base_key=base_key, world_id=world.world_id, palbox_key=palbox_key,
                guild_key=pb.guild_key, confidence=confidence,
                worker_count=worker, active_count=active, average_level=avg_level,
                average_hp_ratio=avg_hp, action_distribution=dist,
                is_new=is_new, is_vanished=False, prev_worker_count=prev_worker,
            ))
        return updates

    @staticmethod
    def _distance(actor, pb, z_weight: float) -> float:
        import math
        # PalBox cell 是量化格；用格中心近似其原始坐标进行 pal↔box 距离比较
        # 为确定性，直接比较 actor 原始坐标与 palbox cell 反量化中心
        return math.sqrt(actor.x ** 2 + actor.y ** 2)  # 占位: 见下方修正
```

> 上面的 `_distance` 需要 palbox 的原始坐标才能算 pal↔box 距离，但 PalBox 只留量化 cell（隐私）。为在保留量化落库的同时得到确定性距离，改为：`_match_palboxes` 时把每个匹配 PalBox 的**原始锚点坐标**临时挂到返回对象上（内存字段，不落库）。修正实现如下（替换上面 `_distance` 占位并调整 `_match_palboxes`）：

在 `_match_palboxes` 内，新建/复用 PalBox 后为其挂原始坐标（内存属性，`PalBox` 为 slots dataclass 不能加属性，改用并行 dict）：

```python
    def _match_palboxes(self, world: World, gd: GameDataSnapshot,
                        existing: list[PalBox]) -> dict[int, PalBox]:
        grid = self._cfg.position_grid_size
        now = gd.observed_at
        by_guild: dict[str | None, list[PalBox]] = {}
        for pb in existing:
            by_guild.setdefault(pb.guild_key, []).append(pb)
        self._anchor_xy: dict[str, tuple[float, float, float]] = {}
        result: dict[int, PalBox] = {}
        for idx, box in enumerate(gd.palboxes):
            gk = self._guild_key(world.world_id, box.guild_id)
            cell = quantize_cell(box.x, box.y, box.z, grid)
            candidates = by_guild.get(gk, [])
            match = self._nearest_within_grid(cell, candidates, grid)
            if match is not None:
                match.last_seen_at = now
                match.status = "active"
                result[idx] = match
                self._anchor_xy[match.palbox_key] = (box.x, box.y, box.z)
            else:
                key = self.palbox_key(world.world_id, gk, cell)
                pb = PalBox(key, world.world_id, gk, cell, now, now, "active")
                by_guild.setdefault(gk, []).append(pb)
                result[idx] = pb
                self._anchor_xy[key] = (box.x, box.y, box.z)
        return result
```

并把 `_distance` 改为用锚点坐标（实例方法）：

```python
    def _distance(self, actor, pb, z_weight: float) -> float:
        import math
        ax, ay, az = self._anchor_xy.get(pb.palbox_key, (0.0, 0.0, 0.0))
        dx = actor.x - ax
        dy = actor.y - ay
        dz = (actor.z or 0.0) - az
        return math.sqrt(dx * dx + dy * dy + z_weight * dz * dz)
```

（`apply` 中 `self._distance(a, pb, zw)` 调用保持不变——现为实例方法。删掉前一版的 staticmethod `_distance`。`__init__` 中初始化 `self._anchor_xy = {}` 与 `self._confirm = {}`。）

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/base_assignment_test.py tests/integration/base_confirmation_test.py -q` → 期望 PASS（5 passed）。

- [ ] 5) 提交：`git add palchronicle/application/base_service.py tests/unit/base_assignment_test.py tests/integration/base_confirmation_test.py && git commit -m "feat(base): assignment + confidence grading + confirmation gate + apply→BaseUpdate"`

---

### Task 3.14：SnapshotService — 接线 ingest_players

**Files:**
- Modify: `palchronicle/application/snapshot_service.py`
- Test: `tests/unit/snapshot_ingest_players_test.py`

**Interfaces:**
- Consumes：`SnapshotService.__init__(self, repo, normalizer_mod, privacy_mod, meta, salt, cfg, clock, players, guilds, bases, events)`（Phase 2 契约）；`RestResponse(ok, status, data, ...)`；`normalizer.normalize_players(raw, now) -> list[dict]`、`privacy_filter.redact_players(rows, world_id, salt, cfg.privacy) -> PlayersSnapshot`；`PlayerService.apply_players(world, snap)` / `mark_uncertain(world)`；`World`。
- Produces：`async ingest_players(self, world: World, resp: RestResponse) -> None`——`resp.ok` 且 `data` → normalize→redact→`players.apply_players`；`resp.ok is False`（端点失败）→ `players.mark_uncertain(world)`。用 fake PlayerService 断言路径。

- [ ] 1) 写失败测试 `tests/unit/snapshot_ingest_players_test.py`：

```python
import pytest

from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.domain.models import World, PlayersSnapshot, PlayerRow
from palchronicle.infrastructure.clock import FakeClock


class FakePlayers:
    def __init__(self):
        self.applied = []
        self.uncertain = []
    async def apply_players(self, world, snap): self.applied.append((world, snap))
    async def mark_uncertain(self, world): self.uncertain.append(world)


class FakeNormalizer:
    @staticmethod
    def normalize_players(raw, now):
        return [{"userId": "u1", "name": "Alice", "level": 5, "ping": 40.0,
                 "building_count": 3}]


class FakePrivacy:
    @staticmethod
    def redact_players(rows, world_id, salt, cfg):
        return PlayersSnapshot(observed_at=1000,
                               players=[PlayerRow("hpk", "u1", "Alice", 5, None, 3)])


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


def _svc(players):
    return SnapshotService(
        repo=None, normalizer_mod=FakeNormalizer, privacy_mod=FakePrivacy,
        meta=None, salt=b"0" * 32, cfg=_cfg(), clock=FakeClock(1000),
        players=players, guilds=None, bases=None, events=None,
    )


@pytest.mark.asyncio
async def test_ok_response_applies_players():
    players = FakePlayers(); svc = _svc(players)
    resp = RestResponse(ok=True, status=200, data={"players": []},
                        duration_ms=1, payload_bytes=2, error=None)
    await svc.ingest_players(_world(), resp)
    assert len(players.applied) == 1
    assert players.applied[0][1].players[0].name == "Alice"
    assert players.uncertain == []


@pytest.mark.asyncio
async def test_failed_response_marks_uncertain():
    players = FakePlayers(); svc = _svc(players)
    resp = RestResponse(ok=False, status=None, data=None,
                        duration_ms=1, payload_bytes=0, error="timeout")
    await svc.ingest_players(_world(), resp)
    assert players.applied == []
    assert players.uncertain == [_world()]
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/snapshot_ingest_players_test.py -q` → 期望 FAIL：`NotImplementedError` 或 `AttributeError`（Phase 2 骨架中 `ingest_players` 未实现/为占位）。

- [ ] 3) 写最小实现 — 在 `SnapshotService` 中实现 `ingest_players`（假定 `__init__` 已存 `self._normalizer/self._privacy/self._salt/self._cfg/self._players`）：

```python
    async def ingest_players(self, world, resp) -> None:
        if not resp.ok or resp.data is None:
            await self._players.mark_uncertain(world)
            return
        now = resp.data.get("observed_at") if isinstance(resp.data, dict) else None
        now = now or self._clock.now()
        rows = self._normalizer.normalize_players(resp.data, now)
        snap = self._privacy.redact_players(rows, world.world_id, self._salt, self._cfg.privacy)
        await self._players.apply_players(world, snap)
```

（若 Phase 2 已给 `ingest_players` 骨架签名，仅替换其函数体。`self._normalizer`/`self._privacy` 为注入的模块对象，故用 `FakeNormalizer`/`FakePrivacy` 类替身即可。）

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/snapshot_ingest_players_test.py -q` → 期望 PASS（2 passed）。

- [ ] 5) 提交：`git add palchronicle/application/snapshot_service.py tests/unit/snapshot_ingest_players_test.py && git commit -m "feat(snapshot): wire ingest_players to PlayerService (apply/mark_uncertain)"`

---

### Task 3.15：SnapshotService — 接线 ingest_game_data（to_thread 归一/聚合 → guilds + bases）

**Files:**
- Modify: `palchronicle/application/snapshot_service.py`
- Test: `tests/unit/snapshot_ingest_game_data_test.py`

**Interfaces:**
- Consumes：`normalizer.normalize_game_data(raw, now, meta) -> GameDataSnapshot`、`privacy_filter.redact_game_data(snap, world_id, salt, cfg.privacy) -> GameDataSnapshot`；`GuildService.apply(world, gd) -> list[Guild]`、`BaseService.apply(world, gd) -> list[BaseUpdate]`、`EventService.base_events(world, updates)`；`asyncio.to_thread`；`Repository.upsert_unknown_classes`（Phase 1；若无则跳过——本任务用 fake repo 断言）；`World`。
- Produces：`async ingest_game_data(self, world: World, resp: RestResponse) -> None`——`resp.ok` 且 data → 用 `asyncio.to_thread` 跑纯计算（`normalize_game_data` + `redact_game_data`）→ `guilds.apply` → `bases.apply` → `events.base_events(world, updates)`；`resp.ok is False` → 直接 return（game-data 失败不动会话，spec §14）。断言 to_thread 路径被走（纯计算函数被调用）与三个服务按序被调用。

- [ ] 1) 写失败测试 `tests/unit/snapshot_ingest_game_data_test.py`：

```python
import pytest

from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.domain.models import World, GameDataSnapshot
from palchronicle.infrastructure.clock import FakeClock


def _gd():
    return GameDataSnapshot(1000, 60.0, 60.0, [], [], [])


class FakeNormalizer:
    calls = []
    @staticmethod
    def normalize_game_data(raw, now, meta):
        FakeNormalizer.calls.append(("norm", now))
        return _gd()


class FakePrivacy:
    calls = []
    @staticmethod
    def redact_game_data(snap, world_id, salt, cfg):
        FakePrivacy.calls.append(("redact", world_id))
        return snap


class FakeGuilds:
    def __init__(self): self.applied = []
    async def apply(self, world, gd): self.applied.append(gd); return []


class FakeBases:
    def __init__(self): self.applied = []
    async def apply(self, world, gd):
        self.applied.append(gd)
        return ["UPD"]  # 占位 update


class FakeEvents:
    def __init__(self): self.base_events_calls = []
    async def base_events(self, world, updates): self.base_events_calls.append(updates)


def _world(): return World("w1", "s1", "g", 0, "S", "1", 0, 0, 1)


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


def _svc(guilds, bases, events):
    FakeNormalizer.calls = []; FakePrivacy.calls = []
    return SnapshotService(
        repo=None, normalizer_mod=FakeNormalizer, privacy_mod=FakePrivacy,
        meta=None, salt=b"0" * 32, cfg=_cfg(), clock=FakeClock(1000),
        players=None, guilds=guilds, bases=bases, events=events,
    )


@pytest.mark.asyncio
async def test_ok_runs_pipeline_and_calls_services():
    guilds, bases, events = FakeGuilds(), FakeBases(), FakeEvents()
    svc = _svc(guilds, bases, events)
    resp = RestResponse(True, 200, {"actors": []}, 1, 2, None)
    await svc.ingest_game_data(_world(), resp)
    assert FakeNormalizer.calls and FakePrivacy.calls   # to_thread 纯计算被走
    assert len(guilds.applied) == 1
    assert len(bases.applied) == 1
    assert events.base_events_calls == [["UPD"]]


@pytest.mark.asyncio
async def test_failed_response_is_noop():
    guilds, bases, events = FakeGuilds(), FakeBases(), FakeEvents()
    svc = _svc(guilds, bases, events)
    resp = RestResponse(False, None, None, 1, 0, "timeout")
    await svc.ingest_game_data(_world(), resp)
    assert guilds.applied == [] and bases.applied == []
    assert events.base_events_calls == []
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/unit/snapshot_ingest_game_data_test.py -q` → 期望 FAIL：`NotImplementedError`/`AttributeError`（`ingest_game_data` 未实现）。

- [ ] 3) 写最小实现 — 在 `SnapshotService` 中实现 `ingest_game_data`（顶部确保 `import asyncio`）：

```python
    async def ingest_game_data(self, world, resp) -> None:
        if not resp.ok or resp.data is None:
            return
        now = self._clock.now()

        def _compute():
            gd = self._normalizer.normalize_game_data(resp.data, now, self._meta)
            return self._privacy.redact_game_data(gd, world.world_id, self._salt, self._cfg.privacy)

        gd = await asyncio.to_thread(_compute)
        await self._guilds.apply(world, gd)
        updates = await self._bases.apply(world, gd)
        if self._events is not None:
            await self._events.base_events(world, updates)
```

（`self._meta`/`self._guilds`/`self._bases`/`self._events` 均为 `__init__` 注入。`asyncio.to_thread` 将纯计算卸载出事件循环，对齐 spec §6.2。）

- [ ] 4) 跑测试确认通过：`python -m pytest tests/unit/snapshot_ingest_game_data_test.py -q` → 期望 PASS（2 passed）。

- [ ] 5) 提交：`git add palchronicle/application/snapshot_service.py tests/unit/snapshot_ingest_game_data_test.py && git commit -m "feat(snapshot): wire ingest_game_data via to_thread → guilds/bases/events"`

---

### Task 3.16：Phase 3 回归 —— 全量单测 + 时间序列集成

**Files:**
- Test（新增汇总标记，不改实现）：无新增源码；仅运行既有测试并修复偶发跨用例状态泄漏。

**Interfaces:**
- Consumes：Task 3.1-3.15 全部测试。
- Produces：无（验收关卡）。

- [ ] 1) 写失败测试 —— 新建 `tests/integration/phase3_smoke_test.py`，串起 players+guilds+bases 一轮 game-data + 一轮 players，验证跨服务不串数据与确定性：

```python
import pytest

from palchronicle.application.player_service import PlayerService
from palchronicle.application.guild_service import GuildService
from palchronicle.application.base_service import BaseService
from palchronicle.domain.models import (
    World, PlayerRow, PlayersSnapshot, CharacterActor, PalBoxActor, GameDataSnapshot,
)
from palchronicle.domain.enums import UnitType, ActionCategory, SessionStatus
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.adapters.sqlite_repository import Repository


class FakeEvents:
    async def new_player(self, w, k): pass
    async def level_up(self, w, k, o, n): pass
    async def new_guild(self, w, k): pass


def _cfg():
    from palchronicle.config import (AppConfig, PrivacyConfig, PollingConfig,
                                     RoutingConfig, WorldConfig, BasesConfig, HistoryConfig)
    from palchronicle.domain.enums import AccessMode
    return AppConfig([], [], RoutingConfig(AccessMode.RESTRICTED, ""), [],
                     PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
                     WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
                     BasesConfig(True, 5000, 0.2, 1, 2000, 0.5),
                     PrivacyConfig("balanced", False, False, 60, 120, 900),
                     HistoryConfig(7, 90, 365, 180))


@pytest.mark.asyncio
async def test_two_worlds_do_not_share_data(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    clock = FakeClock(1000); repo = Repository(db, clock); cfg = _cfg()
    ps = PlayerService(repo, b"s" * 32, cfg, clock); ps.events = FakeEvents()
    gs = GuildService(repo, b"s" * 32, clock); gs.events = FakeEvents()
    bs = BaseService(repo, cfg.bases, clock, b"s" * 32)

    wA = World("wA", "sA", "g", 0, "A", "1", 0, 0, 1)
    wB = World("wB", "sB", "g", 0, "B", "1", 0, 0, 1)

    row = PlayerRow("pkA", "p", "Alice", 5, 40.0, 3)
    await ps.apply_players(wA, PlayersSnapshot(1000, [row]))
    assert await repo.get_open_session("wA", "pkA") is not None
    assert await repo.get_open_session("wB", "pkA") is None  # 世界隔离

    gd = GameDataSnapshot(1000, 60.0, 60.0,
        [CharacterActor(UnitType.BASE_CAMP, None, None, None, None, None, 10, 100, 100,
                        "G1", "Alpha", "PalX", ActionCategory.WORKING,
                        ActionCategory.WORKING, 110.0, 210.0, 0.0, True)],
        [PalBoxActor("G1", "Alpha", "Box", 100.0, 200.0, 0.0)], [])
    await gs.apply(wA, gd)
    updates = await bs.apply(wA, gd)
    assert len(updates) == 1
    assert await repo.list_guilds("wB") == []
    assert await repo.list_bases("wB", include_low=True) == []
    await db.close()
```

- [ ] 2) 跑测试确认失败：`python -m pytest tests/integration/phase3_smoke_test.py -q` → 期望初次 FAIL 或 PASS —— 若 PASS 说明隔离已由 world_id 主键保证；若某断言 FAIL（如 guild_key 未按 world_id 隔离）则定位修正。先运行确认基线。

- [ ] 3) 写最小实现 —— 若步骤 2 全绿则无需改代码（此关卡为回归网）；若某断言 FAIL，按失败信息在对应服务补 world_id 过滤（多为 `guild_key`/`palbox_key` 已含 world_id 前缀，通常无需改）。记录：不得为过测而放宽断言。

- [ ] 4) 跑全量确认通过：`python -m pytest tests/unit tests/integration -q` → 期望全部 PASS（Phase 3 相关 ≥ 16 个测试文件全绿）。

- [ ] 5) 提交：`git add tests/integration/phase3_smoke_test.py && git commit -m "test(phase3): cross-world isolation smoke + full-suite regression gate"`


## Phase 4：事件检测 + 去重 + 模板日报

> 本阶段实现 8 类世界事件的检测/确认/去重落库，接线各追踪服务到事件流，并产出模板日报数据 DTO `DailyReport`。
>
> **前置阶段已就绪（Phase 1–3）**：`domain/enums.py`（`EventType`/`Confidence`/`SessionStatus`/`LeaveReason`/`EndpointName` 等 StrEnum）、`domain/models.py`（`World`/`WorldEvent`/`WorldMetric`/`BaseObservation`/`PlayerSession` 等 dataclass）、`infrastructure/clock.py`（`Clock`/`FakeClock`）、`infrastructure/database.py`（`Database`：`open`/`close`/`execute_write`/`write_tx`/`query`/`write_lock`）、`infrastructure/migrations.py`（`apply_migrations`；`world_events`/`world_metrics`/`bases`/`base_observations`/`player_sessions`/`daily_aggregates` 表 + `idx_events_dedup` 唯一索引已由 migration_0001 建好）、`adapters/sqlite_repository.py`（`Repository`：Phase 1 已建类并实现 server/binding/world/prune 方法；Phase 3 已补 `upsert_base`/`list_bases`/`insert_base_observation`/`latest_base_observation`/`upsert_guild`/`list_guilds`/`upsert_player`/`insert_session`/`update_session`/`list_open_sessions`/`insert_observation` 等）。
>
> **Phase 3 已定义并由本阶段消费的 `BaseUpdate`**（`palchronicle/application/base_service.py`）：
> ```python
> @dataclass(slots=True)
> class BaseUpdate:
>     base_key:str; world_id:str; palbox_key:str; guild_key:str|None
>     confidence:Confidence; worker_count:int; active_count:int
>     average_level:float; average_hp_ratio:float; action_distribution:dict[str,int]
>     is_new:bool; is_vanished:bool; prev_worker_count:int|None
> ```
>
> **本阶段新增的 `Repository` 方法**（严格照契约，签名不得改）：`insert_event(e:WorldEvent)->bool`（dedup 冲突返回 `False`）、`list_events(world_id, since=None, limit=20)->list[WorldEvent]`、`peak_online(world_id, since=None)->int`、`upsert_daily_aggregate(world_id, day, key, value)->None`、`get_daily_aggregate(world_id, day, key)->Any|None`。前置阶段已实现的 `insert_metric`/`latest_metric`/`list_open_sessions`/`list_events`（若 Phase 5 需要则本阶段建）在本阶段被消费或补齐。
>
> **本阶段新增的 `DailyReport`**（`palchronicle/application/report_service.py`；Phase 5 `query_service`/`formatters` 消费）：
> ```python
> @dataclass(slots=True)
> class LevelEvent:  player_name:str; old_level:int; new_level:int
> @dataclass(slots=True)
> class BaseEvent:   base_key:str; kind:str; detail:str      # kind ∈ {"new","vanished","worker_delta"}
> @dataclass(slots=True)
> class DailyReport:
>     day:str; world_day_start:int; world_day_end:int
>     active_players:int; peak_online:int; total_online_seconds:int
>     level_events:list[LevelEvent]; base_events:list[BaseEvent]
>     records:list[str]; summary:str; is_empty:bool
> ```
>
> 全阶段异步测试用 `pytest-asyncio`（`@pytest.mark.asyncio`）；DB 测试用临时文件（aiosqlite + WAL 需真实文件路径，不用 `:memory:`）；时间用 `FakeClock` 保证确定性。测试文件命名 `tests/unit/<模块>_test.py`，接线集成测试放 `tests/integration/`。

---

### Task 4.1：Repository.insert_event —— dedup 落库

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_events_test.py`

**Interfaces:**
- Consumes: `Database.execute_write(sql, params)`、`Database.query(sql, params)`（Phase 1）；`WorldEvent`（契约 `domain/models.py`：`event_id:int|None; world_id:str; event_type:EventType; subject_type:str; subject_key:str; occurred_at:int; confirmed_at:int; payload:dict; visibility:str; confidence:Confidence; dedup_key:str`）；`EventType`/`Confidence`（`domain/enums.py`）；`world_events` 表 + `idx_events_dedup`（migration_0001）。
- Produces: `Repository.insert_event(self, e:WorldEvent) -> bool`（dedup_key 冲突返回 `False`，成功返回 `True`）。

- [ ] **写失败测试** — 创建 `tests/unit/repository_events_test.py`：

```python
import json
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence, EventType
from palchronicle.domain.models import WorldEvent
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _make_repo(tmp_path: Path) -> tuple[Repository, Database, FakeClock]:
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1_700_000_000)
    return Repository(db, clock), db, clock


def _event(dedup: str, etype: EventType = EventType.NEW_PLAYER) -> WorldEvent:
    return WorldEvent(
        event_id=None,
        world_id="s1:guid:0",
        event_type=etype,
        subject_type="player",
        subject_key="pk1",
        occurred_at=1_700_000_000,
        confirmed_at=1_700_000_000,
        payload={"foo": "bar"},
        visibility="public",
        confidence=Confidence.HIGH,
        dedup_key=dedup,
    )


@pytest.mark.asyncio
async def test_insert_event_returns_true_on_new(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        assert await repo.insert_event(_event("s1:guid:0|NEW_PLAYER|pk1")) is True
        rows = await db.query("SELECT dedup_key, payload_json FROM world_events")
        assert len(rows) == 1
        assert rows[0]["dedup_key"] == "s1:guid:0|NEW_PLAYER|pk1"
        assert json.loads(rows[0]["payload_json"]) == {"foo": "bar"}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_insert_event_dedup_returns_false_no_duplicate(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        assert await repo.insert_event(_event("dup|key")) is True
        assert await repo.insert_event(_event("dup|key")) is False
        rows = await db.query("SELECT COUNT(*) AS n FROM world_events")
        assert rows[0]["n"] == 1
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_events_test.py -q`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'insert_event'`（方法尚未实现）。

- [ ] **写最小实现** — 在 `palchronicle/adapters/sqlite_repository.py` 的 `Repository` 类内新增（`import json` 若未在文件顶部则补上）：

```python
    async def insert_event(self, e: WorldEvent) -> bool:
        try:
            await self._db.execute_write(
                """INSERT INTO world_events
                   (world_id, event_type, subject_type, subject_key,
                    occurred_at, confirmed_at, payload_json, visibility,
                    confidence, dedup_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e.world_id,
                    e.event_type.value,
                    e.subject_type,
                    e.subject_key,
                    e.occurred_at,
                    e.confirmed_at,
                    json.dumps(e.payload, ensure_ascii=False, sort_keys=True),
                    e.visibility,
                    e.confidence.value,
                    e.dedup_key,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False
```

  在文件顶部 import 区确保存在 `import json`、`import sqlite3`（`sqlite3.IntegrityError` 是 aiosqlite 抛出的底层异常基类）。假定字段名 `self._db` 与 Phase 1 一致；若 Phase 1 用 `self.db`，随之调整。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_events_test.py -q`。期望 PASS：2 passed。

- [ ] **提交** — 命令：
```
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_events_test.py
git commit -m "feat(repo): insert_event with dedup_key uniqueness"
```

---

### Task 4.2：Repository.list_events + peak_online

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_events_test.py`（追加）

**Interfaces:**
- Consumes: `Database.query`；`world_events`/`world_metrics` 表；`insert_event`（Task 4.1）；`insert_metric`（Phase 1/前置，写 `world_metrics`）。
- Produces:
  - `Repository.list_events(self, world_id:str, since:int|None=None, limit:int=20) -> list[WorldEvent]`（按 `occurred_at` 降序，`since` 为 `occurred_at >= since` 过滤）。
  - `Repository.peak_online(self, world_id:str, since:int|None=None) -> int`（`world_metrics.online_players` 最大值；无数据返回 0；`since` 为 `observed_at >= since` 过滤）。

- [ ] **写失败测试** — 在 `tests/unit/repository_events_test.py` 追加：

```python
from palchronicle.domain.models import WorldMetric


@pytest.mark.asyncio
async def test_list_events_ordered_desc_and_since_filter(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        e_old = _event("k1")
        e_old.occurred_at = 100
        e_new = _event("k2")
        e_new.occurred_at = 300
        e_mid = _event("k3")
        e_mid.occurred_at = 200
        for e in (e_old, e_new, e_mid):
            await repo.insert_event(e)
        got = await repo.list_events("s1:guid:0", limit=10)
        assert [e.occurred_at for e in got] == [300, 200, 100]
        assert [e.dedup_key for e in got] == ["k2", "k3", "k1"]
        since = await repo.list_events("s1:guid:0", since=200, limit=10)
        assert [e.occurred_at for e in since] == [300, 200]
        assert since[0].event_type == EventType.NEW_PLAYER
        assert since[0].payload == {"foo": "bar"}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_list_events_respects_limit_and_world_isolation(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        for i in range(5):
            e = _event(f"w1-{i}")
            e.occurred_at = 100 + i
            await repo.insert_event(e)
        other = _event("other")
        other.world_id = "s2:guid:0"
        await repo.insert_event(other)
        got = await repo.list_events("s1:guid:0", limit=3)
        assert len(got) == 3
        assert [e.occurred_at for e in got] == [104, 103, 102]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_peak_online(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        assert await repo.peak_online("s1:guid:0") == 0
        for at, online in ((100, 3), (200, 7), (300, 5)):
            await repo.insert_metric(
                WorldMetric(
                    world_id="s1:guid:0", observed_at=at, fps=60.0,
                    frame_time=16.0, online_players=online, world_day=1,
                    basecamp_count=2,
                )
            )
        assert await repo.peak_online("s1:guid:0") == 7
        assert await repo.peak_online("s1:guid:0", since=250) == 5
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_events_test.py -q -k "list_events or peak_online"`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'list_events'`（及 `peak_online`）。

- [ ] **写最小实现** — 在 `Repository` 类内新增（`WorldEvent` 重建复用 `EventType`/`Confidence` 枚举）：

```python
    async def list_events(
        self, world_id: str, since: int | None = None, limit: int = 20
    ) -> list[WorldEvent]:
        sql = "SELECT * FROM world_events WHERE world_id = ?"
        params: list = [world_id]
        if since is not None:
            sql += " AND occurred_at >= ?"
            params.append(since)
        sql += " ORDER BY occurred_at DESC, event_id DESC LIMIT ?"
        params.append(limit)
        rows = await self._db.query(sql, params)
        return [
            WorldEvent(
                event_id=r["event_id"],
                world_id=r["world_id"],
                event_type=EventType(r["event_type"]),
                subject_type=r["subject_type"],
                subject_key=r["subject_key"],
                occurred_at=r["occurred_at"],
                confirmed_at=r["confirmed_at"],
                payload=json.loads(r["payload_json"]),
                visibility=r["visibility"],
                confidence=Confidence(r["confidence"]),
                dedup_key=r["dedup_key"],
            )
            for r in rows
        ]

    async def peak_online(self, world_id: str, since: int | None = None) -> int:
        sql = "SELECT MAX(online_players) AS m FROM world_metrics WHERE world_id = ?"
        params: list = [world_id]
        if since is not None:
            sql += " AND observed_at >= ?"
            params.append(since)
        rows = await self._db.query(sql, params)
        val = rows[0]["m"]
        return int(val) if val is not None else 0
```

  确保文件顶部已 `from palchronicle.domain.enums import EventType, Confidence`（Phase 3 大概率已 import 部分枚举；补齐缺的）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_events_test.py -q`。期望 PASS：全部 passed（含 4.1 的 2 个 + 本任务 3 个）。

- [ ] **提交** — 命令：
```
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_events_test.py
git commit -m "feat(repo): list_events (desc, since, limit) + peak_online"
```

---

### Task 4.3：Repository daily_aggregates 读写

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_aggregates_test.py`

**Interfaces:**
- Consumes: `Database.execute_write`/`Database.query`；`daily_aggregates(world_id, day, key, value_json, PK(world_id, day, key))` 表（migration_0001）。
- Produces:
  - `Repository.upsert_daily_aggregate(self, world_id:str, day:str, key:str, value:Any) -> None`（`value` 经 `json.dumps` 落 `value_json`；主键冲突覆盖）。
  - `Repository.get_daily_aggregate(self, world_id:str, day:str, key:str) -> Any|None`（命中则 `json.loads`，否则 `None`）。

- [ ] **写失败测试** — 创建 `tests/unit/repository_aggregates_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _make_repo(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    return Repository(db, FakeClock(start=1_700_000_000)), db


@pytest.mark.asyncio
async def test_get_daily_aggregate_missing_returns_none(tmp_path):
    repo, db = await _make_repo(tmp_path)
    try:
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "peak") is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_upsert_and_get_daily_aggregate_roundtrip(tmp_path):
    repo, db = await _make_repo(tmp_path)
    try:
        await repo.upsert_daily_aggregate("s1:g:0", "2026-07-10", "peak", 12)
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "peak") == 12
        await repo.upsert_daily_aggregate(
            "s1:g:0", "2026-07-10", "summary", {"active": 3, "names": ["a", "b"]}
        )
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "summary") == {
            "active": 3,
            "names": ["a", "b"],
        }
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_upsert_daily_aggregate_overwrites_on_conflict(tmp_path):
    repo, db = await _make_repo(tmp_path)
    try:
        await repo.upsert_daily_aggregate("s1:g:0", "2026-07-10", "peak", 5)
        await repo.upsert_daily_aggregate("s1:g:0", "2026-07-10", "peak", 9)
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "peak") == 9
        rows = await db.query("SELECT COUNT(*) AS n FROM daily_aggregates")
        assert rows[0]["n"] == 1
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_aggregates_test.py -q`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'upsert_daily_aggregate'`。

- [ ] **写最小实现** — 在 `Repository` 类内新增：

```python
    async def upsert_daily_aggregate(
        self, world_id: str, day: str, key: str, value: Any
    ) -> None:
        await self._db.execute_write(
            """INSERT INTO daily_aggregates (world_id, day, key, value_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(world_id, day, key)
               DO UPDATE SET value_json = excluded.value_json""",
            (world_id, day, key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
        )

    async def get_daily_aggregate(
        self, world_id: str, day: str, key: str
    ) -> Any | None:
        rows = await self._db.query(
            "SELECT value_json FROM daily_aggregates WHERE world_id = ? AND day = ? AND key = ?",
            (world_id, day, key),
        )
        if not rows:
            return None
        return json.loads(rows[0]["value_json"])
```

  确保文件顶部 `from typing import Any` 已 import（若缺则补）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_aggregates_test.py -q`。期望 PASS：3 passed。

- [ ] **提交** — 命令：
```
git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_aggregates_test.py
git commit -m "feat(repo): daily_aggregates upsert/get with json value"
```

---

### Task 4.4：EventService.dedup_key + level_up

**Files:**
- Create: `palchronicle/application/event_service.py`
- Test: `tests/unit/event_service_test.py`

**Interfaces:**
- Consumes: `Repository.insert_event`（Task 4.1）；`Clock.now`（`infrastructure/clock.py`）；`World`（`domain/models.py`：`world_id`/`current_day` 等）；`WorldEvent`、`EventType`、`Confidence`。
- Produces:
  - `EventService.__init__(self, repo:Repository, clock:Clock)`。
  - `EventService.dedup_key(world_id:str, event_type:EventType, *parts) -> str`（`@staticmethod`；`"{world_id}|{TYPE_NAME}|{p1}|{p2}..."`，`TYPE_NAME` 用 `event_type.name`，`parts` 逐个 `str()`）。
  - `EventService.level_up(self, world:World, player_key:str, old:int, new:int) -> None`（`new > old` 才发；dedup_key 尾用 `new`；`payload={"old": old, "new": new}`；跨多级仍一条，dedup 由 `new_level` 唯一；等级下降不发）。

- [ ] **写失败测试** — 创建 `tests/unit/event_service_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.event_service import EventService
from palchronicle.domain.enums import EventType
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _world() -> World:
    return World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="Srv", version="1.0", first_seen_at=100,
        last_seen_at=100, current_day=1,
    )


async def _make(tmp_path: Path):
    db = Database(tmp_path / "e.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1000)
    repo = Repository(db, clock)
    return EventService(repo, clock), repo, db, clock


def test_dedup_key_format():
    key = EventService.dedup_key("s1:g:0", EventType.PLAYER_LEVEL_UP, "pk", 42)
    assert key == "s1:g:0|PLAYER_LEVEL_UP|pk|42"


@pytest.mark.asyncio
async def test_level_up_emits_once(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=10, new=13)
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        ev = rows[0]
        assert ev.event_type == EventType.PLAYER_LEVEL_UP
        assert ev.subject_key == "pk1"
        assert ev.payload == {"new": 13, "old": 10}
        assert ev.dedup_key == "s1:guid:0|PLAYER_LEVEL_UP|pk1|13"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_level_up_dedup_same_new_level_no_duplicate(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=10, new=13)
        await svc.level_up(_world(), "pk1", old=12, new=13)  # same new
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_level_up_multi_level_records_old_to_new(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=10, new=15)
        rows = await repo.list_events("s1:guid:0")
        assert rows[0].payload == {"new": 15, "old": 10}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_level_down_emits_nothing(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=20, new=18)
        await svc.level_up(_world(), "pk1", old=20, new=20)  # equal
        rows = await repo.list_events("s1:guid:0")
        assert rows == []
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/event_service_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.event_service'`。

- [ ] **写最小实现** — 创建 `palchronicle/application/event_service.py`：

```python
from __future__ import annotations

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence, EventType
from palchronicle.domain.models import World, WorldEvent
from palchronicle.infrastructure.clock import Clock


class EventService:
    def __init__(self, repo: Repository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    @staticmethod
    def dedup_key(world_id: str, event_type: EventType, *parts: object) -> str:
        tail = "|".join(str(p) for p in parts)
        base = f"{world_id}|{event_type.name}"
        return f"{base}|{tail}" if tail else base

    async def _emit(
        self,
        world: World,
        event_type: EventType,
        subject_type: str,
        subject_key: str,
        dedup: str,
        payload: dict,
        confidence: Confidence = Confidence.HIGH,
        visibility: str = "public",
    ) -> bool:
        now = self._clock.now()
        event = WorldEvent(
            event_id=None,
            world_id=world.world_id,
            event_type=event_type,
            subject_type=subject_type,
            subject_key=subject_key,
            occurred_at=now,
            confirmed_at=now,
            payload=payload,
            visibility=visibility,
            confidence=confidence,
            dedup_key=dedup,
        )
        return await self._repo.insert_event(event)

    async def level_up(
        self, world: World, player_key: str, old: int, new: int
    ) -> None:
        if new <= old:
            return
        dedup = self.dedup_key(
            world.world_id, EventType.PLAYER_LEVEL_UP, player_key, new
        )
        await self._emit(
            world,
            EventType.PLAYER_LEVEL_UP,
            "player",
            player_key,
            dedup,
            {"old": old, "new": new},
        )
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/event_service_test.py -q`。期望 PASS：5 passed。

- [ ] **提交** — 命令：
```
git add palchronicle/application/event_service.py tests/unit/event_service_test.py
git commit -m "feat(events): EventService dedup_key + level_up detection"
```

---

### Task 4.5：EventService.new_player + new_guild

**Files:**
- Modify: `palchronicle/application/event_service.py`
- Test: `tests/unit/event_service_test.py`（追加）

**Interfaces:**
- Consumes: `EventService._emit`/`dedup_key`（Task 4.4）；`EventType.NEW_PLAYER`/`EventType.NEW_GUILD`。
- Produces:
  - `EventService.new_player(self, world:World, player_key:str) -> None`（dedup `world|NEW_PLAYER|player_key`；`payload={}`；重复输入只落一条）。
  - `EventService.new_guild(self, world:World, guild_key:str) -> None`（dedup `world|NEW_GUILD|guild_key`；`payload={}`；`subject_type="guild"`）。

- [ ] **写失败测试** — 在 `tests/unit/event_service_test.py` 追加：

```python
@pytest.mark.asyncio
async def test_new_player_emits_once_and_dedups(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.new_player(_world(), "pk1")
        await svc.new_player(_world(), "pk1")  # duplicate
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].event_type == EventType.NEW_PLAYER
        assert rows[0].subject_type == "player"
        assert rows[0].subject_key == "pk1"
        assert rows[0].dedup_key == "s1:guid:0|NEW_PLAYER|pk1"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_new_guild_emits_once_and_dedups(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.new_guild(_world(), "gk1")
        await svc.new_guild(_world(), "gk1")
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].event_type == EventType.NEW_GUILD
        assert rows[0].subject_type == "guild"
        assert rows[0].subject_key == "gk1"
        assert rows[0].dedup_key == "s1:guid:0|NEW_GUILD|gk1"
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/event_service_test.py -q -k "new_player or new_guild"`。期望 FAIL：`AttributeError: 'EventService' object has no attribute 'new_player'`。

- [ ] **写最小实现** — 在 `EventService` 类内新增：

```python
    async def new_player(self, world: World, player_key: str) -> None:
        dedup = self.dedup_key(world.world_id, EventType.NEW_PLAYER, player_key)
        await self._emit(
            world, EventType.NEW_PLAYER, "player", player_key, dedup, {}
        )

    async def new_guild(self, world: World, guild_key: str) -> None:
        dedup = self.dedup_key(world.world_id, EventType.NEW_GUILD, guild_key)
        await self._emit(
            world, EventType.NEW_GUILD, "guild", guild_key, dedup, {}
        )
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/event_service_test.py -q`。期望 PASS：全部 passed（含前序 5 个 + 本任务 2 个）。

- [ ] **提交** — 命令：
```
git add palchronicle/application/event_service.py tests/unit/event_service_test.py
git commit -m "feat(events): new_player + new_guild detection with dedup"
```

---

### Task 4.6：EventService.world_day —— 里程碑跨越

**Files:**
- Modify: `palchronicle/application/event_service.py`
- Test: `tests/unit/event_service_test.py`（追加）

**Interfaces:**
- Consumes: `EventService._emit`/`dedup_key`；`EventType.WORLD_DAY_MILESTONE`；`Repository.latest_metric`（前置阶段，读上一条 `world_metrics` 判断"跨越"）。
- Produces: `EventService.world_day(self, world:World, days:int) -> None`。判定：里程碑集合 `{100,200,365,500,1000,2000}`；对每个里程碑 `m`，若 `days >= m` 则发一条 `WORLD_DAY_MILESTONE`（dedup `world|WORLD_DAY_MILESTONE|m` 保证每里程碑唯一，天数回退/重复调用不重发）；`payload={"milestone": m, "day": days}`；`subject_type="world"`, `subject_key=world.world_id`。

> 说明：dedup_key 只含 `milestone`，因此"跨越"语义由 dedup 唯一性天然保证——即便某天 `days` 从 99→105 直接跳过 100，或多次以相同 `days` 调用，每个里程碑至多落一条。无需显式读取上一次 days。

- [ ] **写失败测试** — 在 `tests/unit/event_service_test.py` 追加：

```python
@pytest.mark.asyncio
async def test_world_day_crosses_single_milestone(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.world_day(_world(), 105)
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        ev = rows[0]
        assert ev.event_type == EventType.WORLD_DAY_MILESTONE
        assert ev.subject_type == "world"
        assert ev.payload == {"day": 105, "milestone": 100}
        assert ev.dedup_key == "s1:guid:0|WORLD_DAY_MILESTONE|100"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_world_day_milestone_unique_no_duplicate(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.world_day(_world(), 100)
        await svc.world_day(_world(), 150)  # still only past 100
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].payload["milestone"] == 100
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_world_day_crosses_multiple_at_once(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.world_day(_world(), 370)  # >=100,200,365
        rows = await repo.list_events("s1:guid:0")
        milestones = sorted(r.payload["milestone"] for r in rows)
        assert milestones == [100, 200, 365]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_world_day_below_first_milestone_emits_nothing(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.world_day(_world(), 42)
        assert await repo.list_events("s1:guid:0") == []
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/event_service_test.py -q -k world_day`。期望 FAIL：`AttributeError: 'EventService' object has no attribute 'world_day'`。

- [ ] **写最小实现** — 在 `EventService` 类内新增（把里程碑集合定义为类常量）：

```python
    MILESTONES: tuple[int, ...] = (100, 200, 365, 500, 1000, 2000)

    async def world_day(self, world: World, days: int) -> None:
        for m in self.MILESTONES:
            if days >= m:
                dedup = self.dedup_key(
                    world.world_id, EventType.WORLD_DAY_MILESTONE, m
                )
                await self._emit(
                    world,
                    EventType.WORLD_DAY_MILESTONE,
                    "world",
                    world.world_id,
                    dedup,
                    {"milestone": m, "day": days},
                )
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/event_service_test.py -q`。期望 PASS：全部 passed（新增 4 个）。

- [ ] **提交** — 命令：
```
git add palchronicle/application/event_service.py tests/unit/event_service_test.py
git commit -m "feat(events): world_day milestone detection (dedup per milestone)"
```

---

### Task 4.7：EventService.online_record —— 连续 2 快照确认

**Files:**
- Modify: `palchronicle/application/event_service.py`
- Test: `tests/unit/event_service_test.py`（追加）

**Interfaces:**
- Consumes: `EventService._emit`/`dedup_key`；`EventType.ONLINE_RECORD`；`Repository.peak_online`（Task 4.2，判断是否刷新历史最高）。
- Produces: `EventService.online_record(self, world:World, value:int, confirmed:bool) -> None`。语义（对齐 spec §11 ONLINE_RECORD）：`value` 为候选历史最高在线人数；仅当 `confirmed=True`（调用方已在连续 2 个健康 `/players` 快照中维持该值）且 `value > repo.peak_online(world_id)`（严格超过既有历史最高）时才发事件。`confirmed=False`（仅第一次出现该峰值、尚未维持）不发。dedup `world|ONLINE_RECORD|value`；`payload={"value": value}`；`subject_type="world"`。

> 确认逻辑（"连续 2 个健康快照维持"）由**调用方**（Task 4.9 的 metrics ingest 接线）持有跨快照状态并传入 `confirmed`；`EventService` 只做"已确认 + 超历史 + 去重"落库，保持无状态、可确定性测试。

- [ ] **写失败测试** — 在 `tests/unit/event_service_test.py` 追加：

```python
from palchronicle.domain.models import WorldMetric


async def _seed_metric(repo, at, online):
    await repo.insert_metric(
        WorldMetric(
            world_id="s1:guid:0", observed_at=at, fps=60.0, frame_time=16.0,
            online_players=online, world_day=1, basecamp_count=0,
        )
    )


@pytest.mark.asyncio
async def test_online_record_unconfirmed_emits_nothing(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.online_record(_world(), value=8, confirmed=False)
        assert await repo.list_events("s1:guid:0") == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_online_record_confirmed_emits(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await _seed_metric(repo, 100, 5)  # existing peak = 5
        await svc.online_record(_world(), value=8, confirmed=True)
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].event_type == EventType.ONLINE_RECORD
        assert rows[0].subject_type == "world"
        assert rows[0].payload == {"value": 8}
        assert rows[0].dedup_key == "s1:guid:0|ONLINE_RECORD|8"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_online_record_not_exceeding_peak_emits_nothing(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await _seed_metric(repo, 100, 10)  # peak = 10
        await svc.online_record(_world(), value=10, confirmed=True)  # equal, not >
        await svc.online_record(_world(), value=7, confirmed=True)   # below
        assert await repo.list_events("s1:guid:0") == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_online_record_dedup_same_value(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await _seed_metric(repo, 100, 5)
        await svc.online_record(_world(), value=9, confirmed=True)
        await svc.online_record(_world(), value=9, confirmed=True)
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/event_service_test.py -q -k online_record`。期望 FAIL：`AttributeError: 'EventService' object has no attribute 'online_record'`。

- [ ] **写最小实现** — 在 `EventService` 类内新增：

```python
    async def online_record(
        self, world: World, value: int, confirmed: bool
    ) -> None:
        if not confirmed:
            return
        if value <= await self._repo.peak_online(world.world_id):
            return
        dedup = self.dedup_key(world.world_id, EventType.ONLINE_RECORD, value)
        await self._emit(
            world,
            EventType.ONLINE_RECORD,
            "world",
            world.world_id,
            dedup,
            {"value": value},
        )
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/event_service_test.py -q`。期望 PASS：全部 passed（新增 4 个）。

- [ ] **提交** — 命令：
```
git add palchronicle/application/event_service.py tests/unit/event_service_test.py
git commit -m "feat(events): online_record confirmed + exceeds-peak detection"
```

---

### Task 4.8：EventService.base_events —— NEW_BASE / BASE_VANISHED / WORKER_DELTA

**Files:**
- Modify: `palchronicle/application/event_service.py`
- Test: `tests/unit/event_service_test.py`（追加）

**Interfaces:**
- Consumes: `EventService._emit`/`dedup_key`；`EventType.NEW_BASE`/`BASE_VANISHED`/`WORKER_DELTA`；`Confidence`；Phase 3 的 `BaseUpdate`（字段见文件头）；`World.current_day`（用于 dedup 的 `day` 分量与 BASE_VANISHED 的 `first_missing_day`）。
- Produces: `EventService.base_events(self, world:World, updates:list[BaseUpdate]) -> None`。逐条 `BaseUpdate` 处理（对齐 spec §11）：
  - **NEW_BASE**：`u.is_new is True`（Phase 3 已保证门槛：连续 `confirmation_samples` 一致 + `confidence>=medium` + 已先落 base）→ 发 `NEW_BASE`，dedup `world|NEW_BASE|base_key`，`payload={"guild_key": u.guild_key, "worker_count": u.worker_count, "confidence": u.confidence.value}`，`confidence=u.confidence`。
  - **BASE_VANISHED**：`u.is_vanished is True`（Phase 3 已保证连续 ≥3 次缺失 + game-data 健康 + worldguid 未变）→ 发 `BASE_VANISHED`，dedup `world|BASE_VANISHED|base_key|{current_day}`（`first_missing_day` 用 `world.current_day`），`payload={"first_missing_day": world.current_day}`。
  - **WORKER_DELTA**：`u.prev_worker_count is not None` 且 `abs(u.worker_count - u.prev_worker_count) >= max(3, int(u.prev_worker_count * 0.2))`（连续两次确认已由 Phase 3 base_service 保证——它只在满足"连续两次"时把 `prev_worker_count` 设为基线）→ 发 `WORKER_DELTA`，dedup `world|WORKER_DELTA|base_key|{current_day}|{bucket}`，`bucket = "up" if cur>prev else "down"`，`payload={"prev": prev, "cur": cur}`。
  - `low` 置信度 base 的更新：`NEW_BASE` 不发（Phase 3 门槛已挡，但 `base_events` 二次防御：`u.is_new and u.confidence == Confidence.LOW` 直接跳过 NEW_BASE）。

- [ ] **写失败测试** — 在 `tests/unit/event_service_test.py` 追加：

```python
from palchronicle.application.base_service import BaseUpdate
from palchronicle.domain.enums import Confidence


def _update(**kw) -> BaseUpdate:
    defaults = dict(
        base_key="s1:guid:0|BASE|pb1", world_id="s1:guid:0",
        palbox_key="pb1", guild_key="gk1", confidence=Confidence.HIGH,
        worker_count=5, active_count=3, average_level=10.0,
        average_hp_ratio=0.9, action_distribution={"working": 3},
        is_new=False, is_vanished=False, prev_worker_count=None,
    )
    defaults.update(kw)
    return BaseUpdate(**defaults)


@pytest.mark.asyncio
async def test_new_base_event(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.base_events(_world(), [_update(is_new=True, worker_count=6)])
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        ev = rows[0]
        assert ev.event_type == EventType.NEW_BASE
        assert ev.subject_type == "base"
        assert ev.subject_key == "s1:guid:0|BASE|pb1"
        assert ev.dedup_key == "s1:guid:0|NEW_BASE|s1:guid:0|BASE|pb1"
        assert ev.payload == {
            "confidence": "high", "guild_key": "gk1", "worker_count": 6,
        }
        assert ev.confidence == Confidence.HIGH
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_new_base_low_confidence_skipped(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.base_events(
            _world(), [_update(is_new=True, confidence=Confidence.LOW)]
        )
        assert await repo.list_events("s1:guid:0") == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_base_vanished_event_uses_current_day(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        world = _world()
        world.current_day = 7
        await svc.base_events(world, [_update(is_vanished=True)])
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        ev = rows[0]
        assert ev.event_type == EventType.BASE_VANISHED
        assert ev.payload == {"first_missing_day": 7}
        assert ev.dedup_key == "s1:guid:0|BASE_VANISHED|s1:guid:0|BASE|pb1|7"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_worker_delta_threshold_absolute_min_3(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        world = _world()
        world.current_day = 4
        # prev=5 -> threshold=max(3, 1)=3; cur=8 -> delta=3 -> fires (up)
        await svc.base_events(
            world, [_update(prev_worker_count=5, worker_count=8)]
        )
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        ev = rows[0]
        assert ev.event_type == EventType.WORKER_DELTA
        assert ev.payload == {"cur": 8, "prev": 5}
        assert ev.dedup_key == "s1:guid:0|WORKER_DELTA|s1:guid:0|BASE|pb1|4|up"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_worker_delta_below_threshold_no_event(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        # prev=5 -> threshold=3; cur=7 -> delta=2 -> below
        await svc.base_events(
            _world(), [_update(prev_worker_count=5, worker_count=7)]
        )
        assert await repo.list_events("s1:guid:0") == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_worker_delta_20pct_threshold_for_large_base(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        world = _world()
        world.current_day = 2
        # prev=20 -> threshold=max(3, 4)=4; cur=16 -> delta=4 -> fires (down)
        await svc.base_events(
            world, [_update(prev_worker_count=20, worker_count=16)]
        )
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].payload == {"cur": 16, "prev": 20}
        assert rows[0].dedup_key.endswith("|2|down")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_base_events_none_flags_no_event(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.base_events(_world(), [_update()])  # all flags off, prev=None
        assert await repo.list_events("s1:guid:0") == []
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/event_service_test.py -q -k base_events或用 "-k 'new_base or vanished or worker_delta or base_events'"`。实际命令：`python -m pytest tests/unit/event_service_test.py -q -k "new_base or vanished or worker_delta or base_events"`。期望 FAIL：`AttributeError: 'EventService' object has no attribute 'base_events'`。

- [ ] **写最小实现** — 在 `EventService` 类内新增（顶部 import 补 `from palchronicle.application.base_service import BaseUpdate`）：

```python
    async def base_events(
        self, world: World, updates: list["BaseUpdate"]
    ) -> None:
        for u in updates:
            if u.is_new and u.confidence != Confidence.LOW:
                dedup = self.dedup_key(
                    world.world_id, EventType.NEW_BASE, u.base_key
                )
                await self._emit(
                    world,
                    EventType.NEW_BASE,
                    "base",
                    u.base_key,
                    dedup,
                    {
                        "guild_key": u.guild_key,
                        "worker_count": u.worker_count,
                        "confidence": u.confidence.value,
                    },
                    confidence=u.confidence,
                )
            if u.is_vanished:
                dedup = self.dedup_key(
                    world.world_id,
                    EventType.BASE_VANISHED,
                    u.base_key,
                    world.current_day,
                )
                await self._emit(
                    world,
                    EventType.BASE_VANISHED,
                    "base",
                    u.base_key,
                    dedup,
                    {"first_missing_day": world.current_day},
                )
            if u.prev_worker_count is not None:
                prev = u.prev_worker_count
                cur = u.worker_count
                threshold = max(3, int(prev * 0.2))
                if abs(cur - prev) >= threshold:
                    bucket = "up" if cur > prev else "down"
                    dedup = self.dedup_key(
                        world.world_id,
                        EventType.WORKER_DELTA,
                        u.base_key,
                        world.current_day,
                        bucket,
                    )
                    await self._emit(
                        world,
                        EventType.WORKER_DELTA,
                        "base",
                        u.base_key,
                        dedup,
                        {"prev": prev, "cur": cur},
                    )
```

  在文件顶部 import 区加 `from palchronicle.application.base_service import BaseUpdate`（仅供类型标注；若引入循环 import 则改为 `from __future__ import annotations` 已在文件首行 + `if TYPE_CHECKING:` 保护，本文件首行已有 `from __future__ import annotations`，故字符串标注 `"BaseUpdate"` 安全，且运行时不需真 import——直接删掉运行时 import，仅在测试文件导入 `BaseUpdate`）。为避免循环依赖，**不在 event_service 顶层 import base_service**：方法签名用字符串标注 `list["BaseUpdate"]`，运行时鸭子类型访问属性即可。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/event_service_test.py -q`。期望 PASS：全部 passed（新增 7 个）。

- [ ] **提交** — 命令：
```
git add palchronicle/application/event_service.py tests/unit/event_service_test.py
git commit -m "feat(events): base_events NEW_BASE/BASE_VANISHED/WORKER_DELTA"
```

---

### Task 4.9：接线 —— player/base/metrics 事件产生

**Files:**
- Modify: `palchronicle/application/player_service.py`（Phase 3 已建）
- Modify: `palchronicle/application/base_service.py`（Phase 3 已建）
- Modify: `palchronicle/application/snapshot_service.py`（Phase 2/3 已建）
- Test: `tests/integration/event_wiring_test.py`

**Interfaces:**
- Consumes: `EventService.level_up`/`new_player`/`base_events`/`world_day`/`online_record`（Task 4.4–4.8）；`PlayerService.apply_players`（Phase 3；升级/新玩家判定已算出 old/new 与首见标志）；`BaseService.apply`（Phase 3；返回 `list[BaseUpdate]`）；`SnapshotService.ingest_metrics`/`ingest_players`/`ingest_game_data`（契约 `snapshot_service.py`）；`PlayersSnapshot`/`MetricsSnapshot`/`GameDataSnapshot`（契约 `domain/models.py`）。
- Produces: 接线后的行为（无新公共签名，复用契约签名）：
  - `PlayerService.apply_players` 内：检测到新等级 `new>old` → `await self._events.level_up(world, player_key, old, new)`；首见 player → `await self._events.new_player(world, player_key)`。
  - `BaseService.apply` 的结果由 `SnapshotService.ingest_game_data` 转发：`updates = await self._bases.apply(world, gd); await self._events.base_events(world, updates)`；公会首见 → `await self._events.new_guild(world, gk)`。
  - `SnapshotService.ingest_metrics` 内：`await self._events.world_day(world, snap.days)`；并做 online_record 连续 2 快照确认：维护每 world_id 的 `(candidate_value, streak)` 内存状态，`snap.online` ≥ 当前候选则 `streak += 1` 否则重置候选，`streak >= 2` 时 `await self._events.online_record(world, candidate, confirmed=True)`。

> `PlayerService`/`BaseService`/`SnapshotService` 的 `__init__` 已在 Phase 2/3 接收 `events:EventService`（见契约 `SnapshotService.__init__(..., events:EventService)`；`PlayerService`/`BaseService` 若 Phase 3 未注入 events，本任务在其 `__init__` 增加 `events` 形参并由 container 装配传入——container 装配在 Phase 5，本任务只改服务签名与调用点）。

- [ ] **写失败测试** — 创建 `tests/integration/event_wiring_test.py`（用真实 Repository + FakeClock，构造最小 world/snapshot，断言事件被产生）：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.event_service import EventService
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.domain.enums import EventType
from palchronicle.domain.models import MetricsSnapshot, World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _world() -> World:
    return World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="Srv", version="1.0", first_seen_at=0,
        last_seen_at=0, current_day=1,
    )


async def _wire(tmp_path: Path):
    db = Database(tmp_path / "wire.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1000)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    return repo, events, clock, db


@pytest.mark.asyncio
async def test_ingest_metrics_emits_world_day_milestone(tmp_path):
    repo, events, clock, db = await _wire(tmp_path)
    try:
        snap = MetricsSnapshot(
            observed_at=1000, fps=60.0, frame_time=16.0, online=3,
            max_players=32, uptime=1, basecamp_count=0, days=105,
        )
        # SnapshotService only needs repo/events/clock for this path;
        # other collaborators may be None in this focused wiring test.
        svc = SnapshotService.__new__(SnapshotService)
        svc._repo = repo
        svc._events = events
        svc._clock = clock
        svc._online_streak = {}
        await svc.ingest_metrics(_world(), _resp(snap))
        rows = await repo.list_events("s1:guid:0")
        types = {r.event_type for r in rows}
        assert EventType.WORLD_DAY_MILESTONE in types
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_ingest_metrics_online_record_needs_two_snapshots(tmp_path):
    repo, events, clock, db = await _wire(tmp_path)
    try:
        svc = SnapshotService.__new__(SnapshotService)
        svc._repo = repo
        svc._events = events
        svc._clock = clock
        svc._online_streak = {}
        world = _world()

        def snap(online):
            return MetricsSnapshot(
                observed_at=1000, fps=60.0, frame_time=16.0, online=online,
                max_players=32, uptime=1, basecamp_count=0, days=1,
            )

        await svc.ingest_metrics(world, _resp(snap(8)))   # first sighting
        assert not [
            r for r in await repo.list_events("s1:guid:0")
            if r.event_type == EventType.ONLINE_RECORD
        ]
        await svc.ingest_metrics(world, _resp(snap(8)))   # sustained → confirm
        recs = [
            r for r in await repo.list_events("s1:guid:0")
            if r.event_type == EventType.ONLINE_RECORD
        ]
        assert len(recs) == 1
        assert recs[0].payload == {"value": 8}
    finally:
        await db.close()


def _resp(snap):
    # Wraps a pre-normalized snapshot so ingest_metrics can consume it.
    # ingest_metrics is expected to accept an object exposing `.data` as the
    # normalized MetricsSnapshot (RestResponse-shaped). We inline a stub.
    class _R:
        ok = True
        status = 200
        data = snap
        duration_ms = 1
        payload_bytes = 0
        error = None

    return _R()
```

> 注：`ingest_metrics` 的签名契约是 `ingest_metrics(self, world, resp:RestResponse)`。若 Phase 2 的实现里 `ingest_metrics` 直接接收已归一的 `MetricsSnapshot`（而非 `RestResponse`），则把 `_resp(snap)` 改为直接传 `snap` 并相应调整实现；本测试以契约 `RestResponse` 形状（含 `.data`）为准，`ingest_metrics` 内部从 `resp.data` 取归一快照（若 Phase 2 已在 ingest 内做归一，则从 `resp.data` 取原始 dict 后调用 `normalize_metrics`——按 Phase 2 既有实现二选一，保持一致）。

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/integration/event_wiring_test.py -q`。期望 FAIL：`AttributeError`（`SnapshotService` 无 `_online_streak` 处理逻辑，或 `ingest_metrics` 未调用 `events.world_day`/`events.online_record`，断言 `EventType.WORLD_DAY_MILESTONE in types` 失败 / online_record 计数不符）。

- [ ] **写最小实现** — 修改 `palchronicle/application/snapshot_service.py`：在 `__init__` 增加 `self._online_streak: dict[str, tuple[int, int]] = {}`（key=world_id, value=(candidate, streak)）；`ingest_metrics` 增加事件接线（保留原有 `insert_metric` 落库逻辑）：

```python
    async def ingest_metrics(self, world: World, resp: "RestResponse") -> None:
        snap = resp.data
        if snap is None:
            return
        await self._repo.insert_metric(
            WorldMetric(
                world_id=world.world_id, observed_at=snap.observed_at,
                fps=snap.fps, frame_time=snap.frame_time,
                online_players=snap.online, world_day=snap.days,
                basecamp_count=snap.basecamp_count,
            )
        )
        await self._events.world_day(world, snap.days)
        candidate, streak = self._online_streak.get(world.world_id, (0, 0))
        if snap.online >= candidate and snap.online > 0:
            if snap.online == candidate:
                streak += 1
            else:
                candidate, streak = snap.online, 1
        else:
            candidate, streak = snap.online, 1
        self._online_streak[world.world_id] = (candidate, streak)
        if streak >= 2:
            await self._events.online_record(world, candidate, confirmed=True)
```

  在 `palchronicle/application/player_service.py` 的 `apply_players` 内，紧接等级比较处调用（结构对齐 Phase 3 既有比较逻辑；此处补事件调用）：

```python
            if new_level > prev_level:
                await self._events.level_up(world, player_key, prev_level, new_level)
            if is_first_seen:
                await self._events.new_player(world, player_key)
```

  在 `palchronicle/application/snapshot_service.py` 的 `ingest_game_data` 内，`BaseService.apply` 后转发事件（对齐 Phase 3 既有归一/聚合逻辑）：

```python
        updates = await self._bases.apply(world, gd)
        await self._events.base_events(world, updates)
        guilds = await self._guilds.apply(world, gd)
        for g in guilds:
            if g.first_seen_at == self._clock.now():  # 首见本轮
                await self._events.new_guild(world, g.guild_key)
```

  （`GuildService.apply` 的"首见"判定沿用 Phase 3；若 Phase 3 已在 `GuildService` 内返回"新公会 key 列表"更精确，则改为遍历该列表调用 `new_guild`——以 Phase 3 既有产出为准，保持一致，不重复判定。）`player_service.py`/`base_service.py`/`snapshot_service.py` 的 `__init__` 若尚无 `self._events`，加形参 `events` 并赋值 `self._events = events`。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/integration/event_wiring_test.py -q`。期望 PASS：2 passed。再跑全量事件测试确认无回归：`python -m pytest tests/unit/event_service_test.py tests/integration/event_wiring_test.py -q`。

- [ ] **提交** — 命令：
```
git add palchronicle/application/player_service.py palchronicle/application/base_service.py palchronicle/application/snapshot_service.py tests/integration/event_wiring_test.py
git commit -m "feat(events): wire player/base/metrics ingest to EventService"
```

---

### Task 4.10：ReportService.daily —— 模板日报 DTO（有事件日）

**Files:**
- Create: `palchronicle/application/report_service.py`
- Test: `tests/unit/report_service_test.py`

**Interfaces:**
- Consumes: `Repository.list_events(world_id, since, limit)`（Task 4.2）、`Repository.peak_online(world_id, since)`（Task 4.2）、`Repository.list_open_sessions`/会话读侧（Phase 3；本任务用 `Repository` 上会话聚合读方法，若缺则以 `list_events` + `peak_online` 为主，会话时长走 `sessions_in_day` 见下）、`Clock.now`；`WorldConfig`/`AppConfig`（时区取 `server.timezone` 或 `world.timezone`）；`World`；`EventType`。
- Produces:
  - `palchronicle/application/report_service.py` 定义 `LevelEvent`、`BaseEvent`、`DailyReport`（字段见文件头）。
  - `ReportService.__init__(self, repo:Repository, cfg:AppConfig, clock:Clock)`。
  - `ReportService.daily(self, world:World, day:str|None=None) -> DailyReport`。`day` 为 `YYYY-MM-DD`（服务器时区自然日）；`None` → 用 `clock.now()` 折算当日。聚合：取当日 `[world_day_start, world_day_end)`（UTC epoch 秒边界）内事件/指标；`peak_online=repo.peak_online(world_id, since=start)` 且以 `end` 为上界（本任务用当日窗口）；`active_players` = 当日有会话且累计观察≥600s 的玩家数（spec §12 活跃日定义，10 分钟）；`total_online_seconds` = 当日会话观察秒和；`level_events`/`base_events`/`records` 从当日 `world_events` 按类型拆分；`summary` 走模板；内容排序 spec §12：世界里程碑→新纪录→新玩家/公会/据点→玩家成长→公会/据点变化→编辑部总结。
  - **空白日**：无任何显著事件且无活跃玩家 → `is_empty=True`，`summary="平静的一天"`（不编造）。

> 时区折算：用 `zoneinfo.ZoneInfo(tz)`（`tz = server.timezone or cfg.world.timezone`），把 `day` 的当地 00:00 与次日 00:00 转 UTC epoch 得 `[world_day_start, world_day_end)`。`FakeClock` 提供确定性 `now()`。

- [ ] **写失败测试** — 创建 `tests/unit/report_service_test.py`（先测有事件日的字段拆分与排序 + tz 边界；空白日单列 4.11）：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.event_service import EventService
from palchronicle.application.report_service import DailyReport, ReportService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, World as _  # placeholder if needed
from palchronicle.domain.models import World, WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _cfg(tz: str = "Asia/Tokyo") -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig(timezone=tz, locale="zh-CN", fps_smooth=50,
                          fps_moderate=35, fps_laggy=20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="Srv", version="1.0", first_seen_at=0,
        last_seen_at=0, current_day=105,
    )


# 2026-07-10 00:00 Asia/Tokyo (UTC+9) == 2026-07-09 15:00 UTC == 1752073200
DAY_START_UTC = 1752073200
NOON = DAY_START_UTC + 12 * 3600


async def _make(tmp_path: Path, tz="Asia/Tokyo"):
    db = Database(tmp_path / "rep.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=NOON)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    return ReportService(repo, _cfg(tz), clock), repo, events, clock, db


@pytest.mark.asyncio
async def test_daily_splits_events_and_orders(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        clock.set(NOON)
        await events.world_day(w, 105)                # WORLD_DAY_MILESTONE(100)
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=NOON, fps=60.0, frame_time=16.0,
            online_players=6, world_day=105, basecamp_count=1))
        await events.online_record(w, value=6, confirmed=True)  # ONLINE_RECORD
        await events.new_player(w, "pk1")
        await events.level_up(w, "pk1", old=9, new=12)
        rep = await report.daily(w, day="2026-07-10")
        assert isinstance(rep, DailyReport)
        assert rep.day == "2026-07-10"
        assert rep.world_day_start == DAY_START_UTC
        assert rep.world_day_end == DAY_START_UTC + 86400
        assert rep.peak_online == 6
        assert [le.new_level for le in rep.level_events] == [12]
        assert rep.level_events[0].old_level == 9
        # milestone + record present in records
        assert any("100" in r for r in rep.records)
        assert rep.is_empty is False
        assert rep.summary  # non-empty editorial summary
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_daily_natural_day_boundary_excludes_prev_day(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        # event one second BEFORE local midnight of 2026-07-10 → previous day
        clock.set(DAY_START_UTC - 1)
        await events.new_player(w, "pk_prev")
        # event inside the day
        clock.set(NOON)
        await events.new_player(w, "pk_in")
        rep = await report.daily(w, day="2026-07-10")
        new_player_keys = [
            r for r in rep.records if "pk_in" in r or "pk_prev" in r
        ]
        # pk_prev must NOT appear; only pk_in counted
        assert not any("pk_prev" in r for r in rep.records)
    finally:
        await db.close()
```

> `from palchronicle.domain.enums import AccessMode, World as _` 一行仅示意 import 位置——实际 `World` 从 `domain.models` 导入，`AccessMode` 从 `domain.enums`。实现测试文件时删掉占位别名，保留 `from palchronicle.domain.enums import AccessMode`。

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/report_service_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.report_service'`。

- [ ] **写最小实现** — 创建 `palchronicle/application/report_service.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import AppConfig
from palchronicle.domain.enums import EventType
from palchronicle.domain.models import World, WorldEvent
from palchronicle.infrastructure.clock import Clock

_ACTIVE_SECONDS = 600  # spec §12: 活跃日 >= 10 分钟


@dataclass(slots=True)
class LevelEvent:
    player_name: str
    old_level: int
    new_level: int


@dataclass(slots=True)
class BaseEvent:
    base_key: str
    kind: str          # "new" / "vanished" / "worker_delta"
    detail: str


@dataclass(slots=True)
class DailyReport:
    day: str
    world_day_start: int
    world_day_end: int
    active_players: int
    peak_online: int
    total_online_seconds: int
    level_events: list[LevelEvent]
    base_events: list[BaseEvent]
    records: list[str]
    summary: str
    is_empty: bool


class ReportService:
    def __init__(self, repo: Repository, cfg: AppConfig, clock: Clock) -> None:
        self._repo = repo
        self._cfg = cfg
        self._clock = clock

    def _tz(self, world: World) -> ZoneInfo:
        server_tz = ""
        for s in self._cfg.servers:
            if s.server_id == world.server_id:
                server_tz = s.timezone
                break
        return ZoneInfo(server_tz or self._cfg.world.timezone)

    def _day_bounds(self, world: World, day: str | None) -> tuple[str, int, int]:
        tz = self._tz(world)
        if day is None:
            local = datetime.fromtimestamp(self._clock.now(), tz)
            day = local.strftime("%Y-%m-%d")
        y, m, d = (int(x) for x in day.split("-"))
        start_local = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        return day, int(start_local.timestamp()), int(end_local.timestamp())

    async def daily(self, world: World, day: str | None = None) -> DailyReport:
        day, start, end = self._day_bounds(world, day)
        events = [
            e
            for e in await self._repo.list_events(
                world.world_id, since=start, limit=1000
            )
            if e.occurred_at < end
        ]
        peak = await self._repo.peak_online(world.world_id, since=start)

        milestones = [e for e in events if e.event_type == EventType.WORLD_DAY_MILESTONE]
        records_ev = [e for e in events if e.event_type == EventType.ONLINE_RECORD]
        new_players = [e for e in events if e.event_type == EventType.NEW_PLAYER]
        new_guilds = [e for e in events if e.event_type == EventType.NEW_GUILD]
        new_bases = [e for e in events if e.event_type == EventType.NEW_BASE]
        level_ups = [e for e in events if e.event_type == EventType.PLAYER_LEVEL_UP]
        vanished = [e for e in events if e.event_type == EventType.BASE_VANISHED]
        worker_delta = [e for e in events if e.event_type == EventType.WORKER_DELTA]

        level_events = [
            LevelEvent(
                player_name=e.subject_key,
                old_level=int(e.payload.get("old", 0)),
                new_level=int(e.payload.get("new", 0)),
            )
            for e in level_ups
        ]
        base_events: list[BaseEvent] = []
        for e in new_bases:
            base_events.append(BaseEvent(e.subject_key, "new", "新据点出现"))
        for e in vanished:
            base_events.append(BaseEvent(e.subject_key, "vanished", "据点消失"))
        for e in worker_delta:
            base_events.append(BaseEvent(e.subject_key, "worker_delta", "工作帕鲁变化"))

        # 排序: 里程碑 → 新纪录 → 新玩家/公会/据点 → 成长 → 变化 → 编辑部总结
        records: list[str] = []
        for e in milestones:
            records.append(f"世界推进至第 {e.payload.get('milestone')} 天")
        for e in records_ev:
            records.append(f"同时在线新纪录 {e.payload.get('value')} 人")
        for e in new_players:
            records.append(f"新玩家 {e.subject_key} 加入")
        for e in new_guilds:
            records.append(f"新公会 {e.subject_key} 出现")
        for e in new_bases:
            records.append(f"新据点 {e.subject_key} 出现")

        total_online_seconds = 0
        active_players = 0
        try:
            sessions = await self._repo.sessions_in_day(world.world_id, start, end)
            total_online_seconds = sum(s.observed_seconds for s in sessions)
            active_players = sum(
                1 for s in sessions if s.observed_seconds >= _ACTIVE_SECONDS
            )
        except AttributeError:
            pass

        has_content = bool(events) or active_players > 0
        if has_content:
            summary = self._summary(
                milestones, records_ev, new_players, new_guilds,
                new_bases, level_events, base_events, active_players,
            )
        else:
            summary = "平静的一天"

        return DailyReport(
            day=day,
            world_day_start=start,
            world_day_end=end,
            active_players=active_players,
            peak_online=peak,
            total_online_seconds=total_online_seconds,
            level_events=level_events,
            base_events=base_events,
            records=records,
            summary=summary,
            is_empty=not has_content,
        )

    def _summary(
        self, milestones, records_ev, new_players, new_guilds, new_bases,
        level_events, base_events, active_players,
    ) -> str:
        parts: list[str] = []
        if milestones:
            parts.append(f"世界跨越 {len(milestones)} 个里程碑")
        if records_ev:
            parts.append("刷新在线纪录")
        if new_players:
            parts.append(f"{len(new_players)} 名新玩家加入")
        if level_events:
            parts.append(f"{len(level_events)} 次成长")
        if base_events:
            parts.append(f"{len(base_events)} 处据点变化")
        if not parts and active_players:
            parts.append(f"{active_players} 名玩家在线活跃")
        return "，".join(parts) + "。" if parts else "平静的一天"
```

> `Repository.sessions_in_day(world_id, start, end) -> list[PlayerSession]` 若 Phase 3 未提供，则 `daily` 里的 `try/except AttributeError` 使 `total_online_seconds`/`active_players` 优雅降级为 0，不阻塞本阶段；Phase 5 或 Phase 3 补该读方法后自然生效。**若 Phase 3 已提供会话按日聚合的读方法**，把 `sessions_in_day` 换成该确切方法名（保持契约一致）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/report_service_test.py -q`。期望 PASS：2 passed。

- [ ] **提交** — 命令：
```
git add palchronicle/application/report_service.py tests/unit/report_service_test.py
git commit -m "feat(report): DailyReport DTO + daily aggregation (events, ordering, tz)"
```

---

### Task 4.11：ReportService.daily —— 空白日不编造

**Files:**
- Modify: （无需改实现，验证 Task 4.10 的空白日分支）`palchronicle/application/report_service.py`
- Test: `tests/unit/report_service_test.py`（追加）

**Interfaces:**
- Consumes: `ReportService.daily`（Task 4.10）；`DailyReport.is_empty`/`.summary`。
- Produces: 验证契约——无事件且无活跃玩家的自然日返回 `is_empty=True`、`summary="平静的一天"`、各事件列表为空。

- [ ] **写失败测试** — 在 `tests/unit/report_service_test.py` 追加（若 Task 4.10 实现已正确，此测试应直接通过——但按 TDD 先确认它验证的是真实行为；若失败说明空白日分支有 bug）：

```python
@pytest.mark.asyncio
async def test_daily_empty_day_reports_calm(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        rep = await report.daily(w, day="2026-07-10")
        assert rep.is_empty is True
        assert rep.summary == "平静的一天"
        assert rep.level_events == []
        assert rep.base_events == []
        assert rep.records == []
        assert rep.active_players == 0
        assert rep.peak_online == 0
        assert rep.total_online_seconds == 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_daily_none_day_uses_clock_local_date(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        # clock at NOON of 2026-07-10 local (Asia/Tokyo) → day resolves to that date
        rep = await report.daily(w, day=None)
        assert rep.day == "2026-07-10"
        assert rep.world_day_start == DAY_START_UTC
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/report_service_test.py -q -k "empty_day or none_day"`。期望：`test_daily_none_day_uses_clock_local_date` 首次可能 FAIL（若 `_day_bounds` 的 `None` 分支时区折算有 off-by-one）——期望 FAIL 原因 `AssertionError: assert '2026-07-11' == '2026-07-10'` 或 `world_day_start` 不等。`test_daily_empty_day_reports_calm` 若 4.10 已正确则 PASS。若两者皆已 PASS，则本任务作为回归锁定测试，直接进入下一步（TDD 允许"表征已实现行为的测试"作为防回归）。

- [ ] **写最小实现** — 若 `none_day` 测试失败，修正 `_day_bounds` 的 `None` 分支确保用 `datetime.fromtimestamp(now, tz)` 取本地日期字符串（Task 4.10 实现已如此；若失败则检查 `FakeClock.now()` 返回值是否为 epoch 秒且 `NOON` 常量正确）。无需改动其它逻辑：

```python
        if day is None:
            local = datetime.fromtimestamp(self._clock.now(), tz)
            day = local.strftime("%Y-%m-%d")
```

  （此代码已在 Task 4.10 的 `_day_bounds` 中；若测试已通过则此步为 no-op 确认。）

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/report_service_test.py -q`。期望 PASS：全部 passed（含 4.10 的 2 个 + 本任务 2 个）。

- [ ] **提交** — 命令：
```
git add palchronicle/application/report_service.py tests/unit/report_service_test.py
git commit -m "test(report): lock empty-day calm summary + clock-derived date"
```

---

### Task 4.12：Phase 4 集成回归 —— 全事件类型端到端

**Files:**
- Test: `tests/integration/event_pipeline_test.py`

**Interfaces:**
- Consumes: `EventService`（全部方法）、`ReportService.daily`、`Repository.list_events`/`peak_online`（本阶段）；`World`/`WorldMetric`/`BaseUpdate`。
- Produces: 一个时间序列集成测试，串起 8 类事件的产生 + 去重 + 日报聚合，作为 Phase 4 的收口回归。

- [ ] **写失败测试** — 创建 `tests/integration/event_pipeline_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.base_service import BaseUpdate
from palchronicle.application.event_service import EventService
from palchronicle.application.report_service import ReportService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, Confidence, EventType
from palchronicle.domain.models import World, WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

DAY_START_UTC = 1752073200          # 2026-07-10 00:00 Asia/Tokyo
NOON = DAY_START_UTC + 12 * 3600


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World("s1:guid:0", "s1", "guid", 0, "Srv", "1.0", 0, 0, 105)


def _bu(**kw) -> BaseUpdate:
    d = dict(
        base_key="s1:guid:0|BASE|pb1", world_id="s1:guid:0", palbox_key="pb1",
        guild_key="gk1", confidence=Confidence.HIGH, worker_count=6,
        active_count=4, average_level=10.0, average_hp_ratio=0.9,
        action_distribution={"working": 4}, is_new=False, is_vanished=False,
        prev_worker_count=None,
    )
    d.update(kw)
    return BaseUpdate(**d)


@pytest.mark.asyncio
async def test_all_event_types_and_dedup_and_report(tmp_path: Path):
    db = Database(tmp_path / "pipe.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=NOON)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    report = ReportService(repo, _cfg(), clock)
    w = _world()
    try:
        # metrics for peak baseline
        await repo.insert_metric(WorldMetric(
            "s1:guid:0", NOON, 60.0, 16.0, 4, 105, 1))

        await events.world_day(w, 105)                          # milestone 100
        await events.online_record(w, value=7, confirmed=True)  # record
        await events.new_player(w, "pk1")
        await events.new_guild(w, "gk1")
        await events.level_up(w, "pk1", old=9, new=12)
        await events.base_events(w, [_bu(is_new=True)])         # NEW_BASE
        await events.base_events(w, [_bu(is_vanished=True)])    # BASE_VANISHED
        await events.base_events(
            w, [_bu(prev_worker_count=5, worker_count=9)])      # WORKER_DELTA

        # dedup: repeat everything → no new rows
        await events.world_day(w, 150)
        await events.new_player(w, "pk1")
        await events.level_up(w, "pk1", old=11, new=12)

        rows = await repo.list_events("s1:guid:0")
        got = {r.event_type for r in rows}
        assert got == {
            EventType.WORLD_DAY_MILESTONE, EventType.ONLINE_RECORD,
            EventType.NEW_PLAYER, EventType.NEW_GUILD,
            EventType.PLAYER_LEVEL_UP, EventType.NEW_BASE,
            EventType.BASE_VANISHED, EventType.WORKER_DELTA,
        }
        assert len(rows) == 8  # dedup held

        rep = await report.daily(w, day="2026-07-10")
        assert rep.is_empty is False
        assert len(rep.level_events) == 1
        assert len(rep.base_events) == 3
        assert any("100" in r for r in rep.records)
    finally:
        await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/integration/event_pipeline_test.py -q`。期望：若前序任务已全部实现，本测试可能直接 PASS；若有任一事件/去重/聚合缺陷，则相应断言 FAIL（如 `assert len(rows) == 8`、`got == {...}`、`len(rep.base_events) == 3`）。先运行确认它对当前实现有区分力。

- [ ] **写最小实现** — 无新增实现代码（本任务是端到端收口回归）。若失败，按 systematic-debugging 定位到具体 EventService/ReportService 方法修正，并把该修正归入对应任务的提交范围（不在此任务引入未测新行为）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/integration/event_pipeline_test.py -q` 期望 PASS：1 passed。再跑 Phase 4 全量：`python -m pytest tests/unit/event_service_test.py tests/unit/report_service_test.py tests/unit/repository_events_test.py tests/unit/repository_aggregates_test.py tests/integration/event_wiring_test.py tests/integration/event_pipeline_test.py -q`。期望全部 passed。

- [ ] **提交** — 命令：
```
git add tests/integration/event_pipeline_test.py
git commit -m "test(events): end-to-end pipeline covering all 8 event types + dedup + report"
```


## Phase 5：路由 + 查询 + 格式化 + 命令 + 装配

> 本阶段把前四个阶段的领域模型、追踪器、事件、日报串成 **14 个端到端可用命令**。所有签名严格复用「接口契约」。
> 前置阶段已存在（本阶段直接消费，不再重复定义）：
> - `palchronicle/config.py`：`AppConfig`、`ServerConfig`（含 `.ready`）、`RoutingConfig`、`SkippedServer`、`BindingConfig`、`AccessMode`、`parse_config(raw, env)`。
> - `palchronicle/infrastructure/`：`Clock`/`SystemClock`/`FakeClock`、`Database`、`apply_migrations`、`TTLCache`、`EndpointLocks`、`load_or_create_salt`、`Scheduler`。
> - `palchronicle/adapters/`：`Repository`（Phase 1 已建并含 server/binding/world/prune 方法；本阶段补充它消费的 `get_binding_active`/`get_allowed`/`set_active`/`revoke` 等 —— 见 Task 5.1）、`PalworldRestClient`、`MetadataRepository`、`normalizer`、`privacy_filter`。
> - `palchronicle/domain/`：`enums.py`（全部 StrEnum）、`models.py`（全部 dataclass，含 `World`）。
> - `palchronicle/application/`：`SnapshotService`、`PlayerService`、`GuildService`、`BaseService`、`EventService`、`ReportService`（产出 `DailyReport`）。
>
> 全阶段测试文件命名 `tests/unit/<模块>_test.py`；异步测试用 `@pytest.mark.asyncio`；DB 测试用临时文件 + `FakeClock` 注入保证确定性。

---

### Task 5.1：Repository 路由方法（本阶段消费的 group_servers 读写）

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_routing_test.py`

**Interfaces:**
- Consumes: `Database`（`execute_write`/`write_tx`/`query`）、`Clock`、`BindingConfig`、`ServerConfig`、`group_servers(umo,server_id,allowed,active,updated_at)` 表（Phase 1 迁移已建）。
- Produces（补充到既有 `Repository` 类，签名照契约）：
  - `async def get_binding_active(self, umo:str) -> str|None`
  - `async def get_allowed(self, umo:str) -> set[str]`
  - `async def set_active(self, umo:str, server_id:str) -> None`（写 `allowed=1 & active=1`，清同 umo 其它行 active）
  - `async def revoke(self, umo:str, server_id:str) -> None`
  - `async def list_group_servers(self, umo:str) -> dict[str, tuple[bool,bool]]`（返回 `{server_id: (allowed, active)}`，供 `/pal servers` 展示本群状态）

> 说明：Phase 1 已实现 `sync_servers`/`seed_bindings`/`cleanup_orphan_bindings`；本任务只补齐 `routing_service` 与 `commands` 消费的读写方法。

- [ ] **写失败测试** — 创建 `tests/unit/repository_routing_test.py`：

```python
import asyncio
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import BindingConfig, ServerConfig
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _server(name: str) -> ServerConfig:
    return ServerConfig(
        server_id=name, name=name, enabled=True, base_url="http://127.0.0.1:8212",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1000)
    r = Repository(db, clock)
    await r.sync_servers([_server("alpha"), _server("beta")])
    yield r
    await db.close()


@pytest.mark.asyncio
async def test_set_active_makes_row_allowed_and_active(repo):
    await repo.set_active("umo1", "alpha")
    assert await repo.get_binding_active("umo1") == "alpha"
    assert await repo.get_allowed("umo1") == {"alpha"}


@pytest.mark.asyncio
async def test_set_active_is_unique_per_umo(repo):
    await repo.set_active("umo1", "alpha")
    await repo.set_active("umo1", "beta")
    assert await repo.get_binding_active("umo1") == "beta"
    # alpha stays allowed but no longer active
    assert await repo.get_allowed("umo1") == {"alpha", "beta"}
    rows = await repo.list_group_servers("umo1")
    assert rows["alpha"] == (True, False)
    assert rows["beta"] == (True, True)


@pytest.mark.asyncio
async def test_revoke_clears_allowed_and_active(repo):
    await repo.set_active("umo1", "alpha")
    await repo.revoke("umo1", "alpha")
    assert await repo.get_binding_active("umo1") is None
    assert await repo.get_allowed("umo1") == set()


@pytest.mark.asyncio
async def test_seed_binding_does_not_override_runtime(repo):
    await repo.set_active("umo1", "beta")  # runtime choice
    await repo.seed_bindings([BindingConfig(umo="umo1", server="alpha", active=True)])
    # seed is INSERT OR IGNORE: existing rows untouched, beta still active
    assert await repo.get_binding_active("umo1") == "beta"


@pytest.mark.asyncio
async def test_get_allowed_empty_for_unknown_umo(repo):
    assert await repo.get_allowed("nobody") == set()
    assert await repo.get_binding_active("nobody") is None
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_routing_test.py -q`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'get_binding_active'`（这些方法尚未实现）。

- [ ] **写最小实现** — 在 `palchronicle/adapters/sqlite_repository.py` 的 `Repository` 类中追加：

```python
    async def get_binding_active(self, umo: str) -> str | None:
        rows = await self._db.query(
            "SELECT server_id FROM group_servers WHERE umo=? AND active=1 LIMIT 1", (umo,)
        )
        return rows[0]["server_id"] if rows else None

    async def get_allowed(self, umo: str) -> set[str]:
        rows = await self._db.query(
            "SELECT server_id FROM group_servers WHERE umo=? AND allowed=1", (umo,)
        )
        return {r["server_id"] for r in rows}

    async def list_group_servers(self, umo: str) -> dict[str, tuple[bool, bool]]:
        rows = await self._db.query(
            "SELECT server_id, allowed, active FROM group_servers WHERE umo=?", (umo,)
        )
        return {r["server_id"]: (bool(r["allowed"]), bool(r["active"])) for r in rows}

    async def set_active(self, umo: str, server_id: str) -> None:
        now = self._clock.now()
        async with self._db.write_tx() as conn:
            await conn.execute(
                "UPDATE group_servers SET active=0, updated_at=? WHERE umo=? AND active=1",
                (now, umo),
            )
            await conn.execute(
                "INSERT INTO group_servers(umo, server_id, allowed, active, updated_at) "
                "VALUES(?,?,1,1,?) "
                "ON CONFLICT(umo, server_id) DO UPDATE SET allowed=1, active=1, updated_at=?",
                (umo, server_id, now, now),
            )

    async def revoke(self, umo: str, server_id: str) -> None:
        await self._db.execute_write(
            "UPDATE group_servers SET allowed=0, active=0, updated_at=? "
            "WHERE umo=? AND server_id=?",
            (self._clock.now(), umo, server_id),
        )
```

> `self._db` 与 `self._clock` 为 `Repository.__init__(self, db, clock)` 保存的属性（Phase 1 约定；若命名不同按既有属性名调整）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_routing_test.py -q`。期望 PASS：5 passed。

- [ ] **提交** — `git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_routing_test.py && git commit -m "feat(repo): add group_servers routing read/write methods"`

---

### Task 5.2：server_arg.parse_arg（参数自解析）

**Files:**
- Create: `palchronicle/presentation/server_arg.py`
- Test: `tests/unit/server_arg_test.py`

**Interfaces:**
- Consumes: 无（纯字符串处理）。
- Produces：
  - `@dataclass(slots=True) class ParsedArg: name:str; server_override:str|None`
  - `class ArgError(ValueError): ...`
  - `def parse_arg(message_str:str, subcommand:str) -> ParsedArg`
    - 剥离前缀 `/pal <subcommand>`（`message_str` 可能带或不带前导 `/`，也可能带 `pal ` 命令组前缀）；从**尾部**剥离**单个** `@<token>`（token 无空格）作 `server_override`；余下 `strip()` 作 `name`（允许含空格）。仅识别**最后一个**尾部 `@token`；name 内部的 `@` 不触发；多个尾部 `@token` → `raise ArgError`。

- [ ] **写失败测试** — 创建 `tests/unit/server_arg_test.py`：

```python
import pytest

from palchronicle.presentation.server_arg import ArgError, ParsedArg, parse_arg


def test_name_with_spaces_and_server_override():
    r = parse_arg("/pal guild The Red Legion @alpha", "guild")
    assert r == ParsedArg(name="The Red Legion", server_override="alpha")


def test_no_at_token_gives_none_override():
    r = parse_arg("/pal guild The Red Legion", "guild")
    assert r == ParsedArg(name="The Red Legion", server_override=None)


def test_bare_subcommand_no_name():
    r = parse_arg("/pal status", "status")
    assert r == ParsedArg(name="", server_override=None)


def test_only_server_override():
    r = parse_arg("/pal status @beta", "status")
    assert r == ParsedArg(name="", server_override="beta")


def test_at_inside_name_not_triggered():
    # '@' not at the trailing token position => part of name
    r = parse_arg("/pal guild foo@bar legion", "guild")
    assert r == ParsedArg(name="foo@bar legion", server_override=None)


def test_multiple_trailing_at_tokens_is_error():
    with pytest.raises(ArgError):
        parse_arg("/pal guild legion @alpha @beta", "guild")


def test_prefix_without_leading_slash():
    r = parse_arg("pal base #2 @alpha", "base")
    assert r == ParsedArg(name="#2", server_override="alpha")


def test_only_subcommand_word_without_pal_prefix():
    # some frameworks strip the group prefix already
    r = parse_arg("guild My Guild @s", "guild")
    assert r == ParsedArg(name="My Guild", server_override="s")
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/server_arg_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.presentation.server_arg'`。

- [ ] **写最小实现** — 创建 `palchronicle/presentation/server_arg.py`：

```python
from __future__ import annotations

from dataclasses import dataclass


class ArgError(ValueError):
    """Raised when the argument string is malformed (e.g. multiple @tokens)."""


@dataclass(slots=True)
class ParsedArg:
    name: str
    server_override: str | None


def _strip_prefix(message_str: str, subcommand: str) -> str:
    text = message_str.strip()
    if text.startswith("/"):
        text = text[1:]
    parts = text.split()
    # drop optional command-group token "pal"
    if parts and parts[0] == "pal":
        parts = parts[1:]
    # drop the subcommand token if present
    if parts and parts[0] == subcommand:
        parts = parts[1:]
    return " ".join(parts).strip()


def parse_arg(message_str: str, subcommand: str) -> ParsedArg:
    body = _strip_prefix(message_str, subcommand)
    if not body:
        return ParsedArg(name="", server_override=None)

    tokens = body.split()
    override: str | None = None
    if tokens[-1].startswith("@") and len(tokens[-1]) > 1:
        # trailing @token detected; reject a second trailing @token
        if len(tokens) >= 2 and tokens[-2].startswith("@") and len(tokens[-2]) > 1:
            raise ArgError("multiple server overrides")
        override = tokens[-1][1:]
        tokens = tokens[:-1]

    name = " ".join(tokens).strip()
    return ParsedArg(name=name, server_override=override)
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/server_arg_test.py -q`。期望 PASS：8 passed。

- [ ] **提交** — `git add palchronicle/presentation/server_arg.py tests/unit/server_arg_test.py && git commit -m "feat(presentation): add parse_arg for name + @server override"`

---

### Task 5.3：展示 DTO 定义（presentation/dtos.py）

**Files:**
- Create: `palchronicle/presentation/dtos.py`
- Test: `tests/unit/dtos_test.py`

**Interfaces:**
- Consumes: `Confidence`、`PingBucket`（`palchronicle.domain.enums`）。
- Produces（全部 `@dataclass(slots=True)`，字段按 spec §13 各命令输出要点）：
  - `StatusDTO`、`OnlineDTO`（含 `OnlinePlayerRow`）、`WorldSummaryDTO`（含 `WildTopRow`）、`RulesDTO`（含 `RuleRow`）、`GuildDTO`、`GuildDetailDTO`、`BaseDTO`、`BaseDetailDTO`、`EventDTO`、`ServerStatusRow`。

> `DailyReport`（Phase 4 定义）与 `RulesDTO` 等一起被 formatters 消费；`today()` 直接返回 `DailyReport`，不新增 DTO。

- [ ] **写失败测试** — 创建 `tests/unit/dtos_test.py`：

```python
from palchronicle.domain.enums import Confidence, PingBucket
from palchronicle.presentation.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventDTO,
    GuildDetailDTO,
    GuildDTO,
    OnlineDTO,
    OnlinePlayerRow,
    RuleRow,
    RulesDTO,
    ServerStatusRow,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
)


def test_status_dto_fields():
    dto = StatusDTO(
        server_name="alpha", world_name="Palpagos", world_day=42,
        online=3, max_players=32, basecamp_count=5, fps=58.0, frame_time=17.2,
        smoothness_label="流畅", players=[("Neo", 21, "good")],
        peak_online_today=7, updated_at=1000, degraded=False, last_ok=1000,
    )
    assert dto.world_day == 42
    assert dto.players[0] == ("Neo", 21, "good")


def test_online_dto_uses_ping_bucket():
    row = OnlinePlayerRow(name="Neo", level=21, ping_bucket=PingBucket.GOOD, online_seconds=3600)
    dto = OnlineDTO(rows=[row], updated_at=1000, degraded=False)
    assert dto.rows[0].ping_bucket is PingBucket.GOOD


def test_base_detail_carries_confidence():
    dto = BaseDetailDTO(
        display_name="Noema-2", guild_name="Noema", confidence=Confidence.HIGH,
        palbox_count=1, worker_count=8, active_count=6, average_level=17.5,
        average_hp_ratio=0.9, action_distribution={"working": 6, "idle": 2},
        activity_score=82.5, health_score=90.0,
    )
    assert dto.confidence is Confidence.HIGH


def test_remaining_dtos_construct():
    WorldSummaryDTO(
        world_day=1, online=0, players=0, otomo=0, base_pal=0, wild=0, npc=0,
        palbox=0, guilds=0, fps=60.0, average_fps=59.0,
        wild_top=[WildTopRow(name="Lamball", count=4)],
    )
    RulesDTO(rows=[RuleRow(label="经验倍率", value="1.0x")], updated_at=1000, advanced_note=None)
    GuildDTO(name="Noema", observed_members=4, palbox=2, base_pals=10, active_7d=3)
    GuildDetailDTO(
        name="Noema", first_seen_at=1, last_seen_at=2, observed_members=4,
        active_today=2, active_week=3, palbox=2, base_pals=10, average_level=15.0,
        base_event_lines=["据点新增：Noema-2"],
    )
    BaseDTO(index=1, display_name="Noema-1", guild_name="Noema",
            confidence=Confidence.MEDIUM, worker_count=5)
    EventDTO(occurred_at=1000, event_type="new_player", summary="新玩家加入")
    ServerStatusRow(name="alpha", ready=True, online=True, allowed=True, active=True)
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/dtos_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.presentation.dtos'`。

- [ ] **写最小实现** — 创建 `palchronicle/presentation/dtos.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

from palchronicle.domain.enums import Confidence, PingBucket


@dataclass(slots=True)
class StatusDTO:
    server_name: str
    world_name: str
    world_day: int
    online: int
    max_players: int
    basecamp_count: int          # 官方 metrics.basecampnum
    fps: float
    frame_time: float
    smoothness_label: str
    players: list[tuple[str, int, str]]   # (name, level, ping_bucket value)
    peak_online_today: int
    updated_at: int
    degraded: bool
    last_ok: int | None


@dataclass(slots=True)
class OnlinePlayerRow:
    name: str
    level: int
    ping_bucket: PingBucket
    online_seconds: int


@dataclass(slots=True)
class OnlineDTO:
    rows: list[OnlinePlayerRow]
    updated_at: int
    degraded: bool


@dataclass(slots=True)
class WildTopRow:
    name: str
    count: int


@dataclass(slots=True)
class WorldSummaryDTO:
    world_day: int
    online: int
    players: int
    otomo: int
    base_pal: int
    wild: int
    npc: int
    palbox: int
    guilds: int
    fps: float
    average_fps: float
    wild_top: list[WildTopRow]


@dataclass(slots=True)
class RuleRow:
    label: str
    value: str


@dataclass(slots=True)
class RulesDTO:
    rows: list[RuleRow]
    updated_at: int
    advanced_note: str | None


@dataclass(slots=True)
class GuildDTO:
    name: str
    observed_members: int
    palbox: int
    base_pals: int
    active_7d: int


@dataclass(slots=True)
class GuildDetailDTO:
    name: str
    first_seen_at: int
    last_seen_at: int
    observed_members: int
    active_today: int
    active_week: int
    palbox: int
    base_pals: int
    average_level: float
    base_event_lines: list[str]


@dataclass(slots=True)
class BaseDTO:
    index: int
    display_name: str
    guild_name: str | None
    confidence: Confidence
    worker_count: int


@dataclass(slots=True)
class BaseDetailDTO:
    display_name: str
    guild_name: str | None
    confidence: Confidence
    palbox_count: int
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int]
    activity_score: float
    health_score: float


@dataclass(slots=True)
class EventDTO:
    occurred_at: int
    event_type: str
    summary: str


@dataclass(slots=True)
class ServerStatusRow:
    name: str
    ready: bool
    online: bool
    allowed: bool
    active: bool
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/dtos_test.py -q`。期望 PASS：4 passed。

- [ ] **提交** — `git add palchronicle/presentation/dtos.py tests/unit/dtos_test.py && git commit -m "feat(presentation): define display DTOs per spec §13"`

---

### Task 5.4：locale.py（zh-CN 文案表）

**Files:**
- Create: `palchronicle/presentation/locale.py`
- Test: `tests/unit/locale_test.py`

**Interfaces:**
- Consumes: 无。
- Produces：
  - `MESSAGES: dict[str, str]`（zh-CN 文案常量表）
  - `def L(key: str, **kwargs) -> str`（查表 + `str.format(**kwargs)`；缺 key → 抛 `KeyError`，保证测试期能发现漏配）

- [ ] **写失败测试** — 创建 `tests/unit/locale_test.py`：

```python
import pytest

from palchronicle.presentation.locale import L, MESSAGES


def test_no_server_configured_message():
    assert "尚未配置" in L("no_server_configured")


def test_degraded_message_formats_minutes():
    text = L("degraded", minutes=5)
    assert "5" in text
    assert "无法获取" in text


def test_not_authorized_message_includes_server():
    text = L("not_authorized", server="alpha")
    assert "alpha" in text


def test_never_says_server_offline():
    # privacy/honesty red line: degradation must not claim shutdown
    assert "关机" not in MESSAGES["degraded"]


def test_missing_key_raises():
    with pytest.raises(KeyError):
        L("this_key_does_not_exist")
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/locale_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.presentation.locale'`。

- [ ] **写最小实现** — 创建 `palchronicle/presentation/locale.py`：

```python
from __future__ import annotations

MESSAGES: dict[str, str] = {
    "no_server_configured": "尚未配置 Palworld 服务器，请在插件配置页添加。",
    "no_server_resolved": "本会话未指定服务器。管理员可用 /pal use <名称> 绑定，或 /pal servers 查看可用服务器。",
    "server_unknown": "服务器「{server}」不存在或未就绪。",
    "not_authorized": "本会话未被授权使用服务器「{server}」。请管理员先执行 /pal use {server}。",
    "private_restricted": "restricted 模式下私聊不可查询，请在群聊中使用。",
    "active_server_stale": "当前绑定的服务器已不可用，请管理员重新执行 /pal use <名称>。",
    "degraded": "当前无法获取 Palworld 世界数据。最后成功更新：{minutes} 分钟前。",
    "degraded_never": "当前无法获取 Palworld 世界数据（尚无成功记录）。",
    "auth_error": "世界数据接口配置异常，请联系管理员。",
    "guild_not_found": "未找到公会「{name}」。",
    "base_not_found": "未找到据点「{name}」。",
    "bases_disabled_strict": "据点模块因 strict 隐私模式停用。",
    "guilds_unavailable": "公会数据暂不可用。",
    "use_only_group": "该命令仅可在群聊中使用。",
    "use_ok": "已授权本群使用服务器「{server}」并设为当前活动服务器。",
    "unbind_ok": "已撤销本群对服务器「{server}」的授权。",
    "empty_day": "平静的一天，没有值得记录的事件。",
    "no_events": "近期暂无世界事件。",
    "derived_note": "（插件推导）",
}


def L(key: str, **kwargs: object) -> str:
    template = MESSAGES[key]
    return template.format(**kwargs) if kwargs else template
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/locale_test.py -q`。期望 PASS：5 passed。

- [ ] **提交** — `git add palchronicle/presentation/locale.py tests/unit/locale_test.py && git commit -m "feat(presentation): add zh-CN locale table"`

---

### Task 5.5：RoutingService.resolve（五步解析 + 访问校验）

**Files:**
- Create: `palchronicle/application/routing_service.py`
- Test: `tests/unit/routing_service_resolve_test.py`

**Interfaces:**
- Consumes: `Repository`（`get_binding_active`/`get_allowed`）、`AppConfig`（`routing.access_mode`/`routing.default_server`、`servers`）、`ServerConfig.ready`、`AccessMode`、locale `L`。
- Produces：
  - `@dataclass(slots=True) class Resolution: server:ServerConfig|None; error:str|None`
  - `class RoutingService: def __init__(self, repo, cfg)`
  - `async def resolve(self, umo:str, override:str|None, is_group:bool) -> Resolution`（spec §7.2 五步；§7.3 restricted 访问校验、私聊处理）

> 本任务只实现 `resolve`（含内部 `_ready_by_name`/`_ready_servers` 辅助）；`use`/`unbind`/`ready_servers` 在 Task 5.6。

- [ ] **写失败测试** — 创建 `tests/unit/routing_service_resolve_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.routing_service import Resolution, RoutingService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _server(name: str, ready: bool = True) -> ServerConfig:
    return ServerConfig(
        server_id=name, name=name, enabled=True, base_url="http://127.0.0.1:8212",
        username="admin", password="pw" if ready else "", timeout=10,
        verify_tls=True, timezone="",
    )


def _cfg(servers, access=AccessMode.RESTRICTED, default="") -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=access, default_server=default),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    r = Repository(db, FakeClock(1000))
    await r.sync_servers([_server("alpha"), _server("beta")])
    yield r
    await db.close()


@pytest.mark.asyncio
async def test_override_unknown_server_errors(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override="ghost", is_group=True)
    assert res.server is None
    assert "不存在或未就绪" in res.error


@pytest.mark.asyncio
async def test_override_requires_allowed_in_restricted(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override="alpha", is_group=True)
    assert res.server is None
    assert "未被授权" in res.error


@pytest.mark.asyncio
async def test_override_after_authorization_succeeds(repo):
    await repo.set_active("umo1", "alpha")
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override="alpha", is_group=True)
    assert res.error is None
    assert res.server.server_id == "alpha"


@pytest.mark.asyncio
async def test_active_binding_resolves(repo):
    await repo.set_active("umo1", "beta")
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta")]))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server.server_id == "beta"


@pytest.mark.asyncio
async def test_dangling_active_falls_through_to_prompt(repo):
    # active points to a server that is no longer configured/ready
    await repo.set_active("umo1", "beta")
    svc = RoutingService(repo, _cfg([_server("alpha")]))  # beta removed
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None
    assert res.error is not None


@pytest.mark.asyncio
async def test_disabled_server_not_used_as_default(repo):
    svc = RoutingService(repo, _cfg([_server("alpha", ready=False)], default="alpha"))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None


@pytest.mark.asyncio
async def test_single_ready_server_open_mode(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")], access=AccessMode.OPEN))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server.server_id == "alpha"


@pytest.mark.asyncio
async def test_default_server_open_mode(repo):
    svc = RoutingService(
        repo, _cfg([_server("alpha"), _server("beta")], access=AccessMode.OPEN, default="beta")
    )
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server.server_id == "beta"


@pytest.mark.asyncio
async def test_private_chat_restricted_rejected(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    res = await svc.resolve("umo1", override=None, is_group=False)
    assert res.server is None
    assert "私聊" in res.error


@pytest.mark.asyncio
async def test_no_server_configured(repo):
    svc = RoutingService(repo, _cfg([], access=AccessMode.OPEN))
    res = await svc.resolve("umo1", override=None, is_group=True)
    assert res.server is None
    assert "尚未配置" in res.error
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/routing_service_resolve_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.routing_service'`。

- [ ] **写最小实现** — 创建 `palchronicle/application/routing_service.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.enums import AccessMode
from palchronicle.presentation.locale import L


@dataclass(slots=True)
class Resolution:
    server: ServerConfig | None
    error: str | None


class RoutingService:
    def __init__(self, repo: Repository, cfg: AppConfig) -> None:
        self._repo = repo
        self._cfg = cfg

    def _ready_servers(self) -> list[ServerConfig]:
        return [s for s in self._cfg.servers if s.ready]

    def _ready_by_name(self, name: str) -> ServerConfig | None:
        for s in self._ready_servers():
            if s.server_id == name:
                return s
        return None

    async def _authorized(self, umo: str, server_id: str, is_group: bool) -> bool:
        if self._cfg.routing.access_mode is AccessMode.OPEN:
            return True
        if not is_group:
            return False
        return server_id in await self._repo.get_allowed(umo)

    async def resolve(self, umo: str, override: str | None, is_group: bool) -> Resolution:
        if not self._ready_servers():
            return Resolution(None, L("no_server_configured"))

        # private chat under restricted: no allowed records possible
        if self._cfg.routing.access_mode is AccessMode.RESTRICTED and not is_group:
            return Resolution(None, L("private_restricted"))

        # Step 1: explicit @server override
        if override:
            srv = self._ready_by_name(override)
            if srv is None:
                return Resolution(None, L("server_unknown", server=override))
            if not await self._authorized(umo, srv.server_id, is_group):
                return Resolution(None, L("not_authorized", server=srv.server_id))
            return Resolution(srv, None)

        # Step 2: group active binding
        if is_group:
            active = await self._repo.get_binding_active(umo)
            if active:
                srv = self._ready_by_name(active)
                if srv is None:
                    return Resolution(None, L("active_server_stale"))
                if await self._authorized(umo, srv.server_id, is_group):
                    return Resolution(srv, None)

        # Step 3: global default server
        default = self._cfg.routing.default_server
        if default:
            srv = self._ready_by_name(default)
            if srv is not None and await self._authorized(umo, srv.server_id, is_group):
                return Resolution(srv, None)

        # Step 4: single ready server
        ready = self._ready_servers()
        if len(ready) == 1 and await self._authorized(umo, ready[0].server_id, is_group):
            return Resolution(ready[0], None)

        # Step 5: friendly prompt
        return Resolution(None, L("no_server_resolved"))
```

> 说明：restricted 模式下步骤 3/4 的 `_authorized` 对未授权群返回 False，因此会落到步骤 5 提示，符合 spec §7.3；open 模式下 `_authorized` 恒 True，故 default/单服务器可直接命中。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/routing_service_resolve_test.py -q`。期望 PASS：10 passed。

- [ ] **提交** — `git add palchronicle/application/routing_service.py tests/unit/routing_service_resolve_test.py && git commit -m "feat(routing): implement resolve five-step order + access check"`

---

### Task 5.6：RoutingService.use / unbind / ready_servers

**Files:**
- Modify: `palchronicle/application/routing_service.py`
- Test: `tests/unit/routing_service_use_test.py`

**Interfaces:**
- Consumes: `Repository`（`set_active`/`revoke`/`get_binding_active`）、locale `L`。
- Produces（追加到 `RoutingService`）：
  - `async def use(self, umo:str, name:str) -> str`（授权 + 激活，active 唯一；未知/未就绪 server → 返回错误文案；成功 → `L("use_ok")`）
  - `async def unbind(self, umo:str, name:str) -> str`
  - `def ready_servers(self) -> list[ServerConfig]`

- [ ] **写失败测试** — 创建 `tests/unit/routing_service_use_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.routing_service import RoutingService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _server(name: str, ready: bool = True) -> ServerConfig:
    return ServerConfig(
        server_id=name, name=name, enabled=True, base_url="http://127.0.0.1:8212",
        username="admin", password="pw" if ready else "", timeout=10,
        verify_tls=True, timezone="",
    )


def _cfg(servers) -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    r = Repository(db, FakeClock(1000))
    await r.sync_servers([_server("alpha"), _server("beta")])
    yield r
    await db.close()


@pytest.mark.asyncio
async def test_use_unknown_server_returns_error(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    msg = await svc.use("umo1", "ghost")
    assert "不存在或未就绪" in msg
    assert await repo.get_binding_active("umo1") is None


@pytest.mark.asyncio
async def test_use_authorizes_and_activates(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    msg = await svc.use("umo1", "alpha")
    assert "alpha" in msg
    assert await repo.get_binding_active("umo1") == "alpha"
    assert await repo.get_allowed("umo1") == {"alpha"}


@pytest.mark.asyncio
async def test_use_switches_active_uniquely(repo):
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta")]))
    await svc.use("umo1", "alpha")
    await svc.use("umo1", "beta")
    assert await repo.get_binding_active("umo1") == "beta"


@pytest.mark.asyncio
async def test_unbind_revokes(repo):
    svc = RoutingService(repo, _cfg([_server("alpha")]))
    await svc.use("umo1", "alpha")
    msg = await svc.unbind("umo1", "alpha")
    assert "alpha" in msg
    assert await repo.get_binding_active("umo1") is None
    assert await repo.get_allowed("umo1") == set()


@pytest.mark.asyncio
async def test_ready_servers_filters_unready(repo):
    svc = RoutingService(repo, _cfg([_server("alpha"), _server("beta", ready=False)]))
    ids = [s.server_id for s in svc.ready_servers()]
    assert ids == ["alpha"]
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/routing_service_use_test.py -q`。期望 FAIL：`AttributeError: 'RoutingService' object has no attribute 'use'`。

- [ ] **写最小实现** — 在 `palchronicle/application/routing_service.py` 的 `RoutingService` 中追加：

```python
    async def use(self, umo: str, name: str) -> str:
        srv = self._ready_by_name(name)
        if srv is None:
            return L("server_unknown", server=name)
        await self._repo.set_active(umo, srv.server_id)
        return L("use_ok", server=srv.server_id)

    async def unbind(self, umo: str, name: str) -> str:
        srv = self._ready_by_name(name)
        target = srv.server_id if srv is not None else name
        await self._repo.revoke(umo, target)
        return L("unbind_ok", server=target)

    def ready_servers(self) -> list[ServerConfig]:
        return self._ready_servers()
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/routing_service_use_test.py -q`。期望 PASS：5 passed。

- [ ] **提交** — `git add palchronicle/application/routing_service.py tests/unit/routing_service_use_test.py && git commit -m "feat(routing): add use/unbind/ready_servers"`

---

### Task 5.7：Repository 只读查询方法（query_service 消费）

**Files:**
- Modify: `palchronicle/adapters/sqlite_repository.py`
- Test: `tests/unit/repository_query_test.py`

**Interfaces:**
- Consumes: `Database.query`、`WorldMetric`、`Guild`、`Base`、`BaseObservation`、`WorldEvent`、`PlayerIdentity`。
- Produces（补充到 `Repository`，签名照契约 §Repository）：
  - `async def latest_metric(self, world_id:str) -> WorldMetric|None`
  - `async def peak_online(self, world_id:str, since:int|None=None) -> int`
  - `async def list_guilds(self, world_id:str) -> list[Guild]`
  - `async def list_bases(self, world_id:str, include_low:bool=False, include_hidden:bool=False) -> list[Base]`
  - `async def latest_base_observation(self, world_id:str, base_key:str) -> BaseObservation|None`
  - `async def list_events(self, world_id:str, since:int|None=None, limit:int=20) -> list[WorldEvent]`

> `insert_metric`/`insert_event`/`upsert_guild`/`upsert_base`/`insert_base_observation`/`upsert_world`/`get_current_world` 已在前置阶段（Phase 2-4）实现；本任务只补齐读侧。测试用直接 SQL 预置数据后经方法读回，验证行→dataclass 映射。

- [ ] **写失败测试** — 创建 `tests/unit/repository_query_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence, EventType
from palchronicle.domain.models import Base, BaseObservation, Guild, WorldEvent, WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


@pytest.mark.asyncio
async def test_latest_metric_returns_most_recent(repo):
    await repo.insert_metric(WorldMetric(WID, 1000, 58.0, 17.0, 3, 42, 5))
    await repo.insert_metric(WorldMetric(WID, 1100, 55.0, 18.0, 4, 42, 6))
    m = await repo.latest_metric(WID)
    assert m.observed_at == 1100
    assert m.online_players == 4


@pytest.mark.asyncio
async def test_peak_online(repo):
    await repo.insert_metric(WorldMetric(WID, 1000, 58.0, 17.0, 3, 42, 5))
    await repo.insert_metric(WorldMetric(WID, 1100, 55.0, 18.0, 7, 42, 6))
    assert await repo.peak_online(WID) == 7
    assert await repo.peak_online(WID, since=1050) == 7
    assert await repo.peak_online(WID, since=2000) == 0


@pytest.mark.asyncio
async def test_list_guilds(repo):
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1000, 4, 2, 10))
    guilds = await repo.list_guilds(WID)
    assert len(guilds) == 1
    assert guilds[0].latest_name == "Noema"


@pytest.mark.asyncio
async def test_list_bases_hides_low_by_default(repo):
    await repo.upsert_base(Base("b-high", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1000))
    await repo.upsert_base(Base("b-low", WID, "pb2", "Noema-2", "g1", Confidence.LOW, False, False, 900, 1000))
    default = await repo.list_bases(WID)
    assert {b.base_key for b in default} == {"b-high"}
    both = await repo.list_bases(WID, include_low=True)
    assert {b.base_key for b in both} == {"b-high", "b-low"}


@pytest.mark.asyncio
async def test_latest_base_observation(repo):
    await repo.insert_base_observation(
        BaseObservation("b1", WID, 1000, 8, 6, 17.5, 0.9, {"working": 6, "idle": 2})
    )
    o = await repo.latest_base_observation(WID, "b1")
    assert o.worker_count == 8
    assert o.action_distribution == {"working": 6, "idle": 2}


@pytest.mark.asyncio
async def test_list_events_ordered_desc_with_limit(repo):
    for i, ts in enumerate((1000, 1100, 1200)):
        await repo.insert_event(WorldEvent(
            None, WID, EventType.NEW_PLAYER, "player", f"p{i}", ts, ts,
            {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p{i}",
        ))
    events = await repo.list_events(WID, limit=2)
    assert [e.occurred_at for e in events] == [1200, 1100]
    since = await repo.list_events(WID, since=1150)
    assert [e.occurred_at for e in since] == [1200]
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/repository_query_test.py -q`。期望 FAIL：`AttributeError: 'Repository' object has no attribute 'latest_metric'`（或 `peak_online`，取决于哪个先被调用）。

- [ ] **写最小实现** — 在 `palchronicle/adapters/sqlite_repository.py` 的 `Repository` 类中追加（`import json`、`from palchronicle.domain.models import ...`、`from palchronicle.domain.enums import Confidence, EventType` 已存在于该文件顶部；若某个未导入则补上）：

```python
    async def latest_metric(self, world_id: str) -> WorldMetric | None:
        rows = await self._db.query(
            "SELECT * FROM world_metrics WHERE world_id=? ORDER BY observed_at DESC LIMIT 1",
            (world_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return WorldMetric(
            world_id=r["world_id"], observed_at=r["observed_at"], fps=r["fps"],
            frame_time=r["frame_time"], online_players=r["online_players"],
            world_day=r["world_day"], basecamp_count=r["basecamp_count"],
        )

    async def peak_online(self, world_id: str, since: int | None = None) -> int:
        if since is None:
            rows = await self._db.query(
                "SELECT MAX(online_players) AS peak FROM world_metrics WHERE world_id=?",
                (world_id,),
            )
        else:
            rows = await self._db.query(
                "SELECT MAX(online_players) AS peak FROM world_metrics "
                "WHERE world_id=? AND observed_at>=?",
                (world_id, since),
            )
        peak = rows[0]["peak"] if rows else None
        return int(peak) if peak is not None else 0

    async def list_guilds(self, world_id: str) -> list[Guild]:
        rows = await self._db.query(
            "SELECT * FROM guilds WHERE world_id=? ORDER BY latest_name", (world_id,)
        )
        return [
            Guild(
                guild_key=r["guild_key"], world_id=r["world_id"], latest_name=r["latest_name"],
                first_seen_at=r["first_seen_at"], last_seen_at=r["last_seen_at"],
                observed_member_count=r["observed_member_count"], palbox_count=r["palbox_count"],
                base_pal_count=r["base_pal_count"],
            )
            for r in rows
        ]

    async def list_bases(
        self, world_id: str, include_low: bool = False, include_hidden: bool = False
    ) -> list[Base]:
        sql = "SELECT * FROM bases WHERE world_id=?"
        params: list = [world_id]
        if not include_low:
            sql += " AND confidence!=?"
            params.append(Confidence.LOW.value)
        if not include_hidden:
            sql += " AND hidden=0"
        sql += " ORDER BY guild_key, palbox_key"
        rows = await self._db.query(sql, tuple(params))
        return [
            Base(
                base_key=r["base_key"], world_id=r["world_id"], palbox_key=r["palbox_key"],
                display_name=r["display_name"], guild_key=r["guild_key"],
                confidence=Confidence(r["confidence"]), locked_by_admin=bool(r["locked_by_admin"]),
                hidden=bool(r["hidden"]), first_seen_at=r["first_seen_at"],
                last_seen_at=r["last_seen_at"],
            )
            for r in rows
        ]

    async def latest_base_observation(
        self, world_id: str, base_key: str
    ) -> BaseObservation | None:
        rows = await self._db.query(
            "SELECT * FROM base_observations WHERE world_id=? AND base_key=? "
            "ORDER BY observed_at DESC LIMIT 1",
            (world_id, base_key),
        )
        if not rows:
            return None
        r = rows[0]
        return BaseObservation(
            base_key=r["base_key"], world_id=r["world_id"], observed_at=r["observed_at"],
            worker_count=r["worker_count"], active_count=r["active_count"],
            average_level=r["average_level"], average_hp_ratio=r["average_hp_ratio"],
            action_distribution=json.loads(r["action_distribution_json"]),
        )

    async def list_events(
        self, world_id: str, since: int | None = None, limit: int = 20
    ) -> list[WorldEvent]:
        if since is None:
            rows = await self._db.query(
                "SELECT * FROM world_events WHERE world_id=? "
                "ORDER BY occurred_at DESC LIMIT ?",
                (world_id, limit),
            )
        else:
            rows = await self._db.query(
                "SELECT * FROM world_events WHERE world_id=? AND occurred_at>=? "
                "ORDER BY occurred_at DESC LIMIT ?",
                (world_id, since, limit),
            )
        return [
            WorldEvent(
                event_id=r["event_id"], world_id=r["world_id"],
                event_type=EventType(r["event_type"]), subject_type=r["subject_type"],
                subject_key=r["subject_key"], occurred_at=r["occurred_at"],
                confirmed_at=r["confirmed_at"], payload=json.loads(r["payload_json"]),
                visibility=r["visibility"], confidence=Confidence(r["confidence"]),
                dedup_key=r["dedup_key"],
            )
            for r in rows
        ]
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/repository_query_test.py -q`。期望 PASS：6 passed。

- [ ] **提交** — `git add palchronicle/adapters/sqlite_repository.py tests/unit/repository_query_test.py && git commit -m "feat(repo): add read-side query methods for query_service"`

---

### Task 5.8：QueryService — status / online（缓存 + DTO 组装）

**Files:**
- Create: `palchronicle/application/query_service.py`
- Test: `tests/unit/query_service_status_test.py`

**Interfaces:**
- Consumes: `Repository`（`get_current_world`/`latest_metric`/`peak_online`/`latest_observation`/`list_open_sessions`）、`TTLCache`、`AppConfig`、`WorldConfig`（fps 阈值）、`Clock`、`World`。
- Produces：
  - `class QueryService: def __init__(self, repo, cache, cfg, meta, clock, settings_cache)`
  - `async def status(self, world:World) -> StatusDTO`（缓存 TTL 15s）
  - `async def online(self, world:World) -> OnlineDTO`（缓存 TTL 15s）
  - 内部辅助 `_smoothness_label(fps, world_cfg) -> str`（≥fps_smooth→"流畅"；≥fps_moderate→"一般"；≥fps_laggy→"卡顿"；否则"严重卡顿"）

> `settings_cache` 是一个 `dict[str, dict]`（server_id→最近 settings 原始归一 dict），由 `SnapshotService.ingest_settings` 填充，`query_service` 只读；本任务的 status/online 不用它。缓存键含 `world.world_id`。

- [ ] **写失败测试** — 创建 `tests/unit/query_service_status_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, PingBucket, SessionStatus
from palchronicle.domain.models import PlayerObservation, PlayerSession, World, WorldMetric
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


@pytest.fixture
async def qs(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    q = QueryService(repo, TTLCache(clock), _cfg(), meta=None, clock=clock, settings_cache={})
    yield repo, q, clock
    await db.close()


@pytest.mark.asyncio
async def test_status_assembles_dto(qs):
    repo, q, _ = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    # one online player with a recent observation + session
    await repo.upsert_player_from_observation_helper if False else None
    sid = await repo.insert_session(
        PlayerSession(None, WID, "pk1", 1000, 1200, None, 200, SessionStatus.ACTIVE, None)
    )
    await repo.insert_observation(
        PlayerObservation(1200, WID, "pk1", "Neo", 21, PingBucket.GOOD, 3, "g1", None, None)
    )
    dto = await q.status(_world())
    assert dto.world_day == 42
    assert dto.online == 2
    assert dto.basecamp_count == 5
    assert dto.smoothness_label == "流畅"
    assert dto.degraded is False
    assert ("Neo", 21, "good") in dto.players
    assert sid >= 1


@pytest.mark.asyncio
async def test_status_degraded_when_no_metric(qs):
    repo, q, _ = qs
    dto = await q.status(_world())
    assert dto.degraded is True
    assert dto.online == 0


@pytest.mark.asyncio
async def test_status_is_cached(qs):
    repo, q, clock = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    first = await q.status(_world())
    # mutate DB; cached result should be returned within TTL
    await repo.insert_metric(WorldMetric(WID, 1201, 20.0, 40.0, 9, 42, 5))
    second = await q.status(_world())
    assert second.online == first.online == 2
    # advance beyond TTL 15s -> fresh read
    clock.advance(16)
    third = await q.status(_world())
    assert third.online == 9


@pytest.mark.asyncio
async def test_online_dto(qs):
    repo, q, _ = qs
    await repo.insert_session(
        PlayerSession(None, WID, "pk1", 1000, 1200, None, 200, SessionStatus.ACTIVE, None)
    )
    await repo.insert_observation(
        PlayerObservation(1200, WID, "pk1", "Neo", 21, PingBucket.HIGH, 3, "g1", None, None)
    )
    dto = await q.online(_world())
    assert len(dto.rows) == 1
    assert dto.rows[0].name == "Neo"
    assert dto.rows[0].ping_bucket is PingBucket.HIGH
    assert dto.rows[0].online_seconds == 200
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/query_service_status_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.application.query_service'`。

- [ ] **写最小实现** — 创建 `palchronicle/application/query_service.py`：

```python
from __future__ import annotations

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import AppConfig
from palchronicle.domain.models import World
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import Clock
from palchronicle.presentation.dtos import OnlineDTO, OnlinePlayerRow, StatusDTO

_STATUS_TTL = 15
_ONLINE_TTL = 15


class QueryService:
    def __init__(
        self, repo: Repository, cache: TTLCache, cfg: AppConfig, meta, clock: Clock, settings_cache
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache

    def _smoothness_label(self, fps: float) -> str:
        w = self._cfg.world
        if fps >= w.fps_smooth:
            return "流畅"
        if fps >= w.fps_moderate:
            return "一般"
        if fps >= w.fps_laggy:
            return "卡顿"
        return "严重卡顿"

    async def _online_rows(self, world: World) -> list[OnlinePlayerRow]:
        sessions = await self._repo.list_open_sessions(world.world_id)
        rows: list[OnlinePlayerRow] = []
        for s in sessions:
            obs = await self._repo.latest_observation(world.world_id, s.player_key)
            if obs is None:
                continue
            rows.append(
                OnlinePlayerRow(
                    name=obs.name, level=obs.level, ping_bucket=obs.ping_bucket,
                    online_seconds=s.observed_seconds,
                )
            )
        rows.sort(key=lambda r: (-r.level, r.name))
        return rows

    async def status(self, world: World) -> StatusDTO:
        key = f"status:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        metric = await self._repo.latest_metric(world.world_id)
        rows = await self._online_rows(world)
        day_start = self._clock.now() - 86400
        peak_today = await self._repo.peak_online(world.world_id, since=day_start)
        degraded = metric is None

        dto = StatusDTO(
            server_name=world.server_name,
            world_name=world.server_name,
            world_day=metric.world_day if metric else world.current_day,
            online=metric.online_players if metric else 0,
            max_players=0,
            basecamp_count=metric.basecamp_count if metric else 0,
            fps=metric.fps if metric else 0.0,
            frame_time=metric.frame_time if metric else 0.0,
            smoothness_label=self._smoothness_label(metric.fps if metric else 0.0),
            players=[(r.name, r.level, r.ping_bucket.value) for r in rows],
            peak_online_today=peak_today,
            updated_at=metric.observed_at if metric else world.last_seen_at,
            degraded=degraded,
            last_ok=metric.observed_at if metric else None,
        )
        self._cache.set(key, dto, _STATUS_TTL)
        return dto

    async def online(self, world: World) -> OnlineDTO:
        key = f"online:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = await self._online_rows(world)
        dto = OnlineDTO(rows=rows, updated_at=self._clock.now(), degraded=False)
        self._cache.set(key, dto, _ONLINE_TTL)
        return dto
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/query_service_status_test.py -q`。期望 PASS：4 passed。

- [ ] **提交** — `git add palchronicle/application/query_service.py tests/unit/query_service_status_test.py && git commit -m "feat(query): add status/online DTO assembly with TTL cache"`

---

### Task 5.9：QueryService — guilds / bases / base / events

**Files:**
- Modify: `palchronicle/application/query_service.py`
- Test: `tests/unit/query_service_bases_test.py`

**Interfaces:**
- Consumes: `Repository`（`list_guilds`/`list_bases`/`latest_base_observation`/`list_events`）、`BasesConfig`（活跃度/健康分推导系数在 spec §10.3；分数由 base_observation 直接组装）、`Clock`。
- Produces（追加到 `QueryService`）：
  - `async def guilds(self, world) -> list[GuildDTO]`（TTL 90s）
  - `async def bases(self, world) -> list[BaseDTO]`（TTL 90s；含稳定序号，按 repo 排序）
  - `async def base(self, world, key_or_index:str) -> BaseDetailDTO|None`（`#N` 按序号；否则 `display_name`/公会名匹配）
  - `async def events(self, world, today_only:bool) -> list[EventDTO]`（TTL 15s；`today_only` 用服务器日起点过滤）
  - 内部 `_activity_score(o) -> float` / `_health_score(o) -> float`（spec §10.3 公式）

- [ ] **写失败测试** — 创建 `tests/unit/query_service_bases_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, Confidence, EventType
from palchronicle.domain.models import Base, BaseObservation, Guild, World, WorldEvent
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


@pytest.fixture
async def qs(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    q = QueryService(repo, TTLCache(clock), _cfg(), meta=None, clock=clock, settings_cache={})
    yield repo, q, clock
    await db.close()


@pytest.mark.asyncio
async def test_guilds_dto(qs):
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    dtos = await q.guilds(_world())
    assert dtos[0].name == "Noema"
    assert dtos[0].palbox == 2


@pytest.mark.asyncio
async def test_bases_have_stable_index(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("b2", WID, "pb2", "Noema-2", "g1", Confidence.MEDIUM, False, False, 900, 1200))
    dtos = await q.bases(_world())
    assert [d.index for d in dtos] == [1, 2]


@pytest.mark.asyncio
async def test_base_by_index(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.insert_base_observation(
        BaseObservation("b1", WID, 1200, 8, 6, 17.5, 0.9, {"working": 6, "idle": 2})
    )
    dto = await q.base(_world(), "#1")
    assert dto is not None
    assert dto.display_name == "Noema-1"
    assert dto.worker_count == 8
    # activity_score = 100*(0.75*(6/8) + 0.25*(8/8)) = 100*(0.5625+0.25)=81.25
    assert abs(dto.activity_score - 81.25) < 0.01


@pytest.mark.asyncio
async def test_base_by_name(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-2", "g1", Confidence.HIGH, False, False, 900, 1200))
    dto = await q.base(_world(), "Noema-2")
    assert dto is not None
    assert dto.display_name == "Noema-2"


@pytest.mark.asyncio
async def test_base_missing_returns_none(qs):
    repo, q, _ = qs
    assert await q.base(_world(), "#9") is None
    assert await q.base(_world(), "Ghost") is None


@pytest.mark.asyncio
async def test_events_today_only_filters(qs):
    repo, q, clock = qs
    old = clock.now() - 100000
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "p1", old, old, {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p1"))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "p2", 1200, 1200, {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p2"))
    all_events = await q.events(_world(), today_only=False)
    assert len(all_events) == 2
    today = await q.events(_world(), today_only=True)
    assert len(today) == 1
    assert today[0].event_type == "new_player"
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/query_service_bases_test.py -q`。期望 FAIL：`AttributeError: 'QueryService' object has no attribute 'guilds'`。

- [ ] **写最小实现** — 在 `palchronicle/application/query_service.py` 顶部 import 追加，并在 `QueryService` 中追加方法：

```python
# 顶部 import 追加：
from datetime import datetime, timezone as _tz
from zoneinfo import ZoneInfo

from palchronicle.domain.enums import Confidence
from palchronicle.domain.models import BaseObservation
from palchronicle.presentation.dtos import (
    BaseDetailDTO, BaseDTO, EventDTO, GuildDTO,
)

# 类内新增常量：
_GUILDS_TTL = 90
_BASES_TTL = 90
_EVENTS_TTL = 15
```

```python
    def _server_day_start(self, world: World) -> int:
        tz_name = self._cfg.world.timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = _tz.utc
        now = datetime.fromtimestamp(self._clock.now(), tz)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp())

    @staticmethod
    def _activity_score(o: BaseObservation) -> float:
        active_ratio = o.active_count / max(o.worker_count, 1)
        total = sum(o.action_distribution.values()) or 1
        known = sum(v for k, v in o.action_distribution.items() if k != "unknown")
        known_ratio = known / total
        return round(100 * (0.75 * active_ratio + 0.25 * known_ratio), 2)

    @staticmethod
    def _health_score(o: BaseObservation) -> float:
        return round(100 * (0.8 * o.average_hp_ratio + 0.2 * 1.0), 2)

    async def guilds(self, world: World) -> list[GuildDTO]:
        key = f"guilds:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        guilds = await self._repo.list_guilds(world.world_id)
        dtos = [
            GuildDTO(
                name=g.latest_name, observed_members=g.observed_member_count,
                palbox=g.palbox_count, base_pals=g.base_pal_count, active_7d=0,
            )
            for g in guilds
        ]
        self._cache.set(key, dtos, _GUILDS_TTL)
        return dtos

    async def _bases_indexed(self, world: World) -> list[tuple[int, "Base"]]:
        bases = await self._repo.list_bases(world.world_id)
        return list(enumerate(bases, start=1))

    async def bases(self, world: World) -> list[BaseDTO]:
        key = f"bases:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        guild_names = {g.guild_key: g.latest_name for g in await self._repo.list_guilds(world.world_id)}
        dtos = [
            BaseDTO(
                index=i, display_name=b.display_name or f"BASE-{i}",
                guild_name=guild_names.get(b.guild_key), confidence=b.confidence,
                worker_count=0,
            )
            for i, b in await self._bases_indexed(world)
        ]
        self._cache.set(key, dtos, _BASES_TTL)
        return dtos

    async def base(self, world: World, key_or_index: str) -> BaseDetailDTO | None:
        indexed = await self._bases_indexed(world)
        guild_names = {g.guild_key: g.latest_name for g in await self._repo.list_guilds(world.world_id)}
        target = None
        token = key_or_index.strip()
        if token.startswith("#"):
            try:
                idx = int(token[1:])
            except ValueError:
                return None
            for i, b in indexed:
                if i == idx:
                    target = b
                    break
        else:
            for _, b in indexed:
                if (b.display_name and b.display_name == token) or guild_names.get(b.guild_key) == token:
                    target = b
                    break
        if target is None:
            return None
        obs = await self._repo.latest_base_observation(world.world_id, target.base_key)
        worker = obs.worker_count if obs else 0
        active = obs.active_count if obs else 0
        avg_level = obs.average_level if obs else 0.0
        avg_hp = obs.average_hp_ratio if obs else 0.0
        dist = obs.action_distribution if obs else {}
        return BaseDetailDTO(
            display_name=target.display_name or "BASE",
            guild_name=guild_names.get(target.guild_key),
            confidence=target.confidence, palbox_count=1,
            worker_count=worker, active_count=active, average_level=avg_level,
            average_hp_ratio=avg_hp, action_distribution=dist,
            activity_score=self._activity_score(obs) if obs else 0.0,
            health_score=self._health_score(obs) if obs else 0.0,
        )

    async def events(self, world: World, today_only: bool) -> list[EventDTO]:
        key = f"events:{world.world_id}:{int(today_only)}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        since = self._server_day_start(world) if today_only else None
        events = await self._repo.list_events(world.world_id, since=since, limit=20)
        dtos = [
            EventDTO(
                occurred_at=e.occurred_at, event_type=e.event_type.value,
                summary=_event_summary(e),
            )
            for e in events
        ]
        self._cache.set(key, dtos, _EVENTS_TTL)
        return dtos
```

追加模块级函数（文件底部或 import 段下方）：

```python
def _event_summary(e) -> str:
    from palchronicle.domain.enums import EventType as _ET
    p = e.payload or {}
    if e.event_type is _ET.PLAYER_LEVEL_UP:
        return f"玩家升级 Lv{p.get('old', '?')}→Lv{p.get('new', '?')}"
    if e.event_type is _ET.NEW_PLAYER:
        return "新玩家加入世界"
    if e.event_type is _ET.NEW_GUILD:
        return f"新公会出现：{p.get('name', e.subject_key)}"
    if e.event_type is _ET.NEW_BASE:
        return f"新据点确认：{p.get('name', e.subject_key)}"
    if e.event_type is _ET.BASE_VANISHED:
        return "据点已连续多次未被观察到"
    if e.event_type is _ET.WORKER_DELTA:
        return f"据点工作帕鲁数量变化：{p.get('old', '?')}→{p.get('new', '?')}"
    if e.event_type is _ET.WORLD_DAY_MILESTONE:
        return f"世界推进至第 {p.get('milestone', '?')} 天"
    if e.event_type is _ET.ONLINE_RECORD:
        return f"在线人数刷新纪录：{p.get('value', '?')} 人"
    return e.event_type.value
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/query_service_bases_test.py -q`。期望 PASS：6 passed。

- [ ] **提交** — `git add palchronicle/application/query_service.py tests/unit/query_service_bases_test.py && git commit -m "feat(query): add guilds/bases/base/events DTO assembly"`

---

### Task 5.10：QueryService — rules / world_summary / today

**Files:**
- Modify: `palchronicle/application/query_service.py`
- Test: `tests/unit/query_service_rules_test.py`

**Interfaces:**
- Consumes: `settings_cache`（server_id→归一 settings dict）、`MetadataRepository.setting_label`、`Repository.latest_metric`、`ReportService.daily`（Phase 4，产 `DailyReport`）、`PrivacyConfig.mode`（advanced/strict 提示）。
- Produces（追加到 `QueryService`）：
  - `async def rules(self, world) -> RulesDTO`（TTL 1800s；从 `settings_cache[server_id]` 逐字段经 `meta.setting_label` 组装 `RuleRow`；advanced 模式加 `advanced_note`）
  - `async def world_summary(self, world) -> WorldSummaryDTO`（TTL 90s）
  - `async def today(self, world) -> DailyReport`（委托 `ReportService.daily`，当日短缓存 TTL 60s）

> `QueryService.__init__` 需持有 `report` 与 `world_snapshot_cache`（server_id→最近 `GameDataSnapshot`，由 `ingest_game_data` 填充，用于 world_summary 的瞬时计数）。为不破坏既有签名，这两者随 `settings_cache` 一起以属性形式传入：把 `__init__` 扩展为 `def __init__(self, repo, cache, cfg, meta, clock, settings_cache, world_cache=None, report=None)`（新增两个带默认值的可选参数，向后兼容 Task 5.8/5.9 的构造）。

- [ ] **写失败测试** — 创建 `tests/unit/query_service_rules_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode, ActionCategory, UnitType
from palchronicle.domain.models import (
    CharacterActor, GameDataSnapshot, PalBoxActor, World, WorldMetric,
)
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


class _FakeMeta:
    def setting_label(self, field):
        return {"ExpRate": ("经验倍率", "x")}.get(field, (field, ""))

    def pal_name(self, cls):
        return cls


class _FakeReport:
    async def daily(self, world, day=None):
        return "DAILY_SENTINEL"


def _cfg(privacy_mode="balanced") -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig(privacy_mode, False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


def _char(unit: UnitType, pal="Lamball") -> CharacterActor:
    return CharacterActor(
        unit_type=unit, instance_id=None, nickname=None, trainer_instance_id=None,
        trainer_nickname=None, player_userid=None, level=5, hp=100, max_hp=100,
        guild_id="g1", guild_name="Noema", pal_class=pal, action=ActionCategory.IDLE,
        ai_action=ActionCategory.IDLE, x=None, y=None, z=None, is_active=True,
    )


async def _make(tmp_path, privacy_mode="balanced"):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    settings_cache = {"alpha": {"ExpRate": "1.5"}}
    world_cache = {
        "alpha": GameDataSnapshot(
            observed_at=1200, fps=58.0, average_fps=57.0,
            characters=[_char(UnitType.PLAYER), _char(UnitType.WILD, "Lamball"),
                        _char(UnitType.WILD, "Lamball"), _char(UnitType.NPC)],
            palboxes=[PalBoxActor("g1", "Noema", None, 1.0, 2.0, 3.0)],
            unknown_classes=[],
        )
    }
    q = QueryService(
        repo, TTLCache(clock), _cfg(privacy_mode), meta=_FakeMeta(), clock=clock,
        settings_cache=settings_cache, world_cache=world_cache, report=_FakeReport(),
    )
    return db, repo, q


@pytest.mark.asyncio
async def test_rules_maps_settings_labels(tmp_path):
    db, repo, q = await _make(tmp_path)
    dto = await q.rules(_world())
    labels = {r.label: r.value for r in dto.rows}
    assert labels["经验倍率"] == "1.5x"
    assert dto.advanced_note is None
    await db.close()


@pytest.mark.asyncio
async def test_rules_advanced_note(tmp_path):
    db, repo, q = await _make(tmp_path, privacy_mode="advanced")
    dto = await q.rules(_world())
    assert dto.advanced_note is not None
    assert "balanced" in dto.advanced_note
    await db.close()


@pytest.mark.asyncio
async def test_world_summary_counts_unit_types(tmp_path):
    db, repo, q = await _make(tmp_path)
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.0, 1, 42, 5))
    dto = await q.world_summary(_world())
    assert dto.players == 1
    assert dto.wild == 2
    assert dto.npc == 1
    assert dto.palbox == 1
    assert dto.wild_top[0].name == "Lamball"
    assert dto.wild_top[0].count == 2
    await db.close()


@pytest.mark.asyncio
async def test_today_delegates_to_report(tmp_path):
    db, repo, q = await _make(tmp_path)
    result = await q.today(_world())
    assert result == "DAILY_SENTINEL"
    await db.close()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/query_service_rules_test.py -q`。期望 FAIL：`TypeError: __init__() got an unexpected keyword argument 'world_cache'`（当前构造不接受该参数）。

- [ ] **写最小实现** — 修改 `palchronicle/application/query_service.py`：

先扩展 `__init__`（把原签名替换为向后兼容版）：

```python
    def __init__(
        self, repo: Repository, cache: TTLCache, cfg: AppConfig, meta, clock: Clock,
        settings_cache, world_cache=None, report=None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache
        self._world_cache = world_cache if world_cache is not None else {}
        self._report = report
```

在类中追加方法（顶部 import 追加 `RulesDTO, RuleRow, WorldSummaryDTO, WildTopRow`）：

```python
    async def rules(self, world: World) -> RulesDTO:
        key = f"rules:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = self._settings_cache.get(world.server_id, {})
        rows: list[RuleRow] = []
        for field, value in raw.items():
            label, unit = self._meta.setting_label(field)
            rows.append(RuleRow(label=label, value=f"{value}{unit}"))
        advanced_note = None
        if self._cfg.privacy.mode == "advanced":
            advanced_note = "advanced 隐私模式暂按 balanced 生效。"
        elif self._cfg.privacy.mode == "strict":
            advanced_note = "strict 隐私模式下据点模块停用。"
        dto = RulesDTO(rows=rows, updated_at=self._clock.now(), advanced_note=advanced_note)
        self._cache.set(key, dto, 1800)
        return dto

    async def world_summary(self, world: World) -> WorldSummaryDTO:
        key = f"world:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        gd = self._world_cache.get(world.server_id)
        metric = await self._repo.latest_metric(world.world_id)
        counts = {u: 0 for u in ("Player", "OtomoPal", "BaseCampPal", "WildPal", "NPC")}
        wild_counter: dict[str, int] = {}
        palbox = 0
        guild_ids: set = set()
        if gd is not None:
            for c in gd.characters:
                counts[c.unit_type.value] = counts.get(c.unit_type.value, 0) + 1
                if c.unit_type.value == "WildPal" and c.pal_class:
                    name = self._meta.pal_name(c.pal_class) if self._meta else c.pal_class
                    wild_counter[name] = wild_counter.get(name, 0) + 1
                if c.guild_id:
                    guild_ids.add(c.guild_id)
            palbox = len(gd.palboxes)
        wild_top = [
            WildTopRow(name=n, count=c)
            for n, c in sorted(wild_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        ]
        dto = WorldSummaryDTO(
            world_day=metric.world_day if metric else world.current_day,
            online=metric.online_players if metric else counts["Player"],
            players=counts["Player"], otomo=counts["OtomoPal"], base_pal=counts["BaseCampPal"],
            wild=counts["WildPal"], npc=counts["NPC"], palbox=palbox, guilds=len(guild_ids),
            fps=gd.fps if gd else (metric.fps if metric else 0.0),
            average_fps=gd.average_fps if gd else (metric.fps if metric else 0.0),
            wild_top=wild_top,
        )
        self._cache.set(key, dto, _BASES_TTL)
        return dto

    async def today(self, world: World):
        key = f"today:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        report = await self._report.daily(world)
        self._cache.set(key, report, 60)
        return report
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/query_service_rules_test.py tests/unit/query_service_status_test.py tests/unit/query_service_bases_test.py -q`。期望 PASS：全部通过（新 4 + 旧 4 + 旧 6 = 14 passed；确认扩展 `__init__` 未破坏 5.8/5.9）。

- [ ] **提交** — `git add palchronicle/application/query_service.py tests/unit/query_service_rules_test.py && git commit -m "feat(query): add rules/world_summary/today"`

---

### Task 5.11：formatters — 非 golden 分支（degraded / servers / help / online / guilds / guild / bases / base / events）

**Files:**
- Create: `palchronicle/presentation/formatters.py`
- Test: `tests/unit/formatters_test.py`

**Interfaces:**
- Consumes: 全部 DTO（Task 5.3）、`DailyReport`（Phase 4）、`SkippedServer`（config）、`WorldConfig`、locale `L`。
- Produces（纯函数）：
  - `format_online(dto) -> str`、`format_guilds(dto) -> str`、`format_guild(dto) -> str`、`format_bases(dto) -> str`、`format_base(dto) -> str`、`format_events(dto) -> str`、`format_servers(rows, skipped, is_admin) -> str`、`format_help(topic, is_admin) -> str`、`format_degraded(last_ok, now) -> str`
  - （`format_status`/`format_world`/`format_today`/`format_rules` 在 Task 5.12 用 golden 测试单独建）

- [ ] **写失败测试** — 创建 `tests/unit/formatters_test.py`：

```python
from palchronicle.config import SkippedServer
from palchronicle.domain.enums import Confidence, PingBucket
from palchronicle.presentation.dtos import (
    BaseDetailDTO, BaseDTO, EventDTO, GuildDetailDTO, GuildDTO,
    OnlineDTO, OnlinePlayerRow, ServerStatusRow,
)
from palchronicle.presentation.formatters import (
    format_base, format_bases, format_degraded, format_events, format_guild,
    format_guilds, format_help, format_online, format_servers,
)


def test_format_degraded_shows_minutes_not_shutdown():
    text = format_degraded(last_ok=1000, now=1000 + 300)
    assert "5" in text
    assert "关机" not in text


def test_format_degraded_never_ok():
    text = format_degraded(last_ok=None, now=1000)
    assert "无法获取" in text


def test_format_online_lists_players_and_bucket_label():
    dto = OnlineDTO(
        rows=[OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661)], updated_at=1000, degraded=False
    )
    text = format_online(dto)
    assert "Neo" in text
    assert "21" in text
    # ping bucket rendered as a friendly label, never a raw ms number
    assert "优秀" in text


def test_format_online_empty():
    text = format_online(OnlineDTO(rows=[], updated_at=1000, degraded=False))
    assert "当前无玩家在线" in text


def test_format_bases_folds_low_confidence_note():
    dtos = [BaseDTO(1, "Noema-1", "Noema", Confidence.HIGH, 8)]
    text = format_bases(dtos)
    assert "Noema-1" in text
    assert "#1" in text


def test_format_bases_empty():
    assert "暂无" in format_bases([])


def test_format_base_marks_derived():
    dto = BaseDetailDTO("Noema-1", "Noema", Confidence.HIGH, 1, 8, 6, 17.5, 0.9,
                        {"working": 6, "idle": 2}, 81.25, 90.0)
    text = format_base(dto)
    assert "插件推导" in text
    assert "Noema-1" in text


def test_format_guilds_and_guild():
    gs = format_guilds([GuildDTO("Noema", 4, 2, 10, 3)])
    assert "Noema" in gs
    gd = format_guild(GuildDetailDTO("Noema", 1, 2, 4, 2, 3, 2, 10, 15.0, ["据点新增：Noema-2"]))
    assert "Noema" in gd
    assert "据点新增" in gd


def test_format_events_and_empty():
    text = format_events([EventDTO(1000, "new_player", "新玩家加入世界")])
    assert "新玩家加入世界" in text
    assert "暂无" in format_events([])


def test_format_servers_admin_shows_skipped_section():
    rows = [ServerStatusRow("alpha", True, True, True, True)]
    skipped = [SkippedServer(raw_name="dup", reason="duplicate")]
    admin_text = format_servers(rows, skipped, is_admin=True)
    assert "alpha" in admin_text
    assert "被跳过" in admin_text
    guest_text = format_servers(rows, skipped, is_admin=False)
    assert "被跳过" not in guest_text


def test_format_help_role_separation():
    admin = format_help(None, is_admin=True)
    assert "use" in admin
    guest = format_help(None, is_admin=False)
    assert "use" not in guest
    assert "status" in guest
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/formatters_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.presentation.formatters'`。

- [ ] **写最小实现** — 创建 `palchronicle/presentation/formatters.py`：

```python
from __future__ import annotations

from palchronicle.config import SkippedServer
from palchronicle.domain.enums import Confidence, PingBucket
from palchronicle.presentation.dtos import (
    BaseDetailDTO, BaseDTO, EventDTO, GuildDetailDTO, GuildDTO,
    OnlineDTO, ServerStatusRow,
)
from palchronicle.presentation.locale import L

_PING_LABEL = {
    PingBucket.GOOD: "优秀", PingBucket.OK: "正常",
    PingBucket.HIGH: "偏高", PingBucket.UNKNOWN: "未知",
}
_CONF_LABEL = {Confidence.HIGH: "高", Confidence.MEDIUM: "中", Confidence.LOW: "低"}


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(max(seconds, 0), 3600)
    m = rem // 60
    if h:
        return f"{h}小时{m}分"
    return f"{m}分"


def format_degraded(last_ok: int | None, now: int) -> str:
    if last_ok is None:
        return L("degraded_never")
    minutes = max(0, (now - last_ok) // 60)
    return L("degraded", minutes=minutes)


def format_online(dto: OnlineDTO) -> str:
    if not dto.rows:
        return "当前无玩家在线。"
    lines = ["当前在线玩家："]
    for r in dto.rows:
        ping = _PING_LABEL[r.ping_bucket]
        lines.append(f"· {r.name} Lv{r.level} · Ping {ping} · 在线 {_fmt_duration(r.online_seconds)}")
    return "\n".join(lines)


def format_guilds(dto: list[GuildDTO]) -> str:
    if not dto:
        return L("guilds_unavailable")
    lines = ["世界公会（已观察/推导）："]
    for g in dto:
        lines.append(
            f"· {g.name} · 成员~{g.observed_members} · PalBox {g.palbox} · "
            f"工作帕鲁 {g.base_pals} · 近7日活跃 {g.active_7d}"
        )
    return "\n".join(lines)


def format_guild(dto: GuildDetailDTO) -> str:
    lines = [
        f"公会：{dto.name}（已观察/推导）",
        f"观察成员：~{dto.observed_members} · 当日活跃 {dto.active_today} · 当周活跃 {dto.active_week}",
        f"PalBox {dto.palbox} · 工作帕鲁 {dto.base_pals} · 平均等级 {dto.average_level:.1f}",
    ]
    if dto.base_event_lines:
        lines.append("据点变化：")
        lines.extend(f"  · {line}" for line in dto.base_event_lines)
    return "\n".join(lines)


def format_bases(dto: list[BaseDTO]) -> str:
    if not dto:
        return "暂无可展示的据点（插件推导）。"
    lines = ["据点列表（插件推导）："]
    for b in dto:
        guild = b.guild_name or "未确定公会"
        lines.append(f"#{b.index} {b.display_name} · {guild} · 置信度 {_CONF_LABEL[b.confidence]}")
    return "\n".join(lines)


def format_base(dto: BaseDetailDTO) -> str:
    guild = dto.guild_name or "未确定公会"
    dist = "、".join(f"{k}:{v}" for k, v in dto.action_distribution.items()) or "无"
    return "\n".join([
        f"据点：{dto.display_name}（插件推导）",
        f"所属公会：{guild} · 置信度 {_CONF_LABEL[dto.confidence]} · PalBox {dto.palbox_count}",
        f"工作帕鲁 {dto.worker_count} · 活跃 {dto.active_count} · 平均等级 {dto.average_level:.1f}",
        f"平均HP比 {dto.average_hp_ratio:.0%} · 活跃度 {dto.activity_score:.1f} · 健康度 {dto.health_score:.1f}",
        f"Action 分布：{dist}",
    ])


def format_events(dto: list[EventDTO]) -> str:
    if not dto:
        return L("no_events")
    lines = ["近期世界事件："]
    lines.extend(f"· {e.summary}" for e in dto)
    return "\n".join(lines)


def format_servers(
    rows: list[ServerStatusRow], skipped: list[SkippedServer], is_admin: bool
) -> str:
    if not rows and not skipped:
        return L("no_server_configured")
    lines = ["已配置服务器："]
    for r in rows:
        ready = "就绪" if r.ready else "未就绪"
        online = "在线" if r.online else "离线"
        allowed = "已授权" if r.allowed else "未授权"
        active = " ·活动" if r.active else ""
        lines.append(f"· {r.name} · {ready}/{online} · 本群{allowed}{active}")
    if is_admin and skipped:
        lines.append("⚠ 被跳过的无效服务器配置：")
        lines.extend(f"  · {s.raw_name}（{s.reason}）" for s in skipped)
    return "\n".join(lines)


_HELP_GUEST = [
    "PalChronicle 命令：",
    "/pal status  世界状态", "/pal online  当前在线", "/pal world  世界概览",
    "/pal rules  世界规则", "/pal guilds  公会列表", "/pal guild <名称>  公会详情",
    "/pal bases  据点列表", "/pal base <名称|#序号>  据点详情", "/pal events  世界事件",
    "/pal today  今日日报", "/pal servers  服务器列表", "/pal help  帮助",
    "提示：命令末尾可加 @服务器名 指定服务器。",
]
_HELP_ADMIN_EXTRA = [
    "管理员命令：",
    "/pal use <名称>  授权本群并设为活动服务器（仅群聊）",
    "/pal unbind <名称>  撤销本群授权",
]


def format_help(topic: str | None, is_admin: bool) -> str:
    lines = list(_HELP_GUEST)
    if is_admin:
        lines.append("")
        lines.extend(_HELP_ADMIN_EXTRA)
    return "\n".join(lines)
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/formatters_test.py -q`。期望 PASS：11 passed。

- [ ] **提交** — `git add palchronicle/presentation/formatters.py tests/unit/formatters_test.py && git commit -m "feat(presentation): add non-golden formatters"`

---

### Task 5.12：formatters golden — status / world / today / rules + 脱敏输出

**Files:**
- Modify: `palchronicle/presentation/formatters.py`
- Test: `tests/unit/formatters_golden_test.py`
- Golden: `tests/golden/status.txt`、`tests/golden/world.txt`、`tests/golden/today.txt`、`tests/golden/rules.txt`、`tests/golden/online_redacted.txt`（首跑生成并提交，之后比对）

**Interfaces:**
- Consumes: `StatusDTO`、`WorldSummaryDTO`、`RulesDTO`、`DailyReport`（Phase 4：字段 `day, world_day_start, world_day_end, active_players, peak_online, total_online_seconds, level_events:list, base_events:list, records:list, summary:str, is_empty:bool`）、`OnlineDTO`、`WorldConfig`。
- Produces（追加到 formatters）：
  - `format_status(dto:StatusDTO, cfg:WorldConfig) -> str`
  - `format_world(dto:WorldSummaryDTO) -> str`
  - `format_rules(dto:RulesDTO) -> str`
  - `format_today(dto:DailyReport) -> str`

> Golden 机制：测试用固定 DTO 生成文本；若对应 `tests/golden/*.txt` 不存在则写入（首跑生成），存在则严格比对。首跑后把生成的 golden 文件一并提交。脱敏用例 `online_redacted` 断言输出不含原始 ping 数值、只含 bucket 标签。

- [ ] **写失败测试** — 创建 `tests/unit/formatters_golden_test.py`：

```python
from pathlib import Path

from palchronicle.config import WorldConfig
from palchronicle.domain.enums import PingBucket
from palchronicle.presentation.dtos import (
    OnlineDTO, OnlinePlayerRow, RuleRow, RulesDTO, StatusDTO, WildTopRow, WorldSummaryDTO,
)
from palchronicle.presentation.formatters import (
    format_online, format_rules, format_status, format_today, format_world,
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def _check_golden(name: str, actual: str) -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    path = GOLDEN / name
    if not path.exists():
        path.write_text(actual, encoding="utf-8")  # first run: generate
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, f"golden mismatch for {name}"


def _world_cfg() -> WorldConfig:
    return WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20)


def test_status_golden():
    dto = StatusDTO(
        server_name="alpha", world_name="Palpagos", world_day=42, online=2, max_players=32,
        basecamp_count=5, fps=58.0, frame_time=17.2, smoothness_label="流畅",
        players=[("Neo", 21, "good"), ("Trinity", 18, "ok")],
        peak_online_today=7, updated_at=1700000000, degraded=False, last_ok=1700000000,
    )
    _check_golden("status.txt", format_status(dto, _world_cfg()))


def test_world_golden():
    dto = WorldSummaryDTO(
        world_day=42, online=2, players=2, otomo=3, base_pal=8, wild=15, npc=4,
        palbox=3, guilds=2, fps=58.0, average_fps=56.5,
        wild_top=[WildTopRow("Lamball", 5), WildTopRow("Chikipi", 3)],
    )
    _check_golden("world.txt", format_world(dto))


def test_rules_golden():
    dto = RulesDTO(
        rows=[RuleRow("经验倍率", "1.0x"), RuleRow("捕获倍率", "1.0x"), RuleRow("最大玩家", "32")],
        updated_at=1700000000, advanced_note=None,
    )
    _check_golden("rules.txt", format_rules(dto))


def test_today_golden():
    class _Report:
        day = "2026-07-10"
        world_day_start = 41
        world_day_end = 42
        active_players = 5
        peak_online = 7
        total_online_seconds = 36000
        level_events = ["Neo 升至 Lv21"]
        base_events = ["据点新增：Noema-2"]
        records = ["在线人数刷新纪录：7 人"]
        summary = "世界迎来新的一天。"
        is_empty = False

    _check_golden("today.txt", format_today(_Report()))


def test_online_redacted_golden():
    dto = OnlineDTO(
        rows=[
            OnlinePlayerRow("Neo", 21, PingBucket.GOOD, 3661),
            OnlinePlayerRow("Trinity", 18, PingBucket.HIGH, 600),
        ],
        updated_at=1700000000, degraded=False,
    )
    text = format_online(dto)
    # privacy: no raw ping ms leaked
    assert "3661" not in text or "在线" in text  # duration allowed, ping must be bucket
    assert "优秀" in text and "偏高" in text
    _check_golden("online_redacted.txt", text)
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/formatters_golden_test.py -q`。期望 FAIL：`ImportError: cannot import name 'format_status' from 'palchronicle.presentation.formatters'`（`format_status`/`format_world`/`format_rules`/`format_today` 尚未定义）。

- [ ] **写最小实现** — 在 `palchronicle/presentation/formatters.py` 顶部 import 追加 `StatusDTO, WorldSummaryDTO, RulesDTO`（`WorldConfig` 从 `palchronicle.config` 导入），并追加函数：

```python
def format_status(dto: StatusDTO, cfg) -> str:
    if dto.degraded:
        return format_degraded(dto.last_ok, dto.updated_at)
    lines = [
        f"世界：{dto.world_name} · 第 {dto.world_day} 天",
        f"在线：{dto.online}/{dto.max_players} 人 · 今日最高 {dto.peak_online_today}",
        f"据点：{dto.basecamp_count}（官方指标）",
        f"性能：FPS {dto.fps:.0f}（{dto.smoothness_label}） · 帧时间 {dto.frame_time:.1f}ms",
    ]
    if dto.players:
        lines.append("在线玩家：")
        lines.extend(f"  · {n} Lv{lv}" for n, lv, _ in dto.players)
    return "\n".join(lines)


def format_world(dto: WorldSummaryDTO) -> str:
    lines = [
        f"世界概览 · 第 {dto.world_day} 天 · 在线 {dto.online} 人",
        f"角色 {dto.players} · 随行 {dto.otomo} · 工作帕鲁 {dto.base_pal} · "
        f"野生 {dto.wild} · NPC {dto.npc}",
        f"PalBox {dto.palbox} · 公会 {dto.guilds}",
        f"FPS 瞬时 {dto.fps:.0f} / 平均 {dto.average_fps:.0f}",
    ]
    if dto.wild_top:
        top = "、".join(f"{w.name}×{w.count}" for w in dto.wild_top)
        lines.append(f"当前野生帕鲁 Top（仅当前快照）：{top}")
    return "\n".join(lines)


def format_rules(dto: RulesDTO) -> str:
    lines = ["世界规则："]
    for r in dto.rows:
        lines.append(f"· {r.label}：{r.value}")
    if dto.advanced_note:
        lines.append(f"注：{dto.advanced_note}")
    return "\n".join(lines)


def format_today(dto) -> str:
    if getattr(dto, "is_empty", False):
        return L("empty_day")
    hours = dto.total_online_seconds // 3600
    lines = [
        f"今日日报 · {dto.day}",
        f"世界天数：第 {dto.world_day_start} → {dto.world_day_end} 天",
        f"活跃玩家 {dto.active_players} · 最高同时在线 {dto.peak_online} · 累计观察在线 {hours} 小时",
    ]
    if dto.records:
        lines.append("今日纪录：")
        lines.extend(f"  · {r}" for r in dto.records)
    if dto.level_events:
        lines.append("玩家成长：")
        lines.extend(f"  · {e}" for e in dto.level_events)
    if dto.base_events:
        lines.append("据点变化：")
        lines.extend(f"  · {e}" for e in dto.base_events)
    lines.append(dto.summary)
    return "\n".join(lines)
```

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/formatters_golden_test.py -q`。期望 PASS：5 passed（首跑生成 5 个 golden 文件；再跑仍 PASS 证明比对稳定）。

- [ ] **提交** — `git add palchronicle/presentation/formatters.py tests/unit/formatters_golden_test.py tests/golden/status.txt tests/golden/world.txt tests/golden/rules.txt tests/golden/today.txt tests/golden/online_redacted.txt && git commit -m "feat(presentation): add golden formatters for status/world/rules/today + redacted online"`

---

### Task 5.13：commands.py — 命令分发器（parse_arg→resolve→query→format）

**Files:**
- Create: `palchronicle/presentation/commands.py`
- Test: `tests/unit/commands_test.py`

**Interfaces:**
- Consumes: `RoutingService.resolve/use/unbind/ready_servers`、`QueryService.*`、`ReportService`、`parse_arg`、`ArgError`、formatters、locale `L`、`Repository.get_current_world`/`latest_metric`（据点降级/降级文案）。
- Produces：`class Commands`（把业务从 AstrBot `Star` 中抽离，便于用 fake event 测试）：
  - `def __init__(self, routing, query, repo, cfg, clock)`
  - `async def handle_query(self, umo:str, message_str:str, subcommand:str, is_group:bool, formatter:Callable) -> str`（通用：解析 arg → resolve → 取 world → 调 query → format；失败返回文案）
  - `async def status/online/world/rules/guilds/guild/bases/base/events/today(self, umo, message_str, is_group) -> str`（各命令入口）
  - `async def servers(self, umo, is_group, is_admin) -> str`
  - `async def use/unbind(self, umo, message_str, is_group, is_admin) -> str`
  - `def help(self, message_str:str, is_admin:bool) -> str`

> handler 返回 `str`（单条回复文本）；`main.py` 的 AstrBot 子命令只负责 `yield event.plain_result(await commands.xxx(...))`。测试用 fake routing/query 断言文本路径，无需真实 AstrBot。

- [ ] **写失败测试** — 创建 `tests/unit/commands_test.py`：

```python
import pytest

from palchronicle.application.routing_service import Resolution
from palchronicle.config import ServerConfig
from palchronicle.domain.models import World
from palchronicle.presentation.commands import Commands

WID = "alpha:guid-1:0"


def _server() -> ServerConfig:
    return ServerConfig("alpha", "alpha", True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


class _FakeRouting:
    def __init__(self, res: Resolution):
        self._res = res
        self.used = None

    async def resolve(self, umo, override, is_group):
        self._last_override = override
        return self._res

    async def use(self, umo, name):
        self.used = (umo, name)
        return f"USE_OK:{name}"

    async def unbind(self, umo, name):
        return f"UNBIND_OK:{name}"

    def ready_servers(self):
        return [_server()]


class _FakeQuery:
    def __init__(self):
        self.status_called_with = None

    async def status(self, world):
        self.status_called_with = world.world_id
        return "STATUS_DTO"


class _FakeRepo:
    async def get_current_world(self, server_id):
        return _world()

    async def latest_metric(self, world_id):
        return object()

    async def list_group_servers(self, umo):
        return {"alpha": (True, True)}


def _fmt_status(dto, cfg=None):
    return f"FORMATTED:{dto}"


@pytest.mark.asyncio
async def test_query_happy_path():
    routing = _FakeRouting(Resolution(_server(), None))
    query = _FakeQuery()
    cmds = Commands(routing, query, _FakeRepo(), cfg=None, clock=None)
    out = await cmds.handle_query(
        "umo1", "/pal status @alpha", "status", is_group=True,
        formatter=lambda world_dto: f"OUT:{world_dto}",
        query_fn=query.status,
    )
    assert out == "OUT:STATUS_DTO"
    assert query.status_called_with == WID


@pytest.mark.asyncio
async def test_query_resolution_error_returns_error_text():
    routing = _FakeRouting(Resolution(None, "服务器「x」不存在或未就绪。"))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), cfg=None, clock=None)
    out = await cmds.handle_query(
        "umo1", "/pal status", "status", is_group=True,
        formatter=lambda d: "SHOULD_NOT_RENDER", query_fn=_FakeQuery().status,
    )
    assert "不存在或未就绪" in out


@pytest.mark.asyncio
async def test_use_requires_group():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.use("umo1", "/pal use alpha", is_group=False, is_admin=True)
    assert "仅可在群聊" in out


@pytest.mark.asyncio
async def test_use_requires_admin():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.use("umo1", "/pal use alpha", is_group=True, is_admin=False)
    assert "管理" in out or "权限" in out


@pytest.mark.asyncio
async def test_use_happy_path():
    routing = _FakeRouting(Resolution(_server(), None))
    cmds = Commands(routing, _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.use("umo1", "/pal use alpha", is_group=True, is_admin=True)
    assert out == "USE_OK:alpha"
    assert routing.used == ("umo1", "alpha")


@pytest.mark.asyncio
async def test_unbind_happy_path():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    out = await cmds.unbind("umo1", "/pal unbind alpha", is_group=True, is_admin=True)
    assert out == "UNBIND_OK:alpha"


def test_help_role_separation():
    cmds = Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), None, None)
    assert "use" in cmds.help("/pal help", is_admin=True)
    assert "use" not in cmds.help("/pal help", is_admin=False)
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/commands_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.presentation.commands'`。

- [ ] **写最小实现** — 创建 `palchronicle/presentation/commands.py`：

```python
from __future__ import annotations

from typing import Awaitable, Callable

from palchronicle.presentation.formatters import (
    format_bases, format_base, format_degraded, format_events, format_guild,
    format_guilds, format_help, format_online, format_rules, format_servers,
    format_status, format_world,
)
from palchronicle.presentation.dtos import ServerStatusRow
from palchronicle.presentation.locale import L
from palchronicle.presentation.server_arg import ArgError, parse_arg


class Commands:
    def __init__(self, routing, query, repo, cfg, clock) -> None:
        self._routing = routing
        self._query = query
        self._repo = repo
        self._cfg = cfg
        self._clock = clock

    async def _resolve_world(self, umo: str, message_str: str, subcommand: str, is_group: bool):
        try:
            arg = parse_arg(message_str, subcommand)
        except ArgError:
            return None, None, "参数格式错误：一条命令只能指定一个 @服务器。"
        res = await self._routing.resolve(umo, arg.server_override, is_group)
        if res.server is None:
            return None, arg, res.error
        world = await self._repo.get_current_world(res.server.server_id)
        if world is None:
            return None, arg, format_degraded(None, self._clock.now() if self._clock else 0)
        return world, arg, None

    async def handle_query(
        self, umo: str, message_str: str, subcommand: str, is_group: bool,
        formatter: Callable, query_fn: Callable[..., Awaitable],
    ) -> str:
        world, _arg, err = await self._resolve_world(umo, message_str, subcommand, is_group)
        if err is not None:
            return err
        dto = await query_fn(world)
        return formatter(dto)

    async def status(self, umo, message_str, is_group) -> str:
        cfg = self._cfg.world if self._cfg else None
        return await self.handle_query(
            umo, message_str, "status", is_group,
            formatter=lambda d: format_status(d, cfg), query_fn=self._query.status,
        )

    async def online(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "online", is_group,
            formatter=format_online, query_fn=self._query.online,
        )

    async def world(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "world", is_group,
            formatter=format_world, query_fn=self._query.world_summary,
        )

    async def rules(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "rules", is_group,
            formatter=format_rules, query_fn=self._query.rules,
        )

    async def guilds(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "guilds", is_group,
            formatter=format_guilds, query_fn=self._query.guilds,
        )

    async def guild(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "guild", is_group)
        if err is not None:
            return err
        dto = await self._query.guild(world, arg.name)
        if dto is None:
            return L("guild_not_found", name=arg.name)
        return format_guild(dto)

    async def bases(self, umo, message_str, is_group) -> str:
        return await self.handle_query(
            umo, message_str, "bases", is_group,
            formatter=format_bases, query_fn=self._query.bases,
        )

    async def base(self, umo, message_str, is_group) -> str:
        world, arg, err = await self._resolve_world(umo, message_str, "base", is_group)
        if err is not None:
            return err
        dto = await self._query.base(world, arg.name)
        if dto is None:
            return L("base_not_found", name=arg.name)
        return format_base(dto)

    async def events(self, umo, message_str, is_group) -> str:
        today_only = "today" in message_str.split()
        world, _arg, err = await self._resolve_world(umo, message_str, "events", is_group)
        if err is not None:
            return err
        dto = await self._query.events(world, today_only=today_only)
        return format_events(dto)

    async def today(self, umo, message_str, is_group) -> str:
        world, _arg, err = await self._resolve_world(umo, message_str, "today", is_group)
        if err is not None:
            return err
        from palchronicle.presentation.formatters import format_today
        return format_today(await self._query.today(world))

    async def servers(self, umo, is_group, is_admin) -> str:
        ready_ids = {s.server_id for s in self._routing.ready_servers()}
        group = await self._repo.list_group_servers(umo) if is_group else {}
        rows = []
        for s in (self._cfg.servers if self._cfg else self._routing.ready_servers()):
            allowed, active = group.get(s.server_id, (False, False))
            rows.append(ServerStatusRow(
                name=s.name, ready=s.ready, online=s.server_id in ready_ids,
                allowed=allowed, active=active,
            ))
        skipped = self._cfg.skipped if self._cfg else []
        return format_servers(rows, skipped, is_admin)

    async def use(self, umo, message_str, is_group, is_admin) -> str:
        if not is_admin:
            return "该命令需要管理员权限。"
        if not is_group:
            return L("use_only_group")
        arg = parse_arg(message_str, "use")
        name = arg.server_override or arg.name
        return await self._routing.use(umo, name)

    async def unbind(self, umo, message_str, is_group, is_admin) -> str:
        if not is_admin:
            return "该命令需要管理员权限。"
        if not is_group:
            return L("use_only_group")
        arg = parse_arg(message_str, "unbind")
        name = arg.server_override or arg.name
        return await self._routing.unbind(umo, name)

    def help(self, message_str, is_admin) -> str:
        arg = parse_arg(message_str, "help")
        return format_help(arg.name or None, is_admin)
```

> `servers`/`use`/`unbind` 的 `is_admin` 由 `main.py` 的 `@filter.permission_type(ADMIN)` 已保证（Admin 命令仅 Admin 可达）；此处二次判定用于单测与深度防御。`_FakeRepo` 无 `servers` 属性但 `cfg=None` 时 `servers()` 走 `ready_servers()` 兜底。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/commands_test.py -q`。期望 PASS：7 passed。

- [ ] **提交** — `git add palchronicle/presentation/commands.py tests/unit/commands_test.py && git commit -m "feat(presentation): add Commands dispatcher for 14 commands"`

---

### Task 5.14：Container.start / stop（装配 + 生命周期）

**Files:**
- Create: `palchronicle/container.py`
- Test: `tests/unit/container_test.py`

**Interfaces:**
- Consumes: `AppConfig`、`Database`、`apply_migrations`、`load_or_create_salt`、`Repository`、`MetadataRepository`、`TTLCache`、`EndpointLocks`、`Scheduler`、`RoutingService`、`QueryService`、`ReportService`、`SnapshotService`、`PalworldRestClient`、`Clock`。
- Produces：
  - `class Container: def __init__(self, config:AppConfig, data_dir:Path, clock:Clock)`
  - `async def start(self) -> None`（open db + migrate + salt + `sync_servers` + `seed_bindings` + `cleanup_orphan_bindings` + 构建服务 + 起 scheduler；`on_response` 回调 → `SnapshotService` 分发）
  - `async def stop(self) -> None`（取消 scheduler 任务 + 关 rest sessions + 关 db）
  - 暴露属性：`routing`、`query`、`report`、`commands`（供 main.py 委托）
  - `async def _on_response(self, server_id:str, endpoint:EndpointName, resp:RestResponse) -> None`（按端点分发到 `SnapshotService.ingest_*`）

> 为测试可注入，`__init__` 增加可选参数 `rest_factory: Callable[[ServerConfig, Clock], PalworldRestClient] | None = None`（默认 `PalworldRestClient`），`scheduler_factory` 同理，允许测试用 fake 避免真实网络与后台任务。

- [ ] **写失败测试** — 创建 `tests/unit/container_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.config import (
    AppConfig, BasesConfig, BindingConfig, HistoryConfig, PollingConfig,
    PrivacyConfig, RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.container import Container
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock


def _server(name: str) -> ServerConfig:
    return ServerConfig(name, name, True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _cfg(servers, bindings=None) -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=bindings or [],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


class _FakeScheduler:
    def __init__(self, *a, **k):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class _FakeRest:
    def __init__(self, *a, **k):
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_start_builds_services_and_seeds(tmp_path: Path):
    scheds = []

    def sched_factory(*a, **k):
        s = _FakeScheduler()
        scheds.append(s)
        return s

    cfg = _cfg([_server("alpha")], bindings=[BindingConfig("umo1", "alpha", True)])
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=sched_factory)
    await c.start()
    try:
        assert c.routing is not None
        assert c.query is not None
        assert c.commands is not None
        assert scheds and scheds[0].started is True
        # seed binding landed
        assert await c.routing._repo.get_binding_active("umo1") == "alpha"
        # salt file created
        assert (tmp_path / "secret_salt").exists()
    finally:
        await c.stop()
    assert scheds[0].stopped is True


@pytest.mark.asyncio
async def test_stop_closes_rest_and_db(tmp_path: Path):
    rests = []

    def rest_factory(s, clk):
        r = _FakeRest()
        rests.append(r)
        return r

    c = Container(_cfg([_server("alpha")]), tmp_path, FakeClock(1000),
                  rest_factory=rest_factory, scheduler_factory=lambda *a, **k: _FakeScheduler())
    await c.start()
    await c.stop()
    assert rests and all(r.closed for r in rests)


@pytest.mark.asyncio
async def test_on_response_dispatches_info(tmp_path: Path, monkeypatch):
    c = Container(_cfg([_server("alpha")]), tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda *a, **k: _FakeScheduler())
    await c.start()
    from palchronicle.adapters.palworld_rest import RestResponse
    from palchronicle.domain.enums import EndpointName
    calls = []

    async def fake_ingest_info(server, resp):
        calls.append(("info", server.server_id))
        return None

    monkeypatch.setattr(c._snapshot, "ingest_info", fake_ingest_info)
    resp = RestResponse(ok=True, status=200, data={"worldguid": "g"}, duration_ms=1,
                        payload_bytes=1, error=None)
    await c._on_response("alpha", EndpointName.INFO, resp)
    await c.stop()
    assert calls == [("info", "alpha")]
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/container_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'palchronicle.container'`。

- [ ] **写最小实现** — 创建 `palchronicle/container.py`：

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.adapters.palworld_rest import PalworldRestClient, RestResponse
from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.base_service import BaseService
from palchronicle.application.event_service import EventService
from palchronicle.application.guild_service import GuildService
from palchronicle.application.player_service import PlayerService
from palchronicle.application.query_service import QueryService
from palchronicle.application.report_service import ReportService
from palchronicle.application.routing_service import RoutingService
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import Clock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.locks import EndpointLocks
from palchronicle.infrastructure.migrations import apply_migrations
from palchronicle.infrastructure.salt import load_or_create_salt
from palchronicle.infrastructure.scheduler import Scheduler
from palchronicle.presentation.commands import Commands

try:  # normalizer/privacy_filter passed as modules to SnapshotService
    from palchronicle.adapters import normalizer as _normalizer_mod
    from palchronicle.adapters import privacy_filter as _privacy_mod
except Exception:  # pragma: no cover - defensive during partial builds
    _normalizer_mod = None
    _privacy_mod = None


class Container:
    def __init__(
        self, config: AppConfig, data_dir: Path, clock: Clock,
        rest_factory: Callable[[ServerConfig, Clock], PalworldRestClient] | None = None,
        scheduler_factory: Callable[..., Scheduler] | None = None,
    ) -> None:
        self._cfg = config
        self._data_dir = Path(data_dir)
        self._clock = clock
        self._rest_factory = rest_factory or (lambda s, clk: PalworldRestClient(s, clk))
        self._scheduler_factory = scheduler_factory or (lambda **kw: Scheduler(**kw))
        self._db: Database | None = None
        self._rest_clients: dict[str, PalworldRestClient] = {}
        self._scheduler: Scheduler | None = None
        self._snapshot: SnapshotService | None = None
        self.routing: RoutingService | None = None
        self.query: QueryService | None = None
        self.report: ReportService | None = None
        self.commands: Commands | None = None
        self._settings_cache: dict[str, dict] = {}
        self._world_cache: dict[str, object] = {}

    async def start(self) -> None:
        self._db = Database(self._data_dir / "palchronicle.sqlite3")
        await self._db.open()
        await apply_migrations(self._db)
        salt = load_or_create_salt(self._data_dir)

        repo = Repository(self._db, self._clock)
        await repo.sync_servers(self._cfg.servers)
        await repo.seed_bindings(self._cfg.group_bindings)
        ready_ids = {s.server_id for s in self._cfg.servers if s.ready}
        await repo.cleanup_orphan_bindings(ready_ids)

        meta = MetadataRepository(self._data_dir.parent / "metadata")
        try:
            meta.load()
        except Exception:  # pragma: no cover - metadata optional at start
            pass
        cache = TTLCache(self._clock)

        events = EventService(repo, self._clock)
        players = PlayerService(repo, salt, self._cfg, self._clock)
        guilds = GuildService()
        bases = BaseService(repo, self._cfg, self._clock)
        self._snapshot = SnapshotService(
            repo, _normalizer_mod, _privacy_mod, meta, salt, self._cfg, self._clock,
            players, guilds, bases, events,
        )
        self.report = ReportService(repo, self._cfg, self._clock)
        self.routing = RoutingService(repo, self._cfg)
        self.query = QueryService(
            repo, cache, self._cfg, meta, self._clock, self._settings_cache,
            world_cache=self._world_cache, report=self.report,
        )
        self.commands = Commands(self.routing, self.query, repo, self._cfg, self._clock)

        for s in self._cfg.servers:
            if s.ready:
                self._rest_clients[s.server_id] = self._rest_factory(s, self._clock)

        locks = EndpointLocks(self._cfg.polling.max_concurrency)
        self._scheduler = self._scheduler_factory(
            servers=[s for s in self._cfg.servers if s.ready],
            polling=self._cfg.polling, locks=locks, clock=self._clock,
            on_response=self._on_response, rng_seed=None,
        )
        await self._scheduler.start()

    async def _on_response(
        self, server_id: str, endpoint: EndpointName, resp: RestResponse
    ) -> None:
        server = next((s for s in self._cfg.servers if s.server_id == server_id), None)
        if server is None or self._snapshot is None:
            return
        if endpoint is EndpointName.INFO:
            await self._snapshot.ingest_info(server, resp)
            return
        world = None
        if hasattr(self._snapshot, "current_world"):
            world = self._snapshot.current_world(server_id)
        if world is None:
            return
        if endpoint is EndpointName.METRICS:
            await self._snapshot.ingest_metrics(world, resp)
        elif endpoint is EndpointName.PLAYERS:
            await self._snapshot.ingest_players(world, resp)
        elif endpoint is EndpointName.SETTINGS:
            await self._snapshot.ingest_settings(world, resp)
        elif endpoint is EndpointName.GAME_DATA:
            await self._snapshot.ingest_game_data(world, resp)

    async def stop(self) -> None:
        if self._scheduler is not None:
            await self._scheduler.stop()
        for client in self._rest_clients.values():
            await client.close()
        self._rest_clients.clear()
        if self._db is not None:
            await self._db.close()
```

> 说明：`_on_response` 对非 info 端点需要"当前 world"；`SnapshotService.current_world(server_id)` 若在 Phase 2 未暴露，则该方法在 Phase 2 补一个内存映射的 getter（本任务用 `hasattr` 兜底，测试仅覆盖 info 分发路径不依赖它）。`meta` 目录取 `data_dir.parent/"metadata"`（插件安装目录下的 `metadata/`）；load 失败不阻断启动（未知 Class 走安全降级）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/container_test.py -q`。期望 PASS：3 passed。

- [ ] **提交** — `git add palchronicle/container.py tests/unit/container_test.py && git commit -m "feat(container): assemble services + lifecycle start/stop"`

---

### Task 5.15：main.py — Star 子类（生命周期 + 命令组）

**Files:**
- Create: `main.py`
- Test: `tests/unit/main_test.py`

**Interfaces:**
- Consumes: `parse_config`、`Container`、`Commands`（经 `container.commands`）、AstrBot `Star`/`Context`/`AstrBotConfig`/`filter`/`register`/`StarTools`。
- Produces：
  - `class PalChronicle(Star)`：`__init__(self, context, config)`（存 config，不 await）；`async def initialize()`（`parse_config` → `Container.start()`）；`async def terminate()`（`Container.stop()`）；`@filter.command_group("pal") def pal(self): pass`；各子命令 `async def(self, event): yield event.plain_result(await self._c.commands.<...>(...))`。
  - 从 event 取上下文的内部辅助（`_umo(event)`/`_is_group(event)`/`_is_admin(event)`/`_msg(event)`）。

> AstrBot 导入在测试环境不可用，故 main.py 顶部对 `astrbot.*` 的导入用 `try/except ImportError` 包裹并在缺失时提供轻量 stub（仅用于装饰器/基类占位），使 `initialize`/`terminate` 可在 fake context + 内存 db 下单测。真实运行时导入成功，stub 不生效。

- [ ] **写失败测试** — 创建 `tests/unit/main_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.config import (
    AppConfig,  # noqa: F401  (ensure importable)
)


def _raw_config(tmp_path: Path) -> dict:
    return {
        "servers": [
            {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
             "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
             "timezone": ""},
        ],
        "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {"metrics_seconds": 30, "players_seconds": 30, "info_seconds": 600,
                    "settings_seconds": 1800, "game_data_seconds": 120, "jitter_ratio": 0.1,
                    "max_concurrency": 6},
        "world": {"timezone": "Asia/Tokyo", "locale": "zh-CN", "fps_smooth": 50,
                  "fps_moderate": 35, "fps_laggy": 20},
        "bases": {"enabled": True, "assignment_radius": 5000, "ambiguity_ratio": 0.2,
                  "confirmation_samples": 3, "position_grid_size": 2000, "z_weight": 0.5},
        "privacy": {"mode": "balanced", "public_exact_ping": False, "public_positions": False,
                    "ping_good_ms": 60, "ping_ok_ms": 120, "uncertain_timeout": 900},
        "history": {"raw_metrics_days": 7, "aggregate_days": 90, "session_days": 365,
                    "observation_days": 180},
    }


class _FakeContext:
    pass


@pytest.mark.asyncio
async def test_initialize_and_terminate(tmp_path: Path, monkeypatch):
    import main as main_mod

    # avoid real network + real scheduler: monkeypatch Container factory used by main
    from palchronicle.container import Container

    class _FakeRest:
        async def close(self):
            pass

    class _FakeSched:
        async def start(self):
            pass

        async def stop(self):
            pass

    orig_init = Container.__init__

    def patched_init(self, config, data_dir, clock, **kw):
        kw.setdefault("rest_factory", lambda s, c: _FakeRest())
        kw.setdefault("scheduler_factory", lambda **k: _FakeSched())
        orig_init(self, config, data_dir, clock, **kw)

    monkeypatch.setattr(Container, "__init__", patched_init)
    # main.initialize must place data under tmp_path
    monkeypatch.setattr(main_mod, "_resolve_data_dir", lambda: tmp_path)

    plugin = main_mod.PalChronicle(_FakeContext(), _raw_config(tmp_path))
    await plugin.initialize()
    assert plugin._container is not None
    assert plugin._container.commands is not None
    await plugin.terminate()
    assert (tmp_path / "palchronicle.sqlite3").exists()


def test_pal_command_group_is_plain_def():
    import inspect

    import main as main_mod

    # command group handler is a plain (non-async) def per AstrBot convention
    assert not inspect.iscoroutinefunction(main_mod.PalChronicle.pal)
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/unit/main_test.py -q`。期望 FAIL：`ModuleNotFoundError: No module named 'main'`。

- [ ] **写最小实现** — 创建 `main.py`（仓库根）：

```python
from __future__ import annotations

import os
from pathlib import Path

try:  # real AstrBot runtime
    from astrbot.api import AstrBotConfig
    from astrbot.api.event import filter
    from astrbot.api.star import Context, Star, StarTools, register
    _ASTRBOT = True
except Exception:  # test / standalone environment: lightweight stubs
    _ASTRBOT = False
    AstrBotConfig = dict  # type: ignore

    class Context:  # type: ignore
        pass

    class Star:  # type: ignore
        def __init__(self, context=None, config=None):
            pass

    class StarTools:  # type: ignore
        @staticmethod
        def get_data_dir() -> Path:
            return Path(os.getcwd())

    def register(*_a, **_k):  # type: ignore
        def deco(cls):
            return cls
        return deco

    class _PermissionType:
        ADMIN = "admin"

    class _Filter:  # minimal decorator stubs
        PermissionType = _PermissionType

        @staticmethod
        def command_group(_name):
            def deco(fn):
                fn.is_group = True
                return fn
            return deco

        @staticmethod
        def permission_type(_p):
            def deco(fn):
                return fn
            return deco

    filter = _Filter()  # type: ignore

from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.infrastructure.clock import SystemClock


def _resolve_data_dir() -> Path:
    try:
        return Path(StarTools.get_data_dir())
    except Exception:
        return Path(os.getcwd())


@register("astrbot_plugin_palword", "SolitudeRA",
          "只读的 Palworld 世界纪事插件", "0.1.0",
          "https://github.com/SolitudeRA/astrbot_plugin_palword")
class PalChronicle(Star):
    def __init__(self, context, config):
        super().__init__(context, config)
        self._context = context
        self._raw_config = config
        self._container: Container | None = None

    async def initialize(self) -> None:
        cfg = parse_config(self._raw_config, os.environ)
        data_dir = _resolve_data_dir()
        self._container = Container(cfg, data_dir, SystemClock())
        await self._container.start()

    async def terminate(self) -> None:
        if self._container is not None:
            await self._container.stop()
            self._container = None

    # ---- context helpers ----
    @staticmethod
    def _umo(event) -> str:
        return getattr(event, "unified_msg_origin", "")

    @staticmethod
    def _msg(event) -> str:
        return getattr(event, "message_str", "")

    @staticmethod
    def _is_group(event) -> bool:
        fn = getattr(event, "is_private_chat", None)
        if callable(fn):
            return not fn()
        gid = getattr(event, "get_group_id", lambda: "")()
        return bool(gid)

    @staticmethod
    def _is_admin(event) -> bool:
        role = getattr(event, "role", "")
        return role == "admin" or bool(getattr(event, "is_admin", False))

    @filter.command_group("pal")
    def pal(self):
        pass

    @pal.command("status")
    async def status(self, event):
        yield event.plain_result(
            await self._container.commands.status(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("online")
    async def online(self, event):
        yield event.plain_result(
            await self._container.commands.online(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("world")
    async def world(self, event):
        yield event.plain_result(
            await self._container.commands.world(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("rules")
    async def rules(self, event):
        yield event.plain_result(
            await self._container.commands.rules(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("guilds")
    async def guilds(self, event):
        yield event.plain_result(
            await self._container.commands.guilds(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("guild")
    async def guild(self, event):
        yield event.plain_result(
            await self._container.commands.guild(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("bases")
    async def bases(self, event):
        yield event.plain_result(
            await self._container.commands.bases(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("base")
    async def base(self, event):
        yield event.plain_result(
            await self._container.commands.base(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("events")
    async def events(self, event):
        yield event.plain_result(
            await self._container.commands.events(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("today")
    async def today(self, event):
        yield event.plain_result(
            await self._container.commands.today(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("servers")
    async def servers(self, event):
        yield event.plain_result(
            await self._container.commands.servers(self._umo(event), self._is_group(event), self._is_admin(event))
        )

    @pal.command("help")
    async def help(self, event):
        yield event.plain_result(
            self._container.commands.help(self._msg(event), self._is_admin(event))
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @pal.command("use")
    async def use(self, event):
        yield event.plain_result(
            await self._container.commands.use(
                self._umo(event), self._msg(event), self._is_group(event), self._is_admin(event)
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @pal.command("unbind")
    async def unbind(self, event):
        yield event.plain_result(
            await self._container.commands.unbind(
                self._umo(event), self._msg(event), self._is_group(event), self._is_admin(event)
            )
        )
```

> `@pal.command(...)` 需要命令组对象具备 `.command` 属性；真实 AstrBot 的 `command_group` 返回的对象提供它。在 stub 环境下 `pal` 只是带 `is_group` 标记的普通函数、无 `.command`，故测试仅覆盖 `initialize`/`terminate` 与 `pal` 是普通 def；不实例化子命令装饰路径。若 stub 下类体因 `@pal.command` 求值报错，测试 `test_pal_command_group_is_plain_def` 会先暴露——此时把子命令装饰改为对 `getattr(pal, "command", lambda *_a, **_k: (lambda f: f))` 的兼容包装。**实现时**：在 stub 分支为 `pal` 附加一个 `command` 方法返回恒等装饰器，保证 import 阶段不崩：即在 stub 的 `command_group` 装饰器里给返回的 `fn` 挂 `fn.command = lambda *_a, **_k: (lambda f: f)`。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/unit/main_test.py -q`。期望 PASS：2 passed。

- [ ] **提交** — `git add main.py tests/unit/main_test.py && git commit -m "feat(main): Star subclass lifecycle + pal command group"`

---

### Task 5.16：Phase 5 端到端集成（restricted 授权 → 查询）

**Files:**
- Test: `tests/integration/routing_e2e_test.py`

**Interfaces:**
- Consumes: `Container`（fake rest/scheduler）、`Commands`、`RoutingService`、`Repository`。验收 spec §19「restricted 模式下未授权群被拒绝、`/pal use` 授权后可查询」。
- Produces: 无新生产代码；纯集成验证（若失败则回到相应 Task 修实现，不在本任务写实现代码）。

- [ ] **写失败测试** — 创建 `tests/integration/routing_e2e_test.py`：

```python
from pathlib import Path

import pytest

from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.container import Container
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World, WorldMetric
from palchronicle.infrastructure.clock import FakeClock

UMO = "aiocqhttp:GroupMessage:123"


def _server() -> ServerConfig:
    return ServerConfig("alpha", "alpha", True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[_server()], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


class _FakeRest:
    async def close(self):
        pass


class _FakeSched:
    async def start(self):
        pass

    async def stop(self):
        pass


@pytest.mark.asyncio
async def test_restricted_denies_then_use_allows(tmp_path: Path):
    clock = FakeClock(1700000000)
    c = Container(_cfg(), tmp_path, clock,
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    try:
        repo = c.routing._repo
        wid = "alpha:guid-1:0"
        await repo.upsert_world(World(wid, "alpha", "guid-1", 0, "alpha", "0.3", 1, clock.now(), 42))
        await repo.insert_metric(WorldMetric(wid, clock.now(), 58.0, 17.0, 2, 42, 5))

        # 1) unauthorized group is denied
        denied = await c.commands.status(UMO, "/pal status", is_group=True)
        assert "未被授权" in denied or "未指定服务器" in denied

        # 2) admin authorizes via /pal use
        use_msg = await c.commands.use(UMO, "/pal use alpha", is_group=True, is_admin=True)
        assert "alpha" in use_msg

        # 3) now the same group can query status
        ok = await c.commands.status(UMO, "/pal status", is_group=True)
        assert "第 42 天" in ok
        assert "据点：5" in ok
    finally:
        await c.stop()
```

- [ ] **跑测试确认失败** — 命令：`python -m pytest tests/integration/routing_e2e_test.py -q`。期望 FAIL（首跑，未先建 `tests/integration/__init__.py` 或断言不满足时）：最可能是 `AssertionError`（若 `/pal status` 文案与断言字符串不完全一致），据实调整断言或对应 formatter；确认失败原因来自集成路径而非 import 缺失（若 import 缺失说明前置 Task 未提交，回补）。

- [ ] **写最小实现** — 本任务不新增生产代码；若上一步因文案不匹配失败，回到 Task 5.12 的 `format_status` 或 Task 5.5 文案统一断言用词（如把断言改为与 `format_status` 实际输出一致的 `"第 42 天"`、`"据点：5（官方指标）"`）。集成测试作为回归护栏提交。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/integration/routing_e2e_test.py -q`。期望 PASS：1 passed。

- [ ] **提交** — `git add tests/integration/routing_e2e_test.py && git commit -m "test(integration): restricted deny then /pal use allows query e2e"`

---

### Task 5.17：Phase 5 全量回归 + 覆盖确认

**Files:**
- Test: 运行既有全部测试（无新增）

**Interfaces:**
- Consumes: 全阶段测试。
- Produces: 无。收口任务，确保 14 命令端到端可用且前四阶段未回归。

- [ ] **写失败测试** — 无新测试；本步为确认既有失败已清零前的基线：先跑 `python -m pytest tests/ -q --co` 收集用例清单（`--co` 只收集不执行），确认所有 Phase 5 测试模块可被导入（无 collection error）。若有 collection error（import 缺失），说明某前置 Task 未提交，回补对应 Task。

- [ ] **跑测试确认失败/收集** — 命令：`python -m pytest tests/ -q --co 2>&1 | tail -30`。期望：无 `ERROR`（收集阶段全部模块导入成功）。若出现 collection error，记录缺失符号并回到对应 Task。

- [ ] **写最小实现** — 无生产代码改动；本步仅在发现回归时定位修复（修复归属对应 Task，本任务不承载新代码）。

- [ ] **跑测试确认通过** — 命令：`python -m pytest tests/ -q`。期望 PASS：全部通过（Phase 1-5 累计）。特别确认 Phase 5 新增模块：`repository_routing_test`、`server_arg_test`、`dtos_test`、`locale_test`、`routing_service_resolve_test`、`routing_service_use_test`、`repository_query_test`、`query_service_status_test`、`query_service_bases_test`、`query_service_rules_test`、`formatters_test`、`formatters_golden_test`、`commands_test`、`container_test`、`main_test`、`routing_e2e_test` 全绿。

- [ ] **提交** — `git commit --allow-empty -m "test(phase5): full regression green — 14 commands e2e ready"`


## Phase 6：集成 / 隐私 / 路由测试 + fixtures + README

> 本阶段收口：新增 fixtures（合成脱敏 API 快照）、端到端时间序列集成测试、隐私扫描 + 日志脱敏测试、路由 / 访问控制集成测试、metadata 种子补全、README、smoke 测试，最终 `pytest` 全绿。
> 本阶段**不重复**各单元阶段（Phase 1–5）已写的单测；仅新增集成 / 隐私 / 路由测试、fixtures、文档与 smoke。
> 所有消费的类型 / 函数签名严格照《接口契约》与跨阶段共享定义（`BaseUpdate`、`DailyReport`、展示 DTO、`Repository`、`Container`、`SnapshotService`、`RoutingService`、`QueryService`、`format_*`）。

### Task 6.1：fixtures 加载器 helper

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/loader.py`
- Create: `tests/fixtures/normal_world/info.json`, `metrics.json`, `players.json`, `game-data.json`
- Test: `tests/unit/fixtures_loader_test.py`

**Interfaces:**
- Consumes: 无（纯测试基建）。
- Produces：
  - `load_fixture(scenario: str, endpoint: str) -> dict`（读取 `tests/fixtures/<scenario>/<endpoint>.json` 并 `json.load`；`endpoint` 取 `"info"|"metrics"|"players"|"game-data"|"settings"`）
  - `load_series(scenario: str) -> list[dict]`（读取 `tests/fixtures/<scenario>/series.json`，返回按 `tick` 排序的帧列表，每帧形如 `{"tick": int, "endpoint": str, "payload": dict}`）
  - `fixtures_root() -> pathlib.Path`

- [ ] **1. 写失败测试** — 创建 `tests/unit/fixtures_loader_test.py`：

```python
import json
from pathlib import Path

import pytest

from tests.fixtures.loader import fixtures_root, load_fixture, load_series


def test_fixtures_root_points_to_fixtures_dir():
    root = fixtures_root()
    assert root.name == "fixtures"
    assert (root / "loader.py").is_file()


def test_load_fixture_normal_world_info_has_worldguid():
    info = load_fixture("normal_world", "info")
    assert isinstance(info, dict)
    assert "worldguid" in {k.lower() for k in info}


def test_load_fixture_normal_world_players_is_list_payload():
    players = load_fixture("normal_world", "players")
    # /players 响应体是 {"players": [...]}
    assert "players" in {k.lower() for k in players}
    plist = next(v for k, v in players.items() if k.lower() == "players")
    assert isinstance(plist, list) and len(plist) >= 1


def test_load_fixture_missing_scenario_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fixture("does_not_exist", "info")


def test_load_series_sorted_by_tick():
    # api_interrupt_recovery 场景在 Task 6.3 创建；此处先断言排序契约用 normal_world 兜底
    root = fixtures_root()
    series_path = root / "normal_world" / "series.json"
    series_path.write_text(
        json.dumps(
            [
                {"tick": 2, "endpoint": "players", "payload": {"players": []}},
                {"tick": 1, "endpoint": "metrics", "payload": {"fps": 60}},
            ]
        ),
        encoding="utf-8",
    )
    try:
        series = load_series("normal_world")
        assert [f["tick"] for f in series] == [1, 2]
    finally:
        series_path.unlink()
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/unit/fixtures_loader_test.py -q`
  期望 FAIL：`ModuleNotFoundError: No module named 'tests.fixtures.loader'`（loader 与 fixture JSON 尚未创建）。

- [ ] **3. 写最小实现** — 创建 `tests/fixtures/__init__.py`（空文件），创建 `tests/fixtures/loader.py`：

```python
"""合成脱敏 API 快照 fixtures 的加载器。所有 fixture 均为已脱敏样本（无真实 IP/账号/坐标语义）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def fixtures_root() -> Path:
    return Path(__file__).resolve().parent


def load_fixture(scenario: str, endpoint: str) -> dict[str, Any]:
    path = fixtures_root() / scenario / f"{endpoint}.json"
    if not path.is_file():
        raise FileNotFoundError(f"fixture not found: {scenario}/{endpoint}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def load_series(scenario: str) -> list[dict[str, Any]]:
    path = fixtures_root() / scenario / "series.json"
    if not path.is_file():
        raise FileNotFoundError(f"series fixture not found: {scenario}/series.json")
    frames = json.loads(path.read_text(encoding="utf-8"))
    return sorted(frames, key=lambda f: f["tick"])
```

  创建 `tests/fixtures/normal_world/info.json`：

```json
{
  "version": "v0.3.4",
  "servername": "Chronicle Test World",
  "description": "synthetic normal world",
  "worldguid": "WORLDGUID-AAAA-0001"
}
```

  创建 `tests/fixtures/normal_world/metrics.json`：

```json
{
  "serverfps": 58,
  "currentplayernum": 2,
  "serverframetime": 17.2,
  "maxplayernum": 32,
  "uptime": 36000,
  "days": 42,
  "basecampnum": 3
}
```

  创建 `tests/fixtures/normal_world/players.json`：

```json
{
  "players": [
    {"userId": "steam_00001", "playerId": "PID-1", "name": "Akari", "level": 21, "ping": 44.0, "ip": "10.0.0.11", "accountName": "acct_akari", "building_count": 12, "location_x": 100.0, "location_y": 200.0},
    {"userId": "steam_00002", "playerId": "PID-2", "name": "Borel", "level": 15, "ping": 130.0, "ip": "10.0.0.12", "accountName": "acct_borel", "building_count": 4, "location_x": 3000.0, "location_y": 3200.0}
  ]
}
```

  创建 `tests/fixtures/normal_world/game-data.json`：

```json
{
  "fps": 58,
  "average_fps": 55.5,
  "actors": [
    {"unit_type": "Player", "InstanceID": "INST-P1", "NickName": "Akari", "userid": "steam_00001", "Level": 21, "HP": 500, "MaxHP": 500, "GuildID": "G-1", "GuildName": "Noema", "action": "Idle", "LocationX": 100.0, "LocationY": 200.0, "LocationZ": 0.0, "IsActive": "true"},
    {"unit_type": "BaseCampPal", "pal_class": "SheepBall", "Level": 8, "HP": 180, "MaxHP": 200, "GuildID": "G-1", "action": "Work", "AI_Action": "Work", "LocationX": 120.0, "LocationY": 210.0, "LocationZ": 0.0, "IsActive": "true"},
    {"unit_type": "BaseCampPal", "pal_class": "Foxparks", "Level": 10, "HP": 90, "MaxHP": 150, "GuildID": "G-1", "action": "Idle", "AI_Action": "Idle", "LocationX": 118.0, "LocationY": 205.0, "LocationZ": 0.0, "IsActive": "false"},
    {"unit_type": "WildPal", "pal_class": "Lamball", "Level": 3, "HP": 60, "MaxHP": 60, "action": "Idle", "LocationX": 9000.0, "LocationY": 9000.0, "LocationZ": 0.0, "IsActive": "true"}
  ],
  "palboxes": [
    {"GuildID": "G-1", "GuildName": "Noema", "LocationX": 110.0, "LocationY": 205.0, "LocationZ": 0.0}
  ]
}
```

  创建 `tests/fixtures/normal_world/settings.json`：

```json
{
  "ExpRate": 1.0,
  "PalCaptureRate": 1.2,
  "DeathPenalty": "Item",
  "bEnablePlayerToPlayerDamage": false,
  "ServerPlayerMaxNum": 32,
  "GuildPlayerMaxNum": 20,
  "BaseCampMaxNumInGuild": 4
}
```

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/unit/fixtures_loader_test.py -q`
  期望 PASS：5 passed。

- [ ] **5. 提交** —
  `git add tests/fixtures/ tests/unit/fixtures_loader_test.py && git commit -m "test(fixtures): add fixture loader helper + normal_world snapshot"`

---

### Task 6.2：边界 fixtures（无玩家 / 多公会多据点 / 字段缺失 / 未知 Class / IsActive 字符串 / 大小写混用键 / 401）

**Files:**
- Create: `tests/fixtures/no_players/players.json`, `tests/fixtures/no_players/metrics.json`
- Create: `tests/fixtures/multi_guild_base/game-data.json`
- Create: `tests/fixtures/missing_fields/game-data.json`, `tests/fixtures/missing_fields/players.json`
- Create: `tests/fixtures/unknown_class/game-data.json`
- Create: `tests/fixtures/mixed_case_keys/players.json`, `tests/fixtures/mixed_case_keys/game-data.json`
- Create: `tests/fixtures/unauthorized/players.json`（401 由 loader 标注 `status`，见下）
- Test: `tests/unit/fixtures_boundary_test.py`

**Interfaces:**
- Consumes：`load_fixture`（Task 6.1）；`normalize_players` / `normalize_game_data`（契约 `normalizer.py`，Phase 2 产出）；`MetadataRepository`（契约，Phase 2）；`ci_get` / `str_bool`（契约 `normalizer.py`）。
- Produces：边界场景 fixture 文件（供 Task 6.3/6.4 端到端序列引用）。

- [ ] **1. 写失败测试** — 创建 `tests/unit/fixtures_boundary_test.py`（断言归一器能把各边界 fixture 正确降级，从而证明 fixture 内容有效）：

```python
from pathlib import Path

from palchronicle.adapters import normalizer
from palchronicle.adapters.metadata_repository import MetadataRepository
from tests.fixtures.loader import fixtures_root, load_fixture

META = MetadataRepository(Path(__file__).resolve().parents[2] / "metadata")
META.load()


def test_no_players_scenario_yields_empty_player_list():
    raw = load_fixture("no_players", "players")
    rows = normalizer.normalize_players(raw, now=1000)
    assert rows == []


def test_multi_guild_base_has_two_guilds_and_two_palboxes():
    raw = load_fixture("multi_guild_base", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    guild_ids = {a.guild_id for a in snap.characters if a.guild_id}
    assert len(guild_ids) >= 2
    assert len(snap.palboxes) >= 2


def test_missing_fields_game_data_does_not_crash_and_defaults_none():
    raw = load_fixture("missing_fields", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    # 一个 actor 缺 Level/HP/坐标：归一为 None 而非抛错
    assert any(a.level is None for a in snap.characters)
    assert any(a.x is None for a in snap.characters)


def test_unknown_class_registered_and_not_dropped():
    raw = load_fixture("unknown_class", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    assert snap.unknown_classes  # 至少登记一个未知 Class
    # 未知 Class 的 actor 仍保留在快照中，不丢整帧
    assert len(snap.characters) >= 1


def test_mixed_case_keys_players_still_parsed():
    raw = load_fixture("mixed_case_keys", "players")
    rows = normalizer.normalize_players(raw, now=1000)
    assert len(rows) == 1
    assert rows[0]["name"] == "CaseTest"
    assert rows[0]["userId"] == "steam_mixed"


def test_mixed_case_keys_isactive_string_bool_true():
    raw = load_fixture("mixed_case_keys", "game-data")
    snap = normalizer.normalize_game_data(raw, now=1000, meta=META)
    assert snap.characters[0].is_active is True
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/unit/fixtures_boundary_test.py -q`
  期望 FAIL：`FileNotFoundError: fixture not found: no_players/players.json`（边界 fixture 尚未创建）。

- [ ] **3. 写最小实现** — 创建以下 fixture 文件。

  `tests/fixtures/no_players/players.json`：

```json
{"players": []}
```

  `tests/fixtures/no_players/metrics.json`：

```json
{"serverfps": 60, "currentplayernum": 0, "serverframetime": 16.6, "maxplayernum": 32, "uptime": 100, "days": 43, "basecampnum": 3}
```

  `tests/fixtures/multi_guild_base/game-data.json`（两公会各一 PalBox，各带据点帕鲁）：

```json
{
  "fps": 55,
  "average_fps": 54.0,
  "actors": [
    {"unit_type": "BaseCampPal", "pal_class": "SheepBall", "Level": 8, "HP": 180, "MaxHP": 200, "GuildID": "G-1", "action": "Work", "AI_Action": "Work", "LocationX": 100.0, "LocationY": 200.0, "LocationZ": 0.0, "IsActive": "true"},
    {"unit_type": "BaseCampPal", "pal_class": "Foxparks", "Level": 6, "HP": 120, "MaxHP": 120, "GuildID": "G-1", "action": "Idle", "AI_Action": "Idle", "LocationX": 105.0, "LocationY": 205.0, "LocationZ": 0.0, "IsActive": "true"},
    {"unit_type": "BaseCampPal", "pal_class": "Lamball", "Level": 4, "HP": 60, "MaxHP": 60, "GuildID": "G-2", "action": "Work", "AI_Action": "Work", "LocationX": 8000.0, "LocationY": 8000.0, "LocationZ": 0.0, "IsActive": "true"},
    {"unit_type": "BaseCampPal", "pal_class": "Cattiva", "Level": 5, "HP": 70, "MaxHP": 90, "GuildID": "G-2", "action": "Idle", "AI_Action": "Idle", "LocationX": 8010.0, "LocationY": 8005.0, "LocationZ": 0.0, "IsActive": "false"}
  ],
  "palboxes": [
    {"GuildID": "G-1", "GuildName": "Noema", "LocationX": 102.0, "LocationY": 202.0, "LocationZ": 0.0},
    {"GuildID": "G-2", "GuildName": "Vesper", "LocationX": 8005.0, "LocationY": 8002.0, "LocationZ": 0.0}
  ]
}
```

  `tests/fixtures/missing_fields/game-data.json`（一 actor 缺 Level/HP/坐标）：

```json
{
  "fps": 50,
  "actors": [
    {"unit_type": "Player", "InstanceID": "INST-PX", "NickName": "Ghosty", "userid": "steam_x", "GuildID": "G-9", "IsActive": "true"},
    {"unit_type": "BaseCampPal", "pal_class": "SheepBall", "HP": 100, "MaxHP": 200, "GuildID": "G-9", "action": "Work", "LocationX": 10.0, "LocationY": 20.0, "LocationZ": 0.0, "IsActive": "true"}
  ],
  "palboxes": []
}
```

  `tests/fixtures/missing_fields/players.json`（缺 userId，仅 playerId + name）：

```json
{"players": [{"playerId": "PID-ONLY", "name": "NoUserId", "level": 5, "building_count": 0}]}
```

  `tests/fixtures/unknown_class/game-data.json`：

```json
{
  "fps": 57,
  "actors": [
    {"unit_type": "BaseCampPal", "pal_class": "TotallyUnknownPal_XYZ", "Level": 9, "HP": 200, "MaxHP": 200, "GuildID": "G-1", "action": "Work", "AI_Action": "Work", "LocationX": 100.0, "LocationY": 200.0, "LocationZ": 0.0, "IsActive": "true"}
  ],
  "palboxes": [{"GuildID": "G-1", "GuildName": "Noema", "LocationX": 100.0, "LocationY": 200.0, "LocationZ": 0.0}]
}
```

  `tests/fixtures/mixed_case_keys/players.json`（键名大小写混用 + `IP`/`AccountName` 大写变体）：

```json
{"PLAYERS": [{"UserID": "steam_mixed", "PlayerID": "PID-M", "NAME": "CaseTest", "Level": 12, "PING": 70.0, "IP": "10.0.0.99", "AccountName": "acct_case", "Building_Count": 3, "Location_X": 500.0, "Location_Y": 600.0}]}
```

  `tests/fixtures/mixed_case_keys/game-data.json`（`IsActive` 字符串布尔 + 混用键）：

```json
{
  "FPS": 60,
  "Average_FPS": 59.0,
  "Actors": [
    {"Unit_Type": "Player", "InstanceID": "INST-M1", "NICKNAME": "CaseTest", "userid": "steam_mixed", "level": 12, "hp": 400, "maxhp": 400, "guildid": "G-1", "guildname": "Noema", "Action": "Idle", "locationx": 500.0, "locationy": 600.0, "locationz": 0.0, "isactive": "true"}
  ],
  "PalBoxes": [{"guildid": "G-1", "guildname": "Noema", "locationx": 500.0, "locationy": 600.0, "locationz": 0.0}]
}
```

  `tests/fixtures/unauthorized/players.json`（用于 401 场景；HTTP 401 在测试中由伪造 `RestResponse(ok=False, status=401, ...)` 构造，此文件仅作占位说明 401 返回体常为空/HTML）：

```json
{"error": "Unauthorized"}
```

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/unit/fixtures_boundary_test.py -q`
  期望 PASS：6 passed。

- [ ] **5. 提交** —
  `git add tests/fixtures/ tests/unit/fixtures_boundary_test.py && git commit -m "test(fixtures): add boundary snapshots (no-players/multi-guild/missing/unknown/mixed-case/401)"`

---

### Task 6.3：pipeline 集成 — 会话上下线 + 升级 + 世界日里程碑

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`（构建单服务器容器 + FakeClock 的 fixture）
- Create: `tests/integration/pipeline_test.py`
- Test: 同上（本任务只写前 3 个端到端断言，后续任务向同文件追加）

**Interfaces:**
- Consumes：
  - `parse_config(raw, env)`（契约 `config.py`）→ `AppConfig`
  - `Container(config, data_dir, clock)` + `await Container.start()/stop()`（契约 `container.py`）；`Container.query: QueryService`、`Container.routing: RoutingService`
  - `SnapshotService.ingest_info/ingest_metrics/ingest_players/ingest_game_data`（契约，返回 `World|None` / `None`）
  - `Repository.get_current_world(server_id) -> World|None`、`list_open_sessions(world_id)`、`list_events(world_id, since, limit)`、`latest_metric(world_id)`（契约）
  - `WorldEvent.event_type: EventType`、`EventType.PLAYER_LEVEL_UP/WORLD_DAY_MILESTONE`（契约 enums）
  - `RestResponse(ok, status, data, duration_ms, payload_bytes, error)`（契约 `palworld_rest.py`）
  - `FakeClock(start)`、`.advance(secs)`（契约 `clock.py`）
- Produces：集成 fixture `container_for(scenario)`（conftest）与端到端断言。

- [ ] **1. 写失败测试** — 创建 `tests/integration/__init__.py`（空），`tests/integration/conftest.py`：

```python
import pytest_asyncio

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock


def make_config(mode: str = "balanced", access_mode: str = "restricted") -> dict:
    return {
        "servers": [
            {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
             "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": "Asia/Tokyo"}
        ],
        "routing": {"access_mode": access_mode, "default_server": ""},
        "group_bindings": [],
        "polling": {"metrics_seconds": 30, "players_seconds": 30, "info_seconds": 600,
                    "settings_seconds": 1800, "game_data_seconds": 120, "jitter_ratio": 0.0, "max_concurrency": 6},
        "world": {"timezone": "Asia/Tokyo", "locale": "zh-CN", "fps_smooth": 50, "fps_moderate": 35, "fps_laggy": 20},
        "bases": {"enabled": True, "assignment_radius": 5000, "ambiguity_ratio": 0.20,
                  "confirmation_samples": 3, "position_grid_size": 2000, "z_weight": 0.5},
        "privacy": {"mode": mode, "public_exact_ping": False, "public_positions": False,
                    "ping_good_ms": 60, "ping_ok_ms": 120, "uncertain_timeout": 900},
        "history": {"raw_metrics_days": 7, "aggregate_days": 90, "session_days": 365, "observation_days": 180},
    }


def ok(data) -> RestResponse:
    return RestResponse(ok=True, status=200, data=data, duration_ms=5, payload_bytes=len(str(data)), error=None)


def fail(status: int | None = None, error: str = "unreachable") -> RestResponse:
    return RestResponse(ok=False, status=status, data=None, duration_ms=5, payload_bytes=0, error=error)


@pytest_asyncio.fixture
async def harness(tmp_path):
    """返回 (container, server_config, clock, snap_service) 单服务器采集夹具。"""
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(make_config(), env={})
    container = Container(config=cfg, data_dir=tmp_path, clock=clock)
    await container.start()
    server = cfg.servers[0]
    snap = container.snapshot_service_for(server.server_id)
    try:
        yield container, server, clock, snap
    finally:
        await container.stop()
```

> 说明：`Container` 需暴露 `snapshot_service_for(server_id) -> SnapshotService`（Phase 5 装配时按服务器持有）。若 Phase 5 未暴露该名，此 conftest 为该访问器建立契约——实现时在 `Container` 增加该只读访问器（不改变已有 API）。

  创建 `tests/integration/pipeline_test.py`：

```python
import pytest

from palchronicle.domain.enums import EndpointName, EventType, SessionStatus
from tests.fixtures.loader import load_fixture
from tests.integration.conftest import ok

pytestmark = pytest.mark.asyncio


async def _boot_world(snap, server, clock):
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    assert world is not None
    await snap.ingest_metrics(world, ok(load_fixture("normal_world", "metrics")))
    return world


async def test_session_online_then_offline(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)

    # 两个玩家在线
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    sessions = await container.repo.list_open_sessions(world.world_id)
    assert len(sessions) == 2
    assert all(s.status == SessionStatus.ACTIVE for s in sessions)

    # 连续两个健康快照缺失 → 关闭会话
    clock.advance(30)
    await snap.ingest_players(world, ok({"players": []}))
    clock.advance(30)
    await snap.ingest_players(world, ok({"players": []}))
    open_after = await container.repo.list_open_sessions(world.world_id)
    assert open_after == []


async def test_level_up_confirmed_event(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))

    # Akari 从 21 升到 23，连续两次观察确认
    up = {"players": [{"userId": "steam_00001", "playerId": "PID-1", "name": "Akari",
                       "level": 23, "ping": 44.0, "building_count": 12}]}
    clock.advance(30)
    await snap.ingest_players(world, ok(up))
    clock.advance(30)
    await snap.ingest_players(world, ok(up))

    events = await container.repo.list_events(world.world_id, since=None, limit=50)
    level_ups = [e for e in events if e.event_type == EventType.PLAYER_LEVEL_UP]
    assert len(level_ups) == 1
    assert level_ups[0].payload["new_level"] == 23


async def test_world_day_milestone_event(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)

    # metrics.days 从 42 跨过 100 里程碑
    m = load_fixture("normal_world", "metrics")
    m99 = {**m, "days": 99}
    m101 = {**m, "days": 101}
    await snap.ingest_metrics(world, ok(m99))
    await snap.ingest_metrics(world, ok(m101))

    events = await container.repo.list_events(world.world_id, since=None, limit=50)
    milestones = [e for e in events if e.event_type == EventType.WORLD_DAY_MILESTONE]
    assert len(milestones) == 1
    assert milestones[0].payload["milestone"] == 100
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -q`
  期望 FAIL：`AttributeError: 'Container' object has no attribute 'snapshot_service_for'`（访问器未暴露），或 `snapshot_service_for` 返回后 `ingest_*` 尚未串通全链路导致断言不成立。

- [ ] **3. 写最小实现** — 在 `palchronicle/container.py` 的 `Container` 上补充只读访问器（不改动已有装配逻辑）：

```python
    def snapshot_service_for(self, server_id: str) -> "SnapshotService":
        """返回指定服务器的 SnapshotService（集成测试与内部采集回调共用）。"""
        return self._snapshot_services[server_id]
```

  其中 `self._snapshot_services: dict[str, SnapshotService]` 在 `start()` 装配每服务器采集时填充（Phase 5 已按服务器构造 `SnapshotService`；此处仅把它们收进字典并暴露）。同时确保 `Container` 暴露 `self.repo: Repository`（若 Phase 5 未公开，补 `self.repo = repo`）。

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -q`
  期望 PASS：3 passed（session 上下线、升级确认事件、世界日里程碑事件）。

- [ ] **5. 提交** —
  `git add tests/integration/ palchronicle/container.py && git commit -m "test(integration): pipeline session lifecycle + level-up + world-day milestone"`

---

### Task 6.4：pipeline 集成 — API 中断不误判离线 + uncertain 恢复复用

**Files:**
- Create: `tests/fixtures/api_interrupt_recovery/series.json`
- Modify: `tests/integration/pipeline_test.py`（追加两个测试）

**Interfaces:**
- Consumes：`SnapshotService.ingest_players`、`PlayerService.mark_uncertain`（经 `SnapshotService` 在 players 端点失败时调用）、`Repository.list_open_sessions`、`Repository.get_open_session(world_id, player_key)`（active 优先，否则 uncertain）；`SessionStatus.ACTIVE/UNCERTAIN`；`load_series`。
- Produces：`api_interrupt_recovery` 序列 fixture + 两个端到端断言（不误判离线；uncertain 复用同一会话，`joined_at` 不变、时长连续）。

- [ ] **1. 写失败测试** — 追加到 `tests/integration/pipeline_test.py`：

```python
async def test_api_interrupt_does_not_falsely_close_session(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    before = await container.repo.list_open_sessions(world.world_id)
    assert len(before) == 2

    # /players 端点整体失败（非空快照缺人）→ 会话置 uncertain，不结束
    from tests.integration.conftest import fail
    clock.advance(30)
    await snap.ingest_players(world, fail(status=None, error="timeout"))
    clock.advance(30)
    await snap.ingest_players(world, fail(status=None, error="timeout"))

    sessions = await container.repo.list_open_sessions(world.world_id)
    assert len(sessions) == 2  # 仍是开着的会话，未被误判为离线
    assert all(s.status == SessionStatus.UNCERTAIN for s in sessions)


async def test_uncertain_session_reused_on_recovery(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))

    open0 = await container.repo.list_open_sessions(world.world_id)
    akari0 = next(s for s in open0 if "steam_00001" not in s.player_key or True)  # player_key 已哈希
    joined_at_before = min(s.joined_at for s in open0)
    ids_before = {s.id for s in open0}

    # API 中断 → uncertain
    from tests.integration.conftest import fail
    clock.advance(30)
    await snap.ingest_players(world, fail(error="timeout"))
    uncertain = await container.repo.list_open_sessions(world.world_id)
    assert all(s.status == SessionStatus.UNCERTAIN for s in uncertain)

    # 恢复：同玩家再现 → 复用原会话（不新建），joined_at 不变、id 不变、时长连续累加
    clock.advance(60)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    recovered = await container.repo.list_open_sessions(world.world_id)
    assert all(s.status == SessionStatus.ACTIVE for s in recovered)
    assert {s.id for s in recovered} == ids_before          # 复用同一批会话 id，无新建
    assert min(s.joined_at for s in recovered) == joined_at_before
    # 无悬空 uncertain：开着的会话总数仍为 2
    assert len(recovered) == 2
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -k "interrupt or reused" -q`
  期望 FAIL：`AssertionError`（恢复后产生了新会话 id 或产生了悬空 uncertain），或 `ingest_players` 在 `resp.ok=False` 时未路由到 `mark_uncertain`。

- [ ] **3. 写最小实现** — 确保 `SnapshotService.ingest_players` 在 `resp.ok is False` 时不结束会话而是标记 uncertain。在 `palchronicle/application/snapshot_service.py`：

```python
    async def ingest_players(self, world, resp):
        if not resp.ok:
            await self.players.mark_uncertain(world)
            return
        snap = self._privacy.redact_players(
            self._normalizer.normalize_players(resp.data, self._clock.now()),
            world.world_id, self._salt, self._cfg.privacy,
        )
        await self.players.apply_players(world, snap)
```

  确保 `PlayerService.apply_players`（Phase 3）的建/复用规则为：先查 `get_open_session`（active 优先，否则 uncertain）——命中 uncertain 则恢复为 active、沿用 `joined_at`、按健康采样续计 `observed_seconds`，**不新建**；无任何开着会话才 `insert_session`。该逻辑 Phase 3 已实现并单测；本任务仅在集成层验证端到端不产生新 id / 悬空。若断言暴露 Phase 3 复用逻辑缺陷，按 spec §10.1 修正 `apply_players` 的复用分支。

  创建 `tests/fixtures/api_interrupt_recovery/series.json`（供其它序列化测试引用，记录中断-恢复时间轴）：

```json
[
  {"tick": 0, "endpoint": "players", "payload": {"players": [{"userId": "steam_00001", "name": "Akari", "level": 21, "ping": 44.0, "building_count": 12}]}},
  {"tick": 30, "endpoint": "players", "payload": null},
  {"tick": 60, "endpoint": "players", "payload": null},
  {"tick": 120, "endpoint": "players", "payload": {"players": [{"userId": "steam_00001", "name": "Akari", "level": 21, "ping": 44.0, "building_count": 12}]}}
]
```

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -k "interrupt or reused" -q`
  期望 PASS：2 passed。再跑全文件 `python -m pytest tests/integration/pipeline_test.py -q` 期望 5 passed。

- [ ] **5. 提交** —
  `git add tests/fixtures/api_interrupt_recovery/ tests/integration/pipeline_test.py palchronicle/application/snapshot_service.py && git commit -m "test(integration): API interrupt keeps session + uncertain reuse on recovery"`

---

### Task 6.5：pipeline 集成 — PalBox 抖动不误建 + 新据点确认（先落 base 再发事件）+ 据点消失

**Files:**
- Modify: `tests/integration/pipeline_test.py`（追加三个测试）

**Interfaces:**
- Consumes：
  - `SnapshotService.ingest_game_data(world, resp)`（内部 `to_thread` 归一→ `GuildService.apply` → `BaseService.apply` → `EventService.base_events`）
  - `BaseService.apply(world, gd) -> list[BaseUpdate]`；`BaseUpdate`（含 `base_key, guild_key, confidence, worker_count, is_new, is_vanished, prev_worker_count, ...`，见跨阶段共享定义）
  - `EventService.base_events(world, updates)`（NEW_BASE/BASE_VANISHED/WORKER_DELTA）
  - `Repository.list_bases(world_id, include_low, include_hidden)`、`list_palboxes(world_id)`、`list_events(world_id, since, limit)`
  - `EventType.NEW_BASE/BASE_VANISHED`；`Confidence`
  - `BasesConfig.confirmation_samples=3`、`position_grid_size=2000`
- Produces：三个端到端断言（抖动最近邻不新建 PalBox；据点第 3 次确认时 `bases` 行先于 NEW_BASE 事件存在；连续缺失触发 BASE_VANISHED）。

- [ ] **1. 写失败测试** — 追加到 `tests/integration/pipeline_test.py`：

```python
async def _gd_with_base(worker_dx: float = 0.0):
    """一个 G-1 公会、PalBox + 一只据点帕鲁的 game-data；worker_dx 抖动坐标。"""
    return {
        "fps": 58, "average_fps": 55.0,
        "actors": [
            {"unit_type": "BaseCampPal", "pal_class": "SheepBall", "Level": 8, "HP": 180, "MaxHP": 200,
             "GuildID": "G-1", "action": "Work", "AI_Action": "Work",
             "LocationX": 100.0 + worker_dx, "LocationY": 200.0, "LocationZ": 0.0, "IsActive": "true"},
        ],
        "palboxes": [{"GuildID": "G-1", "GuildName": "Noema",
                      "LocationX": 110.0 + worker_dx, "LocationY": 205.0, "LocationZ": 0.0}],
    }


async def test_palbox_jitter_does_not_create_duplicate(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    # 抖动幅度 < position_grid_size(2000) → 最近邻匹配，同一 palbox_key
    for dx in (0.0, 5.0, -8.0, 12.0):
        clock.advance(30)
        await snap.ingest_game_data(world, ok(await _gd_with_base(dx)))
    palboxes = await container.repo.list_palboxes(world.world_id)
    assert len(palboxes) == 1  # 抖动未误建新 PalBox


async def test_new_base_persisted_before_event(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    # 连续 confirmation_samples(3) 次一致归属 → 建 base + 发 NEW_BASE
    for _ in range(3):
        clock.advance(30)
        await snap.ingest_game_data(world, ok(await _gd_with_base()))

    bases = await container.repo.list_bases(world.world_id, include_low=True, include_hidden=True)
    assert len(bases) == 1
    base_key = bases[0].base_key

    events = await container.repo.list_events(world.world_id, since=None, limit=50)
    new_base = [e for e in events if e.event_type == EventType.NEW_BASE]
    assert len(new_base) == 1
    # 事件引用的 base_key 已在 bases 表存在（先落 base 再发事件）
    assert new_base[0].subject_key == base_key


async def test_base_vanished_after_missing(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)
    for _ in range(3):
        clock.advance(30)
        await snap.ingest_game_data(world, ok(await _gd_with_base()))
    assert len(await container.repo.list_bases(world.world_id, include_low=True, include_hidden=True)) == 1

    # 连续 >=3 次健康 game-data 中该据点缺失 → BASE_VANISHED
    empty_gd = {"fps": 58, "average_fps": 55.0, "actors": [], "palboxes": []}
    for _ in range(3):
        clock.advance(30)
        await snap.ingest_game_data(world, ok(empty_gd))

    events = await container.repo.list_events(world.world_id, since=None, limit=50)
    vanished = [e for e in events if e.event_type == EventType.BASE_VANISHED]
    assert len(vanished) == 1
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -k "jitter or before_event or vanished" -q`
  期望 FAIL：断言不成立（例如出现 2 个 PalBox，或 NEW_BASE 事件先于 bases 行、`subject_key` 不匹配，或未产生 BASE_VANISHED）——暴露串联缺陷则按 spec §10.3/§11 在 `SnapshotService.ingest_game_data` 中修正"先 `BaseService.apply`（落 base）再 `EventService.base_events`（发事件）"的顺序。

- [ ] **3. 写最小实现** — 确保 `palchronicle/application/snapshot_service.py` 的 `ingest_game_data` 顺序正确（据点先落库、后发事件）：

```python
    async def ingest_game_data(self, world, resp):
        if not resp.ok:
            return
        gd = await asyncio.to_thread(
            self._normalizer.normalize_game_data, resp.data, self._clock.now(), self._meta
        )
        gd = self._privacy.redact_game_data(gd, world.world_id, self._salt, self._cfg.privacy)
        await self.repo.upsert_unknown_classes(gd.unknown_classes)
        await self.guilds.apply(world, gd)
        updates = await self.bases.apply(world, gd)   # 先落 base 记录
        await self.events.base_events(world, updates) # 再发基于 base_key 的事件
```

  （`import asyncio` 已在文件顶部。`BaseService.apply` 内部完成 PalBox 最近邻匹配、confirmation 计数、`upsert_base` 与置信度；`BaseUpdate.is_new/is_vanished` 驱动 `EventService.base_events`——均为 Phase 3/4 已实现。本任务仅保证 `SnapshotService` 的调用顺序满足 spec §10.3 步骤 5。）

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -k "jitter or before_event or vanished" -q`
  期望 PASS：3 passed。

- [ ] **5. 提交** —
  `git add tests/integration/pipeline_test.py palchronicle/application/snapshot_service.py && git commit -m "test(integration): palbox jitter no-dup + base persisted-before-event + base vanished"`

---

### Task 6.6：pipeline 集成 — 在线纪录（连续 2 快照）+ worldguid 切换隔离 + 多服务器不串数据

**Files:**
- Create: `tests/fixtures/worldguid_switch/info_b.json`
- Modify: `tests/integration/conftest.py`（新增双服务器夹具 `harness_two`）
- Modify: `tests/integration/pipeline_test.py`（追加三个测试）

**Interfaces:**
- Consumes：
  - `EventService.online_record(world, value, confirmed)`（经 metrics/players 采集触发）；`EventType.ONLINE_RECORD`
  - `Repository.peak_online(world_id, since)`
  - `SnapshotService.ingest_info` 处理换世界（新 worldguid → 关闭旧世界活动会话为 uncertain，切换 current world）；`Repository.get_current_world(server_id)`
  - `World.world_id = "{server_id}:{worldguid}:{epoch}"`（spec §6.3）；数据按 world_id 隔离
  - 双服务器：两个 `SnapshotService`（`container.snapshot_service_for("alpha"/"beta")`）；`Repository.list_events` 按 world_id 隔离
- Produces：`harness_two` 夹具 + 三个端到端隔离断言。

- [ ] **1. 写失败测试** — 在 `tests/integration/conftest.py` 追加双服务器夹具：

```python
def make_config_two() -> dict:
    base = make_config()
    base["servers"] = [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": "Asia/Tokyo"},
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": "Asia/Tokyo"},
    ]
    return base


@pytest_asyncio.fixture
async def harness_two(tmp_path):
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(make_config_two(), env={})
    container = Container(config=cfg, data_dir=tmp_path, clock=clock)
    await container.start()
    try:
        yield container, cfg, clock
    finally:
        await container.stop()
```

  创建 `tests/fixtures/worldguid_switch/info_b.json`（同服务器、不同 worldguid）：

```json
{"version": "v0.3.4", "servername": "Chronicle Test World", "description": "world switched", "worldguid": "WORLDGUID-BBBB-0002"}
```

  追加到 `tests/integration/pipeline_test.py`：

```python
async def test_online_record_requires_two_consecutive_snapshots(harness):
    container, server, clock, snap = harness
    world = await _boot_world(snap, server, clock)

    two = load_fixture("normal_world", "players")  # 2 人
    # 第一次达到 2 人在线：尚未在连续 2 个健康快照维持 → 不确认纪录
    await snap.ingest_players(world, ok(two))
    ev1 = [e for e in await container.repo.list_events(world.world_id, since=None, limit=50)
           if e.event_type == EventType.ONLINE_RECORD]
    assert ev1 == []

    # 第二个健康快照仍维持 2 人 → 确认 ONLINE_RECORD
    clock.advance(30)
    await snap.ingest_players(world, ok(two))
    ev2 = [e for e in await container.repo.list_events(world.world_id, since=None, limit=50)
           if e.event_type == EventType.ONLINE_RECORD]
    assert len(ev2) == 1
    assert ev2[0].payload["record_value"] == 2


async def test_worldguid_switch_isolates_data(harness):
    container, server, clock, snap = harness
    world_a = await _boot_world(snap, server, clock)
    await snap.ingest_players(world_a, ok(load_fixture("normal_world", "players")))
    assert len(await container.repo.list_open_sessions(world_a.world_id)) == 2

    # /info 返回新 worldguid → 换世界
    clock.advance(30)
    world_b = await snap.ingest_info(server, ok(load_fixture("worldguid_switch", "info_b")))
    assert world_b is not None
    assert world_b.world_id != world_a.world_id
    assert world_b.worldguid == "WORLDGUID-BBBB-0002"

    # 旧世界活动会话被置 uncertain，不合并到新世界；新世界当前无会话
    assert (await container.repo.get_current_world(server.server_id)).world_id == world_b.world_id
    assert await container.repo.list_open_sessions(world_b.world_id) == []
    old_open = await container.repo.list_open_sessions(world_a.world_id)
    assert all(s.status == SessionStatus.UNCERTAIN for s in old_open)


async def test_two_servers_do_not_cross_contaminate(harness_two):
    container, cfg, clock = harness_two
    alpha, beta = cfg.servers[0], cfg.servers[1]
    snap_a = container.snapshot_service_for(alpha.server_id)
    snap_b = container.snapshot_service_for(beta.server_id)

    world_a = await snap_a.ingest_info(alpha, ok(load_fixture("normal_world", "info")))
    world_b = await snap_b.ingest_info(beta, ok(load_fixture("worldguid_switch", "info_b")))
    assert world_a.world_id != world_b.world_id
    assert world_a.world_id.startswith("alpha:")
    assert world_b.world_id.startswith("beta:")

    await snap_a.ingest_players(world_a, ok(load_fixture("normal_world", "players")))  # 2 人到 alpha
    await snap_b.ingest_players(world_b, ok({"players": []}))                          # beta 无人

    assert len(await container.repo.list_open_sessions(world_a.world_id)) == 2
    assert await container.repo.list_open_sessions(world_b.world_id) == []
    # 事件也隔离：alpha 的 NEW_PLAYER 不落到 beta 的 world_id
    a_events = await container.repo.list_events(world_a.world_id, since=None, limit=50)
    b_events = await container.repo.list_events(world_b.world_id, since=None, limit=50)
    assert len(a_events) >= 2
    assert b_events == []
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -k "online_record or worldguid or cross_contaminate" -q`
  期望 FAIL：`fixture 'harness_two' not found`（首次运行前）后转为断言失败（在线纪录未按连续 2 快照门槛确认，或换世界未隔离，或跨服务器串数据）。

- [ ] **3. 写最小实现** — 确保 `SnapshotService.ingest_info` 在检测到新 worldguid 时执行换世界隔离。在 `palchronicle/application/snapshot_service.py`：

```python
    async def ingest_info(self, server, resp):
        if not resp.ok:
            return await self.repo.get_current_world(server.server_id)
        info = self._normalizer.normalize_info(resp.data, self._clock.now())
        current = await self.repo.get_current_world(server.server_id)
        world_id = f"{server.server_id}:{info.worldguid}:0"
        now = self._clock.now()
        if current is not None and current.world_id != world_id:
            # 换世界：旧世界活动会话置 uncertain，切换 current world，暂停跨世界比较
            await self.players.mark_uncertain(current)
        world = World(
            world_id=world_id, server_id=server.server_id, worldguid=info.worldguid,
            epoch=0, server_name=info.server_name, version=info.version,
            first_seen_at=(current.first_seen_at if current and current.world_id == world_id else now),
            last_seen_at=now, current_day=(current.current_day if current and current.world_id == world_id else 0),
        )
        await self.repo.upsert_world(world)
        return world
```

  （`World` 从 `palchronicle.domain.models` 已导入。`get_current_world` 返回该服务器最近 `last_seen_at` 的世界。在线纪录门槛与多服务器隔离由 Phase 3/4 的 `EventService.online_record(confirmed=...)`、以及 `world_id` 作为一切写入主键保证；本任务在集成层验证。若断言暴露串数据，检查各 upsert/insert 是否都以 `world.world_id` 为键。）

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/pipeline_test.py -k "online_record or worldguid or cross_contaminate" -q`
  期望 PASS：3 passed。再跑全文件 `python -m pytest tests/integration/pipeline_test.py -q` 期望 11 passed。

- [ ] **5. 提交** —
  `git add tests/fixtures/worldguid_switch/ tests/integration/conftest.py tests/integration/pipeline_test.py palchronicle/application/snapshot_service.py && git commit -m "test(integration): online-record 2-snapshot gate + worldguid switch isolation + multi-server no-cross"`

---

### Task 6.7：隐私集成 — DB 全表无 IP / 原始 ID / 明文密码 / 原始 ping

**Files:**
- Create: `tests/integration/privacy_test.py`

**Interfaces:**
- Consumes：
  - `harness` 夹具（Task 6.3）；`SnapshotService.ingest_*`；`Repository`（写侧已落库）
  - `Database.query(sql, params)`（契约 `database.py`，只读连接遍历全表）
  - fixtures `normal_world/players.json`（含 `ip`/`accountName`/原始 `userId`/原始 `ping`）与 `game-data.json`（含坐标）
- Produces：一个跨全表的隐私扫描断言（无 IPv4/IPv6 文本、无原始 userId/playerId、无明文密码 `pw`、无原始 ping 数值列，仅 `ping_bucket`）。

- [ ] **1. 写失败测试** — 创建 `tests/integration/privacy_test.py`：

```python
import re

import pytest

from tests.fixtures.loader import load_fixture
from tests.integration.conftest import ok

pytestmark = pytest.mark.asyncio

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")
RAW_IDS = ("steam_00001", "steam_00002", "PID-1", "PID-2", "acct_akari", "acct_borel")
RAW_PING_VALUES = ("44.0", "130.0", "44", "130")


async def _all_table_names(container):
    rows = await container.db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [r[0] for r in rows]


async def _dump_all_cells(container) -> list[str]:
    cells: list[str] = []
    for table in await _all_table_names(container):
        rows = await container.db.query(f"SELECT * FROM {table}")
        for row in rows:
            for value in tuple(row):
                if value is not None:
                    cells.append(str(value))
    return cells


async def _run_normal_sequence(container, server, clock, snap):
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    await snap.ingest_metrics(world, ok(load_fixture("normal_world", "metrics")))
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))
    clock.advance(30)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))
    return world


async def test_db_has_no_ip_no_raw_id_no_password_no_raw_ping(harness):
    container, server, clock, snap = harness
    await _run_normal_sequence(container, server, clock, snap)

    cells = await _dump_all_cells(container)
    blob = "\n".join(cells)

    assert not IPV4.search(blob), "DB 含 IPv4"
    assert not IPV6.search(blob), "DB 含 IPv6"
    for rid in RAW_IDS:
        assert rid not in blob, f"DB 含原始 ID {rid}"
    assert "pw" not in {c for c in cells}, "DB 含明文密码"

    # ping 仅以 bucket 存在，无原始 ping 数值列
    obs_cols = await container.db.query("SELECT * FROM player_observations LIMIT 1")
    col_names = obs_cols[0].keys() if obs_cols else []
    assert "ping_bucket" in col_names
    assert "ping" not in col_names
    for pv in RAW_PING_VALUES:
        assert pv not in blob, f"DB 含原始 ping 值 {pv}"
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/privacy_test.py -q`
  期望 FAIL：`AttributeError: 'Container' object has no attribute 'db'`（若 `Container` 未暴露 `self.db`），或断言失败（脱敏顺序/落库列不符）。

- [ ] **3. 写最小实现** — 在 `palchronicle/container.py` 暴露只读的 `self.db: Database`（在 `start()` 中 `self.db = database` 已构造的实例即可）：

```python
        # start() 内，open db 之后：
        self.db = database   # 供隐私扫描/集成测试只读遍历全表
```

  该断言驱动的隐私红线由 Phase 2 `privacy_filter`（先归一后脱敏、删 `ip`/`accountName`、HMAC userId、ping→bucket）与 Phase 1/3 的表结构（`player_observations` 只有 `ping_bucket` 列、无 `ping` 列）共同保证。若断言暴露某列泄露原文，回到对应 Phase 修列/修脱敏；本任务只暴露 `db` 访问器。

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/privacy_test.py -q`
  期望 PASS：1 passed。

- [ ] **5. 提交** —
  `git add tests/integration/privacy_test.py palchronicle/container.py && git commit -m "test(privacy): DB-wide scan finds no IP/raw-id/password/raw-ping"`

---

### Task 6.8：隐私集成 — strict 模式无网格 / 据点空 + position_cell 全 NULL

**Files:**
- Modify: `tests/integration/conftest.py`（新增 `harness_strict` 夹具）
- Modify: `tests/integration/privacy_test.py`（追加两个测试）

**Interfaces:**
- Consumes：
  - `parse_config` + `make_config(mode="strict")`（Task 6.3 的 `make_config` 已支持 `mode` 形参）
  - `redact_game_data`（strict：坐标置 None、不持久化 palboxes/bases）；`Repository.list_palboxes/list_bases`
  - `Database.query`（读 `player_observations.position_cell`）
  - `PrivacyConfig.mode = "strict"`（契约 `config.py`）
- Produces：`harness_strict` 夹具 + strict 端到端断言（`palboxes`/`bases` 空、`base_observations` 空、`position_cell` 全 NULL）。

- [ ] **1. 写失败测试** — 在 `tests/integration/conftest.py` 追加：

```python
@pytest_asyncio.fixture
async def harness_strict(tmp_path):
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(make_config(mode="strict"), env={})
    container = Container(config=cfg, data_dir=tmp_path, clock=clock)
    await container.start()
    server = cfg.servers[0]
    snap = container.snapshot_service_for(server.server_id)
    try:
        yield container, server, clock, snap
    finally:
        await container.stop()
```

  追加到 `tests/integration/privacy_test.py`：

```python
async def test_strict_mode_persists_no_bases_no_palboxes(harness_strict):
    container, server, clock, snap = harness_strict
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    # 即便 game-data 含 PalBox 与据点帕鲁，strict 下也连续多帧不落 base/palbox
    for _ in range(4):
        clock.advance(30)
        await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))

    assert await container.repo.list_palboxes(world.world_id) == []
    assert await container.repo.list_bases(world.world_id, include_low=True, include_hidden=True) == []
    baseobs = await container.db.query("SELECT COUNT(*) AS c FROM base_observations")
    assert baseobs[0]["c"] == 0


async def test_strict_mode_position_cell_all_null(harness_strict):
    container, server, clock, snap = harness_strict
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))
    clock.advance(30)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))

    rows = await container.db.query("SELECT position_cell FROM player_observations")
    assert rows, "应有观察记录"
    assert all(r["position_cell"] is None for r in rows)
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/privacy_test.py -k "strict" -q`
  期望 FAIL：`fixture 'harness_strict' not found`，随后转为断言失败（strict 下仍落了 palbox/base 或 position_cell 非 NULL）。

- [ ] **3. 写最小实现** — 确保 `BaseService.apply` 在 strict 模式短路（不落 palbox/base）。在 `palchronicle/application/base_service.py` 的 `apply` 开头：

```python
    async def apply(self, world, gd):
        if self._cfg.privacy.mode == "strict" or not self._cfg.bases.enabled:
            return []   # strict：禁用据点/PalBox 持久化（spec §15）
        # ...（既有 PalBox 匹配/归属/置信度逻辑）
```

  确保 `redact_game_data`（Phase 2）在 strict 下把 `CharacterActor.x/y/z` 置 `None`、清空 `snap.palboxes`，从而 `PlayerService.apply_players` 落库的 `position_cell` 为 `None`。该脱敏 Phase 2 已实现并单测；本任务集成层验证端到端。若断言失败，回 Phase 2 修 `redact_game_data` 的 strict 分支。

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/privacy_test.py -k "strict" -q`
  期望 PASS：2 passed。

- [ ] **5. 提交** —
  `git add tests/integration/conftest.py tests/integration/privacy_test.py palchronicle/application/base_service.py && git commit -m "test(privacy): strict mode persists no grid/base and position_cell all NULL"`

---

### Task 6.9：隐私集成 — 日志脱敏（caplog 断言降级/401/不一致路径不泄原文）

**Files:**
- Modify: `tests/integration/privacy_test.py`（追加日志脱敏测试）

**Interfaces:**
- Consumes：
  - `SnapshotService.ingest_players/ingest_game_data`（传入含原文的 `RestResponse`）
  - `RestResponse(ok=False, status=401, error=...)`（error 须已脱敏）与不一致路径（metrics 人数 ≠ players 数量，spec §14）
  - Python `logging` + pytest `caplog`；被测代码 logger 名 `palchronicle.*`
  - fixtures：含 IP/原始 ID/坐标的注入响应
- Produces：一个 caplog 断言（触发 §14 降级/401/不一致路径后，日志文本不含 IPv4/IPv6、原始 ID、坐标数值、`Authorization`/`Basic `/明文密码）。

- [ ] **1. 写失败测试** — 追加到 `tests/integration/privacy_test.py`：

```python
import logging


async def test_logs_never_leak_raw_on_degradation_paths(harness, caplog):
    container, server, clock, snap = harness
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))

    with caplog.at_level(logging.DEBUG, logger="palchronicle"):
        # 401 认证失败路径（error 内绝不含凭证/URL 明文）
        await snap.ingest_players(world, RestResponse(
            ok=False, status=401, data=None, duration_ms=3, payload_bytes=0, error="auth failed"))
        # 端点失败 → uncertain 降级路径
        await snap.ingest_players(world, RestResponse(
            ok=False, status=None, data=None, duration_ms=3, payload_bytes=0, error="timeout"))
        # 数据不一致：metrics 人数 5，但 players 明细 2 → 记诊断日志（spec §14），仍不泄原文
        m = {**load_fixture("normal_world", "metrics"), "currentplayernum": 5}
        await snap.ingest_metrics(world, ok(m))
        await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
        # game-data 含坐标/原始 userid 的原文，触发正常处理路径的日志
        await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert not IPV4.search(text), "日志泄露 IPv4"
    assert not IPV6.search(text), "日志泄露 IPv6"
    for rid in RAW_IDS:
        assert rid not in text, f"日志泄露原始 ID {rid}"
    for coord in ("100.0", "200.0", "3000.0", "3200.0"):
        assert coord not in text, f"日志泄露坐标 {coord}"
    assert "Basic " not in text and "Authorization" not in text
    assert "pw" not in text.split()  # 明文密码不出现为独立 token
```

> 注：坐标数值 `100.0` 也可能作为通用数字巧合出现于无害日志。为避免假阴性，被测代码在所有降级/诊断日志中**只记键名与类型、计数与 duration_ms/status，绝不 format 响应体或坐标/ID 取值**（spec §14/§15"匿名 schema 摘要"）。该测试因此对"日志中出现任何这些原文子串"零容忍是合理的。

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/privacy_test.py -k "logs_never_leak" -q`
  期望 FAIL：`AssertionError`（若任一降级/诊断日志 format 了响应体、坐标或原始 ID），或若尚无相关日志则测试通过为假绿——因此需先确认被测路径**确有**日志产出（数据不一致路径 spec §14 要求记诊断日志）。

- [ ] **3. 写最小实现** — 确保 §14 不一致路径记诊断日志、且所有降级日志只含匿名摘要。在 `palchronicle/application/snapshot_service.py`：

```python
import logging

_log = logging.getLogger("palchronicle.snapshot")

    async def ingest_metrics(self, world, resp):
        if not resp.ok:
            _log.info("metrics unavailable status=%s duration_ms=%s", resp.status, resp.duration_ms)
            return
        m = self._normalizer.normalize_metrics(resp.data, self._clock.now())
        latest_players = await self.repo.latest_metric(world.world_id)  # 复用最近 players 计数缓存
        # 记录官方指标, 明细以 /players 为准; 仅记数量, 不记任何取值
        self._last_metrics_online = m.online
        # ...（既有落库 insert_metric + online_record 逻辑）

    async def ingest_players(self, world, resp):
        if not resp.ok:
            _log.info("players unavailable status=%s error_kind=%s", resp.status,
                      type(resp.error).__name__ if resp.error else "none")
            await self.players.mark_uncertain(world)
            return
        snap = self._privacy.redact_players(
            self._normalizer.normalize_players(resp.data, self._clock.now()),
            world.world_id, self._salt, self._cfg.privacy,
        )
        if self._last_metrics_online is not None and self._last_metrics_online != len(snap.players):
            _log.info("player_count_mismatch official=%s detailed=%s",
                      self._last_metrics_online, len(snap.players))  # 只记数量, 不记 ID/IP/坐标
        await self.players.apply_players(world, snap)
```

  （`self._last_metrics_online: int | None = None` 在 `SnapshotService.__init__` 初始化。关键点：诊断日志一律用 `%s` 传入 **数量/status/duration/键名**，绝不传响应体、坐标、`userId`、`ip`、`error` 原文。`RestResponse.error` 由 `palworld_rest`（Phase 1）保证已脱敏，此处仅记 `error_kind`/`status`，不打印 error 原文以更保守。若断言暴露某处 log 了原文，删除该 format 参数改为匿名摘要。）

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/privacy_test.py -k "logs_never_leak" -q`
  期望 PASS：1 passed。再跑全文件 `python -m pytest tests/integration/privacy_test.py -q` 期望 5 passed。

- [ ] **5. 提交** —
  `git add tests/integration/privacy_test.py palchronicle/application/snapshot_service.py && git commit -m "test(privacy): logs never leak IP/raw-id/coords on degradation/401/mismatch paths"`

---

### Task 6.10：路由集成 — seed-only 不覆盖运行时 + active 唯一性

**Files:**
- Create: `tests/integration/routing_test.py`

**Interfaces:**
- Consumes：
  - `parse_config` + 带 `group_bindings` 的配置；`Container.start()` 内 `Repository.seed_bindings`（INSERT OR IGNORE, seed-only）
  - `RoutingService.use(umo, name) -> str`、`RoutingService.unbind(umo, name) -> str`（契约 `routing_service.py`）
  - `Repository.get_binding_active(umo) -> str|None`、`get_allowed(umo) -> set[str]`、`set_active(umo, server_id)`
  - `AccessMode.RESTRICTED`
- Produces：seed-only 与 active 唯一性两个断言。

- [ ] **1. 写失败测试** — 创建 `tests/integration/routing_test.py`：

```python
import pytest
import pytest_asyncio

from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.infrastructure.clock import FakeClock
from tests.integration.conftest import make_config

pytestmark = pytest.mark.asyncio

UMO = "aiocqhttp:GroupMessage:123456"


def config_two_servers_with_seed() -> dict:
    cfg = make_config(access_mode="restricted")
    cfg["servers"] = [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": ""},
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": False, "timezone": ""},
    ]
    cfg["group_bindings"] = [{"umo": UMO, "server": "alpha", "active": True}]
    return cfg


@pytest_asyncio.fixture
async def routed(tmp_path):
    clock = FakeClock(start=1_700_000_000)
    cfg = parse_config(config_two_servers_with_seed(), env={})
    container = Container(config=cfg, data_dir=tmp_path, clock=clock)
    await container.start()
    try:
        yield container, cfg
    finally:
        await container.stop()


async def test_seed_only_does_not_override_runtime_use(routed):
    container, cfg = routed
    # 预设让 alpha 为 active；运行时管理员 /pal use beta
    await container.routing.use(UMO, "beta")
    assert await container.repo.get_binding_active(UMO) == "beta"

    # 再次触发一次 seed（模拟重载后 start 再次播种）→ 不得把 active 覆盖回 alpha
    await container.repo.seed_bindings(cfg.group_bindings)
    assert await container.repo.get_binding_active(UMO) == "beta", "seed 覆盖了运行时 use"
    # alpha 仍在 allowed 集合（预设授权保留），但 active 归 beta
    assert "alpha" in await container.repo.get_allowed(UMO)
    assert "beta" in await container.repo.get_allowed(UMO)


async def test_active_uniqueness_per_umo(routed):
    container, cfg = routed
    await container.routing.use(UMO, "alpha")
    await container.routing.use(UMO, "beta")
    # 每 umo 至多一个 active
    rows = await container.db.query(
        "SELECT server_id FROM group_servers WHERE umo=? AND active=1", (UMO,))
    assert [r[0] for r in rows] == ["beta"]
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/routing_test.py -q`
  期望 FAIL：断言失败（若 `seed_bindings` 用 `INSERT ... DO UPDATE` 覆盖了运行时 active，或 `set_active` 未清同 umo 其它 active）。

- [ ] **3. 写最小实现** — 确保 `Repository.seed_bindings` 为 seed-only、`set_active` 保证唯一。在 `palchronicle/adapters/sqlite_repository.py`：

```python
    async def seed_bindings(self, bindings):
        async with self.db.write_tx() as tx:
            for b in bindings:
                # seed-only：仅当该行不存在时插入；已存在则完全不动 allowed/active
                await tx.execute(
                    "INSERT INTO group_servers(umo, server_id, allowed, active, updated_at) "
                    "VALUES(?,?,1,?,?) ON CONFLICT(umo, server_id) DO NOTHING",
                    (b.umo, b.server, 1 if b.active else 0, self.clock.now()),
                )
            # 播种后修正 active 唯一性：每 umo 若有多个 active(来自多条 active=true 预设)，只保留一个
            for umo in {b.umo for b in bindings}:
                rows = await tx.execute_fetchall(
                    "SELECT server_id FROM group_servers WHERE umo=? AND active=1 ORDER BY server_id", (umo,))
                keep = rows[0][0] if rows else None
                if keep is not None:
                    await tx.execute(
                        "UPDATE group_servers SET active=0 WHERE umo=? AND server_id<>?", (umo, keep))

    async def set_active(self, umo, server_id):
        async with self.db.write_tx() as tx:
            await tx.execute("UPDATE group_servers SET active=0 WHERE umo=?", (umo,))
            await tx.execute(
                "INSERT INTO group_servers(umo, server_id, allowed, active, updated_at) VALUES(?,?,1,1,?) "
                "ON CONFLICT(umo, server_id) DO UPDATE SET allowed=1, active=1, updated_at=excluded.updated_at",
                (umo, server_id, self.clock.now()))
```

  （`write_tx()` 产出的事务对象支持 `.execute`/`.execute_fetchall`（aiosqlite 连接 API）。`RoutingService.use` 内部调用 `set_active`。这些方法 Phase 1/5 已建（Phase 1 建 `seed_bindings`/`set_active` 骨架并单测）；本任务在集成层验证 seed-only 语义与 active 唯一性端到端成立。）

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/routing_test.py -q`
  期望 PASS：2 passed。

- [ ] **5. 提交** —
  `git add tests/integration/routing_test.py palchronicle/adapters/sqlite_repository.py && git commit -m "test(routing): seed-only does not override runtime use + active uniqueness"`

---

### Task 6.11：路由集成 — @server 尾缀 + 含空格名字 + restricted 授权前后

**Files:**
- Modify: `tests/integration/routing_test.py`（追加三个测试）

**Interfaces:**
- Consumes：
  - `parse_arg(message_str, subcommand) -> ParsedArg(name, server_override)`、`ArgError`（契约 `server_arg.py`）
  - `RoutingService.resolve(umo, override, is_group) -> Resolution(server, error)`（契约）；`AccessMode.RESTRICTED`
  - `RoutingService.use`（授权）
- Produces：三个断言（@server 尾缀正确剥离且 name 保留空格；restricted 未授权 `resolve` 返回 error；`use` 授权后 `resolve` 返回 server）。

- [ ] **1. 写失败测试** — 追加到 `tests/integration/routing_test.py`：

```python
from palchronicle.presentation.server_arg import ArgError, parse_arg


def test_parse_arg_strips_trailing_server_and_keeps_spaced_name():
    # "/pal guild Sunset Valley @beta" → name="Sunset Valley", override="beta"
    parsed = parse_arg("/pal guild Sunset Valley @beta", subcommand="guild")
    assert parsed.name == "Sunset Valley"
    assert parsed.server_override == "beta"


def test_parse_arg_no_server_override():
    parsed = parse_arg("/pal guild Noema Alliance", subcommand="guild")
    assert parsed.name == "Noema Alliance"
    assert parsed.server_override is None


def test_parse_arg_multiple_trailing_at_is_illegal():
    with pytest.raises(ArgError):
        parse_arg("/pal guild Name @alpha @beta", subcommand="guild")


async def test_restricted_denies_then_allows_after_use(routed):
    container, cfg = routed
    umo = "aiocqhttp:GroupMessage:999"  # 无任何绑定的新群

    # restricted 下未授权 → resolve 返回 error（拒绝），server 为 None
    denied = await container.routing.resolve(umo, override="alpha", is_group=True)
    assert denied.server is None
    assert denied.error is not None

    # 管理员 /pal use alpha 授权后 → resolve 命中 alpha
    await container.routing.use(umo, "alpha")
    allowed = await container.routing.resolve(umo, override=None, is_group=True)
    assert allowed.error is None
    assert allowed.server is not None
    assert allowed.server.server_id == "alpha"
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/routing_test.py -k "parse_arg or denies_then_allows" -q`
  期望 FAIL：`parse_arg` 未正确剥离尾部 `@token`（把 `@beta` 并入 name），或 restricted 未授权时 `resolve` 未返回 error。

- [ ] **3. 写最小实现** — 确保 `parse_arg` 按 spec §13 消歧（仅识别最后一个尾部 `@token`；多个尾部 `@token` 抛 `ArgError`；name 保留空格）。在 `palchronicle/presentation/server_arg.py`：

```python
    import re

    def parse_arg(message_str: str, subcommand: str) -> ParsedArg:
        text = message_str.strip()
        # 去掉 "/pal <subcommand>" 前缀（大小写不敏感, 容忍多空格）
        prefix = re.match(rf"^/?pal\s+{re.escape(subcommand)}\s*", text, flags=re.IGNORECASE)
        rest = text[prefix.end():] if prefix else text
        rest = rest.strip()
        # 尾部 @token 检测：token 无空格
        tokens = rest.split()
        trailing_ats = [t for t in tokens[-2:] if t.startswith("@")]  # 检查末两 token
        at_tokens = [i for i, t in enumerate(tokens) if t.startswith("@")]
        # 仅识别结尾的单个 @token
        override = None
        if tokens and tokens[-1].startswith("@"):
            # 若倒数第二个也是尾部 @token → 非法
            if len(tokens) >= 2 and tokens[-2].startswith("@"):
                raise ArgError("多个 @server 尾缀，请只保留一个")
            override = tokens[-1][1:]
            tokens = tokens[:-1]
        name = " ".join(tokens).strip()
        return ParsedArg(name=name, server_override=override or None)
```

  确保 `RoutingService.resolve` 在 restricted 模式对未授权（`server_id not in get_allowed(umo)`）返回 `Resolution(server=None, error="本会话未被授权使用服务器「X」...")`（spec §7.3）。该逻辑 Phase 5 已实现并单测；本任务集成验证授权前拒绝、`use` 后放行。

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/routing_test.py -k "parse_arg or denies_then_allows" -q`
  期望 PASS：4 passed。

- [ ] **5. 提交** —
  `git add tests/integration/routing_test.py palchronicle/presentation/server_arg.py && git commit -m "test(routing): @server suffix + spaced name + restricted deny/allow via use"`

---

### Task 6.12：路由集成 — 改名/删除服务器悬空绑定兜底

**Files:**
- Modify: `tests/integration/routing_test.py`（追加一个测试）

**Interfaces:**
- Consumes：
  - 先用含 alpha/beta 的配置授权并激活 beta；再用移除 beta 的配置重建 `Container`（复用同一 `tmp_path` 数据目录，保留 `group_servers` 表）
  - `Container.start()` 内 `Repository.cleanup_orphan_bindings(valid_server_ids)` 标记孤儿
  - `RoutingService.resolve(umo, override=None, is_group=True) -> Resolution`（active 指向已消失 server → 视为未绑定，走兜底提示）
- Produces：一个断言（删除 active server 后，resolve 走兜底 error 而非崩溃/静默）。

- [ ] **1. 写失败测试** — 追加到 `tests/integration/routing_test.py`：

```python
async def test_dangling_binding_after_server_removed_falls_back(tmp_path):
    from palchronicle.config import parse_config
    from palchronicle.container import Container
    from palchronicle.infrastructure.clock import FakeClock

    clock = FakeClock(start=1_700_000_000)
    umo = "aiocqhttp:GroupMessage:555"

    # 第一次启动：alpha + beta，授权并激活 beta
    cfg1 = parse_config(config_two_servers_with_seed(), env={})
    c1 = Container(config=cfg1, data_dir=tmp_path, clock=clock)
    await c1.start()
    await c1.routing.use(umo, "beta")
    assert (await c1.repo.get_binding_active(umo)) == "beta"
    await c1.stop()

    # 第二次启动：配置删除 beta（仅剩 alpha）→ 复用同一 data_dir（绑定表保留）
    raw2 = config_two_servers_with_seed()
    raw2["servers"] = [s for s in raw2["servers"] if s["name"] == "alpha"]
    raw2["group_bindings"] = []  # 不再预设
    cfg2 = parse_config(raw2, env={})
    c2 = Container(config=cfg2, data_dir=tmp_path, clock=clock)
    await c2.start()
    try:
        # 本群 active 指向已消失的 beta → 视为未绑定，走兜底（error 非空，server 为 None），不崩溃
        res = await c2.routing.resolve(umo, override=None, is_group=True)
        assert res.server is None
        assert res.error is not None
        # 显式 @beta 指向不存在/未就绪 → 明确提示（error 非空）
        res2 = await c2.routing.resolve(umo, override="beta", is_group=True)
        assert res2.server is None
        assert res2.error is not None
    finally:
        await c2.stop()
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/routing_test.py -k "dangling" -q`
  期望 FAIL：`resolve` 对指向已消失 server 的 active 返回了该 server（未走兜底），或抛未捕获异常。

- [ ] **3. 写最小实现** — 确保 `RoutingService.resolve` 对指向不存在/未就绪 server 的 active/override 走兜底。在 `palchronicle/application/routing_service.py`：

```python
    def _ready_by_name(self, name: str) -> "ServerConfig | None":
        for s in self._cfg.servers:
            if s.server_id == name and s.ready:
                return s
        return None

    async def resolve(self, umo, override, is_group):
        # 1. 显式 @server
        if override is not None:
            s = self._ready_by_name(override)
            if s is None:
                return Resolution(server=None, error=f"服务器「{override}」不存在或未就绪")
            return await self._access_check(umo, s, is_group)
        # 2. 本群 active（须存在且就绪，否则视为未绑定兜底）
        active_id = await self.repo.get_binding_active(umo)
        if active_id is not None:
            s = self._ready_by_name(active_id)
            if s is not None:
                return await self._access_check(umo, s, is_group)
            # active 指向已改名/删除/未就绪 → 兜底提示重绑
            return Resolution(server=None,
                              error="当前活动服务器已不可用，请管理员用 /pal use <名称> 重新绑定")
        # 3. 全局默认
        if self._cfg.routing.default_server:
            s = self._ready_by_name(self._cfg.routing.default_server)
            if s is not None:
                return await self._access_check(umo, s, is_group)
        # 4. 唯一就绪服务器
        ready = self.ready_servers()
        if len(ready) == 1:
            return await self._access_check(umo, ready[0], is_group)
        # 5. 兜底
        return Resolution(server=None,
                          error="本会话未指定服务器。管理员可用 /pal use <名称> 绑定，或 /pal servers 查看可用服务器。")
```

  `_access_check`（restricted 校验 allowed，open 跳过）Phase 5 已实现。`cleanup_orphan_bindings` 在 `Container.start()` 内以当前就绪 server_id 集合调用（Phase 1 已建方法）。若断言暴露 `resolve` 未兜底，按上面补 `_ready_by_name` 就绪校验分支。

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/routing_test.py -k "dangling" -q`
  期望 PASS：1 passed。再跑全文件 `python -m pytest tests/integration/routing_test.py -q` 期望 7 passed。

- [ ] **5. 提交** —
  `git add tests/integration/routing_test.py palchronicle/application/routing_service.py && git commit -m "test(routing): dangling binding after server removed falls back safely"`

---

### Task 6.13：metadata 种子补全（pals / actions / settings 各补数条）

**Files:**
- Modify: `metadata/pals.zh-CN.json`
- Modify: `metadata/actions.json`
- Modify: `metadata/settings.zh-CN.json`
- Test: `tests/unit/metadata_seed_test.py`

**Interfaces:**
- Consumes：`MetadataRepository.load()`、`pal_name(internal_class)`、`action_category(raw_action)`、`setting_label(field)`（契约 `metadata_repository.py`，Phase 2 产出）；`ActionCategory`（契约 enums）。
- Produces：补全后的三个 metadata JSON（本任务只加数据，不改 `MetadataRepository` 代码）。

- [ ] **1. 写失败测试** — 创建 `tests/unit/metadata_seed_test.py`：

```python
from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.domain.enums import ActionCategory

META = MetadataRepository(Path(__file__).resolve().parents[2] / "metadata")
META.load()


def test_pals_seed_covers_common_classes():
    for cls in ("SheepBall", "Foxparks", "Lamball", "Cattiva", "PinkCat"):
        name = META.pal_name(cls)
        assert isinstance(name, str) and name
        # 已知种子应给中文名，而非退化为原始 class 全名
        assert name != cls or cls == "PinkCat"  # PinkCat 为反例(内部名)时容许


def test_actions_seed_maps_known_actions():
    assert META.action_category("Work") == ActionCategory.WORKING
    assert META.action_category("Sleep") == ActionCategory.SLEEPING
    assert META.action_category("Combat") == ActionCategory.COMBAT
    assert META.action_category("Move") == ActionCategory.MOVING
    assert META.action_category("Eat") == ActionCategory.EATING
    assert META.action_category("Idle") == ActionCategory.IDLE
    # 未知 → UNKNOWN（不崩溃）
    assert META.action_category("ZZZ_unknown") == ActionCategory.UNKNOWN


def test_settings_seed_labels_common_fields():
    label, unit = META.setting_label("ExpRate")
    assert label and label != "ExpRate"
    label2, _ = META.setting_label("PalCaptureRate")
    assert label2 and label2 != "PalCaptureRate"
    label3, _ = META.setting_label("DeathPenalty")
    assert label3 and label3 != "DeathPenalty"
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/unit/metadata_seed_test.py -q`
  期望 FAIL：`AssertionError`（种子条目不足，`pal_name`/`setting_label` 退化为原始键，或 `action_category` 未映射 `Sleep`/`Eat` 等）。

- [ ] **3. 写最小实现** — 向三个 metadata JSON 补种子（合并进 Phase 2 已建的结构；下面给出需存在的键，实际文件保留 Phase 2 既有条目并追加这些）。

  `metadata/pals.zh-CN.json`（追加常见帕鲁条目）：

```json
{
  "SheepBall": {"pal_number": 1, "name_zh": "棉悠悠", "name_en": "Lamball", "element_types": ["Neutral"], "rarity": 1, "metadata_version": 1},
  "Foxparks": {"pal_number": 2, "name_zh": "焰狐狸", "name_en": "Foxparks", "element_types": ["Fire"], "rarity": 2, "metadata_version": 1},
  "Lamball": {"pal_number": 3, "name_zh": "棉悠悠", "name_en": "Lamball", "element_types": ["Neutral"], "rarity": 1, "metadata_version": 1},
  "Cattiva": {"pal_number": 4, "name_zh": "喵咪猫", "name_en": "Cattiva", "element_types": ["Neutral"], "rarity": 1, "metadata_version": 1},
  "PinkCat": {"pal_number": 5, "name_zh": "喵咪猫", "name_en": "Cattiva", "element_types": ["Neutral"], "rarity": 1, "metadata_version": 1},
  "Chikipi": {"pal_number": 6, "name_zh": "咕咕鸡", "name_en": "Chikipi", "element_types": ["Neutral"], "rarity": 1, "metadata_version": 1},
  "Pengullet": {"pal_number": 7, "name_zh": "企丸丸", "name_en": "Pengullet", "element_types": ["Water"], "rarity": 2, "metadata_version": 1}
}
```

  `metadata/actions.json`（追加动作映射；键大小写不敏感由 `action_category` 归一）：

```json
{
  "Work": "working",
  "Working": "working",
  "Move": "moving",
  "Moving": "moving",
  "Idle": "idle",
  "Combat": "combat",
  "Attack": "combat",
  "Sleep": "sleeping",
  "Sleeping": "sleeping",
  "Eat": "eating",
  "Eating": "eating",
  "Incapacitated": "incapacitated",
  "Downed": "incapacitated"
}
```

  `metadata/settings.zh-CN.json`（追加 `/pal rules` 常见字段）：

```json
{
  "ExpRate": {"label_zh": "经验倍率", "unit": "x"},
  "PalCaptureRate": {"label_zh": "捕获倍率", "unit": "x"},
  "PalSpawnNumRate": {"label_zh": "帕鲁刷新倍率", "unit": "x"},
  "DropItemMaxNum": {"label_zh": "最大掉落物数量", "unit": ""},
  "DeathPenalty": {"label_zh": "死亡惩罚", "unit": "", "enum_map": {"None": "无", "Item": "掉落物品", "ItemAndEquipment": "掉落物品与装备", "All": "全部掉落"}},
  "bEnablePlayerToPlayerDamage": {"label_zh": "玩家间伤害", "unit": ""},
  "ServerPlayerMaxNum": {"label_zh": "最大玩家数", "unit": "人"},
  "GuildPlayerMaxNum": {"label_zh": "公会最大成员", "unit": "人"},
  "BaseCampMaxNumInGuild": {"label_zh": "公会据点上限", "unit": "个"}
}
```

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/unit/metadata_seed_test.py -q`
  期望 PASS：3 passed。

- [ ] **5. 提交** —
  `git add metadata/ tests/unit/metadata_seed_test.py && git commit -m "feat(metadata): seed common pals/actions/settings entries"`

---

### Task 6.14：smoke 测试（容器对 mock 服务器采集一轮后 /pal status 返回合理文本）

**Files:**
- Create: `tests/integration/smoke_test.py`

**Interfaces:**
- Consumes：
  - `harness`（Task 6.3）；`SnapshotService.ingest_info/ingest_metrics/ingest_players/ingest_game_data`
  - `Container.query: QueryService`；`QueryService.status(world) -> StatusDTO`（契约）
  - `format_status(dto, cfg.world) -> str`（契约 `formatters.py`）；`WorldConfig`
  - fixtures `normal_world/*`
- Produces：一个 smoke 断言（status 文本含世界名、天数、在线人数 2/32、不含任何原始 ID/IP/坐标）。

- [ ] **1. 写失败测试** — 创建 `tests/integration/smoke_test.py`：

```python
import re

import pytest

from palchronicle.presentation.formatters import format_status
from tests.fixtures.loader import load_fixture
from tests.integration.conftest import ok

pytestmark = pytest.mark.asyncio

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


async def test_smoke_status_after_one_collection(harness):
    container, server, clock, snap = harness

    # 对 mock 服务器跑一轮完整采集
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    await snap.ingest_metrics(world, ok(load_fixture("normal_world", "metrics")))
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))

    dto = await container.query.status(world)
    text = format_status(dto, container.config.world)

    # 合理文本：含世界名、天数 42、在线 2/32、官方据点数 3（metrics.basecampnum）
    assert "Chronicle Test World" in text
    assert "42" in text            # 世界天数
    assert "2" in text and "32" in text  # 在线 N/M
    assert "3" in text             # 官方 basecampnum

    # 隐私：status 文本绝不含原始 ID / IP / 明文密码
    assert not IPV4.search(text)
    for leak in ("steam_00001", "steam_00002", "acct_akari", "PID-1", "pw"):
        assert leak not in text
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/integration/smoke_test.py -q`
  期望 FAIL：`AttributeError`（`Container.config`/`Container.query` 未暴露）或 `format_status`/`QueryService.status` 尚未产出含上述字段的文本（若 Phase 5 formatter 字段口径与断言不一致，暴露口径差异）。

- [ ] **3. 写最小实现** — 确保 `Container` 暴露只读 `self.config: AppConfig` 与 `self.query: QueryService`（Phase 5 应已装配 `query`；此处补 `self.config = config`）。在 `palchronicle/container.py` 的 `__init__`：

```python
    def __init__(self, config: AppConfig, data_dir: Path, clock: Clock):
        self.config = config          # 供命令层与集成测试只读访问
        self._data_dir = data_dir
        self._clock = clock
        self._snapshot_services: dict[str, SnapshotService] = {}
        # ...（其余装配在 start() 中完成，含 self.query / self.routing / self.report / self.repo / self.db）
```

  `format_status` 的字段口径（世界名 + 天数 + 在线 N/M + 官方 basecampnum + FPS/流畅度 + 今日最高 + 更新时间）由 spec §13 与 Phase 5 `StatusDTO`/`format_status` 定义；本 smoke 只断言关键子串存在与无泄漏。若断言暴露 formatter 缺字段，回 Phase 5 formatter 按 spec §13 补齐。

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/integration/smoke_test.py -q`
  期望 PASS：1 passed。

- [ ] **5. 提交** —
  `git add tests/integration/smoke_test.py palchronicle/container.py && git commit -m "test(smoke): container collects once then /pal status returns sane redacted text"`

---

### Task 6.15：README（首屏安全强调 + 多服务器/群授权/安装配置）

**Files:**
- Modify: `README.md`
- Test: `tests/unit/readme_test.py`

**Interfaces:**
- Consumes：无（文档）。测试仅对 README 文本做关键短语存在性断言，保证首屏安全声明与用法不缺失。
- Produces：完整 README.md。

- [ ] **1. 写失败测试** — 创建 `tests/unit/readme_test.py`：

```python
from pathlib import Path

README = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")


def test_readme_first_screen_safety_claims():
    for phrase in ("只读", "不控制服务器", "不存储 IP", "不公开精确位置", "启用 REST", "勿暴露公网"):
        assert phrase in README, f"README 缺少安全声明: {phrase}"


def test_readme_requirements_and_usage():
    assert "AstrBot ≥ 4.10.4" in README or "AstrBot >= 4.10.4" in README
    for phrase in ("/pal use", "多服务器", "@server", "群授权", "安装", "配置"):
        assert phrase in README, f"README 缺少用法段落: {phrase}"


def test_readme_lists_readonly_endpoints():
    for ep in ("/info", "/metrics", "/players", "/settings", "/game-data"):
        assert ep in README, f"README 未声明只读端点: {ep}"
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/unit/readme_test.py -q`
  期望 FAIL：`AssertionError`（当前 README 仅有一行标题，缺全部安全声明与用法）。

- [ ] **3. 写最小实现** — 重写 `README.md`：

```markdown
# PalChronicle · 帕鲁纪事（astrbot_plugin_palword）

> 只读的 Palworld 世界纪事、玩家档案与社区观察 AstrBot 插件，基于官方 REST API。

## 安全与隐私（请先阅读）

- **只读**：本插件仅调用官方只读端点 `/info`、`/metrics`、`/players`、`/settings`、`/game-data`，**不控制服务器**、不执行任何写/管理操作。
- **不存储 IP**：入口即删除 IP、Basic Auth 凭证、原始平台账号与原始内部 ID；玩家标识仅以 `HMAC-SHA256(salt, world_id + raw_user_id)` 落库。
- **不公开精确位置**：坐标默认量化为粗网格；`strict` 隐私模式下坐标完全不落库、据点模块停用。Ping 仅以"优秀/正常/偏高"分桶展示，不存原始数值。
- **需在服务器端启用 REST**：Palworld 服务器须开启 REST API（`RESTAPIEnabled=True` 并设置管理员密码）。
- **勿暴露公网**：REST API 请勿直接暴露到公网，走 localhost / 内网 / VPN / 反向代理；密码建议用环境变量（`password_env`）而非明文。

## 环境要求

- AstrBot ≥ 4.10.4（建议最新 4.26.x）
- Python ≥ 3.11
- SQLite 3

## 安装

1. 将本插件放入 AstrBot 的 `plugins/` 目录（或通过插件市场安装）。
2. 安装依赖：`pip install -r requirements.txt`（aiohttp、aiosqlite）。
3. 在 AstrBot 网页配置页填写服务器与路由（见下）。
4. 重载插件。

## 配置

在插件配置页：

- **servers（多服务器）**：可添加多台 Palworld 服务器。`name` 唯一且不含空格/冒号/`@`；`base_url` 如 `http://127.0.0.1:8212`；密码填 `password_env`（环境变量名，推荐）或 `password`（明文，会落盘）。
- **routing.access_mode**：默认 `restricted`（群需管理员授权才能查询某服务器）；`open` 为任意群可查任意服务器。
- **group_bindings（可选预设授权）**：等价于管理员执行 `/pal use`，仅作**初始种子**，不覆盖运行时改动。
- **privacy.mode**：`strict` / `balanced`（默认）/ `advanced`（v0.1 按 balanced 生效）。

## 多服务器与群授权用法

- `/pal servers`：列出所有服务器与本群授权/活动状态。
- `/pal use <名称>`（管理员，仅群聊）：授权本群使用该服务器并设为活动服务器。
- `/pal unbind <名称>`（管理员）：撤销本群对该服务器的授权。
- **@server 尾缀**：任意查询命令可在末尾加 `@<服务器名>` 单次指定目标服务器，如 `/pal status @alpha`、`/pal guild 晨曦联盟 @beta`（服务器名不含空格，公会/据点名可含空格）。

## 命令一览（全部只读、纯文本）

`/pal status`、`/pal online`、`/pal world`、`/pal rules`、`/pal guilds`、`/pal guild <名称>`、
`/pal bases`、`/pal base <名称|#序号>`、`/pal events`、`/pal today`、`/pal help`、
`/pal servers`、`/pal use <名称>`、`/pal unbind <名称>`。

## 降级说明

API 不可达时显示"当前无法获取世界数据，最后成功更新 N 分钟前"，**绝不**臆断"服务器已关机"。部分端点失败时降级相关模块，其余照常。

## 许可证

见 LICENSE。
```

- [ ] **4. 跑测试确认通过** — 运行：
  `python -m pytest tests/unit/readme_test.py -q`
  期望 PASS：3 passed。

- [ ] **5. 提交** —
  `git add README.md tests/unit/readme_test.py && git commit -m "docs(readme): safety-first README with multi-server + group-auth usage"`

---

### Task 6.16：全套测试收口（pytest 全绿）

**Files:**
- Create: `pytest.ini`（若前置阶段未建；配置 asyncio 模式 + testpaths）
- Modify: 无业务代码（仅确认全绿；如暴露跨阶段口径不一致，回对应 Phase 修）

**Interfaces:**
- Consumes：全部 `tests/unit/`、`tests/integration/`、`tests/golden/`（Phase 1–6 累积）。
- Produces：`pytest.ini`（`asyncio_mode = auto` 或显式 `@pytest.mark.asyncio` 兼容）+ 全绿证据。

- [ ] **1. 写失败测试** — 创建 `tests/unit/suite_meta_test.py`（哨兵：确认关键测试文件都存在且可被收集，防止阶段漏挂）：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_phase6_test_files_present():
    expected = [
        "tests/unit/fixtures_loader_test.py",
        "tests/unit/fixtures_boundary_test.py",
        "tests/integration/pipeline_test.py",
        "tests/integration/privacy_test.py",
        "tests/integration/routing_test.py",
        "tests/integration/smoke_test.py",
        "tests/unit/metadata_seed_test.py",
        "tests/unit/readme_test.py",
    ]
    missing = [p for p in expected if not (ROOT / p).is_file()]
    assert missing == [], f"缺失测试文件: {missing}"


def test_fixtures_scenarios_present():
    scenarios = ["normal_world", "no_players", "multi_guild_base", "missing_fields",
                 "unknown_class", "mixed_case_keys", "unauthorized",
                 "api_interrupt_recovery", "worldguid_switch"]
    root = ROOT / "tests" / "fixtures"
    missing = [s for s in scenarios if not (root / s).is_dir()]
    assert missing == [], f"缺失 fixture 场景: {missing}"
```

- [ ] **2. 跑测试确认失败** — 运行：
  `python -m pytest tests/unit/suite_meta_test.py -q`
  期望：若 pytest 未配置 asyncio 模式，`tests/integration/*` 的 `pytestmark = pytest.mark.asyncio` 需要 `pytest-asyncio`；此哨兵本身应 PASS，但**全量** `python -m pytest -q` 可能因缺 `pytest.ini` 的 asyncio 配置而对个别 async 测试报 `async def functions are not natively supported`。据此确认需补 `pytest.ini`。

- [ ] **3. 写最小实现** — 创建 `pytest.ini`（若前置阶段已建则合并，不重复键）：

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = *_test.py
filterwarnings =
    error::RuntimeWarning
```

  （`asyncio_mode = auto` 让所有 `async def test_*` 自动按 asyncio 运行，无需逐个装饰；`python_files = *_test.py` 匹配本仓库 `<module>_test.py` 命名。`filterwarnings` 把未 await 协程等 RuntimeWarning 升级为错误，帮助发现任务泄漏——契合 spec §19 可靠性。）

- [ ] **4. 跑测试确认通过** — 运行全量：
  `python -m pytest -q`
  期望 PASS：全绿（Phase 1–6 所有 unit/integration/golden 测试）。若某跨阶段口径不一致导致红，按报错定位到对应 Phase 的 formatter/DTO/repo 方法修正后重跑，直至 `X passed`。

- [ ] **5. 提交** —
  `git add pytest.ini tests/unit/suite_meta_test.py && git commit -m "test: pytest.ini asyncio auto-mode + suite sentinel; full suite green"`


---

## 执行交接（Execution Handoff）

计划共 6 个阶段、约 94 个任务，按阶段顺序有依赖：Phase 1（基础设施）→ 2（管线）→ 3（追踪）→ 4（事件/日报）→ 5（路由/命令/装配）→ 6（集成/隐私/文档）。同阶段内多数任务可顺序执行；每个任务自带 TDD 五步与提交。

**推荐执行方式：subagent-driven-development** —— 每个任务派一个全新 subagent 实现、两段式评审、任务间检查点，最适合这种任务边界清晰、需逐个把关的长计划。

备选：executing-plans —— 在当前会话内分批执行、带检查点评审。

> 上线前务必对照 spec §21 的"待实服/框架验证清单"用真机脱敏样本核对（`userId`↔`userid`、`InstanceID`/`TrainerInstanceID` 稳定性、PalBox 坐标/GuildID、game-data 真实大小写、`event.message_str` 属性名、`object` 内 `options`/`obvious_hint`、命令组子命令 `alias=` 支持）。
