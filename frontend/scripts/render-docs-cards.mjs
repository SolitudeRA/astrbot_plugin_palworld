import { mkdir, readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const require = createRequire(import.meta.url)
const playwrightPackage = require('playwright/package.json')

export const PLAYWRIGHT_VERSION = playwrightPackage.version
export const CARD_VIEWPORT = { width: 600, height: 400 }
export const CARD_DPR = 1
export const CARD_RENDERER_SCALE = 2
export const EXPECTED_CARD_WIDTH = 1008
export const EXPECTED_LOGICAL_WIDTH = EXPECTED_CARD_WIDTH / CARD_RENDERER_SCALE

const BROWSER_LOCALES = { 'zh-CN': 'zh-CN', ja: 'ja-JP', en: 'en-US' }

export function parseArgs(argv) {
  if (argv.length !== 2 || argv[0] !== '--jobs-file' || !argv[1]) {
    throw new Error('usage: node render-docs-cards.mjs --jobs-file <path>')
  }
  return { jobsFile: path.resolve(argv[1]) }
}

async function assertCardState(page, job) {
  return page.evaluate(({ expectedTheme, expectedWidth }) => {
    const card = document.querySelector('[data-theme]')
    return {
      theme: card?.getAttribute('data-theme'),
      devicePixelRatio: window.devicePixelRatio,
      viewportScale: window.visualViewport?.scale ?? 1,
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
      expectedTheme,
      expectedWidth,
    }
  }, { expectedTheme: job.theme, expectedWidth: EXPECTED_LOGICAL_WIDTH })
}

export async function renderCards(jobs) {
  if (!Array.isArray(jobs) || jobs.length !== 6) {
    throw new Error(`expected exactly 6 card jobs, got ${Array.isArray(jobs) ? jobs.length : 'non-array'}`)
  }

  let browser
  try {
    browser = await chromium.launch({ headless: true })
    const captures = []
    for (const job of jobs) {
      if (!(job.locale in BROWSER_LOCALES)) throw new Error(`unsupported locale: ${job.locale}`)
      if (!['light', 'dark'].includes(job.theme)) throw new Error(`unsupported theme: ${job.theme}`)

      const context = await browser.newContext({
        viewport: CARD_VIEWPORT,
        deviceScaleFactor: CARD_DPR,
        colorScheme: job.theme,
        locale: BROWSER_LOCALES[job.locale],
        reducedMotion: 'reduce',
      })
      try {
        const page = await context.newPage()
        await page.setContent(await readFile(job.htmlPath, 'utf8'), { waitUntil: 'load' })
        await page.evaluate(() => document.fonts.ready)
        const state = await assertCardState(page, job)
        if (state.theme !== job.theme) throw new Error(`${job.output}: unexpected theme ${state.theme}`)
        if (state.devicePixelRatio !== CARD_DPR) {
          throw new Error(`${job.output}: unexpected DPR ${state.devicePixelRatio}`)
        }
        if (state.viewportScale !== 1) {
          throw new Error(`${job.output}: unexpected visual viewport scale ${state.viewportScale}`)
        }
        if (state.width !== EXPECTED_LOGICAL_WIDTH) {
          throw new Error(`${job.output}: expected logical width ${EXPECTED_LOGICAL_WIDTH}, got ${state.width}`)
        }

        await mkdir(path.dirname(job.outputPath), { recursive: true })
        await page.screenshot({ path: job.outputPath, type: 'png', fullPage: true, scale: 'device' })
        const png = await readFile(job.outputPath)
        if (png.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') {
          throw new Error(`${job.output}: renderer did not produce a PNG`)
        }
        const width = png.readUInt32BE(16)
        const height = png.readUInt32BE(20)
        const expectedHeight = state.height * CARD_RENDERER_SCALE
        if (width !== EXPECTED_CARD_WIDTH || Math.abs(height - expectedHeight) > 1) {
          throw new Error(`${job.output}: expected ${EXPECTED_CARD_WIDTH}x~${expectedHeight}, got ${width}x${height}`)
        }
        captures.push({
          output: job.output,
          locale: job.locale,
          theme: job.theme,
          viewport: CARD_VIEWPORT,
          deviceScaleFactor: CARD_DPR,
          rendererScale: CARD_RENDERER_SCALE,
          expectedPixels: { width, height },
        })
      } finally {
        await context.close()
      }
    }
    const chromiumVersion = browser.version()
    await browser.close()
    browser = undefined
    return {
      playwrightVersion: PLAYWRIGHT_VERSION,
      chromiumVersion,
      captures,
    }
  } finally {
    if (browser) await browser.close().catch(() => {})
  }
}

async function main() {
  const { jobsFile } = parseArgs(process.argv.slice(2))
  const payload = JSON.parse(await readFile(jobsFile, 'utf8'))
  const result = await renderCards(payload.jobs)
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
