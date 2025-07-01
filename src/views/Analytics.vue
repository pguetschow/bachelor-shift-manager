<template>
  <div class="container">
    <!-- Header -->
    <div class="row mb-4">
      <div class="col">
        <h2 class="mb-3">
          <i class="bi bi-graph-up text-primary"></i>
          Analysen - {{ company?.name }}
        </h2>
        <nav aria-label="breadcrumb">
          <ol class="breadcrumb">
            <li class="breadcrumb-item">
              <router-link to="/">Unternehmen</router-link>
            </li>
            <li class="breadcrumb-item">
              <router-link :to="{ name: 'dashboard', params: { companyId: $route.params.companyId } }">
                Dashboard
              </router-link>
            </li>
            <li class="breadcrumb-item active" aria-current="page">Analysen</li>
          </ol>
        </nav>
      </div>
    </div>

    <!-- Month Navigation -->
    <div class="row mb-4">
      <div class="col">
        <div class="d-flex justify-content-between align-items-center">
          <button 
            @click="previousMonth" 
            class="btn btn-outline-primary"
          >
            <i class="bi bi-chevron-left"></i> Vorheriger Monat
          </button>
          
          <h4 class="mb-0">
            {{ currentMonthName }} {{ currentYear }}
          </h4>
          
          <button 
            @click="nextMonth" 
            class="btn btn-outline-primary"
          >
            Nächster Monat <i class="bi bi-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="spinner-container">
      <div class="loading-spinner"></div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="alert alert-danger" role="alert">
      {{ error }}
    </div>

    <!-- Analytics Content -->
    <div v-else>
      <!-- Summary Cards -->
      <div class="row mb-4">
        <div class="col-md-3 mb-3">
          <div class="card stat-card">
            <div class="card-body">
              <div class="d-flex justify-content-between">
                <div>
                  <h6 class="card-subtitle mb-2 text-muted">Durchschnittliche Abdeckung</h6>
                  <h3 class="card-title mb-0">{{ formatNumber(coverageStats.coverage_percentage) }}%</h3>
                </div>
                <div class="text-primary">
                  <i class="bi bi-pie-chart fs-1"></i>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="col-md-3 mb-3">
          <div class="card stat-card">
            <div class="card-body">
              <div class="d-flex justify-content-between">
                <div>
                  <h6 class="card-subtitle mb-2 text-muted">Vollständig besetzt</h6>
                  <h3 class="card-title mb-0">{{ formatNumber(coverageStats.fully_staffed) }}</h3>
                </div>
                <div class="text-success">
                  <i class="bi bi-check-circle fs-1"></i>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="col-md-3 mb-3">
          <div class="card stat-card">
            <div class="card-body">
              <div class="d-flex justify-content-between">
                <div>
                  <h6 class="card-subtitle mb-2 text-muted">Unterbesetzt</h6>
                  <h3 class="card-title mb-0">{{ formatNumber(coverageStats.understaffed) }}</h3>
                </div>
                <div class="text-danger">
                  <i class="bi bi-exclamation-triangle fs-1"></i>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="col-md-3 mb-3">
          <div class="card stat-card">
            <div class="card-body">
              <div class="d-flex justify-content-between">
                <div>
                  <h6 class="card-subtitle mb-2 text-muted">Überbesetzt</h6>
                  <h3 class="card-title mb-0">{{ formatNumber(coverageStats.overstaffed) }}</h3>
                </div>
                <div class="text-warning">
                  <i class="bi bi-people fs-1"></i>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Charts Row -->
      <div class="row mb-4">
        <div class="col-lg-6 mb-4">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-bar-chart"></i> Abdeckung nach Schichten
              </h5>
            </div>
            <div class="card-body">
              <div class="chart-container" style="height: 300px;">
                <canvas ref="coverageChart"></canvas>
              </div>
            </div>
          </div>
        </div>

        <div class="col-lg-6 mb-4">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-pie-chart"></i> Abdeckungsverteilung
              </h5>
            </div>
            <div class="card-body">
              <div class="chart-container" style="height: 300px;">
                <canvas ref="distributionChart"></canvas>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Employee Statistics -->
      <div class="row mb-4">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-people"></i> Mitarbeiterstatistiken
              </h5>
            </div>
            <div class="card-body">
              <div class="table-responsive">
                <table class="table table-hover">
                  <thead>
                    <tr>
                      <th>Mitarbeiter</th>
                      <th>Stunden</th>
                      <th>Schichten</th>
                      <th>Durchschnitt/Stunde</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="employee in topEmployees" :key="employee.id">
                      <td>
                        <strong>{{ employee.name }}</strong>
                      </td>
                      <td>{{ formatNumber(employee.hours) }}</td>
                      <td>{{ employee.shifts || 0 }}</td>
                      <td>{{ formatNumber(employee.hours / (employee.shifts || 1)) }}</td>
                      <td>
                        <span 
                          class="badge"
                          :class="getEmployeeStatusClass(employee.hours)"
                        >
                          {{ getEmployeeStatusText(employee.hours) }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch, ref, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import { Chart, registerables } from 'chart.js'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import { analyticsAPI } from '@/services/api'

// Register Chart.js components
Chart.register(...registerables)

const route = useRoute()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()

const company = computed(() => companyStore.currentCompany)
const loading = computed(() => scheduleStore.loading)
const error = computed(() => scheduleStore.error)
const currentYear = computed(() => scheduleStore.currentYear)
const currentMonth = computed(() => scheduleStore.currentMonth)
const coverageStats = computed(() => scheduleStore.getCoverageStats())
const topEmployees = computed(() => scheduleStore.getTopEmployees())
const availableAlgorithms = computed(() => scheduleStore.availableAlgorithms)

const currentMonthName = computed(() => {
  const date = new Date(currentYear.value, currentMonth.value - 1)
  return format(date, 'MMMM', { locale: de })
})

// Chart references
const coverageChart = ref(null)
const distributionChart = ref(null)

const algorithmKPIs = ref({})
const algorithmKPIsLoading = ref(false)
const algorithmKPIsError = ref(null)

const previousMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value - 2)
  scheduleStore.setCurrentDate(newDate)
  loadAnalyticsData()
}

const nextMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value)
  scheduleStore.setCurrentDate(newDate)
  loadAnalyticsData()
}

const getEmployeeStatusClass = (hours) => {
  if (hours >= 160) return 'bg-success'
  if (hours >= 120) return 'bg-warning'
  return 'bg-danger'
}

const getEmployeeStatusText = (hours) => {
  if (hours >= 160) return 'Optimal'
  if (hours >= 120) return 'Gut'
  return 'Niedrig'
}

const loadAlgorithmKPIs = async () => {
  if (!route.params.companyId) return
  algorithmKPIsLoading.value = true
  algorithmKPIsError.value = null
  try {
    const { data } = await analyticsAPI.getAllAlgorithmKPIs(
      route.params.companyId,
      currentYear.value,
      currentMonth.value
    )
    algorithmKPIs.value = data.algorithms || {}
  } catch (err) {
    algorithmKPIsError.value = 'Fehler beim Laden der Algorithmus-KPIs'
    console.error(err)
  } finally {
    algorithmKPIsLoading.value = false
  }
}

const loadAnalyticsData = async () => {
  if (route.params.companyId) {
    await scheduleStore.loadAvailableAlgorithms(route.params.companyId)
    await scheduleStore.loadScheduleData(
      route.params.companyId,
      currentYear.value,
      currentMonth.value,
      scheduleStore.selectedAlgorithm
    )
    await loadAlgorithmKPIs()
  }
}

const createCharts = async () => {
  await nextTick()
  
  // Coverage Chart
  if (coverageChart.value) {
    const ctx = coverageChart.value.getContext('2d')
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Frühschicht', 'Spätschicht', 'Nachtschicht'],
        datasets: [{
          label: 'Abdeckung (%)',
          data: [85, 92, 78],
          backgroundColor: [
            'rgba(52, 152, 219, 0.8)',
            'rgba(39, 174, 96, 0.8)',
            'rgba(52, 73, 94, 0.8)'
          ],
          borderColor: [
            'rgba(52, 152, 219, 1)',
            'rgba(39, 174, 96, 1)',
            'rgba(52, 73, 94, 1)'
          ],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            max: 100
          }
        }
      }
    })
  }
  
  // Distribution Chart
  if (distributionChart.value) {
    const ctx = distributionChart.value.getContext('2d')
    new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Vollständig besetzt', 'Unterbesetzt', 'Überbesetzt'],
        datasets: [{
          data: [
            coverageStats.value.fully_staffed || 0,
            coverageStats.value.understaffed || 0,
            coverageStats.value.overstaffed || 0
          ],
          backgroundColor: [
            'rgba(39, 174, 96, 0.8)',
            'rgba(231, 76, 60, 0.8)',
            'rgba(243, 156, 18, 0.8)'
          ],
          borderColor: [
            'rgba(39, 174, 96, 1)',
            'rgba(231, 76, 60, 1)',
            'rgba(243, 156, 18, 1)'
          ],
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom'
          }
        }
      }
    })
  }
}

const formatNumber = (num) => {
  if (num === null || num === undefined) return '0'
  return parseFloat(num).toFixed(3).replace(/\.?0+$/, '')
}

const formatDate = (date) => {
  // Implementation of formatDate function
}

// Update getBestWorstForKPI and getBestWorstCoverage to return arrays of algorithms with best/worst values
const getBestWorstForKPI = (kpi) => {
  const entries = Object.entries(algorithmKPIs.value)
    .map(([alg, a]) => ({ alg, value: a && typeof a[kpi] === 'number' ? a[kpi] : null }))
    .filter(e => e.value !== null && !isNaN(e.value))
  if (!entries.length) return { best: [], worst: [] }
  let bestValue, worstValue
  if (kpi === 'constraint_violations' || kpi === 'gini_coefficient' || kpi === 'hours_std_dev' || kpi === 'min_hours') {
    bestValue = Math.min(...entries.map(e => e.value))
    worstValue = Math.max(...entries.map(e => e.value))
  } else {
    bestValue = Math.max(...entries.map(e => e.value))
    worstValue = Math.min(...entries.map(e => e.value))
  }
  return {
    best: entries.filter(e => e.value === bestValue).map(e => e.alg),
    worst: entries.filter(e => e.value === worstValue).map(e => e.alg)
  }
}

const getBestWorstCoverage = () => {
  const entries = Object.entries(algorithmKPIs.value)
    .map(([alg, a]) => ({
      alg,
      value: a && a.coverage_rates ? Object.values(a.coverage_rates).reduce((a1, b1) => a1 + b1, 0) / Object.values(a.coverage_rates).length : null
    }))
    .filter(e => e.value !== null && !isNaN(e.value))
  if (!entries.length) return { best: [], worst: [] }
  const bestValue = Math.max(...entries.map(e => e.value))
  const worstValue = Math.min(...entries.map(e => e.value))
  return {
    best: entries.filter(e => e.value === bestValue).map(e => e.alg),
    worst: entries.filter(e => e.value === worstValue).map(e => e.alg)
  }
}

onMounted(async () => {
  await loadAnalyticsData()
  await createCharts()
})

watch(() => route.params.companyId, loadAnalyticsData)
watch(() => scheduleStore.selectedAlgorithm, loadAnalyticsData)
watch([currentYear, currentMonth], loadAnalyticsData)
watch(coverageStats, createCharts, { deep: true })
watch([currentYear, currentMonth], loadAlgorithmKPIs)
</script>

<style scoped>
.algorithm-stats {
  margin-top: 1rem;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.stat-label {
  font-weight: 500;
  color: var(--text-muted);
}

.stat-value {
  font-weight: 600;
  color: var(--text-color);
}

.chart-container {
  position: relative;
}
</style> 