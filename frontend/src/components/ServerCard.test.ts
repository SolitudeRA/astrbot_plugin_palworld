import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ServerCard from './ServerCard.vue'

const row = () => ({ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
  password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' })
const mountCard = (mv: Record<string, unknown>) => mount(ServerCard, { props: { modelValue: mv, indexLabel: '源 01' } })

describe('ServerCard', () => {
  it('查看态：password_set=true 显「已设置」，有修改/移除按钮', () => {
    const w = mountCard(row())
    expect(w.text()).toContain('已设置')
    expect(w.get('button.edit')).toBeTruthy()
    expect(w.get('button.del')).toBeTruthy()
    expect(w.find('input.pw-secret').exists()).toBe(false) // 查看态不渲染 secret 输入
  })
  it('查看态：password_set=false 不显密码行', () => {
    const w = mountCard({ ...row(), password_set: false })
    expect(w.text()).not.toContain('密码')
  })
  it('进编辑态：secret 用 text+text-security、不预填、占位显示已设置', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    const pw = w.get('input.pw-secret')
    expect(pw.attributes('type')).toBe('text') // 非 password：否则受限 iframe 里 Ctrl+V 无反应
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('即便上游传入非空 secret 也绝不回显（进编辑态后仍空）', async () => {
    const w = mountCard({ ...row(), password: 'p@ss' })
    await w.get('button.edit').trigger('click')
    expect((w.get('input.pw-secret').element as HTMLInputElement).value).toBe('')
  })
  it('移除按钮 emit delete', async () => {
    const w = mountCard(row())
    await w.get('button.del').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('编辑态改名后「完成」：emit 合并行(__row_id 保留)，只暂存不落库', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    await w.findAll('input.pw-input[type="text"]')[0].setValue('beta') // name = 第一个文本输入
    await w.get('button.save-card').trigger('click')
    const merged = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(merged.name).toBe('beta')
    expect(merged.__row_id).toBe('srv-0')
    expect(w.emitted('save')).toBeFalsy() // 统一由底部「保存设置」落库
  })
  it('新增行(无 __row_id) 初始即编辑态', () => {
    const w = mountCard({ __row_id: '', name: '', enabled: true, base_url: '', username: '', password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' })
    expect(w.find('button.save-card').exists()).toBe(true)
  })
})
