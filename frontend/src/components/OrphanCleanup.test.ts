import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import OrphanCleanup from './OrphanCleanup.vue'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn(), ...impl }
}

describe('OrphanCleanup', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('有孤儿 → 渲染列表 + 勾选闸；勾选前清理按钮禁用', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, orphans: ['ghost', 'gone'] }) })
    const w = mount(OrphanCleanup); await flushPromises()
    expect(w.text()).toContain('ghost')
    expect(w.text()).toContain('残留数据清理')
    const btn = w.get('button[data-act="purge"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
    await w.get('input[data-act="ack"]').setValue(true)
    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('无孤儿 → 小节不渲染', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, orphans: [] }) })
    const w = mount(OrphanCleanup); await flushPromises()
    expect(w.text()).not.toContain('残留数据清理')
  })

  it('restarting → 视为无孤儿、不渲染', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, orphans: [], restarting: true }) })
    const w = mount(OrphanCleanup); await flushPromises()
    expect(w.text()).not.toContain('残留数据清理')
  })

  it('确认清理 → apiPost mode/orphans/purge 无 body + notify + 刷新列表', async () => {
    const apiGet = vi.fn()
      .mockResolvedValueOnce({ ok: true, orphans: ['ghost'] })   // mount
      .mockResolvedValueOnce({ ok: true, orphans: [] })          // 清理后刷新
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: { ghost: { worlds: 1 } }, rejected: [], failed_server_ids: [] })
    setBridge({ apiGet, apiPost })
    const w = mount(OrphanCleanup); await flushPromises()
    await w.get('input[data-act="ack"]').setValue(true)
    await w.get('button[data-act="purge"]').trigger('click'); await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/orphans/purge', {}) // 无 server_ids
    expect(apiGet).toHaveBeenCalledTimes(2) // mount + 刷新
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(false) // 成功
    expect(w.text()).not.toContain('残留数据清理') // 刷新后空
  })

  it('部分失败 failed_server_ids → 告警 notify(error)', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, orphans: ['ghost', 'bad'] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: { ghost: {} }, rejected: [], failed_server_ids: ['bad'] })
    setBridge({ apiGet, apiPost })
    const w = mount(OrphanCleanup); await flushPromises()
    await w.get('input[data-act="ack"]').setValue(true)
    await w.get('button[data-act="purge"]').trigger('click'); await flushPromises()
    expect((w.emitted('notify')?.at(-1)?.[0] as string)).toContain('失败')
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(true)
  })
})
