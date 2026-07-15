import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  previewTransfer, postTransfer, listOrphans, purgeOrphans, mapTransferError,
} from './transfer'
import { BusinessError, Unauthorized } from './errors'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn(), ...impl }
}

describe('transfer client', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('previewTransfer 用 target 查询串调 apiGet 并透传 payload', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], bindings: [] })
    setBridge({ apiGet })
    const pv = await previewTransfer('single')
    expect(apiGet).toHaveBeenCalledWith('mode/transfer/preview?target=single')
    expect(pv.ready_servers).toEqual([{ server_id: 'a', name: 'a' }])
  })

  it('postTransfer ok:true 返回 config/warnings/summary，body 原样透传', async () => {
    const apiPost = vi.fn().mockResolvedValue({
      ok: true, config: { routing: { world_mode: 'single' } }, warnings: {},
      summary: { from: 'multi', to: 'single', surviving: 'a', migrated: 1, purged: {}, failed_server_ids: [] },
    })
    setBridge({ apiPost })
    const r = await postTransfer({ target_mode: 'single', surviving_server_id: 'a', migrate_umos: ['u1'], purge_others: false })
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'single', surviving_server_id: 'a', migrate_umos: ['u1'], purge_others: false })
    expect((r.config as any).routing.world_mode).toBe('single')
    expect(r.summary.migrated).toBe(1)
  })

  it('postTransfer ok:false → 抛 BusinessError（模式不变由调用方处理）', async () => {
    setBridge({ apiPost: vi.fn().mockResolvedValue({ ok: false, error: 'too_many_groups', detail: {} }) })
    await expect(postTransfer({ target_mode: 'single', migrate_umos: [], purge_others: false }))
      .rejects.toBeInstanceOf(BusinessError)
  })

  it('listOrphans 调 apiGet mode/orphans', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, orphans: ['ghost'] })
    setBridge({ apiGet })
    const r = await listOrphans()
    expect(apiGet).toHaveBeenCalledWith('mode/orphans')
    expect(r.orphans).toEqual(['ghost'])
  })

  it('purgeOrphans 无参不带 server_ids（清全部当前孤儿）', async () => {
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: {}, rejected: [], failed_server_ids: [] })
    setBridge({ apiPost })
    await purgeOrphans()
    expect(apiPost).toHaveBeenCalledWith('mode/orphans/purge', {})
  })

  it('purgeOrphans 显式空数组 → 原样透传 server_ids:[]（后端 FIX1：清 nothing，不退化为清全部）', async () => {
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: {}, rejected: [], failed_server_ids: [] })
    setBridge({ apiPost })
    await purgeOrphans([])
    expect(apiPost).toHaveBeenCalledWith('mode/orphans/purge', { server_ids: [] })
  })

  it('purgeOrphans 显式数组 → 透传 server_ids', async () => {
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: {}, rejected: [], failed_server_ids: [] })
    setBridge({ apiPost })
    await purgeOrphans(['a'])
    expect(apiPost).toHaveBeenCalledWith('mode/orphans/purge', { server_ids: ['a'] })
  })

  it('mapTransferError 映射业务码 / Unauthorized / 未知码兜底', () => {
    expect(mapTransferError(new BusinessError('migrate_bind_failed'))).toContain('预绑定失败')
    expect(mapTransferError(new BusinessError('too_many_groups'))).toContain('上限')
    expect(mapTransferError(new Unauthorized())).toContain('未登录')
    expect(mapTransferError(new BusinessError('unknown_x'))).toBe('操作失败，请重试')
  })
})
