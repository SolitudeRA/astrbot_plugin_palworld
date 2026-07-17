# 命令输出重设计 Design Spec（追认式）

日期：2026-07-17
分支：feat/command-output-redesign（叠于 fix/gamedata-unavailable-lock 之上，锁定分支先行合并）
状态：设计定稿。逐条样张经交互定稿（6 条）+ 批量补齐（23 条），两轮对抗复核清零（一轮四棱镜 32 发现全修；二轮四新棱镜 12 major 全确认 + 13 minor 全采）。

## 0. 背景与定位

/pal 命令族现有输出为 v0.1 时代的朴素平文：无视觉锚点、字段直出（含内部哈希键与 epoch）、措辞多源漂移、占位假数据（恒 0 字段照渲染）。本 spec 把全部 **29 条命令** 的输出与横切回执面（拦截/降级/usage/错误）重做为「纯文本精装」体系：少量语义 emoji、统一原子规范、逐条自由设计。

**命令全集（29，command_registry.PAL_COMMAND_STRINGS）**：world status/overview/rules/events/today · guild list/info/bases/base · player info/bind/unbind · server announce/save/kick/unban/ban/shutdown/stop · link list/add/remove · rank · online · me · help · whoami · whereami · confirm。

## 1. 范围与非目标

**范围内**：formatters.py / locale.py 全量输出改写；为供数所需的后端小扩（§5 汇总）；捎带 bug 修（§6）；locale 键表增删（§7）；文档行为措辞同步（§8）；测试改写（§9）。

**非目标 / 明确不动**：
- 门控语义零改动：admin 硬门先于 feature 门的铁律、visible_actions 唯一谓词、confirm claim-then-execute、name_banned 收敛判定逻辑本身。
- routing resolve 六分支文案沿用（PR#22 已精修）：no_server_configured / single_not_authorized / server_unknown / not_authorized / active_server_stale / no_server_resolved——素文不加图标（六者为解析/授权失败，非换场景可解）。private_restricted 例外，见 §3。
- setup_required 文案沿用（🔧 引导已达标）；link_single_mode 沿现句素文（落点 main._link_dispatch）。
- gamedata 上游锁定**无专属聊天文案**（沿锁定 spec）：锁定家族与普通 enable off 同回 feature_disabled 主句；差异仅在脚注省略（§3）。
- /pal help 的 topic 参数维持忽略（不扩 /pal help <组>）；ConfirmationStore 不改（超时与无 pending 靠文案并句说明）。
- 前端设置页不动（help 组头词表向前端 GROUP_LABELS 靠齐，改的是后端 _GROUP_LABEL）。
- 版本号不在本 spec 内定（随发版决策）。

**现实提示**：#10-12/#23/#25 所属 players 组默认关闭，样张为开启后形态；默认装机 guest 可用面 = world×4（status/rules/events/today）/ online / link list / help / whoami / whereami。guild 组当前随 gamedata 上游锁定不可达，其样张为上游恢复且组启用后的形态——落码即备，恢复即生效。

## 2. 原子规范

1. **标题锚点**：查询类输出首行 `图标 命令名 · 主体名`。图标表：🌍 world status / 🗺️ overview / 📜 rules / 📰 events / 📅 today / 🏰 guild / 🏕️ 据点 / 👤 player·me / 🏆 rank / 👥 online / 🔗 link / 📖 help / 🪪 whoami / 📍 whereami。
   **锚点数据源**：统一 = 插件配置名 `srv.name`（与 @override/link/server 回执/whereami 同一词汇——`_ready_by_name` 按 server_id≡name 匹配，标题可直接复制进 `@` 使用）。供数 = commands 层 resolve 出的 srv 作 formatter 参数，**不扩 DTO**。游戏内 servername（world.server_name）降格为 status 副信息，不作锚点（顺带消 normalizer 默认空串的「· 」空尾风险）。**本 spec 样张中「Palpagos」均为示意，落地渲染配置名**。
2. **状态色点**：🟢 正常 · 🟡 注意 · 🔴 异常。佩点域：性能档位 / 服务器可达态（🟢 在线 / 🔴 离线 / 🟡 未就绪）/ 健康度。玩家仅 🟢 标在线，**离线不佩点**（离线是常态缺席非异常）。回执图标 ✅ / ⚠️ / ❌ 只作整条回执头，**不作节头**。
3. **结构**：一级 `· `；嵌套缩进两空格；脚注行 `└ `，三类=免责/引导/回执补充信息（参数回显、生效细节），**一条为限**；空行分节；节头素文无图标；禁用空格列对齐与横线装饰；**不放数据时效脚注**（降级态的「最后成功于」是诊断信息，保留在状态行内）。
4. **数字与时长**：Lv{n}；时长「N天N时 / N时M分」全局统一（废「N小时M分」与「12 小时」聚合式）；有小时段分钟两位补零（21时05分），不足 1 时只写「45分」；百分比整数；FPS 整数；帧时间 {:.1f}ms；倍率 1.0x；绝对日期 YYYY-MM-DD。
5. **相对日期**：三档词形 今天 / 昨天 / MM-DD（跨年 YYYY-MM-DD）。携时分场景：**时间戳字段**（最后在线/最近观察）全档带 HH:MM；**events/today 节内条目**仅今天条目带 HH:MM（节头承载日期）。
6. **推导标三档**：`（推导）` / 计数级 `~` 前缀（仅成员数类观测计数）/ 不标注（官方数据默认不标）。免责脚注正字「插件观察推导」。首见时间分工：玩家=「首次现身」，公会/据点=「首次观察」。
7. **折叠纪律**：单位=**单列表 7 条**，尾行 `…等共 N 条`（量词随实体：人/条/项）。events 为消息级特例（多日节合计 7）；today 为节级（每节 7，满编 ~35 行接受，实测超限再收）。rank 榜长由 rank_top_n 独占（不受折叠约束），parse 层补 clamp 1–50、0/负回默认 5。折叠上限为独立配置键，5 落点清单见 §5.8。
8. **正字表**：找不到统一「未找到」；未绑定统一「你还没有绑定玩家」；strict 停用句统一句形「{模块}在 strict 隐私模式下停用」。
9. **空态/错误态分派（可判定式）**：**具体目标已定位但其数据缺失**（rules 快照 / overview 快照 / 单据点观测）= ⚠️ 取数失败态；**集合级列举结果为空**（无公会/无在线/无事件）= 素文空态（标题锚点+一句话+可选引导）；错误 = ❌/⚠️ + 原因 + 怎么办。全部收敛 locale。

## 3. 横切决策表

**图标与语气分派**
- ✅ 成功回执 · ⚠️ 拦截/待确认/部分成功 · ❌ 执行失败/找不到目标 · 素文 = usage 与中性通知（无待确认、未绑定、无授权记录等「中性无操作」）。
- 场景/环境不符类拦截统一 ⚠️：`⚠️ 该命令仅可在群聊中使用`（link add/remove 共用 use_only_group 同键同待遇）、whoami/whereami 取不到标识、**private_restricted**（文案沿 PR#22 句仅加 ⚠️ 前缀；从 routing 素文豁免中摘出的唯一分支）。
- **配置停用类拦截统一 ⚠️**：整命令被拒执行的停用主句戴 ⚠️——feature_disabled 与 strict 隐私停用同构（#23 时长榜 / #8 #9 据点模块三处适用）。**边界**：strict 下输出仍产出的字段级裁剪（online/me 砍时长）与正常输出附注（rules 尾注）保持素文——分界=命令是否被拒执行。
- admin_required → `⚠️ 该命令需要管理员权限`。feature_disabled → `⚠️ 该功能未开启` + `└ 管理员可在插件设置页「权限」章开启`；**upstream_unavailable(path) 时省略该脚注**（锁定期设置页开不了，防假承诺；主句仍同句，维持锁定 spec「无专属聊天文案」决策）。
- busy → `⚠️ 插件正在重载配置，请稍后重试`（收编 locale）；ArgError → `⚠️ 一条命令只能指定一个 @服务器`（收编 locale，三处同串归一；第四处 help 裸抛经「help 跳过 parse_arg」根治，见 #26）。

**降级态（三落点）**
- 全局统一式：`🔴 当前无法获取世界数据 · 最后成功于 N 分钟前` / 从未成功 `🔴 尚未成功连接过服务器，请检查「连接」配置`。
- 降级态标题锚点全局统一 `🌍 世界状态 · {服务器名}`，不随发起命令变化（避免 14 图标×降级组合爆炸）。
- 三落点：① formatter（format_degraded 扩 server_name 参数）；② query 层 stale 供数——现状「N 分钟前」为**死分支**（degraded⇔metric is None，last_ok 恒 None），须新增 metric.observed_at 新鲜度判定：超阈值 → degraded=True 且 last_ok=observed_at；③ commands._resolve_world 的 world=None 分支（恒「从未成功」句），传 res.server.name。
- **新鲜度阈值定案**：polling.metrics_seconds × 3 + 60s 余量，纯派生不新增配置键；status stale 与 link list 可达性共用同一 helper（假 clock 边界测试）。

**据点名口径**
- 写侧无赋名路径（display_name 恒 None → BASE-n 占位）；样张中「海岸木材场」类据点名均为示意。
- BASE-n 编号、#8 列表序号、#9 #序号查找、events/today/guild info 解析**全部基于同一张 `list_bases(include_low=True, hidden 排除)` 清单**（_bases_indexed 改传 include_low）。hidden 据点不入清单，事件解析对其走「查无回退『据点』」（不泄漏 hidden 名号）。BASE-n 为位次占位名，据点增减致历史事件序号漂移属固有语义。

**多模式账号状态族带服务器锚**
- bind/unbind/me hide/show/未绑定态补服务器锚或句内带服：player_bindings 与 hidden 均 world 级状态，切活动服后「已绑定」vs「还没绑定」两条消息否则互相矛盾；me hide 现措辞是全局承诺、实为单服生效。单模式省略（world_mode 判定与 help 尾注同源）。#10 player info 同判（查询按当前活动服）。

**隐私收敛（status/online 两入口一次堵死）**
- excluded/hidden 名字级收敛剔除**下沉 _online_rows**，status「在线玩家」节与 online 名单共用（修现状两处均不剔隐藏玩家、/pal me hide 承诺落空的缺陷）。
- 头行在线数分子 = 收敛后名单数（与折叠尾行 N 同源、与名单行数必须同数）；容量 /32 与今日峰值取 metric 聚合值（不可归因，保留）。

## 4. 逐条定稿（29 条）

### 4.1 world status

```
🌍 世界状态 · Palpagos
第 42 天 · v0.6.5 · 已运行 6天9时

在线 2/32 · 今日峰值 7
性能 🟢 流畅 · FPS 58 · 帧时间 17.2ms
据点 5

在线玩家
· Neo Lv21
· Trinity Lv18
```

降级态（一行）：`🔴 当前无法获取世界数据 · 最后成功于 25 分钟前`；从未成功：`🔴 尚未成功连接过服务器，请检查「连接」配置`。

规则：版本/运行时长来自 StatusDetail（现成）；性能状态点=流畅度档位（流畅🟢/一般🟡/卡顿·严重卡顿🔴）；据点独立行（guilds_bases 组关闭时整行消失）；玩家列表轻条目（名+Lv，Ping/时长归 online）；>7 人折叠 `…等共 N 人`；0 人省略该节；不放 description。**在线玩家节走 §3 隐私收敛**；头行分子=收敛后名单数；降级供数见 §3 三落点。

### 4.2 world overview（上游恢复后生效）

```
🗺️ 世界概览 · Palpagos
第 42 天 · 在线 2/32

居民
· 角色 12 · NPC 45
· 帕鲁 随行 38 · 工作 102 · 野生 361

设施
· PalBox 8 · 公会 5 · 据点 5

野生帕鲁 Top（当前快照）
· 疾风隼 ×24
· 棉悠悠 ×18
```

规则：定位=人口普查，**FPS 两行删除**（性能归 status）；在线 x/32 用 latest_metric.max_players；快照缺失不再静默全 0 → `⚠️ 尚未获取到世界快照，稍后再试`（取数失败态）；strict 下 PalBox **项**省略（该行保留公会/据点两计数）；据点数=latest_metric.basecamp_count（官方口径，与 status 同源）。

### 4.3 world rules

```
📜 世界规则 · Palpagos

模式
· 难度 普通 · 硬核 关闭
· 死亡惩罚 掉落物品 · 帕鲁永久死亡 关闭
· PVP 伤害 关闭 · 友军伤害 关闭
· 入侵者袭击 开启

倍率
· 经验 1.0x · 捕获 1.2x
· 工作速度 1.0x · 帕鲁刷新 1.0x
· 白天流速 1.0x · 夜晚流速 1.0x

节奏
· 蛋孵化 72 小时 · 空投间隔 180 分钟

上限
· 玩家 32 · 公会成员 20
· 据点 每公会 4 · 全服 128
```

取数失败态（⚠️ 归错误态）：`📜 世界规则 · Palpagos` + `⚠️ 尚未从服务器获取到规则数据，稍后再试`。
隐私模式注（两种模式两句分叉，勿混）：strict → `└ strict 隐私模式下据点模块停用`；advanced → `└ advanced 隐私模式暂按 balanced 生效`。

规则：策展分节（模式/倍率/节奏/上限），同类字段两两并一行（`A · B`）；**剔除**服务器技术字段（端口/RCON/REST API/日志格式/认证/备份/聊天限速/跨平台）与长尾细倍率（帕鲁·玩家攻防、饱食度/耐力/生命恢复、建筑/采集/掉落细项）；rules() 读 settings 全量快照，字段现成，只动 formatter/query 策展清单；未知枚举值原样回退兜底不动。

### 4.4 world events

```
📰 世界事件 · Palpagos

今天
· 14:32 Neo 升级 Lv21→Lv22
· 09:15 在线人数新纪录 8 人

昨天
· 新玩家 Trinity 加入世界
· 据点「海岸木材场」工作帕鲁 12→18

07-14
· 新公会「Matrix」出现
· 世界迎来第 100 天
```

today 变体（`events today`，不设节头）：`📰 今日事件 · Palpagos` + 直列条目带 HH:MM。
空态：`📰 世界事件 · Palpagos` + `最近还没有新事件`（today 变体：`今天还没有新事件`）。

八类措辞（events/today/guild info 三处同源单一真相）：

| 事件 | 措辞 |
|---|---|
| 玩家升级 | `{name} 升级 Lv{old}→Lv{new}` |
| 新玩家 | `新玩家 {name} 加入世界` |
| 新公会 | `新公会「{name}」出现` |
| 新据点 | `新据点「{name}」确认` |
| 据点消失 | `据点「{name}」疑似消失（连续多次未观察到）` |
| 工作帕鲁增减 | `据点「{name}」工作帕鲁 {prev}→{cur}` |
| 天数里程碑 | `世界迎来第 {m} 天` |
| 在线纪录 | `在线人数新纪录 {value} 人` |

规则：**主体名批量解析为本条 query 层扩**（player_key/guild_key/base_key→显示名；现状 PLAYER_LEVEL_UP/NEW_PLAYER 无名、NEW_GUILD/NEW_BASE 直出内部 subject_key）；隐藏玩家（excluded keys）事件 query 层跳过（与 rank 名字级收敛同哲学）；据点解析用 §3 同源清单；日分组 day_bounds 同源（per-server tz/DST 安全）；仅今天条目带 HH:MM；折叠=消息级合计 7 条；据点/公会事件锁定期写侧不产，渲染规则照落地上游恢复即生效；「疑似消失」不另加（推导）标。

### 4.5 world today

```
📅 今日日报 · Palpagos · 2026-07-17

第 42 → 45 天 · 活跃玩家 3 · 峰值在线 7 · 累计在线 12时40分

今日纪录
· 世界迎来第 100 天
· 在线人数新纪录 8 人
· 新玩家 Trinity 加入世界
· 新公会「Matrix」出现

玩家成长
· Neo 升级 Lv21→Lv22
· Trinity 升级 Lv17→Lv18

据点变化
· 新据点「海岸木材场」确认
· 据点「河谷矿场」工作帕鲁 12→18

今天：1 名新玩家加入，2 次成长，2 处据点变化。
```

空态：`📅 今日日报 · Palpagos · 2026-07-17` + `平静的一天，没有新事件`。

规则：分节=素节头无图标；措辞与 §4.4 事件表全同源；去重=今日纪录只收里程碑/在线纪录/新玩家/新公会，据点类全归「据点变化」节；名字解析与 events 共用同一解析器，**但 today 落点=ReportService 非 query 层**（records 现为应用层 f-string 预渲染串直出 subject_key；DailyReport 需条目结构化+名字在 report_service 内解析；解析器抽为 events/today 两处可达的共享 helper——挂 Repository 或独立 resolver）；隐藏玩家跳过；每节折叠 7（today 为节级特例）；据点变化节 gamedata 锁定期自然缺席（既有屏蔽）；末行编辑部总结保留。
**捎带 bug 修**：report_service.py:164-165 把日窗口 epoch 秒存进 world_day_start/end → 实机直出「第 1752624000 → … 天」。修法：窗口内 metrics 首末 world_day（repo 小扩一条查询）。

### 4.6 guild list（上游恢复后生效）

```
🏰 公会 · Palpagos

· Matrix 成员 ~4 · 工作帕鲁 28 · 据点 2
· Zion 成员 ~2 · 工作帕鲁 9 · 据点 1
└ 公会与据点均为插件观察推导
```

规则：active_7d 恒 0 占位**砍位**；每公会据点数=list_bases 按 guild_key 分组（一条查询）；成员数保留 `~` 推导标；折叠 7；空态 `🏰 公会 · Palpagos` + `暂无公会观察数据`（集合空=素文）。

### 4.7 guild info（上游恢复后生效）

```
🏰 公会 · Matrix
成员 ~4 · 工作帕鲁 28 · 据点 2
首次观察 2026-06-28 · 最近 今天 14:30

据点
· 海岸木材场 置信度高
· 河谷矿场 置信度中

近期动态
· 新据点「河谷矿场」确认
· 据点「海岸木材场」工作帕鲁 12→18
```

规则：恒 0 占位（active_today/active_week/average_level）**砍位**；first/last_seen_at 已在 DTO 零成本渲染（相对日期词表：时间戳字段全档带 HH:MM）；「近期动态」实填=list_events 过滤该公会据点的 NEW_BASE/WORKER_DELTA/BASE_VANISHED（措辞同 §4.4 事件表）；据点列表=list_bases 按 guild_key 过滤；无参补 usage 态 `用法：/pal guild info <公会名>`（修现状「未找到公会「」」）；找不到 `❌ 未找到公会「Zion2」` + `└ /pal guild list 查看已观察公会`。

### 4.8 guild bases（上游恢复后生效）

```
🏕️ 据点 · Palpagos

Matrix
· #1 海岸木材场 置信度高 · 工作帕鲁 18
· #2 河谷矿场 置信度中 · 工作帕鲁 9

未确定公会
· #3 BASE-3 置信度低
└ 据点为插件观察推导；#序号可用于 /pal guild base
```

规则：按公会分组（guild_names 映射已在方法内）；worker_count 实填=latest_base_observation 每据点一条索引查询（现状恒 0 未渲染）；**列表含 low 置信度行**（序号空间与 #9/事件解析同源，见 §3 据点名口径）；hidden 恒不展示；折叠 7（全局）；空态 `暂无可展示的据点`；**strict 态接线死键 bases_disabled_strict**：strict 模式直接回 `⚠️ 据点模块在 strict 隐私模式下停用`（配置停用类统一 ⚠️；现状用户只见莫名空态）。

### 4.9 guild base（上游恢复后生效）

```
🏕️ 据点 · 海岸木材场
公会「Matrix」 · 置信度高

工作帕鲁 18 · 活跃 12 · 平均 Lv17.5
状态 🟢 健康 · 平均HP 92%

行为分布
· 工作中 8 · 移动 5 · 闲置 3 · 未知 2
```

规则：**「行为分布」类目=ActionCategory 8 档中文**（工作中/移动/闲置/战斗/睡觉/进食/濒死/未知——细分工种在采集归一化时已折叠，「伐木/搬运」类目数据面不存在）；health_score 翻译为状态点+词（🟢 健康 ≥75 / 🟡 一般 ≥40 / 🔴 低迷 <40）；activity_score 裸数与 palbox_count（硬编码 1）**砍位**；无观测态 `⚠️ 该据点尚无观测数据`（取数失败态，不再全 0 假数据）；**strict 守卫与 #8 同判**（bases/base 双条在 commands 层判 privacy.mode==strict，同 rank 双砍先例——strict 切换后 DB 残留据点不可经 base 详情绕出）；找不到 `❌ 未找到据点「XX」` + `└ /pal guild bases 查看列表（可用 #序号）`；无参补 usage 态。

### 4.10 player info

在线态：
```
👤 玩家 · Neo
Lv21 · 🟢 在线 · 本次 2时15分

今日在线 3时40分 · 累计 21时05分
公会「Matrix」
首次现身 2026-06-30
```

离线态：`Lv18 · 离线 · 最后在线 昨天 23:41`（次行块同上，无公会行则省）。
strict 态：砍全部时长+最后在线（rank 双砍同哲学），留 Lv/在线状态/公会/首次现身。
找不到：`❌ 未找到玩家「Neo2」` + `└ 名字须与游戏内完全一致，可用 /pal online 查在线玩家`。
缺参数：`用法：/pal player info <玩家名>`。

规则：query 层小扩三项（今日在线=day 窗口 per-player 聚合同源 rank today；累计=同源 rank total；公会名=latest_guild_key 解析，gamedata 锁定期自然缺席）；离线不佩状态点；「最后在线」用相对日期词表（时间戳字段全档带 HH:MM）；卡片与 /pal me 共用；name_banned 收敛不动；多模式作用域同账号状态族（查询按当前活动服，标题或次行补服务器锚与 #25 同判）。

### 4.11 player bind

成功（多模式带服务器锚，单模式省略）：`✅ 已绑定玩家「Neo」 · 主服` + `└ 现在可以用 /pal me 查看自己的状态了`
改绑：`✅ 已改绑到玩家「Neo」（原绑定「Trinity」） · 主服`
找不到：`❌ 未找到玩家「Neo2」，无法绑定` + `└ 名字须与游戏内完全一致，可用 /pal online 查在线玩家`
缺参数：`用法：/pal player bind <玩家名>` + `└ 绑定后可用 /pal me 查看自己的状态`

规则：改绑透明化=小扩（upsert 前 get_binding 查旧绑定，同名重绑不啰嗦直接 ✅）；not found 脚注与 player info 共用同一 locale；隐藏玩家 not found 收敛不变；脚注一条为限。

### 4.12 player unbind

成功（多模式带锚）：`✅ 已解除绑定 · Neo · 主服` + `└ 重新绑定用 /pal player bind <玩家名>`
未绑定：`你还没有绑定玩家，无需解绑`（素文）
悬空绑定：`✅ 已解除绑定 · 主服`（**不渲染 player_key 哈希**——修现状「已解除你与玩家「abc123hash…」」；单模式去锚）

### 4.13–4.19 server 写命令（announce/save/kick/unban/ban/shutdown/stop）

成功回执统一式 `✅ 动作短语 · {server}`（**用上目标**，修现状不显示目标）：
- announce：`✅ 公告已广播 · 主服务器` + `└ "今晚 10 点维护重启"`（回显内容）
- save：`✅ 已执行存档 · 主服务器`
- kick：`✅ 已踢出 Neo（…1234） · 主服务器`
- unban：`✅ 已解封 …1234 · 主服务器`
- ban：`✅ 已封禁 Neo（…1234） · 主服务器`（有理由加 `└ 理由：刷屏`）
- shutdown：`✅ 已发出关服指令 · 主服务器` + `└ 60 秒后关服 · 公告："服务器维护"`
- stop：`✅ 已停止服务进程 · 主服务器`
- 断连已发起（仅 shutdown/stop）：`✅ 指令已发出 · 主服务器` + `└ 服务器连接已断开，按已生效处理`

失败：`❌ 关服失败 · 主服务器` + `└ {error}`；resolve 失败：`❌ 无法执行：{reason}`。
目标族：`❌ 未找到在线玩家「Neo2」` + `└ 离线玩家可用 steam_ userid 直接指定`；同名多命中 `⚠️ 「Neo」有多个同名在线玩家` + 候选行 `· Neo（…1234）` + `└ 用 steam_ userid 精确指定`；`❌ 无法获取在线玩家列表（服务器可能不可达），请稍后重试`。
usage 修正：全部用英文子命令（修「/pal server 踢出」不通顺），如 `用法：/pal server kick <玩家名|steam_userid> [理由]`；unban 加本地 steam_ 前缀校验 `❌ userid 须以 steam_ 开头`（零成本防不透明 REST 错误）。
二次确认预览：`⚠️ 待确认 · 封禁 Neo（…1234） · 主服务器` + `└ 30 秒内发送 /pal confirm 执行，逾期自动作废`（shutdown 变体 `关服（60 秒倒计时）`；stop 变体 `停止服务`）。

**小扩标注**：AdminResult.params 补 target_userid（_execute 已持有；现状 params 无 userid，unban 恒不传 target_name、steam_ 直传时 name=None——`…1234` 尾4 否则无数据可填）。此项为 AdminService 小扩非纯渲染。

### 4.20 link list

```
🔗 已配置服务器

· 主服 🟢 在线 · 本群已授权 · 当前活动
· 备用服 🔴 离线 · 本群未授权
· 测试服 🟡 未就绪 · 本群未授权

无效配置
· bad name（名称含非法字符）
```

规则：状态点三态——🟢 在线 / 🔴 离线（就绪但不可达）/ 🟡 未就绪（配置不完整）；**🟢/🔴 之分为后端小扩**：现状 online≡ready（纯配置谓词），可达性按该服当前 world 的 latest_metric.observed_at 新鲜度派生（§3 同一阈值同 helper）；**私聊时授权段省略**；skipped 段仅管理员可见、节头素文「无效配置」，reason 中文化（empty=名称为空 / duplicate=名称重复 / illegal_char=名称含非法字符 / no_credential=缺少凭据）；空态 `尚未配置 Palworld 服务器` + `└ 在插件设置页「连接」章添加`（**拆键 link_list_empty**，routing 的 no_server_configured 保持原素文）；折叠 7。

### 4.21 link add

成功：`✅ 已授权本群 · 主服（设为当前活动）`（统一用 srv.name——语义卫生项：server_id 构造恒等于 name，非缺陷修复）
换活动服务器时：+ `└ 原活动服务器「备用服」已替换`
不存在/未就绪：`❌ 服务器「XX」不存在或未就绪` + `└ /pal link list 查看可用名称`（**拆键 link_add_unknown**，routing 的 server_unknown 保持素文）
私聊：`⚠️ 该命令仅可在群聊中使用`；usage 拆分：`用法：/pal link add <服务器名>`

**小扩标注**：本条三项（旧活动替换脚注/显示名/成败区分）非纯渲染——RoutingService.use 改结构化返回 `{ok, server_id, replaced_active}`（set_active 前 get_binding_active 取旧值、仅 != 新值时填），locale 渲染上提 commands 层；连带 routing_service_use_test 断言改写。

### 4.22 link remove

成功：`✅ 已撤销本群授权 · 主服`
撤的是当前活动服务器时：+ `└ 该服务器原为本群活动服务器，后续需重新授权指定`
无授权记录：`本群没有「XX」的授权记录`（素文——中性无操作；**先查存在性，修幂等假成功**；名字命中残留记录时仍可清理）
私聊：`⚠️ 该命令仅可在群聊中使用`（与 add 共用 use_only_group 同键同待遇）
usage 拆分：`用法：/pal link remove <服务器名>`

**小扩标注**：存在性/活动态区分非纯渲染——RoutingService.unbind 改结构化返回 `{removed, was_active}`（或 revoke 返 rowcount 二选一，plan 定取舍）。

### 4.23 rank

```
🏆 今日在线时长榜 · Palpagos
1. Neo 3时40分
2. Trinity 1时05分
3. Morpheus 45分
```

total 变体：`🏆 累计在线时长榜 · Palpagos` + `└ 统计范围为数据留存期`；level 变体：`🏆 等级榜 · Palpagos`，行 `1. Morpheus Lv30`。
空榜：`🏆 {榜名} · Palpagos` + `暂无排行数据`（集合空=素文）。
strict：`⚠️ 时长榜在 strict 隐私模式下停用` + `└ 等级榜不受影响：/pal rank level`（配置停用类统一 ⚠️）。

规则：名次序号纯渲染零成本；Top-N=rank_top_n（默认 5，parse 层补 clamp 1–50）；未识别首词回落 today（现状保持）。

### 4.24 online

```
👥 当前在线 · Palpagos
在线 2/32 · 今日峰值 7

· Neo Lv21 · Ping 优秀 · 2时15分
· Trinity Lv18 · Ping 正常 · 45分
```

规则：头行分子=收敛后名单数（§3 隐私收敛；与名单行数必须同数），/32 容量=latest_metric.max_players、今日峰值=peak_online；隐私收敛下沉 _online_rows 与 status 共用；strict 砍时长字段（名/Lv/Ping 保留）；空态 `👥 当前在线 · Palpagos` + `当前无玩家在线`（收编 locale）；折叠 7 + `…等共 N 人`；排序 level 降序保持。

### 4.25 me

卡片=player info 定稿版 + 差异：标题 `👤 我的玩家 · Neo`；已隐藏角标（get_hidden_keys 一查）缀于首次现身行 `· 已隐藏`；未绑定（多模式句内带服）`你在「主服」还没有绑定玩家` + `└ 用 /pal player bind <玩家名> 绑定`（单模式：`你还没有绑定玩家`）。
hide（多模式带锚）：`✅ 已将你从「主服」的排行与查询中隐藏` + `└ /pal me show 恢复`；show：`✅ 已恢复你在「主服」的可见性`（单模式均去服名）。

### 4.26 help

```
📖 PalWorldTerminal 命令

世界
· /pal world status 世界状态
· /pal world rules 世界规则
（…各组同式）

└ 命令末尾加 @服务器名 可指定服务器
```

组头词表（与设置页 GROUP_LABELS 统一定字）：世界 / 公会 / 玩家 / 服务器管控（管理员）/ **服务器授权**（link，废「服务器选择」）/ 其他。

规则：【】组头改素节头；行式 `· /pal {路径} {描述}`；角色/功能/模式过滤逻辑零改动（visible_actions 唯一谓词）；topic 参数维持忽略，**且 help 不再走 parse_arg**（现状裸调无 try/except，尾双 @ 直接抛 ArgError 用户无回复——help 输出与 @服务器 无关，跳过解析即根治）；尾注**单模式省略**（single 下 resolve 忽略 @override，尾注是空承诺）。

### 4.27 whoami

```
🪪 我的账号标识
aiocqhttp:1234567890
└ 建议私聊使用；把标识交给管理员加入权限名单
```

已是管理员时次行加 `你已在管理员名单中`（is_plugin_admin 零查询）；取不到 `⚠️ 当前场景无法识别你的账号，请换个聊天场景再试`。

### 4.28 whereami

```
📍 本群标识
aiocqhttp:GroupMessage:123456789
本群已授权：主服（当前活动）
└ 未授权时把标识交给管理员即可开通查询
```

授权态按 access_mode 分流：restricted 才渲染授权段与脚注（多模式=list_group_servers 一查 / 单模式=single_allowed_groups 零查询）；**open 模式**改显 `当前为开放模式，无需授权即可查询`（授权名单不参与 resolve，否则输出与真实可用性相反）；**单模式 restricted 变体**：已授权=`本群已授权：主服`（无「（当前活动）」括注——active 是多模式概念），未授权沿脚注引导（设置页「连接」章授权群名单）；取不到 `⚠️ 当前场景无法识别群标识，请在群聊中使用`。

### 4.29 confirm

执行成功：`✅ 已确认执行 · 封禁 Neo（…1234） · 主服务器`
断连已发起（**修 confirm 吞「已发起」语义**）：`✅ 已确认 · 关服指令已发出 · 主服务器` + `└ 服务器连接已断开，按已生效处理`
无待确认：`当前没有待确认的操作（可能已超时作废）`（素文，超时并句说明——不改 store）
已失效：`⚠️ 该操作已失效（功能已关闭或服务器不可用），请重新发起`
执行失败：同 server 写失败式 `❌ …`

## 5. 后端小扩清单（非纯渲染改动汇总）

| # | 落点 | 内容 | 消费方 |
|---|---|---|---|
| 1 | QueryService | metric 新鲜度 stale 判定（阈值=polling.metrics_seconds×3+60s，共享 helper） | status 降级双态、link list 可达三态 |
| 2 | 共享 resolver（挂 Repository 或独立） | 事件主体名批量解析：player_key/guild_key/base_key→显示名；hidden 跳过/回退；据点用 include_low 清单 | events、today（ReportService 内）、guild info 近期动态 |
| 3 | ReportService | DailyReport 条目结构化（废 f-string 预渲染 records）+ 名字解析 + 三节分派去重 | today |
| 4 | Repository | 日窗口内 metrics 首末 world_day 查询 | today「第 X → Y 天」bug 修 |
| 5 | QueryService | player 今日在线（day 窗口 per-player 聚合）、留存期累计（同源 rank total）、公会名解析 | player info、me |
| 6 | QueryService | _online_rows 名字级收敛下沉（load_excluded_keys+name_banned） | status 在线玩家节、online |
| 7 | AdminService | AdminResult.params 补 target_userid | server 写回执尾4 |
| 8 | RoutingService | use → `{ok, server_id, replaced_active}`；unbind → `{removed, was_active}`（或 revoke 返 rowcount）；locale 渲染上提 commands 层 | link add/remove |
| 9 | commands/formatters | format_degraded 扩 server_name；_resolve_world 传 res.server.name | 降级第三落点 |
| 10 | config | rank_top_n parse 层 clamp 1–50；**折叠上限新配置键 5 落点**：_conf_schema.json 带 default（平台铁律：schema 无键装载即裁）→ config.py 解析带 clamp → config_view.py 数值类型表 → frontend schema.ts+schema.test.ts（建议挂既有 players 节白拿字段 drift 测试）→ pages/settings 产物重建 | 折叠纪律 |
| 11 | QueryService/commands | _bases_indexed 改传 include_low=True（统一序号空间） | guild bases/base、事件解析 |
| 12 | commands | guild bases/base strict 守卫（privacy.mode==strict 在 commands 层判，同 rank 先例） | #8/#9 |
| 13 | commands | bind 前查旧绑定（改绑透明化）；me 已隐藏角标（get_hidden_keys） | #11/#25 |
| 14 | query/formatters | 锚点供数：commands 层把 resolve 出的 srv.name 传 formatter（不扩 DTO） | 全部查询类标题 |

## 6. 捎带 bug 修清单（现网缺陷，随重设计根治）

1. today 世界天数直出 epoch（report_service.py:164-165，golden 手造 DTO 恰绕开）。
2. status/online 不剔隐藏玩家——/pal me hide 承诺经两入口落空（§3 隐私收敛）。
3. `/pal help xxx @a @b` 裸抛 ArgError 用户无回复（help 跳过 parse_arg 根治）。
4. guild base 详情可绕出 strict（DB 残留据点仍可按名/#序号渲染）。
5. link remove 名字打错也回「已撤销」假成功。
6. server 写回执不显示目标（params.target 现成未用）；confirm 吞 shutdown/stop 断连「已发起」语义。
7. events 的 NEW_GUILD/NEW_BASE 直出内部 subject_key 丑键；today 成长行直出截断哈希。
8. world overview 快照缺失静默全 0 假数据；guild base 无观测全 0 假数据。
9. whereami 引导在 open 模式与真实可用性相反（本次按 access_mode 分流修正）。

## 7. locale 键表处置

- **删除（死键）**：auth_error、derived_note（均零调用点）。
- **新增**：link_list_empty（#20 空态）、link_add_unknown（#21，留 {server} 参数）、busy（收编 main.py 硬编码）、arg_error（收编 _ARG_ERROR_MSG 三处同串）、online 空态等 formatters 硬编码空态串收编键、server 写回执新式样键族（per-action 短语）、拦截/停用新句键。具体键名 plan 定，命名沿现有风格。
- **改写**：feature_disabled（新句+条件脚注）、degraded/degraded_never（统一式）、admin_ok/admin_failed/admin_shutdown_initiated/admin_confirm_*（新回执式）、use_ok/unbind_ok（随 RoutingService 结构化返回上提改写或退役）、use_only_group/private_restricted/whoami*/whereami*（加 ⚠️ 与新式样）、rank_duration_strict/bases_disabled_strict（统一句形+⚠️，后者接线）、me_*/bind_*/unbind_self_*（新式样+正字+锚）、target_*/admin_*usage（新式样）、guilds_unavailable（并入 #6 空态口径）、empty_day/no_events（新空态句）。
- **保持原样**：routing 六分支（no_server_configured/single_not_authorized/server_unknown/not_authorized/active_server_stale/no_server_resolved）、setup_required、link_single_mode。

## 8. 文档同步清单

- docs/commands.md 矩阵（:81-86 与 :31）、docs/configuration.md 的「回「未开放」」**行为义**全部随新文案改「未开启」；**「上游未开放（PalGameDataBridge）」为同形异义保持不动**，两义不可混改。
- tests/unit/readme_test.py:97 中文锚点**显式重锚**：行为义锚改「未开启」，另立「上游未开放」锚守上游义——旧锚改后不红只静默失效（比硬红更隐蔽）。
- rank 变体描述（commands.md「留存期内累计在线时长榜」→「累计在线时长榜」+留存期脚注口径）及其余 29 条涉及的文档引句（target_none、confirm 超时句等）逐一核对，plan 中声明改/不动清单。
- README 输出示例若引用旧式样随改（绝对 URL 规则不变）。

## 9. 测试改写清单（SDD 任务必须显式携带）

1. **tests/golden/ 5 全文比对**（status/world/rules/today/online_redacted.txt）：**人工核对后重生成**——golden 机制文件缺失即静默用当前输出生成（formatters_golden_test.py:28-29），**禁止裸删重跑**。
2. **中文子串断言**（grep `assert.*(世界|玩家|服务器|排行|在线|公会|据点)` 实测 23 文件 40 处）：commands_test/commands_rank_test/commands_player_test/commands_me_bind_test/commands_admin_write_test/gamedata_output_suppression_test/players_group_off_test/main_link_single_test/format_player_test/format_rank_test/formatters_test/report_service_test/locale_rework_test/guild_service_test/snapshot_service_info_test/scheduler_basic_test + integration privacy_test/smoke_test/phase3_smoke_test/routing_e2e_test 等，逐文件随新式样重锚。
3. **report_service_test 专项**：:74-75 epoch 断言随 bug 修反转为真实 world_day；:194 pk-in-records 断言随名字解析落点反转；:102 核对留置。
4. **locale 键表同步**：死键删除；MESSAGES["degraded"] 内容断言（locale_test.py:23）随统一式重写；新增键补测。
5. **readme 中文锚点联动**（§8；PR#13 先例入 checklist）。
6. **help 类测试**（formatters_hierarchy_test/formatters_admin_help_test）：锚 "/pal …" 子串与 HELP_TEXT keys 结构，【】改素节头后多数存活——列**低风险核对项**，逐条跑红补改。
7. **server 写回执消费方测试**（confirmation/admin 链路对【{action}】式样的断言）单独列出。
8. 新增覆盖：stale 判定边界（假 clock）、隐私收敛两入口、据点序号空间一致性、RoutingService 结构化返回、多模式锚/单模式省略分支、strict 守卫 #8/#9、unban 前缀校验、help 双 @ 不再抛。

## 10. 验收标准

1. 29 条命令输出与本 spec §4 样张逐条一致（据点名/世界名按 §2.1/§3 口径为示意，结构与措辞为准）。
2. §3 横切规则全落地：图标分派无双待遇；降级三落点；隐私收敛两入口同数；据点序号空间单一。
3. §6 九项捎带 bug 全部根治且各有回归测试。
4. 全库测试绿（含 §9 改写后）；ruff/mypy 全绿；前端测试绿；产物 no-drift（若动 frontend/schema.ts 须 `npm run build` 重建）。
5. 文档与 readme 锚点按 §8 同步，两义分治无混改。
6. 门控/安全语义零回归：门序铁律、visible_actions 角色隔离、confirm 原子性、name_banned 收敛、审计不落明文——现有安全测试全数保持。

## 附：设计过程记录

- 交互定稿 6 条（world status/rules/events/today/player info/bind），用户逐条拍板；2026-07-17 用户定案「全部确定了」后批量补齐 23 条+横切面。
- 一轮四棱镜对抗验证（数据面/状态覆盖/词汇一致/安全门控）：32 发现（16 major/16 minor）全修。
- 二轮四新棱镜（修正自洽/落地面/体验连贯/完整性缺口）+ 12 major 逐条独立对抗验证：12 确认 0 否决，13 minor 全采，全修。
- 工作台账：.superpowers/sdd/output-design-draft.md（gitignored 工作稿，本 spec 为其正式化，内容以本 spec 为准）。
