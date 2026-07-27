// 前端三语 i18n 地基：reactive locale + 三词典 + fallback + {var} 插值。
// 模块顶层绝不调 guessLocale()——locale 恒以 'zh-CN' 起步（jsdom 默认 navigator.language
// = 'en-US'，若顶层猜会让所有按中文断言的组件测试集体转红）。仅 main.ts 挂载前 setLocale(guessLocale())。
import { ref } from 'vue'
import zhCN from './locales/zh-CN'
import ja from './locales/ja'
import en from './locales/en'

export type Locale = 'zh-CN' | 'ja' | 'en'
const SUPPORTED: readonly Locale[] = ['zh-CN', 'ja', 'en']
const DICTS: Record<Locale, Record<string, string>> = { 'zh-CN': zhCN, ja, en }

export const locale = ref<Locale>('zh-CN') // 模块顶层不猜；默认 zh-CN

export function guessLocale(): Locale {
  const l = (typeof navigator !== 'undefined' && navigator.language) || ''
  if (l.startsWith('ja')) return 'ja'
  if (l.startsWith('en')) return 'en'
  return 'zh-CN'
}

export function setLocale(l: unknown): void {
  // no-op 语义：undefined/null/空串/非 SUPPORTED → 保持当前 locale 不变（不抛、不回落）
  if (typeof l === 'string' && (SUPPORTED as readonly string[]).includes(l)) locale.value = l as Locale
}

export function t(key: string, vars?: Record<string, string | number>): string {
  const s = DICTS[locale.value][key] ?? DICTS['zh-CN'][key] ?? key // fallback 链，永不抛
  if (!vars) return s
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) // 缺参留原样
}
