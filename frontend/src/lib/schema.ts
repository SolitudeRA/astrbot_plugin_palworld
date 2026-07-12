export type FieldType = 'enum' | 'int' | 'float' | 'bool' | 'string'

export interface FieldSpec {
  key: string
  type: FieldType
  label: string
  default: unknown
  options?: string[]
  secret?: boolean // password / value：不预填、走哨兵
}
export interface ObjectSection { key: string; title: string; fields: FieldSpec[] }

export const SERVER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '' },
  { key: 'enabled', type: 'bool', label: '启用', default: true },
  { key: 'base_url', type: 'string', label: 'REST 地址', default: 'http://127.0.0.1:8212' },
  { key: 'username', type: 'string', label: 'Basic 用户名', default: 'admin' },
  { key: 'password', type: 'string', label: '密码', default: '', secret: true },
  { key: 'password_env', type: 'string', label: '密码环境变量名', default: '' },
  { key: 'timeout', type: 'int', label: '超时(秒)', default: 10 },
  { key: 'verify_tls', type: 'bool', label: '校验 TLS', default: true },
  { key: 'timezone', type: 'string', label: '时区(留空用全局)', default: '' },
]

export const HEADER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: 'Header 名', default: '' },
  { key: 'value', type: 'string', label: 'Header 值', default: '', secret: true },
  { key: 'value_env', type: 'string', label: '值环境变量名', default: '' },
  { key: 'servers', type: 'string', label: '限定服务器(逗号分隔;留空=全部)', default: '' },
]

export const OBJECT_SECTIONS: ObjectSection[] = [
  { key: 'routing', title: '路由与访问控制', fields: [
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'] },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '' },
  ]},
  { key: 'polling', title: '轮询间隔', fields: [
    { key: 'metrics_seconds', type: 'int', label: 'metrics(秒)', default: 30 },
    { key: 'players_seconds', type: 'int', label: 'players(秒)', default: 30 },
    { key: 'info_seconds', type: 'int', label: 'info(秒)', default: 600 },
    { key: 'settings_seconds', type: 'int', label: 'settings(秒)', default: 1800 },
    { key: 'game_data_seconds', type: 'int', label: 'game-data(秒)', default: 120 },
    { key: 'jitter_ratio', type: 'float', label: '抖动比例', default: 0.10 },
    { key: 'max_concurrency', type: 'int', label: '并发上限', default: 6 },
  ]},
  { key: 'world', title: '世界与展示', fields: [
    { key: 'timezone', type: 'string', label: '全局时区', default: 'Asia/Tokyo' },
    { key: 'locale', type: 'enum', label: '文案语言', default: 'zh-CN', options: ['zh-CN'] },
    { key: 'fps_smooth', type: 'int', label: 'FPS 流畅阈值', default: 50 },
    { key: 'fps_moderate', type: 'int', label: 'FPS 一般阈值', default: 35 },
    { key: 'fps_laggy', type: 'int', label: 'FPS 卡顿阈值', default: 20 },
  ]},
  { key: 'bases', title: '据点推导', fields: [
    { key: 'enabled', type: 'bool', label: '启用据点推导', default: true },
    { key: 'assignment_radius', type: 'int', label: '归属半径', default: 5000 },
    { key: 'ambiguity_ratio', type: 'float', label: '模糊比阈值', default: 0.20 },
    { key: 'confirmation_samples', type: 'int', label: '确认次数', default: 3 },
    { key: 'position_grid_size', type: 'int', label: '坐标网格', default: 2000 },
    { key: 'z_weight', type: 'float', label: 'Z 轴权重', default: 0.5 },
  ]},
  { key: 'privacy', title: '隐私与脱敏', fields: [
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'] },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60 },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120 },
    { key: 'uncertain_timeout', type: 'int', label: 'uncertain 超时(秒)', default: 900 },
  ]},
  { key: 'history', title: '保留清理天数', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标天数', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合天数', default: 90 },
    { key: 'session_days', type: 'int', label: '会话天数', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察天数', default: 180 },
  ]},
  { key: 'features', title: '功能分组开关', fields: [
    { key: 'report', type: 'bool', label: '日报/在线统计', default: true },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false },
    { key: 'players', type: 'bool', label: '玩家个体查询', default: false },
  ]},
  { key: 'players', title: '玩家个体', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'exclude_names', type: 'string', label: '排除名单（逗号分隔）', default: '' },
  ]},
]
