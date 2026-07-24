"""我的名片图片版模板（spec §5·功能①图片路）。

`build_me_card_html(dto, icons, theme)` 是**纯函数**：入参只有 MeCardDTO + 元素图标表
(element→SVG 串) + 已解析主题（"light"/"dark"）——**无快照、无时钟、无运行时 I/O、无
`auto`**（auto→light/dark 的解析在 Commands.me_card_html，注入固定 clock+tz 后传入）。

隐私红线（§9 P5，测试证实）：输出 HTML **绝不含**坐标 / instance_id / player_key /
绝对时间戳（epoch/ISO）——DTO 边界已闭合这些字段（时间字段是「距今天数」int）。玩家名
/公会名是唯一用户可控自由文本 → **HTML + Jinja 双转义**（含 `{{`/`{%` 的名字会被
html_render 的 Jinja 二次解析破坏，故连花括号一并中和）。元素 SVG 是可信静态内容、内联
不转义（已核 9 个 SVG 无脚本/外链/花括号）。

视觉：C1 浅 / C3 暗两版「现代档案」卡，同一档案骨架（名/等级/公会 → 百分位 hero →
本次·累计 stat 卡 → 随身帕鲁行 → 页脚）。四状态：满（companion shown）/ 无随身
（none_out 虚线）/ 无数据（no_data，绝不谎称没带）/ 离线（badge + 最近上线，无实时血量·随身）。
"""
from __future__ import annotations

import html

from ..application.dtos import MeCardDTO
from .textkit import fmt_duration

# 元素英文键 → 中文（与 domain.Element 九元素 + formatters._ELEMENT_LABEL 对齐）。
_ELEMENT_ZH = {
    "fire": "火", "water": "水", "grass": "草", "electric": "电", "ice": "冰",
    "dragon": "龙", "dark": "暗", "ground": "地", "neutral": "无", "unknown": "未知",
}
# 元素 → 降级 emoji（图标缺失/未收录元素时用；永不依赖字体/图标文件）。
_ELEMENT_EMOJI = {
    "fire": "🔥", "water": "💧", "grass": "🌿", "electric": "⚡", "ice": "❄",
    "dragon": "🐲", "dark": "🌑", "ground": "⛰", "neutral": "⭐",
}
# ActionCategory.value → 中文（与 formatters._ACTION_CAT_LABEL 对齐）。
_ACTION_ZH = {
    "working": "工作中", "moving": "移动", "idle": "闲置", "slacking": "摸鱼",
    "combat": "战斗", "sleeping": "睡觉", "eating": "进食",
    "incapacitated": "濒死", "unknown": "随行",
}


def _esc(text: str) -> str:
    """用户可控自由文本转义：HTML 实体化（< > & " '）+ 中和 Jinja 花括号。

    html_render 先把模板串交 Jinja2 渲染（data 恒 `{}`）再交浏览器——故 `{{ x }}` /
    `{% %}` 会被 Jinja 解析破坏或注入。html.escape 不动花括号，须显式把 `{`/`}` 换成
    HTML 数字实体（Jinja 阶段看到的是 `&#123;` 无花括号、浏览器阶段才解回字面 `{`）。
    """
    return html.escape(text, quote=True).replace("{", "&#123;").replace("}", "&#125;")


def _rel_days(days: int) -> str:
    """距今天数 int（0=今天）→「今天」/「N天前」。绝不当 epoch（隐私 P1）。负值归 0。"""
    n = max(int(days), 0)
    return "今天" if n == 0 else f"{n}天前"


def _companion_face(element: str, icons: dict[str, str]) -> str:
    """随身帕鲁头：优先注入的元素 SVG（可信静态、内联不转义）；缺则降级 emoji。"""
    svg = icons.get(element)
    if svg:
        return svg
    return _ELEMENT_EMOJI.get(element, "🐾")


def _otomo_block(dto: MeCardDTO, icons: dict[str, str]) -> str:
    """随身三态 → 卡区 HTML。离线卡走专属空态（无实时血量/随身）。"""
    if not dto.online:
        return '<div class="otomo empty">离线 · 无实时血量与随身数据</div>'
    if dto.companion_status == "shown" and dto.companion is not None:
        c = dto.companion
        element_zh = _ELEMENT_ZH.get(c.element, c.element)
        action_zh = _ACTION_ZH.get(c.action_label, "随行")
        face = _companion_face(c.element, icons)
        return (
            '<div class="otomo">'
            f'<div class="face">{face}</div>'
            '<div class="info"><div class="l1">随身帕鲁</div>'
            f'<div class="l2">{_esc(c.species_name)} <em>{element_zh}</em></div></div>'
            f'<div class="st">Lv{c.level} · HP {c.hp_ratio:.0%}<br>{action_zh}</div>'
            '</div>'
        )
    if dto.companion_status == "none_out":
        return '<div class="otomo empty">此刻未带出随身帕鲁</div>'
    # no_data：无快照/本人不在快照/game-data 未轮询——绝不谎称没带（C2）。
    return '<div class="otomo empty">随身数据暂不可用（需启用 guilds_bases）</div>'


def _stat_grid(dto: MeCardDTO) -> str:
    """两格 stat 网格。玩家自身 HP 不在 DTO → 不放 HP（用本次/累计在线或最近上线）。"""
    if dto.online:
        cells = [
            ("本次在线", fmt_duration(dto.online_seconds)),
            ("累计在线", fmt_duration(dto.total_seconds)),
        ]
    else:
        cells = [
            ("最近上线", _rel_days(dto.last_seen_at)),
            ("累计在线", fmt_duration(dto.total_seconds)),
        ]
    return "".join(
        f'<div class="stat"><div class="t">{t}</div><div class="d">{d}</div></div>'
        for t, d in cells
    )


def build_me_card_html(dto: MeCardDTO, icons: dict[str, str], theme: str) -> str:
    """MeCardDTO + 元素图标表 + 已解析主题（light/dark）→ 名片 HTML 串（纯函数）。

    theme 恒为 "light"/"dark"（auto 已在 Commands 层解析）；非法值回落 light。
    """
    if theme not in ("light", "dark"):
        theme = "light"
    dark = theme == "dark"
    card_cls = "card dossier c3" if dark else "card dossier"

    guild_html = (
        f'<div class="guild">{_esc(dto.guild_name)}</div>' if dto.guild_name else ""
    )
    badge_html = (
        '<span class="badge"><i></i>此刻不在线</span>' if not dto.online else ""
    )
    pct = f"{max(0.0, min(dto.percentile, 100.0)):.0f}"
    hidden_html = " · 已隐藏（仅自己可见）" if dto.hidden else ""
    foot_right = f"首次记录 {_rel_days(dto.first_seen_at)}{hidden_html}"

    return f"""<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; }}
.page {{ font-family: system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  padding:34px 30px; -webkit-font-smoothing:antialiased; display:flex; justify-content:center; }}
.page.light {{ background:#eceae4; }}
.page.dark {{ background:#0f0c07; }}
.card {{ width:460px; max-width:100%; border-radius:16px; overflow:hidden;
  font-variant-numeric:tabular-nums; }}
.dossier {{ --bg:#f8f6f2; --card:#fff; --ink:#1f2632; --sub:#7a828e; --line:#ebe7df;
  --acc:#0f766e; --acc2:#0d9488; --tint:#dcfce7; --elem:#3f9b45; --heroink:#eafffb;
  background:var(--bg); border:1px solid var(--line); color:var(--ink);
  box-shadow:0 14px 34px -20px rgba(20,30,40,.4); }}
.c3.dossier {{ --bg:#17130d; --card:#211c15; --ink:#efe9de; --sub:#a99e8c; --line:#2e2820;
  --acc:#f59e0b; --acc2:#fbbf24; --tint:#14321f; --elem:#5fce6f; --heroink:#1a1305;
  box-shadow:0 18px 40px -22px rgba(0,0,0,.7); }}
.dossier .in {{ padding:22px 24px 20px; }}
.dossier .top {{ display:flex; justify-content:space-between; align-items:flex-start; }}
.dossier .nm {{ font-size:24px; font-weight:800; letter-spacing:-.01em; }}
.dossier .guild {{ color:var(--sub); font-size:13px; margin-top:4px; font-weight:500; }}
.dossier .lv {{ text-align:right; }}
.dossier .lv b {{ font-size:28px; font-weight:800; color:var(--acc); line-height:1; }}
.dossier .lv span {{ display:block; font-size:10px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--sub); font-weight:700; margin-top:2px; }}
.dossier .badge {{ display:inline-flex; align-items:center; gap:6px; margin-top:9px; font-size:11.5px;
  font-weight:700; color:var(--sub); background:color-mix(in oklab,var(--sub) 14%,transparent);
  padding:3px 10px; border-radius:20px; }}
.dossier .badge i {{ width:6px; height:6px; border-radius:50%; background:var(--sub); display:block; }}
.dossier .hero {{ margin:18px 0; padding:15px 17px;
  background:linear-gradient(100deg,var(--acc),var(--acc2)); border-radius:12px; color:var(--heroink); }}
.c3 .hero {{ color:#2a1e05; }}
.dossier .hero b {{ font-size:32px; font-weight:800; }}
.dossier .hero span {{ font-size:13px; opacity:.92; margin-left:8px; }}
.dossier .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.dossier .stat {{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:11px 13px; }}
.dossier .stat .t {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase;
  color:var(--sub); font-weight:700; }}
.dossier .stat .d {{ font-size:17px; font-weight:800; margin-top:4px; }}
.dossier .otomo {{ margin-top:14px; display:flex; align-items:center; gap:12px; padding:12px 14px;
  background:var(--card); border:1px solid var(--line); border-radius:11px; }}
.dossier .face {{ width:36px; height:36px; border-radius:9px; background:var(--tint); display:grid;
  place-items:center; color:var(--elem); font-size:20px; }}
.dossier .face svg {{ width:21px; height:21px; display:block; }}
.dossier .otomo .info {{ flex:1; }}
.dossier .otomo .l1 {{ font-size:11px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--sub); font-weight:700; }}
.dossier .otomo .l2 {{ font-size:15px; font-weight:700; margin-top:2px; }}
.dossier .otomo .l2 em {{ font-style:normal; color:var(--elem); font-weight:800; }}
.dossier .otomo .st {{ font-size:12.5px; color:var(--sub); text-align:right; line-height:1.35; }}
.dossier .otomo.empty {{ color:var(--sub); font-size:13.5px; justify-content:center; font-weight:600;
  background:transparent; border-style:dashed; }}
.dossier .foot {{ margin-top:16px; padding-top:12px; border-top:1px solid var(--line); font-size:12px;
  color:var(--sub); display:flex; justify-content:space-between; }}
</style>
<div class="page {theme}">
  <div class="{card_cls}" data-theme="{theme}">
    <div class="in">
      <div class="top">
        <div><div class="nm">{_esc(dto.name)}</div>{guild_html}{badge_html}</div>
        <div class="lv"><b>{dto.level}</b><span>Level</span></div>
      </div>
      <div class="hero"><b>{pct}%</b><span>超越有记录玩家</span></div>
      <div class="grid">{_stat_grid(dto)}</div>
      {_otomo_block(dto, icons)}
      <div class="foot"><span>PalWorldTerminal</span><span>{foot_right}</span></div>
    </div>
  </div>
</div>"""
