<template>
  <div class="container">
    <!-- Header -->
    <div class="row mb-4">
      <div class="col">
        <h2 class="mb-3">
          <i class="bi bi-speedometer2 text-primary"></i>
          Dashboard - {{ company?.name }}
        </h2>
        <nav aria-label="breadcrumb">
          <ol class="breadcrumb">
            <li class="breadcrumb-item">
              <router-link to="/">Unternehmen</router-link>
            </li>
            <li class="breadcrumb-item active" aria-current="page">Dashboard</li>
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
            {{ currentMonthName }} {{ scheduleStore.currentYear }}
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

    <!-- Dashboard Content -->
    <div v-else>
      <!-- Statistics Cards -->
      <div class="row mb-4">
        <div class="col-md-3 mb-3">
          <div class="card stat-card">
            <div class="card-body">
              <div class="d-flex justify-content-between">
                <div>
                  <h6 class="card-subtitle mb-2 text-muted">Mitarbeiter</h6>
                  <h3 class="card-title mb-0">{{ coverageStats.total_employees || 0 }}</h3>
                </div>
                <div class="text-primary">
                  <i class="bi bi-people-fill fs-1"></i>
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
                  <h6 class="card-subtitle mb-2 text-muted">Schichten</h6>
                  <h3 class="card-title mb-0">{{ coverageStats.total_shifts || 0 }}</h3>
                </div>
                <div class="text-success">
                  <i class="bi bi-calendar-check fs-1"></i>
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
                  <h6 class="card-subtitle mb-2 text-muted">Arbeitstage</h6>
                  <h3 class="card-title mb-0">{{ coverageStats.working_days || 0 }}</h3>
                </div>
                <div class="text-warning">
                  <i class="bi bi-calendar-week fs-1"></i>
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
                  <h6 class="card-subtitle mb-2 text-muted">Abdeckung</h6>
                  <h3 class="card-title mb-0">{{ formatNumber(coverageStats.coverage_percentage || 0) }}%</h3>
                </div>
                <div class="text-info">
                  <i class="bi bi-pie-chart fs-1"></i>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Coverage Overview -->
      <div class="row mb-4">
        <div class="col-lg-8">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-bar-chart"></i> Schichtabdeckung
              </h5>
            </div>
            <div class="card-body">
              <div v-if="coverageStats.shifts && coverageStats.shifts.length === 0" class="text-muted text-center">
                Keine Schichtdaten verfügbar
              </div>
              <div v-else class="table-responsive">
                <table class="table table-hover">
                  <thead>
                    <tr>
                      <th>Schicht</th>
                      <th>Zeit</th>
                      <th>Min/Max Personal</th>
                      <th>Durchschn. Besetzung</th>
                      <th>Abdeckung</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="stat in coverageStats.shifts" :key="stat.shift.id">
                      <td>
                        <span class="shift-badge" :class="getShiftBadgeClass(stat.shift.name)">
                          {{ getShiftDisplayName(stat.shift.name) }}
                        </span>
                      </td>
                      <td>{{ formatTime(stat.shift.start_time) }} - {{ formatTime(stat.shift.end_time) }}</td>
                      <td>{{ stat.shift.min_staff }} / {{ stat.shift.max_staff }}</td>
                      <td>{{ stat.avg_staff }}</td>
                      <td>
                        <div class="progress" style="height: 20px;">
                          <div 
                            class="progress-bar" 
                            :class="getProgressBarClass(stat.coverage_percentage)"
                            role="progressbar"
                            :style="{ width: formatNumber(stat.coverage_percentage) + '%' }"
                            :aria-valuenow="formatNumber(stat.coverage_percentage)"
                            aria-valuemin="0"
                            aria-valuemax="100"
                          >
                            {{ formatNumber(stat.coverage_percentage) }}%
                          </div>
                        </div>
                      </td>
                      <td>
                        <span class="badge" :class="getStatusBadgeClass(stat.status)">
                          {{ getStatusText(stat.status) }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <div class="col-lg-4">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-trophy"></i> Top Mitarbeiter (Stunden)
              </h5>
            </div>
            <div class="card-body">
              <div v-if="topEmployees.length === 0" class="text-muted text-center">
                Keine Daten verfügbar
              </div>
              <div v-else class="list-group list-group-flush">
                <div 
                  v-for="employee in topEmployees.slice(0, 5)" 
                  :key="employee.id"
                  class="list-group-item d-flex justify-content-between align-items-center"
                >
                  <div>
                    <i class="bi bi-person-circle"></i> {{ employee.name }}
                  </div>
                  <span class="badge bg-primary rounded-pill">{{ formatNumber(employee.hours) }}h</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="row">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-lightning"></i> Schnellaktionen
              </h5>
            </div>
            <div class="card-body">
              <div class="row g-3">
                <div class="col-md-3">
                  <router-link 
                    :to="{ name: 'month-view', params: { companyId: $route.params.companyId } }"
                    class="btn btn-outline-primary w-100"
                  >
                    <i class="bi bi-calendar-month"></i>
                    Monatsansicht
                  </router-link>
                </div>
                <div class="col-md-3">
                  <router-link 
                    :to="{ name: 'analytics', params: { companyId: $route.params.companyId } }"
                    class="btn btn-outline-success w-100"
                  >
                    <i class="bi bi-graph-up"></i>
                    Analysen
                  </router-link>
                </div>
                <div class="col-md-3">
                  <button class="btn btn-outline-warning w-100">
                    <i class="bi bi-download"></i>
                    Export
                  </button>
                </div>
                <div class="col-md-3">
                  <button class="btn btn-outline-info w-100">
                    <i class="bi bi-gear"></i>
                    Einstellungen
                  </button>
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
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'

const route = useRoute()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()

const company = computed(() => companyStore.currentCompany)
const loading = computed(() => scheduleStore.loading)
const error = computed(() => scheduleStore.error)
const coverageStats = computed(() => scheduleStore.getCoverageStats())
const topEmployees = computed(() => scheduleStore.getTopEmployees())

const currentMonthName = computed(() => {
  const date = new Date(scheduleStore.currentYear, scheduleStore.currentMonth - 1)
  return format(date, 'MMMM', { locale: de })
})

const previousMonth = () => {
  const newDate = new Date(scheduleStore.currentYear, scheduleStore.currentMonth - 2)
  scheduleStore.setCurrentDate(newDate)
  loadDashboardData()
}

const nextMonth = () => {
  const newDate = new Date(scheduleStore.currentYear, scheduleStore.currentMonth)
  scheduleStore.setCurrentDate(newDate)
  loadDashboardData()
}

const formatNumber = (num) => {
  if (num === null || num === undefined) return '0'
  return parseFloat(num).toFixed(3).replace(/\.?0+$/, '')
}

const getPercentage = (value, total) => {
  if (!total || total === 0) return 0
  return parseFloat(formatNumber((value / total) * 100))
}

const formatTime = (timeString) => {
  if (!timeString) return ''
  // Remove seconds if present and format as HH:mm
  return timeString.substring(0, 5)
}

const getShiftDisplayName = (shiftName) => {
  const shiftMap = {
    'EarlyShift': 'Frühschicht',
    'MorningShift': 'Morgenschicht',
    'LateShift': 'Spätschicht',
    'NightShift': 'Nachtschicht'
  }
  return shiftMap[shiftName] || shiftName
}

const getShiftBadgeClass = (shiftName) => {
  const classMap = {
    'EarlyShift': 'shift-early',
    'MorningShift': 'shift-morning',
    'LateShift': 'shift-late',
    'NightShift': 'shift-night'
  }
  return classMap[shiftName] || 'shift-default'
}

const getProgressBarClass = (coveragePercentage) => {
  if (coveragePercentage < 80) return 'bg-danger'
  if (coveragePercentage < 95) return 'bg-warning'
  return 'bg-success'
}

const getStatusBadgeClass = (status) => {
  switch (status) {
    case 'ok': return 'bg-success'
    case 'understaffed': return 'bg-danger'
    case 'overstaffed': return 'bg-warning'
    default: return 'bg-primary'
  }
}

const getStatusText = (status) => {
  switch (status) {
    case 'ok': return 'OK'
    case 'understaffed': return 'Unterbesetzt'
    case 'overstaffed': return 'Überbesetzt'
    default: return 'Voll'
  }
}

const loadDashboardData = async () => {
  if (route.params.companyId) {
    await scheduleStore.loadAvailableAlgorithms(route.params.companyId)
    await scheduleStore.loadScheduleData(
      route.params.companyId,
      scheduleStore.currentYear,
      scheduleStore.currentMonth,
      scheduleStore.selectedAlgorithm
    )
  }
}

onMounted(loadDashboardData)

watch(() => route.params.companyId, loadDashboardData)
watch(() => scheduleStore.selectedAlgorithm, loadDashboardData)
</script>

<style scoped>
.shift-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  display: inline-block;
}

.progress {
  border-radius: 0.25rem;
}

.table th {
  border-top: none;
  font-weight: 600;
  color: var(--text-muted);
}

.table td {
  vertical-align: middle;
}

.list-group-item {
  border-left: none;
  border-right: none;
}

.list-group-item:first-child {
  border-top: none;
}

.list-group-item:last-child {
  border-bottom: none;
}
</style> 