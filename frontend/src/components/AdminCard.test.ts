import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import AdminCard from './AdminCard.vue'

describe('AdminCard', () => {
  it('查看态显示 id，点修改进编辑态', async () => {
    const w = mount(AdminCard, { props: { modelValue: { __row_id: 'adm-0', id: 'aiocqhttp:1', note: '群主' }, indexLabel: '席 01' } })
    expect(w.text()).toContain('aiocqhttp:1')
    await w.get('[data-act="edit"]').trigger('click')
    expect(w.find('input').exists()).toBe(true)
  })

  it('编辑 id/note 后完成 emit update:model-value 含新值，__row_id 保留', async () => {
    const w = mount(AdminCard, { props: { modelValue: { __row_id: 'adm-0', id: 'aiocqhttp:1', note: '群主' }, indexLabel: '席 01' } })
    await w.get('[data-act="edit"]').trigger('click')
    const inputs = w.findAll('input')
    await inputs[0].setValue('aiocqhttp:9')
    await inputs[1].setValue('管理')
    await w.get('[data-act="save"]').trigger('click')
    const merged = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(merged.id).toBe('aiocqhttp:9')
    expect(merged.note).toBe('管理')
    expect(merged.__row_id).toBe('adm-0')
    expect(w.emitted('save')).toBeFalsy() // 统一由底部「保存设置」落库
  })

  it('新行取消 emit delete', async () => {
    const w = mount(AdminCard, { props: { modelValue: { __row_id: '', id: '', note: '' }, indexLabel: '席 01' } })
    // 新行初始即编辑态；取消
    await w.get('[data-act="cancel"]').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
})
