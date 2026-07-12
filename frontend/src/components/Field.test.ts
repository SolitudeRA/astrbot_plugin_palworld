import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Field from './Field.vue'
import type { FieldSpec } from '../lib/schema'

const mountField = (spec: FieldSpec, modelValue: unknown) =>
  mount(Field, { props: { spec, modelValue } })

describe('Field', () => {
  it('string：输入 emit 字符串', async () => {
    const w = mountField({ key: 'name', type: 'string', label: '名称', default: '' }, '')
    await w.get('input[type="text"]').setValue('alpha')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['alpha'])
  })
  it('bool：切换 emit boolean', async () => {
    const w = mountField({ key: 'enabled', type: 'bool', label: '启用', default: true }, false)
    await w.get('[role="switch"]').trigger('click')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([true])
  })
  it('int：输入 emit number', async () => {
    const w = mountField({ key: 'timeout', type: 'int', label: '超时', default: 10 }, 10)
    // reka-ui 2.10.1 NumberFieldInput 在 blur/Enter 提交解析后的数值（非每次 input），
    // 故 setValue 后补一次 blur 以触达真实提交路径；断言语义（emit 的是 number）不变。
    const input = w.get('input')
    await input.setValue('25')
    await input.trigger('blur')
    const last = w.emitted('update:modelValue')?.at(-1)?.[0]
    expect(typeof last).toBe('number')
    expect(last).toBe(25)
  })
  it('enum：渲染全部 options', () => {
    const w = mountField({ key: 'mode', type: 'enum', label: '模式', default: 'a', options: ['a', 'b', 'c'] }, 'a')
    expect(w.text()).toContain('模式')
    // 渲染断言：三个 option 值出现在 DOM（不测下拉打开交互）
    for (const opt of ['a', 'b', 'c']) expect(w.html()).toContain(opt)
  })
})
