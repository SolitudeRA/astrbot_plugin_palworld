import type { Locale } from '../lib/i18n'

export const DEFAULT_CAPTURE_OPTIONS = {
  scenario: 'multi',
  locale: 'zh-CN' as Locale,
  theme: 'dark' as const,
  nowMs: 1785196800000,
  seed: 20260728,
}

export type DocsCaptureOptions =
  | { active: false }
  | ({ active: true } & typeof DEFAULT_CAPTURE_OPTIONS)

const CAPTURE_SCENARIOS = new Set(['multi', 'first'])
const CAPTURE_LOCALES = new Set<Locale>(['zh-CN', 'ja', 'en'])

function finiteInteger(raw: string | null): number | null {
  if (raw == null || raw.trim() === '') return null
  const value = Number(raw)
  return Number.isSafeInteger(value) ? value : null
}

export function parseCaptureOptions(search: string): DocsCaptureOptions {
  const params = new URLSearchParams(search)
  if (params.get('capture') !== 'docs') return { active: false }

  const scenario = params.get('scenario')
  const locale = params.get('locale')
  const nowMs = finiteInteger(params.get('now'))
  const seed = finiteInteger(params.get('seed'))
  const valid = scenario !== null
    && CAPTURE_SCENARIOS.has(scenario)
    && locale !== null
    && CAPTURE_LOCALES.has(locale as Locale)
    && params.get('theme') === 'dark'
    && nowMs !== null
    && nowMs > 0
    && seed !== null
    && seed >= 0

  if (!valid) return { active: true, ...DEFAULT_CAPTURE_OPTIONS }
  return {
    active: true,
    scenario: scenario as 'multi' | 'first',
    locale: locale as Locale,
    theme: 'dark',
    nowMs,
    seed,
  }
}
