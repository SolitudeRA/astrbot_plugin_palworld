import { describe, it, expect } from 'vitest'
import { PAL_TREE } from './schema'
import { effEnabled, inheritEnabled, effAdmin, writeAxis, DEFAULT_ENABLED, type PermMap } from './permissions'

const node = (path: string) => PAL_TREE.find((n) => n.path === path)!

describe('effEnabled 三级继承（复刻后端 effective_enabled）', () => {
  it('core 恒开（不可配）', () => {
    expect(effEnabled({}, node('world status'))).toBe(true)
    expect(effEnabled({ world: { enabled: 'off', admin_only: 'inherit' } }, node('world status'))).toBe(true)
  })
  it('无覆盖 → 内置默认（events 开 / players 关）', () => {
    expect(effEnabled({}, node('world events'))).toBe(true)
    expect(effEnabled({}, node('player info'))).toBe(false)
    expect(effEnabled({}, node('rank'))).toBe(false)
  })
  it('叶子覆盖优先于组与内置', () => {
    const map: PermMap = { guild: { enabled: 'on', admin_only: 'inherit' }, 'guild list': { enabled: 'off', admin_only: 'inherit' } }
    expect(effEnabled(map, node('guild list'))).toBe(false)
    expect(effEnabled(map, node('guild info'))).toBe(true) // 兄弟随组
  })
  it('danger 不从组继承（F2）：server 组 on 时 ban 仍内置关', () => {
    const map: PermMap = { server: { enabled: 'on', admin_only: 'inherit' } }
    expect(effEnabled(map, node('server kick'))).toBe(true)   // 非 danger 随组
    expect(effEnabled(map, node('server ban'))).toBe(false)   // danger 只认叶子/内置
    expect(inheritEnabled(map, node('server ban'))).toBe(false)
  })
})

describe('effAdmin（复刻后端 effective_admin_only）', () => {
  it('forced 恒仅管理员；不可锁恒所有人', () => {
    expect(effAdmin({}, node('server kick'))).toBe(true)
    expect(effAdmin({}, node('help'))).toBe(false)
  })
  it('叶子 → 组 → 所有人', () => {
    expect(effAdmin({}, node('guild list'))).toBe(false)
    expect(effAdmin({ guild: { enabled: 'inherit', admin_only: 'on' } }, node('guild list'))).toBe(true)
    expect(effAdmin({ guild: { enabled: 'inherit', admin_only: 'on' }, 'guild list': { enabled: 'inherit', admin_only: 'off' } }, node('guild list'))).toBe(false)
  })
})

describe('writeAxis 稀疏写', () => {
  it('两轴全 inherit → 删键；单轴写不碰另一轴', () => {
    const m1 = writeAxis({}, 'rank', 'admin_only', 'on')
    expect(m1['rank']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    const m2 = writeAxis(m1, 'rank', 'admin_only', 'inherit')
    expect('rank' in m2).toBe(false)
    const m3 = writeAxis({ rank: { enabled: 'on', admin_only: 'on' } }, 'rank', 'admin_only', 'inherit')
    expect(m3['rank']).toEqual({ enabled: 'on', admin_only: 'inherit' }) // enabled 保留
  })
})

describe('DEFAULT_ENABLED 覆盖全部 PAL_TREE 路径', () => {
  it.each(PAL_TREE.map((n) => n.path))('%s 有内置默认', (path) => {
    expect(path in DEFAULT_ENABLED).toBe(true)
  })
})
