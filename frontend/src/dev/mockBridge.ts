// 开发预览用「内存假后端」：把 window.AstrBotPluginPage 换成一份纯内存实现，
// 让整个真实设置页 App 在 vite dev server 上跑起来，逐屏确认阶段二/三的 UI。
//
// 硬约束：本文件与 main-dev.ts / dev.html 均为 dev-only，绝不进 vite build 产物
// （build input 是 index.html，dev.html 不被引用）。响应形状对照后端真源
// palworld_terminal/presentation/{web_api,config_view}.py 逐端点核对，不猜。
//
// 写操作真正改内存状态：保存后 dirty 清、转移后模式徽章变、purge 后孤儿列表空、
// 删服务器保存后产生孤儿——「交互全真、仅数据是假」。
import { OBJECT_SECTIONS } from '../lib/schema'

// 场景在 sessionStorage 里的键（dev.html 的切换小条与 main-dev.ts 共享此常量语义）。
export const SCENARIO_KEY = 'pw-dev-scenario'
export const DEFAULT_SCENARIO = 'multi'

const SENTINEL = '__unchanged__' // 与 lib/collect.ts / config_view.py 一致

export interface MockBridgeOptions {
  nowMs?: number
  seed?: number
  locale?: 'zh-CN' | 'ja' | 'en'
  neutralFixtures?: boolean
  latencyMs?: number
}

// ---- 内部原始配置（未脱敏，含明文占位）与假 DB 状态 ----
type Dict = Record<string, unknown>
interface RawServer {
  name: string; enabled: boolean; base_url: string; username: string
  password: string; password_env: string; timeout: number; verify_tls: boolean; timezone: string
}
interface RawHeader { name: string; value: string; value_env: string; servers: string }
interface RawConfig {
  servers: RawServer[]
  custom_headers: RawHeader[]
  group_bindings: Dict[]
  permission_admins: { id: string; note: string }[]
  command_permissions: { command: string; enabled: string; admin_only: string }[]
  single_allowed_groups: { umo: string; note: string }[]
  routing: Dict
  [section: string]: unknown
}
interface StatusSeed {
  ready: boolean; degraded: boolean; online: number; max_players: number
  fps: number; smoothness: 'smooth' | 'moderate' | 'laggy' | 'very_laggy'; world_day: number
  peak_online_today: number; basecamp_count: number
}
interface AuditRow {
  ts: number; time: string; action: string; server: string
  admin: string; target: string; success: boolean; error: string | null
}
interface GroupBinding { umo: string; server_ids: string[] }
interface Db {
  config: RawConfig
  audits: AuditRow[]
  dataServerIds: Set<string> // DB 里「有历史数据」的 server_id 集合；孤儿 = 有数据但 config 已无
  groupBindings: GroupBinding[] // 多世界 DB 群绑定（preview target=single 的 bindings 源）
  statusByName: Record<string, StatusSeed>
}

// ---- 工具 ----
interface MockRuntime {
  nowSec: () => number
  randInt: (lo: number, hi: number) => number
  delay: () => Promise<void>
}

function seededRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state += 0x6D2B79F5
    let value = state
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}

function createRuntime(options: MockBridgeOptions): MockRuntime {
  const fixedNow = Number.isFinite(options.nowMs) ? Math.floor(options.nowMs! / 1000) : null
  const random = Number.isSafeInteger(options.seed) ? seededRandom(options.seed!) : Math.random
  const latency = Number.isFinite(options.latencyMs) && options.latencyMs! >= 0 ? options.latencyMs! : 140
  return {
    nowSec: () => fixedNow ?? Math.floor(Date.now() / 1000),
    randInt: (lo, hi) => lo + Math.floor(random() * (hi - lo + 1)),
    delay: () => latency === 0 ? Promise.resolve() : new Promise((resolve) => setTimeout(resolve, latency)),
  }
}

const str = (v: unknown): string => (v == null ? '' : String(v))
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T
function clamp(n: number, lo: number, hi: number): number { return Math.max(lo, Math.min(hi, n)) }

const PAD = (n: number) => (n < 10 ? '0' + n : '' + n)
function fmtTs(ts: number): string {
  if (!Number.isFinite(ts)) return ''
  const d = new Date(ts * 1000)
  return `${d.getUTCFullYear()}-${PAD(d.getUTCMonth() + 1)}-${PAD(d.getUTCDate())} `
    + `${PAD(d.getUTCHours())}:${PAD(d.getUTCMinutes())}:${PAD(d.getUTCSeconds())} UTC`
}

// 各 object 节按 schema 默认值构造（保证所有字段有值，表单不落空）。
function defaultSections(): Record<string, Dict> {
  const out: Record<string, Dict> = {}
  for (const sec of OBJECT_SECTIONS) {
    const o: Dict = {}
    for (const f of sec.fields) o[f.key] = f.default
    out[sec.key] = o
  }
  return out
}

// 脱敏：镜像 config_view.redact_config——注入按位 __row_id、抹明文、置 *_set 布尔。
function redact(cfg: RawConfig): Dict {
  const out = clone(cfg) as Dict
  const listPrefix: Record<string, string> = {
    servers: 'srv', custom_headers: 'hdr', group_bindings: 'bind',
    permission_admins: 'adm', command_permissions: 'cmd', single_allowed_groups: 'sag',
  }
  for (const [section, prefix] of Object.entries(listPrefix)) {
    const items = out[section]
    if (!Array.isArray(items)) continue
    items.forEach((it: Dict, i: number) => { if (it && typeof it === 'object') it.__row_id = `${prefix}-${i}` })
    if (section === 'servers') {
      for (const it of items as Dict[]) {
        const pw = str(it.password); const env = str(it.password_env)
        it.password = ''
        it.password_set = Boolean(pw) || Boolean(env)
      }
    }
    if (section === 'custom_headers') {
      for (const it of items as Dict[]) {
        const val = str(it.value); const env = str(it.value_env)
        it.value = ''
        it.value_set = Boolean(val) || Boolean(env)
      }
    }
  }
  return out
}

// 孤儿 = DB 有数据但当前 config 已不含的 server_id（server_id 即 name，见 config.py）。
function computeOrphans(db: Db): string[] {
  const valid = new Set(db.config.servers.map((s) => s.name))
  return [...db.dataServerIds].filter((id) => !valid.has(id)).sort()
}

const SMOOTHNESS_LABELS = {
  'zh-CN': { smooth: '流畅', moderate: '一般', laggy: '卡顿', very_laggy: '严重卡顿' },
  ja: { smooth: '滑らか', moderate: '普通', laggy: 'カクつき', very_laggy: '深刻なカクつき' },
  en: { smooth: 'Smooth', moderate: 'Fair', laggy: 'Laggy', very_laggy: 'Very laggy' },
} as const

function statusRows(db: Db, runtime: MockRuntime): Dict[] {
  const t = runtime.nowSec()
  const world = db.config.world
  const locale = world && typeof world === 'object' && !Array.isArray(world)
    ? str((world as Dict).locale)
    : 'zh-CN'
  const labels = SMOOTHNESS_LABELS[locale as keyof typeof SMOOTHNESS_LABELS] ?? SMOOTHNESS_LABELS['zh-CN']
  return db.config.servers.map((s) => {
    const seed = db.statusByName[s.name]
    if (!seed || !seed.ready) return { name: s.name, ready: false }
    const online = clamp(seed.online + runtime.randInt(-1, 1), 0, seed.max_players)
    const peak = Math.max(seed.peak_online_today, online)
    if (seed.degraded) {
      return { name: s.name, ready: true, degraded: true, last_ok: t - runtime.randInt(120, 600) }
    }
    const fps = seed.fps + runtime.randInt(-2, 2)
    return {
      name: s.name, ready: true, degraded: false,
      online, max_players: seed.max_players, fps,
      smoothness: seed.smoothness, smoothness_label: labels[seed.smoothness], world_day: seed.world_day,
      peak_online_today: peak, basecamp_count: seed.basecamp_count,
      updated_at: t - runtime.randInt(2, 40),
      // 详细区（demo 假数据）：字段名对齐 Palworld API（info/metrics/settings），
      // 统一落地时后端 status_rows 白名单按此形状扩展
      detail: {
        version: 'v0.6.5.1',
        description: `Palworld dedicated server ${s.name}`,
        uptime_seconds: 6 * 86400 + 4 * 3600 + runtime.randInt(0, 3000),
        frametime_ms: Math.round(10000 / Math.max(fps, 1)) / 10,
        address: String(s.base_url ?? ''),
        rules: { difficulty: 'Normal', pvp: 'Off', death_penalty: 'Drop items and equipment', exp_rate: 'x1.0' },
      },
    }
  })
}

// ---- config/save：镜像 validate_and_backfill + 落库往返 ----
function oldServerByRowId(list: RawServer[], rid: string | null | undefined): RawServer | null {
  if (!rid || !rid.startsWith('srv-')) return null
  const i = Number(rid.slice(4))
  return Number.isInteger(i) && i >= 0 && i < list.length ? list[i] : null
}
function oldHeaderByRowId(list: RawHeader[], rid: string | null | undefined): RawHeader | null {
  if (!rid || !rid.startsWith('hdr-')) return null
  const i = Number(rid.slice(4))
  return Number.isInteger(i) && i >= 0 && i < list.length ? list[i] : null
}

function applySave(db: Db, body: Dict, runtime: MockRuntime): Dict {
  const oldServers = db.config.servers
  const oldHeaders = db.config.custom_headers
  const inServers = Array.isArray(body.servers) ? (body.servers as Dict[]) : []
  const inHeaders = Array.isArray(body.custom_headers) ? (body.custom_headers as Dict[]) : []

  db.config.servers = inServers.map((s) => {
    const old = oldServerByRowId(oldServers, s.__row_id as string | null)
    let password = s.password
    if (password === SENTINEL) password = old ? old.password : '' // 哨兵→回填旧密码
    return {
      name: str(s.name), enabled: s.enabled === true, base_url: str(s.base_url),
      username: str(s.username), password: str(password), password_env: str(s.password_env),
      timeout: typeof s.timeout === 'number' ? s.timeout : Number(s.timeout) || 0,
      verify_tls: s.verify_tls === true, timezone: str(s.timezone),
    }
  })
  db.config.custom_headers = inHeaders.map((h) => {
    const old = oldHeaderByRowId(oldHeaders, h.__row_id as string | null)
    let value = h.value
    if (value === SENTINEL) value = old ? old.value : ''
    return { name: str(h.name), value: str(value), value_env: str(h.value_env), servers: str(h.servers) }
  })
  db.config.permission_admins = (Array.isArray(body.permission_admins) ? body.permission_admins as Dict[] : [])
    .map((a) => ({ id: str(a.id), note: str(a.note) }))
  db.config.single_allowed_groups = (Array.isArray(body.single_allowed_groups) ? body.single_allowed_groups as Dict[] : [])
    .map((g) => ({ umo: str(g.umo), note: str(g.note) }))
  db.config.command_permissions = (Array.isArray(body.command_permissions) ? body.command_permissions as Dict[] : [])
    .map((c) => ({ command: str(c.command), enabled: str(c.enabled), admin_only: str(c.admin_only) }))
  for (const sec of OBJECT_SECTIONS) {
    if (body[sec.key] && typeof body[sec.key] === 'object') db.config[sec.key] = { ...(body[sec.key] as Dict) }
  }
  // group_bindings 不在 body 内（collectBody 故意省略）→ 保留旧值，不清空。
  return { ok: true, warnings: {}, config: redact(db.config), saved_ts: runtime.nowSec() }
}

// ---- config/locale：镜像 locale-only patch，只改 world.locale ----
function applyLocalePatch(db: Db, body: Dict, runtime: MockRuntime): Dict {
  const value = body.locale
  if (value !== 'zh-CN' && value !== 'ja' && value !== 'en') {
    return { ok: false, error: 'invalid_field', detail: { path: 'world.locale' } }
  }
  const world = db.config.world
  db.config.world = {
    ...(world && typeof world === 'object' && !Array.isArray(world) ? world as Dict : {}),
    locale: value,
  }
  return { ok: true, config: redact(db.config), saved_ts: runtime.nowSec() }
}

// ---- mode/transfer/preview ----
function transferPreview(db: Db, target: string): Dict {
  const ready = db.config.servers.filter((s) => s.enabled).map((s) => ({ server_id: s.name, name: s.name }))
  if (target === 'single') {
    return { ok: true, ready_servers: ready, bindings: db.groupBindings.map((b) => clone(b)) }
  }
  if (target === 'multi') {
    const allowed_groups = db.config.single_allowed_groups.map((e) => ({ umo: e.umo, note: e.note }))
    return { ok: true, ready_servers: ready, allowed_groups }
  }
  return { ok: false, error: 'invalid_target', detail: {} }
}

// ---- mode/transfer：改内存 world_mode + 回传新 config + summary/warnings ----
function runTransfer(db: Db, body: Dict, runtime: MockRuntime): Dict {
  const target = body.target_mode
  const current = str(db.config.routing.world_mode) || 'multi'
  if (target !== 'single' && target !== 'multi') return { ok: false, error: 'invalid_target', detail: {} }
  if (target === current) return { ok: false, error: 'no_change', detail: {} }

  const migrate = Array.isArray(body.migrate_umos) ? (body.migrate_umos as unknown[]).map(str) : []
  const purged: Record<string, Record<string, number>> = {}
  const failed: string[] = []

  if (target === 'single') {
    const survivor = str(body.surviving_server_id)
    const purgeOthers = body.purge_others === true
    // survivor 移到首位
    const idx = db.config.servers.findIndex((s) => s.name === survivor)
    if (idx > 0) db.config.servers.unshift(db.config.servers.splice(idx, 1)[0])
    if (purgeOthers) {
      const others = db.config.servers.filter((s) => s.name !== survivor).map((s) => s.name)
      db.config.servers = db.config.servers.filter((s) => s.name === survivor)
      for (const id of others) {
        db.dataServerIds.delete(id) // 数据被清 → 不留孤儿
        purged[id] = {
          worlds: 1,
          sessions: runtime.randInt(3, 60),
          metrics: runtime.randInt(50, 400),
        }
      }
    }
    // 迁移群授权并入单世界名单（move：清源群绑定）
    const existing = new Set(db.config.single_allowed_groups.map((e) => e.umo))
    for (const umo of migrate) if (!existing.has(umo)) {
      db.config.single_allowed_groups.push({ umo, note: '从多世界绑定迁移' }); existing.add(umo)
    }
    db.config.group_bindings = []
    db.groupBindings = []
    db.config.routing.world_mode = 'single'
    pushAudit(db, 'mode_transfer', survivor || 'mode_transfer', runtime)
    return {
      ok: true, config: redact(db.config), warnings: {},
      summary: { from: current, to: 'single', surviving: survivor, migrated: migrate.length, purged, failed_server_ids: failed },
    }
  }

  // single → multi：清单世界名单（move），迁移的群预绑到首个就绪台
  db.config.single_allowed_groups = []
  const readyTarget = db.config.servers.find((s) => s.enabled)
  if (readyTarget && migrate.length) {
    for (const umo of migrate) db.groupBindings.push({ umo, server_ids: [readyTarget.name] })
  }
  db.config.routing.world_mode = 'multi'
  pushAudit(db, 'mode_transfer', readyTarget?.name || 'mode_transfer', runtime)
  return {
    ok: true, config: redact(db.config), warnings: {},
    summary: { from: current, to: 'multi', surviving: null, migrated: migrate.length, purged: {}, failed_server_ids: failed },
  }
}

// ---- mode/orphans/purge：现场重算孤儿集，交集过滤，其余 rejected ----
function runPurge(db: Db, body: Dict, runtime: MockRuntime): Dict {
  const orphans = new Set(computeOrphans(db))
  const requested = body && Array.isArray(body.server_ids) ? (body.server_ids as unknown[]).map(str) : null
  const targets = requested === null ? [...orphans].sort() : [...new Set(requested)].sort()
  if (!targets.length) return { ok: true, purged: {}, rejected: [], failed_server_ids: [] }
  const purged: Record<string, Record<string, number>> = {}
  const rejected: string[] = []
  const failed: string[] = []
  for (const sid of targets) {
    if (!orphans.has(sid)) { rejected.push(sid); continue } // TOCTOU 防线
    db.dataServerIds.delete(sid)
    purged[sid] = {
      worlds: 1,
      sessions: runtime.randInt(2, 40),
      metrics: runtime.randInt(30, 300),
    }
  }
  pushAudit(db, 'orphan_purge', targets[0], runtime)
  return { ok: true, purged, rejected, failed_server_ids: failed }
}

function pushAudit(db: Db, action: string, server: string, runtime: MockRuntime): void {
  const ts = runtime.nowSec()
  db.audits.unshift({ ts, time: fmtTs(ts), action, server, admin: 'demo-admin', target: '', success: true, error: null })
}

// ---- 场景 preset ----
function scenarioMulti(runtime: MockRuntime, neutralFixtures = false): Db {
  const names = neutralFixtures
    ? {
        tokyo: 'Tokyo-01',
        osaka: 'Osaka-02',
        seoul: 'Seoul-03',
        retiredA: 'Retired-01',
        retiredB: 'Retired-02',
      }
    : {
        tokyo: '东京一号',
        osaka: '大阪二号',
        seoul: '首尔三号',
        retiredA: '名古屋旧服',
        retiredB: '福冈退役服',
      }
  const config: RawConfig = {
    ...defaultSections(),
    servers: [
      { name: names.tokyo, enabled: true, base_url: 'http://tokyo.example.com:8212', username: 'admin', password: '', password_env: 'PAL_TOKYO_PW', timeout: 10, verify_tls: true, timezone: 'Asia/Tokyo' },
      { name: names.osaka, enabled: true, base_url: 'http://osaka.example.com:8212', username: 'admin', password: 'demo-secret', password_env: '', timeout: 10, verify_tls: true, timezone: 'Asia/Tokyo' },
      { name: names.seoul, enabled: true, base_url: 'http://seoul.example.com:8212', username: 'admin', password: '', password_env: '', timeout: 15, verify_tls: false, timezone: 'Asia/Seoul' },
    ],
    custom_headers: [
      { name: 'CF-Access-Client-Id', value: '', value_env: 'CF_CLIENT_ID', servers: '' },
      { name: 'X-Debug', value: 'on', value_env: '', servers: names.tokyo },
    ],
    group_bindings: [],
    permission_admins: [
      { id: neutralFixtures ? 'operator-01' : 'aiocqhttp:10001', note: neutralFixtures ? 'Primary operator' : '主管理员' },
      { id: neutralFixtures ? 'operator-02' : 'aiocqhttp:10002', note: neutralFixtures ? 'Backup operator' : '副管理员' },
    ],
    command_permissions: [
      { command: 'guild list', enabled: 'inherit', admin_only: 'on' },
      { command: 'world today', enabled: 'off', admin_only: 'inherit' },
      { command: 'rank', enabled: 'on', admin_only: 'inherit' },
    ],
    single_allowed_groups: [],
    routing: { access_mode: 'restricted', world_mode: 'multi', default_server: names.tokyo, setup_confirmed: true },
  }
  return {
    config,
    audits: seedAudits(runtime, names, neutralFixtures),
    // 东京/大阪/首尔有数据 + 两个已从 config 移除但仍有数据的孤儿
    dataServerIds: new Set([names.tokyo, names.osaka, names.seoul, names.retiredA, names.retiredB]),
    groupBindings: [
      { umo: 'demo:Group:100', server_ids: [names.tokyo] },
      { umo: 'demo:Group:200', server_ids: [names.tokyo, names.osaka] },
      { umo: 'demo:Group:300', server_ids: [names.seoul] },
    ],
    statusByName: {
      [names.tokyo]: { ready: true, degraded: false, online: 12, max_players: 32, fps: 58, smoothness: 'smooth', world_day: 47, peak_online_today: 21, basecamp_count: 6 },
      [names.osaka]: { ready: true, degraded: false, online: 4, max_players: 16, fps: 33, smoothness: 'moderate', world_day: 12, peak_online_today: 9, basecamp_count: 2 },
      [names.seoul]: { ready: true, degraded: true, online: 0, max_players: 24, fps: 0, smoothness: 'very_laggy', world_day: 0, peak_online_today: 0, basecamp_count: 0 },
    },
  }
}

function scenarioSingle(runtime: MockRuntime, neutralFixtures = false): Db {
  const serverName = neutralFixtures ? 'Primary-01' : '我的私服'
  const config: RawConfig = {
    ...defaultSections(),
    servers: [
      { name: serverName, enabled: true, base_url: 'http://primary.example.com:8212', username: 'admin', password: '', password_env: 'PAL_HOME_PW', timeout: 10, verify_tls: true, timezone: 'Asia/Tokyo' },
    ],
    custom_headers: [],
    group_bindings: [],
    permission_admins: [{ id: neutralFixtures ? 'operator-01' : 'aiocqhttp:20001', note: neutralFixtures ? 'Primary operator' : '服主' }],
    command_permissions: [{ command: 'server shutdown', enabled: 'inherit', admin_only: 'on' }],
    single_allowed_groups: [
      { umo: 'demo:Group:701', note: neutralFixtures ? 'Primary group' : '核心群' },
      { umo: 'demo:Group:702', note: neutralFixtures ? 'Announcements' : '公告群' },
    ],
    routing: { access_mode: 'restricted', world_mode: 'single', default_server: '', setup_confirmed: true },
  }
  return {
    config,
    audits: seedAudits(runtime, {
      tokyo: serverName,
      osaka: serverName,
      seoul: serverName,
      retiredA: 'Retired-01',
      retiredB: 'Retired-02',
    }, neutralFixtures).slice(0, 2),
    dataServerIds: new Set([serverName]),
    groupBindings: [],
    statusByName: {
      [serverName]: { ready: true, degraded: false, online: 3, max_players: 8, fps: 60, smoothness: 'smooth', world_day: 5, peak_online_today: 5, basecamp_count: 1 },
    },
  }
}

function scenarioFirstSetup(_runtime: MockRuntime, _neutralFixtures = false): Db {
  // setup_confirmed:false → 触发首次引导屏
  const config: RawConfig = {
    ...defaultSections(),
    servers: [], custom_headers: [], group_bindings: [],
    permission_admins: [], command_permissions: [], single_allowed_groups: [],
    routing: { access_mode: 'restricted', world_mode: 'single', default_server: '', setup_confirmed: false },
  }
  return { config, audits: [], dataServerIds: new Set(), groupBindings: [], statusByName: {} }
}

function scenarioAuditEmpty(runtime: MockRuntime, neutralFixtures = false): Db {
  const db = scenarioMulti(runtime, neutralFixtures)
  db.audits = [] // 审计空态
  return db
}

function scenarioEmptyConfig(_runtime: MockRuntime, _neutralFixtures = false): Db {
  // 已确认过模式、但尚未配置任何服务器：看空态表单（多世界）
  const config: RawConfig = {
    ...defaultSections(),
    servers: [], custom_headers: [], group_bindings: [],
    permission_admins: [], command_permissions: [], single_allowed_groups: [],
    routing: { access_mode: 'restricted', world_mode: 'multi', default_server: '', setup_confirmed: true },
  }
  return { config, audits: [], dataServerIds: new Set(), groupBindings: [], statusByName: {} }
}

interface FixtureNames {
  tokyo: string
  osaka: string
  seoul: string
  retiredA: string
  retiredB: string
}

function seedAudits(runtime: MockRuntime, names: FixtureNames, neutralFixtures: boolean): AuditRow[] {
  const t = runtime.nowSec()
  const admin = neutralFixtures ? 'operator-01' : 'demo-admin'
  const target = neutralFixtures ? 'player-01#a1b2c3' : '捣乱玩家#a1b2c3'
  return [
    { ts: t - 120, time: fmtTs(t - 120), action: 'announce', server: names.tokyo, admin, target: '', success: true, error: null },
    { ts: t - 900, time: fmtTs(t - 900), action: 'kick', server: names.osaka, admin, target, success: true, error: null },
    { ts: t - 3600, time: fmtTs(t - 3600), action: 'ban', server: names.seoul, admin, target: '#f0e1d2', success: false, error: 'target_not_found' },
    { ts: t - 7200, time: fmtTs(t - 7200), action: 'save', server: names.tokyo, admin, target: '', success: true, error: null },
  ]
    .concat(
      // 批量历史记录：演示前端分页（每页 50；后端封顶 200 的中间量级）
      Array.from({ length: 116 }, (_, i) => {
        const actions = ['save', 'announce', 'kick', 'unban']
        const servers = [names.tokyo, names.osaka, names.seoul]
        const ts = t - 10800 - i * 5400
        return {
          ts, time: fmtTs(ts), action: actions[i % actions.length], server: servers[i % servers.length],
          admin: i % 5 === 0 ? (neutralFixtures ? 'operator-02' : 'night-op') : admin,
          target: i % 4 === 2
            ? `${neutralFixtures ? 'player' : '玩家'}-${String(i).padStart(2, '0')}#${((i * 2654435761) % 0xffffff).toString(16).padStart(6, '0')}`
            : '',
          success: i % 9 !== 7, error: i % 9 === 7 ? 'timeout' : null,
        }
      }),
    )
}

export interface ScenarioDef {
  label: string
  build: (runtime: MockRuntime, neutralFixtures?: boolean) => Db
}
export const SCENARIOS: Record<string, ScenarioDef> = {
  first: { label: '首次设置', build: scenarioFirstSetup },
  multi: { label: '多服务器', build: scenarioMulti },
  single: { label: '单服务器', build: scenarioSingle },
  auditEmpty: { label: '审计空态', build: scenarioAuditEmpty },
  transferHelper: { label: '切换 helper', build: scenarioMulti }, // 数据同多服务器；main-dev 进场后自动打开切换 helper 供设计预览
  emptyConfig: { label: '无服务器空配置', build: scenarioEmptyConfig },
}
// dev.html 切换小条渲染顺序
export const SCENARIO_ORDER = ['first', 'multi', 'single', 'auditEmpty', 'emptyConfig'] as const

// ---- 装配 bridge ----
export function createMockBridge(scenarioId: string, options: MockBridgeOptions = {}): AstrBotBridge {
  const runtime = createRuntime(options)
  const def = SCENARIOS[scenarioId] ?? SCENARIOS[DEFAULT_SCENARIO]
  const db = def.build(runtime, options.neutralFixtures === true)
  if (options.locale) {
    db.config.world = {
      ...(db.config.world && typeof db.config.world === 'object' && !Array.isArray(db.config.world)
        ? db.config.world as Dict
        : {}),
      locale: options.locale,
    }
  }

  function splitQuery(path: string): { base: string; params: URLSearchParams } {
    const q = path.indexOf('?')
    if (q < 0) return { base: path, params: new URLSearchParams() }
    return { base: path.slice(0, q), params: new URLSearchParams(path.slice(q + 1)) }
  }

  return {
    async ready(): Promise<void> { /* 假 bridge 恒就绪 */ },

    async apiGet(path: string): Promise<unknown> {
      await runtime.delay()
      const { base, params } = splitQuery(path)
      switch (base) {
        case 'config/get':
          return { ok: true, config: redact(db.config), page_version: 1 }
        case 'status/overview':
          return { ok: true, servers: statusRows(db, runtime) }
        case 'audit/list':
          return { ok: true, audits: db.audits.map((r) => ({ ...r })) }
        case 'mode/orphans':
          return { ok: true, orphans: computeOrphans(db) }
        case 'mode/transfer/preview':
          return transferPreview(db, params.get('target') ?? '')
        default:
          return { ok: false, error: 'not_found', detail: { path: base } }
      }
    },

    async apiPost(path: string, body?: unknown): Promise<unknown> {
      await runtime.delay()
      const b = (body && typeof body === 'object' ? body : {}) as Dict
      switch (path) {
        case 'config/save':
          return applySave(db, b, runtime)
        case 'config/locale':
          return applyLocalePatch(db, b, runtime)
        case 'mode/transfer':
          return runTransfer(db, b, runtime)
        case 'mode/orphans/purge':
          return runPurge(db, b, runtime)
        default:
          return { ok: false, error: 'not_found', detail: { path } }
      }
    },
  }
}
