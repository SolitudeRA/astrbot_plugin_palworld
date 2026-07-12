<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { apiGet, apiPost } from '../lib/bridge'
import { Unauthorized, BusinessError } from '../lib/errors'
import { collectBody, type SettingsState } from '../lib/collect'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS } from '../lib/schema'
import ServerCard from './ServerCard.vue'
import HeaderCard from './HeaderCard.vue'
import SectionForm from './SectionForm.vue'

const phase = ref<'loading' | 'error' | 'ready'>('loading')
const fatalMsg = ref('')
const saving = ref(false)
const notice = ref('')

const state = reactive<SettingsState>({ servers: [], custom_headers: [], sections: {} })

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

function toast(msg: string) { notice.value = msg; setTimeout(() => { if (notice.value === msg) notice.value = '' }, 3000) }

async function save() {
  if (saving.value) return
  saving.value = true; notice.value = ''
  try {
    const res = await apiPost<{ ok: boolean; warnings?: Record<string, unknown[]> }>('config/save', collectBody(state))
    const w = res.warnings ?? {}
    const skips = [...((w.skipped_servers as unknown[]) ?? []), ...((w.skipped_headers as unknown[]) ?? [])]
    toast(skips.length ? `已保存（${skips.length} 条被跳过）` : '已保存并重载')
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e))
    else if (e instanceof Unauthorized) toast('未登录或登录已过期')
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败')
    else toast('保存失败')
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
      <h3 class="pw-section-title">服务器</h3>
      <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || i" :model-value="s"
        @update:model-value="(v) => state.servers[i] = v" @delete="state.servers.splice(i, 1)" />
      <button class="pw-add" @click="state.servers.push(emptyRow(SERVER_FIELDS))">+ 添加服务器</button>

      <h3 class="pw-section-title">自定义请求头</h3>
      <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || i" :model-value="h"
        @update:model-value="(v) => state.custom_headers[i] = v" @delete="state.custom_headers.splice(i, 1)" />
      <button class="pw-add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS))">+ 添加请求头</button>

      <SectionForm v-for="sec in OBJECT_SECTIONS" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => state.sections[sec.key] = v" />

      <div class="pw-save-bar">
        <button class="pw-save pw-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存并重载' }}</button>
        <span v-if="notice" class="pw-notice">{{ notice }}</span>
      </div>
    </template>
  </div>
</template>
