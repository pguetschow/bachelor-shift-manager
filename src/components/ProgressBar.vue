<template>
  <div class="progress" :style="{ height: height + 'px' }">
    <div 
      class="progress-bar" 
      :class="progressBarClass"
      role="progressbar"
      :style="{ width: percentage + '%' }"
      :aria-valuenow="percentage"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <span v-if="showLabel" class="progress-label">{{ percentage }}%</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  percentage: {
    type: Number,
    required: true
  },
  height: {
    type: Number,
    default: 20
  },
  showLabel: {
    type: Boolean,
    default: true
  },
  variant: {
    type: String,
    default: 'auto' // 'auto', 'success', 'warning', 'danger', 'info'
  }
})

const progressBarClass = computed(() => {
  if (props.variant !== 'auto') {
    return `bg-${props.variant}`
  }
  
  // Auto-determine color based on percentage
  if (props.percentage < 80) return 'bg-danger'
  if (props.percentage < 95) return 'bg-warning'
  return 'bg-success'
})
</script>

<style scoped>
.progress {
  border-radius: 0.25rem;
}

.progress-label {
  font-size: 0.875rem;
  font-weight: 500;
}
</style> 