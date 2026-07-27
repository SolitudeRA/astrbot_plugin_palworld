import { describe, it, expect, beforeEach, vi } from 'vitest'
import { locale, setLocale, guessLocale, t } from './i18n'
import zhCN from './locales/zh-CN'
import ja from './locales/ja'
import en from './locales/en'

beforeEach(() => setLocale('zh-CN'))

describe('i18n 键集/占位符奇偶校验', () => {
  it('三词典键集严格相等', () => {
    const kz = Object.keys(zhCN).sort(),
      kj = Object.keys(ja).sort(),
      ke = Object.keys(en).sort()
    expect(kj).toEqual(kz)
    expect(ke).toEqual(kz)
  })
  it('每键占位符集三语相等', () => {
    const ph = (s: string) => (s.match(/\{(\w+)\}/g) ?? []).sort()
    for (const k of Object.keys(zhCN))
      for (const d of [ja, en]) expect(ph(d[k] ?? '')).toEqual(ph(zhCN[k]))
  })
})

describe('t() 契约', () => {
  it('缺键回退键名、永不抛', () => {
    expect(t('__missing__')).toBe('__missing__')
  })

  it('目标语缺键回退 zh 基线', () => {
    // zh 基线有键、ja 词典无此键：切到 ja 后仍应取到 zh 值（证明 fallback 链）
    zhCN['__fallback__'] = '中文基线'
    try {
      setLocale('ja')
      expect(t('__fallback__')).toBe('中文基线')
    } finally {
      delete zhCN['__fallback__']
    }
  })

  it('{var} 插值；缺参留原样', () => {
    // 运行时注入含占位的临时键，验证替换逻辑：{n} 被替、缺参的 {x} 留原样
    zhCN['__test_interp__'] = '有 {n} 个 {x}'
    try {
      expect(t('__test_interp__', { n: 3 })).toBe('有 3 个 {x}')
    } finally {
      delete zhCN['__test_interp__']
    }
  })
})

describe('setLocale no-op 语义', () => {
  it('undefined/null/空串/非法值保持当前 locale', () => {
    setLocale('ja')
    setLocale(undefined)
    expect(locale.value).toBe('ja')
    setLocale(null)
    expect(locale.value).toBe('ja')
    setLocale('')
    expect(locale.value).toBe('ja')
    setLocale('xx')
    expect(locale.value).toBe('ja')
    setLocale('zh-CN')
    expect(locale.value).toBe('zh-CN')
  })
})

describe('guessLocale', () => {
  it('按 navigator.language 前缀猜，否则 zh-CN', () => {
    try {
      vi.stubGlobal('navigator', { language: 'ja-JP' })
      expect(guessLocale()).toBe('ja')
      vi.stubGlobal('navigator', { language: 'en-US' })
      expect(guessLocale()).toBe('en')
      vi.stubGlobal('navigator', { language: 'fr-FR' })
      expect(guessLocale()).toBe('zh-CN')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
