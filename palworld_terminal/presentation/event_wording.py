"""八类世界事件措辞单一真相源（spec §4.4）。

现状事件渲染措辞多源：query 层 `_event_summary`、report 层 f-string、guild info 各写
一份，改词即漂移。本模块把八类事件措辞收敛为一处纯函数，events（T6）/ today（T7
ReportService 内）/ guild info 近期动态（T10）三处共用——单一真相源。

名字解析（含隐藏玩家跳过、据点/公会查无回退）由 `name_resolver` 供，本模块只管措辞：
入参 `name` 即 resolver 解析出的显示名。玩家事件的隐藏/查无过滤由调用方据 resolver
缺席先行跳过（本函数不做过滤）；据点/公会事件的 `name` 恒由 resolver 供（含回退
「据点」/「公会」）；世界主体事件（里程碑/在线纪录）无名，`name` 传空串即可（不消费）。

纯函数，只依赖 domain（enums/models），无 IO，避免 report_service→formatters→
query_service→report_service 的导入环。
"""
from __future__ import annotations

from ..domain.enums import EventType
from ..domain.models import WorldEvent


def event_wording(event: WorldEvent, name: str) -> str:
    """单条事件 → 面向用户措辞（spec §4.4 八类表，逐字精确）。

    name = resolver 解析出的显示名（玩家/公会/据点主体）；世界主体事件不消费 name。
    未知事件类型兜底返回枚举值（不冒异常）。
    """
    p = event.payload or {}
    et = event.event_type
    if et is EventType.PLAYER_LEVEL_UP:
        return f"{name} 升级 Lv{p.get('old', '?')}→Lv{p.get('new', '?')}"
    if et is EventType.NEW_PLAYER:
        return f"新玩家 {name} 加入世界"
    if et is EventType.NEW_GUILD:
        return f"新公会「{name}」出现"
    if et is EventType.NEW_BASE:
        return f"新据点「{name}」确认"
    if et is EventType.BASE_VANISHED:
        # 「疑似消失」自带不确定性，不另加（推导）标（spec §4.4）。
        return f"据点「{name}」疑似消失（连续多次未观察到）"
    if et is EventType.WORKER_DELTA:
        return f"据点「{name}」工作帕鲁 {p.get('prev', '?')}→{p.get('cur', '?')}"
    if et is EventType.WORLD_DAY_MILESTONE:
        return f"世界迎来第 {p.get('milestone', '?')} 天"
    if et is EventType.ONLINE_RECORD:
        return f"在线人数新纪录 {p.get('value', '?')} 人"
    return et.value
