import { describe, it, expect } from 'vitest'
import { bootMessage } from './boot'
import { BridgeMissing } from './errors'

describe('bootMessage', () => {
  it('bridge 缺失 → 提示需要插件页环境', () => {
    expect(bootMessage(new BridgeMissing())).toContain('AstrBot ≥ v4.24.1')
  })
  it('其他错误 → 通用刷新提示（不泄露原文）', () => {
    expect(bootMessage(new Error('secret internal detail'))).toBe('初始化失败，请刷新')
  })
})
