from __future__ import annotations

from pathlib import Path
from typing import Callable

from palchronicle.adapters import normalizer as _normalizer_mod
from palchronicle.adapters import privacy_filter as _privacy_mod
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

    async def start(self) -> None:
        self._db = Database(self._data_dir / "palchronicle.sqlite3")
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

        meta = MetadataRepository(self._data_dir.parent / "metadata")
        try:
            meta.load()
        except Exception:  # pragma: no cover - metadata optional at start
            pass
        cache = TTLCache(self._clock)

        events = EventService(repo, self._clock)
        players = PlayerService(repo, salt, self._cfg, self._clock)
        guilds = GuildService(repo, salt, self._clock)
        bases = BaseService(repo, self._cfg.bases, self._clock, salt)
        players.events = events
        guilds.events = events
        self._snapshot = SnapshotService(
            repo, _normalizer_mod, _privacy_mod, meta, salt, self._cfg, self._clock,
            players, guilds, bases, events,
            shared_settings=self._settings_cache, shared_world=self._world_cache,
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
            on_response=self._on_response, rng_seed=None, fetcher=self._fetch,
        )
        await self._scheduler.start()

    def snapshot_service_for(self, server_id: str) -> SnapshotService:
        """返回指定服务器的 SnapshotService（集成测试与内部采集回调共用）。"""
        return self._snapshot

    async def _fetch(self, server_id: str, endpoint: EndpointName) -> RestResponse:
        client = self._rest_clients[server_id]
        return await client.fetch(endpoint)

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
        if self._scheduler is not None:
            await self._scheduler.stop()
        for client in self._rest_clients.values():
            await client.close()
        self._rest_clients.clear()
        if self._db is not None:
            await self._db.close()
