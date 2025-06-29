import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/api'

export const useScheduleStore = defineStore('schedule', () => {
  const scheduleData = ref({})
  const dayScheduleData = ref({})
  const employeeScheduleData = ref({})
  const employeeYearlyData = ref({})
  const availableAlgorithms = ref([])
  const selectedAlgorithm = ref('')
  const loading = ref(false)
  const error = ref(null)
  const currentDate = ref(new Date())

  const currentYear = computed(() => currentDate.value.getFullYear())
  const currentMonth = computed(() => currentDate.value.getMonth() + 1)

  async function loadScheduleData(companyId, year, month, algorithm = null) {
    loading.value = true
    error.value = null
    
    try {
      const params = { year, month }
      if (algorithm) {
        params.algorithm = algorithm
      }
      
      const response = await api.get(`/api/companies/${companyId}/schedule/`, { params })
      scheduleData.value = response.data
    } catch (err) {
      error.value = 'Failed to load schedule data'
      console.error('Error loading schedule data:', err)
    } finally {
      loading.value = false
    }
  }

  async function loadDayScheduleData(companyId, date, algorithm = null) {
    loading.value = true
    error.value = null
    
    try {
      const params = {}
      if (algorithm) {
        params.algorithm = algorithm
      }
      
      const response = await api.get(`/api/companies/${companyId}/day/${date}/`, { params })
      dayScheduleData.value = response.data
    } catch (err) {
      error.value = 'Failed to load day schedule data'
      console.error('Error loading day schedule data:', err)
    } finally {
      loading.value = false
    }
  }

  async function loadEmployeeScheduleData(companyId, employeeId, year, month, algorithm = null) {
    loading.value = true
    error.value = null
    
    try {
      const params = { year, month }
      if (algorithm) {
        params.algorithm = algorithm
      }
      
      const response = await api.get(`/api/companies/${companyId}/employees/${employeeId}/schedule/`, { params })
      employeeScheduleData.value = response.data
    } catch (err) {
      error.value = 'Failed to load employee schedule data'
      console.error('Error loading employee schedule data:', err)
    } finally {
      loading.value = false
    }
  }

  async function loadEmployeeYearlyData(companyId, employeeId, year, algorithm = null) {
    loading.value = true
    error.value = null
    
    try {
      const params = { year }
      if (algorithm) {
        params.algorithm = algorithm
      }
      
      const response = await api.get(`/api/companies/${companyId}/employees/${employeeId}/yearly/`, { params })
      employeeYearlyData.value = response.data
    } catch (err) {
      error.value = 'Failed to load employee yearly data'
      console.error('Error loading employee yearly data:', err)
    } finally {
      loading.value = false
    }
  }

  async function loadAvailableAlgorithms(companyId) {
    try {
      const response = await api.get(`/api/companies/${companyId}/algorithms/`)
      availableAlgorithms.value = response.data.algorithms
      
      // Set default algorithm if available
      if (availableAlgorithms.value.length > 0 && !selectedAlgorithm.value) {
        const defaultAlg = availableAlgorithms.value.find(alg => 
          alg.includes('Linear Programming (ILP)')
        ) || availableAlgorithms.value[0]
        selectedAlgorithm.value = defaultAlg
      }
    } catch (err) {
      console.error('Error loading algorithms:', err)
    }
  }

  function setSelectedAlgorithm(algorithm) {
    selectedAlgorithm.value = algorithm
  }

  function setCurrentDate(date) {
    currentDate.value = new Date(date)
  }

  function getScheduleForDate(date) {
    const dateStr = date.toISOString().split('T')[0]
    return scheduleData.value.schedule_data?.[dateStr] || null
  }

  function getEmployeeSchedule(employeeId) {
    // Implementation for getting employee-specific schedule
    return null
  }

  function getCoverageStats() {
    return scheduleData.value.coverage_stats || {}
  }

  function getTopEmployees() {
    return scheduleData.value.top_employees || []
  }

  return {
    scheduleData,
    dayScheduleData,
    employeeScheduleData,
    employeeYearlyData,
    availableAlgorithms,
    selectedAlgorithm,
    loading,
    error,
    currentDate,
    currentYear,
    currentMonth,
    loadScheduleData,
    loadDayScheduleData,
    loadEmployeeScheduleData,
    loadEmployeeYearlyData,
    loadAvailableAlgorithms,
    setSelectedAlgorithm,
    setCurrentDate,
    getScheduleForDate,
    getEmployeeSchedule,
    getCoverageStats,
    getTopEmployees
  }
}) 