<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import SettingsPanel from './components/SettingsPanel.vue'
import StatusPanel from './components/StatusPanel.vue'

const tab = ref<'settings' | 'status'>('settings')
const fatal = ref('')
onErrorCaptured((err) => { fatal.value = (err as Error)?.message || '页面发生错误'; return false })
</script>

<template>
  <div v-if="fatal" class="pw-fatal">{{ fatal }}<button class="pw-primary" @click="fatal = ''">重试</button></div>
  <div v-else class="pw-app">
    <nav class="pw-tabs">
      <button :class="{ active: tab === 'settings' }" @click="tab = 'settings'">设置</button>
      <button :class="{ active: tab === 'status' }" @click="tab = 'status'">状态</button>
    </nav>
    <main class="pw-main">
      <SettingsPanel v-if="tab === 'settings'" />
      <StatusPanel v-else />
    </main>
  </div>
</template>
