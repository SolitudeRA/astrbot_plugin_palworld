import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsPanel from './SettingsPanel.vue'
import ServerCard from './ServerCard.vue'
import { collectBody } from '../lib/collect'

const cfg = () => ({ ok: true, config: {
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
  routing: { access_mode: 'restricted', default_server: '', setup_confirmed: true },
  polling: { metrics_seconds: 30, players_seconds: 30, info_seconds: 600, settings_seconds: 1800,
    game_data_seconds: 120, jitter_ratio: 0.1, max_concurrency: 6 },
  world: { timezone: 'Asia/Tokyo', locale: 'zh-CN', fps_smooth: 50, fps_moderate: 35, fps_laggy: 20 },
  bases: { enabled: true, assignment_radius: 5000, ambiguity_ratio: 0.2, confirmation_samples: 3,
    position_grid_size: 2000, z_weight: 0.5 },
  privacy: { mode: 'balanced', public_exact_ping: false, public_positions: false,
    ping_good_ms: 60, ping_ok_ms: 120, uncertain_timeout: 900 },
  history: { raw_metrics_days: 7, aggregate_days: 90, session_days: 365, observation_days: 180 },
  players: { rank_top_n: 5, exclude_names: '' },
  server_admin: { require_confirmation: false, confirmation_timeout: 30, audit_retention_days: 180 },
  permission_admins: [],
  command_permissions: [],
}, page_version: 1 })

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})
const mountAt = (chapter: string) => mount(SettingsPanel, { props: { chapter } })
// 挂载「连接」章（渲染 routing 段）并以 overrides 覆盖 config 顶层键（如 routing）。
// brief 示例用的 mountAccess 原不存在，就地补一个薄封装：合并 config、挂载、flush。
const mountAccess = async (overrides: Record<string, any> = {}) => {
  const c = cfg(); Object.assign(c.config, overrides);
  (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(c)
  const w = mountAt('access'); await flushPromises()
  return w
}

describe('SettingsPanel', () => {
  it('功能章渲染玩家查询节（players 迁至功能章：功能参数与启停同住）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mountAt('features'); await flushPromises()
    expect(w.text()).toContain('排行榜人数') // players 配置节字段
    const wp = mountAt('permissions'); await flushPromises()
    expect(wp.text()).not.toContain('排行榜人数') // 权限章不再渲染 players 段
  })
  it('权限章渲染 server_admin 配置节（server_admin 重新安家于权限章）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mountAt('permissions'); await flushPromises()
    expect(w.text()).toContain('危险命令二次确认') // server_admin 配置段字段
    expect(w.text()).toContain('审计留存天数')
  })
  it('保存 body 携带 server_admin 段（类型正确，往返闭合）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: true, warnings: {} })
    const w = mountAt('permissions'); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    const [, body] = (window.AstrBotPluginPage!.apiPost as any).mock.calls[0]
    expect(typeof body.server_admin.require_confirmation).toBe('boolean')
    expect(typeof body.server_admin.confirmation_timeout).toBe('number')
  })
  it('config 缺 server_admin 键不崩，applyConfig 退化为空段', async () => {
    // 已确认安装（routing.setup_confirmed）方渲染正常章节；server_admin 仍缺，验退化不崩
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, config: { routing: { setup_confirmed: true } } })
    const w = mountAt('permissions'); await flushPromises()
    expect(w.text()).toContain('服务器管控') // 段仍按 schema 渲染，不因缺键崩
  })
  it('access 章渲染默认查询节 + 危险区（访问模式 + 切换运行模式）+ 保存条', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mountAt('access'); await flushPromises()
    expect(w.text()).toContain('默认查询') // routing 段拆出 access_mode 后改名
    expect(w.text()).toContain('危险区')
    expect(w.text()).toContain('访问模式') // 危险区首行
    expect(w.text()).toContain('切换运行模式')
    expect(w.text()).toContain('保存设置')
    expect(w.get('button.pw-save')).toBeTruthy()
  })
  it('config/get unauthorized → 整块错误态，不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: false, error: 'unauthorized', detail: {} })
    const w = mountAt('access'); await flushPromises()
    expect(w.text()).toContain('未登录')
  })
  it('保存 apiPost body 不含 group_bindings/features，含 command_permissions（body 恒全量）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: true, warnings: {} })
    const w = mountAt('access'); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    const [, body] = (window.AstrBotPluginPage!.apiPost as any).mock.calls[0]
    expect('group_bindings' in body).toBe(false)
    expect('features' in body).toBe(false)
    expect(Array.isArray(body.command_permissions)).toBe(true)
    expect(typeof body.polling.metrics_seconds).toBe('number')
  })
  it('保存业务错误 credential_redirect → 就地提示，不塌整页', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: false, error: 'credential_redirect', detail: { path: 'servers[0].password' } })
    const w = mountAt('access'); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    expect(w.text()).toContain('请点击该服务器的「修改」重新输入密码后再保存')
    expect(w.text()).toContain('保存设置') // 表单/保存条仍在（未塌成整页错误）
  })

  it('保存响应回传 config 时用其刷新 state(新行获得服务端 __row_id)', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const saved = cfg().config
    saved.servers = [...saved.servers,
      { __row_id: 'srv-1', name: 'newbie', enabled: true, base_url: 'http://y', username: 'admin',
        password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' }];
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: true, warnings: {}, config: saved })
    const w = mountAt('access'); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    expect(w.text()).toContain('newbie') // state 已被落库后的 config 刷新
  })

  it('改动后显示未保存提示,保存成功后消失', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: true, warnings: {}, config: cfg().config })
    const w = mountAt('access'); await flushPromises()
    expect(w.text()).not.toContain('有未保存的更改')
    await w.get('button.add').trigger('click') // 添加服务器 → dirty
    expect(w.text()).toContain('有未保存的更改')
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    expect(w.text()).not.toContain('有未保存的更改') // applyConfig 复位
  })

  it('权限章渲染 callout + 管理员名单 + 命令树', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mountAt('permissions'); await flushPromises()
    expect(w.text()).toContain('管理员名单') // 管理员名单区块
    expect(w.text()).toContain('命令权限') // 命令树区块标题
    expect(w.text()).toContain('/pal world status') // 命令树含具体命令完整路径（恒开核心必列）
    expect(w.text()).toContain('名单为空') // 空名单提示
    expect(w.text()).toContain('名单全局') // 爆炸半径安全警句(勿静默删除)
  })

  it('权限章：点击命令树三态段 → 覆盖命令权限并置 dirty，collectBody 产出该行', async () => {
    const c = cfg()
    c.config.command_permissions = [{ command: 'player', enabled: 'on', admin_only: 'inherit' }] // 开玩家功能，行才在权限页列出
    ;(window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(c)
    const w = mountAt('permissions'); await flushPromises()
    expect((w.vm as any).state.command_perms).toEqual({ player: { enabled: 'on', admin_only: 'inherit' } })
    const row = w.findAll('.ct-leaf').find((r) => r.text().includes('player info'))!
    // 单轴表：admin 开关 off(继承所有人) → 点击置 on（仅管理员）= 显式覆盖
    await row.find('.pw-switch').trigger('click')
    expect((w.vm as any).state.command_perms['player info']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    expect(w.text()).toContain('有未保存的更改')
    const body = collectBody((w.vm as any).state)
    expect(body.command_permissions).toEqual([
      { command: 'player', enabled: 'on', admin_only: 'inherit' },
      { command: 'player info', enabled: 'inherit', admin_only: 'on' },
    ])
  })

  it('权限章：applyConfig 从 command_permissions 行还原树 state（hydrate 往返）', async () => {
    const c = cfg()
    c.config.command_permissions = [
      { command: 'guild', enabled: 'on', admin_only: 'inherit' }, // 开公会功能，行才在权限页列出
      { command: 'guild list', enabled: 'inherit', admin_only: 'on' },
    ];
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(c)
    const w = mountAt('permissions'); await flushPromises()
    // 树 state 读回该覆盖行
    expect((w.vm as any).state.command_perms['guild list']).toEqual({ enabled: 'inherit', admin_only: 'on' })
    // CommandTree 该叶子 admin 开关显示覆盖生效值（checked）+ amber 覆盖环（ovr）
    const row = w.findAll('.ct-leaf').find((r) => r.text().includes('guild list'))!
    const adminSwitch = row.find('.pw-switch')
    expect(adminSwitch.attributes('data-state')).toBe('checked')
    expect(adminSwitch.classes()).toContain('ovr')
  })

  it('config 缺 permission 两键不崩、collectBody 产出空数组', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: true, config: {} })
    const w = mountAt('permissions'); await flushPromises()
    const body = collectBody((w.vm as any).state)
    expect(body.permission_admins).toEqual([])
    expect(body.command_permissions).toEqual([])
  })

  it('single 模式隐藏 world_mode/default_server 字段但 collect 仍回传 world_mode', async () => {
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', world_mode: 'single', setup_confirmed: true } })
    // routing 表单不渲染 world_mode（恒隐藏）/ default_server（single 隐藏）标签
    expect(w.text()).not.toContain('默认服务器')
    // 锚字段 hint 而非「运行模式」子串——危险区标题「切换运行模式」合法含该词（子串陷阱）
    expect(w.text()).not.toContain('「多服务器」按群绑定/切换服务器')
    // 顶部只读模式标识
    expect(w.text()).toContain('单服务器')
    // 字段隐藏但值仍回传（collectBody 从 state 读，不受模板过滤影响）
    const body = collectBody((w.vm as any).state) as any
    expect(body.routing.world_mode).toBe('single')
  })

  it('multi 模式呈现 default_server 字段与「多服务器」标识（world_mode 仍恒隐藏，fail-safe 全字段）', async () => {
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', world_mode: 'multi', setup_confirmed: true } })
    expect(w.text()).toContain('默认服务器') // 多模式保留默认服务器字段
    // world_mode 字段任何模式都隐藏——锚其 hint 串防子串陷阱（危险区标题含「运行模式」）
    expect(w.text()).not.toContain('「多服务器」按群绑定/切换服务器')
    expect(w.text()).toContain('多服务器')
    const body = collectBody((w.vm as any).state) as any
    expect(body.routing.world_mode).toBe('multi')
  })

  it('applyConfig 对缺 world_mode 的 routing 兜底 seed 为 multi（collect 恒有值）', async () => {
    // 默认 cfg().routing 不带 world_mode → seed 兜底 multi（fail-safe）
    const w = await mountAccess()
    expect(w.text()).toContain('多服务器')
    const body = collectBody((w.vm as any).state) as any
    expect(body.routing.world_mode).toBe('multi')
  })

  it('single 模式渲染单台服务器表单、不显示增删、不截断 state.servers（保存仍含 2 台）', async () => {
    const w = await mountAccess({
      routing: { access_mode: 'restricted', default_server: '', world_mode: 'single', setup_confirmed: true },
      servers: [{ __row_id: 'srv-0', name: 'A' }, { __row_id: 'srv-1', name: 'B' }],
    })
    // 单模式只编辑 servers[0] → 无「＋ 添加服务器」增按钮
    // （注：自定义请求头段另有 button.add「添加请求头」，故按文案而非类名判定）
    expect(w.text()).not.toContain('添加服务器')
    expect(w.findAll('button.add').some((b) => b.text().includes('添加服务器'))).toBe(false)
    // 唯一服务器不给删（hideDelete）→ 查看态无「移除」按钮
    expect(w.text()).not.toContain('移除')
    // 模板只渲染一张服务器卡（servers[0]）
    expect(w.findAllComponents(ServerCard)).toHaveLength(1)
    // 核心不变量：single 只编辑 servers[0]，多余的第二台原样保留 → collect 仍含 2 台
    const body = collectBody((w.vm as any).state) as any
    expect(body.servers).toHaveLength(2)
    expect(body.servers.map((s: any) => s.name)).toEqual(['A', 'B'])
  })

  it('single + restricted 显示授权群名单区', async () => {
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', world_mode: 'single', setup_confirmed: true } })
    expect(w.text()).toContain('授权群名单')
    expect(w.text()).toContain('「受限授权」模式下，仅名单内的群可查询服务器')
    expect(w.text()).toContain('/pal whereami')
  })

  it('改访问模式未保存 → 授权群名单不实时收折（跟已保存快照走）+ 显示保存后生效', async () => {
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', world_mode: 'single', setup_confirmed: true } })
    expect(w.text()).toContain('授权群名单')
    ;(w.vm as any).state.sections.routing.access_mode = 'open' // 模拟下拉改动（未保存）
    await w.vm.$nextTick()
    expect(w.text()).toContain('授权群名单') // 名单仍在：显隐依据落库快照
    expect(w.text()).toContain('（保存后生效）')
  })

  it('single + open 不显示授权群名单区（受限才呈现）', async () => {
    const w = await mountAccess({ routing: { access_mode: 'open', default_server: '', world_mode: 'single', setup_confirmed: true } })
    expect(w.text()).not.toContain('授权群名单')
  })

  it('multi 模式不显示授权群名单区（仅 single+restricted）', async () => {
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', world_mode: 'multi', setup_confirmed: true } })
    expect(w.text()).not.toContain('授权群名单')
  })

  it('applyConfig 无条件 hydrate single_allowed_groups，collect 往返闭合（含 multi 不抹除）', async () => {
    const w = await mountAccess({
      routing: { access_mode: 'restricted', default_server: '', world_mode: 'multi', setup_confirmed: true },
      single_allowed_groups: [{ __row_id: 'sag-0', umo: 'aiocqhttp:GroupMessage:1', note: '主群' }],
    })
    // multi 模式虽不显示名单区，state 仍 hydrate、collect 仍回传（防切模式抹除）
    expect((w.vm as any).state.single_allowed_groups).toHaveLength(1)
    const body = collectBody((w.vm as any).state) as any
    expect(body.single_allowed_groups).toEqual([{ __row_id: 'sag-0', umo: 'aiocqhttp:GroupMessage:1', note: '主群' }])
  })

  it('config 缺 single_allowed_groups 键不崩、collect 产出空数组', async () => {
    const w = await mountAccess()
    const body = collectBody((w.vm as any).state) as any
    expect(body.single_allowed_groups).toEqual([])
  })

  it('single 模式 + 空 servers 配置渲染不崩（applyConfig seed 补一台占位）', async () => {
    const w = await mountAccess({
      routing: { access_mode: 'restricted', default_server: '', world_mode: 'single', setup_confirmed: true },
      servers: [],
    })
    // 空配置 seed 补一台占位（绝不截断已有；此处本无已有）→ state 有 1 台
    expect((w.vm as any).state.servers).toHaveLength(1)
    // 渲染未抛错（mountAccess 已 flush），服务器区块标题在（single 用单数措辞）
    expect(w.text()).toContain('当前监测的唯一服务器')
    // 单台占位仍能 collect
    const body = collectBody((w.vm as any).state) as any
    expect(body.servers).toHaveLength(1)
  })

  it('未确认时显示引导屏、取代正常章节', async () => {
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', setup_confirmed: false } })
    expect(w.findComponent({ name: 'ModeOnboarding' }).exists()).toBe(true)
    expect(w.text()).not.toContain('保存设置')
  })

  it('已确认时不显引导屏、显示正常章节', async () => {
    const w = await mountAccess()  // cfg() 已 setup_confirmed:true
    expect(w.findComponent({ name: 'ModeOnboarding' }).exists()).toBe(false)
    expect(w.text()).toContain('保存设置')
  })

  it('确认写 world_mode + setup_confirmed 并保存', async () => {
    const post = (window.AstrBotPluginPage!.apiPost as any)
    post.mockResolvedValue({ ok: true, warnings: {} })
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', setup_confirmed: false } })
    await w.findComponent({ name: 'ModeOnboarding' }).vm.$emit('confirm', 'multi')
    await flushPromises()
    const body = post.mock.calls.at(-1)![1]
    expect(body.routing.world_mode).toBe('multi')
    expect(body.routing.setup_confirmed).toBe(true)
  })

  it('确认保存失败 → 还原 setup_confirmed，引导屏仍挂载（防写侧半态死锁）', async () => {
    const post = (window.AstrBotPluginPage!.apiPost as any)
    post.mockRejectedValue(new Error('boom'))  // 保存失败（瞬时/未鉴权/回滚等）
    const w = await mountAccess({ routing: { access_mode: 'restricted', default_server: '', setup_confirmed: false } })
    await w.findComponent({ name: 'ModeOnboarding' }).vm.$emit('confirm', 'multi')
    await flushPromises()
    // 失败还原：引导屏仍挂载、不进正常章节，整页刷新才恢复的半态被杜绝
    expect(w.findComponent({ name: 'ModeOnboarding' }).exists()).toBe(true)
    expect((w.vm as any).state.sections.routing.setup_confirmed).toBe(false)
    expect(w.text()).not.toContain('保存设置')
  })
})
