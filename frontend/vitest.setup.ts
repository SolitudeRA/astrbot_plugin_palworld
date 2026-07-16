import { vi } from 'vitest'

// Node 25 的 experimental webstorage 与 jsdom 冲突，使 localStorage 退化为无方法空对象
// （getItem/setItem/clear 全 undefined）；CI 的 Node 22（.nvmrc）不受影响。缺方法时补一份
// 标准 in-memory Storage，令本地任意 Node 版本与 CI 等价，localStorage 断言可正常跑。
if (typeof globalThis.localStorage?.clear !== 'function') {
  const store = new Map<string, string>()
  const mem = {
    get length() { return store.size },
    clear() { store.clear() },
    getItem(k: string) { return store.has(k) ? store.get(k)! : null },
    key(i: number) { return [...store.keys()][i] ?? null },
    removeItem(k: string) { store.delete(k) },
    setItem(k: string, v: string) { store.set(k, String(v)) },
  } as Storage
  try {
    Object.defineProperty(globalThis, 'localStorage', { value: mem, configurable: true, writable: true })
  } catch {
    ;(globalThis as unknown as { localStorage: Storage }).localStorage = mem
  }
}

// 全局兜底 bridge；单测可在 beforeEach 覆盖 window.AstrBotPluginPage
vi.stubGlobal('AstrBotPluginPage', {
  ready: () => Promise.resolve(),
  apiGet: vi.fn().mockResolvedValue({}),
  apiPost: vi.fn().mockResolvedValue({ ok: true }),
})
