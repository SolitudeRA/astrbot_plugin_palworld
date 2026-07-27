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
- 18 张正式截图来自同一 commit、同一演示数据、同一布局 scale；原图与 README 实际展示宽度下均清晰可读。
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

`docs/images/README.md` 扩展为三语资产矩阵，记录来源、scale、尺寸、演示数据政策与复现步骤。

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
- 可以在被跨文档引用的标题前新增显式稳定 anchor，但不能移除既有标题。

### 5.2 跨语言稳定 ID

所有被文档内部或跨文档引用的章节使用语义化英文 ID，例如：

- `first-setup`
- `world-mode`
- `permissions`
- `server-admin`
- `plugin-page`
- `feature-groups`
- `degraded-behavior`

三语同一章节使用同一 ID；标题文本正常翻译。链接优先指向显式 ID，不依赖日文/英文标题的 auto-slug。

### 5.3 唯一性

- 同一文件内显式 ID 不重复。
- 相对链接的 fragment 必须存在于目标文件。
- 不使用 GitHub 私有或非标准扩展生成 anchor。

## 6. 翻译契约

### 6.1 中文是事实规范源

- 中文决定章节职责、功能事实、安全边界和技术覆盖面。
- 日英文档结构完整平行，但允许为自然语言调整句序、段落内语序与标点。
- 不允许删去难译段落、危险操作后果、隐私告知或降级行为。

### 6.2 逐字保持的内容

下列内容不翻译、不改写：

- `/pal ...` 命令路径与参数 token
- 配置键、JSON/YAML 字段、枚举存储值
- 环境变量、文件路径、模块名、类/函数名
- REST endpoint、URL、版本号
- shell 命令与可执行代码
- 产品名 `PalWorldTerminal`、`AstrBot`、`Palworld REST API`

代码围栏中的自然语言输出示例可按 locale 翻译；可执行命令和技术 token 必须保持。

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

中文 6 张也重新生成，保证 18 张来自同一代码版本和演示数据。

### 7.2 数据与场景

- 设置页使用 `frontend/dev.html` 与 `frontend/src/dev/mockBridge.ts` 的确定性演示数据。
- 三语捕获前重置到相同场景，不依赖上一次浏览器交互残留。
- 地址使用 `example.com`；账号、玩家、服务器、状态数据均为演示值。
- 不连接真实服务器，不读取真实账号、群、Token、密码或审计数据。
- 四张设置页图片保持现有正式图片的深色主题与内容职责。
- 两张名片使用同一虚构玩家数据，主题分别为 light/dark。

### 7.3 设置页 scale 契约

- 浏览器 zoom：`100%`
- CSS viewport/capture width：`1100 CSS px`
- `deviceScaleFactor`：`2`
- 禁止通过缩小字体、浏览器 zoom 或 DPR 塞入英文长文案
- 常规设置页物理 PNG：`2200×1920`
- onboarding 物理 PNG：`2200×1200`
- README：`width="100%"`，以 2× 像素密度呈现 1× 布局
- 不允许截图后拉伸或二次缩放；仅允许无损 PNG 优化

英文长文案需要自然换行；若相同语义场景在固定高度内无法完整展示，先精炼文案或调整场景滚动位置，不降低 scale。

### 7.4 图片名片 scale 契约

- 通过真实 card renderer 加载对应 locale 后生成。
- 使用 renderer 原生 `1008×900` PNG，不做浏览器截屏或重采样。
- README 继续以 `width="49%"` 并排展示 light/dark。

### 7.5 人工目检

每张图片分别检查：

- 原图 100% 下的字体、抗锯齿、缺字、豆腐块与裁切
- 约 820px README 内容宽度下的正文、标签与按钮可读性
- 目标语言正确，无 raw key、`{placeholder}` 或错误 fallback
- 英文无中文展示串；日文无简中整句残留
- 三语场景、数据、主题、裁切与布局 scale 一致
- 不含真实敏感数据

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
   - 同族三语的标题级别序列一致
   - 显式 anchor ID 集合一致且文件内唯一
   - fenced block 的数量与语言标签序列一致
   - Markdown 表格数量与列数序列一致

4. **链接完整**
   - 相对文件路径存在
   - fragment 命中目标文件的显式 ID，或中文保留标题的既有兼容目标
   - 日英文档不链接中文子文档（语言导航除外）

5. **技术 token**
   - 将现有中文守卫中的命令、配置键、endpoint、环境变量等语言无关 token 应用于三语文档聚合
   - 不要求三语自然语言逐字相同

6. **截图映射**
   - 三语 README 各自引用 6 张正确语言图片
   - 通过 PNG IHDR（标准库读取）锁定像素尺寸
   - Banner/Logo 仍引用共用资产

7. **残留与占位符**
   - 英文正文剔除语言导航后不含 CJK
   - 日文不做汉字零容忍；使用简中整句/中文标点守卫加人工校对
   - 三语禁止 `TODO`、`TBD`、`待翻译`、模板占位残留

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
- `npm run test:run`
- `npm run typecheck`
- `npm run build`
- `npm run verify:bundle`
- `git diff --check`

若未修改运行时/前端源码，生产 bundle 必须 no-drift；若受限校对修改前端词典，必须提交对应重建产物并证明重复构建无漂移。

### 9.2 文档人工验收

- 逐份通读日英 README、configuration、commands、CONTRIBUTING。
- 对照运行时词典检查核心术语与聊天输出示例。
- 从每份文档完整走一遍中→日→英→中的导航闭环。
- 在 GitHub Markdown 渲染中复核目录、anchor、表格、代码围栏和图片。
- 18 张图片按 §7.5 全数目检。

### 9.3 完成定义

以下任一情况存在时，不得称 Phase 3 完成：

- 任一语言缺文档、缺章节、缺安全告知或缺截图
- 日英页面的正文链接意外落到中文
- fragment、图片或外部链接失效
- 技术 token 被翻译或误改
- 英文/日文截图靠缩放字体或 zoom 才能容纳
- 图片包含真实敏感数据
- 任一自动门禁失败

## 10. 失败处理

- **英文过长**：先改写为自然、简洁的英文，再调整捕获滚动位置；禁止降低 zoom、字体或 DPR。
- **anchor 冲突**：修正显式稳定 ID；不依赖语言相关 auto-slug 猜测。
- **文档与运行时术语冲突**：以已发布运行时词典为基准；若词典明确错误，按 §6.4 受限修复并补测试。
- **结构不平行**：补齐缺失章节/表格/代码围栏，不通过放宽测试掩盖。
- **截图泄密或状态漂移**：丢弃整组并从重置后的确定性 mock 重新生成。
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

1. 建立三语文档 manifest、失败测试、语言导航与显式 anchor 骨架。
2. 完成英文四文档族，做技术 token/链接/安全语义校对。
3. 完成日文四文档族，做术语与简中残留校对。
4. 对截图涉及的 Phase 1/2 日英语句做受限一致性校对。
5. 从同一 commit、同一演示数据生成 18 张正式图片。
6. 更新图片资产说明，执行结构测试、全量门禁与三语人工验收。
