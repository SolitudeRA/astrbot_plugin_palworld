import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ServerCard from './ServerCard.vue'

const row = () => ({ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
  password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' })

describe('ServerCard', () => {
  it('secret 用 text+text-security 遮罩（绕受限 iframe 的 password 粘贴门控）、不预填、占位显示已设置', () => {
    const w = mount(ServerCard, { props: { modelValue: row() } })
    const pw = w.get('input.pw-secret')
    expect(pw.attributes('type')).toBe('text') // 非 password：否则受限 iframe 里 Chrome/Edge Ctrl+V 无反应
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('即便上游传入非空 secret 也绝不回显（安全红线：非受控输入）', () => {
    const w = mount(ServerCard, { props: { modelValue: { ...row(), password: 'p@ss' } } })
    const pw = w.get('input.pw-secret')
    expect((pw.element as HTMLInputElement).value).toBe('')
  })
  it('删除按钮 emit delete', async () => {
    const w = mount(ServerCard, { props: { modelValue: row() } })
    await w.get('button.pw-danger').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('改名字 emit 合并后的行', async () => {
    const w = mount(ServerCard, { props: { modelValue: row() } })
    await w.get('input[type="text"]').setValue('beta')
    const emitted = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(emitted.name).toBe('beta')
    expect(emitted.__row_id).toBe('srv-0') // __row_id 保留
  })
})
