from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

from .adapters import normalizer as _normalizer_mod
from .adapters.icon_repository import IconRepository
from .adapters.metadata_repository import MetadataRepository
from .adapters.palworld_rest import PalworldRestClient
from .adapters.sqlite_repository import Repository
from .application.admin_service import AdminService
from .application.base_service import BaseService
from .application.event_service import EventService
from .application.guild_service import GuildService
from .application.player_service import PlayerService
from .application.query_service import QueryService
from .application.report_service import ReportService
from .application.routing_service import RoutingService
from .application.snapshot_service import SnapshotService
from .config import AppConfig, ServerConfig
from .domain import privacy as _privacy_mod
from .domain.enums import EndpointName
from .infrastructure.cache import TTLCache
from .infrastructure.clock import Clock
from .infrastructure.database import Database
from .infrastructure.locks import EndpointLocks
from .infrastructure.migrations import apply_migrations
from .infrastructure.salt import load_or_create_salt
from .infrastructure.scheduler import Scheduler
from .presentation.commands import Commands
from .presentation.confirmation import ConfirmationStore
from .shared.command_permissions import active_endpoints, effective_enabled
from .shared.rest import RestResponse

_log = logging.getLogger("palworld_terminal.container")

_DB_NAME = "palworld_terminal.sqlite3"
_LEGACY_DB_NAME = "palchronicle.sqlite3"  # 内部包名改名(2026-07)前的数据库文件名


def migrate_legacy_db(data_dir: Path) -> None:
    """旧数据库就地改名,老实例升级无感;新库已存在则不动(不覆盖)。"""
    legacy = data_dir / _LEGACY_DB_NAME
    target = data_dir / _DB_NAME
    if not legacy.exists() or target.exists():
        return
    # -wal/-shm 是 SQLite 伴生文件,异常关闭后可能残留,须随主库同名迁移。
    # 用 os.replace 而非 rename:Windows 上 rename 目标存在会抛 FileExistsError
    # (如孤儿 -wal 场景),replace 跨平台静默覆盖、天然幂等。
    for suffix in ("", "-wal", "-shm"):
        src = data_dir / f"{_LEGACY_DB_NAME}{suffix}"
        if src.exists():
            os.replace(src, data_dir / f"{_DB_NAME}{suffix}")
    _log.info("数据库已从 %s 迁移为 %s", _LEGACY_DB_NAME, _DB_NAME)


class Container:
    def __init__(
        self, config: AppConfig, data_dir: Path, clock: Clock,
        rest_factory: Callable[[ServerConfig, Clock], PalworldRestClient] | None = None,
        scheduler_factory: Callable[..., Scheduler] | None = None,
    ) -> None:
        self._cfg = config
        self.config = config  # 供命令层与集成测试只读访问（precedent: repo/db 别名）
        self._data_dir = Path(data_dir)
        self._clock = clock
        self._rest_factory = rest_factory or (lambda s, clk: PalworldRestClient(s, clk))
        self._scheduler_factory = scheduler_factory or (lambda **kw: Scheduler(**kw))
        self._db: Database | None = None
        self._repo: Repository | None = None
        self._rest_clients: dict[str, PalworldRestClient] = {}
        self._scheduler: Scheduler | None = None
        self._snapshot: SnapshotService | None = None
        self.routing: RoutingService | None = None
        self.query: QueryService | None = None
        self.report: ReportService | None = None
        self.commands: Commands | None = None
        self._settings_cache: dict[str, dict] = {}
        self._world_cache: dict[str, object] = {}
        self._info_cache: dict[str, dict] = {}

    async def start(self) -> None:
        if self._cfg.skipped_headers:
            # 只含 name+reason；value（可能是网关凭证）绝不入日志
            _log.warning(
                "custom_headers 跳过 %d 条: %s",
                len(self._cfg.skipped_headers),
                ", ".join(f"{h.raw_name}({h.reason})"
                          for h in self._cfg.skipped_headers),
            )
        migrate_legacy_db(self._data_dir)
        self._db = Database(self._data_dir / _DB_NAME)
        self.db = self._db  # 供隐私扫描/集成测试只读遍历全表
        await self._db.open()
        await apply_migrations(self._db)
        salt = load_or_create_salt(self._data_dir)

        repo = Repository(self._db, self._clock)
        self._repo = repo
        self.repo = repo
        await repo.sync_servers(self._cfg.servers)
        await repo.seed_bindings(self._cfg.group_bindings)
        ready_ids = {s.server_id for s in self._cfg.servers if s.ready}
        await repo.cleanup_orphan_bindings(ready_ids)

        # metadata/ 随插件包分发，按包位置解析（palworld_terminal/ 的上级即插件根目录）；
        # data_dir 是 AstrBot 的插件数据目录（<astrbot>/data/plugin_data/<插件名>），
        # 与安装目录无关，不能用来定位 metadata。
        metadata_dir = Path(__file__).resolve().parent.parent / "metadata"
        meta = MetadataRepository(metadata_dir)
        try:
            meta.load()
        except Exception as exc:  # metadata 缺失时降级为占位渲染，但必须留痕
            _log.warning("metadata load failed dir=%s error=%s", metadata_dir, exc)

        # 元素图标 assets 与 metadata 同源、按包位置解析（非 data_dir/CWD）；
        # load() 缺文件自身降级，整体异常也留痕降级（图片名片 fallback emoji）。
        icon_dir = Path(__file__).resolve().parent.parent / "assets" / "element-icons"
        icons = IconRepository(icon_dir)
        try:
            icons.load()
        except Exception as exc:
            _log.warning("element icons load failed dir=%s error=%s", icon_dir, exc)
        cache = TTLCache(self._clock)

        ov = self._cfg.permissions.command_overrides
        events = EventService(repo, self._clock) if effective_enabled(ov, "world events") else None
        players = PlayerService(repo, salt, self._cfg, self._clock)
        _game_data_on = EndpointName.GAME_DATA in active_endpoints(ov)
        guilds = GuildService(repo, salt, self._clock) if _game_data_on else None
        bases = (BaseService(repo, self._cfg.bases, self._clock, salt)
                 if _game_data_on else None)
        players.events = events
        if guilds is not None:
            guilds.events = events
        self._snapshot = SnapshotService(
            repo, _normalizer_mod, _privacy_mod, meta, salt, self._cfg, self._clock,
            players, guilds, bases, events,
            shared_settings=self._settings_cache, shared_world=self._world_cache,
            shared_info=self._info_cache,
        )
        self.report = ReportService(repo, self._cfg, self._clock)
        self.routing = RoutingService(repo, self._cfg)
        self.query = QueryService(
            repo, cache, self._cfg, meta, self._clock, self._settings_cache,
            world_cache=self._world_cache, report=self.report,
            info_cache=self._info_cache,
        )
        admin = AdminService(
            self.routing, self._fetch, self._post, repo, salt, self._clock,
            normalize_players=_normalizer_mod.normalize_players,
        )
        confirmations = ConfirmationStore(self._clock)
        self.commands = Commands(
            self.routing, self.query, repo, self._cfg, self._clock, salt,
            admin_service=admin, confirmations=confirmations,
            icons=icons.icons(),
        )

        for s in self._cfg.servers:
            if s.ready:
                self._rest_clients[s.server_id] = self._rest_factory(s, self._clock)

        locks = EndpointLocks(self._cfg.polling.max_concurrency)
        self._scheduler = self._scheduler_factory(
            servers=[s for s in self._cfg.servers if s.ready],
            polling=self._cfg.polling, locks=locks, clock=self._clock,
            on_response=self._on_response, rng_seed=None, fetcher=self._fetch,
            endpoints=active_endpoints(self._cfg.permissions.command_overrides),
        )
        await self._scheduler.start()

    def snapshot_service(self) -> SnapshotService:
        """返回全服务器共享的 SnapshotService（集成测试与内部采集回调共用）。

        该服务是单例：多服务器数据在其内部按 world（world_id 前缀为 server_id）隔离，
        无需按 server_id 区分实例。
        """
        # start() 成功后必已初始化；类型收窄用 cast，不引入运行时断言
        return cast(SnapshotService, self._snapshot)

    async def _fetch(self, server_id: str, endpoint: EndpointName) -> RestResponse:
        client = self._rest_clients[server_id]
        return await client.fetch(endpoint)

    async def _post(
        self, server_id: str, path: str, json_body: dict | None
    ) -> RestResponse:
        # 写端点回调（照 _fetch 按 server_id 路由；routing.resolve 只返回 ready
        # 服务器，故 _rest_clients 必含对应 client）。
        client = self._rest_clients[server_id]
        return await client.post(path, json_body)

    async def _on_response(
        self, server_id: str, endpoint: EndpointName, resp: RestResponse
    ) -> None:
        server = next((s for s in self._cfg.servers if s.server_id == server_id), None)
        if server is None or self._snapshot is None or self._repo is None:
            return
        if endpoint is EndpointName.INFO:
            await self._snapshot.ingest_info(server, resp)
            return
        world = await self._repo.get_current_world(server_id)
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
