<template>
  <div class="row mb-4">
    <div class="col">
      <div class="d-flex justify-content-between align-items-center">
        <button 
          @click="$emit('previous')" 
          class="btn btn-outline-primary"
        >
          <i class="bi bi-chevron-left"></i> Vorheriger Tag
        </button>
        
        <h4 class="mb-0">
          {{ formattedDate }}
        </h4>
        
        <button 
          @click="$emit('next')" 
          class="btn btn-outline-primary"
        >
          Nächster Tag <i class="bi bi-chevron-right"></i>
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
  date: {
    type: Date,
    required: true
  }
})

defineEmits(['previous', 'next'])

const formattedDate = computed(() => {
  return format(props.date, 'EEEE, dd.MM.yyyy', { locale: de })
})
</script> 