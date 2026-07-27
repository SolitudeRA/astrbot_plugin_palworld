<script setup lang="ts">
import { ref } from 'vue'
import { locale, setLocale, t, type Locale } from '../lib/i18n'

type Mode = 'single' | 'multi'
type Confirmation = { locale: Locale; mode: Mode }

const emit = defineEmits<{ (e: 'confirm', value: Confirmation): void }>()
const step = ref<1 | 2>(1)
const selectedLocale = ref<Locale>(locale.value)
const selectedMode = ref<Mode | null>(null)

// 语言名是 locale 选择器的例外：始终显示母语名，不随当前 UI 语言翻译。
const LOCALES: readonly { value: Locale; label: string }[] = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'ja', label: '日本語' },
  { value: 'en', label: 'English' },
]
const MODES: readonly Mode[] = ['single', 'multi']
const KEY_DIR: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }

function chooseLocale(value: Locale) {
  selectedLocale.value = value
  setLocale(value)
}

function onLocaleKeydown(e: KeyboardEvent) {
  const dir = KEY_DIR[e.key]
  if (dir === undefined) return
  e.preventDefault()
  const values = LOCALES.map((item) => item.value)
  const index = values.indexOf(selectedLocale.value)
  chooseLocale(values[(index + dir + values.length) % values.length])
  const el = (e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-locale="${selectedLocale.value}"]`)
  el?.focus()
}

// 保留原有模式 radiogroup 行为：空选态按正向键落第一项、反向键落最后一项，
// 已选态则环绕移动；每次移动后把焦点交给对应卡片。
function onModeKeydown(e: KeyboardEvent) {
  const dir = KEY_DIR[e.key]
  if (dir === undefined) return
  e.preventDefault()
  if (selectedMode.value === null) {
    selectedMode.value = dir > 0 ? MODES[0] : MODES[MODES.length - 1]
  } else {
    const index = MODES.indexOf(selectedMode.value)
    selectedMode.value = MODES[(index + dir + MODES.length) % MODES.length]
  }
  const el = (e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-mode="${selectedMode.value}"]`)
  el?.focus()
}

function confirm() {
  if (selectedMode.value) emit('confirm', { locale: selectedLocale.value, mode: selectedMode.value })
}
</script>

<template>
  <div class="pw-onboarding">
    <div class="panel">
      <template v-if="step === 1">
        <div class="head">
          <h2>{{ t('onboarding.language_title') }}</h2>
          <span class="badge">{{ t('onboarding.first_setup') }} · {{ t('onboarding.step', { current: 1, total: 2 }) }}</span>
        </div>
        <p class="lead">{{ t('onboarding.language_lead') }}</p>
        <div class="cards language-cards" role="radiogroup" :aria-label="t('onboarding.language_aria')" @keydown="onLocaleKeydown">
          <button v-for="item in LOCALES" :key="item.value" type="button" class="mode-card"
            :data-locale="item.value" role="radio" :aria-checked="selectedLocale === item.value"
            :class="{ selected: selectedLocale === item.value }"
            :tabindex="selectedLocale === item.value ? 0 : -1" @click="chooseLocale(item.value)">
            <span class="ct">{{ item.label }}</span>
            <span class="cd">{{ t(`onboarding.locale.${item.value}.desc`) }}</span>
          </button>
        </div>
        <div class="actions">
          <button type="button" class="commit next" data-act="next" @click="step = 2">{{ t('onboarding.next') }}</button>
        </div>
      </template>

      <template v-else>
        <div class="head">
          <h2>{{ t('onboarding.mode_title') }}</h2>
          <span class="badge">{{ t('onboarding.first_setup') }} · {{ t('onboarding.step', { current: 2, total: 2 }) }}</span>
        </div>
        <p class="lead">{{ t('onboarding.mode_lead') }}</p>
        <div class="cards" role="radiogroup" :aria-label="t('onboarding.mode_aria')" @keydown="onModeKeydown">
          <button v-for="mode in MODES" :key="mode" type="button" class="mode-card"
            :data-mode="mode" role="radio" :aria-checked="selectedMode === mode"
            :class="{ selected: selectedMode === mode }"
            :tabindex="selectedMode ? (selectedMode === mode ? 0 : -1) : 0"
            @click="selectedMode = mode">
            <span class="ct">{{ t(`onboarding.mode.${mode}.title`) }}</span>
            <span class="cd">{{ t(`onboarding.mode.${mode}.desc`) }}</span>
          </button>
        </div>
        <div class="actions">
          <button type="button" class="ghost" data-act="back" @click="step = 1">{{ t('onboarding.back') }}</button>
          <button type="button" class="commit confirm" :disabled="!selectedMode" @click="confirm">{{ t('onboarding.confirm') }}</button>
        </div>
        <p v-if="selectedMode" class="hint">
          {{ t('onboarding.hint_before', { mode: t(`onboarding.mode.${selectedMode}.title`) }) }}<b class="hint-ref">{{ t('punct.quote_open') }}{{ t('chapter.access.label') }}{{ t('punct.quote_close') }}</b>{{ t('onboarding.hint_after') }}
        </p>
      </template>
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
.language-cards .mode-card { min-width: 0; padding: var(--space-4); }
.language-cards .ct { font-size: var(--fs-heading); }
.actions { display: flex; align-items: center; gap: var(--space-3); }
.hint { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); }
.hint-ref { color: var(--amber); font-weight: var(--fw-semibold); }
@media (max-width: 620px) { .cards { flex-direction: column; } }
</style>
