<template>
  <div v-if="isDev" class="debug-banner">
    <span>Vite last refresh: {{ lastRefresh }}</span>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const lastRefresh = ref(new Date().toLocaleTimeString())
const isDev = import.meta.env.DEV

onMounted(() => {
  if (import.meta.hot) {
    import.meta.hot.accept(() => {
      lastRefresh.value = new Date().toLocaleTimeString()
    })
  }
})
</script>

<style scoped>
.debug-banner {
  position: fixed;
  right: 16px;
  bottom: 16px;
  background: #222;
  color: #fff;
  padding: 8px 16px;
  border-radius: 8px 8px 0 8px;
  font-size: 14px;
  opacity: 0.85;
  z-index: 9999;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
</style> 