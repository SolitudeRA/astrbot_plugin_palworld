import { describe, it, expect } from 'vitest'
import { CHAPTERS, DEFAULT_CHAPTER } from './chapters'
import { OBJECT_SECTIONS } from './schema'

describe('chapters', () => {
  it('默认章为 access 且存在', () => {
    expect(DEFAULT_CHAPTER).toBe('access')
    expect(CHAPTERS.some((c) => c.id === 'access')).toBe(true)
  })
  it('配置章的 blocks 并集恰等于 OBJECT_SECTIONS 全 8 键（不重不漏）', () => {
    const union = CHAPTERS.flatMap((c) => c.blocks ?? [])
    expect(union.slice().sort()).toEqual(OBJECT_SECTIONS.map((s) => s.key).slice().sort())
    expect(new Set(union).size).toBe(union.length) // 无重复
  })
  it('恰一个 status 章', () => {
    expect(CHAPTERS.filter((c) => c.kind === 'status')).toHaveLength(1)
  })
})
