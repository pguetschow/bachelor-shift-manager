<template>
  <div class="container">
    <!-- Header -->
    <div class="row mb-4">
      <div class="col">
        <h2 class="mb-3">
          <i class="bi bi-people text-primary"></i>
          Mitarbeiter - {{ company?.name }}
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

    <!-- Employees Table -->
    <div v-else class="row">
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            <h5 class="card-title mb-0">
              <i class="bi bi-table"></i> Mitarbeiterübersicht
            </h5>
          </div>
          <div class="card-body">
            <div class="table-responsive">
              <table class="table table-hover">
                <thead>
                  <tr>
                    <th 
                      @click="sortBy('name')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'name' }"
                    >
                      Name
                      <i class="bi" :class="getSortIcon('name')"></i>
                    </th>
                    <th 
                      @click="sortBy('monthly_stats.possible_hours')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'monthly_stats.possible_hours' }"
                    >
                      Mögliche Stunden (Monat)
                      <i class="bi" :class="getSortIcon('monthly_stats.possible_hours')"></i>
                    </th>
                    <th 
                      @click="sortBy('monthly_stats.worked_hours')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'monthly_stats.worked_hours' }"
                    >
                      Gearbeitete Stunden (Monat)
                      <i class="bi" :class="getSortIcon('monthly_stats.worked_hours')"></i>
                    </th>
                    <th 
                      @click="sortBy('monthly_stats.absences')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'monthly_stats.absences' }"
                    >
                      Fehltage (Monat)
                      <i class="bi" :class="getSortIcon('monthly_stats.absences')"></i>
                    </th>
                    <th 
                      @click="sortBy('yearly_stats.worked_hours')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'yearly_stats.worked_hours' }"
                    >
                      Gearbeitete Stunden (Jahr)
                      <i class="bi" :class="getSortIcon('yearly_stats.worked_hours')"></i>
                    </th>
                    <th 
                      @click="sortBy('monthly_stats.utilization_percentage')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'monthly_stats.utilization_percentage' }"
                    >
                      Auslastung (Monat)
                      <i class="bi" :class="getSortIcon('monthly_stats.utilization_percentage')"></i>
                    </th>
                    <th 
                      @click="sortBy('yearly_stats.utilization_percentage')" 
                      class="sortable-header"
                      :class="{ 'sorted': sortKey === 'yearly_stats.utilization_percentage' }"
                    >
                      Auslastung (Jahr)
                      <i class="bi" :class="getSortIcon('yearly_stats.utilization_percentage')"></i>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="employee in sortedEmployees" :key="employee.id">
                    <td>
                      <router-link 
                        :to="{ name: 'employee-view', params: { companyId: $route.params.companyId, employeeId: employee.id } }"
                        class="text-decoration-none"
                      >
                        <strong class="text-primary">{{ employee.name }}</strong>
                      </router-link>
                      <br>
                      <small class="text-muted">{{ employee.position }}</small>
                    </td>
                    <td>{{ formatNumber(employee.monthly_stats.possible_hours) }}h</td>
                    <td>
                      <span :class="getHoursClass(employee.monthly_stats.worked_hours, employee.monthly_stats.possible_hours)">
                        {{ formatNumber(employee.monthly_stats.worked_hours) }}h
                      </span>
                    </td>
                    <td>
                      <span :class="getAbsenceClass(employee.monthly_stats.absences)">
                        {{ employee.monthly_stats.absences }}
                      </span>
                    </td>
                    <td>{{ formatNumber(employee.yearly_stats.worked_hours) }}h</td>
                    <td>
                      <span :class="getUtilizationClass(employee.monthly_stats.utilization_percentage)">
                        {{ formatNumber(employee.monthly_stats.utilization_percentage) }}%
                      </span>
                    </td>
                    <td>
                      <span :class="getUtilizationClass(employee.yearly_stats.utilization_percentage)">
                        {{ formatNumber(employee.yearly_stats.utilization_percentage) }}%
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

    <!-- Summary Statistics -->
    <div class="row mt-4">
      <div class="col-md-3 mb-3">
        <div class="card stat-card">
          <div class="card-body">
            <div class="d-flex justify-content-between">
              <div>
                <h6 class="card-subtitle mb-2 text-muted">Gesamtmitarbeiter</h6>
                <h3 class="card-title mb-0">{{ employees.length }}</h3>
              </div>
              <div class="text-primary">
                <i class="bi bi-people fs-1"></i>
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
                <h6 class="card-subtitle mb-2 text-muted">Durchschnittliche Auslastung</h6>
                <h3 class="card-title mb-0">{{ formatNumber(averageUtilization) }}%</h3>
              </div>
              <div class="text-success">
                <i class="bi bi-graph-up fs-1"></i>
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
                <h6 class="card-subtitle mb-2 text-muted">Gesamtstunden (Monat)</h6>
                <h3 class="card-title mb-0">{{ formatNumber(totalMonthlyHours) }}h</h3>
              </div>
              <div class="text-info">
                <i class="bi bi-clock fs-1"></i>
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
                <h6 class="card-subtitle mb-2 text-muted">Gesamtstunden (Jahr)</h6>
                <h3 class="card-title mb-0">{{ formatNumber(totalYearlyHours) }}h</h3>
              </div>
              <div class="text-warning">
                <i class="bi bi-calendar-year fs-1"></i>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch, ref } from 'vue'
import { useRoute } from 'vue-router'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import { analyticsAPI } from '@/services/api'

const route = useRoute()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()

const company = computed(() => companyStore.currentCompany)
const loading = ref(false)
const error = ref(null)
const employees = ref([])
const currentYear = computed(() => scheduleStore.currentYear)
const currentMonth = computed(() => scheduleStore.currentMonth)

// Sorting state
const sortKey = ref('name')
const sortOrder = ref('asc')

const currentMonthName = computed(() => {
  const date = new Date(currentYear.value, currentMonth.value - 1)
  return format(date, 'MMMM', { locale: de })
})

const sortedEmployees = computed(() => {
  if (!employees.value.length) return []
  
  return [...employees.value].sort((a, b) => {
    let aValue = getNestedValue(a, sortKey.value)
    let bValue = getNestedValue(b, sortKey.value)
    
    // Handle string values
    if (typeof aValue === 'string') {
      aValue = aValue.toLowerCase()
      bValue = bValue.toLowerCase()
    }
    
    if (sortOrder.value === 'asc') {
      return aValue > bValue ? 1 : -1
    } else {
      return aValue < bValue ? 1 : -1
    }
  })
})

const averageUtilization = computed(() => {
  if (!employees.value.length) return 0
  const total = employees.value.reduce((sum, emp) => sum + emp.monthly_stats.utilization_percentage, 0)
  return total / employees.value.length
})

const totalMonthlyHours = computed(() => {
  return employees.value.reduce((sum, emp) => sum + emp.monthly_stats.worked_hours, 0)
})

const totalYearlyHours = computed(() => {
  return employees.value.reduce((sum, emp) => sum + emp.yearly_stats.worked_hours, 0)
})

const getNestedValue = (obj, path) => {
  return path.split('.').reduce((current, key) => current?.[key], obj)
}

const sortBy = (key) => {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
}

const getSortIcon = (key) => {
  if (sortKey.value !== key) return 'bi-arrow-down-up'
  return sortOrder.value === 'asc' ? 'bi-arrow-up' : 'bi-arrow-down'
}

const getHoursClass = (worked, possible) => {
  const percentage = (worked / possible) * 100
  if (percentage >= 90) return 'text-success fw-bold'
  if (percentage >= 70) return 'text-warning'
  return 'text-danger'
}

const getAbsenceClass = (absences) => {
  if (absences === 0) return 'text-success'
  if (absences <= 3) return 'text-warning'
  return 'text-danger fw-bold'
}

const getUtilizationClass = (percentage) => {
  if (percentage >= 90) return 'text-success fw-bold'
  if (percentage >= 70) return 'text-warning'
  return 'text-danger'
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
  if (!route.params.companyId) return
  
  loading.value = true
  error.value = null
  
  try {
    const response = await analyticsAPI.getEmployeeStatistics(
      route.params.companyId,
      currentYear.value,
      currentMonth.value,
      scheduleStore.selectedAlgorithm
    )
    employees.value = response.data.employees
  } catch (err) {
    console.error('Error loading employee data:', err)
    error.value = 'Fehler beim Laden der Mitarbeiterdaten'
  } finally {
    loading.value = false
  }
}

const formatNumber = (num) => {
  if (num === null || num === undefined) return '0'
  return parseFloat(num).toFixed(2).replace(/\.?0+$/, '')
}

onMounted(async () => {
  await loadEmployeeData()
})

watch(() => route.params.companyId, loadEmployeeData)
watch(() => scheduleStore.selectedAlgorithm, loadEmployeeData)
watch([currentYear, currentMonth], loadEmployeeData)
</script>

<style scoped>
.sortable-header {
  cursor: pointer;
  user-select: none;
  position: relative;
}

.sortable-header:hover {
  background-color: rgba(0, 0, 0, 0.05);
}

.sortable-header.sorted {
  background-color: rgba(0, 123, 255, 0.1);
}

.sortable-header i {
  margin-left: 0.5rem;
  font-size: 0.8em;
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

.stat-card {
  transition: transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
}

/* Employee name link styles */
a.text-decoration-none strong {
  transition: color 0.2s ease;
}

a.text-decoration-none:hover strong {
  color: #0056b3 !important;
  text-decoration: underline;
}
</style> 