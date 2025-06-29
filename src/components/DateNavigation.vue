<template>
  <div class="row mb-4">
    <div class="col">
      <div class="date-navigation">
        <button 
          @click="$emit('previous')" 
          class="btn btn-outline-primary navigation-btn"
          aria-label="Vorheriger Tag"
          type="button"
        >
          <i class="bi bi-chevron-left"></i>
          <span class="btn-text">Vorheriger Tag</span>
        </button>
        
        <h4 class="date-title mb-0">
          {{ formattedDate }}
        </h4>
        
        <button 
          @click="$emit('next')" 
          class="btn btn-outline-primary navigation-btn"
          aria-label="Nächster Tag"
          type="button"
        >
          <span class="btn-text">Nächster Tag</span>
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

<style scoped>
.date-navigation {
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

.date-title {
  text-align: center;
  flex: 1;
  margin: 0 0.5rem;
}

/* Mobile optimizations */
@media (max-width: 576px) {
  .date-navigation {
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
  
  .date-title {
    font-size: 1.125rem;
    margin: 0 0.25rem;
  }
}

@media (max-width: 768px) {
  .date-title {
    font-size: 1.25rem;
  }
  
  .navigation-btn {
    min-height: 44px;
    min-width: 44px;
    position: relative;
    z-index: 10;
    touch-action: manipulation;
  }
}

@media (max-width: 480px) {
  .date-title {
    font-size: 1rem;
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