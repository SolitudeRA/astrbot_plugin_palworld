import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ModeTransfer from './ModeTransfer.vue'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn(), ...impl }
}
const mk = (worldMode: string, dirty = false, serverNames: string[] = ['a']) =>
  mount(ModeTransfer, { props: { worldMode, dirty, serverNames } })

describe('ModeTransfer 切换控件', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('渲染当前模式 + 切换按钮（multi 显示切换到单服务器）', () => {
    setBridge({})
    const w = mk('multi')
    expect(w.text()).toContain('当前模式：多服务器')
    expect(w.get('button[data-act="switch"]').text()).toContain('切换到单服务器')
  })

  it('dirty 时切换按钮禁用 + 提示先保存', () => {
    setBridge({})
    const w = mk('multi', true)
    expect((w.get('button[data-act="switch"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(w.text()).toContain('保存后可切换')
  })

  it('single→multi：预览就绪台后 flow=confirm、target=multi', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [] }) })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).target).toBe('multi')
    expect((w.vm as any).flow).toBe('confirm')
  })

  it('multi→single 单就绪台：flow=confirm、survivingId 取该台', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], bindings: [] }) })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('confirm')
    expect((w.vm as any).survivingId).toBe('a')
  })

  it('multi→single 多就绪台：flow=wizard', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }, { server_id: 'b', name: 'b' }], bindings: [] }) })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('wizard')
  })

  it('multi→single 零就绪台：notify 阻止、flow 保持 idle', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [], bindings: [] }) })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect(w.emitted('notify')?.[0]?.[1]).toBe(true) // error=true
  })

  it('restarting：notify 稍后再试、flow 保持 idle', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, restarting: true }) })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect((w.emitted('notify')?.[0]?.[0] as string)).toContain('重载中')
  })
})
