"""事件主体名共享 resolver（spec §3 据点名口径 / §4.4 八类事件表 / §6#7）。

现状 world_events 渲染直出内部 subject_key：NEW_GUILD/NEW_BASE 露公会/据点内部
key，PLAYER_LEVEL_UP/NEW_PLAYER 干脆无名。本模块把三类 key 批量解析为显示名，
供 T6 events / T7 today（ReportService 内）/ T10 guild info「近期动态」三处复用
（八类措辞的单一真相源在 formatter 层，本模块只供名）。

QueryService 与 ReportService 均持 repo/cfg，故 resolver 落在应用层独立模块（无状态
自由函数），两侧可干净复用；不挂 Repository（避免适配层混入名字级隐私收敛这类应用策略）。
"""
from __future__ import annotations

from collections.abc import Iterable

from ..adapters.sqlite_repository import Repository
from ..domain.models import WorldEvent

# 查无回退占位（绝不回落内部 subject_key，否则重现 §6#7 丑键泄漏）。
BASE_FALLBACK = "据点"
GUILD_FALLBACK = "公会"


def keep_world_subject_under_strict(
    events: list[WorldEvent], strict: bool
) -> list[WorldEvent]:
    """strict 隐私模式：事件只保留 world 主体（世界迎来第 N 天 / 在线人数新纪录——聚合值、
    无个体归因，与 status 保留 peak_online 同哲学）；player（升级/新玩家的活动与时刻）、
    base（据点，§4.7-4.9「据点不可绕出 strict」）、guild 主体一律剔除。events（T6，
    QueryService）与 today（T7，ReportService）两条数据路径共用本单一真相源，杜绝
    「作息/时刻/据点」在 strict 下经事件面绕出。strict=False 原样返回（浅拷贝）。"""
    if not strict:
        return list(events)
    return [e for e in events if e.subject_type == "world"]


async def load_excluded_keys(
    repo: Repository, world_id: str, exclude_names: Iterable[str]
) -> set[str]:
    """被排除/隐藏玩家 key 全集：exclude_names 配置展开为该名下所有 player_key +
    自助隐藏 hidden_players。与 rank/status 隐私收敛同一真相源（QueryService
    与 ReportService 共用本函数，避免各自复制口径漂移）。"""
    keys: set[str] = set()
    for name in exclude_names:
        for key in await repo.list_players_by_name(world_id, name):
            keys.add(key)
    keys |= await repo.get_hidden_keys(world_id)
    return keys


async def resolve_subjects(
    repo: Repository,
    world_id: str,
    events: Iterable[WorldEvent],
    excluded_keys: set[str],
) -> dict[str, str]:
    """批量解析事件主体显示名，返回 subject_key → 显示名。消费方按 event.subject_type
    区分回退语义：

      - player：解析 players.latest_name。被排除/隐藏（excluded_keys）、或同名任一 key
        被排除/隐藏（名字级收敛，防同名另一 key 补位泄露）、或查无身份 → **不入表**；
        调用方据 subject_type=="player" 且 key 缺席即跳过整条事件（与 rank 名字级收敛
        同哲学，不泄漏隐藏玩家）。
      - guild：解析 guilds.latest_name；查无 → 回退「公会」（绝不回落内部 key）。
      - base：按 list_bases(include_low=True, hidden 排除) 清单位次给 display_name 或
        BASE-{i}；hidden/查无（不在清单）→ 回退「据点」（不泄漏隐藏据点名号）。序号空间
        与 QueryService._bases_indexed / guild bases 列表 / guild base #序号 查找同源。
      - world（里程碑/在线纪录）：无名主体，不入表。
    """
    result: dict[str, str] = {}

    # 分主体类型批量去重收集待解析 key
    player_keys: set[str] = set()
    guild_keys: set[str] = set()
    base_keys: set[str] = set()
    for e in events:
        if e.subject_type == "player":
            player_keys.add(e.subject_key)
        elif e.subject_type == "guild":
            guild_keys.add(e.subject_key)
        elif e.subject_type == "base":
            base_keys.add(e.subject_key)
        # world 主体无名，忽略

    # base：单一序号空间（include_low=True、hidden 排除），与 _bases_indexed 同源
    if base_keys:
        indexed = {
            b.base_key: (b.display_name or f"BASE-{i}")
            for i, b in enumerate(
                await repo.list_bases(world_id, include_low=True), start=1
            )
        }
        for k in base_keys:
            result[k] = indexed.get(k, BASE_FALLBACK)

    # guild：按 guild_key → latest_name，查无回退「公会」
    if guild_keys:
        guild_names = {
            g.guild_key: g.latest_name for g in await repo.list_guilds(world_id)
        }
        for k in guild_keys:
            result[k] = guild_names.get(k, GUILD_FALLBACK)

    # player：被排除/隐藏或名字级收敛命中或查无 → 缺席（调用方跳过整条）
    banned_names: set[str] = set()
    for k in player_keys:
        if k in excluded_keys:
            continue
        ident = await repo.get_player(world_id, k)
        if ident is None or not ident.latest_name:
            continue
        name = ident.latest_name
        # 名字级收敛（rank/name_banned 同语义）：同名任一 key 被排除/隐藏即整名跳过
        if name in banned_names:
            continue
        siblings = await repo.list_players_by_name(world_id, name)
        if any(s in excluded_keys for s in siblings):
            banned_names.add(name)
            continue
        result[k] = name

    return result
