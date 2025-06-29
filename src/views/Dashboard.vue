<template>
  <div class="container">
    <!-- Header -->
    <PageHeader 
      title="Dashboard"
      icon="bi bi-speedometer2"
      :breadcrumbs="[
        { text: 'Dashboard' }
      ]"
    />

    <!-- Month Navigation -->
    <MonthNavigation 
      :current-year="scheduleStore.currentYear"
      :current-month="scheduleStore.currentMonth"
      @previous="previousMonth"
      @next="nextMonth"
    />

    <!-- Loading State -->
    <LoadingState :loading="loading" />

    <!-- Error State -->
    <ErrorState :error="error" />

    <!-- Dashboard Content -->
    <div v-if="!loading && !error">
      <!-- Statistics Cards -->
      <div class="row mb-4">
        <div class="col-md-3 mb-3">
          <StatCard 
            subtitle="Mitarbeiter"
            :value="coverageStats.total_employees || 0"
            icon="bi bi-people-fill"
            icon-color="text-primary"
          />
        </div>

        <div class="col-md-3 mb-3">
          <StatCard 
            subtitle="Schichten"
            :value="coverageStats.total_shifts || 0"
            icon="bi bi-calendar-check"
            icon-color="text-success"
          />
        </div>

        <div class="col-md-3 mb-3">
          <StatCard 
            subtitle="Arbeitstage"
            :value="coverageStats.working_days || 0"
            icon="bi bi-calendar-week"
            icon-color="text-warning"
          />
        </div>

        <div class="col-md-3 mb-3">
          <StatCard 
            subtitle="Abdeckung"
            :value="formatNumber(coverageStats.coverage_percentage || 0) + '%'"
            icon="bi bi-pie-chart"
            icon-color="text-info"
          />
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
                        <ShiftBadge :shift-name="stat.shift.name" />
                      </td>
                      <td>
                        <TimeDisplay 
                          :time="stat.shift.start_time" 
                          format="time-range" 
                          :end-time="stat.shift.end_time" 
                        />
                      </td>
                      <td>{{ stat.shift.min_staff }} / {{ stat.shift.max_staff }}</td>
                      <td>{{ stat.avg_staff }}</td>
                      <td>
                        <ProgressBar 
                          :percentage="formatNumber(stat.coverage_percentage)"
                          :height="20"
                        />
                      </td>
                      <td>
                        <StatusBadge :status="stat.status" />
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
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import { useFormatters } from '@/composables/useFormatters'

// Components
import PageHeader from '@/components/PageHeader.vue'
import MonthNavigation from '@/components/MonthNavigation.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import StatCard from '@/components/StatCard.vue'
import ShiftBadge from '@/components/ShiftBadge.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import TimeDisplay from '@/components/TimeDisplay.vue'

const route = useRoute()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()
const { formatNumber } = useFormatters()

const company = computed(() => companyStore.currentCompany)
const loading = computed(() => scheduleStore.loading)
const error = computed(() => scheduleStore.error)
const coverageStats = computed(() => scheduleStore.getCoverageStats())
const topEmployees = computed(() => scheduleStore.getTopEmployees())

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