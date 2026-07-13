# README 重设计 + 品牌改名(PalWorldTerminal)设计规格

**日期:** 2026-07-13
**分支:** `docs/readme-polish`
**内容真源:** README 预览 Artifact v2(https://claude.ai/code/artifact/7c496677-12ce-4289-a834-ed741503467a),用户已逐块批准。

## 1. 决策(用户已确认)

| # | 决策 |
|---|------|
| D1 | 品牌显示名全量改为 **PalWorldTerminal · 帕鲁世界终端**;GitHub 仓库名与标识层不动 |
| D2 | README 多级结构:主页只留最重要信息;配置详解迁 `docs/configuration.md`、指令全表迁 `docs/commands.md` |
| D3 | 头部:banner 图片占位(`docs/images/banner.png`,注释形式待补图)+ 居中标题 + 徽章行 + tagline + 一行安全摘要 + `·` 分隔锚点导航 |
| D4 | 徽章 5 枚(shields.io 静态):version v0.1.0 / python 3.11+ / AstrBot ≥4.24.1 / license GPL-3.0 / **Palworld 1.0+**(不要 REST 只读徽章) |
| D5 | 功能特性:**无 emoji** 普通圆点列表 8 条 |
| D6 | 效果预览:**无截图占位**,只留 `/pal status` 真实格式回复示例(代码块;示例数据虚构、格式来自 formatters.py:144-156) |
| D7 | tagline 直白化:「监测 Palworld 专用服务器,在群里提供状态查询、日报与玩家档案。只读,基于官方 REST API。」 |

## 2. 品牌改名边界(勘探定案)

**改(显示层):**
1. `README.md`(标题 + 正文设置页名,随重写)
2. `metadata.yaml` `display_name: PalWorldTerminal · 帕鲁世界终端`
3. `palchronicle/presentation/formatters.py:133` `"PalChronicle 命令："` → `"PalWorldTerminal 命令："`
4. `frontend/src/App.vue:34` brand → `<span class="cn">帕鲁世界终端</span><span class="en">PalWorldTerminal</span>`
5. `frontend/index.html:6` `<title>PalWorldTerminal 设置</title>`
6. `pages/settings/`(产物,重 build 生成)

**连带测试同步:**
- `tests/unit/skeleton_test.py:20` display_name 断言 → 新品牌
- `frontend/src/App.test.ts:16` `toContain('帕鲁纪事')` → `toContain('帕鲁世界终端')`
- formatters 相关测试若断言「PalChronicle 命令」→ 同步(实现时 grep)

**不动(标识层,绝不碰):** 仓库名/目录、python 包 `palchronicle` 与全部 import、`class PalChronicle(Star)` 及其测试引用、`pyproject`/`ci.yml` 包路径、DB 文件名 `palchronicle.sqlite3`、logger 名 `palchronicle.*`、localStorage key `palchronicle-theme`(改则老用户主题偏好丢失)、包 docstring、`docs/superpowers`/`docs/verification` 历史存档、`docs/design/settings-redesign-demo.html`(历史设计基准)。

## 3. 文件结构

| 文件 | 动作 | 内容 |
|---|---|---|
| `README.md` | 重写 | demo v2 主页逐字转 markdown:居中头部(banner 注释占位/标题/徽章/tagline/安全摘要行/锚点导航)→ 功能特性(8 条无 emoji)→ 效果预览(status 示例)→ 快速开始(5 步)→ 指令(常用 8 条表 + 链接)→ 配置(要点 + 功能开关 4 组表 + 链接)→ 安全与隐私(6 锚点短语全保留)→ 详细文档 → 开源协议(GPL-3.0) |
| `docs/configuration.md` | 新建 | 原 README 配置区全文迁移:servers/routing 散文、polling/world/bases/history 四表、custom_headers(含保留头/重启说明)、插件页面说明、features 详解(guilds_bases 上游限制全文) |
| `docs/commands.md` | 新建 | 原命令详表 18 条、功能开关矩阵、players/guilds_bases 默认关说明、多服务器与群授权用法、降级说明 |
| `docs/images/` | 新建目录 | `.gitkeep`;banner.png 用户后补 |
| `tests/unit/readme_test.py` | 重构 | 见 §4 |

## 4. readme_test 重构原则

- `test_readme_first_screen_safety_claims` **仍只读 README.md**(主页强制安全声明:只读/不控制服务器/不存储 IP/不公开精确位置/启用 REST/勿暴露公网)。
- 其余内容型测试改读 **文档合集**(README.md + docs/configuration.md + docs/commands.md 拼接文本):锚点存在于文档体系任一处即可。所有既有锚点短语(polling/world/bases/history 键名、custom_headers、插件页面、features、命令表、players 组)一个不删。
- 新增断言:README 含指向 `docs/configuration.md` 与 `docs/commands.md` 的链接(防文档断链)。

## 5. 验收

后端 pytest 全绿(含重构后的 readme_test + skeleton_test)· 前端 test:run + typecheck + build + verify:bundle 全绿(brand 改动重 build)· README/docs 无「PalChronicle/帕鲁纪事」残留(历史存档与标识层除外)。
