<script setup lang="ts">
import { ref } from 'vue'
const emit = defineEmits<{ (e: 'confirm', mode: 'single' | 'multi'): void }>()
const selected = ref<'single' | 'multi' | null>(null)

// radiogroup 键盘可达：方向键在 single/multi 间移动 selected；切换后 focus 对应卡；
// preventDefault 抑制页面滚动。空选态（selected=null）无「当前项」可环绕，按方向落端点：
// 正向(Right/Down)→第一项、反向(Left/Up)→最后一项；已选态两项环绕翻转。
const MODES = ['single', 'multi'] as const
const KEY_DIR: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }
function onKeydown(e: KeyboardEvent) {
  const dir = KEY_DIR[e.key]
  if (dir === undefined) return
  e.preventDefault()
  if (selected.value === null) {
    selected.value = dir > 0 ? MODES[0] : MODES[MODES.length - 1]
  } else {
    const idx = MODES.indexOf(selected.value)
    selected.value = MODES[(idx + dir + MODES.length) % MODES.length]
  }
  const el = (e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-mode="${selected.value}"]`)
  el?.focus()
}
</script>

<template>
  <div class="pw-onboarding">
    <div class="panel">
      <div class="head">
        <h2>选择运行模式</h2>
        <span class="badge">首次设置</span>
      </div>
      <p class="lead">这台机器人要管理一台还是多台 Palworld 服务器？界面与命令会按所选模式精简。</p>
      <div class="cards" role="radiogroup" aria-label="运行模式" @keydown="onKeydown">
        <button type="button" class="mode-card" data-mode="single" role="radio"
          :aria-checked="selected === 'single'" :class="{ selected: selected === 'single' }"
          :tabindex="selected ? (selected === 'single' ? 0 : -1) : 0"
          @click="selected = 'single'">
          <span class="ct">单服务器</span>
          <span class="cd">只连接一台服务器。命令不用带服务器名，配置最简单，适合自建单服。</span>
        </button>
        <button type="button" class="mode-card" data-mode="multi" role="radio"
          :aria-checked="selected === 'multi'" :class="{ selected: selected === 'multi' }"
          :tabindex="selected ? (selected === 'multi' ? 0 : -1) : 0"
          @click="selected = 'multi'">
          <span class="ct">多服务器</span>
          <span class="cd">连接多台服务器，按群授权、分别监测与管控，适合社区与多服运营。</span>
        </button>
      </div>
      <button type="button" class="commit confirm" :disabled="!selected"
        @click="selected && emit('confirm', selected)">确认并开始</button>
      <p v-if="selected" class="hint">已选「{{ selected === 'single' ? '单服务器' : '多服务器' }}」，之后可随时在<b class="hint-ref">「连接」</b>页转换</p>
    </div>
  </div>
</template>

<style scoped>
.pw-onboarding { min-height: calc(100vh - 230px); display: flex; align-items: center; justify-content: center; padding: var(--space-6) 0 12vh; }
.panel { width: 100%; max-width: 620px; display: flex; flex-direction: column; gap: var(--space-4); }
.head { display: flex; align-items: baseline; gap: var(--space-3); }
.head h2 { margin: 0; font-size: var(--fs-display); font-weight: var(--fw-semibold); line-height: var(--lh-tight); }
.badge { margin-left: auto; font-size: var(--fs-caption); text-transform: uppercase; letter-spacing: var(--track-eyebrow); color: var(--amber); font-weight: var(--fw-medium); }
.lead { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); line-height: var(--lh-snug); }
.cards { display: flex; gap: var(--space-3); }
/* 类名刻意避开全局 .card（条目卡体系带 .card + .card 纵向间距，兄弟横排会被压出高低差） */
.mode-card { position: relative; flex: 1 1 0; display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-5); text-align: left; font-family: var(--sans); color: var(--ink); background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); box-shadow: var(--shadow-md); cursor: pointer; transition: border-color var(--motion-fast), background var(--motion-fast), box-shadow var(--motion-fast); }
.mode-card:hover { border-color: var(--rule-2); }
.mode-card:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.mode-card.selected { border-color: var(--focus); background: color-mix(in srgb, var(--focus) 10%, var(--card)); box-shadow: inset 0 0 0 1px var(--focus); }
.mode-card.selected::after { content: "✓"; position: absolute; top: 12px; right: 14px; color: var(--focus); font-weight: var(--fw-semibold); font-size: var(--fs-body); }
.mode-card .ct { font-size: var(--fs-title); font-weight: var(--fw-semibold); line-height: var(--lh-tight); }
.mode-card .cd { font-size: var(--fs-sm); color: var(--ink-3); line-height: var(--lh-snug); }
.confirm { align-self: flex-start; }
.hint { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); }
.hint-ref { color: var(--amber); font-weight: var(--fw-semibold); }
@media (max-width: 620px) { .cards { flex-direction: column; } }
</style>
