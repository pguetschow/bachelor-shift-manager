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
  background-color: var(--shift-early-light);
  color: var(--shift-early-color);
  border: 1px solid var(--shift-early-border);
}

.shift-morning {
  background-color: var(--shift-morning-light);
  color: var(--shift-morning-color);
  border: 1px solid var(--shift-morning-border);
}

.shift-late {
  background-color: var(--shift-late-light);
  color: var(--shift-late-color);
  border: 1px solid var(--shift-late-border);
}

.shift-night {
  background-color: var(--shift-night-light);
  color: var(--shift-night-color);
  border: 1px solid var(--shift-night-border);
}

.shift-default {
  background-color: #f5f5f5;
  color: #616161;
  border: 1px solid #e0e0e0;
}
</style> 