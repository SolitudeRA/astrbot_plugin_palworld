import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import App from './App.vue'
import { locale, setLocale } from './lib/i18n'
import en from './lib/locales/en'

beforeEach(() => {
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve(),
    // 默认已完成首次选模（setup_confirmed:true）→ 不进引导态 → 左轨照常显示。
    // 未确认（引导态隐藏左轨）由下方两条专测覆盖。
    apiGet: vi.fn().mockResolvedValue({ ok: true, config: { routing: { setup_confirmed: true } }, servers: [] }),
    apiPost: vi.fn().mockResolvedValue({ ok: true }),
  }
})

describe('App', () => {
  it('默认渲染报头与左索引，可切到状态章', async () => {
    const w = mount(App); await flushPromises()
    expect(w.text()).toContain('帕鲁世界终端')
    const rail = w.findAll('.rail button')
    expect(rail.some((b) => b.text().includes('状态'))).toBe(true)
    expect(rail.some((b) => b.text().includes('连接'))).toBe(true)
    const obs = rail.find((b) => b.text().includes('状态'))!
    await obs.trigger('click'); await flushPromises()
    expect(w.text()).toContain('刷新') // 进入 StatusPanel
  })
  it('切到审计章 → 渲染 AuditPanel（非 StatusPanel/SettingsPanel）', async () => {
    const w = mount(App, { global: { stubs: {
      AuditPanel: { template: '<div>AUDIT_STUB</div>' },
      StatusPanel: { template: '<div>STATUS_STUB</div>' },
      SettingsPanel: { template: '<div>SETTINGS_STUB</div>' },
    } } })
    await flushPromises()
    const rail = w.findAll('.rail button')
    const auditBtn = rail.find((b) => b.text().includes('审计'))!
    await auditBtn.trigger('click'); await flushPromises()
    expect(w.text()).toContain('AUDIT_STUB')
    expect(w.text()).not.toContain('STATUS_STUB')
  })
  it('子组件抛错 → 错误边界兜底，不白屏', async () => {
    const Boom = { setup() { throw new Error('boom-child') }, template: '<div/>' }
    const w = mount(App, { global: { stubs: { SettingsPanel: Boom } } })
    await flushPromises()
    expect(w.text()).toContain('页面发生错误，请刷新重试')
    expect(w.text()).not.toContain('boom-child') // 不透传原始错误
  })

  it('首次未选模 → 隐藏整条左轨，只显引导屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, config: {}, servers: [] })
    const w = mount(App); await flushPromises()
    expect(w.find('nav.rail').exists()).toBe(false)
    expect(w.text()).toContain('选择语言')
    expect(w.find('select.locale-switch').exists()).toBe(false)
    expect(w.text()).toContain('帕鲁世界终端') // 品牌头保留
  })

  it('已完成首次选模 → 左轨显示', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, config: { routing: { setup_confirmed: true } }, servers: [] })
    const w = mount(App); await flushPromises()
    expect(w.find('nav.rail').exists()).toBe(true)
    expect(w.find('select.locale-switch').exists()).toBe(true)
  })

  it('顶栏语言切换器只调用 config/locale，成功后保留新 locale', async () => {
    const post = window.AstrBotPluginPage!.apiPost as any
    const w = mount(App); await flushPromises()
    await w.get('select.locale-switch').setValue('ja')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('config/locale', { locale: 'ja' })
    expect(post.mock.calls.some(([, body]: any[]) => body && 'servers' in body)).toBe(false)
    expect(locale.value).toBe('ja')
  })

  it('顶栏语言 patch 失败回滚到已应用 locale', async () => {
    const post = window.AstrBotPluginPage!.apiPost as any
    post.mockResolvedValueOnce({ ok: false, error: 'restart_failed_rolled_back', detail: {} })
    const w = mount(App); await flushPromises()
    expect(locale.value).toBe('zh-CN')
    await w.get('select.locale-switch').setValue('en')
    await flushPromises()
    expect(locale.value).toBe('zh-CN')
    expect((w.get('select.locale-switch').element as HTMLSelectElement).value).toBe('zh-CN')
  })

  it('主题按钮、口号与章节索引 aria 随 locale 响应', async () => {
    en['app.theme.dark'] = '☾ Dark'
    en['app.theme.light'] = '☀ Light'
    en['app.subtitle'] = 'Palworld server monitoring and control'
    en['app.chapter_index'] = 'Chapter index'
    try {
      setLocale('en')
      const w = mount(App); await flushPromises()
      expect(w.text()).toContain('Palworld server monitoring and control')
      expect(w.get('.mast button').text()).toBe('☾ Dark')
      expect(w.get('nav.rail').attributes('aria-label')).toBe('Chapter index')

      setLocale('zh-CN')
      await nextTick()
      expect(w.text()).toContain('Palworld 服务器监测与管控')
      expect(w.get('.mast button').text()).toBe('☾ 深色')
    } finally {
      setLocale('zh-CN')
      delete en['app.theme.dark']
      delete en['app.theme.light']
      delete en['app.subtitle']
      delete en['app.chapter_index']
    }
  })
})

function stubMatchMedia(prefersDark: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: prefersDark && q.includes('dark'),
    media: q, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false,
  }))
}

describe('首次进入按系统深浅色', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })
  afterEach(() => vi.unstubAllGlobals())

  it('无存储值 + 系统偏好深色 → data-theme=dark', () => {
    stubMatchMedia(true)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('无存储值 + 系统偏好浅色 → data-theme=light', () => {
    stubMatchMedia(false)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('已有存储值时忽略系统偏好（存储优先）', () => {
    localStorage.setItem('palworld-terminal-theme', 'light')
    stubMatchMedia(true)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('无存储值 + 预设 data-theme=dark + 系统偏好浅色 → 仍 dark（中间档胜过系统偏好）', () => {
    // 存储缺失时，预设 data-theme（第二档）优先于 matchMedia（第三档）
    document.documentElement.setAttribute('data-theme', 'dark')
    stubMatchMedia(false)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('matchMedia 抛错 + 无存储无预设 → 回退 light（末档兜底）', () => {
    vi.stubGlobal('matchMedia', () => { throw new Error('no matchMedia') })
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
