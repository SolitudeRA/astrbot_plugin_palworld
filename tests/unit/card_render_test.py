"""我的名片图片版模板（spec §5·功能①图片路·T9）纯函数断言。

build_me_card_html(dto, icons, theme) 是纯函数：只吃 DTO + 图标表 + 已解析主题。
覆盖：隐私（无坐标/instance_id/player_key/绝对时间戳）· 名字/公会 HTML+Jinja 转义 ·
C1 浅/C3 暗两主题各出对应结构 · 四状态（满/none_out/no_data/离线）· 元素图标注入与降级。
"""
from palworld_terminal.application.dtos import CompanionView, MeCardDTO
from palworld_terminal.presentation.card_render import build_me_card_html

_EPOCH = 1_700_000_000  # 若误当时间戳渲染会现的 epoch 秒；HTML 绝不含之
_GRASS_SVG = '<svg viewBox="0 0 24 24"><path d="M4 19 GRASSMARK"/></svg>'
_ICONS = {"grass": _GRASS_SVG, "fire": "<svg>FIREMARK</svg>"}


def _companion(**kw):
    base = dict(species_name="皮皮龙", element="grass", level=48,
                action_label="working", hp_ratio=0.8)
    base.update(kw)
    return CompanionView(**base)


def _dto(**kw):
    base = dict(
        name="晚风", level=34, online=True, online_seconds=8040,
        guild_name="哈夫克工业", hidden=False, today_seconds=7200, total_seconds=360000,
        percentile=87.0, last_seen_at=3, first_seen_at=10,
        companion=None, companion_status="no_data",
    )
    base.update(kw)
    return MeCardDTO(**base)


# ---- 隐私红线：HTML 无坐标 / instance_id / player_key / 绝对时间戳 ----

def test_no_coords_no_ids_no_absolute_timestamp():
    dto = _dto(companion=_companion(), companion_status="shown")
    html = build_me_card_html(dto, _ICONS, "light")
    # 绝对时间戳（epoch/1970）绝不出现
    assert "1970" not in html
    assert str(_EPOCH) not in html
    # id / key / 坐标字段名皆不出现（DTO 边界已闭合，模板只吃投影字段）
    for banned in ("instance_id", "player_key", "player_userid", "trainer_instance",
                   "LocationX", "LocationY", "userid", "steam_"):
        assert banned not in html


def test_days_ago_rendered_not_epoch():
    html = build_me_card_html(_dto(online=False, last_seen_at=3, first_seen_at=10),
                              _ICONS, "light")
    assert "3天前" in html          # 最近上线：距今天数
    assert "10天前" in html         # 首次记录：距今天数
    assert "1970" not in html


# ---- 转义：名字/公会含 HTML + Jinja 花括号 → 全中和，绝不原样出串 ----

def test_name_and_guild_escaped_html_and_jinja():
    dto = _dto(name="<b>{{7*7}}</b>", guild_name="{% raw %}<i>G</i>")
    html = build_me_card_html(dto, _ICONS, "light")
    # 原始危险片段绝不出现
    assert "<b>{{7*7}}</b>" not in html
    assert "{{7*7}}" not in html
    assert "{%" not in html and "{{" not in html
    assert "<i>G</i>" not in html
    # 转义后的实体在（HTML 实体化 + 花括号数字实体）
    assert "&lt;b&gt;" in html
    assert "&#123;&#123;" in html   # {{ → &#123;&#123;


# ---- C1 浅 / C3 暗：两主题各出对应结构 ----

def test_light_theme_structure():
    html = build_me_card_html(_dto(), _ICONS, "light")
    assert 'data-theme="light"' in html
    assert "card dossier c3" not in html        # 浅版卡不挂 c3 暗类
    assert "page light" in html


def test_dark_theme_structure():
    html = build_me_card_html(_dto(), _ICONS, "dark")
    assert 'data-theme="dark"' in html
    assert "card dossier c3" in html            # 暗版卡挂 c3
    assert "page dark" in html


def test_illegal_theme_falls_back_light():
    html = build_me_card_html(_dto(), _ICONS, "auto")   # 非法值（auto 本应上游解析）
    assert 'data-theme="light"' in html         # 回落浅版
    assert "card dossier c3" not in html         # 未挂 c3 暗类
    assert "page light" in html


# ---- 四状态 ----

def test_state_full_shows_companion_with_injected_svg():
    dto = _dto(companion=_companion(), companion_status="shown")
    html = build_me_card_html(dto, _ICONS, "light")
    assert "87%" in html                        # 百分位 hero
    assert "超越有记录玩家" in html
    assert "皮皮龙" in html                      # 物种
    assert "草" in html                          # 元素中文
    assert "Lv48" in html
    assert "80%" in html                         # 随身 HP
    assert "工作中" in html
    assert "GRASSMARK" in html                   # 注入的元素 SVG 内联（不转义）
    assert "此刻未带出" not in html and "暂不可用" not in html


def test_state_none_out_dashed():
    html = build_me_card_html(_dto(companion_status="none_out"), _ICONS, "light")
    assert "此刻未带出随身帕鲁" in html
    assert "暂不可用" not in html


def test_state_no_data_never_lies():
    html = build_me_card_html(_dto(companion_status="no_data"), _ICONS, "light")
    assert "随身数据暂不可用（需启用 guilds_bases）" in html
    assert "没带" not in html
    assert "未带出" not in html


def test_state_offline_badge_no_realtime():
    html = build_me_card_html(
        _dto(online=False, online_seconds=0, companion_status="no_data",
             last_seen_at=3, total_seconds=360000),
        _ICONS, "light")
    assert "此刻不在线" in html                  # badge
    assert "最近上线" in html
    assert "3天前" in html
    assert "无实时血量与随身数据" in html
    assert "1970" not in html


# ---- 元素图标缺失 → 降级 emoji（永不依赖字体/图标文件）----

def test_missing_icon_falls_back_to_emoji():
    dto = _dto(companion=_companion(element="water"), companion_status="shown")
    html = build_me_card_html(dto, _ICONS, "light")   # icons 无 water
    assert "💧" in html                          # 降级 emoji
    assert "水" in html                          # 元素中文仍在


def test_unknown_element_degrades_gracefully():
    dto = _dto(companion=_companion(species_name="谜之兽", element="unknown"),
               companion_status="shown")
    html = build_me_card_html(dto, _ICONS, "light")
    assert "谜之兽" in html
    assert "未知" in html                        # unknown → 「未知」
    assert "🐾" in html                          # 无元素 emoji → 通用降级


# ---- 隐藏角标 ----

def test_hidden_badge_present_when_hidden():
    html = build_me_card_html(_dto(hidden=True), _ICONS, "light")
    assert "已隐藏（仅自己可见）" in html
