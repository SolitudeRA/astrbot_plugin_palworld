import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const styles = resolve(__dirname, 'tokens.css')
const css = readFileSync(styles, 'utf8')

describe('tokens.css 无半 px 字号漂移', () => {
  it('不含小数 px 字号', () => {
    const halfPx = css.match(/font-size:\s*\d+\.\d+px/g) ?? []
    expect(halfPx).toEqual([])
  })
  it('font-size 一律走 var(--fs-*)（除特征常量 line-height:1 外无裸 px 字号）', () => {
    const rawPx = css.match(/font-size:\s*\d+px/g) ?? []
    expect(rawPx).toEqual([])
  })
})

const COMPONENTS = [
  'CommandTree', 'SettingsPanel', 'ModeConfirmDialog', 'OrphanCleanup', 'TransferWizard',
]
describe('组件 scoped 无裸 hex 颜色', () => {
  it.each(COMPONENTS)('%s.vue scoped 内不含 #hex', (name) => {
    const src = readFileSync(resolve(__dirname, `../components/${name}.vue`), 'utf8')
    const scoped = src.split('<style').slice(1).join('<style')
    expect(scoped.length).toBeGreaterThan(0)
    const hex = scoped.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []
    expect(hex).toEqual([])
  })
})

describe('组件 scoped 无裸 px 字号', () => {
  it.each(COMPONENTS)('%s.vue scoped 内 font-size 一律走 var(--fs-*)', (name) => {
    const src = readFileSync(resolve(__dirname, `../components/${name}.vue`), 'utf8')
    const scoped = src.split('<style').slice(1).join('<style')
    expect(scoped.length).toBeGreaterThan(0)
    const rawPx = scoped.match(/font-size:\s*\d+px/g) ?? []
    expect(rawPx).toEqual([])
  })
})
