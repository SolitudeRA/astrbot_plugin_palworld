import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import GroupCard from './GroupCard.vue'

describe('GroupCard', () => {
  it('查看态显示 umo，点修改进编辑态', async () => {
    const w = mount(GroupCard, { props: { modelValue: { __row_id: 'sag-0', umo: 'aiocqhttp:GroupMessage:1', note: '主群' }, indexLabel: '授权群 01' } })
    expect(w.text()).toContain('aiocqhttp:GroupMessage:1')
    await w.get('[data-act="edit"]').trigger('click')
    expect(w.find('input').exists()).toBe(true)
  })

  it('编辑 umo/note 后完成 emit update:model-value 含新值，__row_id 保留', async () => {
    const w = mount(GroupCard, { props: { modelValue: { __row_id: 'sag-0', umo: 'aiocqhttp:GroupMessage:1', note: '主群' }, indexLabel: '授权群 01' } })
    await w.get('[data-act="edit"]').trigger('click')
    const inputs = w.findAll('input')
    await inputs[0].setValue('aiocqhttp:GroupMessage:9')
    await inputs[1].setValue('分群')
    await w.get('[data-act="save"]').trigger('click')
    const merged = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(merged.umo).toBe('aiocqhttp:GroupMessage:9')
    expect(merged.note).toBe('分群')
    expect(merged.__row_id).toBe('sag-0')
    expect(w.emitted('save')).toBeFalsy() // 统一由底部「保存设置」落库
  })

  it('新行取消 emit delete', async () => {
    const w = mount(GroupCard, { props: { modelValue: { __row_id: '', umo: '', note: '' }, indexLabel: '授权群 01' } })
    // 新行初始即编辑态；取消
    await w.get('[data-act="cancel"]').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
})
