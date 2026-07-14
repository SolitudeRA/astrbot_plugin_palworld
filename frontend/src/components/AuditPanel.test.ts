import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AuditPanel from './AuditPanel.vue'

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

describe('AuditPanel', () => {
  it('渲染只读审计表（时间/管理员/动作/目标/服务器/结果）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({
      ok: true, audits: [
        { ts: 1_700_000_000, time: '2023-11-14 22:13 UTC', action: 'kick', server: 'alpha',
          admin: 'qq:1', target: 'Alice#abcdef', success: true, error: null },
        { ts: 1_699_999_000, time: '2023-11-14 21:56 UTC', action: 'stop', server: 'beta',
          admin: 'qq:2', target: '', success: false, error: 'server_offline' },
      ],
    })
    const w = mount(AuditPanel); await flushPromises()
    // 表头
    expect(w.text()).toContain('时间')
    expect(w.text()).toContain('管理员')
    expect(w.text()).toContain('动作')
    expect(w.text()).toContain('目标')
    expect(w.text()).toContain('服务器')
    expect(w.text()).toContain('结果')
    // 行内容
    expect(w.text()).toContain('2023-11-14 22:13 UTC')
    expect(w.text()).toContain('qq:1')
    expect(w.text()).toContain('kick')
    expect(w.text()).toContain('Alice#abcdef')
    expect(w.text()).toContain('alpha')
    expect(w.text()).toContain('成功')
    // 失败行
    expect(w.text()).toContain('stop')
    expect(w.text()).toContain('beta')
    expect(w.text()).toContain('失败')
  })

  it('空数组显示空态', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, audits: [] })
    const w = mount(AuditPanel); await flushPromises()
    expect(w.text()).toContain('暂无管理操作记录')
  })

  it('读取失败进 error 态,不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockRejectedValue(new Error('net'))
    const w = mount(AuditPanel); await flushPromises()
    expect(w.text()).toContain('读取审计记录失败')
  })

  it('restarting 显示正在应用新配置', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, audits: [], restarting: true })
    const w = mount(AuditPanel); await flushPromises()
    expect(w.text()).toContain('正在应用新配置')
  })
})
