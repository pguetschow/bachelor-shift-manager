<template>
  <span>{{ formattedTime }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  time: {
    type: String,
    required: true
  },
  format: {
    type: String,
    default: 'HH:mm' // 'HH:mm', 'HH:mm:ss', 'time-range'
  },
  endTime: {
    type: String,
    default: null
  }
})

const formattedTime = computed(() => {
  if (!props.time) return ''
  
  if (props.format === 'time-range' && props.endTime) {
    return `${formatTime(props.time)} - ${formatTime(props.endTime)}`
  }
  
  return formatTime(props.time)
})

const formatTime = (timeString) => {
  if (!timeString) return ''
  // Remove seconds if present and format as HH:mm
  return timeString.substring(0, 5)
}
</script> 