<template>
  <div class="container px-3">
    <!-- Header -->
    <PageHeader 
      title="Monatsansicht"
      icon="bi bi-calendar-month"
      :breadcrumbs="[
        { 
          text: 'Dashboard', 
          to: { name: 'dashboard', params: { companyId: $route.params.companyId } } 
        },
        { text: 'Monatsansicht' }
      ]"
    />

    <!-- Month Navigation -->
    <MonthNavigation 
      :current-year="currentYear"
      :current-month="currentMonth"
      @previous="previousMonth"
      @next="nextMonth"
    />

    <!-- Loading State -->
    <LoadingState :loading="loading" />

    <!-- Error State -->
    <ErrorState :error="error" />

    <!-- Calendar -->
    <div v-if="!loading && !error" class="calendar-container">
      <!-- Calendar Header -->
      <div class="row calendar-header g-0">
        <div 
          v-for="day in weekDays" 
          :key="day" 
          class="col calendar-day-header"
        >
          {{ day }}
        </div>
      </div>

      <!-- Calendar Body -->
      <div class="calendar-body">
        <div 
          v-for="week in calendarWeeks" 
          :key="week[0]?.date || 'empty-week'"
          class="row calendar-week g-0"
        >
          <div 
            v-for="day in week" 
            :key="day?.date || 'empty-day'"
            class="col calendar-day"
            :class="getDayClasses(day)"
            @click="selectDay(day)"
          >
            <div v-if="day" class="calendar-day-content">
              <div class="calendar-day-number">{{ day.day }}</div>
              
              <!-- Shift indicators -->
              <div class="shift-indicators">
                <div 
                  v-for="[shiftName, shiftData] in getSortedShifts(day.shifts)" 
                  :key="shiftName"
                  class="shift-indicator"
                  :class="[
                    getShiftColorClass(shiftName),
                    getShiftStatusClass(shiftData.status)
                  ]"
                  :title="`${getShiftDisplayName(shiftName)}: ${shiftData.count}/${shiftData.max_staff} (Min: ${shiftData.min_staff}, Max: ${shiftData.max_staff})`"
                  v-show="shouldShowShifts(day)"
                >
                  <div class="shift-header">
                    <div class="shift-name">{{ getShiftDisplayName(shiftName) }}</div>
                    <div class="shift-staffing">
                      <div class="staffing-row">
                        <span class="current">{{ shiftData.count }} (min: {{ shiftData.min_staff }}, max: {{ shiftData.max_staff }})</span>
                      </div>
                    </div>
                    <div class="limit-icons">
                      <i 
                        v-if="shiftData.count < shiftData.min_staff" 
                        class="bi bi-exclamation-triangle-fill text-warning"
                        title="Unterbesetzt"
                      ></i>
                      <i 
                        v-if="shiftData.count > shiftData.max_staff" 
                        class="bi bi-exclamation-circle-fill text-danger"
                        title="Überbesetzt"
                      ></i>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- Day status indicators -->
              <div class="day-status">
                <StatusBadge 
                  v-if="day.is_holiday" 
                  status="holiday"
                  size="small"
                />
                <StatusBadge 
                  v-else-if="day.is_sunday && !company?.sunday_is_workday" 
                  status="sunday"
                  size="small"
                />
                <StatusBadge 
                  v-else-if="day.is_non_working" 
                  status="non_working"
                  size="small"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="row mt-4">
      <div class="col">
        <div class="card">
          <div class="card-header">
            <h6 class="card-title mb-0">Legende</h6>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="col-md-6">
                <h6>Schichtfarben:</h6>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-early me-2"></span>
                  <span>Frühschicht</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-morning me-2"></span>
                  <span>Tagesschicht</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-late me-2"></span>
                  <span>Spätschicht</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-night me-2"></span>
                  <span>Nachtschicht</span>
                </div>
              </div>
              <div class="col-md-6">
                <h6>Schichtstatus:</h6>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-early status-ok me-2"></span>
                  <span>Vollständig besetzt</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-early status-understaffed me-2"></span>
                  <span>Unterbesetzt (roter Rand)</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <span class="shift-indicator shift-early status-overstaffed me-2"></span>
                  <span>Überbesetzt (gelber Rand)</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <i class="bi bi-exclamation-triangle-fill text-warning me-2"></i>
                  <span>Unterbesetzt</span>
                </div>
                <div class="d-flex align-items-center mb-2">
                  <i class="bi bi-exclamation-circle-fill text-danger me-2"></i>
                  <span>Überbesetzt</span>
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
import { useRoute, useRouter } from 'vue-router'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import { useFormatters } from '@/composables/useFormatters'

// Components
import PageHeader from '@/components/PageHeader.vue'
import MonthNavigation from '@/components/MonthNavigation.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()
const { getShiftDisplayName, getShiftColorClass } = useFormatters()

const company = computed(() => companyStore.currentCompany)
const loading = computed(() => scheduleStore.loading)
const error = computed(() => scheduleStore.error)
const currentYear = computed(() => scheduleStore.currentYear)
const currentMonth = computed(() => scheduleStore.currentMonth)
const calendarWeeks = computed(() => scheduleStore.getCalendarWeeks())
const weekDays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

const currentMonthName = computed(() => {
  const date = new Date(currentYear.value, currentMonth.value - 1)
  return format(date, 'MMMM', { locale: de })
})

const getDayClasses = (day) => {
  if (!day) return []
  
  const classes = []
  if (day.is_today) classes.push('today')
  if (day.is_sunday) classes.push('weekend')
  if (day.is_holiday || day.is_non_working) classes.push('non-working')
  
  return classes
}

const getShiftStatusClass = (status) => {
  switch (status) {
    case 'ok': return 'status-ok'
    case 'understaffed': return 'status-understaffed'
    case 'overstaffed': return 'status-overstaffed'
    default: return 'status-ok'
  }
}

const getShiftOrder = (shiftName) => {
  const orderMap = {
    'EarlyShift': 1,
    'MorningShift': 2,
    'LateShift': 3,
    'NightShift': 4
  }
  return orderMap[shiftName] || 999
}

const getSortedShifts = (shifts) => {
  return Object.entries(shifts).sort(([a], [b]) => {
    return getShiftOrder(a) - getShiftOrder(b)
  })
}

const shouldShowShifts = (day) => {
  // Don't show shifts on holidays
  if (day.is_holiday) {
    return false
  }
  
  // Don't show shifts on Sundays if company has Sunday off
  if (day.is_sunday && !company.value?.sunday_is_workday) {
    return false
  }
  
  // Don't show shifts on non-working days
  if (day.is_non_working) {
    return false
  }
  
  return true
}

const previousMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value - 2)
  scheduleStore.setCurrentDate(newDate)
  loadMonthData()
}

const nextMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value)
  scheduleStore.setCurrentDate(newDate)
  loadMonthData()
}

const selectDay = (day) => {
  if (!day) return
  
  // Set the selected date in the store
  scheduleStore.setSelectedDate(day.date)
  
  router.push({
    name: 'day-view',
    params: {
      companyId: route.params.companyId,
      date: day.dateStr
    }
  })
}

const loadMonthData = async () => {
  if (route.params.companyId) {
    await scheduleStore.loadScheduleData(
      route.params.companyId,
      currentYear.value,
      currentMonth.value,
      scheduleStore.selectedAlgorithm
    )
  }
}

onMounted(loadMonthData)

watch(() => route.params.companyId, loadMonthData)
watch(() => scheduleStore.selectedAlgorithm, loadMonthData)
watch([currentYear, currentMonth], loadMonthData)
</script>

<style scoped>
.calendar-container {
  background: white;
  border-radius: 0.5rem;
  box-shadow: 0 0.125rem 0.25rem rgba(0,0,0,.075);
  overflow: hidden;
  margin: 0;
}

.calendar-header {
  background-color: var(--primary-color);
  color: white;
  font-weight: 600;
  margin: 0;
}

.calendar-day-header {
  padding: 1rem 0.5rem;
  text-align: center;
  border-right: 1px solid rgba(255,255,255,0.1);
  min-height: 3rem;
}

.calendar-day-header:last-child {
  border-right: none;
}

.calendar-week {
  border-bottom: 1px solid #dee2e6;
  margin: 0;
}

.calendar-week:last-child {
  border-bottom: none;
}

.calendar-day {
  border-right: 1px solid #dee2e6;
  min-height: 8rem;
  padding: 0.25rem;
  position: relative;
  cursor: pointer;
  transition: background-color 0.2s;
}

.calendar-day:last-child {
  border-right: none;
}

.calendar-day:hover {
  background-color: #f8f9fa;
}

.calendar-day.today {
  background-color: #e3f2fd;
  border-color: var(--secondary-color);
}

.calendar-day.weekend {
  background-color: #fafafa;
}

.calendar-day.non-working {
  background-color: #fff3cd;
}

.calendar-day-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.calendar-day-number {
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.shift-indicators {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.shift-indicator {
  padding: 0.125rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  text-align: center;
  background-color: #f8f9fa;
  border: 1px solid var(--border-color);
  color: white;
  font-weight: 500;
}

.shift-header {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.0625rem;
}

.shift-name {
  font-weight: 600;
  font-size: 0.6rem;
  text-align: center;
}

.shift-staffing {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.0625rem;
}

.staffing-row {
  display: flex;
  align-items: center;
  justify-content: center;
}

.current {
  color: #fff;
  font-weight: 600;
  font-size: 0.75rem;
  text-align: center;
}

.limit-icons {
  display: flex;
  justify-content: center;
  gap: 0.0625rem;
  margin-top: 0.0625rem;
}

.limit-icons i {
  font-size: 0.6rem;
}

/* Shift-specific colors */
.shift-indicator.shift-early {
  background-color: #3498db;
  border-color: #3498db;
}

.shift-indicator.shift-morning {
  background-color: #e67e22;
  border-color: #e67e22;
}

.shift-indicator.shift-late {
  background-color: #27ae60;
  border-color: #27ae60;
}

.shift-indicator.shift-night {
  background-color: #34495e;
  border-color: #34495e;
}

.shift-indicator.shift-default {
  background-color: #95a5a6;
  border-color: #95a5a6;
}

/* Status overlays - these will modify the appearance based on staffing status */
.shift-indicator.status-ok {
  opacity: 1;
}

.shift-indicator.status-understaffed {
  opacity: 0.7;
  border: 2px solid var(--danger-color);
}

.shift-indicator.status-overstaffed {
  opacity: 0.8;
  border: 2px solid var(--warning-color);
}

.shift-count {
  font-weight: 600;
  font-size: 0.875rem;
}

.day-status {
  margin-top: 0.5rem;
  text-align: center;
}

.day-status .badge {
  font-size: 0.75rem;
}
</style> 