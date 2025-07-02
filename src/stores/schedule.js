import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { format, startOfMonth, endOfMonth, eachDayOfInterval, startOfWeek, endOfWeek, isSameMonth, isToday } from 'date-fns'
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
  const selectedDate = ref(new Date())

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

  function setSelectedDate(date) {
    selectedDate.value = new Date(date)
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

  function getCalendarWeeks() {
    if (!currentYear.value || !currentMonth.value) return []
    
    const monthStart = startOfMonth(new Date(currentYear.value, currentMonth.value - 1))
    const monthEnd = endOfMonth(monthStart)
    const calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 })
    const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })
    
    const days = eachDayOfInterval({ start: calendarStart, end: calendarEnd })
    const weeks = []
    
    for (let i = 0; i < days.length; i += 7) {
      const week = days.slice(i, i + 7).map(day => {
        if (!isSameMonth(day, monthStart)) {
          return null
        }
        
        const dateStr = format(day, 'yyyy-MM-dd')
        const dayScheduleData = scheduleData.value.schedule_data?.[dateStr] || {}
        
        return {
          day: day.getDate(),
          date: day,
          dateStr,
          shifts: dayScheduleData.shifts || {},
          is_today: isToday(day),
          is_holiday: dayScheduleData.is_holiday || false,
          is_sunday: day.getDay() === 0,
          is_non_working: dayScheduleData.is_non_working || false
        }
      })
      weeks.push(week)
    }
    
    return weeks
  }

  function getDayShifts() {
    const dayData = dayScheduleData.value

    if (!dayData || !dayData.shifts) {
      console.log('No day schedule data available')
      return []
    }

    // If dayData.shifts is an array of objects with a 'shift' key, return the 'shift' property
    if (Array.isArray(dayData.shifts) && dayData.shifts.length && dayData.shifts[0].shift) {
      return dayData.shifts.map(s => s.shift)
    }
    // If dayData.shifts is already an array of shift objects, return as is
    if (Array.isArray(dayData.shifts)) {
      return dayData.shifts
    }
    return []
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
    selectedDate,
    currentYear,
    currentMonth,
    loadScheduleData,
    loadDayScheduleData,
    loadEmployeeScheduleData,
    loadEmployeeYearlyData,
    loadAvailableAlgorithms,
    setSelectedAlgorithm,
    setCurrentDate,
    setSelectedDate,
    getScheduleForDate,
    getEmployeeSchedule,
    getCoverageStats,
    getTopEmployees,
    getCalendarWeeks,
    getDayShifts
  }
}) 