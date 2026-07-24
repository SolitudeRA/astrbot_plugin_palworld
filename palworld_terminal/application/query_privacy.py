from __future__ import annotations

from ..config import AppConfig
from ..domain.models import World, WorldEvent
from .name_resolver import load_excluded_keys as _load_excluded_keys
from .name_resolver import resolve_subjects
from .ports import ReadRepositoryPort


class _PrivacyBase:
    """隐私脊柱：排除名单 / 名字级封禁判定 / 事件主体解析。四查询 mixin 继承本类，
    跨组隐私调用经 self/MRO 解析到这里（脊柱是唯一跨切点）。"""

    _repo: ReadRepositoryPort
    _cfg: AppConfig

    async def load_excluded_keys(self, world: World) -> set[str]:
        # 与 ReportService/name_resolver 共用同一真相源（避免口径复制漂移）。
        return await _load_excluded_keys(
            self._repo, world.world_id, self._cfg.players.exclude_names
        )

    async def resolve_event_subjects(
        self, world: World, events: list[WorldEvent]
    ) -> dict[str, str]:
        """事件主体名批量解析入口（events() 接 resolver，供 T6 events 复用）。
        隐藏/被排除玩家主体缺席（调用方跳过整条）；据点用统一序号空间、hidden 回退
        「据点」；公会查无回退「公会」。ReportService（T7 today）另经 name_resolver
        自由函数复用同一逻辑。"""
        excluded = await self.load_excluded_keys(world)
        return await resolve_subjects(self._repo, world.world_id, events, excluded)

    async def name_banned(self, world: World, name: str, excluded: set[str]) -> bool:
        """名字级收敛判定(与 rank 两榜同语义):同名任一 key 被排除/隐藏
        即整组不可见——同一玩家改名/多 key 时,自助隐藏不因另一 key
        未隐藏而被绕过。"""
        keys = await self._repo.list_players_by_name(world.world_id, name)
        return any(k in excluded for k in keys)
