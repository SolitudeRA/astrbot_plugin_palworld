import assert from 'node:assert/strict'
import test from 'node:test'
import path from 'node:path'
import {
  CARD_DPR,
  CARD_RENDERER_SCALE,
  CARD_VIEWPORT,
  EXPECTED_CARD_WIDTH,
  EXPECTED_LOGICAL_WIDTH,
  parseArgs,
} from './render-docs-cards.mjs'

test('card renderer locks production-equivalent scale and native width', () => {
  assert.deepEqual(CARD_VIEWPORT, { width: 600, height: 400 })
  assert.equal(CARD_DPR, 1)
  assert.equal(CARD_RENDERER_SCALE, 2)
  assert.equal(EXPECTED_LOGICAL_WIDTH, 504)
  assert.equal(EXPECTED_CARD_WIDTH, 1008)
})

test('card renderer accepts only an explicit jobs file', () => {
  assert.deepEqual(parseArgs(['--jobs-file', 'tmp/jobs.json']), {
    jobsFile: path.resolve('tmp/jobs.json'),
  })
  assert.throws(() => parseArgs([]), /usage:/)
  assert.throws(() => parseArgs(['--jobs-file']), /usage:/)
  assert.throws(() => parseArgs(['--output-dir', 'tmp']), /usage:/)
})
