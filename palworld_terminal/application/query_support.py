"""QueryService 拆分的中立支撑层：模块级 helper / DTO / 常量（无类、无 self 依赖）。
从 query_service.py 迁出，供 5 个 query_* mixin 共享、门面 re-export 保外部路径。"""
from __future__ import annotations

from dataclasses import dataclass, field

_STATUS_TTL = 15
_ONLINE_TTL = 15


def metric_stale(observed_at: int, now: int, metrics_seconds: int) -> bool:
    """指标新鲜度判定（spec §3 降级态）：距最后成功观测超阈值即视为陈旧。

    阈值 = metrics_seconds × 3 + 60s 余量（纯派生自 polling.metrics_seconds，不新增
    配置键、随轮询周期缩放）。status 降级双态与 link list 可达三态（T12）共用本判定。
    边界：距今恰为阈值不算陈旧，超阈值方为陈旧。
    """
    return now - observed_at > metrics_seconds * 3 + 60

# 状态卡 detail.rules 子集：输出键 → 设置快照字段。措辞经 meta.setting_display
# 统一渲染（与 /pal world rules 同源）；快照缺该字段则整键省略。
_STATUS_RULE_FIELDS = (
    ("difficulty", "Difficulty"),
    ("pvp", "bEnablePlayerToPlayerDamage"),
    ("death_penalty", "DeathPenalty"),
    ("exp_rate", "ExpRate"),
)

# /pal world rules 策展分节（spec §4.3）：四节定序、每项 (展示label, settings字段, 值类型)。
# 剔除服务器技术字段（端口/RCON/REST API/日志/认证/备份/聊天限速/跨平台）与长尾细倍率
# （攻防/饱食度/耐力/生命恢复/建筑/采集/掉落）。值类型决定 value 渲染：
#   enum    → meta.setting_display（枚举措辞，如 普通/关闭/开启/掉落物品）
#   rate    → {num}x（ASCII x；spec §2.4「倍率 1.0x」，不用 metadata 的全角 ×）
#   hours   → {num} 小时（游戏设定原单位，spec §2.4 豁免，不套时长格式）
#   minutes → {num} 分钟（同上）
#   int     → {num}（裸数，剥单位）
_RULES_SECTIONS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("模式", (
        ("难度", "Difficulty", "enum"),
        ("硬核", "bHardcore", "enum"),
        ("死亡惩罚", "DeathPenalty", "enum"),
        ("帕鲁永久死亡", "bPalLost", "enum"),
        ("PVP 伤害", "bEnablePlayerToPlayerDamage", "enum"),
        ("友军伤害", "bEnableFriendlyFire", "enum"),
        ("入侵者袭击", "bEnableInvaderEnemy", "enum"),
    )),
    ("倍率", (
        ("经验", "ExpRate", "rate"),
        ("捕获", "PalCaptureRate", "rate"),
        ("工作速度", "WorkSpeedRate", "rate"),
        ("帕鲁刷新", "PalSpawnNumRate", "rate"),
        ("白天流速", "DayTimeSpeedRate", "rate"),
        ("夜晚流速", "NightTimeSpeedRate", "rate"),
    )),
    ("节奏", (
        ("蛋孵化", "PalEggDefaultHatchingTime", "hours"),
        ("空投间隔", "SupplyDropSpan", "minutes"),
    )),
    ("上限", (
        ("玩家", "ServerPlayerMaxNum", "int"),
        ("公会成员", "GuildPlayerMaxNum", "int"),
        ("据点 每公会", "BaseCampMaxNumInGuild", "int"),
        ("全服", "BaseCampMaxNum", "int"),
    )),
)


def _fmt_rules_num(value) -> str:
    """规则数值渲染：整值去小数点（32.0→32 / 1.0→1），非整保留（1.2→1.2）；
    非数字原样回退（未知枚举/异常值不冒 500）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


@dataclass(slots=True)
class PlayerProfileDTO:
    name: str
    level: int
    online: bool
    online_seconds: int
    # spec §5#16 扩字段（数据 PlayerIdentity 现成，DTO 通管；player info + me 共用卡片）。
    # 今日在线=day 窗口 per-player 聚合同源 rank today；累计=同源 rank total；
    # guild_name=latest_guild_key 解析（gamedata 锁定期自然缺席→None→formatter 省行）；
    # hidden=仅 me 路径查 get_hidden_keys 落位（首次现身行「· 已隐藏」角标）。
    first_seen_at: int = 0
    last_seen_at: int = 0
    guild_name: str | None = None
    today_seconds: int = 0
    total_seconds: int = 0
    hidden: bool = False


@dataclass(slots=True)
class RankBoardsDTO:
    time_rows: list[tuple[str, int]]   # (name, seconds) 今日在线时长
    level_rows: list[tuple[str, int]]  # (name, level)
    total_rows: list[tuple[str, int]] = field(default_factory=list)  # (name, seconds) 留存期累计
