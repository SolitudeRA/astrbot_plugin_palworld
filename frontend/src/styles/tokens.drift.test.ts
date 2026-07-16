import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const styles = resolve(__dirname, 'tokens.css')
const css = readFileSync(styles, 'utf8')

describe('tokens.css 无半 px 字号漂移', () => {
  it('不含小数 px 字号', () => {
    // /i 大小写不敏感（Font-Size/PX 亦查）；\d* 前导数字可选，覆盖前导点小数（如 .5px）与常规小数（1.5px）
    const halfPx = css.match(/font-size:\s*\d*\.\d+px/gi) ?? []
    expect(halfPx).toEqual([])
  })
  it('font-size 一律走 var(--fs-*)（除特征常量 line-height:1 外无裸 px 字号）', () => {
    const rawPx = css.match(/font-size:\s*\d+px/gi) ?? []
    expect(rawPx).toEqual([])
  })
})

const COMPONENTS = [
  'CommandTree', 'SettingsPanel', 'ModeConfirmDialog', 'OrphanCleanup', 'TransferWizard',
  'ModeOnboarding', 'ModeTransfer', 'StatusPanel', 'AuditPanel',
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
    // /i 大小写不敏感；\d*\.?\d+ 统一整数/小数/前导点小数（15px、1.5px、.5px 皆命中）
    const rawPx = scoped.match(/font-size:\s*\d*\.?\d+px/gi) ?? []
    expect(rawPx).toEqual([])
  })
})
