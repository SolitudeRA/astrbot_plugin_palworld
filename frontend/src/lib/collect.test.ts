import { describe, it, expect } from 'vitest'
import { collectBody, collectSecret, SENTINEL, type SettingsState } from './collect'

const baseState = (): SettingsState => ({
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
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
    features: { report: true, events: true, guilds_bases: false },
  },
})

const TOP_KEYS = ['servers', 'routing', 'group_bindings', 'custom_headers',
  'polling', 'world', 'bases', 'privacy', 'history', 'features']

describe('collectBody', () => {
  it('数值字段产出 number（非字符串）', () => {
    const st = baseState(); st.sections.polling.metrics_seconds = '45' // 模拟原生 input 给了字符串
    const body = collectBody(st) as any
    expect(typeof body.polling.metrics_seconds).toBe('number')
    expect(body.polling.metrics_seconds).toBe(45)
    expect(typeof body.polling.jitter_ratio).toBe('number')
  })
  it('布尔字段产出 boolean（治 bool("false")===true 陷阱）', () => {
    const body = collectBody(baseState()) as any
    expect(typeof body.features.report).toBe('boolean')
    expect(body.features.guilds_bases).toBe(false)
  })
  it('body 完全不含 group_bindings 键（后端缺键保留旧值）', () => {
    expect('group_bindings' in (collectBody(baseState()) as any)).toBe(false)
  })
  it('顶层键 ⊆ 后端 _TOP_KEYS', () => {
    for (const k of Object.keys(collectBody(baseState()))) expect(TOP_KEYS).toContain(k)
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
