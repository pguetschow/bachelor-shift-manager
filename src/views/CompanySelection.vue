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
                  
                  <!-- Sunday Workday Info -->
                  <div class="mb-3">
                    <span class="badge" :class="company.sunday_is_workday ? 'bg-success' : 'bg-secondary'">
                      <i class="bi" :class="company.sunday_is_workday ? 'bi-calendar-check' : 'bi-calendar-x'"></i>
                      {{ company.sunday_is_workday ? 'Sonntag ist Arbeitstag' : 'Sonntag ist Ruhetag' }}
                    </span>
                  </div>
                  
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
                  
                  <!-- Benchmark Status Display -->
                  <div v-if="benchmarkStatus" class="mb-3">
                    <div class="alert" :class="getStatusAlertClass()">
                      <div class="d-flex align-items-center justify-content-between">
                        <div>
                          <strong>Status: {{ getStatusDisplayText() }}</strong>
                          <div v-if="benchmarkStatus.started_at" class="small">
                            Gestartet: {{ formatDateTime(benchmarkStatus.started_at) }}
                          </div>
                          <div v-if="benchmarkStatus.completed_at" class="small">
                            Abgeschlossen: {{ formatDateTime(benchmarkStatus.completed_at) }}
                          </div>
                          <div v-if="benchmarkStatus.error_message" class="small text-danger">
                            Fehler: {{ benchmarkStatus.error_message }}
                          </div>
                        </div>
                        <div v-if="benchmarkStatus.status === 'running'" class="spinner-border spinner-border-sm" role="status">
                          <span class="visually-hidden">Loading...</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <!-- Benchmark Controls -->
                  <div class="d-flex justify-content-center align-items-center gap-3 mb-3">
                    <label class="form-check-label">
                      <input type="checkbox" class="form-check-input me-2" v-model="loadFixtures" />
                      Mit Beispieldaten (Fixtures) ausführen
                    </label>
                  </div>
                  
                  <div class="d-flex justify-content-center gap-2">
                    <!-- Start/Force Button -->
                    <button 
                      class="btn" 
                      :class="getStartButtonClass()" 
                      :disabled="benchmarkStatus?.status === 'running' && !forceRun"
                      @click="runBenchmark"
                    >
                      <span v-if="benchmarkStatus?.status === 'running' && !forceRun">
                        <i class="bi bi-lock"></i> Läuft...
                      </span>
                      <span v-else-if="benchmarkStatus?.status === 'running' && forceRun">
                        <i class="bi bi-arrow-repeat spin"></i> Erzwingen...
                      </span>
                      <span v-else>
                        <i class="bi bi-rocket"></i> 
                        {{ benchmarkStatus?.status === 'running' ? 'Erzwingen' : 'Benchmark starten' }}
                      </span>
                    </button>
                    
                    <!-- Force Toggle -->
                    <div v-if="benchmarkStatus?.status === 'running'" class="form-check">
                      <input 
                        type="checkbox" 
                        class="form-check-input" 
                        id="forceRun" 
                        v-model="forceRun"
                      />
                      <label class="form-check-label small" for="forceRun">
                        Erzwingen
                      </label>
                    </div>
                    
                    <!-- Reset Button -->
                    <button 
                      v-if="benchmarkStatus?.status !== 'idle'"
                      class="btn btn-outline-secondary btn-sm" 
                      @click="resetBenchmark"
                      :disabled="benchmarkStatus?.status === 'running'"
                    >
                      <i class="bi bi-arrow-clockwise"></i> Zurücksetzen
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
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
const benchmarkStatus = ref(null)
const forceRun = ref(false)
let statusInterval = null

const getStatusAlertClass = () => {
  if (!benchmarkStatus.value) return 'alert-info'
  
  switch (benchmarkStatus.value.status) {
    case 'running': return 'alert-warning'
    case 'completed': return 'alert-success'
    case 'failed': return 'alert-danger'
    default: return 'alert-info'
  }
}

const getStatusDisplayText = () => {
  if (!benchmarkStatus.value) return 'Unbekannt'
  
  switch (benchmarkStatus.value.status) {
    case 'idle': return 'Bereit'
    case 'running': return 'Läuft...'
    case 'completed': return 'Abgeschlossen'
    case 'failed': return 'Fehlgeschlagen'
    default: return 'Unbekannt'
  }
}

const getStartButtonClass = () => {
  if (benchmarkStatus.value?.status === 'running' && !forceRun.value) {
    return 'btn-secondary disabled'
  } else if (benchmarkStatus.value?.status === 'running' && forceRun.value) {
    return 'btn-warning'
  } else {
    return 'btn-outline-primary'
  }
}

const formatDateTime = (dateString) => {
  if (!dateString) return ''
  return new Date(dateString).toLocaleString('de-DE')
}

const loadBenchmarkStatus = async () => {
  try {
    const response = await fetch('/api/benchmark-status/')
    if (response.ok) {
      benchmarkStatus.value = await response.json()
    }
  } catch (e) {
    console.error('Error loading benchmark status:', e)
  }
}

const runBenchmark = async () => {
  running.value = true
  message.value = ''
  try {
    const response = await fetch('/api/run-benchmark/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        load_fixtures: loadFixtures.value,
        force: forceRun.value
      })
    })
    
    const result = await response.json()
    
    if (response.ok) {
      message.value = 'Benchmark wurde gestartet. Die Ergebnisse erscheinen nach Abschluss im Export-Ordner.'
      await loadBenchmarkStatus()
    } else {
      message.value = result.message || 'Fehler beim Starten des Benchmarks.'
    }
  } catch (e) {
    message.value = 'Fehler beim Starten des Benchmarks.'
  } finally {
    running.value = false
    forceRun.value = false
  }
}

const resetBenchmark = async () => {
  try {
    const response = await fetch('/api/reset-benchmark/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    
    if (response.ok) {
      message.value = 'Benchmark-Status wurde zurückgesetzt.'
      await loadBenchmarkStatus()
    } else {
      message.value = 'Fehler beim Zurücksetzen des Benchmarks.'
    }
  } catch (e) {
    message.value = 'Fehler beim Zurücksetzen des Benchmarks.'
  }
}

onMounted(async () => {
  if (companies.value.length === 0) {
    await companyStore.loadCompanies()
  }
  
  // Load initial status
  await loadBenchmarkStatus()
  
  // Set up status polling if running
  if (benchmarkStatus.value?.status === 'running') {
    statusInterval = setInterval(loadBenchmarkStatus, 5000) // Poll every 5 seconds
  }
})

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval)
  }
})

// Watch for status changes to start/stop polling
const startStatusPolling = () => {
  if (statusInterval) {
    clearInterval(statusInterval)
  }
  
  if (benchmarkStatus.value?.status === 'running') {
    statusInterval = setInterval(loadBenchmarkStatus, 5000)
  }
}

// Watch benchmark status changes
const watchStatus = () => {
  if (benchmarkStatus.value?.status === 'running') {
    startStatusPolling()
  } else if (statusInterval) {
    clearInterval(statusInterval)
    statusInterval = null
  }
}

// Set up watcher
import { watch } from 'vue'
watch(() => benchmarkStatus.value?.status, watchStatus)
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