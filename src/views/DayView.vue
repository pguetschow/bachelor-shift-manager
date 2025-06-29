<template>
  <div class="container">
    <!-- Header -->
    <PageHeader 
      title="Tagesansicht"
      icon="bi bi-calendar-day"
      :breadcrumbs="[
        { 
          text: 'Dashboard', 
          to: { name: 'dashboard', params: { companyId: $route.params.companyId } } 
        },
        { 
          text: 'Monatsansicht', 
          to: { name: 'month-view', params: { companyId: $route.params.companyId } } 
        },
        { text: 'Tagesansicht' }
      ]"
    />

    <!-- Date Navigation -->
    <DateNavigation 
      :date="selectedDate"
      @previous="previousDay"
      @next="nextDay"
    />

    <!-- Loading State -->
    <LoadingState :loading="loading" />

    <!-- Error State -->
    <ErrorState :error="error" />

    <!-- Day Content -->
    <div v-if="!loading && !error">
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
                      <StatusBadge 
                        v-if="isHoliday" 
                        status="holiday"
                      />
                      <StatusBadge 
                        v-else-if="isSundayDay" 
                        status="sunday"
                      />
                      <StatusBadge 
                        v-else-if="isNonWorking" 
                        status="non_working"
                      />
                      <StatusBadge 
                        v-else 
                        status="working"
                      />
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
                <StatusBadge :status="shift.status" />
              </div>
              <div class="shift-time mt-2">
                <i class="bi bi-clock"></i>
                <TimeDisplay 
                  :time="shift.start_time" 
                  format="time-range" 
                  :end-time="shift.end_time" 
                />
              </div>
            </div>
            <div class="card-body">
              <!-- Staffing Info -->
              <div class="staffing-info mb-3">
                <div class="d-flex justify-content-between align-items-center">
                  <span class="label">Besetzung:</span>
                  <span class="value">{{ shift.assigned_count }}/{{ shift.max_staff }}</span>
                </div>
                <ProgressBar 
                  :percentage="getStaffingPercentage(shift)"
                  :height="8"
                  :show-label="false"
                />
                <div class="staffing-limits mt-1">
                  <small class="text-muted">
                    Min: {{ shift.min_staff }} | Max: {{ shift.max_staff }}
                  </small>
                </div>
              </div>

              <!-- Assigned Employees -->
              <div class="assigned-employees">
                <h6 class="section-title">Zugewiesene Mitarbeiter</h6>
                <div v-if="!shift.assigned_employees || shift.assigned_employees.length === 0" class="text-muted text-center py-3">
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
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { format } from 'date-fns'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import { useFormatters } from '@/composables/useFormatters'

// Components
import PageHeader from '@/components/PageHeader.vue'
import DateNavigation from '@/components/DateNavigation.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import TimeDisplay from '@/components/TimeDisplay.vue'
import ProgressBar from '@/components/ProgressBar.vue'

const route = useRoute()
const router = useRouter()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()
const { 
  formatDate, 
  getDayOfWeek, 
  getShiftDisplayName, 
  getShiftColorClass, 
  getStatusBadgeClass 
} = useFormatters()

const company = computed(() => companyStore.currentCompany)
const loading = computed(() => scheduleStore.loading)
const error = computed(() => scheduleStore.error)
const selectedDate = computed(() => scheduleStore.selectedDate || new Date())
const shifts = computed(() => scheduleStore.getDayShifts() || [])
const totalShifts = computed(() => shifts.value?.length || 0)

const isHoliday = computed(() => {
  if (!selectedDate.value) return false
  const dateStr = format(selectedDate.value, 'yyyy-MM-dd')
  return scheduleStore.scheduleData.schedule_data?.[dateStr]?.is_holiday || false
})

const isSundayDay = computed(() => selectedDate.value?.getDay() === 0)
const isNonWorking = computed(() => {
  if (!selectedDate.value) return false
  const dateStr = format(selectedDate.value, 'yyyy-MM-dd')
  return scheduleStore.scheduleData.schedule_data?.[dateStr]?.is_non_working || false
})

const previousDay = () => {
  if (!selectedDate.value) return
  const newDate = new Date(selectedDate.value)
  newDate.setDate(newDate.getDate() - 1)
  scheduleStore.setSelectedDate(newDate)
  loadDayData()
}

const nextDay = () => {
  if (!selectedDate.value) return
  const newDate = new Date(selectedDate.value)
  newDate.setDate(newDate.getDate() + 1)
  scheduleStore.setSelectedDate(newDate)
  loadDayData()
}

const getStaffingPercentage = (shift) => {
  if (!shift.max_staff || shift.max_staff === 0) return 0
  return Math.min((shift.assigned_count / shift.max_staff) * 100, 100)
}

const navigateToEmployee = (employeeId) => {
  router.push({
    name: 'employee-view',
    params: { 
      companyId: route.params.companyId, 
      employeeId 
    }
  })
}

const loadDayData = async () => {
  if (route.params.companyId && selectedDate.value) {
    const dateStr = format(selectedDate.value, 'yyyy-MM-dd')
    await scheduleStore.loadDayScheduleData(
      route.params.companyId,
      dateStr,
      scheduleStore.selectedAlgorithm
    )
  }
}

onMounted(loadDayData)

watch(() => route.params.companyId, loadDayData)
watch(() => scheduleStore.selectedAlgorithm, loadDayData)
</script>

<style scoped>
.day-info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
}

.day-info-item .label {
  font-weight: 600;
  color: var(--text-muted);
}

.day-info-item .value {
  font-weight: 500;
}

.shift-column-card {
  height: 100%;
  transition: transform 0.2s ease-in-out;
}

.shift-column-card:hover {
  transform: translateY(-2px);
}

.shift-column-card .card-header {
  color: white;
  font-weight: 600;
}

.shift-time {
  font-size: 0.875rem;
  opacity: 0.9;
}

.staffing-info .label {
  font-weight: 600;
  color: var(--text-muted);
}

.staffing-info .value {
  font-weight: 500;
}

.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.employee-list {
  max-height: 200px;
  overflow-y: auto;
}

.employee-item {
  padding: 0.5rem 0;
  border-bottom: 1px solid #f0f0f0;
}

.employee-item:last-child {
  border-bottom: none;
}

.employee-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  transition: color 0.2s ease-in-out;
}

.employee-info:hover {
  color: var(--bs-primary);
}

.employee-name {
  font-weight: 500;
}

.shift-early {
  background: linear-gradient(135deg, #1976d2, #1565c0);
}

.shift-morning {
  background: linear-gradient(135deg, #7b1fa2, #6a1b9a);
}

.shift-late {
  background: linear-gradient(135deg, #f57c00, #ef6c00);
}

.shift-night {
  background: linear-gradient(135deg, #c2185b, #ad1457);
}
</style> 