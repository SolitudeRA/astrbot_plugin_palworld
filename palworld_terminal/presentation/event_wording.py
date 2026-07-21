"""八类世界事件措辞唯一渲染源（spec §4.4）。

`render_event(view)` 把八类事件措辞收敛为一处；presentation.formatters 是唯一消费者
（events / today / guild info 近期动态三处输出面共用），改词只此一处，杜绝「改词即漂移」。

入参 `EventView` 由 application 层经 `event_view` 单一构造入口产出（已含名字解析：隐藏
玩家跳过、据点/公会查无回退）——本模块只管措辞、不做过滤：玩家事件的隐藏/查无由构造方
先行跳过；据点/公会事件的 `name` 恒有值（含回退「据点」/「公会」）；世界主体事件
（里程碑/在线纪录）无名，`name` 为空串（不消费）。

依赖 domain（enums）与 application.dtos（EventView），无 IO。措辞与数据流反向解耦：
application 只产结构化 EventView，presentation 独占措辞渲染（不再有 application→presentation
反向依赖）。
"""
from __future__ import annotations

from ..application.dtos import EventView
from ..domain.enums import EventType


def _or_q(v: int | None) -> object:
    return v if v is not None else "?"


def render_event(view: EventView) -> str:
    """EventView → 面向用户措辞（spec §4.4 八类表，逐字精确）。
    八类措辞唯一渲染源；未知类型兜底返回枚举值，不冒异常。"""
    et = view.event_type
    if et is EventType.PLAYER_LEVEL_UP:
        return f"{view.name} 升级 Lv{_or_q(view.old)}→Lv{_or_q(view.new)}"
    if et is EventType.NEW_PLAYER:
        return f"新玩家 {view.name} 加入世界"
    if et is EventType.NEW_GUILD:
        return f"新公会「{view.name}」出现"
    if et is EventType.NEW_BASE:
        return f"新据点「{view.name}」确认"
    if et is EventType.BASE_VANISHED:
        return f"据点「{view.name}」疑似消失（连续多次未观察到）"
    if et is EventType.WORKER_DELTA:
        return f"据点「{view.name}」工作帕鲁 {_or_q(view.prev)}→{_or_q(view.cur)}"
    if et is EventType.WORLD_DAY_MILESTONE:
        return f"世界迎来第 {_or_q(view.milestone)} 天"
    if et is EventType.ONLINE_RECORD:
        return f"在线人数新纪录 {_or_q(view.value)} 人"
    return et.value
