// Dev-only 入口：先装内存假 bridge，再动态 import 真实 main.ts。
// 动态 import 保证求值顺序——main.ts 顶层立即 boot() 并读 window.AstrBotPluginPage，
// 故必须在 import 之前把 bridge 挂上，boot guard 才能看到它。
// 本文件不进 vite build 产物（build input 是 index.html，仅 dev.html 引用此文件）。
import { createMockBridge, DEFAULT_SCENARIO, SCENARIO_KEY } from './mockBridge'

let scenario = DEFAULT_SCENARIO
try {
  scenario = sessionStorage.getItem(SCENARIO_KEY) || DEFAULT_SCENARIO
} catch { /* 隐私模式等禁用 storage：回退默认场景 */ }

window.AstrBotPluginPage = createMockBridge(scenario)

await import('../main')

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
