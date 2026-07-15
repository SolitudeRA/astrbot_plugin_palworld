<script setup lang="ts">
import { ref } from 'vue'
const emit = defineEmits<{ (e: 'confirm', mode: 'single' | 'multi'): void }>()
const selected = ref<'single' | 'multi' | null>(null)
</script>

<template>
  <div class="onboarding">
    <h2>欢迎使用 帕鲁世界终端</h2>
    <p class="lead">首次使用请先选择运行模式（之后可在 AstrBot 齿轮更改）：</p>
    <div class="cards">
      <button type="button" class="mode-card" data-mode="single"
        :class="{ picked: selected === 'single' }" @click="selected = 'single'">
        <span class="t">单服务器</span>
        <span class="d">唯一服务器；群授权走「授权群名单 + /pal whereami」。</span>
      </button>
      <button type="button" class="mode-card" data-mode="multi"
        :class="{ picked: selected === 'multi' }" @click="selected = 'multi'">
        <span class="t">多服务器</span>
        <span class="d">多台服务器；用 /pal link 绑定切换。</span>
      </button>
    </div>
    <button type="button" class="confirm" :disabled="!selected"
      @click="selected && emit('confirm', selected)">确认并开始</button>
  </div>
</template>

<style scoped>
.onboarding { display: flex; flex-direction: column; gap: 16px; max-width: 720px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.mode-card { flex: 1 1 260px; display: flex; flex-direction: column; gap: 6px; padding: 16px;
  text-align: left; border: 1px solid var(--pw-border, #3a3a3a); border-radius: 10px;
  background: transparent; cursor: pointer; }
.mode-card.picked { border-color: var(--pw-accent, #6ea8fe); box-shadow: 0 0 0 1px var(--pw-accent, #6ea8fe); }
.mode-card .t { font-weight: 600; }
.mode-card .d { opacity: .75; font-size: .9em; }
.confirm { align-self: flex-start; padding: 8px 18px; border-radius: 8px; cursor: pointer; }
.confirm:disabled { opacity: .5; cursor: not-allowed; }
</style>
