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
  it('enum：渲染 SelectTrigger 离散节点（而非裸子串）', () => {
    const w = mountField({ key: 'mode', type: 'enum', label: '模式', default: 'a', options: ['a', 'b', 'c'] }, 'a')
    expect(w.text()).toContain('模式')
    // reka-ui 2.10.1 的 Select 在 jsdom 里只渲染 trigger；SelectContent/SelectItem 在
    // 关闭态是 <!--v-if-->，仅在 open 时挂载（且 open 依赖 jsdom 不具备的定位/指针 API）。
    // 原断言 for(opt of 'abc') html().toContain(opt) 是假阳性：a/b/c 作为单字符会命中
    // class/aria-*/标签名，即便零个 option 渲染也照样绿。改为对 SelectTrigger 这个
    // 真实离散节点断言——枚举分支不渲染（走 v-else 文本框 / 换错分支）时会失败。
    const triggers = w.findAll('[role="combobox"]')
    expect(triggers).toHaveLength(1)
    expect(triggers[0].attributes('aria-label')).toBe('mode')
    expect(triggers[0].element.tagName).toBe('BUTTON')
    // 枚举分支不应回退到 string 的纯文本输入框
    expect(w.find('input[type="text"]').exists()).toBe(false)
  })
})
