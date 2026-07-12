import { OBJECT_SECTIONS, type FieldType } from './schema'

export const SENTINEL = '__unchanged__'

export interface SettingsState {
  servers: Record<string, unknown>[]
  custom_headers: Record<string, unknown>[]
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

export function collectBody(state: SettingsState): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  body.servers = state.servers.map(collectServer)
  body.custom_headers = state.custom_headers.map(collectHeader)
  for (const section of OBJECT_SECTIONS) {
    const vals = state.sections[section.key] ?? {}
    const out: Record<string, unknown> = {}
    for (const f of section.fields) out[f.key] = coerce(f.type, vals[f.key])
    body[section.key] = out
  }
  // 绝不含 group_bindings：后端缺键保留旧值，避免清空预设群授权（spec §4.3）
  return body
}
