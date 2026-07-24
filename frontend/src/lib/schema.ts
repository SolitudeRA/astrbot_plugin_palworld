export type FieldType = 'enum' | 'int' | 'float' | 'bool' | 'string'

export interface FieldSpec {
  key: string
  type: FieldType
  label: string
  default: unknown
  options?: string[]
  optionLabels?: Record<string, string> // 仅展示：英文存储值→中文显示名（:value 恒绑原值，collect 往返不受影响）
  secret?: boolean // password / value：不预填、走哨兵
  hint?: string // 仅展示：字段说明（不参与 collect / schema 对齐）
}
export interface ObjectSection { key: string; title: string; fields: FieldSpec[]; subtitle?: string }

export const SERVER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '唯一标识，勿含空格 / 冒号 / @' },
  { key: 'enabled', type: 'bool', label: '启用', default: true },
  { key: 'base_url', type: 'string', label: '服务器地址', default: 'http://127.0.0.1:8212', hint: '填 IP 或域名，含端口（默认 8212）' },
  { key: 'username', type: 'string', label: '用户名', default: 'admin' },
  { key: 'password', type: 'string', label: '密码', default: '', secret: true, hint: '留空则不修改；更推荐用下方环境变量' },
  { key: 'password_env', type: 'string', label: '密码环境变量名', default: '', hint: '填环境变量名，启动时从中读取密码；与密码二选一' },
  { key: 'timeout', type: 'int', label: '连接超时（秒）', default: 10 },
  { key: 'verify_tls', type: 'bool', label: '校验 TLS 证书', default: true, hint: '关闭后不校验证书，仅建议自签名或内网环境使用' },
  { key: 'timezone', type: 'string', label: '时区', default: '', hint: 'IANA 名称，如 Asia/Tokyo；留空用默认时区' },
]

export const HEADER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '如 CF-Access-Client-Id' },
  { key: 'value', type: 'string', label: '值', default: '', secret: true, hint: '留空则不修改；敏感值更推荐用环境变量' },
  { key: 'value_env', type: 'string', label: '值环境变量名', default: '', hint: '填环境变量名，启动时从中读取值；与值二选一' },
  { key: 'servers', type: 'string', label: '限定服务器', default: '', hint: '多个用逗号分隔；留空 = 发给所有服务器' },
]

export const OBJECT_SECTIONS: ObjectSection[] = [
  { key: 'routing', title: '访问控制', subtitle: '哪些群可以查询，以及默认查询哪台服务器', fields: [
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'], optionLabels: { restricted: '受限授权', open: '完全开放' }, hint: '「受限授权」需管理员授权后群才可查询；「完全开放」所有群可查询' },
    { key: 'world_mode', type: 'enum', label: '运行模式', default: 'single', options: ['multi', 'single'], optionLabels: { multi: '多服务器', single: '单服务器' }, hint: '「单服务器」所有操作对应唯一服务器；「多服务器」按群绑定/切换服务器' },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '', hint: '群里没指定、也没绑定时查询它' },
    // 首次引导确认标记：恒隐藏（不渲染成表单字段），仅为让 collectBody 逐字段重建时回传（coerce bool 严格 === true）。
    { key: 'setup_confirmed', type: 'bool', label: '首次设置已确认', default: false },
  ]},
  { key: 'polling', title: '轮询间隔', subtitle: '每类数据多久从服务器拉取一次，单位：秒', fields: [
    { key: 'metrics_seconds', type: 'int', label: '性能指标', default: 30, hint: '帧率、在线人数等；对应 metrics 接口' },
    { key: 'players_seconds', type: 'int', label: '在线玩家', default: 30, hint: '玩家列表与状态；对应 players 接口' },
    { key: 'info_seconds', type: 'int', label: '服务器信息', default: 600, hint: '名称、版本等；对应 info 接口' },
    { key: 'settings_seconds', type: 'int', label: '服务器设置', default: 1800, hint: '对应 settings 接口' },
    { key: 'game_data_seconds', type: 'int', label: '世界数据', default: 120, hint: '仅「公会与据点」启用时拉取；对应 game-data 接口' },
    { key: 'jitter_ratio', type: 'float', label: '间隔随机波动', default: 0.10, hint: '按比例加随机偏移，避免所有请求同时发出' },
    { key: 'max_concurrency', type: 'int', label: '同时请求数上限', default: 6 },
  ]},
  { key: 'world', title: '世界与展示', subtitle: '时区与 FPS 流畅度分档', fields: [
    { key: 'timezone', type: 'string', label: '默认时区', default: 'Asia/Tokyo', hint: 'IANA 名称，如 Asia/Tokyo' },
    { key: 'locale', type: 'enum', label: '消息语言', default: 'zh-CN', options: ['zh-CN'], optionLabels: { 'zh-CN': '简体中文' } },
    { key: 'fps_smooth', type: 'int', label: 'FPS 流畅阈值', default: 50, hint: '≥ 此值为流畅' },
    { key: 'fps_moderate', type: 'int', label: 'FPS 一般阈值', default: 35, hint: '≥ 此值为一般' },
    { key: 'fps_laggy', type: 'int', label: 'FPS 卡顿阈值', default: 20, hint: '≥ 此值为卡顿，低于则为严重卡顿' },
  ]},
  { key: 'bases', title: '据点推导', subtitle: '仅在「公会与据点」启用时生效', fields: [
    { key: 'enabled', type: 'bool', label: '启用', default: true },
    { key: 'assignment_radius', type: 'int', label: '据点归属半径', default: 5000, hint: '玩家距据点多远以内算作驻守' },
    { key: 'ambiguity_ratio', type: 'float', label: '归属模糊比', default: 0.20, hint: '最近与次近据点距离之比超过此值时，暂不判定归属' },
    { key: 'confirmation_samples', type: 'int', label: '确认次数', default: 3 },
    { key: 'position_grid_size', type: 'int', label: '坐标网格边长', default: 2000 },
    { key: 'z_weight', type: 'float', label: '高度权重', default: 0.5, hint: '计算距离时高度（Z 轴）的权重' },
  ]},
  { key: 'privacy', title: '隐私与脱敏', subtitle: '决定玩家个人信息公开到什么程度', fields: [
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'], optionLabels: { strict: '最严', balanced: '均衡', advanced: '进阶' }, hint: '「最严」最保守；「均衡」为默认' },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false, hint: '关闭时只显示优秀 / 正常 / 偏高' },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60, hint: '≤ 此值为优秀（毫秒）' },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120, hint: '≤ 此值为正常，超过则为偏高（毫秒）' },
    { key: 'uncertain_timeout', type: 'int', label: '掉线判定时间（秒）', default: 900, hint: '超过此时长无响应即视为离线' },
  ]},
  { key: 'history', title: '数据保留', subtitle: '各类数据的留存目标；当前版本尚未自动清理', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合统计', default: 90 },
    { key: 'session_days', type: 'int', label: '玩家会话', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察记录', default: 180 },
  ]},
  { key: 'players', title: '玩家查询', subtitle: '「玩家查询」启用时生效', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'list_fold_limit', type: 'int', label: '列表折叠上限', default: 7, hint: '单个列表超过此条数则折叠为「前 N 条 + 汇总」（最小 1）' },
    { key: 'exclude_names', type: 'string', label: '排除名单', default: '', hint: '逗号分隔；名单内玩家不进榜单、不可查询' },
  ]},
  { key: 'presentation', title: '展示与卡片', subtitle: '个人名片图片版外观', fields: [
    { key: 'me_card_theme', type: 'enum', label: '名片主题', default: 'light', options: ['light', 'dark', 'auto'], optionLabels: { light: '浅色', dark: '暗色', auto: '跟随昼夜' }, hint: '个人名片图片版配色；「跟随昼夜」按服务器本地时钟（6:00–18:00 浅色，其余暗色）' },
  ]},
  { key: 'server_admin', title: '服务器管控', subtitle: '「服务器管控」任一组启用时生效；写操作仅授权管理员可用', fields: [
    { key: 'require_confirmation', type: 'bool', label: '危险命令二次确认', default: false, hint: '开启后关服 / 封禁等危险命令须在有效期内 /pal confirm 再确认' },
    { key: 'confirmation_timeout', type: 'int', label: '确认有效期（秒）', default: 30, hint: '二次确认的有效时长，超时作废（范围 5-600）' },
    { key: 'audit_retention_days', type: 'int', label: '审计留存天数', default: 180, hint: '管控操作日志留存目标（范围 1-3650；当前尚未自动清理；日志含玩家名 / 账号等明文信息）' },
  ]},
]

// 命令权限三态：inherit=继承默认 / on=强制开启（enable）或锁为仅管理员（admin_only）/
// off=强制关闭（enable）或放开（admin_only）。与后端 config._TRISTATE / _conf_schema.json
// command_permissions 行取值全等。
export type Tri = 'inherit' | 'on' | 'off'

// 命令组中文展示名（权限章命令树分组头）。null 组（扁平命令）归「其他」段。
export const GROUP_LABELS: Record<string, string> = {
  world: '世界', guild: '公会', player: '玩家', server: '服务器管控', link: '服务器授权',
}

export interface PalTreeNode {
  group: string | null // 组命令填组名（world/guild/player/server/link）；扁平命令为 null（其他段）
  path: string // 完整命令路径（`world status` / 扁平 `rank`）——与后端 COMMAND_META 键全等
  label: string // UI 展示名（无方括号，保 PAL_TREE 数组 JSON 可解析）
  enableConfigurable: boolean // 可配置启用（feat_group != core）
  adminConfigurable: boolean // 可配置仅管理员（path ∈ LOCKABLE_COMMANDS）
  adminForced: boolean // 强制仅管理员（gate ∈ admin/admin_write）
  danger: boolean // 危险写命令（path ∈ DANGER_COMMANDS）
  defaultEnabled: boolean // 内置启用默认（= 后端 default_enabled(path)：core/events/report→true，其余→false）
}

// 完整命令树描述：覆盖全部命令（COMMAND_META 全集，非仅可锁 15），供权限章树 UI 渲染。
// 每项各标志须与后端 command_permissions 派生谓词全等（enable_configurable /
// admin_configurable / admin_forced_true / DANGER_COMMANDS）——由
// tests/unit/frontend_pal_commands_test.py::test_frontend_tree_matches_backend_meta 跨端锚定。
// 【JSON 可解析】数组字面量用双引号键/值 + true/false/null，无嵌套 []，
// 便于 Python 端抽出数组文本直接 json.loads；改动请保持此形态。
export const PAL_TREE: PalTreeNode[] = [
  {"group": "world", "path": "world status", "label": "世界状态", "enableConfigurable": false, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": "world", "path": "world overview", "label": "世界概览", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "world", "path": "world rules", "label": "世界规则", "enableConfigurable": false, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": "world", "path": "world events", "label": "世界事件", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": "world", "path": "world today", "label": "今日日报", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": "guild", "path": "guild list", "label": "公会列表", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "guild", "path": "guild info", "label": "公会详情", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "guild", "path": "guild bases", "label": "据点列表", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "guild", "path": "guild base", "label": "据点详情", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "player", "path": "player info", "label": "玩家查询", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "player", "path": "player bind", "label": "绑定玩家", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "player", "path": "player unbind", "label": "解绑玩家", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": "server", "path": "server announce", "label": "全服广播", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": false},
  {"group": "server", "path": "server save", "label": "保存存档", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": false},
  {"group": "server", "path": "server kick", "label": "踢出玩家", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": false},
  {"group": "server", "path": "server unban", "label": "解封玩家", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": false},
  {"group": "server", "path": "server ban", "label": "封禁玩家", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": true, "defaultEnabled": false},
  {"group": "server", "path": "server shutdown", "label": "倒计时关服", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": true, "defaultEnabled": false},
  {"group": "server", "path": "server stop", "label": "立即停止", "enableConfigurable": true, "adminConfigurable": false, "adminForced": true, "danger": true, "defaultEnabled": false},
  {"group": "link", "path": "link list", "label": "服务器列表", "enableConfigurable": false, "adminConfigurable": false, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": "link", "path": "link add", "label": "授权服务器", "enableConfigurable": false, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": true},
  {"group": "link", "path": "link remove", "label": "撤销授权", "enableConfigurable": false, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": true},
  {"group": null, "path": "rank", "label": "排行榜", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": null, "path": "online", "label": "当前在线", "enableConfigurable": false, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": null, "path": "me", "label": "我的信息", "enableConfigurable": true, "adminConfigurable": true, "adminForced": false, "danger": false, "defaultEnabled": false},
  {"group": null, "path": "help", "label": "帮助", "enableConfigurable": false, "adminConfigurable": false, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": null, "path": "whoami", "label": "我的账号标识", "enableConfigurable": false, "adminConfigurable": false, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": null, "path": "whereami", "label": "本群标识", "enableConfigurable": false, "adminConfigurable": false, "adminForced": false, "danger": false, "defaultEnabled": true},
  {"group": null, "path": "confirm", "label": "确认执行", "enableConfigurable": false, "adminConfigurable": false, "adminForced": true, "danger": false, "defaultEnabled": true}
]
