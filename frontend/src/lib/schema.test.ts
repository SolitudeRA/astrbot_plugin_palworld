import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS } from './schema'

// vitest root = frontend/；仓库根的 _conf_schema.json 在上一层。
// 注：import.meta.url 先取到局部变量再传入，避开 vite import-analysis 对
// `new URL('...', import.meta.url)` 字面量的资源改写（会重写成 /@fs 的 http URL，
// 令 fileURLToPath 报 "URL must be of scheme file"）。
const here = import.meta.url
const schemaPath = fileURLToPath(new URL('../../../_conf_schema.json', here))
const RAW = JSON.parse(readFileSync(schemaPath, 'utf8'))

function keysOfObject(section: string): string[] {
  return Object.keys(RAW[section].items).sort()
}
function keysOfTemplateList(section: string, tpl: string): string[] {
  return Object.keys(RAW[section].templates[tpl].items).sort()
}

describe('schema 完整性（对齐 _conf_schema.json，缺一即失败）', () => {
  it('7 个 object 节字段集完全一致', () => {
    for (const sec of OBJECT_SECTIONS) {
      const declared = sec.fields.map((f) => f.key).sort()
      expect(declared, `节 ${sec.key} 字段不齐`).toEqual(keysOfObject(sec.key))
    }
  })
  it('SERVER_FIELDS 覆盖 servers 模板全字段', () => {
    expect(SERVER_FIELDS.map((f) => f.key).sort()).toEqual(keysOfTemplateList('servers', 'server'))
  })
  it('HEADER_FIELDS 覆盖 custom_headers 模板全字段', () => {
    expect(HEADER_FIELDS.map((f) => f.key).sort()).toEqual(keysOfTemplateList('custom_headers', 'header'))
  })
  it('OBJECT_SECTIONS 恰为 7 个 object 节（不含 servers/custom_headers/group_bindings）', () => {
    expect(OBJECT_SECTIONS.map((s) => s.key)).toEqual(
      ['routing', 'polling', 'world', 'bases', 'privacy', 'history', 'features'])
  })
})
