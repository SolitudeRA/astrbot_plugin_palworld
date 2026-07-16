import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const css = readFileSync(resolve(__dirname, 'tokens.css'), 'utf8')

describe('tokens.css 定义了完整 scale', () => {
  const required = [
    '--fs-display:24px', '--fs-title:21px', '--fs-heading:17px',
    '--fs-body:15px', '--fs-sm:14px', '--fs-caption:13px',
    '--space-1:4px', '--space-4:16px', '--space-10:40px',
    '--r-sm:6px', '--r-lg:12px',
    '--shadow-md:', '--shadow-lg:', '--z-modal:50', '--motion-base:180ms',
    '--on-warn:', '--scrim:', '--mono:',
  ]
  it.each(required)('含 %s', (tok) => {
    expect(css.replace(/\s/g, '')).toContain(tok.replace(/\s/g, ''))
  })
  it('body 使用 --fs-body 而非硬编码 14px', () => {
    expect(/body\s*\{[^}]*font-size:\s*var\(--fs-body\)/.test(css)).toBe(true)
  })
})
