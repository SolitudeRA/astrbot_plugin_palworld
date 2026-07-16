import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FeaturePanel from './FeaturePanel.vue'
import type { CmdPerm } from '../lib/collect'

const mk = (mv: Record<string, CmdPerm> = {}) => mount(FeaturePanel, { props: { modelValue: mv } })
const row = (w: ReturnType<typeof mk>, feat: string) => w.find(`[data-feat="${feat}"]`)

describe('FeaturePanel 功能开关', () => {
  it('渲染 6 个功能行，默认态：events 开、guilds_bases 关、danger 带危险标', () => {
    const w = mk()
    for (const f of ['events', 'report', 'guilds_bases', 'players', 'server_admin_basic', 'server_admin_danger'])
      expect(row(w, f).exists()).toBe(true)
    expect(row(w, 'events').find('.pw-switch').attributes('data-state')).toBe('checked')
    expect(row(w, 'guilds_bases').find('.pw-switch').attributes('data-state')).toBe('unchecked')
    expect(row(w, 'server_admin_danger').text()).toContain('危险')
  })

  it('开「公会与据点」→ 写 guild 组键 on', async () => {
    const w = mk()
    await row(w, 'guilds_bases').find('.pw-switch').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['guild']).toEqual({ enabled: 'on', admin_only: 'inherit' })
    expect(w.emitted('change')).toBeTruthy()
  })

  it('开「玩家相关」→ 写 player/rank/me 三键（照后端迁移表映射）', async () => {
    const w = mk()
    await row(w, 'players').find('.pw-switch').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    for (const k of ['player', 'rank', 'me']) expect(emitted[k]).toEqual({ enabled: 'on', admin_only: 'inherit' })
  })

  it('关回默认 → 键清除（不留冗余覆盖）', async () => {
    const w = mk({ guild: { enabled: 'on', admin_only: 'inherit' } })
    await row(w, 'guilds_bases').find('.pw-switch').trigger('click') // on → off == 默认 → inherit
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect('guild' in emitted).toBe(false)
  })

  it('成员被单独设置（不一致）→ 显示「部分开启」；切开关收编成员叶子覆盖（admin 轴保留）', async () => {
    const w = mk({
      guild: { enabled: 'on', admin_only: 'inherit' },
      'guild list': { enabled: 'off', admin_only: 'on' },
    })
    expect(row(w, 'guilds_bases').text()).toContain('部分开启')
    await row(w, 'guilds_bases').find('.pw-switch').trigger('click') // mixed 按开显示 → 目标关（=默认）→ 全收编
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect('guild' in emitted).toBe(false)                       // 组键清除（关==默认）
    expect(emitted['guild list']).toEqual({ enabled: 'inherit', admin_only: 'on' }) // 叶子 enabled 收编、admin 保留
  })

  it('危险功能开关写 3 个 danger 叶子键（danger 不走组键，F2）', async () => {
    const w = mk()
    await row(w, 'server_admin_danger').find('.pw-switch').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    for (const k of ['server ban', 'server shutdown', 'server stop'])
      expect(emitted[k]).toEqual({ enabled: 'on', admin_only: 'inherit' })
    expect('server' in emitted).toBe(false)
  })
})
