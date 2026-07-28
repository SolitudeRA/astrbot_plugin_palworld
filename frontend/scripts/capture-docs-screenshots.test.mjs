import assert from 'node:assert/strict'
import test from 'node:test'
import {
  CAPTURE_CASES,
  CAPTURE_NOW_MS,
  CAPTURE_SEED,
  captureUrl,
  parseArgs,
} from './capture-docs-screenshots.mjs'

test('capture manifest has 12 unique locale-scoped outputs', () => {
  assert.equal(CAPTURE_CASES.length, 12)
  assert.equal(new Set(CAPTURE_CASES.map((item) => item.output)).size, 12)
  assert.deepEqual(
    [...new Set(CAPTURE_CASES.map((item) => item.locale))],
    ['zh-CN', 'ja', 'en'],
  )
  for (const locale of ['zh-CN', 'ja', 'en']) {
    const rows = CAPTURE_CASES.filter((item) => item.locale === locale)
    assert.equal(rows.length, 4)
    assert.deepEqual(rows.map((item) => item.id), [
      'settings-servers',
      'settings-features',
      'settings-permissions',
      'settings-onboarding',
    ])
  }
})

test('capture cases pin CSS viewport, DPR, scenario, chapter, clock, and seed', () => {
  for (const item of CAPTURE_CASES) {
    assert.equal(item.deviceScaleFactor, 2)
    assert.equal(item.viewport.width, 1100)
    assert.equal(item.viewport.height, item.id === 'settings-onboarding' ? 600 : 960)
    assert.equal(item.expectedPixels.width, 2200)
    assert.equal(item.expectedPixels.height, item.id === 'settings-onboarding' ? 1200 : 1920)
    assert.equal(item.scenario, item.id === 'settings-onboarding' ? 'first' : 'multi')
    assert.equal(item.chapter, item.id === 'settings-onboarding' ? null : {
      'settings-servers': 'access',
      'settings-features': 'features',
      'settings-permissions': 'permissions',
    }[item.id])

    const url = new URL(captureUrl('http://127.0.0.1:4173', item))
    assert.equal(url.pathname, '/dev.html')
    assert.equal(url.searchParams.get('capture'), 'docs')
    assert.equal(url.searchParams.get('locale'), item.locale)
    assert.equal(url.searchParams.get('theme'), 'dark')
    assert.equal(url.searchParams.get('now'), String(CAPTURE_NOW_MS))
    assert.equal(url.searchParams.get('seed'), String(CAPTURE_SEED))
  }
})

test('CLI parser supports output, base URL, and dry-run manifest', () => {
  assert.deepEqual(parseArgs([
    '--output-dir',
    'tmp/out',
    '--base-url',
    'http://localhost:9000/',
    '--dry-run-manifest',
  ]), {
    outputDir: 'tmp/out',
    baseUrl: 'http://localhost:9000',
    dryRunManifest: true,
  })
  assert.throws(() => parseArgs(['--unknown']), /unknown argument/)
})
