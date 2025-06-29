<template>
  <div class="card stat-card">
    <div class="card-body">
      <div class="d-flex justify-content-between">
        <div>
          <h6 class="card-subtitle mb-2 text-muted">{{ subtitle }}</h6>
          <h3 class="card-title mb-0">{{ value }}</h3>
        </div>
        <div :class="iconColorClass">
          <i :class="iconClass" class="fs-1"></i>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  subtitle: {
    type: String,
    required: true
  },
  value: {
    type: [String, Number],
    required: true
  },
  icon: {
    type: String,
    default: 'bi bi-info-circle'
  },
  iconColor: {
    type: String,
    default: 'text-primary'
  }
})

const iconClass = computed(() => props.icon)
const iconColorClass = computed(() => props.iconColor)
</script>

<style scoped>
.stat-card {
  transition: transform 0.2s ease-in-out;
}

.stat-card:hover {
  transform: translateY(-2px);
}
</style> 