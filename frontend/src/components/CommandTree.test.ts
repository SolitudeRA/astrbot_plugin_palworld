import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandTree from './CommandTree.vue'
import type { CmdPerm } from '../lib/collect'
import type { Axis } from '../lib/permissions'

const mountTree = (axis: Axis, mv: Record<string, CmdPerm> = {}, hideGroups?: string[]) =>
  mount(CommandTree, { props: { modelValue: mv, axis, ...(hideGroups ? { hideGroups } : {}) } })
type W = ReturnType<typeof mountTree>
const leaf = (w: W, path: string) => w.findAll('.ct-leaf').find((r) => r.text().includes(path))!
const groupHead = (w: W, label: string) => w.findAll('.ct-grouphead').find((r) => r.text().includes(label))!
// server 组默认收折：需要其叶子的用例先点组名展开
const openGroup = (w: W, label: string) => groupHead(w, label).find('.ct-gname').trigger('click')

describe('enabled 轴（功能页实例）', () => {
  it('行集：完整命令树 29 条（enabled 轴全展开）；hidePaths 拆去危险区 5 条；核心命令显示锁定「恒开·内置」', () => {
    const w = mountTree('enabled')
    expect(w.findAll('.ct-leaf')).toHaveLength(29) // enabled 轴全展开（危险命令由页面危险区承载时才隐藏）
    const wh = mount(CommandTree, { props: { modelValue: {}, axis: 'enabled' as Axis, hidePaths: ['server kick', 'server unban', 'server ban', 'server shutdown', 'server stop'] } })
    expect(wh.findAll('.ct-leaf')).toHaveLength(24) // 危险区承载的 5 条不渲染
    const status = leaf(w, 'world status')
    expect(status.find('.ct-lock').exists()).toBe(true)
    expect(status.text()).toContain('恒开')
    expect(status.findAll('.pw-switch')).toHaveLength(0)
    expect(leaf(w, 'world events').find('.pw-switch').exists()).toBe(true)
  })
  it('生效值：events 内置开、player info 内置关；组覆盖 on → 随组、danger 不随组（F2）', async () => {
    expect(leaf(mountTree('enabled'), 'world events').find('.pw-switch').attributes('data-state')).toBe('checked')
    expect(leaf(mountTree('enabled'), 'player info').find('.pw-switch').attributes('data-state')).toBe('unchecked')
    const w = mountTree('enabled', { server: { enabled: 'on', admin_only: 'inherit' } })
    expect(leaf(w, 'server kick').find('.pw-switch').attributes('data-state')).toBe('checked')
    expect(leaf(w, 'server ban').find('.pw-switch').attributes('data-state')).toBe('unchecked')
    expect(leaf(w, 'server kick').classes()).toContain('grouped')
    expect(leaf(w, 'server ban').classes()).not.toContain('grouped') // danger 永不随组
  })
  it('danger 行带红「危险」标 + danger 类（enabled 轴专属）', () => {
    const row = leaf(mountTree('enabled'), 'server stop')
    expect(row.classes()).toContain('danger')
    expect(row.text()).toContain('危险')
  })
  it('组头开关写组键 enabled、不逐叶展开；切回默认清键', async () => {
    // 组头开关示范载体迁 player（可配组）：guild 上游不可用无可配叶子、组头无开关。
    const w = mountTree('enabled')
    await groupHead(w, '玩家').find('.pw-switch').trigger('click') // 组默认关 → 开
    let emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['player']).toEqual({ enabled: 'on', admin_only: 'inherit' })
    expect('player info' in emitted).toBe(false)
    const w2 = mountTree('enabled', { player: { enabled: 'on', admin_only: 'inherit' } })
    await groupHead(w2, '玩家').find('.pw-switch').trigger('click') // 开 → 关 == 默认 → 清
    emitted = w2.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect('player' in emitted).toBe(false)
  })
  it('enabled 轴组头开关收编例外但保留 danger 自设（F2 不归组管）', async () => {
    const w = mountTree('enabled', {
      'server kick': { enabled: 'off', admin_only: 'inherit' },  // 普通例外 → 收编
      'server ban': { enabled: 'on', admin_only: 'inherit' },    // danger 自设 → 保留
    })
    await groupHead(w, '服务器管控').find('.pw-switch').trigger('click') // 整组置 on
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['server']).toEqual({ enabled: 'on', admin_only: 'inherit' })
    expect('server kick' in emitted).toBe(false)                        // 例外被收编
    expect(emitted['server ban']).toEqual({ enabled: 'on', admin_only: 'inherit' }) // danger 保留
  })
  it('admin 覆盖不在 enabled 轴亮标', () => {
    const w = mountTree('enabled', { rank: { enabled: 'inherit', admin_only: 'on' } })
    expect(leaf(w, 'rank').find('.ov-dot').exists()).toBe(false)
    expect(leaf(w, 'rank').find('.ct-reset').exists()).toBe(false)
  })
  it('上游不可用叶行显「暂不可用」锁定 + 徽标「上游」非「内置」（无开关）', () => {
    const w = mountTree('enabled')
    const row = leaf(w, 'guild list')
    expect(row.find('.ct-lock').exists()).toBe(true)
    expect(row.text()).toContain('暂不可用')
    expect(row.text()).not.toContain('恒开')
    expect(row.find('.ct-lock small').text()).toBe('上游')
    expect(row.text()).not.toContain('内置')
    expect(row.findAll('.pw-switch')).toHaveLength(0) // 不可配无开关
  })
  it('存量 guild 组行不亮受管：不可配组头无 managed 类、无「整组」标', () => {
    // §3.5 容忍的存量 {"command":"guild","enabled":"on"} 组行不该让不可配组头误亮整组标
    const w = mountTree('enabled', { guild: { enabled: 'on', admin_only: 'inherit' } })
    const head = groupHead(w, '公会')
    expect(head.classes()).not.toContain('managed')
    expect(head.text()).not.toContain('整组')
    expect(head.find('.grp-tag').exists()).toBe(false)
  })
  it('可配组（player）组覆盖仍亮受管高亮 + 整组标（受管抑制不误伤可配组）', () => {
    const w = mountTree('enabled', { player: { enabled: 'on', admin_only: 'inherit' } })
    const head = groupHead(w, '玩家')
    expect(head.classes()).toContain('managed')
    expect(head.text()).toContain('整组')
  })
})

describe('admin_only 轴（权限章实例）', () => {
  it('行集：只列当前启用的命令（默认=恒开核心+events/today）；开功能后对应组出现', async () => {
    const w = mountTree('admin_only')
    expect(w.findAll('.ct-leaf')).toHaveLength(12) // 恒开核心 10（world2+link3+扁平5）+ events/today（overview force-off 不列）
    expect(w.findAll('.ct-leaf').some((r) => r.text().includes('guild list'))).toBe(false) // 上游不可用不列
    const help = leaf(w, '/pal help')
    expect(help.find('.ct-lock').exists()).toBe(true)
    expect(help.text()).toContain('所有人')
    expect(leaf(w, 'world status').find('.pw-switch').exists()).toBe(true) // 可锁行是开关
    // 开 server 基础写（组键）后 kick 出现为锁定行（forced 仅管理员）；danger 三条仍关不列
    const w2 = mountTree('admin_only', { server: { enabled: 'on', admin_only: 'inherit' } })
    await openGroup(w2, '服务器管控')
    const kick = leaf(w2, 'server kick')
    expect(kick.find('.ct-lock').exists()).toBe(true)
    expect(kick.text()).toContain('仅管理员')
    expect(w2.findAll('.ct-leaf').some((r) => r.text().includes('server ban'))).toBe(false) // danger 不随组
  })
  it('server 组 admin 全 forced → 组头无批量开关（显 —）', () => {
    const head = groupHead(mountTree('admin_only', { server: { enabled: 'on', admin_only: 'inherit' } }), '服务器管控')
    expect(head.findAll('.pw-switch')).toHaveLength(0)
    expect(head.find('.ct-na').exists()).toBe(true)
  })
  it('生效值：无覆盖 → 所有人（unchecked）；组覆盖 on → 随组 checked + grouped', () => {
    // admin 轴示范载体迁 player（guild 上游不可用不列于 admin 轴）。
    expect(leaf(mountTree('admin_only', { player: { enabled: 'on', admin_only: 'inherit' } }), 'player info').find('.pw-switch').attributes('data-state')).toBe('unchecked')
    const w = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'on' } })
    expect(leaf(w, 'player info').find('.pw-switch').attributes('data-state')).toBe('checked')
    expect(leaf(w, 'player info').classes()).toContain('grouped')
  })
  it('切开关偏离继承 → 写显式；切回继承 → 自动清 admin 轴', async () => {
    const w = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'inherit' } })
    await leaf(w, 'player info').find('.pw-switch').trigger('click')
    let emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['player info']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    expect(w.emitted('change')).toBeTruthy()
    const w2 = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'inherit' }, 'player info': { enabled: 'inherit', admin_only: 'on' } })
    await leaf(w2, 'player info').find('.pw-switch').trigger('click')
    emitted = w2.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect('player info' in emitted).toBe(false)
  })
  it('enabled 覆盖不在 admin 轴亮标（各轴只认本轴）', () => {
    const w2 = mountTree('admin_only', { rank: { enabled: 'on', admin_only: 'inherit' } })
    expect(leaf(w2, 'rank').find('.ov-dot').exists()).toBe(false)
  })
  it('组 admin 覆盖 → 组头「整组」标 + 受管态', () => {
    const w = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'on' } })
    const head = groupHead(w, '玩家')
    expect(head.text()).toContain('整组')
    expect(head.classes()).toContain('managed')
  })
  it('整组 + 叶子单独 → 标显「整组 · 1 单独」；组未管但有单独 → 弱化「1 单独」计数', () => {
    const w = mountTree('admin_only', {
      player: { enabled: 'on', admin_only: 'on' },
      'player info': { enabled: 'inherit', admin_only: 'off' },
    })
    const tag = groupHead(w, '玩家').find('.grp-tag')
    expect(tag.text()).toContain('整组 · 1 单独')
    expect(tag.classes()).toContain('mixed') // 非纯整组换 warn 色标
    const pure = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'on' } })
    expect(groupHead(pure, '玩家').find('.grp-tag').classes()).not.toContain('mixed')
    const w2 = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'inherit' }, 'player info': { enabled: 'inherit', admin_only: 'on' } })
    const head2 = groupHead(w2, '玩家')
    expect(head2.text()).toContain('1 单独')
    expect(head2.text()).not.toContain('整组')
    expect(head2.classes()).not.toContain('managed')
  })
  it('组头开关操作收编叶子例外（另一轴保留）', async () => {
    const w = mountTree('admin_only', { player: { enabled: 'on', admin_only: 'inherit' }, 'player info': { enabled: 'on', admin_only: 'off' } })
    await groupHead(w, '玩家').find('.pw-switch').trigger('click') // 整组置 on
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['player']).toEqual({ enabled: 'on', admin_only: 'on' })
    expect(emitted['player info']).toEqual({ enabled: 'on', admin_only: 'inherit' }) // admin 例外收编、enabled 保留
  })
  it('扁平组头无批量开关（无组键可写）', () => {
    expect(groupHead(mountTree('admin_only'), '其他').findAll('.pw-switch')).toHaveLength(0)
  })
  it('hideGroups=[link] 隐藏服务器授权组；缺省渲染', () => {
    expect(mountTree('admin_only', {}, ['link']).text()).not.toContain('服务器授权')
    expect(mountTree('admin_only').text()).toContain('服务器授权')
  })
  it('hideGroups 不触碰 modelValue（不删隐藏组权限、不发 emit）', () => {
    const mv: Record<string, CmdPerm> = { 'link list': { enabled: 'off', admin_only: 'inherit' } }
    const w = mountTree('admin_only', mv, ['link'])
    expect(w.text()).toContain('世界')
    expect(w.emitted('update:modelValue')).toBeFalsy()
    expect(mv['link list']).toEqual({ enabled: 'off', admin_only: 'inherit' })
  })
})
