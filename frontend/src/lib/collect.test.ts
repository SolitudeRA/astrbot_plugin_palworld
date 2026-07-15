import { describe, it, expect } from 'vitest'
import { collectBody, collectSecret, SENTINEL, type SettingsState, type CmdPerm } from './collect'

const baseState = (): SettingsState => ({
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
  permission_admins: [],
  command_perms: {},
  sections: {
    routing: { access_mode: 'restricted', default_server: '' },
    polling: { metrics_seconds: 30, players_seconds: 30, info_seconds: 600, settings_seconds: 1800,
      game_data_seconds: 120, jitter_ratio: 0.1, max_concurrency: 6 },
    world: { timezone: 'Asia/Tokyo', locale: 'zh-CN', fps_smooth: 50, fps_moderate: 35, fps_laggy: 20 },
    bases: { enabled: true, assignment_radius: 5000, ambiguity_ratio: 0.2, confirmation_samples: 3,
      position_grid_size: 2000, z_weight: 0.5 },
    privacy: { mode: 'balanced', public_exact_ping: false, public_positions: false,
      ping_good_ms: 60, ping_ok_ms: 120, uncertain_timeout: 900 },
    history: { raw_metrics_days: 7, aggregate_days: 90, session_days: 365, observation_days: 180 },
    players: { rank_top_n: 5, exclude_names: '' },
    server_admin: { require_confirmation: false, confirmation_timeout: 30, audit_retention_days: 180 },
  },
})

// 命令树 state 稀疏 map：仅列出被覆盖命令，未列轴退化 inherit（保插入顺序）
function makeTreeState(overrides: Record<string, Partial<CmdPerm>>): SettingsState {
  const command_perms: Record<string, CmdPerm> = {}
  for (const k of Object.keys(overrides)) {
    command_perms[k] = { enabled: 'inherit', admin_only: 'inherit', ...overrides[k] }
  }
  return { servers: [], custom_headers: [], permission_admins: [], command_perms, sections: {} }
}

// 后端 config_view._TOP_KEYS（Phase 2：无 features/admin_only_commands，含 command_permissions）
const TOP_KEYS = ['servers', 'routing', 'group_bindings', 'custom_headers',
  'polling', 'world', 'bases', 'privacy', 'history', 'players',
  'server_admin', 'permission_admins', 'command_permissions', 'single_allowed_groups']

describe('collectBody', () => {
  it('数值字段产出 number（非字符串）', () => {
    const st = baseState(); st.sections.polling.metrics_seconds = '45' // 模拟原生 input 给了字符串
    const body = collectBody(st) as any
    expect(typeof body.polling.metrics_seconds).toBe('number')
    expect(body.polling.metrics_seconds).toBe(45)
    expect(typeof body.polling.jitter_ratio).toBe('number')
  })
  it('布尔字段产出 boolean（治 bool("false")===true 陷阱）', () => {
    const st = baseState(); st.sections.bases.enabled = 'false' // 模拟脏字符串
    const body = collectBody(st) as any
    expect(typeof body.bases.enabled).toBe('boolean')
    expect(body.bases.enabled).toBe(false) // 严格 === true，杜绝 'false'→true
    expect(body.privacy.public_exact_ping).toBe(false)
  })
  it('collectBody 产出 server_admin 段：数值转 number、开关转 boolean', () => {
    const st = baseState()
    st.sections.server_admin.confirmation_timeout = '45' // 模拟原生 input 给了字符串
    const body = collectBody(st) as any
    expect(typeof body.server_admin.require_confirmation).toBe('boolean')
    expect(typeof body.server_admin.confirmation_timeout).toBe('number')
    expect(body.server_admin.confirmation_timeout).toBe(45)
    expect(typeof body.server_admin.audit_retention_days).toBe('number')
    expect(body.server_admin.audit_retention_days).toBe(180)
  })
  it('body 完全不含 group_bindings 键（后端缺键保留旧值）', () => {
    expect('group_bindings' in (collectBody(baseState()) as any)).toBe(false)
  })
  it('body 完全不含 features / admin_only_commands（Phase 2 已由 command_permissions 取代）', () => {
    const body = collectBody(baseState()) as any
    expect('features' in body).toBe(false)
    expect('admin_only_commands' in body).toBe(false)
    expect(Array.isArray(body.command_permissions)).toBe(true)
  })
  it('顶层键 ⊆ 后端 _TOP_KEYS', () => {
    for (const k of Object.keys(collectBody(baseState()))) expect(TOP_KEYS).toContain(k)
  })
  it('collectBody 含 permission_admins(剥 meta)与 command_permissions 稀疏行', () => {
    const body = collectBody(makeTreeState({}))
    expect(body.command_permissions).toEqual([]) // 全 inherit → 空
    const st: any = makeTreeState({})
    st.permission_admins = [{ __row_id: 'adm-0', __local_key: 'local-1', id: 'aiocqhttp:1', note: 'x' }]
    expect(collectBody(st).permission_admins).toEqual([{ __row_id: 'adm-0', id: 'aiocqhttp:1', note: 'x' }])
  })
  it('collectBody 恒回传 single_allowed_groups（含 multi，防抹除）', () => {
    const state = { servers: [], custom_headers: [], sections: {}, single_allowed_groups: [{ __row_id: 'sag-0', umo: 'g1', note: 'x' }] } as any
    expect(collectBody(state).single_allowed_groups).toEqual([{ __row_id: 'sag-0', umo: 'g1', note: 'x' }])
  })
  it('collectBody 缺 single_allowed_groups 键退化空数组（不崩）', () => {
    expect(collectBody(makeTreeState({})).single_allowed_groups).toEqual([])
  })
  it('collectGroup 剥 __local_key、新行 __row_id 归 null（往返闭合）', () => {
    const st: any = makeTreeState({})
    st.single_allowed_groups = [{ __row_id: '', __local_key: 'local-1', umo: 'aiocqhttp:GroupMessage:1', note: '' }]
    expect(collectBody(st).single_allowed_groups).toEqual([{ __row_id: null, umo: 'aiocqhttp:GroupMessage:1', note: '' }])
  })
  it('command_permissions 稀疏三态行（两轴皆 inherit 的命令省略，保插入顺序）', () => {
    const state = makeTreeState({ guild: { enabled: 'on' }, 'world today': { enabled: 'off' } })
    expect(collectBody(state).command_permissions).toEqual([
      { command: 'guild', enabled: 'on', admin_only: 'inherit' },
      { command: 'world today', enabled: 'off', admin_only: 'inherit' },
    ])
  })
  it('command_permissions 全 inherit 的命令不产行（稀疏）', () => {
    const state = makeTreeState({ 'world status': { enabled: 'inherit', admin_only: 'inherit' }, 'player info': { admin_only: 'on' } })
    expect(collectBody(state).command_permissions).toEqual([
      { command: 'player info', enabled: 'inherit', admin_only: 'on' },
    ])
  })
  it('组名行覆盖整组：写组名一行、不逐叶展开', () => {
    const state = makeTreeState({ server: { enabled: 'on' } })
    const rows = collectBody(state).command_permissions as { command: string }[]
    expect(rows).toEqual([{ command: 'server', enabled: 'on', admin_only: 'inherit' }])
    // 整组启用只写组名行；ban/shutdown/stop 等 danger 叶子不随组写（复核 F2，由后端不继承组）
    expect(rows.some((r) => ['server ban', 'server shutdown', 'server stop'].includes(r.command))).toBe(false)
  })
  it('server 行保留 __row_id；新建行(无 id)不注入哨兵到空密码', () => {
    const st = baseState(); st.servers.push({ __row_id: '', name: 'b', enabled: true, base_url: '',
      username: 'admin', password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' })
    const body = collectBody(st) as any
    expect(body.servers[0].__row_id).toBe('srv-0')
    expect(body.servers[1].__row_id).toBe(null)
    expect(body.servers[1].password).toBe('') // 新建行空密码 = 无明文
  })
})

describe('collectSecret', () => {
  it('新建行留空 = 空串', () => { expect(collectSecret('', true)).toBe('') })
  it('既有行留空 = 哨兵', () => { expect(collectSecret('', false)).toBe(SENTINEL) })
  it('有值 = 原值', () => { expect(collectSecret('pw', false)).toBe('pw') })
  it('字面量哨兵输入被拒绝', () => { expect(() => collectSecret(SENTINEL, false)).toThrow() })
})

describe('collectHeader(经 collectBody)', () => {
  it('header 行:__row_id 保留/新行 null、secret 哨兵、字段透传、不含 __local_key', () => {
    const st = baseState()
    st.custom_headers.push(
      { __row_id: 'hdr-0', name: 'X-Api-Key', value: '', value_env: 'ENV_A', servers: 'a,b' },
      { __row_id: '', __local_key: 'local-1', name: 'CF-Id', value: 'tok', value_env: '', servers: '' },
    )
    const body = collectBody(st) as any
    expect(body.custom_headers).toHaveLength(2)
    expect(body.custom_headers[0]).toEqual({
      __row_id: 'hdr-0', name: 'X-Api-Key', value: SENTINEL, value_env: 'ENV_A', servers: 'a,b',
    })
    expect(body.custom_headers[1]).toEqual({
      __row_id: null, name: 'CF-Id', value: 'tok', value_env: '', servers: '',
    })
    expect('__local_key' in body.custom_headers[1]).toBe(false) // 客户端 key 不外传
  })
})
