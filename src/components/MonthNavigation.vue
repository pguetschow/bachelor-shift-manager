<template>
  <div class="row mb-4">
    <div class="col">
      <div class="d-flex justify-content-between align-items-center">
        <button 
          @click="$emit('previous')" 
          class="btn btn-outline-primary"
        >
          <i class="bi bi-chevron-left"></i> Vorheriger Monat
        </button>
        
        <h4 class="mb-0">
          {{ currentMonthName }} {{ currentYear }}
        </h4>
        
        <button 
          @click="$emit('next')" 
          class="btn btn-outline-primary"
        >
          Nächster Monat <i class="bi bi-chevron-right"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'

const props = defineProps({
  currentYear: {
    type: Number,
    required: true
  },
  currentMonth: {
    type: Number,
    required: true
  }
})

defineEmits(['previous', 'next'])

const currentMonthName = computed(() => {
  const date = new Date(props.currentYear, props.currentMonth - 1)
  return format(date, 'MMMM', { locale: de })
})
</script> 