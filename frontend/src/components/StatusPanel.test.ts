import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StatusPanel from './StatusPanel.vue'

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('StatusPanel', () => {
  it('渲染服务器状态卡片', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({
      ok: true, servers: [{ name: 'alpha', ready: true, online: 3, max_players: 32,
        fps: 59.4, smoothness_label: '流畅', world_day: 60, peak_online_today: 5,
        basecamp_count: 2, updated_at: Math.floor(Date.now() / 1000) - 12, degraded: false }] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('alpha')
    expect(w.text()).toContain('在线 3/32')
    expect(w.text()).toContain('FPS 59（流畅）')
    expect(w.text()).toContain('第 60 天')
    expect(w.text()).toContain('今日峰值 5')
    expect(w.text()).toContain('据点 2')
    expect(w.text()).toContain('秒前')
  })
  it('restarting 显示正在应用新配置', async () => {
    // restarting 态会 setTimeout(load, 3000)（StatusPanel.vue:19）；用假计时器
    // 避免真 3s 定时器泄漏到后续用例（afterEach 里 useRealTimers 复位）。
    vi.useFakeTimers()
    ;(window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, servers: [], restarting: true })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('正在应用新配置')
    w.unmount()
  })
  it('读取失败进 error 态,不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockRejectedValue(new Error('net'))
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('读取状态失败')
  })
})
