import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SectionForm from './SectionForm.vue'
import { OBJECT_SECTIONS } from '../lib/schema'

// features 节已随 Phase 2 移除，改用 privacy 节（含 enum + bool 开关 + 数值）做通用渲染夹具
const privacy = OBJECT_SECTIONS.find((s) => s.key === 'privacy')!

describe('SectionForm', () => {
  it('渲染节标题与全部字段', () => {
    const w = mount(SectionForm, { props: { section: privacy, modelValue: { mode: 'balanced', public_exact_ping: false, public_positions: false } } })
    expect(w.text()).toContain('隐私与脱敏')
    for (const f of privacy.fields) expect(w.text()).toContain(f.label)
  })
  it('改一个字段 emit 合并后的整节值', async () => {
    const w = mount(SectionForm, { props: { section: privacy, modelValue: { mode: 'balanced', public_exact_ping: false, public_positions: false } } })
    await w.findAll('[role="switch"]')[0].trigger('click') // public_exact_ping：首个 bool 开关
    const emitted = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(emitted).toMatchObject({ mode: 'balanced', public_exact_ping: true, public_positions: false })
  })
})
