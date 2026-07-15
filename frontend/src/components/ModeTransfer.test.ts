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

  it('single→multi 确认 → POST 正确 body、ok:true 后 emit applied + 成功 notify', async () => {
    const savedCfg = { routing: { world_mode: 'multi' } }
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [{ umo: 'u1', note: '' }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: savedCfg, warnings: {},
      summary: { from: 'single', to: 'multi', surviving: null, migrated: 1, purged: {}, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    const dlg = w.findComponent({ name: 'ModeConfirmDialog' })
    expect(dlg.exists()).toBe(true)
    dlg.vm.$emit('confirm', ['u1']); await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'multi', migrate_umos: ['u1'], purge_others: false })
    expect(w.emitted('applied')?.[0]?.[0]).toEqual(savedCfg)
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(false) // 成功非 error
    expect((w.vm as any).flow).toBe('idle') // 子流关闭
  })

  it('multi→single 单台确认 → body 带 surviving_server_id、purge_others=false', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }], bindings: [{ umo: 'u1', server_ids: ['keep'] }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: {}, warnings: {},
      summary: { from: 'multi', to: 'single', surviving: 'keep', migrated: 1, purged: {}, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('confirm', ['u1']); await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'single', migrate_umos: ['u1'], purge_others: false, surviving_server_id: 'keep' })
  })

  it('ok:false（too_many_groups）→ 错误 notify、不 emit applied、模式不变', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [{ umo: 'u1', note: '' }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: false, error: 'too_many_groups', detail: {} })
    setBridge({ apiGet, apiPost })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('confirm', ['u1']); await flushPromises()
    expect(w.emitted('applied')).toBeFalsy()
    expect((w.emitted('notify')?.at(-1)?.[0] as string)).toContain('上限')
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(true)
  })

  it('ok:true 带 warnings.cleared_group_servers=false → applied + 告警 notify(error)', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }], bindings: [{ umo: 'u1', server_ids: ['keep'] }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: {}, warnings: { cleared_group_servers: false },
      summary: { from: 'multi', to: 'single', surviving: 'keep', migrated: 1, purged: {}, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('confirm', ['u1']); await flushPromises()
    expect(w.emitted('applied')).toBeTruthy() // 模式确已切、须对齐后端
    expect((w.emitted('notify')?.at(-1)?.[0] as string)).toContain('清理未尽')
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(true)
  })

  it('对话框 cancel → 关闭子流、无 POST', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [] })
    const apiPost = vi.fn()
    setBridge({ apiGet, apiPost })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('cancel'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect(apiPost).not.toHaveBeenCalled()
  })
})
