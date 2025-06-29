<template>
  <div id="app">
    <nav class="navbar navbar-expand-lg navbar-dark">
      <div class="container-fluid">
        <router-link class="navbar-brand" to="/">
          <i class="bi bi-calendar3"></i> Schichtplanungssystem
        </router-link>
        
        <button 
          class="navbar-toggler" 
          type="button" 
          data-bs-toggle="collapse" 
          data-bs-target="#navbarNav"
        >
          <span class="navbar-toggler-icon"></span>
        </button>
        
        <div class="collapse navbar-collapse" id="navbarNav">
          <ul class="navbar-nav me-auto mb-2 mb-lg-0">
            <li class="nav-item">
              <router-link 
                class="nav-link" 
                :to="{ name: 'dashboard', params: { companyId: $route.params.companyId } }"
                v-if="$route.params.companyId"
              >
                <i class="bi bi-speedometer2"></i> Dashboard
              </router-link>
            </li>
            <li class="nav-item">
              <router-link 
                class="nav-link" 
                :to="{ name: 'month-view', params: { companyId: $route.params.companyId } }"
                v-if="$route.params.companyId"
              >
                <i class="bi bi-calendar-month"></i> Monatsansicht
              </router-link>
            </li>
            <li class="nav-item">
              <router-link 
                class="nav-link" 
                :to="{ name: 'employees', params: { companyId: $route.params.companyId } }"
                v-if="$route.params.companyId"
              >
                <i class="bi bi-people"></i> Mitarbeiter
              </router-link>
            </li>
            <li class="nav-item">
              <router-link 
                class="nav-link" 
                :to="{ name: 'analytics', params: { companyId: $route.params.companyId } }"
                v-if="$route.params.companyId"
              >
                <i class="bi bi-graph-up"></i> Analysen
              </router-link>
            </li>
          </ul>
          
          <span class="navbar-text" v-if="company">
            <i class="bi bi-building"></i> {{ company.name }}
            <algorithm-selector 
              v-if="availableAlgorithms.length"
              :algorithms="availableAlgorithms"
              :selected="selectedAlgorithm"
              @change="onAlgorithmChange"
            />
          </span>
        </div>
      </div>
    </nav>
    
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import AlgorithmSelector from '@/components/AlgorithmSelector.vue'

const route = useRoute()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()

const company = computed(() => companyStore.currentCompany)
const availableAlgorithms = computed(() => scheduleStore.availableAlgorithms)
const selectedAlgorithm = computed(() => scheduleStore.selectedAlgorithm)

const onAlgorithmChange = (algorithm) => {
  scheduleStore.setSelectedAlgorithm(algorithm)
}
</script>

<style scoped>
.main-content {
  min-height: calc(100vh - 56px);
  padding: 2rem 0;
}
</style> 