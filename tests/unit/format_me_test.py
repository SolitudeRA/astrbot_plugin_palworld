"""/pal me 文字版名片渲染（spec §5·T7）：四状态文字——满（百分位+随身）/ none_out /
no_data / 离线。消费 T6 的 MeCardDTO；last_seen_at/first_seen_at 是「距今天数」int
（0=今天），渲染成「N天前」/「今天」，绝不 fromtimestamp（隐私 P1，无绝对时间戳/无 1970）。"""
from palworld_terminal.application.dtos import CompanionView, MeCardDTO
from palworld_terminal.presentation.formatters import format_me

_EPOCH = 1_700_000_000  # 若误当时间戳渲染会现的 epoch 秒；离线卡绝不含之


def _dto(**kw):
    base = dict(
        name="皮皮", level=30, online=True, online_seconds=3900,
        guild_name="晨曦", hidden=False, today_seconds=7200, total_seconds=360000,
        percentile=40.0, last_seen_at=0, first_seen_at=10,
        companion=None, companion_status="no_data",
    )
    base.update(kw)
    return MeCardDTO(**base)


def _companion():
    return CompanionView(
        species_name="皮皮龙", element="grass", level=48,
        action_label="working", hp_ratio=0.8,
    )


# ---- 满：online + shown → 百分位 + 随身（皮皮龙草 Lv48）----

def test_full_state_shows_percentile_and_companion():
    text = format_me(_dto(companion=_companion(), companion_status="shown"))
    assert "皮皮" in text                     # 名片主体
    assert "Lv30" in text
    # 百分位：措辞「超越有记录玩家」（非「全服」）+ 数字
    assert "超越有记录玩家" in text
    assert "全服" not in text
    assert "40%" in text
    # 随身高光：物种 + 元素中文（草）+ 等级 + HP% + 状态
    assert "皮皮龙" in text
    assert "草" in text
    assert "Lv48" in text
    assert "80%" in text
    assert "工作中" in text
    # 满态不得混入无随身/无数据措辞
    assert "未带出" not in text
    assert "暂不可用" not in text


# ---- none_out：online + 有快照 + 本人在 + 无随身 → 「此刻未带出随身帕鲁」----

def test_none_out_state_says_not_brought_out():
    text = format_me(_dto(companion=None, companion_status="none_out"))
    assert "此刻未带出随身帕鲁" in text
    assert "暂不可用" not in text


# ---- no_data：online 但无 game-data 快照 → 「暂不可用（需启用 guilds_bases）」，绝不谎称没带 ----

def test_no_data_state_says_unavailable_not_lying():
    text = format_me(_dto(companion=None, companion_status="no_data"))
    assert "随身数据暂不可用（需启用 guilds_bases）" in text
    assert "没带" not in text            # 绝不谎称「没带」
    assert "未带出" not in text


# ---- 离线：online==False → 「此刻不在线」+ 最近上线 N天前 + 累计在线；无实时 HP/随身/绝对时间戳 ----

def test_offline_state_no_realtime_no_absolute_timestamp():
    text = format_me(_dto(
        online=False, online_seconds=0, companion=None, companion_status="no_data",
        last_seen_at=3, first_seen_at=10, total_seconds=360000,
    ))
    assert "此刻不在线" in text
    assert "3天前" in text                # 距今天数渲染，非绝对日期
    assert "累计" in text
    # 离线无实时血量 / 无随身段 / 无实时在线点（🟢）
    assert "HP" not in text
    assert "随身" not in text
    assert "🟢" not in text
    # 隐私 P1：绝不出绝对时间戳（epoch / 1970）
    assert "1970" not in text
    assert str(_EPOCH) not in text


def test_offline_last_seen_today_when_zero_days():
    text = format_me(_dto(online=False, online_seconds=0, last_seen_at=0))
    assert "今天" in text
    assert "1970" not in text
