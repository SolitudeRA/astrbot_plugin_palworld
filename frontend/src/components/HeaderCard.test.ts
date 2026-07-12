import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HeaderCard from './HeaderCard.vue'

const row = () => ({ __row_id: 'hdr-0', name: 'X-Api-Key', value: '', value_set: true,
  value_env: '', servers: '' })

describe('HeaderCard', () => {
  it('value 不预填明文，占位显示已设置', () => {
    const w = mount(HeaderCard, { props: { modelValue: row() } })
    const pw = w.get('input[type="password"]')
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('即便上游传入非空 secret 也绝不回显（安全红线：非受控输入）', () => {
    const w = mount(HeaderCard, { props: { modelValue: { ...row(), value: 'secret' } } })
    const pw = w.get('input[type="password"]')
    expect((pw.element as HTMLInputElement).value).toBe('')
  })
  it('删除按钮 emit delete', async () => {
    const w = mount(HeaderCard, { props: { modelValue: row() } })
    await w.get('button.pw-danger').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('改名字 emit 合并后的行', async () => {
    const w = mount(HeaderCard, { props: { modelValue: row() } })
    await w.get('input[type="text"]').setValue('X-Renamed')
    const emitted = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(emitted.name).toBe('X-Renamed')
    expect(emitted.__row_id).toBe('hdr-0') // __row_id 保留
  })
})
