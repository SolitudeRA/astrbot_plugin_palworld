import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HeaderCard from './HeaderCard.vue'

const row = () => ({ __row_id: 'hdr-0', name: 'X-Api-Key', value: '', value_set: true, value_env: '', servers: '' })
const mountCard = (mv: Record<string, unknown>) => mount(HeaderCard, { props: { modelValue: mv, indexLabel: '头 01' } })

describe('HeaderCard', () => {
  it('查看态：value_set=true 显「已设置」，有修改/移除', () => {
    const w = mountCard(row())
    expect(w.text()).toContain('已设置')
    expect(w.get('button.edit')).toBeTruthy()
    expect(w.get('button.del')).toBeTruthy()
    expect(w.find('input.pw-secret').exists()).toBe(false)
  })
  it('查看态：value_set=false 且无 value_env 显「未设置」', () => {
    const w = mountCard({ ...row(), value_set: false })
    expect(w.text()).toContain('未设置')
  })
  it('进编辑态：secret 用 text+text-security、不预填、占位显示已设置', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    const pw = w.get('input.pw-secret')
    expect(pw.attributes('type')).toBe('text')
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('即便上游传入非空 secret 也绝不回显', async () => {
    const w = mountCard({ ...row(), value: 'secret' })
    await w.get('button.edit').trigger('click')
    expect((w.get('input.pw-secret').element as HTMLInputElement).value).toBe('')
  })
  it('移除按钮 emit delete', async () => {
    const w = mountCard(row())
    await w.get('button.del').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('编辑态改名后保存：emit 合并行(__row_id 保留) + emit save', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    await w.findAll('input.pw-input[type="text"]')[0].setValue('X-Renamed') // name
    await w.get('button.save-card').trigger('click')
    const merged = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(merged.name).toBe('X-Renamed')
    expect(merged.__row_id).toBe('hdr-0')
    expect(w.emitted('save')).toBeTruthy()
  })
})
