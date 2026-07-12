import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from './App.vue'

beforeEach(() => {
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve(),
    apiGet: vi.fn().mockResolvedValue({ ok: true, config: {}, servers: [] }),
    apiPost: vi.fn().mockResolvedValue({ ok: true }),
  }
})

describe('App', () => {
  it('默认渲染报头与左索引，可切到观测台', async () => {
    const w = mount(App); await flushPromises()
    expect(w.text()).toContain('帕鲁纪事')
    const rail = w.findAll('.rail button')
    expect(rail.some((b) => b.text().includes('观测台'))).toBe(true)
    expect(rail.some((b) => b.text().includes('接入'))).toBe(true)
    const obs = rail.find((b) => b.text().includes('观测台'))!
    await obs.trigger('click'); await flushPromises()
    expect(w.text()).toContain('刷新') // 进入 StatusPanel
  })
  it('子组件抛错 → 错误边界兜底，不白屏', async () => {
    const Boom = { setup() { throw new Error('boom-child') }, template: '<div/>' }
    const w = mount(App, { global: { stubs: { SettingsPanel: Boom } } })
    await flushPromises()
    expect(w.text()).toContain('boom-child')
  })
})
