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

