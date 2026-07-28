import { describe, expect, it } from 'vitest'
import { DEFAULT_CAPTURE_OPTIONS, parseCaptureOptions } from './capture'

describe('docs capture parameters', () => {
  it('accepts the documented deterministic contract', () => {
    expect(parseCaptureOptions(
      '?capture=docs&scenario=first&locale=ja&theme=dark&now=1785196800000&seed=42',
    )).toEqual({
      active: true,
      scenario: 'first',
      locale: 'ja',
      theme: 'dark',
      nowMs: 1785196800000,
      seed: 42,
    })
  })

  it('falls back to safe deterministic defaults for invalid values', () => {
    expect(parseCaptureOptions(
      '?capture=docs&scenario=unknown&locale=fr&theme=light&now=soon&seed=NaN',
    )).toEqual({ active: true, ...DEFAULT_CAPTURE_OPTIONS })
  })

  it('does not activate for normal dev preview', () => {
    expect(parseCaptureOptions('?scenario=first')).toEqual({ active: false })
  })
})
