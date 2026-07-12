import { vi } from 'vitest'

// 全局兜底 bridge；单测可在 beforeEach 覆盖 window.AstrBotPluginPage
vi.stubGlobal('AstrBotPluginPage', {
  ready: () => Promise.resolve(),
  apiGet: vi.fn().mockResolvedValue({}),
  apiPost: vi.fn().mockResolvedValue({ ok: true }),
})
