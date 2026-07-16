import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StatusPanel from './StatusPanel.vue'

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('StatusPanel', () => {
  it('渲染服务器状态卡片', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({
      ok: true, servers: [{ name: 'alpha', ready: true, online: 3, max_players: 32,
        fps: 59.4, smoothness_label: '流畅', world_day: 60, peak_online_today: 5,
        basecamp_count: 2, updated_at: Math.floor(Date.now() / 1000) - 12, degraded: false }] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('alpha')
    // 读数网格：在线 stat 大数字 + /max 副字 + 峰值副读数；FPS 数字与流畅度分离着色
    expect(w.find('.oc-value').text()).toBe('3/32')
    expect(w.text()).toContain('在线玩家')
    expect(w.text()).toContain('今日峰值 5')
    expect(w.text()).toContain('59')
    expect(w.find('.fps-good').text()).toBe('流畅')
    expect(w.text()).toContain('第 60 天')
    expect(w.text()).toContain('据点数')
    expect(w.text()).toContain('秒前')
    // 在线占比进度条按 3/32 计算宽度
    expect(w.find('.oc-bar i').attributes('style')).toContain('width: 9%')
  })
  it('仅一台 → 详细区恒展开且无 chevron；detail 缺失静默不渲染', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({
      ok: true, servers: [{ name: 'solo', ready: true, degraded: false, online: 1, max_players: 8,
        fps: 60, smoothness_label: '流畅', world_day: 3, peak_online_today: 2,
        detail: { version: 'v0.6.5.1', uptime_seconds: 90061, rules: { difficulty: '普通' } } }] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.find('.oc-chev').exists()).toBe(false) // 单台不显收起控件
    expect(w.text()).toContain('运行信息')
    expect(w.text()).toContain('v0.6.5.1')
    expect(w.text()).toContain('1 天 1 小时')
    expect(w.text()).toContain('世界规则')
    expect(w.text()).toContain('普通')
  })
  it('多台 → 默认收起，点卡头展开该台详细区', async () => {
    const mk = (name: string) => ({ name, ready: true, degraded: false, online: 1, max_players: 8,
      fps: 60, smoothness_label: '流畅', world_day: 3, peak_online_today: 2,
      detail: { version: 'v0.6.5.1' } })
    ;(window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, servers: [mk('a'), mk('b')] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).not.toContain('运行信息') // 默认收起
    await w.findAll('.oc-head')[0].trigger('click')
    expect(w.findAll('.oc-detail')).toHaveLength(1) // 只展开点击的那台
    expect(w.text()).toContain('运行信息')
  })
  it('多台 ready 健康行默认收起 → 绝不落 fallback「尚未建立连接」，仍显读数；展开后显运行信息', async () => {
    // fallback 链回归守卫：ready 且非 degraded 的健康行收起（多台默认收起）时，
    // 绝不能落到「尚未建立连接」这条只锚定「未 ready」的 fallback（曾有 v-else 链 bug）。
    const mk = (name: string) => ({ name, ready: true, degraded: false, online: 2, max_players: 16,
      fps: 60, smoothness_label: '流畅', world_day: 5, peak_online_today: 4,
      detail: { version: 'v0.6.5.1', uptime_seconds: 3600 } })
    ;(window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, servers: [mk('a'), mk('b')] })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).not.toContain('尚未建立连接') // 健康行不落未连接 fallback
    expect(w.findAll('.oc-degraded')).toHaveLength(0) // 无任何降级/未连接文案元素
    expect(w.text()).not.toContain('运行信息') // 收起态详细区不渲染（既有不变量保持绿）
    expect(w.text()).toContain('在线玩家') // 读数网格仍在
    await w.findAll('.oc-head')[0].trigger('click')
    expect(w.text()).toContain('运行信息') // 展开该台后详细区出现
  })
  it('restarting 显示正在应用新配置', async () => {
    // restarting 态会 setTimeout(load, 3000)（StatusPanel.vue:19）；用假计时器
    // 避免真 3s 定时器泄漏到后续用例（afterEach 里 useRealTimers 复位）。
    vi.useFakeTimers()
    ;(window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, servers: [], restarting: true })
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('正在应用新配置')
    w.unmount()
  })
  it('读取失败进 error 态,不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockRejectedValue(new Error('net'))
    const w = mount(StatusPanel); await flushPromises()
    expect(w.text()).toContain('读取状态失败')
  })
})
