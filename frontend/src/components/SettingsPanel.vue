<script setup lang="ts">
import { reactive, ref, onMounted, computed } from 'vue'
import { apiGet, apiPost } from '../lib/bridge'
import { Unauthorized, BusinessError } from '../lib/errors'
import { collectBody, type SettingsState, type CmdPerm } from '../lib/collect'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS, type Tri } from '../lib/schema'
import { CHAPTERS } from '../lib/chapters'
import ServerCard from './ServerCard.vue'
import HeaderCard from './HeaderCard.vue'
import AdminCard from './AdminCard.vue'
import GroupCard from './GroupCard.vue'
import CommandTree from './CommandTree.vue'
import SectionForm from './SectionForm.vue'

const props = defineProps<{ chapter: string }>()

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
const isPermissions = computed(() => props.chapter === 'permissions')

// 运行模式（single/multi）。兜底 'multi' 为 fail-safe：呈现全部字段、不隐藏不截断；
// applyConfig 已 seed，实践中 world_mode 恒有值，兜底几乎不触发。
const worldMode = computed(() => (state.sections.routing?.world_mode as string) ?? 'multi')
const singleRestricted = computed(() =>
  worldMode.value === 'single' && ((state.sections.routing?.access_mode as string) ?? 'restricted') === 'restricted')
// 按模式过滤 routing 段字段：页面无模式开关 → 恒隐藏 world_mode；single 再隐藏 default_server。
// 仅过滤展示，state.sections.routing 仍保全值，collectBody 照常回传（不丢 world_mode）。
const visibleSections = computed(() => currentSections.value.map((s) => {
  if (s.key !== 'routing') return s
  const hide = new Set<string>(['world_mode'])
  if (worldMode.value === 'single') hide.add('default_server')
  return { ...s, fields: s.fields.filter((f) => !hide.has(f.key)) }
}))

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

async function save() {
  if (saving.value) return
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
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast('未登录或登录已过期，请重新登录 Dashboard', true)
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败，请重试', true)
    else toast('保存失败，请重试', true)
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
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
        <span class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }} · 切换请到插件齿轮配置</span>
      </div>

      <template v-if="isAccess">
        <section>
          <div class="group-head"><span class="t">服务器</span><span class="c">要监测的 Palworld 服务器</span></div>
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
        <section>
          <div class="group-head"><span class="t">自定义请求头</span><span class="c">每次请求都会带上</span></div>
          <p class="grouphint">含凭证的请求头建议填写「限定服务器」。留空会发给所有服务器，包括以后新增的。</p>
          <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || (h.__local_key as string)" :model-value="h" :index-label="'请求头 ' + pad(i + 1)"
            @update:model-value="(v) => { state.custom_headers[i] = v; dirty = true }" @delete="state.custom_headers.splice(i, 1); dirty = true" />
          <button class="add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS)); dirty = true">＋ 添加请求头</button>
        </section>
        <section v-if="singleRestricted">
          <div class="group-head"><span class="t">授权群名单</span><span class="c">单世界受限模式下，仅这些会话可查询服务器</span></div>
          <p class="grouphint">群里发 /pal whereami 获取群标识后填入。名单为空 = 当前无人可查询。</p>
          <GroupCard v-for="(g, i) in state.single_allowed_groups" :key="(g.__row_id as string) || (g.__local_key as string)" :model-value="g" :index-label="'授权群 ' + pad(i + 1)"
            @update:model-value="(v) => { state.single_allowed_groups![i] = v; dirty = true }" @delete="state.single_allowed_groups!.splice(i, 1); dirty = true" />
          <button class="add" @click="state.single_allowed_groups!.push(emptyGroup()); dirty = true">＋ 添加授权群</button>
        </section>
      </template>

      <template v-if="isPermissions">
        <div class="callout">
          <p class="callout-t">两层权限模型</p>
          <p>管理员命令的准入由两层共同决定：<b>受托名单</b>决定「谁是管理员」，<b>锁定命令</b>决定「哪些命令只有管理员能用」。未锁定的命令所有群成员都能用。</p>
          <p class="callout-warn">名册全局：加入者在其所在每个群都有管理员权，含对任意群 server add/remove；多群共用同一 bot 请谨慎。</p>
        </div>
        <section>
          <div class="group-head"><span class="t">受托名单</span><span class="c">名单内成员可执行下方锁定的命令</span></div>
          <p v-if="!(state.permission_admins ?? []).length" class="grouphint">名单为空 → 群里暂无人可执行管理员命令</p>
          <AdminCard v-for="(a, i) in state.permission_admins" :key="(a.__row_id as string) || (a.__local_key as string)" :model-value="a" :index-label="'受托 ' + pad(i + 1)"
            @update:model-value="(v) => { state.permission_admins![i] = v; dirty = true }" @delete="state.permission_admins!.splice(i, 1); dirty = true" />
          <button class="add" @click="state.permission_admins!.push(emptyAdmin()); dirty = true">＋ 添加受托成员</button>
        </section>
        <section>
          <div class="group-head"><span class="t">命令权限</span><span class="c">逐条 / 按组设置命令的启用与仅管理员</span></div>
          <p class="grouphint">未覆盖（默认）的命令按内置规则处理。写操作 / 授权类命令内置仅管理员、核心命令内置常开，均不可改。</p>
          <CommandTree :model-value="state.command_perms ?? {}" :hide-groups="worldMode === 'single' ? ['link'] : []"
            @update:model-value="(v) => { state.command_perms = v }" @change="dirty = true" />
        </section>
      </template>

      <SectionForm v-for="sec in visibleSections" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => { state.sections[sec.key] = v; dirty = true }" />

      <div class="savebar">
        <button class="commit pw-save" :disabled="saving" @click="() => save()">{{ saving ? '保存中…' : '保存设置' }}</button>
        <span v-if="notice.msg" :class="notice.error ? 'pw-error' : 'receipt'">{{ notice.msg }}</span>
        <span v-else-if="dirty" class="unsaved">有未保存的更改</span>
        <span class="note">所有修改（含服务器、请求头）都用这里统一保存</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 只读模式标识：仿 muted chip，靠右贴于章标题；窄屏允许换行避免溢出 */
.chapter-head { flex-wrap: wrap; row-gap: 6px; }
.mode-badge { margin-left: auto; align-self: center; font-size: 11.5px; color: var(--ink-2); background: color-mix(in srgb, var(--focus) 6%, var(--card)); border: 1px solid var(--rule); border-radius: var(--r); padding: 4px 10px; white-space: nowrap; }
.callout { background: color-mix(in srgb, var(--focus) 7%, var(--card)); border: 1px solid color-mix(in srgb, var(--focus) 30%, var(--rule)); border-left: 3px solid var(--focus); border-radius: var(--r); padding: 13px 16px; display: flex; flex-direction: column; gap: 6px; }
.callout p { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.55; }
.callout p b { color: var(--ink); font-weight: 600; }
.callout .callout-t { font-size: 13.5px; font-weight: 600; color: var(--ink); }
.callout .callout-warn { color: var(--warn); }
</style>
