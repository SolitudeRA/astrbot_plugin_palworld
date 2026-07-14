<script setup lang="ts">
import { ref, computed, watchEffect, onErrorCaptured } from 'vue'
import SettingsPanel from './components/SettingsPanel.vue'
import StatusPanel from './components/StatusPanel.vue'
import AuditPanel from './components/AuditPanel.vue'
import { CHAPTERS, DEFAULT_CHAPTER } from './lib/chapters'

const chapter = ref(DEFAULT_CHAPTER)
// 按当前章的 kind 分派面板：status→StatusPanel、audit→AuditPanel、其余→SettingsPanel
const currentKind = computed(() => CHAPTERS.find((c) => c.id === chapter.value)?.kind ?? 'settings')
const fatal = ref('')
// 固定文案,不透传 err.message(与 boot.ts 不回显原始错误的策略一致,防内部信息泄露)
onErrorCaptured(() => { fatal.value = '页面发生错误，请刷新重试'; return false })

const THEME_KEY = 'palworld-terminal-theme'
const LEGACY_THEME_KEY = 'palchronicle-theme' // 改名(2026-07)前的 key,读回退保住老用户偏好
function readStored(): 'light' | 'dark' | null {
  try {
    const v = localStorage.getItem(THEME_KEY) ?? localStorage.getItem(LEGACY_THEME_KEY)
    return v === 'light' || v === 'dark' ? v : null
  } catch { return null }
}
function writeStored(v: 'light' | 'dark') { try { localStorage.setItem(THEME_KEY, v) } catch { /* 受限 iframe 忽略 */ } }
function initialTheme(): 'light' | 'dark' {
  const stored = readStored(); if (stored) return stored
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}
const theme = ref<'light' | 'dark'>(initialTheme())
watchEffect(() => { document.documentElement.setAttribute('data-theme', theme.value) })
function toggleTheme() { theme.value = theme.value === 'dark' ? 'light' : 'dark'; writeStored(theme.value) }

const observeChapters = CHAPTERS.filter((c) => c.group === '观测')
const configChapters = CHAPTERS.filter((c) => c.group === '配置')
</script>

<template>
  <div v-if="fatal" class="pw-fatal">{{ fatal }}<button class="pw-primary" @click="fatal = ''">重试</button></div>
  <div v-else class="stage">
    <div class="console">
      <header>
        <div class="mast">
          <div class="brand"><span class="cn">帕鲁世界终端</span><span class="en">PalWorldTerminal</span></div>
          <button class="ghost" @click="toggleTheme">{{ theme === 'dark' ? '☀ 浅色' : '☾ 深色' }}</button>
        </div>
        <div class="dateline"></div>
        <div class="subline"><span>Palworld 服务器监测 · 只读</span></div>
      </header>
      <div class="layout">
        <nav class="rail" aria-label="章节索引">
          <button v-for="c in observeChapters" :key="c.id" :aria-current="chapter === c.id ? 'true' : 'false'" @click="chapter = c.id">
            {{ c.label }}<span v-if="c.kind === 'status'" class="dot" aria-hidden="true"></span>
          </button>
          <div class="rail-sep" aria-hidden="true"></div>
          <button v-for="c in configChapters" :key="c.id" :aria-current="chapter === c.id ? 'true' : 'false'" @click="chapter = c.id">{{ c.label }}</button>
        </nav>
        <div class="pane">
          <SettingsPanel v-show="currentKind === 'settings'" :chapter="chapter" />
          <StatusPanel v-if="currentKind === 'status'" />
          <AuditPanel v-if="currentKind === 'audit'" />
        </div>
      </div>
    </div>
  </div>
</template>
