import { describe, it, expect } from 'vitest'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS, GROUP_LABELS, PAL_TREE } from './schema'
import { CHAPTERS } from './chapters'
import zhCN from './locales/zh-CN'

// 数据层键覆盖：按「渲染派生规则」遍历 schema/chapters 结构，逐键断言其存在于词典——
// 堵住「结构里有字段、词典漏了对应键」的盲区（漏键会让该语渲染回退到键名/字节漂移）。
// 键派生规则（与各渲染点计算完全一致）：
//   OBJECT_SECTIONS 字段  field.<section.key>.<field.key>.label / .hint（有 hint 才加）
//   SERVER_FIELDS（无 section）  field.server.<field.key>.label / .hint
//   HEADER_FIELDS（无 section）  field.header.<field.key>.label / .hint
//   章节  section.<section.key>.title / .subtitle（有 subtitle 才加）
//   选项  opt.<section.key>.<field.key>.<optionValue>（仅 optionLabels 字段；locale 字段除外——母语名恒定不译，不进 opt 键）
//   命令组  group.<GROUP_LABELS 键>
//   命令  cmd.<PAL_TREE.path 去空格换 _>（如 "world status" → cmd.world_status）
//   章标签  chapter.<CHAPTERS.id>.label
function expectedKeys(): string[] {
  const ks: string[] = []
  for (const s of OBJECT_SECTIONS) {
    ks.push(`section.${s.key}.title`)
    if (s.subtitle) ks.push(`section.${s.key}.subtitle`)
    for (const f of s.fields) {
      ks.push(`field.${s.key}.${f.key}.label`)
      if (f.hint) ks.push(`field.${s.key}.${f.key}.hint`)
      if (f.optionLabels && f.key !== 'locale')
        for (const v of Object.keys(f.optionLabels)) ks.push(`opt.${s.key}.${f.key}.${v}`)
    }
  }
  for (const f of SERVER_FIELDS) { ks.push(`field.server.${f.key}.label`); if (f.hint) ks.push(`field.server.${f.key}.hint`) }
  for (const f of HEADER_FIELDS) { ks.push(`field.header.${f.key}.label`); if (f.hint) ks.push(`field.header.${f.key}.hint`) }
  for (const k of Object.keys(GROUP_LABELS)) ks.push(`group.${k}`)
  for (const n of PAL_TREE) ks.push(`cmd.${n.path.replace(/ /g, '_')}`)
  for (const c of CHAPTERS) ks.push(`chapter.${c.id}.label`)
  return ks
}

describe('数据层键覆盖', () => {
  // 本阶段（Phase 2 Task 2）只向 zh 基线补数据层键；ja/en 由 T10 统一补齐。
  // 故此刻仅断言 zh 词典含所有派生键。T10 后可把下方断言扩到三词典（对 ja/en 各跑一遍）。
  // 注：词典是「含点」平键（如 'section.routing.title'）的扁平表；toHaveProperty 会把点当嵌套
  // 路径解析，故用 hasOwnProperty 精确判定平键存在。
  it('每个派生键存在于 zh 词典', () => {
    for (const k of expectedKeys())
      expect(Object.prototype.hasOwnProperty.call(zhCN, k), `zh 缺键 ${k}`).toBe(true)
  })
})
