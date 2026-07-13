# 权限管理设计

> 状态:草拟,待四视角对抗复核 + 用户审阅
> 日期:2026-07-14
> 范围:后端(权限模型 + 命令门 + whoami)+ 前端(设置页「权限」章)+ 文档。不改 DB schema、不做迁移(名单走配置 template_list,非 DB 表)。

## 目标

给插件一套**自有的两层权限模型**,让"能进设置页的人"可以把"在群里执行管理员命令"的资格,授予指定的聊天账号——不依赖、也不复用 AstrBot 的框架管理员名单。

本轮落地维度 1(权限主体)+ 维度 2(命令级细粒度)。维度 3(Web 角色分级)在现有 AstrBot 上不可行(单管理员 Dashboard、无角色),不做;维度 4(更细群授权)YAGNI,不做。

## 两层权限模型

- **超级管理员** = 能打开插件设置页的人(AstrBot Dashboard 账户)。天然最高权,不进任何名单。其权力**只在设置页**:维护受托名单与命令门。在群里没有天然权限(网页身份与群账号是两个不互通的身份空间)。
- **受托群管理员** = 超管在设置页 `permission_admins` 名单里指定的聊天账号。在**群聊里和 bot 对话**时,可执行"管理员命令"。
- **群里管理员权限的唯一来源就是这份名单**——严格只认它,**不认** AstrBot `admins_id` / `event.is_admin()`。

### 关键背景(来自 AstrBot 接口勘探)

- AstrBot 有全局框架管理员名单 `admins_id`(裸 sender_id),`event.is_admin()` 查它。本设计**刻意不复用**它——要的是插件专属、可独立于 bot 全局管理员的授权。
- AstrBot Dashboard 是单管理员、JWT 无角色;框架已用 `require_plugin_scope` 对插件 web 端点做 JWT 鉴权。所以"设置页 = 超管"由平台天然保证,无需插件再做 Web 侧角色判定。

## 命令门:哪些命令算"管理员命令"

两类,合并判定"某命令是否需要管理员":

1. **内置(始终需管理员,不可关)**:`/pal server add`、`/pal server remove`(服务器授权/撤销本质是特权操作)。**裸 `/pal server`(列表)仍是全员**。此门内建在 `server()` 方法体,与本设计前一版一致,不受配置影响。
2. **可配(`admin_only_commands`)**:超管可把**其它整条命令**锁成仅管理员(如把 `/pal player`、`/pal rank` 锁起来)。默认 `[]`(空)。
   - `whoami` 永远全员,不可锁(否则用户无法查自己的标识)。
   - 注意语义:`admin_only_commands` 锁的是**整条命令**;对 `server` 无意义(其列表要保持全员、add/remove 已内置),故 `server` 不进 `admin_only_commands`,在设置页 UI 里以"内置·不可关"的锁定态展示。

**有权判定**:`is_admin(event)` ≡ `_sender_id(event) ∈ permission_admins 的 id 集合`。命令 X 需要管理员当且仅当:`X 属内置管理员命令`(server add/remove)`或 X ∈ admin_only_commands`。非管理员触发需管理员的命令 → 回 `admin_required`。

## 身份格式

- 名单元素 id = `平台:账号`,如 `aiocqhttp:12345`。**与插件现有 `_sender_id(event)`(`main.py:300-306`,`f"{get_platform_name()}:{get_sender_id()}"`)逐字一致**,判定就是精确字符串比对。
- 新增命令 `/pal whoami`:回显发送者自己的 `_sender_id(event)` 串,供用户报给超管填入名单。全员可用,不受 features、不受 admin 门。

## 配置数据形态

新增两个顶层配置键(复用已验证的顶层 template_list / list 机制,避免嵌套结构的未知风险):

- **`permission_admins`**:顶层 template_list,行结构 `{ id: string, note: string }`(`id` 必填,`note` 可选备注,仅超管自己看)。复用 `servers` / `custom_headers` / `group_bindings` 同款机制。
- **`admin_only_commands`**:顶层字符串列表(`type: list`,元素为命令名),默认 `[]`(空)——即默认无额外锁定命令。存储只含超管勾选的**额外**命令;`server` 的内置门不入此列表,`whoami` 不可入(见上)。

> 名单是**配置**不是 DB 表 → 不需要 migration。老实例升级后 `permission_admins` 为空。

## 后端改动

### palworld_terminal/config.py
- 新增 `PermissionsConfig` dataclass:`admins: list[AdminEntry]`(`AdminEntry` 含 `id: str`、`note: str`)、`admin_only_commands: list[str]`。
- parse:从 raw config 解析 `permission_admins`(逐行取 id/note,跳过 id 为空的行)与 `admin_only_commands`(列表,去空白、去重、剔除 `whoami` 与 `server`)。
- `AppConfig` 加 `permissions: PermissionsConfig` 字段。

### main.py
- `_is_admin(event)`(现 296-298 读 `event.role`)改为:`self._sender_id(event) in self._admin_ids()`,其中 `_admin_ids()` 返回 `{a.id for a in cfg.permissions.admins}`。**不再读 `event.role`**。
- 新增中央命令门:一个单一 choke point(建议在 `_guarded` 外再包一层 `_gated_cmd(event, command_name, call)`,或每个 handler 传入命令名),对 `command_name ∈ admin_only_commands` 的命令,非管理员直接回 `admin_required`,不触达底层。`server` 不走此门(其 add/remove 内置门在 commands 层)。
- 新增 `@pal.command("whoami")` handler → `c.commands.whoami(event)` 返回 `_sender_id(event)`。
- `server` handler:仍传 `is_admin`(现在 = 插件名单判定)给 `commands.server()`,后者 add/remove 的 `if not is_admin` 守卫不变;`server_usage`/`use_only_group` 守卫不变。

### palworld_terminal/presentation/commands.py
- 新增 `whoami(self, sender_id) -> str`:回 `L("whoami", id=sender_id)`(或直接回标识串)。不带 `@_gated`。

### palworld_terminal/presentation/command_registry.py
- `COMMANDS` 加 `("whoami", "core")`;`HELP_LINE` 加 `"whoami": "/pal whoami  查看我的账号标识"`。

### palworld_terminal/presentation/locale.py
- 新增 `whoami` 文案(如 `你的账号标识：{id}（把它报给管理员即可加入受托名单）`)。`admin_required` 保留复用。

### palworld_terminal/presentation/config_view.py(web 保存校验/脱敏)
- `_TOP_KEYS`(27-30)加 `permission_admins`、`admin_only_commands`。
- `permission_admins`:加进 template_list 机制 `_LIST_SECTIONS`/`_ROW_ID_PREFIX`/`_SECTION_KEYS`/`redact_config`/`_strip_meta`(id/note 均非 secret,redact 为透传,但仍要纳入 meta 剥离与结构校验)。
- `admin_only_commands`:作为字符串列表校验(元素为 str),缺键保留旧值语义与其它键一致。

### _conf_schema.json
- 加 `permission_admins`(template_list,templates 含 `id`/`note` 两字段)与 `admin_only_commands`(`type: list`,items string,default `[]`)。description 直白面向超管。

## 前端改动(设置页「权限」章,乙方案:可视化编辑)

参照勘探结论,复用 `access` 章的自定义渲染范式(`isAccess` 特判块 + 卡片列表),`permission` 章不走 `blocks`/`SectionForm`(两块内容都需自定义 UI)。

### frontend/src/lib/chapters.ts
- `CHAPTERS` 加 `{ id: 'permissions', label: '权限', group: '配置', kind: 'settings', blocks: [] }`。
- `blocks: []` → 不引入新 `OBJECT_SECTIONS` 键 → `chapters.test`(blocks 并集 = 全 sections)与 `schema.test`(OBJECT_SECTIONS 恰 8 键有序)**均不需改断言**。

### frontend/src/components/AdminCard.vue(新建)
- 照抄 `HeaderCard.vue` 的查看/编辑两态、`freshNew`(新行取消即 delete)、`draft` 暂存、`saveCard` 浅比较只暂存不落库。字段:`id`(等宽输入,占位"如 aiocqhttp:12345")、`note`(可选)。

### frontend/src/components/SettingsPanel.vue
- 加 `isPermissions`(仿 `isAccess`,25 行)特判块,渲染:
  - 两层模型说明 callout(超管 / 受托,含"只认名单"提示)。
  - `permission_admins` 卡片列表(照抄 `SettingsPanel.vue:115-121` 的 servers/headers 容器:`v-for` + `:key` 用 `__row_id||__local_key`、`emptyRow` 新行、add/delete/update 事件、dirty 跟踪)。空名单显示"名单为空→群里暂无人可执行管理员命令"提示。
  - `admin_only_commands` chip 网格:命令清单(来自新增前端常量 `PAL_COMMANDS`)逐个 chip,点亮=需管理员;`server` 锁定为"内置·不可关"态、`whoami` 锁定为"全员·不可锁"态,其余可切,default 全灭。
- `applyConfig`(49-55)读入 `permission_admins`(逐行浅拷 + 注入 `__local_key`)与 `admin_only_commands`(数组)。

### frontend/src/lib/collect.ts
- 新增 `collectAdmin`(仿 `collectHeader`:剥 `__row_id`/`__local_key`、白名单字段 id/note)。
- `collectBody` 加 `body.permission_admins = state.permission_admins.map(collectAdmin)`、`body.admin_only_commands = [...state.admin_only_commands]`。
- `SettingsState` 接口(5-9)加两字段。
- collect 顶层键白名单 `TOP_KEYS` 常量(collect.test.ts:23)同步加两键。

### frontend/src/lib/schema.ts
- 新增导出常量 `PAL_COMMANDS`(命令名 + 所属功能组,供 chip 网格),源清单对齐 `command_registry.py`。`OBJECT_SECTIONS` 不动(permission 不是 object 节)。

### 构建产物
- 改前端后必须 `cd frontend && npm run build`(内置 normalize-eol)并提交 `pages/settings/`。产物单文件、CSP 禁外链;`verify-bundle` 从仓库根跑;CI `git diff --exit-code -- pages/settings` no-drift 会因未重建转红。

## 数据流

```
群里:/pal server add alpha
  → main.server handler → _is_admin(event) = _sender_id ∈ permission_admins?
  → commands.server():add 分支 if not is_admin → admin_required;否则 routing.use

群里:/pal player Alice(若 player ∈ admin_only_commands)
  → main 中央命令门:player ∈ admin_only_commands 且 _sender_id ∉ 名单 → admin_required

群里:/pal whoami
  → main.whoami handler → commands.whoami(_sender_id(event)) → "你的账号标识：aiocqhttp:12345…"

设置页:超管编辑受托名单/命令门 → collectBody → config/save → 落库
```

## 权限/守卫矩阵

| 场景 | 判定 |
|---|---|
| `/pal server`(裸列表) | 全员(私聊也可) |
| `/pal server add\|remove` | 内置需管理员(`_sender_id ∈ permission_admins`)+ 仅群聊 |
| 命令 ∈ `admin_only_commands` | 需管理员(`_sender_id ∈ permission_admins`) |
| `/pal whoami` | 全员,永不锁 |
| 其余命令 | 全员(受 features 组开关约束,与权限正交) |

## 兼容性(行为变化,需在文档与 PR 说明)

- 现状:`server add/remove` 靠 `event.role=="admin"`(AstrBot 框架管理员)放行。
- 新模型:靠 `_sender_id ∈ permission_admins`(插件名单)。**升级后 `permission_admins` 为空 → 群里没人能 `server add/remove`**,直到超管在设置页加人(或用现有 `group_bindings` 预设授权那条配置路径先授权群)。这是刻意的"显式授权",已与用户确认。

## 测试策略

### 后端
- `config.py` parse:`permission_admins` 逐行、跳空 id、去重;`admin_only_commands` 去空白/去重/剔除 whoami&server。新增 `tests/unit/config_permissions_test.py`。
- 权限门:`_is_admin` = 名单判定;命令 ∈ admin_only_commands 非管理员回 admin_required;server add/remove 名单判定;whoami 全员且回正确标识。扩 `commands_test.py` / 新增测试;命名空间冒烟 `namespace_runtime_smoke_test.py` calls 加 `whoami` 并按需覆盖 admin 门深分支。
- `config_view.py`:`permission_admins`/`admin_only_commands` 进 `_TOP_KEYS` 后 web 保存往返;template_list meta 剥离;非法 shape 拒绝。扩 `config_view_validate_test.py`/`web_api_save_test.py`/`web_api_read_test.py`/`conf_schema_test.py`。

### 前端
- `AdminCard.test.ts`(新):两态、freshNew 取消即 delete、save 浅比较、id/note 字段。
- `collect.test.ts`:`TOP_KEYS` 常量加两键;`permission_admins` 行剥 meta;`admin_only_commands` 透传数组。
- `SettingsPanel.test.ts`:permissions 章渲染(callout + 卡片 + chip 网格);mock cfg 补 `permission_admins`/`admin_only_commands`;保存 body 含两键且结构正确;chip 点选改 state。
- `chapters.test.ts` / `schema.test.ts`:因 permission 不加 OBJECT_SECTION、blocks 为空,**断言无需改**(需在测试里确认新增 chapter 不破坏现有断言)。
- `App.test.ts`:可补"权限"章按钮断言。

### 文档
- `docs/commands.md`:加 `/pal whoami` 行;新增"权限"说明节(两层模型、受托名单、命令门、内置 server 门)。
- `docs/configuration.md`:加 `permission_admins`/`admin_only_commands` 配置说明。
- `README.md`:功能特性/安全与隐私提"细粒度授权";命令计数同步(加 whoami → 详表行数变化,更新"N 条指令"计数)。
- `readme_test.py`:中文锚点同步(加 `/pal whoami` 锚点等),grep 确认无遗漏。

## 版本

`v0.8.5` → `v0.9.0`(新增权限子系统 + 新命令 + 新设置章,minor)。同步 metadata.yaml / main.py @register / `__init__.py` / README 徽章 / 版本断言测试。

## 命名空间加载安全

新增 `whoami()`、权限门逻辑、AdminCard 无 import 隐患;包内一律相对导入,函数体内绝不绝对自导入。既有静态扫描 + 运行时冒烟对新命令生效。

## 非目标(YAGNI)

- 不做 Web 设置页角色分级(平台不可行)。
- 不做聊天命令管理名单(`/pal admin add`);名单只在设置页配。
- 不做按人/审计的更细群授权。
- 不复用、不修改 AstrBot `admins_id`。
- 不改 `RoutingService` 底层、不改 DB schema、不迁移。
