import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StatusPanel from './StatusPanel.vue'

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

describe('StatusPanel', () => {
  it('渲染服务器状态卡片', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({
      ok: true, servers: [{ name: 'alpha', ready: true, online: 3, smoothness_label: '流畅', degraded: false }] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('alpha')
    expect(w.text()).toContain('在线 3')
    expect(w.text()).toContain('流畅')
  })
  it('restarting 显示重载中', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, servers: [], restarting: true })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('正在重载')
  })
  it('读取失败进 error 态,不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockRejectedValue(new Error('net'))
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('读取状态失败')
  })
})
