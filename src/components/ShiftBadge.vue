<template>
  <span class="shift-badge" :class="badgeClass">
    {{ displayName }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  shiftName: {
    type: String,
    required: true
  },
  size: {
    type: String,
    default: 'normal' // 'small', 'normal', 'large'
  }
})

const displayName = computed(() => {
  const shiftMap = {
    'EarlyShift': 'Frühschicht',
    'MorningShift': 'Morgenschicht',
    'LateShift': 'Spätschicht',
    'NightShift': 'Nachtschicht'
  }
  return shiftMap[props.shiftName] || props.shiftName
})

const badgeClass = computed(() => {
  const baseClass = 'shift-badge'
  const sizeClass = `shift-badge-${props.size}`
  const colorClass = getShiftColorClass(props.shiftName)
  return `${baseClass} ${sizeClass} ${colorClass}`
})

const getShiftColorClass = (shiftName) => {
  const classMap = {
    'EarlyShift': 'shift-early',
    'MorningShift': 'shift-morning',
    'LateShift': 'shift-late',
    'NightShift': 'shift-night'
  }
  return classMap[shiftName] || 'shift-default'
}
</script>

<style scoped>
.shift-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-weight: 500;
  display: inline-block;
}

.shift-badge-small {
  font-size: 0.75rem;
  padding: 0.125rem 0.375rem;
}

.shift-badge-normal {
  font-size: 0.875rem;
  padding: 0.25rem 0.5rem;
}

.shift-badge-large {
  font-size: 1rem;
  padding: 0.375rem 0.75rem;
}

.shift-early {
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #bbdefb;
}

.shift-morning {
  background-color: #f3e5f5;
  color: #7b1fa2;
  border: 1px solid #e1bee7;
}

.shift-late {
  background-color: #fff3e0;
  color: #f57c00;
  border: 1px solid #ffcc02;
}

.shift-night {
  background-color: #fce4ec;
  color: #c2185b;
  border: 1px solid #f8bbd9;
}

.shift-default {
  background-color: #f5f5f5;
  color: #616161;
  border: 1px solid #e0e0e0;
}
</style> 