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
              class="col-md-4"
            >
              <div class="card h-100 text-center company-card" @click="selectCompany(company)">
                <div class="card-body d-flex flex-column">
                  <div class="company-icon mb-3">
                    <span class="display-1">{{ company.icon }}</span>
                  </div>
                  <h3 class="card-title">{{ company.name }}</h3>
                  <p class="card-text text-muted flex-grow-1">{{ company.description }}</p>
                  <button class="btn btn-primary btn-lg mt-3">
                    <i class="bi bi-box-arrow-in-right"></i> Auswählen
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

          <!-- Benchmark Controls -->
          <div class="row justify-content-center mt-5">
            <div class="col-lg-8">
              <div class="card bg-light">
                <div class="card-body text-center">
                  <h5 class="card-title mb-3">
                    <i class="bi bi-speedometer2"></i> Algorithmus-Benchmark
                  </h5>
                  <p class="card-text mb-4">
                    Testen Sie die verschiedenen Optimierungsalgorithmen und vergleichen Sie deren Performance 
                    für verschiedene Unternehmensgrößen.
                  </p>
                  <div class="d-flex justify-content-center align-items-center gap-3">
                    <label class="form-check-label">
                      <input type="checkbox" class="form-check-input me-2" v-model="loadFixtures" />
                      Mit Beispieldaten (Fixtures) ausführen
                    </label>
                    <button class="btn btn-outline-primary" :disabled="running" @click="runBenchmark">
                      <span v-if="running">
                        <i class="bi bi-arrow-repeat spin"></i> Läuft...
                      </span>
                      <span v-else>
                        <i class="bi bi-rocket"></i> Benchmark starten
                      </span>
                    </button>
                  </div>
                  <div v-if="message" class="alert alert-info mt-3 mb-0">{{ message }}</div>
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
import { ref, computed, onMounted } from 'vue'
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

const loadFixtures = ref(true)
const running = ref(false)
const message = ref('')

const runBenchmark = async () => {
  running.value = true
  message.value = ''
  try {
    const response = await fetch('/api/run-benchmark/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ load_fixtures: loadFixtures.value })
    })
    if (response.ok) {
      message.value = 'Benchmark wurde gestartet. Die Ergebnisse erscheinen nach Abschluss im Export-Ordner.'
    } else {
      message.value = 'Fehler beim Starten des Benchmarks.'
    }
  } catch (e) {
    message.value = 'Fehler beim Starten des Benchmarks.'
  } finally {
    running.value = false
  }
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

.company-icon {
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.company-icon .display-1 {
  font-size: 4rem;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

.card.bg-light {
  border: 1px solid rgba(0,0,0,.125);
}

.form-check-input:checked {
  background-color: var(--bs-primary);
  border-color: var(--bs-primary);
}
</style> 