# 三语 i18n Phase 3 · 文档与截图设计

> 日期：2026-07-27
> 状态：用户逐节确认（文件结构、翻译与链接、截图 scale、测试与验收）
> 前置：Phase 1（后端聊天输出/图片名片/metadata，PR #40）与 Phase 2（设置页前端，PR #41）已合并 `main`
> 基线：`ed175b0`
> 分支：`feat/i18n-phase3-docs`

## 1. 目标

完成三语 i18n 的文档层：

1. GitHub 默认入口继续是简体中文 `README.md`。
2. README、配置文档、命令文档与贡献指南均提供完整的简体中文、日文、英文版本。
3. 每份文档顶部可在同一文档族的三种语言之间直接切换。
4. 三语 README 分别展示对应 locale 的真实设置页与图片名片截图。
5. 日英内容与运行时三语词典使用一致术语，技术 token、安全边界和功能事实不漂移。

### 1.1 成功标准

- 中文默认入口、既有中文 URL、标题与内容型测试锚保持有效。
- 日英文档不是摘要版：章节职责、关键事实、技术 token、代码/命令示例和安全告知与中文规范源完整平行。
- 任意文档的语言导航均落到同一文档族，不跳错页、不回落到另一语言。
- 日英 README 只引用对应语言的子文档与截图。
- 18 张正式截图来自 manifest 记录的同一 source commit、同一语义演示数据和同一布局 scale；原图与 README
  实际展示宽度下均清晰可读。
- 正式截图可以由仓库内锁版本的单一命令重新生成；manifest 能证明 locale、场景、主题、scale、来源 commit
  与当前 PNG 的对应关系。
- 自动守卫、人工语言审查、浏览器/图片目检与项目全量门禁全部通过。

## 2. 当前基线

### 2.1 用户文档

| 中文规范源 | 当前规模 | 职责 |
|---|---:|---|
| `README.md` | 243 行 | 默认入口、能力展示、快速开始、安全边界、文档导航 |
| `CONTRIBUTING.md` | 37 行 | 开发环境、构建、测试、提交流程 |
| `docs/configuration.md` | 198 行 | 配置字段、权限、轮询、隐私、设置页 |
| `docs/commands.md` | 191 行 | 命令树、参数、模式、权限、服务器管控 |

当前不存在 `README.ja.md`、`README.en.md` 或日英平行子文档。

### 2.2 现有守卫

- `tests/unit/readme_test.py` 将 `README.md`、`docs/configuration.md`、`docs/commands.md` 合并为中文文档面，锁定首屏安全声明、配置键、命令矩阵、模式/权限/管控行为等内容。
- 中文内容锚是现有回归契约；Phase 3 不把这些断言替换成日英措辞，也不降低安全声明强度。
- Phase 3 新建独立的 `tests/unit/docs_i18n_test.py`，负责三语结构、导航、链接、技术 token 与图片资产守卫。

### 2.3 术语源

按优先级使用：

1. `palworld_terminal/presentation/locales/{zh-CN,ja,en}.json`
2. `frontend/src/lib/locales/{zh-CN,ja,en}.ts`
3. metadata 中已落地的帕鲁名、设置项与枚举译法
4. Palworld/AstrBot 官方英文技术名

文档不得自造与运行时冲突的同义词。

### 2.4 正式图片

中文 README 当前使用：

- 设置页：`settings-servers.png`、`settings-features.png`、`settings-permissions.png`、`settings-onboarding.png`
- 图片名片：`me-card-light.png`、`me-card-dark.png`
- 共用品牌资产：`banner.png`、`logo.png`

品牌资产与语言无关，不制作日英变体。

## 3. 文件与目录结构

### 3.1 文档族

中文文件保持原路径；新增 8 份平行文档：

```text
README.md
README.ja.md
README.en.md

CONTRIBUTING.md
CONTRIBUTING.ja.md
CONTRIBUTING.en.md

docs/configuration.md
docs/configuration.ja.md
docs/configuration.en.md

docs/commands.md
docs/commands.ja.md
docs/commands.en.md
```

### 3.2 图片目录

中文沿用现有路径，日英使用语言目录与相同文件名：

```text
docs/images/
  settings-servers.png
  settings-features.png
  settings-permissions.png
  settings-onboarding.png
  me-card-light.png
  me-card-dark.png

  ja/
    settings-servers.png
    settings-features.png
    settings-permissions.png
    settings-onboarding.png
    me-card-light.png
    me-card-dark.png

  en/
    settings-servers.png
    settings-features.png
    settings-permissions.png
    settings-onboarding.png
    me-card-light.png
    me-card-dark.png
```

另新增：

- `docs/images/screenshots.manifest.json`：18 张正式截图的来源、场景、scale、像素尺寸与 SHA-256 清单。
- `scripts/capture_docs_assets.py`：18 张正式资产的唯一用户入口。
- `frontend/scripts/capture-docs-screenshots.mjs`：由总入口调用的设置页捕获实现。
- `scripts/export_docs_cards.py`：由总入口调用的图片名片导出实现；必须走真实 `build_me_card_html` 和
  与生产 `html_render(html, {}, options={"type": "png"})` 等价的 Jinja→Chromium→PNG 契约，禁止复制
  一份静态卡片模板冒充 renderer 输出。

`docs/images/README.md` 扩展为三语资产矩阵，记录来源、scale、尺寸、演示数据政策与复现步骤。它与截图
manifest 属于维护者资产说明，不是用户文档族，不要求三语化。

## 4. 语言导航

### 4.1 统一外观

全部 12 份文档在标题附近显示同一顺序：

```text
简体中文 | 日本語 | English
```

语言名使用母语名，恒定不译；当前语言使用不可点击的加粗文本，其余两项为相对链接。

### 4.2 同族映射

| 文档族 | 简体中文 | 日本語 | English |
|---|---|---|---|
| README | `README.md` | `README.ja.md` | `README.en.md` |
| CONTRIBUTING | `CONTRIBUTING.md` | `CONTRIBUTING.ja.md` | `CONTRIBUTING.en.md` |
| configuration | `configuration.md` | `configuration.ja.md` | `configuration.en.md` |
| commands | `commands.md` | `commands.ja.md` | `commands.en.md` |

导航只能横向切换同一行的文件。

### 4.3 同语言链接

- 日文 README 只链接 `docs/configuration.ja.md`、`docs/commands.ja.md`、`CONTRIBUTING.ja.md`。
- 英文 README 只链接 `docs/configuration.en.md`、`docs/commands.en.md`、`CONTRIBUTING.en.md`。
- 日英 configuration/commands 之间的交叉引用保持同一语言。
- Issue、CI、License、Palworld REST API、AstrBot 等外部链接三语共用。

## 5. 标题与 anchor

### 5.1 中文兼容

- 不改现有中文标题，保留 GitHub 已生成的中文 auto-slug，避免破坏外部深链。
- 在每个现有标题前新增显式稳定 anchor，但不能移除或改写既有中文标题。

### 5.2 跨语言稳定 ID

四个文档族的所有标题都使用显式、语义化英文 ID；所有被文档内部或跨文档引用的章节必须链接到这些 ID，例如：

- `first-setup`
- `world-mode`
- `permissions`
- `server-admin`
- `plugin-page`
- `feature-groups`
- `degraded-behavior`

三语同一章节使用同一 ID；标题文本正常翻译。仓库内链接统一指向显式 ID，不依赖任一语言标题的
auto-slug。中文标题文本保持不变，因此既有外部 auto-slug 深链继续兼容；本地自动测试不自行猜测
GitHub 的中文 slug 算法。

### 5.3 唯一性

- 同一文件内显式 ID 不重复。
- 相对链接的 fragment 必须存在于目标文件。
- 显式 anchor 统一使用仓库选定的一种标准 HTML 写法，并通过 GitHub GFM API 与 Draft PR 实际渲染验证；
  不混用多种写法，也不依赖 GitHub 私有 anchor 扩展。

## 6. 翻译契约

### 6.1 中文是事实规范源

- 中文决定章节职责、功能事实、安全边界和技术覆盖面。
- 日英文档结构完整平行，但允许为自然语言调整句序、段落内语序与标点。
- 不允许删去难译段落、危险操作后果、隐私告知或降级行为。

### 6.2 逐字保持的内容

下列真实输入或技术字面不翻译、不改写：

- `/pal ...` 命令路径、子命令、枚举值与真实输入别名（包括 `卡`、`图`）
- 配置键、JSON/YAML 字段、枚举存储值
- 环境变量、文件路径、模块名、类/函数名
- REST endpoint、URL、版本号
- shell 命令与可执行代码
- 产品名 `PalWorldTerminal`、`AstrBot`、`Palworld REST API`

`<名称>`、`<玩家名>`、`<消息>` 等是说明性 metavariable，不是用户必须逐字输入的 token；日英文档应翻译为
`<name>`、`<player>`、`<message>` 等自然目标语言写法。代码围栏中的自然语言输出示例可按 locale 翻译；
可执行命令和上述真实技术字面必须保持。

### 6.3 语言质量

- 英文使用直接、简洁的技术文档语气，不保留中文语序。
- 日文使用自然的管理画面/服务器运维表达，避免逐字汉字替换。
- 安全警告、默认关闭、仅管理员、审计、明文/PII 等语义强度不得减弱。
- 图片 alt text 使用文档对应语言，说明场景而非堆砌关键词。
- 不引入机器翻译标记、未校对占位符或“暂缺翻译”回落。

### 6.4 Phase 1/2 受限校对

文档翻译与截图阶段对 Phase 1/2 日英语句做一次有边界的一致性校对：

- 允许修复明确误译、同一术语前后冲突、进入正式截图的生硬/错误文案。
- 修复必须同步日英词典与测试，且不改变 key、placeholder、配置值或业务行为。
- 实施计划必须先列出允许修改的精确 locale key 与理由；未列入清单的运行时文案不在本 Phase 修改。
- 不扩展为运行时文案重写，不引入新 i18n 机制。

## 7. 截图矩阵

### 7.1 18 张正式图片

| 场景 | zh-CN | ja | en |
|---|---:|---:|---:|
| 服务器连接 | 1 | 1 | 1 |
| 功能启停 | 1 | 1 | 1 |
| 权限管理 | 1 | 1 | 1 |
| 首次引导 | 1 | 1 | 1 |
| 浅色图片名片 | 1 | 1 | 1 |
| 深色图片名片 | 1 | 1 | 1 |

中文 6 张也重新生成，保证 18 张来自 manifest 记录的同一 source commit 和同一组语义实体。source commit
是生成资产前已提交的代码/文案状态；生成后的 PNG 与 manifest 在后续资产提交中一并纳入版本控制。

### 7.2 数据、场景与确定性

- 设置页使用 `frontend/dev.html` 与 `frontend/src/dev/mockBridge.ts` 的正式 capture mode。
- capture mode 仅用于开发截图，必须隐藏 dev toolbar，并显式固定 locale、场景、主题、时钟与随机种子。
- 正式 manifest 为每张设置页记录 scenario ID、locale、theme、viewport、DPR、捕获目标/滚动步骤与输出路径。
- 三语捕获前由 harness 创建全新 browser context，清空 storage，并重置到同一语义场景；不得依赖上一次交互。
- 演示实体使用跨语言中性的稳定标识，如 `Tokyo-01`、`Osaka-02`、`operator-01`；三语“同一数据”指相同
  实体、数值和状态，不要求 locale 文案字节相同。
- 地址使用 `example.com`；账号、玩家、服务器、状态数据均为演示值。
- 不连接真实服务器，不读取真实账号、群、Token、密码或审计数据。
- 四张设置页图片保持现有正式图片的深色主题与内容职责。
- 两张名片使用同一虚构玩家数据，主题分别为 light/dark。

### 7.3 设置页生成与 scale 契约

18 张资产统一由 `python scripts/capture_docs_assets.py --source-commit <sha>` 生成；设置页部分只允许由它
调用 `frontend/scripts/capture-docs-screenshots.mjs`。前端捕获实现使用
`frontend/package-lock.json` 锁定的 Playwright/Chromium 版本，并在拍摄前等待应用稳定与
`document.fonts.ready`；脚本启动后必须断言 `window.innerWidth`、`window.innerHeight`、
`window.devicePixelRatio === 2`、`visualViewport.scale === 1`、当前 locale 和主题。

- 浏览器 zoom：`100%`
- 常规设置页 CSS viewport：`1100×960`
- onboarding CSS viewport：`1100×600`
- `deviceScaleFactor`：`2`
- 禁止通过缩小字体、浏览器 zoom 或 DPR 塞入英文长文案
- 常规设置页物理 PNG：`2200×1920`
- onboarding 物理 PNG：`2200×1200`
- README：`width="100%"`，以 2× 像素密度呈现 1× 布局
- 不允许截图后拉伸或二次缩放；仅允许无损 PNG 优化

英文长文案需要自然换行；若相同语义场景在固定高度内无法完整展示，先精炼文案或调整场景滚动位置，不降低 scale。

### 7.4 图片名片生成与 scale 契约

- 通过仓库内正式导出入口调用真实 `build_me_card_html`、对应 locale 和生产 HTML render 参数生成。
- 保持 renderer 的 `zoom: 2` 与原生 `1008px` 输出宽度；高度由内容、字体和自然换行决定，不强凑
  `900px`。六张图片各自的原生高度写入 manifest 并由 IHDR 测试锁定。
- 不固定高度、不裁切、不补边、不做浏览器二次截屏或重采样。
- README 继续以 `width="49%"` 并排展示 light/dark。

### 7.5 人工目检

每张图片分别检查：

- 原图 100% 下的字体、抗锯齿、缺字、豆腐块与裁切
- 约 820px README 内容宽度下的正文、标签与按钮可读性
- 目标语言正确，无 raw key、未插值 `{placeholder}` 或错误 fallback
- 英文界面除品牌字标、母语语言名和真实输入别名白名单外无中文 UI 文案；中性演示数据不含中文
- 日文界面无来自简中词典的整句 fallback；共享汉字与日文标点不作为泄漏证据
- 三语场景、数据、主题、裁切与布局 scale 一致
- 不含真实敏感数据

### 7.6 截图 manifest

`docs/images/screenshots.manifest.json` 至少记录：

- schema version、source commit、生成命令、Node/Playwright/Chromium 版本
- 每张图片的 locale、kind、scenario、theme、viewport、DPR、zoom、像素宽高
- 图片 SHA-256；设置页额外记录 capture target/滚动步骤，名片额外记录 renderer scale

source commit、18 张路径、SHA-256 与当前文件必须一致。CI 默认校验 manifest、哈希、IHDR 与映射，不做
跨平台像素级重建比较；正式资产仍必须由同一锁版本命令生成并完成 §7.5 人工目检。

## 8. 自动测试设计

### 8.1 新增 `tests/unit/docs_i18n_test.py`

使用显式 manifest 描述四个文档族及三种语言，禁止用宽泛 glob 把内部 spec/plan 纳入。

测试职责：

1. **文件与编码**
   - 12 份文档存在
   - UTF-8、LF、无 BOM

2. **语言导航**
   - 每份文档包含且只包含一组规范语言导航
   - 当前语言不可点击，另外两项指向正确同族文件

3. **结构平行**
   - 同族三语逐项比较有序 `(heading level, stable ID)`，不只比较级别序列
   - 每个显式 anchor 紧邻其标题、文件内唯一，三语集合和顺序一致
   - fenced block 的数量与语言标签序列一致
   - Markdown 表格比较数量、列数、数据行数与 manifest 指定的稳定首列技术键
   - Markdown 解析必须忽略 fenced code，并正确处理 escaped pipe 与 inline code，不能用逐行 `split("|")`

4. **链接完整**
   - 相对文件路径存在
   - 仓库内 fragment 必须命中目标文件的显式稳定 ID
   - 日英文档不链接中文子文档（语言导航除外）

5. **技术 token**
   - 按“文档族/稳定章节”建立必需命令、配置键、endpoint、环境变量 manifest
   - 每种语言必须在相同文档族与章节命中，禁止跨 README/configuration/commands 聚合抵消遗漏
   - 不要求三语自然语言逐字相同

6. **截图映射**
   - 三语 README 各自引用 6 张正确语言图片
   - 通过 PNG IHDR（标准库读取）锁定设置页固定尺寸、名片原生宽度与 manifest 记录高度
   - 校验 manifest schema、统一 source commit、路径、SHA-256、locale、场景、主题、scale 与实际文件
   - Banner/Logo 仍引用共用资产

7. **残留与占位符**
   - 英文只扫描解析后的 prose 节点；允许精确白名单中的真实输入别名、品牌字标与母语语言名，不做
     对整份 Markdown 的粗暴 CJK 零容忍
   - 日文使用维护在测试中的“简中源整句/高风险短语”清单加人工校对；共享汉字与 `、。` 等日文标点不报错
   - `TODO`、`TBD`、`待翻译` 只在 prose 节点禁止；命令 metavariable、代码与合法模板语法不视为残留

### 8.2 保留 `tests/unit/readme_test.py`

- 中文内容锚继续作为功能与安全事实的强回归门。
- Phase 3 只为导航/显式 anchor 做必要的兼容调整，不把中文断言迁到翻译文本。

### 8.3 运行时校对测试

若受限校对修改日英运行时词典：

- 后端三词典键集/placeholder 集严格相等
- 前端三词典键集/placeholder 集严格相等
- 被修正文案的组件或 formatter 增加精确回归断言
- zh-CN 输出不变

## 9. 验收与发布门禁

### 9.1 自动门禁

- `python -m pytest -q -p no:cacheprovider tests/unit/readme_test.py tests/unit/docs_i18n_test.py`
- 全量 `python -m pytest -q -p no:cacheprovider`
- `ruff check .`
- `mypy palworld_terminal`
- `lint-imports`
- `npm --prefix frontend run test:run`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build`
- `npm --prefix frontend run verify:bundle`
- 截图 manifest/路径/SHA-256/IHDR 校验
- `git diff --check`

若未修改运行时/前端源码，生产 bundle 必须 no-drift；若受限校对修改前端词典，必须提交对应重建产物并证明重复构建无漂移。

### 9.2 文档人工验收

- 逐份通读日英 README、configuration、commands、CONTRIBUTING。
- 对照运行时词典检查核心术语与聊天输出示例。
- 从每份文档完整走一遍中→日→英→中的导航闭环。
- push 前使用 GitHub GFM API 复核生成 HTML；Draft PR 创建后再在 GitHub 文件页完整复核目录、anchor、
  表格、代码围栏、相对链接和图片。
- 18 张图片按 §7.5 全数目检。

### 9.3 完成定义

以下任一情况存在时，不得称 Phase 3 完成：

- 任一语言缺文档、缺章节、缺安全告知或缺截图
- 日英页面的正文链接意外落到中文
- fragment、图片或已完成联网复核的外部链接失效；临时网络不可用必须记录为待验收，不能假报通过
- 技术 token 被翻译或误改
- 英文/日文截图靠缩放字体或 zoom 才能容纳
- 图片包含真实敏感数据
- 任一自动门禁失败

## 10. 失败处理

- **英文过长**：先改写为自然、简洁的英文，再调整 manifest 中的捕获滚动位置；禁止降低 zoom、字体或 DPR。
- **anchor 冲突**：修正显式稳定 ID；不依赖语言相关 auto-slug 猜测。
- **文档与运行时术语冲突**：以已发布运行时词典为基准；若词典明确错误，按 §6.4 受限修复并补测试。
- **结构不平行**：补齐缺失章节/表格/代码围栏，不通过放宽测试掩盖。
- **截图泄密或状态漂移**：丢弃整组并从全新 context、固定时钟/随机种子的 capture mode 重新生成。
- **固定 scale 下裁切**：精炼文案或选择同语义完整视图；禁止后期拉伸。

## 11. 非目标

- 翻译 `docs/superpowers/**` 内部设计史与实现计划
- 翻译 `_conf_schema.json`、开发日志、代码注释或 AstrBot register 描述
- 引入文档站点、自动翻译服务、gettext 或第三方 i18n 框架
- 按群/按服语言
- 重构 Phase 1/2 的 locale 架构
- 为 Banner/Logo 制作语言变体
- 借文档翻译扩展新功能、配置项或权限行为

## 12. 实施顺序

1. 建立三语文档 manifest、失败测试、语言导航与全标题显式 anchor 骨架。
2. 完成英文四文档族，做技术 token/链接/安全语义校对。
3. 完成日文四文档族，做术语与简中残留校对。
4. 冻结运行时校对 key 清单；只对清单内的 Phase 1/2 日英语句做受限一致性校对。
5. 实现并验证 capture mode、锁版本截图入口与截图 manifest。
6. 提交代码/文案 source commit，从该 commit 与同一语义演示数据生成 18 张正式图片。
7. 更新图片资产说明，执行结构测试、manifest 校验、全量门禁与三语人工验收。
