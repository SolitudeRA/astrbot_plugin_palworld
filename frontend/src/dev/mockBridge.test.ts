import { describe, expect, it } from 'vitest'
import { createMockBridge } from './mockBridge'

describe('dev mock bridge locale patch', () => {
  it('只更新 world.locale，并在下一次 config/get 中保留', async () => {
    const bridge = createMockBridge('multi')
    const before = await bridge.apiGet('config/get')

    const result = await bridge.apiPost('config/locale', { locale: 'en' })
    const after = await bridge.apiGet('config/get')

    expect(result).toMatchObject({ ok: true, config: { world: { locale: 'en' } } })
    expect(after).toMatchObject({ ok: true, config: { world: { locale: 'en' } } })
    expect((after as any).config.routing).toEqual((before as any).config.routing)
    expect((after as any).config.servers).toEqual((before as any).config.servers)
  })

  it('status 响应同时返回稳定流畅度键与当前 locale 的显示串', async () => {
    const bridge = createMockBridge('multi')

    await bridge.apiPost('config/locale', { locale: 'ja' })
    const result = await bridge.apiGet('status/overview')
    const servers = (result as any).servers

    expect(result).toMatchObject({ ok: true })
    expect(servers[0]).toMatchObject({ smoothness: 'smooth', smoothness_label: '滑らか' })
    expect(servers[1]).toMatchObject({ smoothness: 'moderate', smoothness_label: '普通' })
  })

  it('audit 响应使用与真实仓库一致的稳定 action 键', async () => {
    const bridge = createMockBridge('multi')

    const result = await bridge.apiGet('audit/list')
    const actions = (result as any).audits.map((row: any) => row.action)

    expect(actions.slice(0, 4)).toEqual(['announce', 'kick', 'ban', 'save'])
    expect(actions.every((action: string) => !action.startsWith('server '))).toBe(true)
  })

  it('拒绝不支持的 locale，且不改现有配置', async () => {
    const bridge = createMockBridge('multi')

    const result = await bridge.apiPost('config/locale', { locale: 'fr' })
    const after = await bridge.apiGet('config/get')

    expect(result).toEqual({
      ok: false,
      error: 'invalid_field',
      detail: { path: 'world.locale' },
    })
    expect(after).toMatchObject({ ok: true, config: { world: { locale: 'zh-CN' } } })
  })
})
