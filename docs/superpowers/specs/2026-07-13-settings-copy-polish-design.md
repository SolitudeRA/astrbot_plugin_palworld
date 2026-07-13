# 设置页文案打磨(Settings Copy Polish)设计规格

**日期:** 2026-07-13
**类型:** 纯前端文案替换(字符串级),零逻辑/契约/样式改动
**基线:** main(PR #11 设置页重设计 + PR #12 已合并)

---

## 1. 方向决策(用户已确认)

| # | 决策 | 含义 |
|---|------|------|
| D1 | **全面直白** | 所有 UI 词零猜测成本,文学性词汇全部替换(品牌名除外) |
| D2 | **品牌名留,副题直白化** | 「帕鲁纪事 / PalChronicle」保留;副题换成直白描述 |
| D3 | **用途优先,术语退 hint** | label 说用途,端点名/算法术语下沉到 hint |
| D4 | **核心名词 = 服务器** | 不用「数据源」;组名/按钮/状态页/提示统一「服务器」 |
| D5 | **底部保存按钮 = 「保存设置」** | 去掉「本页」误导(实际全量保存) |
| D6 | **ready=false 状态词 = 「未连接」** | 替换「未就绪」 |

## 2. 文案准则(研究得出,写作时全程遵守)

1. label = 名词短语,2–6 字为宜,句末不加句号(Ant Design / Semi Design)。
2. hint 单句不加句号;两句及以上每句都加句号(Ant Design)。
3. 无人称直陈,不出现「你/您」;「请」只用于真实可做的动作;不用感叹号。
4. 中英文、中文与数字之间加半角空格:「30 秒」「Ping 阈值」「TLS 证书」(中文文案排版指北)。
5. 术语唯一:删除=「移除」、编辑=「修改」、启停=「启用/停用」,全页一套。
6. 「不合法」全局淘汰,改「有误」(NN/g don't blame the user / 微软风格指南)。
7. 「稍候/稍后」区分:正在等=「请稍候」;过会儿再做某动作=「请稍后再试」。
8. 错误 = 发生了什么 + 怎么办;补救必须真实可做(NN/g)。
9. 单位可上收:同一节全部字段同单位时,单位声明在节副题,字段 label 不重复带。

## 3. 全量词表(权威,逐字实现)

### 3.1 `frontend/src/App.vue`

| 位置 | 现在 | 改为 |
|---|---|---|
| 副题 subline | 世界纪事 · 只读观测台 | **Palworld 服务器监测 · 只读** |
| 主题按钮(暗色时) | ☀ 昼阅 | **☀ 浅色** |
| 主题按钮(亮色时) | ☾ 夜观 | **☾ 深色** |
| railcap「观测」「配置」 | 两个 railcap | **删除**;「状态」章按钮与后五章之间用分隔线(样式细节:一个带 `margin-top` 的分隔元素或 CSS 类,不引入新文案) |
| 品牌 | 帕鲁纪事 / PalChronicle | 保留 |
| 错误边界按钮 | 重试 | 保留 |

### 3.2 `frontend/src/lib/chapters.ts`

| id | 现在 label | 改为 |
|---|---|---|
| status | 观测台 | **状态** |
| access | 接入 | **连接** |
| cadence | 采集 | 保留 |
| world | 世界与据点 | 保留 |
| privacy | 隐私与留存 | 保留 |
| feature | 功能分组 | **功能开关** |

`group` 字段('观测'/'配置')保留在数据结构里(App 用它分组渲染分隔),但 railcap 文本不再显示——如实现更干净,可把 `group` 语义改为纯分组键,不改亦可。id/kind/blocks 一律不动。

### 3.3 `frontend/src/lib/schema.ts`(只改 label/hint/subtitle 字符串;key/type/default/options/secret/顺序一律不动)

**SERVER_FIELDS:**

| key | label(现在 → 改为) | hint(现在 → 改为) |
|---|---|---|
| name | 名称(不变) | 唯一标识,勿含空格 / 冒号 / @(不变) |
| enabled | 启用(不变) | — |
| base_url | 服务器地址(不变) | 官方只读 REST 端点,含端口(默认 8212)→ **填 IP 或域名,含端口(默认 8212)** |
| username | 用户名(不变) | — |
| password | 密码(不变) | 留空则保持不变;更推荐用下方环境变量 → **留空则不修改;更推荐用下方环境变量** |
| password_env | 密码环境变量名(不变) | 与密码二选一,更安全 → **填环境变量名,启动时从中读取密码;与密码二选一** |
| timeout | 超时(秒)→ **连接超时(秒)** | — |
| verify_tls | 校验 TLS 证书(不变) | http 地址不校验 → **关闭后不校验证书,仅建议自签名或内网环境使用** |
| timezone | 时区(不变) | 如 Asia/Tokyo;留空用全局时区 → **IANA 名称,如 Asia/Tokyo;留空用默认时区** |

**HEADER_FIELDS:**

| key | label | hint |
|---|---|---|
| name | 名称(不变) | 如 CF-Access-Client-Id(不变) |
| value | 值(不变) | 留空则保持不变;敏感值更推荐用环境变量 → **留空则不修改;敏感值更推荐用环境变量** |
| value_env | 值环境变量名(不变) | 与值二选一,更安全 → **填环境变量名,启动时从中读取值;与值二选一** |
| servers | 限定服务器(不变) | 多个用逗号分隔;留空 = 发给所有服务器(不变) |

**OBJECT_SECTIONS:**

| 节 key | title / subtitle | 字段改动 |
|---|---|---|
| routing | 路由与访问控制 → **访问控制**;subtitle → **哪些群可以查询,以及默认查询哪台服务器** | access_mode「访问模式」hint → **restricted 需管理员授权;open 全开放**;default_server「默认服务器」hint → **群里没指定、也没绑定时查询它** |
| polling | 轮询间隔(不变);subtitle → **每类数据多久从服务器拉取一次,单位:秒** | metrics_seconds「metrics 指标」→ **「性能指标」**hint **帧率、在线人数等;对应 metrics 接口**;players_seconds「players 在线」→ **「在线玩家」**hint **玩家列表与状态;对应 players 接口**;info_seconds「info 信息」→ **「服务器信息」**hint **名称、版本等;对应 info 接口**;settings_seconds「settings 设置」→ **「服务器设置」**hint **对应 settings 接口**;game_data_seconds「game-data 世界快照」→ **「世界数据」**hint **仅「公会与据点」启用时拉取;对应 game-data 接口**;jitter_ratio「抖动比例」→ **「间隔随机波动」**hint **按比例加随机偏移,避免所有请求同时发出**;max_concurrency「并发上限」→ **「同时请求数上限」**hint 删除 |
| world | 世界与展示(不变);subtitle **时区与 FPS 流畅度分档**(不变) | timezone「全局时区」→ **「默认时区」**hint「IANA」→ **IANA 名称,如 Asia/Tokyo**;locale「文案语言」→ **「消息语言」**;fps_smooth hint → **≥ 此值为流畅**;fps_moderate hint → **≥ 此值为一般**;fps_laggy hint → **≥ 此值为卡顿,低于则为严重卡顿** |
| bases | 据点推导(不变);subtitle **仅在「公会与据点」开启时生效** → **仅在「公会与据点」启用时生效**(动词统一「启用」) | enabled「启用据点推导」→ **「启用」**;assignment_radius「归属半径」→ **「据点归属半径」**hint 新增 **玩家距据点多远以内算作驻守**;ambiguity_ratio「模糊比阈值」→ **「归属模糊比」**hint「最近 / 次近距离差比」→ **最近与次近据点距离之比超过此值时,暂不判定归属**;confirmation_samples「确认次数」(不变);position_grid_size「坐标网格」→ **「坐标网格边长」**hint「坐标量化网格边长」→ 删除(label 已说清);z_weight「Z 轴权重」→ **「高度权重」**hint 新增 **计算距离时高度(Z 轴)的权重** |
| privacy | 隐私与脱敏(不变);subtitle「决定纪事如何收敛个体信息」→ **决定玩家个人信息公开到什么程度** | mode「隐私模式」hint「strict 最保守 · balanced 默认」→ **strict 最保守;balanced 为默认**;public_exact_ping hint「关 = 只显示优秀 / 正常 / 偏高」→ **关闭时只显示优秀 / 正常 / 偏高**;ping_good_ms hint → **≤ 此值为优秀(毫秒)**;ping_ok_ms hint → **≤ 此值为正常,超过则为偏高(毫秒)**;uncertain_timeout「掉线判定超时」→ **「掉线判定时间(秒)」**hint「多久无响应即判定离线(秒)」→ **超过此时长无响应即视为离线** |
| history | 保留清理天数 → **数据保留**;subtitle「各类数据的留存窗口(天)」→ **各类数据的保留天数,到期自动清理** | raw_metrics_days「原始指标天数」→ **「原始指标」**;aggregate_days「预聚合天数」→ **「预聚合统计」**;session_days「会话天数」→ **「玩家会话」**;observation_days「观察天数」→ **「观察记录」**(单位上收到副题) |
| features | 功能分组开关 → **功能开关**;subtitle「关掉的分组不采集数据,相关命令提示「未开放」」→ **关闭的功能不采集数据,相关命令会提示未开放** | report「日报 / 在线统计」(不变)hint「/pal today」(不变);events「世界事件记录」(不变);guilds_bases「公会与据点」(不变)hint「依赖 /game-data;专用服务器暂不支持」(不变);players「玩家个体查询」→ **「玩家查询」**hint「排行 / 档案 / 自助绑定」(不变) |
| players | 玩家个体 → **玩家查询**;subtitle「「玩家个体查询」开启时生效」→ **「玩家查询」启用时生效** | rank_top_n「排行榜人数」(不变);exclude_names「排除名单」(不变)hint「逗号分隔,排除出榜 / 查询」→ **逗号分隔;名单内玩家不进榜单、不可查询** |

### 3.4 `frontend/src/components/SettingsPanel.vue`

| 位置 | 现在 | 改为 |
|---|---|---|
| 组名 | 数据源 / 要观测的 Palworld 服务器 | **服务器 / 要监测的 Palworld 服务器** |
| 添加按钮 | ＋ 添加数据源 | **＋ 添加服务器** |
| indexLabel | '源 ' + pad | **'服务器 ' + pad**(「服务器 01」) |
| 请求头 indexLabel | '头 ' + pad | **'请求头 ' + pad** |
| grouphint | 带凭证的请求头,记得用「限定服务器」缩小范围——留空会发给所有服务器(含以后新增的)。 | **含凭证的请求头建议填写「限定服务器」。留空会发给所有服务器,包括以后新增的。** |
| 保存按钮 | 保存本页设置 | **保存设置** |
| savebar note | 数据源、请求头点各自的「保存」即生效;这里保存本页其余设置 | **服务器、请求头点各自的「保存」即生效;其余设置用这里保存** |
| toast 成功 | 已保存并重载 | **已保存,已生效** |
| toast 跳过 | 已保存({N} 条被跳过) | **已保存,{N} 条无效条目未生效** |
| ERR.save_in_progress | 保存进行中,请稍候 | 保留 |
| ERR.too_frequent | 保存过于频繁,请稍**候**再试 | **保存过于频繁,请稍后再试** |
| ERR.too_large | 配置过大 | **配置内容过大,请精简后再保存** |
| ERR.invalid_shape | 配置结构不合法 | **配置格式有误,请刷新页面后重试** |
| ERR.invalid_field | 字段不合法 | **字段填写有误**(path 拼接逻辑不变) |
| ERR.credential_redirect | 修改了服务器地址,请重新输入该服务器密码 | 保留 |
| ERR.restart_failed_rolled_back | 重载失败,已回滚到旧配置 | **保存未生效,已恢复原配置** |
| ERR.restart_failed | 重载失败且回滚失败,请检查后台 | **保存未生效且恢复失败,请检查后台日志** |
| ERR.unauthorized | 未登录或登录已过期 | **未登录或登录已过期,请重新登录 Dashboard** |
| save 兜底 toast | 保存失败 | **保存失败,请重试** |
| load 错误(fatalMsg) | 未登录或登录已过期,请重新登录 Dashboard / 读取配置失败,请重试 | 保留 |

### 3.5 `frontend/src/components/ServerCard.vue` / `HeaderCard.vue`

| 位置 | 现在 | 改为 |
|---|---|---|
| secret 占位(已设置) | 已设置(留空保持不变) | **已设置,留空则不修改** |
| secret 占位(未设置) | 未设置 | 保留 |
| Server 查看态「超时」 | 超时 | **连接超时** |
| Server 查看态「密码变量」 | 密码变量 | **密码环境变量** |
| Header 查看态「值变量」 | 值变量 | **值环境变量** |
| 查看态其余(地址/用户名/密码/校验 TLS/时区/值/作用域/所有服务器/限定 …) | | 保留 |
| 按钮 修改/移除/取消/保存、已保存 ✓、启用/停用 chip、(未命名) | | 保留(已符合准则) |

### 3.6 `frontend/src/components/StatusPanel.vue`

| 位置 | 现在 | 改为 |
|---|---|---|
| 章标题 | 观测台 | **状态** |
| stint | 数据源实时状态 | **服务器实时状态** |
| chip good | 就绪 | **正常** |
| chip warn | 数据缺失 | **部分数据缺失** |
| chip idle | 未就绪 | **未连接** |
| read 区 !ready 文本 | 未就绪 | **未连接** |
| restarting | 插件正在重载配置… | **正在应用新配置…** |
| 空态(ready 分支 rows.length===0,现无文案) | (空白) | 新增一行 `.pw-muted`:**尚未添加服务器,或数据尚未采集** |
| 刷新按钮 / 加载中… / 读取状态失败,请重试 | | 保留 |

### 3.7 不动的(明确范围外)

- `boot.ts` 两条(「需要 AstrBot ≥ v4.24.1 的插件页面环境」「初始化失败,请刷新」)——已合格。
- 后端产生的词:`smoothness_label`(流畅/一般/卡顿…)、错误 code 本身、`/pal` 命令输出——不属于设置页。
- `metadata.yaml`、README(实现时检查 README 是否引用了被改的 label,若有则同步,预期无)。
- 一切非字符串代码:collect/bridge/errors 类型、组件逻辑、CSS(除 railcap 删除伴随的微调)。

## 4. 测试锚点影响

| 测试 | 断言 | 影响 |
|---|---|---|
| App.test | rail 含「观测台」「接入」;点「观测台」→ 含「刷新」 | **改**:「观测台」→「状态」、「接入」→「连接」;railcap 删除不影响(断言的是 button) |
| SettingsPanel.test | 「功能分组开关」「玩家个体」(feature 章);「路由与访问控制」「保存本页设置」(access 章);button.pw-save;credential_redirect 文案;「未登录」 | **改**:「功能开关」「玩家查询」「访问控制」「保存设置」;其余锚点(pw-save 类、credential_redirect 文案、「未登录」子串)不变仍绿 |
| ServerCard/HeaderCard.test | placeholder toContain('已设置');「已设置」查看态断言 | **不破**:新占位「已设置,留空则不修改」仍含「已设置」;查看态摘要仍显「已设置」 |
| StatusPanel.test | 「alpha」「在线 3」「流畅」「正在重载」「读取状态失败」 | **改一处**:「正在重载」→ 断言改为「正在应用新配置」;其余不动(「流畅」来自 mock 的 smoothness_label) |
| chapters/schema/collect/bridge/boot/Field/SectionForm.test | key 集 / 契约 / 角色断言 | **全部不受影响**(只改 label/hint/subtitle 字符串;SectionForm.test 断言 label 文本来自 OBJECT_SECTIONS 常量本身,随源变,不硬编码——核对:它断言 `f.label` 动态取值 ✓,「功能分组开关」硬编码一处需改为「功能开关」) |

(核对说明:SectionForm.test 第 11 行 `expect(w.text()).toContain('功能分组开关')` 是硬编码,需同步改「功能开关」;第 12 行遍历 `features.fields` 动态断言,不需改。)

## 5. 验收

`npm run test:run`(全绿,含同步更新的锚点)+ `npm run typecheck` + `npm run build && verify:bundle`(从仓库根)。视觉零变化(除 railcap 消失与分隔线),纯文字替换。
