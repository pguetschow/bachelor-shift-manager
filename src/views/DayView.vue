<template>
  <div class="container">
    <!-- Header -->
    <div class="row mb-4">
      <div class="col">
        <h2 class="mb-3">
          <i class="bi bi-calendar-day text-primary"></i>
          Tagesansicht - {{ formatDate(selectedDate) }}
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
            <li class="breadcrumb-item">
              <router-link :to="{ name: 'month-view', params: { companyId: $route.params.companyId } }">
                Monatsansicht
              </router-link>
            </li>
            <li class="breadcrumb-item active" aria-current="page">Tagesansicht</li>
          </ol>
        </nav>
      </div>
    </div>

    <!-- Date Navigation -->
    <div class="row mb-4">
      <div class="col">
        <div class="d-flex justify-content-between align-items-center">
          <button 
            @click="previousDay" 
            class="btn btn-outline-primary"
          >
            <i class="bi bi-chevron-left"></i> Vorheriger Tag
          </button>
          
          <h4 class="mb-0">
            {{ formatDate(selectedDate) }}
          </h4>
          
          <button 
            @click="nextDay" 
            class="btn btn-outline-primary"
          >
            Nächster Tag <i class="bi bi-chevron-right"></i>
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

    <!-- Day Content -->
    <div v-else>
      <!-- Day Info Card -->
      <div class="row mb-4">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-info-circle"></i> Taginformationen
              </h5>
            </div>
            <div class="card-body">
              <div class="row">
                <div class="col-md-3">
                  <div class="day-info-item">
                    <span class="label">Datum:</span>
                    <span class="value">{{ formatDate(selectedDate) }}</span>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="day-info-item">
                    <span class="label">Wochentag:</span>
                    <span class="value">{{ getDayOfWeek(selectedDate) }}</span>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="day-info-item">
                    <span class="label">Typ:</span>
                    <span class="value">
                      <span 
                        v-if="isHoliday" 
                        class="badge bg-danger"
                      >
                        Feiertag
                      </span>
                      <span 
                        v-else-if="isSundayDay" 
                        class="badge bg-secondary"
                      >
                        Sonntag
                      </span>
                      <span 
                        v-else-if="isNonWorking" 
                        class="badge bg-warning"
                      >
                        Nicht-Arbeitstag
                      </span>
                      <span 
                        v-else 
                        class="badge bg-success"
                      >
                        Arbeitstag
                      </span>
                    </span>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="day-info-item">
                    <span class="label">Schichten:</span>
                    <span class="value">{{ totalShifts }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Shifts as Columns -->
      <div class="row">
        <div 
          v-for="shift in shifts" 
          :key="shift.id"
          class="col-md-6 col-lg-4 mb-4"
        >
          <div class="card shift-column-card">
            <div class="card-header" :class="getShiftColorClass(shift.name)">
              <div class="d-flex justify-content-between align-items-center">
                <h6 class="card-title mb-0">
                  {{ getShiftDisplayName(shift.name) }}
                </h6>
                <span 
                  class="badge"
                  :class="getStatusBadgeClass(shift.status)"
                >
                  {{ getStatusText(shift.status) }}
                </span>
              </div>
              <div class="shift-time mt-2">
                <i class="bi bi-clock"></i>
                {{ formatTime(shift.start_time) }} - {{ formatTime(shift.end_time) }}
              </div>
            </div>
            <div class="card-body">
              <!-- Staffing Info -->
              <div class="staffing-info mb-3">
                <div class="d-flex justify-content-between align-items-center">
                  <span class="label">Besetzung:</span>
                  <span class="value">{{ shift.assigned_count }}/{{ shift.max_staff }}</span>
                </div>
                <div class="progress mt-2">
                  <div 
                    class="progress-bar" 
                    :class="getProgressBarClass(shift.status)"
                    :style="{ width: getStaffingPercentage(shift) + '%' }"
                  ></div>
                </div>
                <div class="staffing-limits mt-1">
                  <small class="text-muted">
                    Min: {{ shift.min_staff }} | Max: {{ shift.max_staff }}
                  </small>
                </div>
              </div>

              <!-- Assigned Employees -->
              <div class="assigned-employees">
                <h6 class="section-title">Zugewiesene Mitarbeiter</h6>
                <div v-if="shift.assigned_employees.length === 0" class="text-muted text-center py-3">
                  <i class="bi bi-people"></i>
                  <div>Keine Mitarbeiter zugewiesen</div>
                </div>
                <div v-else class="employee-list">
                  <div 
                    v-for="employee in shift.assigned_employees" 
                    :key="employee.id"
                    class="employee-item"
                  >
                    <div class="employee-info" @click="navigateToEmployee(employee.id)">
                      <i class="bi bi-person-circle"></i>
                      <span class="employee-name">{{ employee.name }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- No Shifts Message -->
      <div v-if="shifts.length === 0" class="row">
        <div class="col-12">
          <div class="card">
            <div class="card-body text-center">
              <i class="bi bi-calendar-x fs-1 text-muted"></i>
              <h5 class="mt-3">Keine Schichten für diesen Tag</h5>
              <p class="text-muted">
                Für diesen Tag sind keine Schichten geplant oder es handelt sich um einen Feiertag/Nicht-Arbeitstag.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { format, parseISO, addDays, subDays, isSunday } from 'date-fns'
import { de } from 'date-fns/locale'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'

const route = useRoute()
const router = useRouter()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()

const company = computed(() => companyStore.currentCompany)
const loading = computed(() => scheduleStore.loading)
const error = computed(() => scheduleStore.error)

const selectedDate = ref(new Date())

// Parse date from route parameter
const parseDateFromRoute = () => {
  if (route.params.date) {
    try {
      selectedDate.value = parseISO(route.params.date)
    } catch (e) {
      console.error('Invalid date format:', route.params.date)
      selectedDate.value = new Date()
    }
  }
}

const formatDate = (date) => {
  return format(date, 'dd.MM.yyyy', { locale: de })
}

const getDayOfWeek = (date) => {
  return format(date, 'EEEE', { locale: de })
}

const formatTime = (timeString) => {
  if (!timeString) return ''
  const time = parseISO(`2000-01-01T${timeString}`)
  return format(time, 'HH:mm')
}

const isHoliday = computed(() => dayData.value.is_holiday || false)
const isSundayDay = computed(() => dayData.value.is_sunday || isSunday(selectedDate.value))
const isNonWorking = computed(() => dayData.value.is_non_working || false)

const scheduleData = computed(() => {
  const dateStr = format(selectedDate.value, 'yyyy-MM-dd')
  return scheduleStore.scheduleData.schedule_data?.[dateStr] || []
})

const dayData = computed(() => scheduleStore.dayScheduleData)

const shifts = computed(() => {
  return dayData.value.shifts || []
})

const totalShifts = computed(() => shifts.value.length)

const getShiftDisplayName = (shiftName) => {
  const shiftMap = {
    'EarlyShift': 'Frühschicht',
    'MorningShift': 'Morgenschicht',
    'LateShift': 'Spätschicht',
    'NightShift': 'Nachtschicht'
  }
  return shiftMap[shiftName] || shiftName
}

const getShiftColorClass = (shiftName) => {
  const shiftNameLower = shiftName.toLowerCase()
  if (shiftNameLower.includes('früh') || shiftNameLower.includes('early')) {
    return 'shift-early'
  } else if (shiftNameLower.includes('spät') || shiftNameLower.includes('late')) {
    return 'shift-late'
  } else if (shiftNameLower.includes('nacht') || shiftNameLower.includes('night')) {
    return 'shift-night'
  } else if (shiftNameLower.includes('tag') || shiftNameLower.includes('day') || shiftNameLower.includes('morning')) {
    return 'shift-morning'
  }
  // Default color for unknown shifts
  return 'shift-default'
}

const getProgressBarClass = (status) => {
  switch (status) {
    case 'ok': return 'bg-success'
    case 'understaffed': return 'bg-danger'
    case 'overstaffed': return 'bg-warning'
    case 'full': return 'bg-info'
    default: return 'bg-secondary'
  }
}

const getStatusBadgeClass = (status) => {
  switch (status) {
    case 'ok': return 'bg-success'
    case 'understaffed': return 'bg-danger'
    case 'overstaffed': return 'bg-warning'
    case 'full': return 'bg-info'
    default: return 'bg-secondary'
  }
}

const getStatusText = (status) => {
  switch (status) {
    case 'ok': return 'Vollständig besetzt'
    case 'understaffed': return 'Unterbesetzt'
    case 'overstaffed': return 'Überbesetzt'
    case 'full': return 'Voll besetzt'
    default: return 'Unbekannt'
  }
}

const formatNumber = (num) => {
  if (num === null || num === undefined) return '0'
  return parseFloat(num).toFixed(3).replace(/\.?0+$/, '')
}

const getStaffingPercentage = (shift) => {
  return parseFloat(formatNumber((shift.assigned_count / shift.max_staff) * 100))
}

const getShiftBadgeClass = (shiftName) => {
  switch (shiftName.toLowerCase()) {
    case 'frühschicht': return 'bg-primary'
    case 'spätschicht': return 'bg-success'
    case 'nachtschicht': return 'bg-dark'
    default: return 'bg-secondary'
  }
}

const previousDay = () => {
  selectedDate.value = subDays(selectedDate.value, 1)
  updateRoute()
}

const nextDay = () => {
  selectedDate.value = addDays(selectedDate.value, 1)
  updateRoute()
}

const updateRoute = () => {
  const dateStr = format(selectedDate.value, 'yyyy-MM-dd')
  router.push({
    name: 'day-view',
    params: {
      companyId: route.params.companyId,
      date: dateStr
    }
  })
}

const loadDayData = async () => {
  if (route.params.companyId) {
    const dateStr = format(selectedDate.value, 'yyyy-MM-dd')
    await scheduleStore.loadDayScheduleData(
      route.params.companyId,
      dateStr,
      scheduleStore.selectedAlgorithm
    )
  }
}

const navigateToEmployee = (employeeId) => {
  router.push({
    name: 'employee-view',
    params: {
      companyId: route.params.companyId,
      employeeId: employeeId
    }
  })
}

onMounted(() => {
  parseDateFromRoute()
  loadDayData()
})

watch(() => route.params.date, parseDateFromRoute)
watch(() => route.params.companyId, loadDayData)
</script>

<style scoped>
.day-info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.day-info-item .label {
  font-weight: 500;
  color: var(--text-muted);
}

.day-info-item .value {
  font-weight: 600;
  color: var(--text-color);
}

.shift-column-card {
  border: none;
  box-shadow: 0 0.125rem 0.25rem rgba(0,0,0,.075);
  transition: transform 0.2s;
  height: 100%;
}

.shift-column-card:hover {
  transform: translateY(-2px);
}

.shift-time {
  font-size: 0.875rem;
  color: rgba(255,255,255,0.9);
  margin-bottom: 0;
}

/* Shift-specific colors - matching calendar view */
.card-header.shift-early {
  background-color: #3498db !important;
  border-color: #3498db !important;
}

.card-header.shift-morning {
  background-color: #e67e22 !important;
  border-color: #e67e22 !important;
}

.card-header.shift-late {
  background-color: #27ae60 !important;
  border-color: #27ae60 !important;
}

.card-header.shift-night {
  background-color: #34495e !important;
  border-color: #34495e !important;
}

.card-header.shift-default {
  background-color: #95a5a6 !important;
  border-color: #95a5a6 !important;
}

.staffing-info {
  display: flex;
  flex-direction: column;
}

.staffing-info .label {
  color: var(--text-muted);
  font-size: 0.875rem;
}

.staffing-info .value {
  font-weight: 600;
  font-size: 1rem;
}

.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.employee-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.employee-item {
  display: flex;
  align-items: center;
  padding: 0.5rem;
  background-color: #f8f9fa;
  border-radius: 0.25rem;
  border-left: 3px solid var(--primary-color);
}

.employee-info {
  display: flex;
  align-items: center;
  flex: 1;
  cursor: pointer;
  transition: all 0.2s ease;
  padding: 0.25rem;
  border-radius: 0.25rem;
}

.employee-info:hover {
  background-color: rgba(52, 152, 219, 0.1);
  transform: translateX(2px);
}

.employee-info .bi-person-circle {
  margin-right: 0.5rem;
  color: var(--primary-color);
}

.employee-info .employee-name {
  font-weight: 500;
  font-size: 0.875rem;
  color: var(--primary-color);
  text-decoration: none;
}

.employee-info:hover .employee-name {
  text-decoration: underline;
}
</style> 