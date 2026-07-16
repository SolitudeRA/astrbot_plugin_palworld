import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandTree from './CommandTree.vue'
import type { CmdPerm } from '../lib/collect'

const mountTree = (mv: Record<string, CmdPerm> = {}, hideGroups?: string[]) =>
  mount(CommandTree, { props: { modelValue: mv, ...(hideGroups ? { hideGroups } : {}) } })
const leaf = (w: ReturnType<typeof mountTree>, path: string) =>
  w.findAll('.ct-leaf').find((r) => r.text().includes(path))!
const groupHead = (w: ReturnType<typeof mountTree>, label: string) =>
  w.findAll('.ct-grouphead').find((r) => r.text().includes(label))!

describe('管理员限制表（单轴）行集', () => {
  it('只列可锁命令：world status 在、forced 的 server kick 不在、不可锁的 help 不在', () => {
    const w = mountTree()
    expect(leaf(w, 'world status')).toBeTruthy()
    expect(w.findAll('.ct-leaf').some((r) => r.text().includes('server kick'))).toBe(false)
    expect(w.findAll('.ct-leaf').some((r) => r.text().includes('/pal help'))).toBe(false)
  })
  it('表尾说明收拢内置规则（恒仅管理员 / 恒所有人）', () => {
    const w = mountTree()
    expect(w.find('.ct-note').text()).toContain('恒需管理员')
    expect(w.find('.ct-note').text()).toContain('不可更改')
  })
  it('扁平可锁命令归「其他」段（rank/online/me）', () => {
    const w = mountTree()
    const flat = w.findAll('.ct-group').find((g) => g.text().includes('其他'))!
    expect(flat.text()).toContain('rank')
    expect(flat.text()).toContain('排行榜')
  })
})

describe('生效值与开关写值', () => {
  it('无覆盖 → 开关显所有人（unchecked）；组覆盖 on → 叶子随组 checked + grouped 竖条', () => {
    expect(leaf(mountTree(), 'guild list').find('.pw-switch').attributes('data-state')).toBe('unchecked')
    const w = mountTree({ guild: { enabled: 'inherit', admin_only: 'on' } })
    expect(leaf(w, 'guild list').find('.pw-switch').attributes('data-state')).toBe('checked')
    expect(leaf(w, 'guild list').classes()).toContain('grouped')
  })
  it('切开关偏离继承 → 写显式；切回继承值 → 自动清 admin 轴', async () => {
    const w = mountTree()
    await leaf(w, 'player info').find('.pw-switch').trigger('click')
    let emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['player info']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    const w2 = mountTree({ 'player info': { enabled: 'inherit', admin_only: 'on' } })
    await leaf(w2, 'player info').find('.pw-switch').trigger('click')
    emitted = w2.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect('player info' in emitted).toBe(false)
    expect(w2.emitted('change')).toBeTruthy()
  })
  it('组头开关写组名行、不逐叶展开', async () => {
    const w = mountTree()
    await groupHead(w, '世界').find('.pw-switch').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['world']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    expect('world status' in emitted).toBe(false)
  })
  it('扁平组头无批量开关（无组键可写）', () => {
    const head = groupHead(mountTree(), '其他')
    expect(head.findAll('.pw-switch')).toHaveLength(0)
  })
})

describe('覆盖来源可视化与恢复（只认 admin 轴）', () => {
  it('admin 单独设置 → 圆点 + ovr 环 + ↺；enabled 覆盖不亮标（归功能页管辖）', () => {
    const w = mountTree({ 'rank': { enabled: 'inherit', admin_only: 'on' } })
    expect(leaf(w, 'rank').find('.ov-dot').exists()).toBe(true)
    expect(leaf(w, 'rank').find('.pw-switch').classes()).toContain('ovr')
    expect(leaf(w, 'rank').find('.ct-reset').exists()).toBe(true)
    const w2 = mountTree({ 'rank': { enabled: 'on', admin_only: 'inherit' } })
    expect(leaf(w2, 'rank').find('.ov-dot').exists()).toBe(false)
    expect(leaf(w2, 'rank').find('.ct-reset').exists()).toBe(false)
  })
  it('↺ 只清 admin 轴，enabled 覆盖原样保留', async () => {
    const w = mountTree({ 'rank': { enabled: 'on', admin_only: 'on' } })
    await leaf(w, 'rank').find('.ct-reset').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['rank']).toEqual({ enabled: 'on', admin_only: 'inherit' })
  })
  it('组 admin 覆盖 → 组头「整组」标 + 受管态类；组头 ↺ 清组 admin', async () => {
    const w = mountTree({ guild: { enabled: 'inherit', admin_only: 'on' } })
    const head = groupHead(w, '公会')
    expect(head.text()).toContain('整组')
    expect(head.classes()).toContain('managed')
    await head.find('.ct-reset').trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect('guild' in emitted).toBe(false)
  })
})

describe('hideGroups（单模式）', () => {
  it('单模式说明行不提「服务器授权」；多模式提', () => {
    expect(mountTree({}, ['link']).find('.ct-note').text()).not.toContain('服务器授权')
    expect(mountTree().find('.ct-note').text()).toContain('服务器授权')
  })
  it('hideGroups 不触碰 modelValue（不删隐藏组权限、不发 emit）', () => {
    const mv: Record<string, CmdPerm> = { 'link list': { enabled: 'off', admin_only: 'inherit' } }
    const w = mountTree(mv, ['link'])
    expect(w.text()).toContain('世界')
    expect(w.emitted('update:modelValue')).toBeFalsy()
    expect(mv['link list']).toEqual({ enabled: 'off', admin_only: 'inherit' })
  })
})
