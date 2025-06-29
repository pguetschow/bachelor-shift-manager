<template>
  <div class="container">
    <div class="row justify-content-center">
      <div class="col-lg-8">
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

        <div v-else class="row g-4">
          <div 
            v-for="company in companies" 
            :key="company.id"
            class="col-md-6 col-lg-4"
          >
            <div class="card h-100 company-card" @click="selectCompany(company)">
              <div class="card-body text-center">
                <div class="company-icon mb-3">
                  <span class="display-4">{{ company.icon }}</span>
                </div>
                <h5 class="card-title">{{ company.name }}</h5>
                <p class="card-text text-muted">{{ company.description }}</p>
                <div class="company-stats">
                  <small class="text-muted">
                    {{ company.employee_count || 0 }} Mitarbeiter • 
                    {{ company.shift_count || 0 }} Schichten
                  </small>
                </div>
              </div>
              <div class="card-footer bg-transparent">
                <button class="btn btn-primary w-100">
                  <i class="bi bi-arrow-right"></i> Auswählen
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
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
}

.company-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 0.5rem 1rem rgba(0,0,0,.15);
}

.company-icon {
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.company-stats {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}
</style> 