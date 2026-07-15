import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandTree from './CommandTree.vue'
import type { CmdPerm } from '../lib/collect'

const mountTree = (mv: Record<string, CmdPerm> = {}) => mount(CommandTree, { props: { modelValue: mv } })
const leaf = (w: ReturnType<typeof mountTree>, path: string) =>
  w.findAll('.ct-leaf').find((r) => r.text().includes(path))!
const groupHead = (w: ReturnType<typeof mountTree>, label: string) =>
  w.findAll('.ct-grouphead').find((r) => r.text().includes(label))!

describe('CommandTree 不可配格锁定', () => {
  it('核心命令 world status 的 enable 格锁定为「开」（内置），无三态段', () => {
    const cells = leaf(mountTree(), 'world status').findAll('.ct-cell')
    expect(cells[0].find('.ct-lock').exists()).toBe(true)
    expect(cells[0].text()).toContain('开')
    expect(cells[0].findAll('.seg')).toHaveLength(0)
  })
  it('server kick 的 admin_only 恒「仅管理员」锁定；enable 仍可配', () => {
    const cells = leaf(mountTree(), 'server kick').findAll('.ct-cell')
    expect(cells[0].findAll('.seg').length).toBeGreaterThan(0)
    expect(cells[1].find('.ct-lock').exists()).toBe(true)
    expect(cells[1].text()).toContain('仅管理员')
  })
  it('link list 的 admin_only 恒「所有人」锁定（非 forced 但不可锁）', () => {
    const cells = leaf(mountTree(), 'link list').findAll('.ct-cell')
    expect(cells[1].find('.ct-lock').exists()).toBe(true)
    expect(cells[1].text()).toContain('所有人')
  })
})

describe('CommandTree danger 标记与分组', () => {
  it('danger 叶子 server stop 有危险标记与 danger 类', () => {
    const row = leaf(mountTree(), 'server stop')
    expect(row.classes()).toContain('danger')
    expect(row.text()).toContain('危险')
  })
  it('扁平命令归「其他」段', () => {
    const w = mountTree()
    const flat = w.findAll('.ct-group').find((g) => g.text().includes('其他'))!
    expect(flat.text()).toContain('rank')
    expect(flat.text()).toContain('排行榜')
  })
})

describe('CommandTree 三态编辑与组头批量', () => {
  it('点击叶子三态段 → emit 新 map + change 事件', async () => {
    const w = mountTree()
    const adminCell = leaf(w, 'player info').findAll('.ct-cell')[1]
    await adminCell.findAll('.seg').find((b) => b.text() === '仅管理')!.trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['player info']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    expect(w.emitted('change')).toBeTruthy()
  })
  it('已覆盖单元格高亮为显式态（act），继承态不高亮', () => {
    const w = mountTree({ 'player info': { enabled: 'inherit', admin_only: 'on' } })
    const adminCell = leaf(w, 'player info').findAll('.ct-cell')[1]
    expect(adminCell.findAll('.seg').find((b) => b.text() === '仅管理')!.classes()).toContain('act')
    expect(adminCell.findAll('.seg').find((b) => b.text() === '默认')!.classes()).not.toContain('act')
  })
  it('组头「整组启用」写组名行、不逐叶展开（排除 danger 叶子，F2）', async () => {
    const w = mountTree()
    const enableCell = groupHead(w, '服务器管控').findAll('.ct-cell')[0]
    await enableCell.findAll('.seg').find((b) => b.text() === '开')!.trigger('click')
    const emitted = w.emitted('update:modelValue')!.at(-1)![0] as Record<string, CmdPerm>
    expect(emitted['server']).toEqual({ enabled: 'on', admin_only: 'inherit' })
    for (const d of ['server ban', 'server shutdown', 'server stop']) expect(d in emitted).toBe(false)
  })
  it('server 组「整组仅管理员」不可配（全 forced）→ 组头显 —', () => {
    const adminCell = groupHead(mountTree(), '服务器管控').findAll('.ct-cell')[1]
    expect(adminCell.find('.ct-na').exists()).toBe(true)
    expect(adminCell.findAll('.seg')).toHaveLength(0)
  })
})

describe('CommandTree hideGroups 显示过滤（单模式隐藏 link）', () => {
  it('hideGroups=[link] 时不渲染 link 组', () => {
    const wrapper = mount(CommandTree, { props: { modelValue: {}, hideGroups: ['link'] } })
    expect(wrapper.text()).not.toContain('服务器授权')  // GROUP_LABELS.link
  })
  it('hideGroups=[link] 仍渲染其他组，且不触碰 modelValue（不删隐藏组权限、不发 emit）', () => {
    const mv: Record<string, CmdPerm> = { 'link list': { enabled: 'off', admin_only: 'inherit' } }
    const wrapper = mount(CommandTree, { props: { modelValue: mv, hideGroups: ['link'] } })
    expect(wrapper.text()).toContain('世界')          // 未隐藏组照常渲染
    expect(wrapper.text()).not.toContain('服务器授权')  // link 组隐藏
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()  // 纯显示过滤，不改 state
    expect(mv['link list']).toEqual({ enabled: 'off', admin_only: 'inherit' })  // 隐藏组权限原样保留
  })
  it('hideGroups 缺省时 link 组正常渲染（多模式默认）', () => {
    expect(mountTree().text()).toContain('服务器授权')
  })
})
