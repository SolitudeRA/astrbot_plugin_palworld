<script setup lang="ts">
import { reactive, ref, onMounted, computed, watchEffect } from 'vue'
import { apiGet, apiPost } from '../lib/bridge'
import { Unauthorized, BusinessError } from '../lib/errors'
import { collectBody, type SettingsState, type CmdPerm } from '../lib/collect'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS, PAL_TREE, type Tri } from '../lib/schema'
import { effEnabled, inheritEnabled, writeAxis } from '../lib/permissions'
import { SwitchRoot, SwitchThumb } from 'reka-ui'
import { CHAPTERS } from '../lib/chapters'
import ServerCard from './ServerCard.vue'
import HeaderCard from './HeaderCard.vue'
import AdminCard from './AdminCard.vue'
import GroupCard from './GroupCard.vue'
import CommandTree from './CommandTree.vue'
import SectionForm from './SectionForm.vue'
import Field from './Field.vue'
import ModeOnboarding from './ModeOnboarding.vue'
import ModeTransfer from './ModeTransfer.vue'
import { locale, setLocale, t, type Locale } from '../lib/i18n'

const props = defineProps<{ chapter: string }>()
// 上抛首次引导态：App.vue 据此隐藏整条左轨（首次未选模时不渲染任何章节索引）。
const emit = defineEmits<{ (e: 'onboarding', value: boolean): void }>()

const phase = ref<'loading' | 'error' | 'ready'>('loading')
const fatalKey = ref('')
const saving = ref(false)
const localePatching = ref(false)
const appliedLocale = ref<Locale>(locale.value)
const notice = reactive<{ msg: string; error: boolean }>({ msg: '', error: false })

const state = reactive<SettingsState>({ servers: [], custom_headers: [], sections: {}, permission_admins: [], command_perms: {}, single_allowed_groups: [] })
const dirty = ref(false)

const chapterMeta = computed(() => CHAPTERS.find((c) => c.id === props.chapter))
const chapterTitle = computed(() => chapterMeta.value ? t(`chapter.${chapterMeta.value.id}.label`) : '')
const currentSections = computed(() => OBJECT_SECTIONS.filter((s) => chapterMeta.value?.blocks?.includes(s.key)))
const isAccess = computed(() => props.chapter === 'access')
const isFeatures = computed(() => props.chapter === 'features')
const isPermissions = computed(() => props.chapter === 'permissions')

// 全部已配置服务器名（含非就绪）——转移向导删除侧摘要用（M = 所有非 surviving 台）
const serverNames = computed(() => state.servers.map((s) => String((s as Record<string, unknown>).name ?? '')))

// 运行模式（single/multi）。兜底 'multi' 为 fail-safe：呈现全部字段、不隐藏不截断；
// applyConfig 已 seed，实践中 world_mode 恒有值，兜底几乎不触发。
const worldMode = computed(() => (state.sections.routing?.world_mode as string) ?? 'multi')
// 授权群名单的显隐跟「已保存」的访问模式走（applyConfig 快照），而非编辑中的下拉值——
// 危险区里改下拉不实时收折名单，保存生效后才带动画收折/展开。
const savedAccessMode = ref('restricted')
const singleRestricted = computed(() => worldMode.value === 'single' && savedAccessMode.value === 'restricted')
// 首次引导：未确认（setup_confirmed !== true）时 ready 相态渲染引导屏取代正常章节。
// 严格 === true 与后端 is True 对齐；缺键 / 非布尔一律视为未确认。
const needsOnboarding = computed(() => state.sections.routing?.setup_confirmed !== true)
// 仅在 ready 相态且未确认时上抛 true → App.vue 隐藏左轨；load 中 / 失败一律 false（左轨照常显示）。
watchEffect(() => emit('onboarding', phase.value === 'ready' && needsOnboarding.value))

// 按模式过滤 routing 段字段：恒隐藏 world_mode/setup_confirmed；access_mode 拆去危险区行；
// single 再隐藏 default_server。仅过滤展示，state.sections.routing 仍保全值，collectBody 照常回传。
// 拆空后段整个剔除（单模式 routing 无可见字段）；多模式剩 default_server，段改名「默认查询」更贴切。
const visibleSections = computed(() => currentSections.value.map((s) => {
  if (s.key !== 'routing') return s
  const hide = new Set<string>(['world_mode', 'setup_confirmed', 'access_mode'])
  if (worldMode.value === 'single') hide.add('default_server')
  return { ...s, fields: s.fields.filter((f) => !hide.has(f.key)) }
}).filter((s) => s.fields.length > 0))
// 排序原则：小参数控件在前，大面积浏览/批量控件在后（危险区恒垫底）。
// 定制章（连接/功能/权限）的表单段 inline 到各自语义位置；tailSections 只服务纯表单章。
const hasCustomLayout = computed(() => isAccess.value || isFeatures.value || isPermissions.value)
const tailSections = computed(() => (hasCustomLayout.value ? [] : visibleSections.value))
// 危险区「访问模式」行：字段规格取自 schema 单一真相源；说明按当前值动态给后果
const ACCESS_MODE_SPEC = OBJECT_SECTIONS.find((s) => s.key === 'routing')!.fields.find((f) => f.key === 'access_mode')!
const accessMode = computed(() => (state.sections.routing?.access_mode as string) ?? 'restricted')
const accessModeDesc = computed(() => accessMode.value === 'open'
  ? t('settings.access_mode.open_desc')
  : t('settings.access_mode.restricted_desc'))

// 功能页危险区：危险命令启停逐条开关（不随整组，F2）；文案给后果说明
const DANGER_CMD_SPECS = [
  { path: 'server kick', key: 'server_kick' },
  { path: 'server unban', key: 'server_unban' },
  { path: 'server ban', key: 'server_ban' },
  { path: 'server shutdown', key: 'server_shutdown' },
  { path: 'server stop', key: 'server_stop' },
] as const
const DANGER_CMDS = computed(() => DANGER_CMD_SPECS.map((d) => ({
  ...d,
  label: t(`settings.danger.command.${d.key}.label`),
  desc: t(`settings.danger.command.${d.key}.desc`),
  node: PAL_TREE.find((n) => n.path === d.path)!,
})))
const DANGER_PATHS = DANGER_CMD_SPECS.map((d) => d.path)
type DangerCmd = (typeof DANGER_CMDS.value)[number]
const dangerOn = (node: DangerCmd['node']) => effEnabled(state.command_perms ?? {}, node)
const dangerOverridden = (path: string) => (state.command_perms ?? {})[path]?.enabled !== undefined && (state.command_perms ?? {})[path]?.enabled !== 'inherit'
function onDangerToggle(d: DangerCmd, target: boolean) {
  const inh = inheritEnabled(state.command_perms ?? {}, d.node) // danger 恒=内置默认（关）
  state.command_perms = writeAxis(state.command_perms ?? {}, d.path, 'enabled', target === inh ? 'inherit' : (target ? 'on' : 'off'))
  dirty.value = true
}

const ERR_CODES = new Set([
  'save_in_progress', 'too_frequent', 'too_large', 'invalid_shape', 'invalid_field',
  'credential_redirect', 'restart_failed_rolled_back', 'restart_failed', 'unauthorized',
])
function errorText(code: string): string {
  return ERR_CODES.has(code) ? t(`err.${code}`) : t('err.save_failed')
}
const mapError = (e: BusinessError) => errorText(e.code) + (e.path ? `${t('punct.colon')}${e.path}` : '')

let localSeq = 0
function emptyRow(fields: typeof SERVER_FIELDS): Record<string, unknown> {
  // __local_key 仅供 v-for :key(collectServer/collectHeader 显式拾取字段,
  // 不会透传给后端):多条未保存新行共用 __row_id='' 时 :key 回退 index,
  // 删中间行会销毁其下正在编辑的卡片(审查 F2)
  const row: Record<string, unknown> = { __row_id: '', __local_key: `local-${++localSeq}` }
  for (const f of fields) row[f.key] = f.default
  return row
}
function pad(n: number) { return n < 10 ? '0' + n : '' + n }

function applyConfig(c: Record<string, any>) {
  dirty.value = false
  state.servers = (c.servers ?? []).map((s: Record<string, unknown>) => ({ ...s }))
  state.custom_headers = (c.custom_headers ?? []).map((h: Record<string, unknown>) => ({ ...h }))
  state.sections = {}
  for (const sec of OBJECT_SECTIONS) state.sections[sec.key] = { ...(c[sec.key] ?? {}) }
  // 后端 world.locale 是界面与机器人消息的共同真相源。旧配置缺键时 setLocale no-op，
  // 保留 main.ts 已按浏览器猜出的初始语言。
  setLocale(state.sections.world?.locale)
  appliedLocale.value = locale.value
  // seed world_mode：防空值被 coerce 成 '' 撞枚举校验；'multi' 为 fail-safe（呈现全字段）
  if (!state.sections.routing) state.sections.routing = {}
  if (!state.sections.routing.world_mode) state.sections.routing.world_mode = 'multi'
  // 落库快照：授权群名单显隐依据（编辑中的下拉值不实时驱动收折）
  savedAccessMode.value = (state.sections.routing.access_mode as string) ?? 'restricted'
  // 单模式表单只渲染 servers[0]：空配置补一台占位（绝不截断已有——仅在 length===0 时补）
  if (worldMode.value === 'single' && state.servers.length === 0) {
    state.servers = [emptyRow(SERVER_FIELDS)]
  }
  // ?? []：空 config / 旧配置缺键时不崩，退化为空名单 / 无命令覆盖
  state.permission_admins = (c.permission_admins ?? []).map((a: Record<string, unknown>) => ({ ...a, __local_key: `local-${++localSeq}` }))
  // 无条件 hydrate（不管当前模式）：由 singleRestricted 只控制显示，collect 恒回传防抹除
  state.single_allowed_groups = (c.single_allowed_groups ?? []).map((g: Record<string, unknown>) => ({ ...g, __local_key: `local-${++localSeq}` }))
  // 命令权限行 → 稀疏树 state（保 config 行序；缺轴退化 inherit；忽略非法/空 command）
  const perms: Record<string, CmdPerm> = {}
  for (const row of (c.command_permissions ?? []) as Record<string, unknown>[]) {
    const command = String(row?.command ?? '')
    if (!command) continue
    perms[command] = {
      enabled: (row.enabled as Tri) ?? 'inherit',
      admin_only: (row.admin_only as Tri) ?? 'inherit',
    }
  }
  state.command_perms = perms
}

// 转移完成：按后端回传 config 重水化（孤儿清理已随切换 helper 完成步处理）
function onTransferApplied(c: Record<string, unknown>) {
  applyConfig(c)
}

function emptyAdmin(): Record<string, unknown> {
  return { __row_id: '', __local_key: `local-${++localSeq}`, id: '', note: '' }
}

function emptyGroup(): Record<string, unknown> {
  return { __row_id: '', __local_key: `local-${++localSeq}`, umo: '', note: '' }
}

async function load() {
  phase.value = 'loading'
  try {
    const r = await apiGet<{ config: Record<string, any> }>('config/get')
    applyConfig(r.config)
    phase.value = 'ready'
  } catch (e) {
    fatalKey.value = e instanceof Unauthorized ? 'err.unauthorized' : 'settings.load_error'
    phase.value = 'error'
  }
}
onMounted(load)

function toast(msg: string, error = false) {
  notice.msg = msg; notice.error = error
  // 错误提示多为引导性(如 credential_redirect),停留更久
  setTimeout(() => { if (notice.msg === msg) { notice.msg = ''; notice.error = false } }, error ? 6000 : 3000)
}

// 引导屏确认：写所选模式 + setup_confirmed=true，await 保存。落库后 GET 回传 setup_confirmed:true
// → needsOnboarding 翻假 → 转正常章节；同时后端命令闸清（Task 2）。
// 保存失败（未鉴权/会话过期/瞬时 RequestFailed/restart_failed_rolled_back）时还原 setup_confirmed，
// 令引导屏复现，防前端「已确认」而后端仍 setup_confirmed=false 的写侧半态死锁（spec §8）。
async function onConfirmMode(value: { locale: Locale; mode: 'single' | 'multi' }) {
  if (!state.sections.world) state.sections.world = {}
  if (!state.sections.routing) state.sections.routing = {}
  setLocale(value.locale)
  state.sections.world.locale = value.locale
  state.sections.routing.world_mode = value.mode
  state.sections.routing.setup_confirmed = true
  const ok = await save()
  if (ok) appliedLocale.value = value.locale
  else state.sections.routing.setup_confirmed = false  // 保存失败→还原，引导屏复现
}

const localeChangeDisabled = computed(() => saving.value || localePatching.value)

// 顶栏语言切换只提交 locale-only patch，避免把 SettingsPanel 内尚未保存的草稿夹带进全量保存。
// UI 先乐观切换；任何业务/网络失败都回到最后一次后端已应用的 locale。
async function setLocaleAndPersist(value: Locale): Promise<boolean> {
  if (localeChangeDisabled.value) return false
  const previous = appliedLocale.value
  setLocale(value)
  localePatching.value = true
  notice.msg = ''; notice.error = false
  try {
    await apiPost('config/locale', { locale: value })
    if (!state.sections.world) state.sections.world = {}
    state.sections.world.locale = value
    appliedLocale.value = value
    return true
  } catch (e) {
    setLocale(previous)
    if (!state.sections.world) state.sections.world = {}
    state.sections.world.locale = previous
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast(t('err.unauthorized'), true)
    else toast(t('err.locale_update_failed'), true)
    return false
  } finally {
    localePatching.value = false
  }
}

async function save(): Promise<boolean> {
  if (saving.value) return false
  saving.value = true; notice.msg = ''; notice.error = false
  try {
    const res = await apiPost<{ ok: boolean; warnings?: Record<string, unknown[]>; config?: Record<string, any> }>('config/save', collectBody(state))
    // 用落库后的脱敏配置刷新 state:新行拿到服务端 __row_id 与 password_set,
    // 否则该行再次编辑时留空密码会被当「新行空密码」提交,清掉已存密码(审查 F1)。
    // 已知取舍:重填会重建全部卡片,其他正在编辑未保存的卡片草稿以落库数据为准丢弃
    if (res.config) applyConfig(res.config)
    else dirty.value = false
    const w = res.warnings ?? {}
    const skips = [...((w.skipped_servers as unknown[]) ?? []), ...((w.skipped_headers as unknown[]) ?? [])]
    if (skips.length) toast(t('settings.saved_skipped', { n: skips.length }))
    else toast(t('settings.saved_applied'))
    return true
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast(t('err.unauthorized'), true)
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? t('err.reserved_sentinel') : t('err.save_failed_retry'), true)
    else toast(t('err.save_failed_retry'), true)
    return false
  } finally {
    saving.value = false
  }
}

defineExpose({ state, setLocaleAndPersist, localeChangeDisabled })
</script>

<template>
  <div class="pw-settings">
    <p v-if="phase === 'loading'" class="pw-muted">{{ t('settings.loading') }}</p>
    <div v-else-if="phase === 'error'" class="pw-fatal">{{ t(fatalKey) }}<button class="pw-primary" @click="load">{{ t('app.retry') }}</button></div>
    <template v-else>
      <ModeOnboarding v-if="needsOnboarding" @confirm="onConfirmMode" />
      <template v-else>
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
        <span v-if="!isAccess" class="mode-badge">{{ t('settings.mode_badge', { mode: t(`settings.mode.${worldMode}`) }) }}</span>
      </div>

      <template v-if="isAccess">
        <section>
          <div class="group-head"><span class="t">{{ t('settings.servers.title') }}</span><span class="c">{{ worldMode === 'single' ? t('settings.servers.single_desc') : t('settings.servers.multi_desc') }}</span></div>
          <template v-if="worldMode === 'multi'">
            <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || (s.__local_key as string)" :model-value="s" :index-label="t('settings.servers.index', { index: pad(i + 1) })"
              @update:model-value="(v) => { state.servers[i] = v; dirty = true }" @delete="state.servers.splice(i, 1); dirty = true" />
            <button class="add" @click="state.servers.push(emptyRow(SERVER_FIELDS)); dirty = true">{{ t('settings.servers.add') }}</button>
          </template>
          <!-- 单模式：只编辑 servers[0]（不显示增删），多余的服务器保留在 state 里原样回传（绝不截断）。
               v-else-if 空守卫：seed + phase 门已保证渲染时 servers[0] 存在，此处再兜一层防空窗崩 -->
          <ServerCard v-else-if="state.servers[0]" :key="(state.servers[0].__row_id as string) || (state.servers[0].__local_key as string)"
            :model-value="state.servers[0]" :index-label="t('settings.servers.title')" :hide-delete="true"
            @update:model-value="(v) => { state.servers[0] = v; dirty = true }" @delete="() => {}" />
        </section>
        <SectionForm v-for="sec in visibleSections" :key="'inline-' + sec.key" :section="sec"
          :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />
        <section>
          <div class="group-head"><span class="t">{{ t('settings.headers.title') }}</span><span class="c">{{ t('settings.headers.subtitle') }}</span></div>
          <p class="grouphint">{{ t('settings.headers.hint') }}</p>
          <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || (h.__local_key as string)" :model-value="h" :index-label="t('settings.headers.index', { index: pad(i + 1) })"
            @update:model-value="(v) => { state.custom_headers[i] = v; dirty = true }" @delete="state.custom_headers.splice(i, 1); dirty = true" />
          <button class="add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS)); dirty = true">{{ t('settings.headers.add') }}</button>
        </section>
        <Transition name="collapse">
          <section v-if="singleRestricted">
            <div class="collapse-inner">
              <div class="group-head"><span class="t">{{ t('settings.groups.title') }}</span><span class="c">{{ t('settings.groups.subtitle') }}</span></div>
              <p class="grouphint">{{ t('settings.groups.hint') }}</p>
              <GroupCard v-for="(g, i) in state.single_allowed_groups" :key="(g.__row_id as string) || (g.__local_key as string)" :model-value="g" :index-label="t('settings.groups.index', { index: pad(i + 1) })"
                @update:model-value="(v) => { state.single_allowed_groups![i] = v; dirty = true }" @delete="state.single_allowed_groups!.splice(i, 1); dirty = true" />
              <button class="add" @click="state.single_allowed_groups!.push(emptyGroup()); dirty = true">{{ t('settings.groups.add') }}</button>
            </div>
          </section>
        </Transition>
        <!-- 危险区垫底：影响重大的操作集中于红框容器（模式切换恒在；残留清理有孤儿才现行） -->
        <section>
          <div class="group-head"><span class="t t-danger">{{ t('settings.danger.title') }}</span><span class="c">{{ t('settings.danger.general_desc') }}</span></div>
          <div class="danger-zone">
            <div class="dz-item">
              <div class="dz-info">
                <span class="dz-title">{{ t('field.routing.access_mode.label') }}</span>
                <span class="dz-desc">{{ accessModeDesc }}<b v-if="accessMode !== savedAccessMode" class="dz-pending">{{ t('settings.pending_after_save') }}</b></span>
              </div>
              <Field :spec="ACCESS_MODE_SPEC" section="routing" :model-value="state.sections.routing?.access_mode ?? 'restricted'"
                @update:model-value="(v) => { state.sections.routing.access_mode = v; dirty = true }" />
            </div>
            <!-- 残留数据清理不再常驻：孤儿由切换 helper 的完成步负责（切换才产生孤儿） -->
            <ModeTransfer :world-mode="worldMode" :dirty="dirty" :server-names="serverNames"
              @applied="onTransferApplied" @notify="(m, e) => toast(m, e)" />
          </div>
        </section>
      </template>

      <template v-if="isFeatures">
        <!-- 小参数段前置（玩家查询参数），大面积功能树垫底 -->
        <SectionForm v-for="sec in visibleSections" :key="'inline-' + sec.key" :section="sec"
          :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />
        <section>
          <div class="group-head"><span class="t">{{ t('settings.features.title') }}</span><span class="c">{{ t('settings.features.subtitle') }}</span></div>
          <p class="grouphint">{{ t('settings.features.hint') }}</p>
          <CommandTree axis="enabled" :hide-paths="DANGER_PATHS" :model-value="state.command_perms ?? {}"
            @update:model-value="(v) => { state.command_perms = v }" @change="dirty = true" />
        </section>
        <!-- 危险区垫底：危险命令不随整组开关，须在此逐条开启 -->
        <section>
          <div class="group-head"><span class="t t-danger">{{ t('settings.danger.title') }}</span><span class="c">{{ t('settings.danger.commands_desc') }}</span></div>
          <div class="danger-zone">
            <div v-for="d in DANGER_CMDS" :key="d.path" class="dz-item">
              <div class="dz-info">
                <span class="dz-title">{{ d.label }}<span class="dz-path mono">/pal {{ d.path }}</span></span>
                <span class="dz-desc">{{ d.desc }}</span>
              </div>
              <SwitchRoot class="pw-switch sm" :class="{ ovr: dangerOverridden(d.path) }"
                :model-value="dangerOn(d.node)" :aria-label="t('common.enable_aria', { label: d.label })"
                @update:model-value="(v: boolean) => onDangerToggle(d, v)">
                <SwitchThumb class="pw-switch-thumb" />
              </SwitchRoot>
            </div>
          </div>
        </section>
      </template>

      <template v-if="isPermissions">
        <div class="callout">
          <p class="callout-t">{{ t('settings.permissions.callout_title') }}</p>
          <p>{{ t('settings.permissions.callout_intro') }}<b>{{ t('settings.permissions.admin_list_term') }}</b>{{ t('settings.permissions.callout_after_admin') }}<b>{{ t('settings.permissions.locked_commands_term') }}</b>{{ t('settings.permissions.callout_after_commands') }}</p>
          <p class="callout-warn">{{ t('settings.permissions.callout_warn') }}</p>
        </div>
        <section>
          <div class="group-head"><span class="t">{{ t('settings.admins.title') }}</span><span class="c">{{ t('settings.admins.subtitle') }}</span></div>
          <p v-if="!(state.permission_admins ?? []).length" class="grouphint">{{ t('settings.admins.empty') }}</p>
          <AdminCard v-for="(a, i) in state.permission_admins" :key="(a.__row_id as string) || (a.__local_key as string)" :model-value="a" :index-label="t('settings.admins.index', { index: pad(i + 1) })"
            @update:model-value="(v) => { state.permission_admins![i] = v; dirty = true }" @delete="state.permission_admins!.splice(i, 1); dirty = true" />
          <button class="add" @click="state.permission_admins!.push(emptyAdmin()); dirty = true">{{ t('settings.admins.add') }}</button>
        </section>
        <!-- 小参数段前置（服务器管控：二次确认/审计留存），大面积限制树垫底 -->
        <SectionForm v-for="sec in visibleSections" :key="'inline-' + sec.key" :section="sec"
          :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />
        <section>
          <div class="group-head"><span class="t">{{ t('settings.command_permissions.title') }}</span><span class="c">{{ t('settings.command_permissions.subtitle') }}</span></div>
          <p class="grouphint">{{ t('settings.command_permissions.hint') }}</p>
          <CommandTree axis="admin_only" :model-value="state.command_perms ?? {}" :hide-groups="worldMode === 'single' ? ['link'] : []"
            @update:model-value="(v) => { state.command_perms = v }" @change="dirty = true" />
        </section>
      </template>

      <SectionForm v-for="sec in tailSections" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />

      <div class="savebar">
        <button class="commit pw-save" :disabled="saving" @click="() => save()">{{ saving ? t('settings.saving') : t('settings.save') }}</button>
        <span v-if="notice.msg" :class="notice.error ? 'pw-error' : 'receipt'">{{ notice.msg }}</span>
        <span v-else-if="dirty" class="unsaved">{{ t('settings.unsaved') }}</span>
        <span class="note">{{ t('settings.save_note') }}</span>
      </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
/* 只读模式标识：仿 muted chip，靠右贴于章标题；窄屏允许换行避免溢出 */
.chapter-head { flex-wrap: wrap; row-gap: var(--space-2); }
.mode-badge { margin-left: auto; align-self: center; font-size: var(--fs-caption); color: var(--ink-2); background: color-mix(in srgb, var(--focus) 6%, var(--card)); border: 1px solid var(--rule); border-radius: var(--r); padding: var(--space-1) var(--space-3); white-space: nowrap; }
.callout { background: color-mix(in srgb, var(--focus) 7%, var(--card)); border: 1px solid color-mix(in srgb, var(--focus) 30%, var(--rule)); border-left: 3px solid var(--focus); border-radius: var(--r); padding: var(--space-3) var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
.callout p { margin: 0; font-size: var(--fs-caption); color: var(--ink-2); line-height: var(--lh-base); }
.callout p b { color: var(--ink); font-weight: var(--fw-semibold); }
.callout .callout-t { font-size: var(--fs-sm); font-weight: var(--fw-semibold); color: var(--ink); }
.callout .callout-warn { color: var(--warn); }
.dz-path { margin-left: var(--space-2); font-size: var(--fs-caption); color: var(--ink-3); font-weight: var(--fw-regular); }
.pw-switch.ovr { box-shadow: 0 0 0 2px var(--override); }
/* 访问模式改动未保存时的生效提示 */
.dz-pending { color: var(--warn); font-weight: var(--fw-medium); }
/* 授权群名单收折动画：grid-rows 0fr↔1fr + 淡出；reduced-motion 由全局豁免 */
.collapse-enter-active, .collapse-leave-active { display: grid; transition: grid-template-rows var(--motion-slow) var(--ease-out), opacity var(--motion-slow) var(--ease-out); }
.collapse-enter-from, .collapse-leave-to { grid-template-rows: 0fr; opacity: 0; }
.collapse-enter-to, .collapse-leave-from { grid-template-rows: 1fr; opacity: 1; }
.collapse-inner { overflow: hidden; min-height: 0; }
</style>
