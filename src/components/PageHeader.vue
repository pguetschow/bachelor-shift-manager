<template>
  <div class="row mb-4">
    <div class="col">
      <h2 class="mb-3">
        <i :class="iconClass" :style="{ color: iconColor }"></i>
        {{ title }}
        <span v-if="company?.name" class="text-muted">- {{ company.name }}</span>
      </h2>
      <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
          <li class="breadcrumb-item">
            <router-link to="/">Unternehmen</router-link>
          </li>
          <li 
            v-for="(crumb, index) in breadcrumbs" 
            :key="index"
            class="breadcrumb-item"
            :class="{ active: index === breadcrumbs.length - 1 }"
            :aria-current="index === breadcrumbs.length - 1 ? 'page' : undefined"
          >
            <router-link 
              v-if="crumb.to && index !== breadcrumbs.length - 1" 
              :to="crumb.to"
            >
              {{ crumb.text }}
            </router-link>
            <span v-else>{{ crumb.text }}</span>
          </li>
        </ol>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCompanyStore } from '@/stores/company'

const props = defineProps({
  title: {
    type: String,
    required: true
  },
  icon: {
    type: String,
    default: 'bi bi-house'
  },
  iconColor: {
    type: String,
    default: 'var(--bs-primary)'
  },
  breadcrumbs: {
    type: Array,
    default: () => []
  }
})

const companyStore = useCompanyStore()
const company = computed(() => companyStore.currentCompany)

const iconClass = computed(() => props.icon)
</script>

<style scoped>
.breadcrumb-item + .breadcrumb-item::before {
  content: ">";
}
</style> 