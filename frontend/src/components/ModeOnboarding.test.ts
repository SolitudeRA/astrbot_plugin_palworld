import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ModeOnboarding from './ModeOnboarding.vue'
import { locale, setLocale } from '../lib/i18n'

const toModeStep = async (w: ReturnType<typeof mount>) => {
  await w.get('[data-act="next"]').trigger('click')
}

describe('ModeOnboarding', () => {
  it('第一步选择语言，默认当前 locale，母语名恒定显示', () => {
    setLocale('zh-CN')
    const w = mount(ModeOnboarding)
    expect(w.text()).toContain('选择语言')
    expect(w.text()).toContain('简体中文')
    expect(w.text()).toContain('日本語')
    expect(w.text()).toContain('English')
    expect(w.get('[data-locale="zh-CN"]').attributes('aria-checked')).toBe('true')
  })

  it('第一步点选语言立即切 UI locale，但不 emit confirm', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-locale="ja"]').trigger('click')
    expect(locale.value).toBe('ja')
    expect(w.emitted('confirm')).toBeFalsy()
  })

  it('下一步进入运行模式，未点选前确认按钮禁用', async () => {
    const w = mount(ModeOnboarding)
    await toModeStep(w)
    expect(w.text()).toContain('选择运行模式')
    expect((w.get('button.confirm').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('点选单服务器后 emit {locale,mode}', async () => {
    setLocale('ja')
    const w = mount(ModeOnboarding)
    await toModeStep(w)
    await w.get('[data-mode="single"]').trigger('click')
    await w.get('button.confirm').trigger('click')
    expect(w.emitted('confirm')?.[0]).toEqual([{ locale: 'ja', mode: 'single' }])
  })

  it('点选多服务器 emit {locale,mode}', async () => {
    setLocale('en')
    const w = mount(ModeOnboarding)
    await toModeStep(w)
    await w.get('[data-mode="multi"]').trigger('click')
    await w.get('button.confirm').trigger('click')
    expect(w.emitted('confirm')?.[0]).toEqual([{ locale: 'en', mode: 'multi' }])
  })

  it('语言与模式各自组成 radiogroup（a11y）', async () => {
    const w = mount(ModeOnboarding)
    expect(w.get('[role="radiogroup"]').attributes('aria-label')).toBe('界面与消息语言')
    expect(w.findAll('[role="radio"]')).toHaveLength(3)
    await toModeStep(w)
    expect(w.get('[role="radiogroup"]').attributes('aria-label')).toBe('运行模式')
    expect(w.findAll('[role="radio"]')).toHaveLength(2)
  })

  it('语言步方向键环绕并即时 setLocale', async () => {
    setLocale('zh-CN')
    const w = mount(ModeOnboarding)
    await w.get('[role="radiogroup"]').trigger('keydown', { key: 'ArrowLeft' })
    expect(w.get('[data-locale="en"]').attributes('aria-checked')).toBe('true')
    expect(locale.value).toBe('en')
  })

  it('模式步方向键在两卡间切换 selected（保留既有 a11y）', async () => {
    const w = mount(ModeOnboarding)
    await toModeStep(w)
    await w.get('[data-mode="single"]').trigger('click')
    await w.get('[role="radiogroup"]').trigger('keydown', { key: 'ArrowRight' })
    expect(w.get('[data-mode="multi"]').attributes('aria-checked')).toBe('true')
    expect(w.get('[data-mode="single"]').attributes('aria-checked')).toBe('false')
  })

  it('模式步空选态 ArrowRight/ArrowLeft 分别落第一项/最后一项', async () => {
    const w = mount(ModeOnboarding)
    await toModeStep(w)
    await w.get('[role="radiogroup"]').trigger('keydown', { key: 'ArrowRight' })
    expect(w.get('[data-mode="single"]').attributes('aria-checked')).toBe('true')

    const w2 = mount(ModeOnboarding)
    await toModeStep(w2)
    await w2.get('[role="radiogroup"]').trigger('keydown', { key: 'ArrowLeft' })
    expect(w2.get('[data-mode="multi"]').attributes('aria-checked')).toBe('true')
  })

  it('第二步可返回语言步，已选语言保留', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-locale="ja"]').trigger('click')
    await toModeStep(w)
    await w.get('[data-act="back"]').trigger('click')
    expect(w.get('[data-locale="ja"]').attributes('aria-checked')).toBe('true')
  })

  it('已选模式时显示含「连接」页的转换指引', async () => {
    const w = mount(ModeOnboarding)
    await toModeStep(w)
    expect(w.find('.hint').exists()).toBe(false)
    await w.get('[data-mode="single"]').trigger('click')
    expect(w.get('.hint').text()).toContain('连接')
    expect(w.get('.hint').text()).toContain('单服务器')
  })
})
