import { createApp, h } from 'vue'
import App from './App.vue'
import { ready } from './lib/bridge'
import { bootMessage } from './lib/boot'
import { setLocale, guessLocale } from './lib/i18n'
import './styles/tokens.css'

async function boot() {
  setLocale(guessLocale()) // 挂载前按 navigator.language 猜一次；模块顶层不猜
  try {
    await ready()
  } catch (e) {
    createApp({ render: () => h('div', { class: 'pw-fatal' }, bootMessage(e)) }).mount('#app')
    return
  }
  createApp(App).mount('#app')
}
boot()
