import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// Check if we're in SSR mode
if (typeof window !== 'undefined' && window.__INITIAL_STATE__) {
  // Hydrate the store with SSR data
  pinia.state.value = window.__INITIAL_STATE__
}

app.mount('#app') 