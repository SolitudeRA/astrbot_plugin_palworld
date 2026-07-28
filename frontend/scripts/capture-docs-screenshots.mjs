import { randomUUID } from 'node:crypto'
import { access, mkdir, readFile, rename, rm } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const require = createRequire(import.meta.url)
const playwrightPackage = require('playwright/package.json')
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_DIR = path.resolve(SCRIPT_DIR, '..')

export const CAPTURE_NOW_MS = 1785196800000
export const CAPTURE_SEED = 20260728
export const PLAYWRIGHT_VERSION = playwrightPackage.version

const LOCALES = ['zh-CN', 'ja', 'en']
const BROWSER_LOCALES = { 'zh-CN': 'zh-CN', ja: 'ja-JP', en: 'en-US' }
const SCREENSHOTS = [
  { id: 'settings-servers', scenario: 'multi', chapter: 'access', height: 960 },
  { id: 'settings-features', scenario: 'multi', chapter: 'features', height: 960 },
  { id: 'settings-permissions', scenario: 'multi', chapter: 'permissions', height: 960 },
  { id: 'settings-onboarding', scenario: 'first', chapter: null, height: 600 },
]

export const CAPTURE_CASES = LOCALES.flatMap((locale) => SCREENSHOTS.map((shot) => {
  const prefix = locale === 'zh-CN' ? '' : `${locale}/`
  return {
    ...shot,
    locale,
    theme: 'dark',
    viewport: { width: 1100, height: shot.height },
    deviceScaleFactor: 2,
    expectedPixels: { width: 2200, height: shot.height * 2 },
    output: `${prefix}${shot.id}.png`,
  }
}))

export function captureUrl(baseUrl, item) {
  const url = new URL('/dev.html', `${baseUrl.replace(/\/+$/, '')}/`)
  url.search = new URLSearchParams({
    capture: 'docs',
    scenario: item.scenario,
    locale: item.locale,
    theme: item.theme,
    now: String(CAPTURE_NOW_MS),
    seed: String(CAPTURE_SEED),
  }).toString()
  return url.toString()
}

export function parseArgs(argv) {
  let outputDir = null
  let baseUrl = 'http://127.0.0.1:4173'
  let dryRunManifest = false
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--output-dir') {
      outputDir = argv[++index]
      if (!outputDir) throw new Error('--output-dir requires a value')
    } else if (arg === '--base-url') {
      baseUrl = argv[++index]
      if (!baseUrl) throw new Error('--base-url requires a value')
      baseUrl = baseUrl.replace(/\/+$/, '')
    } else if (arg === '--dry-run-manifest') {
      dryRunManifest = true
    } else {
      throw new Error(`unknown argument: ${arg}`)
    }
  }
  if (!dryRunManifest && !outputDir) throw new Error('--output-dir is required')
  return { outputDir, baseUrl, dryRunManifest }
}

function pngDimensions(buffer) {
  const signature = buffer.subarray(0, 8).toString('hex')
  if (signature !== '89504e470d0a1a0a') throw new Error('screenshot is not a PNG')
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) }
}

async function assertOutputAbsent(outputDir) {
  try {
    await access(outputDir)
  } catch {
    return
  }
  throw new Error(`output directory already exists: ${outputDir}`)
}

async function assertCaptureState(page, item) {
  const state = await page.evaluate(() => {
    const root = document.documentElement
    const toolbar = document.getElementById('dev-scenario')
    return {
      devicePixelRatio: window.devicePixelRatio,
      viewportScale: window.visualViewport?.scale ?? 1,
      locale: root.dataset.docsCaptureLocale,
      scenario: root.dataset.docsCaptureScenario,
      theme: root.getAttribute('data-theme'),
      ready: root.dataset.docsCaptureReady,
      toolbarHidden: toolbar?.hidden === true || (toolbar ? getComputedStyle(toolbar).display === 'none' : true),
    }
  })
  if (state.devicePixelRatio !== 2) throw new Error(`unexpected DPR: ${state.devicePixelRatio}`)
  if (state.viewportScale !== 1) throw new Error(`unexpected visual viewport scale: ${state.viewportScale}`)
  if (state.locale !== item.locale) throw new Error(`unexpected locale: ${state.locale}`)
  if (state.scenario !== item.scenario) throw new Error(`unexpected scenario: ${state.scenario}`)
  if (state.theme !== 'dark') throw new Error(`unexpected theme: ${state.theme}`)
  if (state.ready !== 'true') throw new Error('capture ready marker is missing')
  if (!state.toolbarHidden) throw new Error('dev scenario toolbar is visible')
}

export async function captureSettings({ outputDir, baseUrl }) {
  const finalOutput = path.resolve(outputDir)
  await assertOutputAbsent(finalOutput)
  const parent = path.dirname(finalOutput)
  const staging = path.join(parent, `.${path.basename(finalOutput)}.tmp-${randomUUID()}`)
  await mkdir(staging, { recursive: false })

  let browser
  try {
    browser = await chromium.launch({ headless: true })
    for (const item of CAPTURE_CASES) {
      const context = await browser.newContext({
        viewport: item.viewport,
        deviceScaleFactor: item.deviceScaleFactor,
        colorScheme: 'dark',
        locale: BROWSER_LOCALES[item.locale],
      })
      try {
        const page = await context.newPage()
        await page.goto(captureUrl(baseUrl, item), { waitUntil: 'domcontentloaded' })
        await page.waitForFunction(() => document.documentElement.dataset.docsCaptureReady === 'true')
        if (item.chapter) {
          const chapter = page.locator(`[data-chapter="${item.chapter}"]`)
          await chapter.click()
          await chapter.waitFor({ state: 'visible' })
          await page.waitForFunction(
            (id) => document.querySelector(`[data-chapter="${id}"]`)?.getAttribute('aria-current') === 'true',
            item.chapter,
          )
        }
        await page.evaluate(() => document.fonts.ready)
        await assertCaptureState(page, item)

        const destination = path.join(staging, ...item.output.split('/'))
        await mkdir(path.dirname(destination), { recursive: true })
        await page.screenshot({ path: destination, type: 'png', fullPage: false, scale: 'device' })
        const actual = pngDimensions(await readFile(destination))
        if (actual.width !== item.expectedPixels.width || actual.height !== item.expectedPixels.height) {
          throw new Error(`${item.output}: expected ${item.expectedPixels.width}x${item.expectedPixels.height}, `
            + `got ${actual.width}x${actual.height}`)
        }
      } finally {
        await context.close()
      }
    }
    const chromiumVersion = browser.version()
    await browser.close()
    browser = undefined
    await rename(staging, finalOutput)
    return {
      playwrightVersion: PLAYWRIGHT_VERSION,
      chromiumVersion,
      outputDir: finalOutput,
      captures: CAPTURE_CASES,
    }
  } catch (error) {
    if (browser) await browser.close().catch(() => {})
    await rm(staging, { recursive: true, force: true })
    throw error
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.dryRunManifest) {
    process.stdout.write(`${JSON.stringify({
      playwrightVersion: PLAYWRIGHT_VERSION,
      frontendDir: FRONTEND_DIR,
      captures: CAPTURE_CASES,
    }, null, 2)}\n`)
    return
  }
  const result = await captureSettings(args)
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
