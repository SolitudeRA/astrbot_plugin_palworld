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
  it('默认设置 tab，可切到状态', async () => {
    const w = mount(App); await flushPromises()
    const tabs = w.findAll('.pw-tabs button')
    expect(tabs[0].text()).toBe('设置')
    await tabs[1].trigger('click'); await flushPromises()
    expect(w.text()).toContain('刷新') // StatusPanel 的刷新按钮
  })
  it('子组件抛错 → 错误边界兜底，不白屏', async () => {
    const Boom = { setup() { throw new Error('boom-child') }, template: '<div/>' }
    const w = mount(App, { global: { stubs: { SettingsPanel: Boom } } })
    await flushPromises()
    expect(w.text()).toContain('boom-child')
  })
})
