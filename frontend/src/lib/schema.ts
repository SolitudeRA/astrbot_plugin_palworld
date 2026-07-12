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
  { key: 'base_url', type: 'string', label: '服务器地址', default: 'http://127.0.0.1:8212', hint: '官方只读 REST 端点，含端口（默认 8212）' },
  { key: 'username', type: 'string', label: '用户名', default: 'admin' },
  { key: 'password', type: 'string', label: '密码', default: '', secret: true, hint: '留空则保持不变；更推荐用下方环境变量' },
  { key: 'password_env', type: 'string', label: '密码环境变量名', default: '', hint: '与密码二选一，更安全' },
  { key: 'timeout', type: 'int', label: '超时（秒）', default: 10 },
  { key: 'verify_tls', type: 'bool', label: '校验 TLS 证书', default: true, hint: 'http 地址不校验' },
  { key: 'timezone', type: 'string', label: '时区', default: '', hint: '如 Asia/Tokyo；留空用全局时区' },
]

export const HEADER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '如 CF-Access-Client-Id' },
  { key: 'value', type: 'string', label: '值', default: '', secret: true, hint: '留空则保持不变；敏感值更推荐用环境变量' },
  { key: 'value_env', type: 'string', label: '值环境变量名', default: '', hint: '与值二选一，更安全' },
  { key: 'servers', type: 'string', label: '限定服务器', default: '', hint: '多个用逗号分隔；留空 = 发给所有服务器' },
]

export const OBJECT_SECTIONS: ObjectSection[] = [
  { key: 'routing', title: '路由与访问控制', subtitle: '群 ↔ 服务器 的寻址与授权', fields: [
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'], hint: 'restricted 需管理员授权 · open 全开放' },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '', hint: '群里没指定、也没绑定时用它' },
  ]},
  { key: 'polling', title: '轮询间隔', subtitle: '每个端点多久拉取一次数据（秒）', fields: [
    { key: 'metrics_seconds', type: 'int', label: 'metrics 指标', default: 30 },
    { key: 'players_seconds', type: 'int', label: 'players 在线', default: 30 },
    { key: 'info_seconds', type: 'int', label: 'info 信息', default: 600 },
    { key: 'settings_seconds', type: 'int', label: 'settings 设置', default: 1800 },
    { key: 'game_data_seconds', type: 'int', label: 'game-data 世界快照', default: 120, hint: '仅「公会与据点」开启时才拉取' },
    { key: 'jitter_ratio', type: 'float', label: '抖动比例', default: 0.10, hint: '给间隔加随机抖动，避免整点齐发' },
    { key: 'max_concurrency', type: 'int', label: '并发上限', default: 6, hint: '同时进行的请求数上限' },
  ]},
  { key: 'world', title: '世界与展示', subtitle: '时区与 FPS 流畅度分档', fields: [
    { key: 'timezone', type: 'string', label: '全局时区', default: 'Asia/Tokyo', hint: 'IANA' },
    { key: 'locale', type: 'enum', label: '文案语言', default: 'zh-CN', options: ['zh-CN'] },
    { key: 'fps_smooth', type: 'int', label: 'FPS 流畅阈值', default: 50, hint: '≥ 此值 = 流畅' },
    { key: 'fps_moderate', type: 'int', label: 'FPS 一般阈值', default: 35, hint: '≥ 此值 = 一般' },
    { key: 'fps_laggy', type: 'int', label: 'FPS 卡顿阈值', default: 20, hint: '≥ 此值 = 卡顿，低于 = 严重卡顿' },
  ]},
  { key: 'bases', title: '据点推导', subtitle: '仅在「公会与据点」开启时生效', fields: [
    { key: 'enabled', type: 'bool', label: '启用据点推导', default: true },
    { key: 'assignment_radius', type: 'int', label: '归属半径', default: 5000 },
    { key: 'ambiguity_ratio', type: 'float', label: '模糊比阈值', default: 0.20, hint: '最近 / 次近距离差比' },
    { key: 'confirmation_samples', type: 'int', label: '确认次数', default: 3 },
    { key: 'position_grid_size', type: 'int', label: '坐标网格', default: 2000, hint: '坐标量化网格边长' },
    { key: 'z_weight', type: 'float', label: 'Z 轴权重', default: 0.5 },
  ]},
  { key: 'privacy', title: '隐私与脱敏', subtitle: '决定纪事如何收敛个体信息', fields: [
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'], hint: 'strict 最保守 · balanced 默认' },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false, hint: '关 = 只显示优秀 / 正常 / 偏高' },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60, hint: '≤ 此值 = 优秀（毫秒）' },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120, hint: '≤ = 正常，超过 = 偏高（毫秒）' },
    { key: 'uncertain_timeout', type: 'int', label: '掉线判定超时', default: 900, hint: '多久无响应即判定离线（秒）' },
  ]},
  { key: 'history', title: '保留清理天数', subtitle: '各类数据的留存窗口（天）', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标天数', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合天数', default: 90 },
    { key: 'session_days', type: 'int', label: '会话天数', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察天数', default: 180 },
  ]},
  { key: 'features', title: '功能分组开关', subtitle: '关掉的分组不采集数据，相关命令提示「未开放」', fields: [
    { key: 'report', type: 'bool', label: '日报 / 在线统计', default: true, hint: '/pal today' },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true, hint: '/pal events' },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false, hint: '依赖 /game-data；专用服务器暂不支持' },
    { key: 'players', type: 'bool', label: '玩家个体查询', default: false, hint: '排行 / 档案 / 自助绑定' },
  ]},
  { key: 'players', title: '玩家个体', subtitle: '「玩家个体查询」开启时生效', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'exclude_names', type: 'string', label: '排除名单', default: '', hint: '逗号分隔，排除出榜 / 查询' },
  ]},
]
