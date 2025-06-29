import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { renderToString } from '@vue/server-renderer'
import App from './App.vue'
import routes from './router/routes'

export async function render(url, manifest, initialState = {}) {
  const app = createSSRApp(App)
  const pinia = createPinia()
  
  // Create router instance
  const router = createRouter({
    history: createMemoryHistory(),
    routes
  })
  
  // Set the router location
  await router.push(url)
  await router.isReady()
  
  app.use(pinia)
  app.use(router)
  
  // Set initial state
  if (initialState) {
    pinia.state.value = initialState
  }
  
  const ctx = {}
  const html = await renderToString(app, ctx)
  
  return {
    html,
    state: pinia.state.value,
    router
  }
} 