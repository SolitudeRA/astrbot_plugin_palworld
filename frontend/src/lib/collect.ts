import { OBJECT_SECTIONS, type FieldType, type Tri } from './schema'

export const SENTINEL = '__unchanged__'

// 命令树单元格三态（enable / admin_only 两轴）。命令树 state 为稀疏 map：
// 键为命令完整路径或组名，仅「被触碰过」的命令进 map，两轴皆 inherit 的行 collect 时省略。
export interface CmdPerm { enabled: Tri; admin_only: Tri }

export interface SettingsState {
  servers: Record<string, unknown>[]
  custom_headers: Record<string, unknown>[]
  // 可选：部分 SettingsState 构造点（含旧测试）不带这些键，collectBody 以兜底避免崩
  permission_admins?: Record<string, unknown>[]
  // 单世界受限模式的授权群名单（顶层键 single_allowed_groups，行结构 {umo, note}）。
  // collectBody 无条件回传（含 multi 模式）——防切模式保存时把名单抹除
  single_allowed_groups?: Record<string, unknown>[]
  // 命令权限树 state：command(路径/组名) -> 两轴三态。稀疏，仅含被覆盖的命令
  command_perms?: Record<string, CmdPerm>
  sections: Record<string, Record<string, unknown>>
}

const str = (v: unknown): string => (v == null ? '' : String(v))

export function collectSecret(value: unknown, isNew: boolean): string {
  const v = str(value)
  if (v === SENTINEL) throw new Error('不能使用保留字 __unchanged__')
  if (v !== '') return v
  return isNew ? '' : SENTINEL
}

function coerce(type: FieldType, v: unknown): unknown {
  if (type === 'int' || type === 'float') return typeof v === 'number' ? v : Number(v)
  if (type === 'bool') return v === true // 严格：只有 boolean true 为真，杜绝 'false'→true
  return str(v) // string / enum
}

function collectServer(row: Record<string, unknown>): Record<string, unknown> {
  const rowId = (row.__row_id as string) || null
  const isNew = !rowId
  return {
    __row_id: rowId,
    name: str(row.name),
    enabled: row.enabled === true,
    base_url: str(row.base_url),
    username: str(row.username),
    password: collectSecret(row.password, isNew),
    password_env: str(row.password_env),
    timeout: typeof row.timeout === 'number' ? row.timeout : Number(row.timeout),
    verify_tls: row.verify_tls === true,
    timezone: str(row.timezone),
  }
}

function collectHeader(row: Record<string, unknown>): Record<string, unknown> {
  const rowId = (row.__row_id as string) || null
  const isNew = !rowId
  return {
    __row_id: rowId,
    name: str(row.name),
    value: collectSecret(row.value, isNew),
    value_env: str(row.value_env),
    servers: str(row.servers),
  }
}

function collectAdmin(row: Record<string, unknown>): Record<string, unknown> {
  return { __row_id: (row.__row_id as string) || null, id: str(row.id), note: str(row.note) }
}

function collectGroup(row: Record<string, unknown>): Record<string, unknown> {
  return { __row_id: (row.__row_id as string) || null, umo: str(row.umo), note: str(row.note) }
}

export function collectBody(state: SettingsState): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  body.servers = state.servers.map(collectServer)
  body.custom_headers = state.custom_headers.map(collectHeader)
  // ?? []：缺省即空，避免 undefined.map 崩溃
  body.permission_admins = (state.permission_admins ?? []).map(collectAdmin)
  // 无条件回传（含 multi）：切到 multi 保存时不抹除单模式授权群名单（数据安全）
  body.single_allowed_groups = (state.single_allowed_groups ?? []).map(collectGroup)
  // command_permissions：命令树 state → 稀疏三态行。两轴皆 inherit 的命令省略；
  // 组名行覆盖整组、完整路径行覆盖单叶。保插入顺序（hydrate 时按 config 行序、编辑时追加）
  const perms = state.command_perms ?? {}
  body.command_permissions = Object.keys(perms).reduce<Record<string, string>[]>((rows, command) => {
    const { enabled, admin_only } = perms[command]
    if (enabled !== 'inherit' || admin_only !== 'inherit') rows.push({ command, enabled, admin_only })
    return rows
  }, [])
  for (const section of OBJECT_SECTIONS) {
    const vals = state.sections[section.key] ?? {}
    const out: Record<string, unknown> = {}
    for (const f of section.fields) out[f.key] = coerce(f.type, vals[f.key])
    body[section.key] = out
  }
  // 绝不含 group_bindings：后端缺键保留旧值，避免清空预设群授权（spec §4.3）
  return body
}
