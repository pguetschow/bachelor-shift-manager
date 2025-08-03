<template>
  <div class="container">
    <!-- Header -->
    <div class="row mb-4">
      <div class="col">
        <h2 class="mb-3">
          <i class="bi bi-person text-primary"></i>
          Mitarbeiteransicht - {{ employee?.name || 'Laden...' }}
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
            <li class="breadcrumb-item active" aria-current="page">Mitarbeiter</li>
          </ol>
        </nav>
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

    <!-- Employee Content -->
    <div v-else-if="employee">
      <!-- Employee Info Card -->
      <div class="row mb-4">
        <div class="col-lg-8">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-person-circle"></i> Mitarbeiterinformationen
              </h5>
            </div>
            <div class="card-body">
              <div class="row">
                <div class="col-md-6">
                  <div class="employee-info-item">
                    <span class="label">Name:</span>
                    <span class="value">{{ employee.name }}</span>
                  </div>
                  <div class="employee-info-item">
                    <span class="label">Position:</span>
                    <span class="value">{{ employee.position || 'Mitarbeiter' }}</span>
                  </div>
                  <div class="employee-info-item">
                    <span class="label">Max. Stunden/Woche:</span>
                    <span class="value">{{ employee.max_hours_per_week }}h</span>
                  </div>
                </div>
                <div class="col-md-6">
                  <div class="employee-info-item">
                    <span class="label">Aktuelle Stunden:</span>
                    <span class="value">{{ formatNumber(currentHours) }}h</span>
                  </div>
                  <div class="employee-info-item">
                    <span class="label">Geplante Schichten:</span>
                    <span class="value">{{ scheduledShifts }}</span>
                  </div>
                  <div class="employee-info-item">
                    <span class="label">Durchschnitt/Shift:</span>
                    <span class="value">{{ formatNumber(employeeStats.average_hours_per_shift) }}h</span>
                  </div>
                  <div class="employee-info-item">
                    <span class="label">Bevorzugte Schichten:</span>
                    <span class="value">
                      <span 
                        v-for="shift in employee.preferred_shifts" 
                        :key="shift"
                        class="badge bg-info me-1"
                      >
                        {{ getShiftDisplayName(shift) }}
                      </span>
                      <span v-if="!employee.preferred_shifts || employee.preferred_shifts.length === 0" class="text-muted">
                        Keine Präferenzen
                      </span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div class="col-lg-4">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-graph-up"></i> Statistiken
              </h5>
            </div>
            <div class="card-body">
              <div class="stat-item">
                <span class="stat-label">Aktuelle Stunden:</span>
                <span class="stat-value">{{ formatNumber(currentHours) }}h</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">Geplante Schichten:</span>
                <span class="stat-value">{{ scheduledShifts }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">Auslastung:</span>
                <span class="stat-value">{{ formatNumber(employeeStats.utilization_percentage) }}%</span>
              </div>
              <div class="progress mt-3">
                <div 
                  class="progress-bar" 
                  :class="getUtilizationClass(employeeStats.utilization_percentage)"
                  :style="{ width: Math.min(employeeStats.utilization_percentage, 100) + '%' }"
                ></div>
              </div>
            </div>
          </div>
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

      <!-- Employee Schedule -->
      <div class="row mb-4">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-calendar3"></i> Monatsplan
              </h5>
            </div>
            <div class="card-body">
              <div class="table-responsive">
                <table class="table table-hover">
                  <thead>
                    <tr>
                      <th>Datum</th>
                      <th>Wochentag</th>
                      <th>Schicht</th>
                      <th>Zeit</th>
                      <th>Stunden</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="assignment in employeeSchedule" :key="assignment.id">
                      <td>
                        <strong>{{ formatDate(assignment.date) }}</strong>
                      </td>
                      <td>{{ getDayOfWeek(assignment.date) }}</td>
                      <td>
                        <span class="badge" :class="getShiftBadgeClass(assignment.shift.name)">
                          {{ getShiftDisplayName(assignment.shift.name) }}
                        </span>
                      </td>
                      <td>
                        {{ formatTime(assignment.shift.start_time) }} - {{ formatTime(assignment.shift.end_time) }}
                      </td>
                      <td>{{ calculateShiftHours(assignment.shift) }}h</td>
                      <td>
                        <span class="badge bg-success">Geplant</span>
                      </td>
                    </tr>
                    <tr v-if="employeeSchedule.length === 0">
                      <td colspan="6" class="text-center text-muted">
                        Keine Schichten für diesen Monat geplant
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Yearly Overview -->
      <div class="row mb-4">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-calendar-year"></i> Jahresübersicht {{ currentYear }}
              </h5>
            </div>
            <div class="card-body">
              <div v-if="!yearlyData" class="text-center">
                <button @click="loadYearlyData" class="btn btn-primary">
                  <i class="bi bi-download"></i> Jahresdaten laden
                </button>
              </div>
              <div v-else>
                <div class="row mb-4">
                  <div class="col-md-3">
                    <div class="stat-item">
                      <span class="stat-label">Jahresstunden:</span>
                      <span class="stat-value">{{ formatNumber(yearlyData.yearly_statistics.total_hours) }}h</span>
                    </div>
                  </div>
                  <div class="col-md-3">
                    <div class="stat-item">
                      <span class="stat-label">Jahresschichten:</span>
                      <span class="stat-value">{{ yearlyData.yearly_statistics.total_shifts }}</span>
                    </div>
                  </div>
                  <div class="col-md-3">
                    <div class="stat-item">
                      <span class="stat-label">Max. Jahresstunden (52 Wochen):</span>
                      <span class="stat-value">{{ formatNumber(yearlyData.yearly_statistics.max_yearly_hours) }}h</span>
                    </div>
                  </div>
                  <div class="col-md-3">
                    <div class="stat-item">
                      <span class="stat-label">Jahresauslastung:</span>
                      <span class="stat-value" :class="getYearlyUtilizationClass(yearlyData.yearly_statistics.yearly_utilization_percentage)">
                        {{ formatNumber(yearlyData.yearly_statistics.yearly_utilization_percentage) }}%
                      </span>
                    </div>
                  </div>
                </div>
                
                <!-- Yearly Utilization Progress Bar -->
                <div class="row mb-4">
                  <div class="col-12">
                    <div class="utilization-progress">
                      <div class="d-flex justify-content-between mb-2">
                        <span class="text-muted">Jahresauslastung</span>
                        <span class="text-muted">{{ formatNumber(yearlyData.yearly_statistics.total_hours) }}h / {{ formatNumber(yearlyData.yearly_statistics.max_yearly_hours) }}h</span>
                      </div>
                      <div class="progress" style="height: 20px;">
                        <div 
                          class="progress-bar" 
                          :class="getUtilizationClass(yearlyData.yearly_statistics.yearly_utilization_percentage)"
                          :style="{ width: Math.min(yearlyData.yearly_statistics.yearly_utilization_percentage, 100) + '%' }"
                        >
                          {{ formatNumber(yearlyData.yearly_statistics.yearly_utilization_percentage) }}%
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <!-- Monthly Chart -->
                <div class="chart-container" style="height: 300px;">
                  <canvas ref="yearlyChart"></canvas>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Workload Chart -->
      <div class="row">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-bar-chart"></i> Arbeitslast pro Woche
              </h5>
            </div>
            <div class="card-body">
              <div v-if="!weeklyWorkload || weeklyWorkload.length === 0" class="text-center text-muted py-4">
                <i class="bi bi-bar-chart" style="font-size: 3rem; opacity: 0.3;"></i>
                <p class="mt-3">Keine Wochenarbeitslast-Daten für diesen Monat verfügbar</p>
                <small>Die Arbeitslast wird basierend auf den geplanten Schichten für diesen Monat berechnet.</small>
              </div>
              <div v-else>
                <div class="chart-container" style="height: 300px;">
                  <canvas ref="workloadChart"></canvas>
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
import { computed, onMounted, watch, ref, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { format, parseISO } from 'date-fns'
import { de } from 'date-fns/locale'
import { Chart, registerables } from 'chart.js'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import { KPICalculator } from '@/services/kpiCalculator'

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

const currentMonthName = computed(() => {
  const date = new Date(currentYear.value, currentMonth.value - 1)
  return format(date, 'MMMM', { locale: de })
})

// Chart reference
const workloadChart = ref(null)
const yearlyChart = ref(null)
const yearlyData = ref(null)

// Real-time data storage
const employeeData = ref(null)
const employeeSchedule = ref([])
const employeeStats = ref({})
const weeklyWorkload = ref([])

// Computed properties for real-time calculations
const employee = computed(() => employeeData.value?.employee || {})
const currentHours = computed(() => employeeStats.value.total_hours || 0)
const scheduledShifts = computed(() => employeeStats.value.total_shifts || 0)

// KPI Calculator instance
const kpiCalculator = computed(() => {
  if (company.value) {
    return new KPICalculator(company.value)
  }
  return null
})

const formatNumber = (num) => {
  if (num === null || num === undefined) return '0'
  return parseFloat(num).toFixed(3).replace(/\.?0+$/, '')
}

const formatDate = (dateString) => {
  return format(parseISO(dateString), 'dd.MM.yyyy', { locale: de })
}

const getDayOfWeek = (dateString) => {
  return format(parseISO(dateString), 'EEEE', { locale: de })
}

const formatTime = (timeString) => {
  if (!timeString) return ''
  const time = parseISO(`2000-01-01T${timeString}`)
  return format(time, 'HH:mm')
}

const calculateShiftHours = (shift) => {
  if (!shift.start_time || !shift.end_time) return 0
  
  const start = parseISO(`2000-01-01T${shift.start_time}`)
  const end = parseISO(`2000-01-01T${shift.end_time}`)
  
  // Handle overnight shifts
  let hours = (end - start) / (1000 * 60 * 60)
  if (hours < 0) hours += 24
  
  return parseFloat(formatNumber(hours))
}

const getShiftDisplayName = (shiftName) => {
  const shiftMap = {
    'EarlyShift': 'Frühschicht',
    'MorningShift': 'Morgenschicht',
    'LateShift': 'Spätschicht',
    'NightShift': 'Nachtschicht'
    'SupportShift': 'Unterstützungsschicht'
  }
  return shiftMap[shiftName] || shiftName
}

const getShiftBadgeClass = (shiftName) => {
  const shiftNameLower = shiftName.toLowerCase()
  if (shiftNameLower.includes('früh') || shiftNameLower.includes('early')) {
    return 'bg-primary'
  } else if (shiftNameLower.includes('spät') || shiftNameLower.includes('late')) {
    return 'bg-success'
  } else if (shiftNameLower.includes('nacht') || shiftNameLower.includes('night')) {
    return 'bg-dark'
  } else if (shiftNameLower.includes('tag') || shiftNameLower.includes('day') || shiftNameLower.includes('morning')) {
    return 'bg-warning'
  }
  return 'bg-secondary'
}

const getUtilizationClass = (percentage) => {
  if (percentage >= 100) return 'bg-danger'
  if (percentage >= 80) return 'bg-warning'
  return 'bg-success'
}

const getYearlyUtilizationClass = (percentage) => {
  if (percentage >= 100) return 'text-danger fw-bold'
  if (percentage >= 80) return 'text-warning fw-bold'
  return 'text-success fw-bold'
}

const previousMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value - 2)
  scheduleStore.setCurrentDate(newDate)
  loadEmployeeData()
}

const nextMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value)
  scheduleStore.setCurrentDate(newDate)
  loadEmployeeData()
}

const loadEmployeeData = async () => {
  if (route.params.companyId && route.params.employeeId && kpiCalculator.value) {
    try {
      // Load raw schedule data from API
      const response = await fetch(`/api/companies/${route.params.companyId}/employees/${route.params.employeeId}/schedule/?year=${currentYear.value}&month=${currentMonth.value}&algorithm=${scheduleStore.selectedAlgorithm || ''}`)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      // Store raw data
      employeeData.value = data
      employeeSchedule.value = data.schedule_data || []
      
      // Calculate KPIs in real-time
      const stats = kpiCalculator.value.calculateEmployeeStatistics(
        data.employee,
        data.schedule_data || [],
        currentYear.value,
        currentMonth.value
      )
      
      employeeStats.value = stats
      weeklyWorkload.value = stats.weekly_workload || []
      
      // Create chart after data is loaded
      await nextTick()
      setTimeout(() => {
        createWorkloadChart()
      }, 100)
    } catch (error) {
      console.error('Error loading employee data:', error)
      // Set empty data on error
      employeeData.value = null
      employeeSchedule.value = []
      employeeStats.value = {}
      weeklyWorkload.value = []
    }
  }
}

const loadYearlyData = async () => {
  if (route.params.companyId && route.params.employeeId && kpiCalculator.value) {
    try {
      // Load raw yearly data from API
      const response = await fetch(`/api/companies/${route.params.companyId}/employees/${route.params.employeeId}/yearly/?year=${currentYear.value}&algorithm=${scheduleStore.selectedAlgorithm || ''}`)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      // Calculate yearly KPIs in real-time
      const yearlyStats = kpiCalculator.value.calculateYearlyStatistics(
        data.employee,
        data.schedule_data || [],
        currentYear.value
      )
      
      yearlyData.value = {
        ...data,
        yearly_statistics: yearlyStats,
        monthly_breakdown: yearlyStats.monthly_breakdown
      }
      
      await createYearlyChart()
    } catch (error) {
      console.error('Error loading yearly data:', error)
      // Set empty data on error
      yearlyData.value = null
    }
  }
}

const createWorkloadChart = async () => {
  await nextTick()
  
  // Check if Chart.js is available
  if (typeof Chart === 'undefined') {
    console.error('Chart.js is not loaded')
    return
  }
  
  if (workloadChart.value) {
    // Destroy existing chart if it exists
    if (window.workloadChartInstance) {
      window.workloadChartInstance.destroy()
    }
    
    // Check if we have data
    if (!weeklyWorkload.value || weeklyWorkload.value.length === 0) {
      return
    }
    
    try {
      const ctx = workloadChart.value.getContext('2d')
      
      window.workloadChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: weeklyWorkload.value.map((_, index) => `Woche ${index + 1}`),
          datasets: [{
            label: 'Arbeitsstunden',
            data: weeklyWorkload.value,
            backgroundColor: 'rgba(52, 152, 219, 0.8)',
            borderColor: 'rgba(52, 152, 219, 1)',
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: {
              beginAtZero: true,
              max: Math.max(...weeklyWorkload.value, 50),
              title: {
                display: true,
                text: 'Stunden'
              }
            },
            x: {
              title: {
                display: true,
                text: 'Woche'
              }
            }
          },
          plugins: {
            legend: {
              display: false
            }
          }
        }
      })
    } catch (error) {
      console.error('Error creating workload chart:', error)
    }
  }
}

const createYearlyChart = async () => {
  await nextTick()
  
  // Check if Chart.js is available
  if (typeof Chart === 'undefined') {
    console.error('Chart.js is not loaded')
    return
  }
  
  if (yearlyChart.value && yearlyData.value) {
    // Destroy existing chart if it exists
    if (window.yearlyChartInstance) {
      window.yearlyChartInstance.destroy()
    }
    
    const ctx = yearlyChart.value.getContext('2d')
    const monthlyData = yearlyData.value.monthly_breakdown
    
    window.yearlyChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [
          'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
          'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'
        ],
        datasets: [{
          label: 'Stunden',
          data: monthlyData.hours,
          backgroundColor: 'rgba(52, 152, 219, 0.8)',
          borderColor: 'rgba(52, 152, 219, 1)',
          borderWidth: 1
        }, {
          label: 'Schichten',
          data: monthlyData.shifts,
          backgroundColor: 'rgba(231, 76, 60, 0.8)',
          borderColor: 'rgba(231, 76, 60, 1)',
          borderWidth: 1,
          yAxisID: 'y1'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            type: 'linear',
            display: true,
            position: 'left',
            title: {
              display: true,
              text: 'Stunden'
            }
          },
          y1: {
            type: 'linear',
            display: true,
            position: 'right',
            title: {
              display: true,
              text: 'Schichten'
            },
            grid: {
              drawOnChartArea: false,
            },
          },
          x: {
            title: {
              display: true,
              text: 'Monat'
            }
          }
        },
        plugins: {
          legend: {
            display: true,
            position: 'top'
          }
        }
      }
    })
  }
}

onMounted(async () => {
  await loadEmployeeData()
  await loadYearlyData()
  // Ensure chart is created after everything is loaded
  setTimeout(() => {
    createWorkloadChart()
  }, 200)
})

watch(() => route.params.employeeId, async () => {
  await loadEmployeeData()
  await loadYearlyData()
})
watch(() => route.params.companyId, async () => {
  await loadEmployeeData()
  await loadYearlyData()
})
watch([currentYear, currentMonth], async () => {
  await loadEmployeeData()
  await loadYearlyData()
})
watch(weeklyWorkload, async (newData) => {
  if (newData && newData.length > 0) {
    setTimeout(() => {
      createWorkloadChart()
    }, 100)
  }
}, { deep: true })

// Watch for algorithm changes to recalculate KPIs
watch(() => scheduleStore.selectedAlgorithm, async () => {
  await loadEmployeeData()
  await loadYearlyData()
})
</script>

<style scoped>
.employee-info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.employee-info-item .label {
  font-weight: 500;
  color: var(--text-muted);
}

.employee-info-item .value {
  font-weight: 600;
  color: var(--text-color);
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
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

.utilization-progress {
  background-color: #f8f9fa;
  padding: 1rem;
  border-radius: 0.375rem;
  border: 1px solid #dee2e6;
}

.utilization-progress .progress {
  background-color: #e9ecef;
  border-radius: 0.375rem;
}

.utilization-progress .progress-bar {
  font-weight: 600;
  font-size: 0.875rem;
  line-height: 1.25;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-value.bg-success {
  color: #198754 !important;
  font-weight: 700;
}

.stat-value.bg-warning {
  color: #fd7e14 !important;
  font-weight: 700;
}

.stat-value.bg-danger {
  color: #dc3545 !important;
  font-weight: 700;
}
</style> 