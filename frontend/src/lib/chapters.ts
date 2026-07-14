export interface Chapter {
  id: string
  label: string
  group: '观测' | '配置'
  kind: 'status' | 'settings' | 'audit' // status/audit 为只读观测；settings 渲染配置块
  blocks?: string[] // 该配置章渲染的 OBJECT_SECTIONS 键
}

export const CHAPTERS: Chapter[] = [
  { id: 'status', label: '状态', group: '观测', kind: 'status' },
  { id: 'audit', label: '审计', group: '观测', kind: 'audit', blocks: [] },
  { id: 'access', label: '连接', group: '配置', kind: 'settings', blocks: ['routing'] },
  { id: 'cadence', label: '采集', group: '配置', kind: 'settings', blocks: ['polling'] },
  { id: 'world', label: '世界与据点', group: '配置', kind: 'settings', blocks: ['world', 'bases'] },
  { id: 'privacy', label: '隐私与留存', group: '配置', kind: 'settings', blocks: ['privacy', 'history'] },
  { id: 'feature', label: '功能开关', group: '配置', kind: 'settings', blocks: ['features', 'players', 'server_admin'] },
  { id: 'permissions', label: '权限', group: '配置', kind: 'settings', blocks: [] },
]

export const DEFAULT_CHAPTER = 'access'
