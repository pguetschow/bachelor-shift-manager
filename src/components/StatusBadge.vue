<template>
  <span class="badge" :class="badgeClass">
    {{ displayText }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    required: true
  },
  size: {
    type: String,
    default: 'normal' // 'small', 'normal', 'large'
  }
})

const displayText = computed(() => {
  const statusMap = {
    'ok': 'OK',
    'understaffed': 'Unterbesetzt',
    'overstaffed': 'Überbesetzt',
    'full': 'Voll',
    'holiday': 'Feiertag',
    'sunday': 'Sonntag',
    'non_working': 'Nicht-Arbeitstag',
    'working': 'Arbeitstag'
  }
  return statusMap[props.status] || props.status
})

const badgeClass = computed(() => {
  const baseClass = 'badge'
  const sizeClass = getSizeClass(props.size)
  const colorClass = getStatusColorClass(props.status)
  return `${baseClass} ${sizeClass} ${colorClass}`
})

const getSizeClass = (size) => {
  switch (size) {
    case 'small': return 'badge-sm'
    case 'large': return 'badge-lg'
    default: return ''
  }
}

const getStatusColorClass = (status) => {
  switch (status) {
    case 'ok': return 'bg-success'
    case 'understaffed': return 'bg-danger'
    case 'overstaffed': return 'bg-warning'
    case 'full': return 'bg-primary'
    case 'holiday': return 'bg-danger'
    case 'sunday': return 'bg-secondary'
    case 'non_working': return 'bg-warning'
    case 'working': return 'bg-success'
    default: return 'bg-primary'
  }
}
</script>

<style scoped>
.badge-sm {
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
}

.badge-lg {
  font-size: 1rem;
  padding: 0.5rem 1rem;
}
</style> 