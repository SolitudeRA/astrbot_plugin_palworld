from __future__ import annotations

from ..config import AppConfig
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .ports import ReadRepositoryPort
from .query_dex import _DexQueries
from .query_events import _EventSummaryQueries
from .query_guild import _GuildBaseQueries
from .query_players import _RankProfileQueries
from .query_status import _StatusQueries
from .query_support import _STATUS_RULE_FIELDS as _STATUS_RULE_FIELDS

# 保外部 import 路径（门面 re-export，见 §6）——冗余别名规避 ruff F401：
from .query_support import PlayerProfileDTO as PlayerProfileDTO
from .query_support import RankBoardsDTO as RankBoardsDTO
from .query_support import metric_stale as metric_stale


class QueryService(
    _StatusQueries,
    _GuildBaseQueries,
    _EventSummaryQueries,
    _RankProfileQueries,
    _DexQueries,
):
    """读查询门面。实现按查询关注点拆入 5 个查询 mixin（query_*.py）；隐私三方法
    （load_excluded_keys/name_banned/resolve_event_subjects）为跨组共享脊柱，
    落 _PrivacyBase，**五查询 mixin 均继承 _PrivacyBase**，跨组调用经 self/MRO
    解析到脊柱（门面只列五 mixin，_PrivacyBase 由它们传递继承）。模块级
    helper/DTO/常量迁中立 query_support.py。"""

    _GUILDS_TTL = 90
    _BASES_TTL = 90
    _EVENTS_TTL = 15

    def __init__(
        self, repo: ReadRepositoryPort, cache: TTLCache, cfg: AppConfig, meta, clock: Clock,
        settings_cache, world_cache=None, report=None, info_cache=None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache
        self._world_cache = world_cache if world_cache is not None else {}
        self._report = report
        self._info_cache = info_cache if info_cache is not None else {}
