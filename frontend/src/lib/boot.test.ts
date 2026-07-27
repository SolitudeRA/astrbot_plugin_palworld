import { describe, it, expect } from 'vitest'
import { bootMessage } from './boot'
import { BridgeMissing } from './errors'
import { setLocale } from './i18n'
import en from './locales/en'

describe('bootMessage', () => {
  it('bridge 缺失 → 提示需要插件页环境', () => {
    expect(bootMessage(new BridgeMissing())).toContain('AstrBot ≥ v4.24.1')
  })
  it('其他错误 → 通用刷新提示（不泄露原文）', () => {
    expect(bootMessage(new Error('secret internal detail'))).toBe('初始化失败，请刷新')
  })

  it('启动错误文案随 locale 响应', () => {
    en['app.boot.failed'] = 'BOOT_FAILED_EN'
    try {
      setLocale('en')
      expect(bootMessage(new Error('secret internal detail'))).toBe('BOOT_FAILED_EN')
    } finally {
      setLocale('zh-CN')
      delete en['app.boot.failed']
    }
  })
})
