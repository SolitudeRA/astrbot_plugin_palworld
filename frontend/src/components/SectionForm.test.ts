import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SectionForm from './SectionForm.vue'
import { OBJECT_SECTIONS } from '../lib/schema'

const features = OBJECT_SECTIONS.find((s) => s.key === 'features')!

describe('SectionForm', () => {
  it('渲染节标题与全部字段', () => {
    const w = mount(SectionForm, { props: { section: features, modelValue: { report: true, events: true, guilds_bases: false } } })
    expect(w.text()).toContain('功能开关')
    for (const f of features.fields) expect(w.text()).toContain(f.label)
  })
  it('改一个字段 emit 合并后的整节值', async () => {
    const w = mount(SectionForm, { props: { section: features, modelValue: { report: true, events: true, guilds_bases: false } } })
    await w.findAll('[role="switch"]')[2].trigger('click') // guilds_bases
    const emitted = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(emitted).toMatchObject({ report: true, events: true, guilds_bases: true })
  })
})
