<template>
  <div class="row mb-4">
    <div class="col">
      <div class="month-navigation">
        <button 
          @click="$emit('previous')" 
          class="btn btn-outline-primary navigation-btn"
          aria-label="Vorheriger Monat"
          type="button"
        >
          <i class="bi bi-chevron-left"></i>
          <span class="btn-text">Vorheriger Monat</span>
        </button>
        
        <h4 class="month-title mb-0">
          {{ currentMonthName }} {{ currentYear }}
        </h4>
        
        <button 
          @click="$emit('next')" 
          class="btn btn-outline-primary navigation-btn"
          aria-label="Nächster Monat"
          type="button"
        >
          <span class="btn-text">Nächster Monat</span>
          <i class="bi bi-chevron-right"></i>
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

<style scoped>
.month-navigation {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.navigation-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  white-space: nowrap;
  min-width: fit-content;
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.month-title {
  text-align: center;
  flex: 1;
  margin: 0 0.5rem;
}

/* Mobile optimizations */
@media (max-width: 576px) {
  .month-navigation {
    gap: 0.5rem;
  }
  
  .navigation-btn {
    padding: 0.75rem 1rem;
    font-size: 0.875rem;
    min-height: 44px; /* Minimum touch target size */
    min-width: 44px;
    border-radius: 0.375rem;
    position: relative;
    z-index: 10;
    touch-action: manipulation;
  }
  
  .btn-text {
    display: none;
  }
  
  .month-title {
    font-size: 1.25rem;
    margin: 0 0.25rem;
  }
}

@media (max-width: 768px) {
  .month-title {
    font-size: 1.5rem;
  }
  
  .navigation-btn {
    min-height: 44px;
    min-width: 44px;
    position: relative;
    z-index: 10;
    touch-action: manipulation;
  }
}

/* Ensure buttons are clickable on all devices */
.navigation-btn:active {
  transform: scale(0.98);
}

.navigation-btn:focus {
  outline: 2px solid var(--bs-primary);
  outline-offset: 2px;
}

/* Additional mobile touch improvements */
@media (hover: none) and (pointer: coarse) {
  .navigation-btn {
    -webkit-tap-highlight-color: rgba(0, 123, 255, 0.3);
    touch-action: manipulation;
  }
}
</style> 