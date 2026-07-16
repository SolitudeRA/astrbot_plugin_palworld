# 整体 UI 优化 · 阶段二+三「对齐·重构·精修」设计（spec）

> 日期：2026-07-16　分支：`feat/ui-overhaul`（叠在阶段一「地基」之上）
> 流程说明：本阶段采用「demo 逐屏定稿 → 统一落地」迭代——`frontend/dev.html` 全真前端 + 内存 mock（零生产影响），用户逐屏确认每项设计后落进真组件。本 spec 是**定稿决策的汇总记录（追认式）**，与代码同源；落地任务见 §12。
> 阶段一 spec：`2026-07-16-ui-foundation-design.md`（token 体系/排版定标/focus-visible/.mono/主题默认）。

## 1. 信息架构（章节与排序）

**左轨**：观测组「状态 / 审计」+ 配置组「连接 / **功能**（新增章）/ 采集 / 世界与据点 / 隐私与留存 / 权限」。

**排序总原则**（全章适用）：小参数控件在前，大面积浏览/批量控件垫底，**危险区恒最后**。

- **连接**：服务器（单模式单卡 hide-delete / 多模式卡列表）→ 默认查询（routing 段拆出 access_mode 后改名，多模式含 default_server；单模式段消失）→ 自定义请求头 → 授权群名单（仅 单模式+受限授权；显隐跟**已保存**快照，保存后 grid-rows 收折动画）→ **危险区**：访问模式（下拉 + 动态后果说明 + 未保存「（保存后生效）」）+ 切换运行模式（dz 行形态，含 dirty 门）。
- **功能**：玩家查询参数段（players 段迁入：功能参数与启停同住）→ 功能开关树（`CommandTree axis="enabled"`，危险命令拆出不渲染）→ **危险区**：5 条写命令逐条开关（踢出/解封/封禁/关服/停止，严重度升序；说明「写操作命令集中管理；封禁/关服/停止不随整组开关」——踢出/解封仍随组联动，开关如实显示生效值）。
- **权限**：两层权限说明卡 →「管理员名单」（原受托名单；卡片标签「管理员 N」、按钮「＋ 添加管理员」）→ 服务器管控段（二次确认/审计留存）→「命令权限」树（`axis="admin_only"`，**只列当前启用的命令**——功能关着谈不上谁可用，功能页开启即时出现；server 组默认收折）。
- 单模式术语统一：「受限授权」（弃「单世界受限模式」）；服务器组头说明单数化「当前监测的唯一服务器」。

## 2. 命令树 CommandTree（单轴复用组件）

一个组件、两轴两实例（`axis: 'enabled' | 'admin_only'`），交互同套：

- **完整树呈现**：两页同一棵 29 条命令树（认知一致）；本轴不可配的行显示锁定文本（enabled：「恒开·内置」；admin：「仅管理员·内置」「所有人·内置」），不消失。
- **开关 = 生效值**：小号开关（`.pw-switch.sm` 全局变体）直接显示三级继承生效值（叶子→组→内置默认，danger 不随组 F2）——前端 `lib/permissions.ts` 复刻后端 `effective_enabled/effective_admin_only` 算法；内置默认经 L2 跨端锚定。
- **自动回归**：切开关回到继承值即自动清覆盖（不留冗余键，两轴全 inherit 删键）；**无恢复按钮**（曾有 ↺，定稿删除——切回即清，按钮冗余）。
- **组头开关 = 整组统一**：操作时收编组内叶子本轴覆盖（enabled 轴保留 danger 自设——F2 不归组管）。
- **受管视觉（三态）**：纯整组 = override 色 title 行底+左竖条+组名着色+实心「整组」标；**混合**（有单独设置）= title 行底/竖条/组名换 **warn 琥珀** + 标「整组 · N 单独」（warn 实心）；组未管但有自设 = 弱化灰字「N 单独」计数。仅 title 行变色，区块内竖条不随混合态变。
- **单独设置行**：override 底色（12%，深于随组行 8%）+ 名旁圆点 + 开关外环；**锁定行永不亮覆盖标**（不可设置谈不上单独设置——曾有误亮 bug，已修并防回归）。
- **危险标**：仅 enabled 轴显示（红「危险」小标+行首红竖条，解释「不随整组」）；admin 轴该三条恒锁定，不显标。
- **过滤 props**：`hideGroups`（单模式隐 link）、`hidePaths`（功能页危险区承载的 5 条）。

**双主题 override 语义色**：`--override/--on-override` token（浅色主题**靛蓝** #3D63B8、深色主题**青** #4FC4CE）——「你设置过的」语义与键盘焦点环（--focus）解耦，明暗各自配色。

## 3. 危险区体系（全局原语）

`.danger-zone`（红框淡红底容器）+ `.dz-item`（左标题+说明、右操作）+ `.dz-btn`（红轮廓按钮）+ `.group-head .t-danger`。成员归类原则：影响重大/不可逆/准入放开类集中垫底。现有三处：连接章（访问模式+切换运行模式）、功能章（5 写命令）、切换 helper 完成步（残留清理复用容器）。

## 4. 切换运行模式 helper（全覆盖流程）

- **全覆盖壳**（弃小弹窗）：`.helper-overlay`（paper 点阵底全屏）+ `.helper-panel`（720px 居中卡）+ `.helper-head`/`.helper-steps` 全局原语。
- **向导 4 步**：保留台 — 迁移群 — 处置 — 确认；步骤指示器当前步蓝底数字、完成步打 ✓。
- **选择卡** `.pick-list/.pick-row`：radio/checkbox 行升级为整行可点选择卡，选中 focus 边+淡底+内环；「永久删除」选中整卡 **danger 红**；`.helper-actions` 页脚分隔线。
- **完成步（新）**：切换成功进全覆盖结果页——成功绿 ✓ / 告警琥珀 ! 的 hero（图标圆+标题+摘要）+ **内嵌残留数据清理**（OrphanCleanup 复用，danger-zone 形态）+「完成」收尾；成功不再 toast。
- **OrphanCleanup 不再常驻连接章**——孤儿由切换产生、由切换收尾步清理。**已知边界（文档化）**：删服务器+保存产生的孤儿暂无常驻 UI 入口，下次进入切换 helper 完成步可清。
- 失败仍 toast + 关流程（模式不变，不留半态）。
- dev demo 场景条含「切换 helper」直达场景（main-dev DOM 驱动自动打开，零生产耦合）。

## 5. 首次选模屏 ModeOnboarding（阶段二早期已落地，commit 5405d7e + 修复）

全尺寸居中偏上（`calc(100vh-230px)` flex 居中 + 12vh 底部留白）、无图标、badge「首次设置」、display24/title21/sm14 三级层级、定稿文案（「这台机器人要管理一台还是多台…」）、选中 focus 卡 + ✓、确认复用全局 `.commit`、radiogroup+方向键 roving；**首次未确认时 App.vue 隐藏整条左轨**（SettingsPanel 上抛 onboarding 态）；hint「已选「X」，之后可随时在**「连接」**页转换」（「连接」amber semibold 强调）；类名避开全局 `.card`（撞名教训：`.card + .card` 纵向间距在横排兄弟上压出高低差）。

## 6. 状态页 StatusPanel

- **观测卡 + 读数网格**（`auto-fit` 响应式）：在线玩家大数字 + `/max` 副字 + **占比进度条**（flux 色、宽度动画）+ 今日峰值副读数；FPS 大数字 + 流畅度着色副字（流畅=flux/一般=warn/卡顿·严重卡顿=danger）；世界时间；据点数（有值才显）。
- **可展开详细区**：「运行信息」（版本/运行时长/帧时间/地址/描述）+「世界规则」（难度/PVP/死亡惩罚/经验倍率）kv 网格；多台默认收起点卡头展开（chevron），**仅一台恒展开**（单模式必然命中）；`detail` 缺失静默不渲染。
- 数据契约：`status/overview` 白名单扩 `detail` 子对象（L1 后端任务；字段名对齐 Palworld API info/metrics/settings 语义；rules 值为与 `/pal world rules` 同措辞的中文串；未 ready/degraded 行不带 detail）。

## 7. 审计页 AuditPanel

观测面表格（card 外框、raise 渐变表头 eyebrow 风、dashed 行分隔不引 zebra、hover 蓝微高亮）；时间/管理员/目标三列 `.mono` 等宽、动作列中字重、空目标灰「—」；结果列 chip：成功绿 / **失败红**（`chip.bad` 全局新增，hover title 显错误码）；空/错误态卡框居中（错误带刷新）；窄屏横向滚动兜底。**分页**：每页 10 条窗口式页码（1 2 3 … N，当前页 focus 蓝底反白，‹ › 边界禁用，「共 N 条」，刷新回第 1 页）——后端 ts DESC+LIMIT 封顶，客户端分页即完备方案。

## 8. 其它定稿项

- **枚举中文化**：`FieldSpec.optionLabels`（显示中文、`:value` 存储恒英文）：受限授权/完全开放、单服务器/多服务器（与全 UI 统一，弃确认屏的「单世界/多世界」）、最严/均衡/进阶、简体中文；hint 同步中文词。
- **危险色统一**：不可逆销毁类 `--warn`→`--danger`（OrphanCleanup 文案与按钮、TransferWizard 删除摘要/确认盒/「永久删除」选项）；提示类（unsaved/tag-new/callout-warn/chip.warn）保留 warn。
- **savebar 实底**（弃羽化渐变——sticky 悬浮时透出下层内容）。
- **ModeTransfer**：模式条形态弃用，定稿为危险区行（标题「切换运行模式」+ 当前模式加粗嵌说明 + dirty 黄字 + 红轮廓切换按钮）。
- **用词表**：受托名单→**管理员名单**（L3 全库同步）；管理员限制→**命令权限**；首次初始化→首次设置；单世界受限模式→受限授权；名册全局→名单全局（随 L3 三端统一）。
- 全局原语新增清单：`--override/--on-override`、`--on-focus`、`chip.bad`、`.pw-switch.sm`、`.helper-*`、`.pick-*`、`.danger-zone/.dz-*`、`.grp-tag/.grp-count`。

## 9. dev demo 基础设施（长期资产，零生产影响）

`frontend/dev.html` + `src/dev/{main-dev,mockBridge}.ts`：内存 mock 覆盖 8 端点（形状对照 `web_api.py` 双向核对）、5+1 场景（首次设置/多服务器/单服务器/审计空态/空配置/切换 helper 直达）、写操作真状态变化。约束：`npm run build` 产物 byte-identical、verify:bundle 过、dev 文件不进 bundle。

## 10. 测试与守卫

- 前端基线 247 passed（demo 迭代终点）；drift 守卫 COMPONENTS 含 7 组件（L4 增补 StatusPanel/AuditPanel）。
- `lib/permissions.ts` 纯函数单测（三级继承/F2/writeAxis 稀疏写）。
- 测试铁律沿用：改文案/结构与测试锚点同一提交同步；子串陷阱用更长锚（「运行模式」案例）。
- 后端基线 912 passed + 1 skipped；L1/L2 新增测试；readme_test 中文锚点随 L3 同步。

## 11. 已知遗留（不阻塞本 PR）

- AsyncState 四态收敛未做（StatusPanel/AuditPanel/SettingsPanel 各自实现 loading/error/empty；helper 全覆盖已替代 BaseDialog 需求）。
- 响应式 620–880 中间带未专项调优（读数网格/表格滚动已天然自适应）。
- CommandTree「危险」概念未在权限页有任何呈现（定稿：不需要）；命令树无图例行（用户未拍板，暂不加）。
- 删服务器+保存的孤儿无常驻清理入口（见 §4 边界）。

## 12. 统一落地任务（L1–L6）

| 任务 | 内容 | 验收 |
|---|---|---|
| L1 后端 | `status_rows` 扩 `detail`（§6 形状逐字；rules 措辞复用 world rules；缺数据降级不 500） | 后端测试 + 全套绿 |
| L2 跨端 | `PAL_TREE` 加 `defaultEnabled` + `frontend_pal_commands_test` 锚定 + `lib/permissions` 改派生（导出名不变） | 两端测试绿、消费方零改动 |
| L3 全库 | 「受托」用词同步（docs×2/locale/README/_conf_schema/readme_test 锚点/前端「名册→名单」） | grep 零残留 + readme_test 绿 |
| L4 前端收尾 | drift COMPONENTS 增补、typecheck 清点、`npm run build` 产物重建 | vitest + no-drift 绿 |
| L5 验证终审 | 全套（vitest/pytest/ruff/mypy）+ 全分支终审（opus）+ fix wave | Ready to merge |
| L6 收尾 | 最终产物 + PR（阶段一+二+三一并，遵用户「全部完成再 PR」） | PR 创建 |

## 13. 验收标准（整分支）

1. demo（dev.html）与真实产物行为一致；六配置章 + 两观测章全部按 §1–§8 呈现。
2. 前后端测试全绿；产物 LF 干净 no-drift；跨端锚定（PAL_TREE 双字段集 + defaultEnabled）全等。
3. 明暗两主题逐章目测：override 双主题色、danger 语义、helper 全流程、状态卡展开、审计分页。
4. 全库用词一致（管理员名单/命令权限/受限授权/名单全局）。
