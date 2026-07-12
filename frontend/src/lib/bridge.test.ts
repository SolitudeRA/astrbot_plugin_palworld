import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiGet, apiPost } from './bridge'
import { BridgeMissing, Unauthorized, BusinessError, RequestFailed } from './errors'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve(),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    ...impl,
  }
}

describe('bridge', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('apiGet 正常返回业务包', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, config: { servers: [] } }) })
    const r = await apiGet<{ ok: boolean; config: unknown }>('config/get')
    expect(r.config).toEqual({ servers: [] })
  })

  it('apiGet ok:false unauthorized → Unauthorized（根因 B 回归锚点）', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: false, error: 'unauthorized', detail: {} }) })
    await expect(apiGet('config/get')).rejects.toBeInstanceOf(Unauthorized)
  })

  it('apiPost ok:false 其他 → BusinessError 携带 code/path', async () => {
    setBridge({ apiPost: vi.fn().mockResolvedValue({ ok: false, error: 'credential_redirect', detail: { path: 'servers[0].password' } }) })
    await expect(apiPost('config/save', {})).rejects.toMatchObject({ code: 'credential_redirect', path: 'servers[0].password' })
  })

  it('transport reject → RequestFailed', async () => {
    setBridge({ apiGet: vi.fn().mockRejectedValue(new Error('network')) })
    await expect(apiGet('status/overview')).rejects.toBeInstanceOf(RequestFailed)
  })

  it('bridge 缺失 → BridgeMissing', async () => {
    await expect(apiGet('config/get')).rejects.toBeInstanceOf(BridgeMissing)
  })

  it('detail 非对象/无 path → BusinessError.path 为 undefined（detail 白名单）', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: false, error: 'invalid_shape', detail: null }) })
    await expect(apiGet('config/get')).rejects.toMatchObject({ code: 'invalid_shape', path: undefined })
  })
})
