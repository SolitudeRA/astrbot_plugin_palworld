export type FieldType = 'enum' | 'int' | 'float' | 'bool' | 'string'

export interface FieldSpec {
  key: string
  type: FieldType
  label: string
  default: unknown
  options?: string[]
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
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'], hint: 'restricted 需管理员授权；open 全开放' },
    { key: 'world_mode', type: 'enum', label: '运行模式', default: 'multi', options: ['multi', 'single'], hint: 'multi 多世界（按群绑定/切换服务器）；single 单世界（所有操作对应唯一服务器）。⚠️ single + restricted 并存时访问控制不生效' },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '', hint: '群里没指定、也没绑定时查询它' },
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
    { key: 'locale', type: 'enum', label: '消息语言', default: 'zh-CN', options: ['zh-CN'] },
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
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'], hint: 'strict 最保守；balanced 为默认' },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false, hint: '关闭时只显示优秀 / 正常 / 偏高' },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60, hint: '≤ 此值为优秀（毫秒）' },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120, hint: '≤ 此值为正常，超过则为偏高（毫秒）' },
    { key: 'uncertain_timeout', type: 'int', label: '掉线判定时间（秒）', default: 900, hint: '超过此时长无响应即视为离线' },
  ]},
  { key: 'history', title: '数据保留', subtitle: '各类数据的保留天数，到期自动清理', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合统计', default: 90 },
    { key: 'session_days', type: 'int', label: '玩家会话', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察记录', default: 180 },
  ]},
  { key: 'features', title: '功能开关', subtitle: '关闭的功能不采集数据，相关命令会提示未开放', fields: [
    { key: 'report', type: 'bool', label: '日报 / 在线统计', default: true, hint: '/pal today' },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true, hint: '/pal events' },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false, hint: '依赖 /game-data；专用服务器暂不支持' },
    { key: 'players', type: 'bool', label: '玩家查询', default: false, hint: '排行 / 档案 / 自助绑定' },
    { key: 'server_admin_basic', type: 'bool', label: '服务器管控·基础', default: false, hint: '公告 / 存档 / 踢人 / 解封等写操作，仅授权管理员可用；开启前请先配置管理员名单' },
    { key: 'server_admin_danger', type: 'bool', label: '服务器管控·危险', default: false, hint: '封禁 / 关服 / 停服等高破坏写操作，仅授权管理员可用；stop 会终止进程、可能丢失未存档进度，慎开' },
  ]},
  { key: 'players', title: '玩家查询', subtitle: '「玩家查询」启用时生效', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'exclude_names', type: 'string', label: '排除名单', default: '', hint: '逗号分隔；名单内玩家不进榜单、不可查询' },
  ]},
  { key: 'server_admin', title: '服务器管控', subtitle: '「服务器管控」任一组启用时生效；写操作仅授权管理员可用', fields: [
    { key: 'require_confirmation', type: 'bool', label: '危险命令二次确认', default: false, hint: '开启后关服 / 封禁等危险命令须在有效期内 /pal confirm 再确认' },
    { key: 'confirmation_timeout', type: 'int', label: '确认有效期（秒）', default: 30, hint: '二次确认的有效时长，超时作废（范围 5-600）' },
    { key: 'audit_retention_days', type: 'int', label: '审计留存天数', default: 180, hint: '管控操作日志保留天数，到期清理（范围 1-3650；日志含玩家名 / 账号等明文信息）' },
  ]},
]

// 可锁命令(astrbot 命令串)+ 所属功能组。内容须 == 后端 LOCKABLE_COMMANDS,
// 由 tests/unit/frontend_pal_commands_test.py 跨端锚定。
export const PAL_COMMANDS: { cmd: string; g: string }[] = [
  { cmd: 'world status', g: 'core' }, { cmd: 'world overview', g: 'core' },
  { cmd: 'world rules', g: 'core' }, { cmd: 'world events', g: 'events' },
  { cmd: 'world today', g: 'report' },
  { cmd: 'guild list', g: 'guilds_bases' }, { cmd: 'guild info', g: 'guilds_bases' },
  { cmd: 'guild bases', g: 'guilds_bases' }, { cmd: 'guild base', g: 'guilds_bases' },
  { cmd: 'player info', g: 'players' }, { cmd: 'player bind', g: 'players' },
  { cmd: 'player unbind', g: 'players' },
  { cmd: 'rank', g: 'players' }, { cmd: 'online', g: 'core' }, { cmd: 'me', g: 'players' },
]
