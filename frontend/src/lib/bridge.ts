import { BridgeMissing, Unauthorized, BusinessError, RequestFailed } from './errors'

function getBridge(): AstrBotBridge {
  const b = window.AstrBotPluginPage
  if (!b || typeof b.apiGet !== 'function') throw new BridgeMissing()
  return b
}

// 业务包统一解包：只白名单取 detail.path；ok:false 分流为 Unauthorized/BusinessError。
function unwrap<T>(r: any): T {
  if (r && typeof r === 'object' && r.ok === false) {
    const code = String(r.error ?? 'unknown')
    if (code === 'unauthorized') throw new Unauthorized()
    const path = r.detail && typeof r.detail === 'object' && typeof r.detail.path === 'string'
      ? r.detail.path : undefined
    throw new BusinessError(code, path)
  }
  return r as T
}

export async function ready(): Promise<void> {
  const b = getBridge()
  if (typeof b.ready === 'function') await b.ready()
}

export async function apiGet<T = unknown>(endpoint: string): Promise<T> {
  const b = getBridge()
  let r: any
  try { r = await b.apiGet(endpoint) } catch (e) { throw new RequestFailed((e as Error)?.message) }
  return unwrap<T>(r)
}

export async function apiPost<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
  const b = getBridge()
  let r: any
  try { r = await b.apiPost(endpoint, body) } catch (e) { throw new RequestFailed((e as Error)?.message) }
  return unwrap<T>(r)
}
