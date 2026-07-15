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
})
