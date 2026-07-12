import { createApp, h } from 'vue'
import App from './App.vue'
import { ready } from './lib/bridge'
import { bootMessage } from './lib/boot'
import './styles/tokens.css'

async function boot() {
  try {
    await ready()
  } catch (e) {
    createApp({ render: () => h('div', { class: 'pw-fatal' }, bootMessage(e)) }).mount('#app')
    return
  }
  createApp(App).mount('#app')
}
boot()
