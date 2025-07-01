<template>
  <div class="container">
    <PageHeader 
      title="Algorithmusvergleich"
      icon="bi bi-bar-chart"
      :breadcrumbs="[
        { text: 'Dashboard', to: { name: 'dashboard', params: { companyId: $route.params.companyId } } },
        { text: 'Algorithmusvergleich' }
      ]"
    />

    <MonthNavigation 
      :current-year="currentYear"
      :current-month="currentMonth"
      @previous="previousMonth"
      @next="nextMonth"
    />

    <LoadingState :loading="algorithmKPIsLoading" />
    <ErrorState :error="algorithmKPIsError" />

    <div v-if="!algorithmKPIsLoading && !algorithmKPIsError">
      <div class="row mb-4">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-gear"></i> Algorithmusvergleich
              </h5>
            </div>
            <div class="card-body">
              <div v-if="availableAlgorithms.length === 0" class="text-muted text-center">
                Keine Algorithmen verfügbar
              </div>
              <div v-else class="row">
                <div 
                  v-for="algorithm in availableAlgorithms" 
                  :key="algorithm"
                  class="col-md-6 col-lg-4 mb-3"
                >
                  <div class="card">
                    <div class="card-body text-center">
                      <h6 class="card-title">{{ algorithm }}</h6>
                      <div v-if="algorithmKPIs[algorithm]">
                        <div class="algorithm-stats">
                          <div class="stat-item">
                            <span class="stat-label">Ø Abdeckung:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].coverage_rates ? Object.values(algorithmKPIs[algorithm].coverage_rates).reduce((a, b) => a + b, 0) / Object.values(algorithmKPIs[algorithm].coverage_rates).length : 0) }}%
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Ø Stunden pro Mitarbeiter:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].avg_hours_per_employee) }}
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Laufzeit:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].runtime) }}s
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Standardabweichung der Stunden:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].hours_std_dev) }}
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Gini-Koeffizient:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].gini_coefficient) }}
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Anzahl Constraint-Verletzungen:</span>
                            <span class="stat-value">
                              {{ algorithmKPIs[algorithm].constraint_violations }}
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Minimale Stunden:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].min_hours) }}
                            </span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">Maximale Stunden:</span>
                            <span class="stat-value">
                              {{ formatNumber(algorithmKPIs[algorithm].max_hours) }}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div v-else>
                        <span class="text-muted">Keine Daten</span>
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

    <div v-if="!yearlyKPIsLoading && !yearlyKPIsError" class="row mb-4">
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            <h5 class="card-title mb-0">
              <i class="bi bi-calendar3"></i> Jahresstatistik ({{ currentYear }})
            </h5>
          </div>
          <div class="card-body">
            <div v-if="availableAlgorithms.length === 0" class="text-muted text-center">
              Keine Algorithmen verfügbar
            </div>
            <div v-else class="row">
              <div 
                v-for="algorithm in availableAlgorithms" 
                :key="algorithm"
                class="col-md-6 col-lg-4 mb-3"
              >
                <div class="card">
                  <div class="card-body text-center">
                    <h6 class="card-title">{{ algorithm }}</h6>
                    <div v-if="yearlyKPIs[algorithm]">
                      <div class="algorithm-stats">
                        <div class="stat-item">
                          <span class="stat-label">Ø Abdeckung:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].coverage_rates ? Object.values(yearlyKPIs[algorithm].coverage_rates).reduce((a, b) => a + b, 0) / Object.values(yearlyKPIs[algorithm].coverage_rates).length : 0) }}%
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Ø Stunden pro Mitarbeiter:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].avg_hours_per_employee) }}
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Laufzeit:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].runtime) }}s
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Standardabweichung der Stunden:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].hours_std_dev) }}
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Gini-Koeffizient:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].gini_coefficient) }}
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Anzahl Constraint-Verletzungen:</span>
                          <span class="stat-value">
                            {{ yearlyKPIs[algorithm].constraint_violations }}
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Minimale Stunden:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].min_hours) }}
                          </span>
                        </div>
                        <div class="stat-item">
                          <span class="stat-label">Maximale Stunden:</span>
                          <span class="stat-value">
                            {{ formatNumber(yearlyKPIs[algorithm].max_hours) }}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div v-else>
                      <span class="text-muted">Keine Daten</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <LoadingState :loading="yearlyKPIsLoading" />
    <ErrorState :error="yearlyKPIsError" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import { analyticsAPI } from '@/services/api'
import { useCompanyStore } from '@/stores/company'
import { useScheduleStore } from '@/stores/schedule'
import PageHeader from '@/components/PageHeader.vue'
import MonthNavigation from '@/components/MonthNavigation.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'

const route = useRoute()
const companyStore = useCompanyStore()
const scheduleStore = useScheduleStore()

const currentYear = computed(() => scheduleStore.currentYear)
const currentMonth = computed(() => scheduleStore.currentMonth)
const availableAlgorithms = computed(() => scheduleStore.availableAlgorithms)

const algorithmKPIs = ref({})
const algorithmKPIsLoading = ref(false)
const algorithmKPIsError = ref(null)

const yearlyKPIs = ref({})
const yearlyKPIsLoading = ref(false)
const yearlyKPIsError = ref(null)

const formatNumber = (num) => {
  if (num === null || num === undefined) return '0'
  return parseFloat(num).toFixed(3).replace(/\.?0+$/, '')
}

const previousMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value - 2)
  scheduleStore.setCurrentDate(newDate)
  loadAlgorithmKPIs()
}

const nextMonth = () => {
  const newDate = new Date(currentYear.value, currentMonth.value)
  scheduleStore.setCurrentDate(newDate)
  loadAlgorithmKPIs()
}

const loadAlgorithmKPIs = async () => {
  if (!route.params.companyId) return
  algorithmKPIsLoading.value = true
  algorithmKPIsError.value = null
  try {
    await scheduleStore.loadAvailableAlgorithms(route.params.companyId)
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

const loadYearlyKPIs = async () => {
  if (!route.params.companyId) return
  yearlyKPIsLoading.value = true
  yearlyKPIsError.value = null
  try {
    await scheduleStore.loadAvailableAlgorithms(route.params.companyId)
    const { data } = await analyticsAPI.getAllAlgorithmKPIs(
      route.params.companyId,
      currentYear.value,
      null // no month for yearly
    )
    yearlyKPIs.value = data.algorithms || {}
  } catch (err) {
    yearlyKPIsError.value = 'Fehler beim Laden der Jahresstatistik-KPIs'
    console.error(err)
  } finally {
    yearlyKPIsLoading.value = false
  }
}

watch([currentYear, currentMonth], loadAlgorithmKPIs)
watch(() => route.params.companyId, loadAlgorithmKPIs)
watch([currentYear, () => route.params.companyId], loadYearlyKPIs)

// Initial load
loadAlgorithmKPIs()
loadYearlyKPIs()
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
</style> 