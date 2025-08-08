<template>
  <div class="container">
    <div class="row justify-content-center">
      <div class="col-lg-10">
        <div class="text-center mb-5">
          <h1 class="display-4 mb-3">
            <i class="bi bi-calendar3 text-primary"></i>
            Schichtplanungssystem
          </h1>
          <p class="lead text-muted">
            Wählen Sie ein Unternehmen aus, um mit der Schichtplanung zu beginnen
          </p>
        </div>

        <div v-if="loading" class="spinner-container">
          <div class="loading-spinner"></div>
        </div>

        <div v-else-if="error" class="alert alert-danger" role="alert">
          {{ error }}
        </div>

        <div v-else>
          <!-- Company Selection -->
          <div class="row g-4 mb-5">
            <div 
              v-for="company in companies" 
              :key="company.id"
              class="col-md-6"
            >
              <div 
                class="card h-100 text-center company-card" 
                @click="selectCompany(company)"
              >
                <div class="card-body d-flex flex-column">
                  <div class="company-icon mb-3">
                    <span class="display-1">{{ company.icon }}</span>
                  </div>
                  <h3 class="card-title">{{ company.name }}</h3>
                  <p class="card-text text-muted flex-grow-1">{{ company.description }}</p>
                  
                  <!-- Sunday Workday Info -->
                  <div class="mb-3">
                    <span class="badge" :class="company.sunday_is_workday ? 'bg-success' : 'bg-secondary'">
                      <i class="bi" :class="company.sunday_is_workday ? 'bi-calendar-check' : 'bi-calendar-x'"></i>
                      {{ company.sunday_is_workday ? 'Sonntag ist Arbeitstag' : 'Sonntag ist Ruhetag' }}
                    </span>
                  </div>
                  
                  <button class="btn btn-lg btn-primary mt-3">
                    <i class="bi bi-box-arrow-in-right"></i> 
                    Auswählen
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Info Section -->
          <div class="row justify-content-center mt-5">
            <div class="col-lg-8">
              <div class="card bg-light">
                <div class="card-body text-center">
                  <h5 class="card-title">
                    <i class="bi bi-info-circle"></i> Hinweis
                  </h5>
                  <p class="card-text">
                    Diese Demo zeigt die Schichtplanung für verschiedene Unternehmensgrößen. 
                    Die Daten werden durch verschiedene Optimierungsalgorithmen generiert.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCompanyStore } from '@/stores/company'

const router = useRouter()
const companyStore = useCompanyStore()

const companies = computed(() => companyStore.companies)
const loading = computed(() => companyStore.loading)
const error = computed(() => companyStore.error)

const selectCompany = (company) => {
  router.push({ name: 'dashboard', params: { companyId: company.id } })
}

onMounted(async () => {
  if (companies.value.length === 0) {
    await companyStore.loadCompanies()
  }
})
</script>

<style scoped>
.company-card {
  cursor: pointer;
  transition: all 0.3s ease;
  border: 2px solid transparent;
}

.company-card:hover {
  transform: translateY(-5px);
  border-color: var(--bs-secondary);
  box-shadow: 0 0.5rem 1rem rgba(0,0,0,.15);
}

.spinner-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.loading-spinner {
  width: 3rem;
  height: 3rem;
  border: 0.25em solid #f3f3f3;
  border-top: 0.25em solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style> 