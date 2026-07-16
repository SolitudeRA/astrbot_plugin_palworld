// 命令权限生效值 + 功能组定义——复刻后端 application/command_permissions.py 的
// FEATURE_DEFAULTS / effective_enabled / effective_admin_only / _FEATURE_MIGRATION。
// 【demo 临时对齐】统一落地时 defaultEnabled 并入 PAL_TREE + 跨端锚定测试防漂移。
import type { PalTreeNode, Tri } from './schema'
import type { CmdPerm } from './collect'

export type Axis = 'enabled' | 'admin_only'
export type PermMap = Record<string, CmdPerm>

// 内置默认（enabled 轴）：core 恒开；events/report 默认开；
// guilds_bases/players/server_admin_* 默认关。
export const DEFAULT_ENABLED: Record<string, boolean> = {
  'world status': true, 'world overview': true, 'world rules': true,
  'world events': true, 'world today': true,
  'guild list': false, 'guild info': false, 'guild bases': false, 'guild base': false,
  'player info': false, 'player bind': false, 'player unbind': false,
  'server announce': false, 'server save': false, 'server kick': false, 'server unban': false,
  'server ban': false, 'server shutdown': false, 'server stop': false,
  'link list': true, 'link add': true, 'link remove': true,
  'rank': false, 'online': true, 'me': false,
  'help': true, 'whoami': true, 'whereami': true, 'confirm': true,
}
// 组的内置默认（组内可配叶子的 FEATURE_DEFAULTS，组内恰好一致）
export const GROUP_DEFAULT_ENABLED: Record<string, boolean> = {
  world: true, guild: false, player: false, server: false,
}

export const cellOf = (map: PermMap, command: string, axis: Axis): Tri =>
  map[command]?.[axis] ?? 'inherit'
export const hasOverride = (map: PermMap, command: string): boolean =>
  cellOf(map, command, 'enabled') !== 'inherit' || cellOf(map, command, 'admin_only') !== 'inherit'

// enabled 生效：叶子覆盖 → （danger 不随组，F2）→ 组覆盖 → 内置默认
export function inheritEnabled(map: PermMap, n: PalTreeNode): boolean {
  const dflt = DEFAULT_ENABLED[n.path] ?? false
  if (n.danger) return dflt
  if (n.group) {
    const g = cellOf(map, n.group, 'enabled')
    if (g !== 'inherit') return g === 'on'
  }
  return dflt
}
export function effEnabled(map: PermMap, n: PalTreeNode): boolean {
  if (!n.enableConfigurable) return true // core 恒开
  const leaf = cellOf(map, n.path, 'enabled')
  if (leaf !== 'inherit') return leaf === 'on'
  return inheritEnabled(map, n)
}
// admin_only 生效：forced 恒真；不可锁恒假；叶子 → 组 → 假（所有人）
export function inheritAdmin(map: PermMap, n: PalTreeNode): boolean {
  if (n.group) {
    const g = cellOf(map, n.group, 'admin_only')
    if (g !== 'inherit') return g === 'on'
  }
  return false
}
export function effAdmin(map: PermMap, n: PalTreeNode): boolean {
  if (n.adminForced) return true
  if (!n.adminConfigurable) return false
  const leaf = cellOf(map, n.path, 'admin_only')
  if (leaf !== 'inherit') return leaf === 'on'
  return inheritAdmin(map, n)
}

// 写单轴；两轴全 inherit 时删键（不留冗余空行）
export function writeAxis(map: PermMap, command: string, axis: Axis, v: Tri): PermMap {
  const cur: CmdPerm = map[command] ?? { enabled: 'inherit', admin_only: 'inherit' }
  const nextPerm: CmdPerm = { ...cur, [axis]: v }
  const next = { ...map }
  if (nextPerm.enabled === 'inherit' && nextPerm.admin_only === 'inherit') delete next[command]
  else next[command] = nextPerm
  return next
}

// ---- 功能组（对齐后端 FEATURE_DEFAULTS 键名 + _FEATURE_MIGRATION 写键映射）----
export interface FeatureSpec {
  key: string           // feat 组名（后端 FEATURE_DEFAULTS 键）
  label: string
  hint: string
  default: boolean
  danger?: boolean
  writeKeys: string[]   // 开关落盘键（命令组键或叶子键，照后端迁移表）
  memberPaths: string[] // 聚合生效值的成员命令（可配 enable 的叶子）
}
export const FEATURES: FeatureSpec[] = [
  { key: 'events', label: '世界事件', hint: '查询服务器事件流（/pal world events）',
    default: true, writeKeys: ['world events'], memberPaths: ['world events'] },
  { key: 'report', label: '今日日报', hint: '当天事件汇总报告（/pal world today）',
    default: true, writeKeys: ['world today'], memberPaths: ['world today'] },
  { key: 'guilds_bases', label: '公会与据点', hint: '公会列表 / 详情与据点推导；开启后增加世界数据轮询',
    default: false, writeKeys: ['guild'],
    memberPaths: ['guild list', 'guild info', 'guild bases', 'guild base'] },
  { key: 'players', label: '玩家查询与绑定', hint: '玩家信息 / 排行榜 / 我的信息与绑定',
    default: false, writeKeys: ['player', 'rank', 'me'],
    memberPaths: ['player info', 'player bind', 'player unbind', 'rank', 'me'] },
  { key: 'server_admin_basic', label: '服务器管控 · 基础', hint: '广播 / 存档 / 踢人 / 解封（写操作，仅管理员）',
    default: false, writeKeys: ['server announce', 'server save', 'server kick', 'server unban'],
    memberPaths: ['server announce', 'server save', 'server kick', 'server unban'] },
  { key: 'server_admin_danger', label: '服务器管控 · 危险', hint: '封禁 / 倒计时关服 / 立即停止（高危写操作，仅管理员）',
    default: false, danger: true, writeKeys: ['server ban', 'server shutdown', 'server stop'],
    memberPaths: ['server ban', 'server shutdown', 'server stop'] },
]

export type FeatureAgg = 'on' | 'off' | 'mixed'
export function featureAgg(map: PermMap, f: FeatureSpec, nodeOf: (path: string) => PalTreeNode): FeatureAgg {
  const vals = f.memberPaths.map((p) => effEnabled(map, nodeOf(p)))
  if (vals.every((v) => v)) return 'on'
  if (vals.every((v) => !v)) return 'off'
  return 'mixed'
}

// 功能开关写值：先清成员叶子 enabled 覆盖（收编例外，admin 轴保留），
// 再写映射键；目标 == 内置默认 → 写 inherit（清除，不留冗余）。
export function setFeature(map: PermMap, f: FeatureSpec, target: boolean): PermMap {
  let next = { ...map }
  for (const p of f.memberPaths) next = writeAxis(next, p, 'enabled', 'inherit')
  const v: Tri = target === f.default ? 'inherit' : (target ? 'on' : 'off')
  for (const k of f.writeKeys) next = writeAxis(next, k, 'enabled', v)
  return next
}
