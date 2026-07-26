"""八类世界事件措辞唯一渲染源（spec §4.4）。

`render_event(view)` 把八类事件措辞收敛为一处；presentation.formatters 是唯一消费者
（events / today / guild info 近期动态三处输出面共用），改词只此一处，杜绝「改词即漂移」。

入参 `EventView` 由 application 层经 `event_view` 单一构造入口产出（已含名字解析：隐藏
玩家跳过）——本模块只管措辞、不做过滤：玩家事件的隐藏/查无由构造方先行跳过；据点/公会
事件查无时 name 为空串（i18n §3.2：name_resolver 不再产中文回退词），本模块经
`L("fallback_base")`/`L("fallback_guild")` 兜底渲染；世界主体事件（里程碑/在线纪录）
无名，`name` 为空串（不消费）。

依赖 domain（enums）、application.dtos（EventView）与 presentation.locale（L），无 IO。
措辞与数据流反向解耦：application 只产结构化 EventView，presentation 独占措辞渲染
（不再有 application→presentation 反向依赖）。
"""
from __future__ import annotations

from ..application.dtos import EventView
from ..domain.enums import EventType
from .locale import L


def _or_q(v: int | None) -> object:
    return v if v is not None else "?"


def render_event(view: EventView) -> str:
    """EventView → 面向用户措辞（spec §4.4 八类表，逐字精确）。
    八类措辞经 locale 键渲染（唯一渲染源）；未知类型兜底返回枚举值，不冒异常。
    据点/公会查无（name 空）经 L("fallback_*") 兜底后填入 name 占位（i18n §3.2）。"""
    et = view.event_type
    if et is EventType.PLAYER_LEVEL_UP:
        return L("event_level_up", name=view.name, old=_or_q(view.old), new=_or_q(view.new))
    if et is EventType.NEW_PLAYER:
        return L("event_new_player", name=view.name)
    if et is EventType.NEW_GUILD:
        return L("event_new_guild", name=view.name or L("fallback_guild"))
    if et is EventType.NEW_BASE:
        return L("event_new_base", name=view.name or L("fallback_base"))
    if et is EventType.BASE_VANISHED:
        return L("event_base_vanished", name=view.name or L("fallback_base"))
    if et is EventType.WORKER_DELTA:
        return L("event_worker_delta",
                 name=view.name or L("fallback_base"),
                 prev=_or_q(view.prev), cur=_or_q(view.cur))
    if et is EventType.WORLD_DAY_MILESTONE:
        return L("event_world_day", milestone=_or_q(view.milestone))
    if et is EventType.ONLINE_RECORD:
        return L("event_online_record", value=_or_q(view.value))
    return et.value
