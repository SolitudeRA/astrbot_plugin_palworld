from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import Confidence, EventType, PingBucket
from ..domain.models import WorldEvent


@dataclass(slots=True)
class StatusDetailDTO:
    """状态卡「详细区」的白名单子集（仅世界级信息，不含玩家个体数据）。

    version/address 恒有值；description/uptime 依赖 info/metrics 采集，缺失给空串/0；
    rules 仅含快照里存在的规则键（缺项省略，不塞空串）。
    """
    version: str
    description: str
    uptime_seconds: int
    frametime_ms: float
    address: str
    rules: dict[str, str]


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
    updated_at: int          # 数据时间戳（有 metric 时=observed_at；web 新鲜度用）
    degraded: bool
    last_ok: int | None
    # 详细区：仅 ready 且非 degraded 时装配（degraded/骨架行为 None，status_rows 不下发）
    detail: StatusDetailDTO | None = None
    # 生成本快照时的真实当下：降级态 format_degraded 据此算「最后成功于 N 分钟前」
    # （updated_at 在陈旧时=last_ok，不能充当 now）。仅聊天降级渲染消费，不入 web 白名单。
    now: int = 0


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
    # 头行供数（spec §4.24）：/max 容量=latest_metric.max_players、今日峰值=peak_online
    # （聚合值，不可归因，保留原值）。头行在线数分子恒 = len(rows)（收敛后名单数，§3 隐私收敛）。
    max_players: int = 0
    peak_online: int = 0


@dataclass(slots=True)
class WildTopRow:
    name: str
    count: int


@dataclass(slots=True)
class WorldSummaryDTO:
    """world overview 人口普查（spec §4.2）。

    online/max_players/basecamp_count 取 latest_metric（官方口径，与 status 同源）；
    人口/设施计数来自 game-data 快照。FPS 归 status，不入本 DTO。
    available=False（game-data 快照缺失）时 formatter 走 ⚠️ 取数失败态（不再静默全 0）。
    """
    world_day: int
    online: int
    max_players: int
    players: int
    otomo: int
    base_pal: int
    wild: int
    npc: int
    palbox: int
    guilds: int
    basecamp_count: int
    wild_top: list[WildTopRow]
    available: bool


@dataclass(slots=True)
class RuleSection:
    title: str                       # 节名（模式/倍率/节奏/上限），素文无图标
    items: list[tuple[str, str]]     # (展示label, 已渲染值)——formatter 两两并一行


@dataclass(slots=True)
class RulesDTO:
    """world rules 策展分节（spec §4.3）。

    sections 已由 query 层按策展清单裁剪 + 值渲染（倍率 1.0x / 节奏保游戏原单位 /
    上限裸数）。available=False（settings 快照未获取）→ formatter 走 ⚠️ 取数失败态。
    privacy_note 两模式分叉句（strict / advanced），balanced 为 None。
    """
    sections: list[RuleSection]
    available: bool
    privacy_note: str | None
    updated_at: int


@dataclass(slots=True)
class GuildDTO:
    """guild list 行（spec §4.6）。据点数=list_bases 按 guild_key 分组（§5#15）。
    active_7d 占位与 PalBox 计数按定案砍位（PalBox 归 overview 设施节）。"""
    name: str
    observed_members: int
    base_pals: int
    base_count: int


@dataclass(slots=True)
class GuildDetailDTO:
    """guild info 卡片（spec §4.7）。恒 0 占位（active_*/average_level）与 PalBox 砍位。
    bases=(display_name, confidence) 按 guild_key 过滤（含 low 序号空间）；recent_events=
    list_events 过滤该公会据点的 NEW_BASE/WORKER_DELTA/BASE_VANISHED，经 event_view 构造
    EventView（措辞渲染下沉 presentation.render_event）。"""
    name: str
    first_seen_at: int
    last_seen_at: int
    observed_members: int
    base_pals: int
    base_count: int
    bases: list[tuple[str, Confidence]]
    recent_events: list[EventView]


@dataclass(slots=True)
class BaseDTO:
    index: int
    display_name: str
    guild_name: str | None
    confidence: Confidence
    worker_count: int


@dataclass(slots=True)
class BaseDetailDTO:
    """guild base 详情（spec §4.9）+ 车间现场富化（spec §6）。palbox_count（硬编码 1）与
    activity_score 裸数砍位。available=False（latest_base_observation 缺失）→ formatter 走
    ⚠️ 无观测态（不再全 0 假数据）。

    车间现场（§6）三派生字段：
      · slacker_rate —— slacking 计数占 action_distribution 总数比例 ∈ [0,1]（空/零→0.0）；
      · mood —— **由 slacker_rate 阈值派生**的稳定键（fired_up / slacking_off）；中文/徽章/
        吐槽映射下沉 presentation（locale 模板），不在数据层预渲染；
      · species_top —— 就近可见快照按公会名聚合的 BaseCampPal 物种 (name, count) 降序 Top-N
        （Class→meta.pal_name）；无快照/无公会名→空（C2 只报此刻可见，不臆造）。"""
    display_name: str
    guild_name: str | None
    confidence: Confidence
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int]
    health_score: float
    available: bool = True
    mood: str = "fired_up"
    slacker_rate: float = 0.0
    species_top: list[tuple[str, int]] = field(default_factory=list)


@dataclass(slots=True)
class EventView:
    occurred_at: int
    event_type: EventType
    name: str
    old: int | None = None
    new: int | None = None
    prev: int | None = None
    cur: int | None = None
    milestone: int | None = None
    value: int | None = None


def event_view(e: WorldEvent, name: str) -> EventView:
    """WorldEvent → EventView：EventView 唯一构造入口（spec §6.1a）。
    只抽 render_event 需要的具名字段；内部键（guild_key/day/worker_count/
    confidence/first_missing_day）不被读取、绝不进 EventView（§6.1 隐私加固）。"""
    p = e.payload or {}
    return EventView(
        occurred_at=e.occurred_at,
        event_type=e.event_type,
        name=name,
        old=p.get("old"),
        new=p.get("new"),
        prev=p.get("prev"),
        cur=p.get("cur"),
        milestone=p.get("milestone"),
        value=p.get("value"),
    )


@dataclass(slots=True)
class ServerStatusRow:
    name: str
    ready: bool
    online: bool
    allowed: bool
    active: bool


@dataclass(slots=True)
class CompanionView:
    """随身帕鲁高光（spec §5）：从 game-data OtomoPal actor 投影而来。

    element/action_label 为**稳定键**（meta.element 输出 / ActionCategory.value），中文措辞与
    图标映射下沉 presentation（T7 文字 / T9 图片）——不在数据层预渲染。
    instance_id/trainer_instance_id/坐标绝不进本视图（内存 join 用途，DTO 边界闭合，§9 P6）。
    """
    species_name: str    # meta.pal_name(pal_class)（未收录→安全缩写）
    element: str         # meta.element(pal_class)：fire/…/neutral，未收录/无 → "unknown"（降级）
    level: int           # OtomoPal.level（缺→0）
    action_label: str    # ActionCategory.value（working/slacking/…）；presentation 映中文
    hp_ratio: float      # hp/max_hp ∈ [0,1]（缺/除零→0.0）


@dataclass(slots=True)
class MeCardDTO:
    """我的名片数据层（spec §5）：/pal me 文字版（T7）/ 图片版（T9）共用数据投影。

    percentile：等级**超越有记录玩家**的比例 ∈ [0,100]（复用 list_players_by_level 分布，
    C2 口径——非「全服」）。
    companion_status ∈ {shown, none_out, no_data}（复用 world_summary 的 available 范式）：
      · shown    —— 在线且快照见其带出的 OtomoPal（companion 非空）；
      · none_out —— 在线 + 快照有 + 找到本人 actor 但无匹配随身（「此刻未带出随身帕鲁」）；
      · no_data  —— 无快照 / 本人不在快照 / 离线（随身数据不可用，**绝不谎称没带**）。
    last_seen_at/first_seen_at：**在 application 层预粗化为距今整天数**（非绝对 epoch；0=今天）
    ——隐私 P1：绝对登录/登出时刻=作息，绝不出绝对时间戳。online_seconds/today_seconds/
    total_seconds 是**时长**（秒），非时刻，无隐私粗化需求。
    """
    name: str
    level: int
    online: bool
    online_seconds: int
    guild_name: str | None
    hidden: bool
    today_seconds: int
    total_seconds: int
    percentile: float
    last_seen_at: int    # 预粗化：距今整天数（days ago），非 epoch
    first_seen_at: int   # 预粗化：距今整天数（days ago），非 epoch
    companion: CompanionView | None
    companion_status: str


@dataclass(slots=True)
class RankClimbEntry:
    name: str
    gain: int          # 周窗 level 涨幅（max(0, current − baseline)，恒 > 0 才上榜）


@dataclass(slots=True)
class RankClimbDTO:
    """rank climb 飞升榜（spec §7）：周窗 level 涨幅，gain > 0 才上榜。

    rows 已按 gain 降序取 Top-N（名字级收敛，被排除/隐藏整组剔除）。
    shallow=True 表示无任一窗前观测（bot 记录不足 7 天）→ formatter 措辞「自 bot 记录以来」。
    viewer_* = 调用方（已绑定）本人在全体涨幅玩家中的榜位（非仅 Top-N）；未绑定/本人无涨幅→None。
    viewer_gap = 距前一位的 gain 差；viewer_rank==1（榜首）时为 None。
    """
    rows: list[RankClimbEntry]
    shallow: bool = False
    viewer_rank: int | None = None
    viewer_gain: int | None = None
    viewer_gap: int | None = None
