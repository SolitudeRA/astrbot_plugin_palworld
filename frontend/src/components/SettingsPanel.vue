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

const props = defineProps<{ chapter: string }>()
// 上抛首次引导态：App.vue 据此隐藏整条左轨（首次未选模时不渲染任何章节索引）。
const emit = defineEmits<{ (e: 'onboarding', value: boolean): void }>()

const phase = ref<'loading' | 'error' | 'ready'>('loading')
const fatalMsg = ref('')
const saving = ref(false)
const notice = reactive<{ msg: string; error: boolean }>({ msg: '', error: false })

const state = reactive<SettingsState>({ servers: [], custom_headers: [], sections: {}, permission_admins: [], command_perms: {}, single_allowed_groups: [] })
const dirty = ref(false)

const chapterMeta = computed(() => CHAPTERS.find((c) => c.id === props.chapter))
const chapterTitle = computed(() => chapterMeta.value?.label ?? '')
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
  return { ...s, title: '默认查询', subtitle: '群里没指定、也没绑定时查询哪台服务器', fields: s.fields.filter((f) => !hide.has(f.key)) }
}).filter((s) => s.fields.length > 0))
// 排序原则：小参数控件在前，大面积浏览/批量控件在后（危险区恒垫底）。
// 定制章（连接/功能/权限）的表单段 inline 到各自语义位置；tailSections 只服务纯表单章。
const hasCustomLayout = computed(() => isAccess.value || isFeatures.value || isPermissions.value)
const tailSections = computed(() => (hasCustomLayout.value ? [] : visibleSections.value))
// 危险区「访问模式」行：字段规格取自 schema 单一真相源；说明按当前值动态给后果
const ACCESS_MODE_SPEC = OBJECT_SECTIONS.find((s) => s.key === 'routing')!.fields.find((f) => f.key === 'access_mode')!
const accessMode = computed(() => (state.sections.routing?.access_mode as string) ?? 'restricted')
const accessModeDesc = computed(() => accessMode.value === 'open'
  ? '完全开放：所有群（含以后新增的）都可查询服务器'
  : '受限授权：仅授权名单内的群可查询')

// 功能页危险区：危险命令启停逐条开关（不随整组，F2）；文案给后果说明
const DANGER_CMDS = [
  { path: 'server kick', label: '踢出玩家', desc: '将在线玩家踢出服务器（写操作，仅管理员可用）' },
  { path: 'server unban', label: '解封玩家', desc: '将玩家移出封禁名单（写操作，仅管理员可用）' },
  { path: 'server ban', label: '封禁玩家', desc: '将玩家加入服务器封禁名单（写操作，仅管理员可用）' },
  { path: 'server shutdown', label: '倒计时关服', desc: '按秒数倒计时关闭服务器（写操作，仅管理员可用）' },
  { path: 'server stop', label: '立即停止', desc: '立刻停止服务器进程（写操作，仅管理员可用）' },
].map((d) => ({ ...d, node: PAL_TREE.find((n) => n.path === d.path)! }))
const DANGER_PATHS = DANGER_CMDS.map((d) => d.path)
const dangerOn = (node: (typeof DANGER_CMDS)[number]['node']) => effEnabled(state.command_perms ?? {}, node)
const dangerOverridden = (path: string) => (state.command_perms ?? {})[path]?.enabled !== undefined && (state.command_perms ?? {})[path]?.enabled !== 'inherit'
function onDangerToggle(d: (typeof DANGER_CMDS)[number], target: boolean) {
  const inh = inheritEnabled(state.command_perms ?? {}, d.node) // danger 恒=内置默认（关）
  state.command_perms = writeAxis(state.command_perms ?? {}, d.path, 'enabled', target === inh ? 'inherit' : (target ? 'on' : 'off'))
  dirty.value = true
}

const ERR: Record<string, string> = {
  save_in_progress: '保存进行中，请稍候', too_frequent: '保存过于频繁，请稍后再试',
  too_large: '配置内容过大，请精简后再保存', invalid_shape: '配置格式有误，请刷新页面后重试',
  invalid_field: '字段填写有误',
  credential_redirect: '修改了服务器地址，请点击该服务器的「修改」重新输入密码后再保存',
  restart_failed_rolled_back: '保存未生效，已恢复原配置',
  restart_failed: '保存未生效且恢复失败，请检查后台日志',
  unauthorized: '未登录或登录已过期，请重新登录 Dashboard',
}
const mapError = (e: BusinessError) => (ERR[e.code] ?? '保存失败') + (e.path ? `：${e.path}` : '')

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
    fatalMsg.value = e instanceof Unauthorized ? '未登录或登录已过期，请重新登录 Dashboard' : '读取配置失败，请重试'
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
async function onConfirmMode(mode: 'single' | 'multi') {
  if (!state.sections.routing) state.sections.routing = {}
  state.sections.routing.world_mode = mode
  state.sections.routing.setup_confirmed = true
  const ok = await save()
  if (!ok) state.sections.routing.setup_confirmed = false  // 保存失败→还原，引导屏复现
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
    if (skips.length) toast(`已保存，${skips.length} 条无效条目未生效`)
    else toast('已保存，已生效')
    return true
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast('未登录或登录已过期，请重新登录 Dashboard', true)
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败，请重试', true)
    else toast('保存失败，请重试', true)
    return false
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="pw-settings">
    <p v-if="phase === 'loading'" class="pw-muted">加载中…</p>
    <div v-else-if="phase === 'error'" class="pw-fatal">{{ fatalMsg }}<button class="pw-primary" @click="load">重试</button></div>
    <template v-else>
      <ModeOnboarding v-if="needsOnboarding" @confirm="onConfirmMode" />
      <template v-else>
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
        <span v-if="!isAccess" class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }}</span>
      </div>

      <template v-if="isAccess">
        <section>
          <div class="group-head"><span class="t">服务器</span><span class="c">{{ worldMode === 'single' ? '当前监测的唯一服务器' : '要监测的 Palworld 服务器' }}</span></div>
          <template v-if="worldMode === 'multi'">
            <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || (s.__local_key as string)" :model-value="s" :index-label="'服务器 ' + pad(i + 1)"
              @update:model-value="(v) => { state.servers[i] = v; dirty = true }" @delete="state.servers.splice(i, 1); dirty = true" />
            <button class="add" @click="state.servers.push(emptyRow(SERVER_FIELDS)); dirty = true">＋ 添加服务器</button>
          </template>
          <!-- 单模式：只编辑 servers[0]（不显示增删），多余的服务器保留在 state 里原样回传（绝不截断）。
               v-else-if 空守卫：seed + phase 门已保证渲染时 servers[0] 存在，此处再兜一层防空窗崩 -->
          <ServerCard v-else-if="state.servers[0]" :key="(state.servers[0].__row_id as string) || (state.servers[0].__local_key as string)"
            :model-value="state.servers[0]" :index-label="'服务器'" :hide-delete="true"
            @update:model-value="(v) => { state.servers[0] = v; dirty = true }" @delete="() => {}" />
        </section>
        <SectionForm v-for="sec in visibleSections" :key="'inline-' + sec.key" :section="sec"
          :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />
        <section>
          <div class="group-head"><span class="t">自定义请求头</span><span class="c">每次请求都会带上</span></div>
          <p class="grouphint">含凭证的请求头建议填写「限定服务器」。留空会发给所有服务器，包括以后新增的。</p>
          <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || (h.__local_key as string)" :model-value="h" :index-label="'请求头 ' + pad(i + 1)"
            @update:model-value="(v) => { state.custom_headers[i] = v; dirty = true }" @delete="state.custom_headers.splice(i, 1); dirty = true" />
          <button class="add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS)); dirty = true">＋ 添加请求头</button>
        </section>
        <Transition name="collapse">
          <section v-if="singleRestricted">
            <div class="collapse-inner">
              <div class="group-head"><span class="t">授权群名单</span><span class="c">「受限授权」模式下，仅名单内的群可查询服务器</span></div>
              <p class="grouphint">群里发 /pal whereami 获取群标识后填入。名单为空 = 当前无人可查询。</p>
              <GroupCard v-for="(g, i) in state.single_allowed_groups" :key="(g.__row_id as string) || (g.__local_key as string)" :model-value="g" :index-label="'授权群 ' + pad(i + 1)"
                @update:model-value="(v) => { state.single_allowed_groups![i] = v; dirty = true }" @delete="state.single_allowed_groups!.splice(i, 1); dirty = true" />
              <button class="add" @click="state.single_allowed_groups!.push(emptyGroup()); dirty = true">＋ 添加授权群</button>
            </div>
          </section>
        </Transition>
        <!-- 危险区垫底：影响重大的操作集中于红框容器（模式切换恒在；残留清理有孤儿才现行） -->
        <section>
          <div class="group-head"><span class="t t-danger">危险区</span><span class="c">影响重大的操作集中在这里，请谨慎</span></div>
          <div class="danger-zone">
            <div class="dz-item">
              <div class="dz-info">
                <span class="dz-title">访问模式</span>
                <span class="dz-desc">{{ accessModeDesc }}<b v-if="accessMode !== savedAccessMode" class="dz-pending">（保存后生效）</b></span>
              </div>
              <Field :spec="ACCESS_MODE_SPEC" :model-value="state.sections.routing?.access_mode ?? 'restricted'"
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
          <div class="group-head"><span class="t">功能开关</span><span class="c">按组批量或逐条设置命令的启停</span></div>
          <p class="grouphint">开 = 可用，关 = 停用。谁能使用哪些命令，在「权限」页设置；危险命令不随整组开关，需逐条开启。</p>
          <CommandTree axis="enabled" :hide-paths="DANGER_PATHS" :model-value="state.command_perms ?? {}"
            @update:model-value="(v) => { state.command_perms = v }" @change="dirty = true" />
        </section>
        <!-- 危险区垫底：危险命令不随整组开关，须在此逐条开启 -->
        <section>
          <div class="group-head"><span class="t t-danger">危险区</span><span class="c">写操作命令集中管理；封禁 / 关服 / 停止不随整组开关</span></div>
          <div class="danger-zone">
            <div v-for="d in DANGER_CMDS" :key="d.path" class="dz-item">
              <div class="dz-info">
                <span class="dz-title">{{ d.label }}<span class="dz-path mono">/pal {{ d.path }}</span></span>
                <span class="dz-desc">{{ d.desc }}</span>
              </div>
              <SwitchRoot class="pw-switch sm" :class="{ ovr: dangerOverridden(d.path) }"
                :model-value="dangerOn(d.node)" :aria-label="d.label + ' 启用'"
                @update:model-value="(v: boolean) => onDangerToggle(d, v)">
                <SwitchThumb class="pw-switch-thumb" />
              </SwitchRoot>
            </div>
          </div>
        </section>
      </template>

      <template v-if="isPermissions">
        <div class="callout">
          <p class="callout-t">两层权限模型</p>
          <p>管理员命令的准入由两层共同决定：<b>管理员名单</b>决定谁有管理员身份，<b>锁定命令</b>决定哪些命令只有管理员能用。未锁定的命令所有群成员都能用。</p>
          <p class="callout-warn">名册全局：加入者在其所在每个群都有管理员权，含对任意群 server add/remove；多群共用同一 bot 请谨慎。</p>
        </div>
        <section>
          <div class="group-head"><span class="t">管理员名单</span><span class="c">名单内成员可执行下方锁定的命令</span></div>
          <p v-if="!(state.permission_admins ?? []).length" class="grouphint">名单为空 → 群里暂无人可执行管理员命令</p>
          <AdminCard v-for="(a, i) in state.permission_admins" :key="(a.__row_id as string) || (a.__local_key as string)" :model-value="a" :index-label="'管理员 ' + pad(i + 1)"
            @update:model-value="(v) => { state.permission_admins![i] = v; dirty = true }" @delete="state.permission_admins!.splice(i, 1); dirty = true" />
          <button class="add" @click="state.permission_admins!.push(emptyAdmin()); dirty = true">＋ 添加管理员</button>
        </section>
        <!-- 小参数段前置（服务器管控：二次确认/审计留存），大面积限制树垫底 -->
        <SectionForm v-for="sec in visibleSections" :key="'inline-' + sec.key" :section="sec"
          :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />
        <section>
          <div class="group-head"><span class="t">命令权限</span><span class="c">按组或逐条设置哪些命令仅管理员可用</span></div>
          <p class="grouphint">开 = 仅管理员可用，关 = 所有人可用。只列出当前启用的命令；功能的启停在「功能」页设置。</p>
          <CommandTree axis="admin_only" :model-value="state.command_perms ?? {}" :hide-groups="worldMode === 'single' ? ['link'] : []"
            @update:model-value="(v) => { state.command_perms = v }" @change="dirty = true" />
        </section>
      </template>

      <SectionForm v-for="sec in tailSections" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />

      <div class="savebar">
        <button class="commit pw-save" :disabled="saving" @click="() => save()">{{ saving ? '保存中…' : '保存设置' }}</button>
        <span v-if="notice.msg" :class="notice.error ? 'pw-error' : 'receipt'">{{ notice.msg }}</span>
        <span v-else-if="dirty" class="unsaved">有未保存的更改</span>
        <span class="note">所有修改（含服务器、请求头）都用这里统一保存</span>
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
