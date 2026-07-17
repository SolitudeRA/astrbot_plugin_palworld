// 命令权限生效值 + 功能组定义——复刻后端 application/command_permissions.py 的
// FEATURE_DEFAULTS / effective_enabled / effective_admin_only / _FEATURE_MIGRATION。
// 内置启用默认单一真相源在 PAL_TREE.defaultEnabled（= 后端 default_enabled(path)），
// 由 tests/unit/frontend_pal_commands_test.py 跨端锚定；此处仅按 path/group 派生表。
import { PAL_TREE, type PalTreeNode, type Tri } from './schema'
import type { CmdPerm } from './collect'

export type Axis = 'enabled' | 'admin_only'
export type PermMap = Record<string, CmdPerm>

// 内置默认（enabled 轴）：core 恒开；events/report 默认开；
// guilds_bases/players/server_admin_* 默认关。由 PAL_TREE.defaultEnabled 派生。
export const DEFAULT_ENABLED: Record<string, boolean> = Object.fromEntries(
  PAL_TREE.map((n) => [n.path, n.defaultEnabled]),
)

// 组的内置默认：组内**可配（enableConfigurable）**叶子的 defaultEnabled。组内值须一致
// （不一致直接抛错，绝不静默取首个）；无可配叶子的组（如 link）不产键——消费方按 `?? false`。
function deriveGroupDefaults(): Record<string, boolean> {
  const out: Record<string, boolean> = {}
  for (const n of PAL_TREE) {
    if (n.group === null || !n.enableConfigurable) continue
    const prev = out[n.group]
    if (prev === undefined) out[n.group] = n.defaultEnabled
    else if (prev !== n.defaultEnabled)
      throw new Error(`组 ${n.group} 可配叶子 defaultEnabled 不一致：${prev} vs ${n.defaultEnabled}`)
  }
  return out
}
export const GROUP_DEFAULT_ENABLED: Record<string, boolean> = deriveGroupDefaults()

export const cellOf = (map: PermMap, command: string, axis: Axis): Tri =>
  map[command]?.[axis] ?? 'inherit'
export const hasOverride = (map: PermMap, command: string): boolean =>
  cellOf(map, command, 'enabled') !== 'inherit' || cellOf(map, command, 'admin_only') !== 'inherit'

// enabled 生效：叶子覆盖 → （danger 不随组，F2）→ 组覆盖 → 内置默认
export function inheritEnabled(map: PermMap, n: PalTreeNode): boolean {
  if (n.unavailable) return false // 上游不可用硬锁——必须先于 !enableConfigurable 的恒开(fail-open)分支
  const dflt = DEFAULT_ENABLED[n.path] ?? false
  if (n.danger) return dflt
  if (n.group) {
    const g = cellOf(map, n.group, 'enabled')
    if (g !== 'inherit') return g === 'on'
  }
  return dflt
}
export function effEnabled(map: PermMap, n: PalTreeNode): boolean {
  if (n.unavailable) return false // 上游不可用硬锁——必须先于 !enableConfigurable 的恒开(fail-open)分支
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

