export interface Chapter {
  id: string
  label: string
  group: '观测' | '配置'
  kind: 'status' | 'settings'
  blocks?: string[] // 该配置章渲染的 OBJECT_SECTIONS 键
}

export const CHAPTERS: Chapter[] = [
  { id: 'status', label: '观测台', group: '观测', kind: 'status' },
  { id: 'access', label: '接入', group: '配置', kind: 'settings', blocks: ['routing'] },
  { id: 'cadence', label: '采集', group: '配置', kind: 'settings', blocks: ['polling'] },
  { id: 'world', label: '世界与据点', group: '配置', kind: 'settings', blocks: ['world', 'bases'] },
  { id: 'privacy', label: '隐私与留存', group: '配置', kind: 'settings', blocks: ['privacy', 'history'] },
  { id: 'feature', label: '功能分组', group: '配置', kind: 'settings', blocks: ['features', 'players'] },
]

export const DEFAULT_CHAPTER = 'access'
