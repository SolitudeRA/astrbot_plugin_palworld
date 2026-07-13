<script setup lang="ts">
import { reactive, ref, onMounted, computed } from 'vue'
import { apiGet, apiPost } from '../lib/bridge'
import { Unauthorized, BusinessError } from '../lib/errors'
import { collectBody, type SettingsState } from '../lib/collect'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS } from '../lib/schema'
import { CHAPTERS } from '../lib/chapters'
import ServerCard from './ServerCard.vue'
import HeaderCard from './HeaderCard.vue'
import SectionForm from './SectionForm.vue'

const props = defineProps<{ chapter: string }>()

const phase = ref<'loading' | 'error' | 'ready'>('loading')
const fatalMsg = ref('')
const saving = ref(false)
const notice = reactive<{ msg: string; error: boolean }>({ msg: '', error: false })

const state = reactive<SettingsState>({ servers: [], custom_headers: [], sections: {} })

const chapterMeta = computed(() => CHAPTERS.find((c) => c.id === props.chapter))
const chapterTitle = computed(() => chapterMeta.value?.label ?? '')
const currentSections = computed(() => OBJECT_SECTIONS.filter((s) => chapterMeta.value?.blocks?.includes(s.key)))
const isAccess = computed(() => props.chapter === 'access')

const ERR: Record<string, string> = {
  save_in_progress: '保存进行中，请稍候', too_frequent: '保存过于频繁，请稍后再试',
  too_large: '配置内容过大，请精简后再保存', invalid_shape: '配置格式有误，请刷新页面后重试',
  invalid_field: '字段填写有误',
  credential_redirect: '修改了服务器地址，请重新输入该服务器密码',
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
  state.servers = (c.servers ?? []).map((s: Record<string, unknown>) => ({ ...s }))
  state.custom_headers = (c.custom_headers ?? []).map((h: Record<string, unknown>) => ({ ...h }))
  state.sections = {}
  for (const sec of OBJECT_SECTIONS) state.sections[sec.key] = { ...(c[sec.key] ?? {}) }
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
  setTimeout(() => { if (notice.msg === msg) { notice.msg = ''; notice.error = false } }, 3000)
}

async function save(opts: { silent?: boolean; done?: (ok: boolean) => void } = {}) {
  if (saving.value) { opts.done?.(false); return }
  saving.value = true; notice.msg = ''; notice.error = false
  try {
    const res = await apiPost<{ ok: boolean; warnings?: Record<string, unknown[]>; config?: Record<string, any> }>('config/save', collectBody(state))
    // 用落库后的脱敏配置刷新 state:新行拿到服务端 __row_id 与 password_set,
    // 否则该行再次编辑时留空密码会被当「新行空密码」提交,清掉已存密码(审查 F1)。
    // 已知取舍:重填会重建全部卡片,其他正在编辑未保存的卡片草稿以落库数据为准丢弃
    if (res.config) applyConfig(res.config)
    const w = res.warnings ?? {}
    const skips = [...((w.skipped_servers as unknown[]) ?? []), ...((w.skipped_headers as unknown[]) ?? [])]
    if (skips.length) toast(`已保存，${skips.length} 条无效条目未生效`)
    else if (!opts.silent) toast('已保存，已生效')
    opts.done?.(true)
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast('未登录或登录已过期，请重新登录 Dashboard', true)
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败，请重试', true)
    else toast('保存失败，请重试', true)
    opts.done?.(false)
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
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2></div>

      <template v-if="isAccess">
        <section>
          <div class="group-head"><span class="t">服务器</span><span class="c">要监测的 Palworld 服务器</span></div>
          <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || (s.__local_key as string)" :model-value="s" :index-label="'服务器 ' + pad(i + 1)"
            @update:model-value="(v) => state.servers[i] = v" @delete="state.servers.splice(i, 1)" @save="(done) => save({ silent: true, done })" />
          <button class="add" @click="state.servers.push(emptyRow(SERVER_FIELDS))">＋ 添加服务器</button>
        </section>
        <section>
          <div class="group-head"><span class="t">自定义请求头</span><span class="c">每次请求都会带上</span></div>
          <p class="grouphint">含凭证的请求头建议填写「限定服务器」。留空会发给所有服务器，包括以后新增的。</p>
          <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || (h.__local_key as string)" :model-value="h" :index-label="'请求头 ' + pad(i + 1)"
            @update:model-value="(v) => state.custom_headers[i] = v" @delete="state.custom_headers.splice(i, 1)" @save="(done) => save({ silent: true, done })" />
          <button class="add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS))">＋ 添加请求头</button>
        </section>
      </template>

      <SectionForm v-for="sec in currentSections" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => state.sections[sec.key] = v" />

      <div class="savebar">
        <button class="commit pw-save" :disabled="saving" @click="() => save()">{{ saving ? '保存中…' : '保存设置' }}</button>
        <span v-if="notice.msg" :class="notice.error ? 'pw-error' : 'receipt'">{{ notice.msg }}</span>
        <span class="note">服务器、请求头点各自的「保存」即生效；其余设置用这里保存</span>
      </div>
    </template>
  </div>
</template>
