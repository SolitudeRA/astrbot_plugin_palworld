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
  save_in_progress: '保存进行中，请稍候', too_frequent: '保存过于频繁，请稍候再试',
  too_large: '配置过大', invalid_shape: '配置结构不合法', invalid_field: '字段不合法',
  credential_redirect: '修改了服务器地址，请重新输入该服务器密码',
  restart_failed_rolled_back: '重载失败，已回滚到旧配置',
  restart_failed: '重载失败且回滚失败，请检查后台', unauthorized: '未登录或登录已过期',
}
const mapError = (e: BusinessError) => (ERR[e.code] ?? '保存失败') + (e.path ? `：${e.path}` : '')

function emptyRow(fields: typeof SERVER_FIELDS): Record<string, unknown> {
  const row: Record<string, unknown> = { __row_id: '' }
  for (const f of fields) row[f.key] = f.default
  return row
}
function pad(n: number) { return n < 10 ? '0' + n : '' + n }

async function load() {
  phase.value = 'loading'
  try {
    const r = await apiGet<{ config: Record<string, any> }>('config/get')
    const c = r.config
    state.servers = (c.servers ?? []).map((s: Record<string, unknown>) => ({ ...s }))
    state.custom_headers = (c.custom_headers ?? []).map((h: Record<string, unknown>) => ({ ...h }))
    state.sections = {}
    for (const sec of OBJECT_SECTIONS) state.sections[sec.key] = { ...(c[sec.key] ?? {}) }
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
    const res = await apiPost<{ ok: boolean; warnings?: Record<string, unknown[]> }>('config/save', collectBody(state))
    const w = res.warnings ?? {}
    const skips = [...((w.skipped_servers as unknown[]) ?? []), ...((w.skipped_headers as unknown[]) ?? [])]
    if (skips.length) toast(`已保存（${skips.length} 条被跳过）`)
    else if (!opts.silent) toast('已保存并重载')
    opts.done?.(true)
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast('未登录或登录已过期', true)
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败', true)
    else toast('保存失败', true)
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
          <div class="group-head"><span class="t">数据源</span><span class="c">要观测的 Palworld 服务器</span></div>
          <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || i" :model-value="s" :index-label="'源 ' + pad(i + 1)"
            @update:model-value="(v) => state.servers[i] = v" @delete="state.servers.splice(i, 1)" @save="(done) => save({ silent: true, done })" />
          <button class="add" @click="state.servers.push(emptyRow(SERVER_FIELDS))">＋ 添加数据源</button>
        </section>
        <section>
          <div class="group-head"><span class="t">自定义请求头</span><span class="c">每次请求都会带上</span></div>
          <p class="grouphint">带凭证的请求头，记得用「限定服务器」缩小范围——留空会发给所有服务器（含以后新增的）。</p>
          <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || i" :model-value="h" :index-label="'头 ' + pad(i + 1)"
            @update:model-value="(v) => state.custom_headers[i] = v" @delete="state.custom_headers.splice(i, 1)" @save="(done) => save({ silent: true, done })" />
          <button class="add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS))">＋ 添加请求头</button>
        </section>
      </template>

      <SectionForm v-for="sec in currentSections" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => state.sections[sec.key] = v" />

      <div class="savebar">
        <button class="commit pw-save" :disabled="saving" @click="() => save()">{{ saving ? '保存中…' : '保存本页设置' }}</button>
        <span v-if="notice.msg" :class="notice.error ? 'pw-error' : 'receipt'">{{ notice.msg }}</span>
        <span class="note">数据源、请求头点各自的「保存」即生效；这里保存本页其余设置</span>
      </div>
    </template>
  </div>
</template>
