import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ModeOnboarding from './ModeOnboarding.vue'

describe('ModeOnboarding', () => {
  it('确认按钮在未点选前禁用', () => {
    const w = mount(ModeOnboarding)
    const btn = w.get('button.confirm')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('点选单服务器后启用并 emit confirm=single', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-mode="single"]').trigger('click')
    const btn = w.get('button.confirm')
    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
    await btn.trigger('click')
    expect(w.emitted('confirm')?.[0]).toEqual(['single'])
  })

  it('点选多服务器 emit confirm=multi', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-mode="multi"]').trigger('click')
    await w.get('button.confirm').trigger('click')
    expect(w.emitted('confirm')?.[0]).toEqual(['multi'])
  })

  it('两卡组成 radiogroup（a11y）', () => {
    const w = mount(ModeOnboarding)
    const group = w.get('[role="radiogroup"]')
    expect(group.attributes('aria-label')).toBe('运行模式')
    expect(w.findAll('[role="radio"]')).toHaveLength(2)
  })

  it('方向键在两卡间切换 selected（aria-checked 翻转）', async () => {
    const w = mount(ModeOnboarding)
    await w.get('[data-mode="single"]').trigger('click')
    expect(w.get('[data-mode="single"]').attributes('aria-checked')).toBe('true')
    await w.get('[role="radiogroup"]').trigger('keydown', { key: 'ArrowRight' })
    expect(w.get('[data-mode="multi"]').attributes('aria-checked')).toBe('true')
    expect(w.get('[data-mode="single"]').attributes('aria-checked')).toBe('false')
  })

  it('已选时显示 hint（含「连接」页转换指引）', async () => {
    const w = mount(ModeOnboarding)
    expect(w.find('.hint').exists()).toBe(false)
    await w.get('[data-mode="single"]').trigger('click')
    expect(w.get('.hint').text()).toContain('连接')
    expect(w.get('.hint').text()).toContain('单服务器')
  })
})
