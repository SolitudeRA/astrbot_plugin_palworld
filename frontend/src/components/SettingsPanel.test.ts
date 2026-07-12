import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsPanel from './SettingsPanel.vue'

const cfg = () => ({ ok: true, config: {
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
  routing: { access_mode: 'restricted', default_server: '' },
  polling: { metrics_seconds: 30, players_seconds: 30, info_seconds: 600, settings_seconds: 1800,
    game_data_seconds: 120, jitter_ratio: 0.1, max_concurrency: 6 },
  world: { timezone: 'Asia/Tokyo', locale: 'zh-CN', fps_smooth: 50, fps_moderate: 35, fps_laggy: 20 },
  bases: { enabled: true, assignment_radius: 5000, ambiguity_ratio: 0.2, confirmation_samples: 3,
    position_grid_size: 2000, z_weight: 0.5 },
  privacy: { mode: 'balanced', public_exact_ping: false, public_positions: false,
    ping_good_ms: 60, ping_ok_ms: 120, uncertain_timeout: 900 },
  history: { raw_metrics_days: 7, aggregate_days: 90, session_days: 365, observation_days: 180 },
  features: { report: true, events: true, guilds_bases: false, players: false },
  players: { rank_top_n: 5, exclude_names: '' },
}, page_version: 1 })

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

describe('SettingsPanel', () => {
  it('加载后渲染 10 节（含 features 分组标题）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mount(SettingsPanel); await flushPromises()
    expect(w.text()).toContain('功能分组开关')
    expect(w.text()).toContain('玩家个体')
    expect(w.text()).toContain('路由与访问控制')
    expect(w.text()).toContain('保存并重载')
  })
  it('config/get unauthorized → 整块错误态，不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: false, error: 'unauthorized', detail: {} })
    const w = mount(SettingsPanel); await flushPromises()
    expect(w.text()).toContain('未登录')
  })
  it('保存调用 apiPost，body 不含 group_bindings 且类型正确', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: true, warnings: {} })
    const w = mount(SettingsPanel); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    const [, body] = (window.AstrBotPluginPage!.apiPost as any).mock.calls[0]
    expect('group_bindings' in body).toBe(false)
    expect(typeof body.polling.metrics_seconds).toBe('number')
    expect(typeof body.features.report).toBe('boolean')
  })
  it('保存业务错误 credential_redirect → 就地提示，不打整页错误态', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: false, error: 'credential_redirect', detail: { path: 'servers[0].password' } })
    const w = mount(SettingsPanel); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    expect(w.text()).toContain('请重新输入该服务器密码')
    expect(w.text()).toContain('功能分组开关') // 表单仍在（未塌成整页错误）
  })
})
