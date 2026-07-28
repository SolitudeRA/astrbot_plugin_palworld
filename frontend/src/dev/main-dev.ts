// Dev-only 入口：先装内存假 bridge，再动态 import 真实 main.ts。
// 动态 import 保证求值顺序——main.ts 顶层立即 boot() 并读 window.AstrBotPluginPage，
// 故必须在 import 之前把 bridge 挂上，boot guard 才能看到它。
// 本文件不进 vite build 产物（build input 是 index.html，仅 dev.html 引用此文件）。
import { createMockBridge, DEFAULT_SCENARIO, SCENARIO_KEY } from './mockBridge'
import { parseCaptureOptions } from './capture'

const capture = parseCaptureOptions(location.search)
let scenario: string
if (capture.active) {
  scenario = capture.scenario
  try {
    localStorage.removeItem('palworld-terminal-theme')
    localStorage.removeItem('palchronicle-theme')
  } catch { /* capture context 禁用 storage 时仍以根节点属性固定主题 */ }
  document.documentElement.setAttribute('data-theme', capture.theme)
  document.documentElement.dataset.docsCapture = 'true'
  document.documentElement.dataset.docsCaptureScenario = capture.scenario
  document.documentElement.dataset.docsCaptureLocale = capture.locale
  document.documentElement.dataset.docsCaptureTheme = capture.theme
  document.getElementById('dev-scenario')?.setAttribute('hidden', '')
} else {
  scenario = DEFAULT_SCENARIO
  try {
    scenario = sessionStorage.getItem(SCENARIO_KEY) || DEFAULT_SCENARIO
  } catch { /* 隐私模式等禁用 storage：回退默认场景 */ }
}

window.AstrBotPluginPage = createMockBridge(
  scenario,
  capture.active
    ? {
        nowMs: capture.nowMs,
        seed: capture.seed,
        locale: capture.locale,
        neutralFixtures: true,
        latencyMs: 0,
      }
    : {},
)

await import('../main')

async function waitForCaptureReady(): Promise<void> {
  if (!capture.active) return
  for (let attempt = 0; attempt < 200; attempt += 1) {
    const localeReady = capture.scenario === 'first'
      ? document.querySelector(`[data-locale="${capture.locale}"][aria-checked="true"]`) !== null
      : (document.querySelector<HTMLSelectElement>('select.locale-switch')?.value === capture.locale)
    const scenarioReady = capture.scenario === 'first'
      ? document.querySelector('nav.rail') === null && document.querySelector('[data-locale]') !== null
      : document.querySelector('[data-chapter="access"]') !== null
    if (localeReady && scenarioReady && document.documentElement.getAttribute('data-theme') === capture.theme) {
      if (document.fonts?.ready) await document.fonts.ready
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
      document.documentElement.dataset.docsCaptureReady = 'true'
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  throw new Error('docs capture UI did not become ready')
}

await waitForCaptureReady()

// 「切换 helper」预览场景：挂载完成后自动点击危险区的切换按钮，直达 helper 设计页。
// 纯 dev 侧 DOM 驱动，零生产代码耦合。
if (scenario === 'transferHelper') {
  const tryOpen = (attempt = 0) => {
    const btn = document.querySelector<HTMLButtonElement>('[data-act="switch"]')
    if (btn) { btn.click(); return }
    if (attempt < 50) setTimeout(() => tryOpen(attempt + 1), 100)
  }
  tryOpen()
}
