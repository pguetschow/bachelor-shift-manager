/**
 * Real-time KPI Calculator Service
 * Calculates KPIs directly from schedule data without relying on store
 */

import { format, parseISO, startOfWeek, endOfWeek, eachDayOfInterval, isWeekend } from 'date-fns'
import { de } from 'date-fns/locale'

export class KPICalculator {
  constructor(company) {
    this.company = company
    this.sundaysOff = !company.sunday_is_workday
  }

  /**
   * Calculate employee statistics from schedule data
   */
  calculateEmployeeStatistics(employee, scheduleData, year, month) {
    if (!scheduleData || scheduleData.length === 0) {
      return this.getEmptyStatistics()
    }

    const totalHours = this.calculateTotalHours(scheduleData)
    const totalShifts = scheduleData.length
    const averageHoursPerShift = totalShifts > 0 ? totalHours / totalShifts : 0
    
    // Calculate expected monthly hours based on contract and absences
    const expectedMonthlyHours = this.calculateExpectedMonthlyHours(employee, year, month)
    const utilizationPercentage = this.calculateUtilizationPercentage(totalHours, expectedMonthlyHours)
    
    // Calculate weekly workload
    const weeklyWorkload = this.calculateWeeklyWorkload(scheduleData, year, month)

    return {
      total_hours: totalHours,
      total_shifts: totalShifts,
      average_hours_per_shift: averageHoursPerShift,
      utilization_percentage: utilizationPercentage,
      weekly_workload: weeklyWorkload
    }
  }

  /**
   * Calculate yearly statistics from schedule data
   */
  calculateYearlyStatistics(employee, scheduleData, year) {
    if (!scheduleData || scheduleData.length === 0) {
      return this.getEmptyYearlyStatistics()
    }

    const totalHours = this.calculateTotalHours(scheduleData)
    const totalShifts = scheduleData.length
    const averageHoursPerShift = totalShifts > 0 ? totalHours / totalShifts : 0
    
    // Calculate expected yearly hours
    const expectedYearlyHours = this.calculateExpectedYearlyHours(employee, year)
    const yearlyUtilizationPercentage = this.calculateUtilizationPercentage(totalHours, expectedYearlyHours)
    
    // Calculate monthly breakdown
    const monthlyBreakdown = this.calculateMonthlyBreakdown(scheduleData, year)

    return {
      total_hours: totalHours,
      total_shifts: totalShifts,
      average_hours_per_shift: averageHoursPerShift,
      max_yearly_hours: expectedYearlyHours,
      yearly_utilization_percentage: yearlyUtilizationPercentage,
      monthly_breakdown: monthlyBreakdown
    }
  }

  /**
   * Calculate total hours from schedule data
   */
  calculateTotalHours(scheduleData) {
    return scheduleData.reduce((total, entry) => {
      const shiftHours = this.calculateShiftHours(entry.shift)
      return total + shiftHours
    }, 0)
  }

  /**
   * Calculate shift hours from shift data
   */
  calculateShiftHours(shift) {
    if (!shift.start_time || !shift.end_time) return 0
    
    const start = parseISO(`2000-01-01T${shift.start_time}`)
    const end = parseISO(`2000-01-01T${shift.end_time}`)
    
    // Handle overnight shifts
    let hours = (end - start) / (1000 * 60 * 60)
    if (hours < 0) hours += 24
    
    return hours
  }

  /**
   * Calculate expected monthly hours based on contract and absences
   */
  calculateExpectedMonthlyHours(employee, year, month) {
    const weeklyHours = employee.max_hours_per_week
    const shiftsPerWeek = weeklyHours / 8 // Assuming 8-hour shifts
    
    // Calculate working days in month (excluding weekends and holidays)
    const workingDays = this.getWorkingDaysInMonth(year, month)
    
    // Calculate absences in this month
    const absencesInMonth = this.getAbsencesInMonth(employee, year, month)
    
    // Available working days = total working days - absences
    const availableWorkingDays = workingDays - absencesInMonth
    
    // Expected hours = available days * shifts per week * 8 hours
    return availableWorkingDays * (shiftsPerWeek / 7) * 8
  }

  /**
   * Calculate expected yearly hours
   */
  calculateExpectedYearlyHours(employee, year) {
    const weeklyHours = employee.max_hours_per_week
    
    // Calculate total working days in year
    let totalWorkingDays = 0
    for (let month = 1; month <= 12; month++) {
      totalWorkingDays += this.getWorkingDaysInMonth(year, month)
    }
    
    // Calculate total absences in year
    const totalAbsences = this.getAbsencesInYear(employee, year)
    
    // Available working days
    const availableWorkingDays = totalWorkingDays - totalAbsences
    
    // Expected hours = available days * weekly hours / 7
    return availableWorkingDays * (weeklyHours / 7)
  }

  /**
   * Get working days in a month (excluding weekends and holidays)
   */
  getWorkingDaysInMonth(year, month) {
    const startDate = new Date(year, month - 1, 1)
    const endDate = new Date(year, month, 0)
    
    let workingDays = 0
    const currentDate = new Date(startDate)
    
    while (currentDate <= endDate) {
      const dayOfWeek = currentDate.getDay()
      
      // Skip weekends (0 = Sunday, 6 = Saturday)
      if (this.sundaysOff && dayOfWeek === 0) {
        currentDate.setDate(currentDate.getDate() + 1)
        continue
      }
      
      if (dayOfWeek === 6) {
        currentDate.setDate(currentDate.getDate() + 1)
        continue
      }
      
      // Skip holidays (simplified - you might want to add holiday detection)
      if (this.isHoliday(currentDate)) {
        currentDate.setDate(currentDate.getDate() + 1)
        continue
      }
      
      workingDays++
      currentDate.setDate(currentDate.getDate() + 1)
    }
    
    return workingDays
  }

  /**
   * Check if a date is a holiday (simplified implementation)
   */
  isHoliday(date) {
    const month = date.getMonth() + 1
    const day = date.getDate()
    
    // German holidays (simplified)
    const holidays = [
      { month: 1, day: 1 },   // Neujahr
      { month: 5, day: 1 },   // Tag der Arbeit
      { month: 10, day: 3 },  // Tag der Deutschen Einheit
      { month: 12, day: 25 }, // Weihnachten
      { month: 12, day: 26 }, // 2. Weihnachtstag
    ]
    
    return holidays.some(holiday => holiday.month === month && holiday.day === day)
  }

  /**
   * Get absences in a specific month
   */
  getAbsencesInMonth(employee, year, month) {
    if (!employee.absences) return 0
    
    return employee.absences.filter(absenceDate => {
      const date = parseISO(absenceDate)
      return date.getFullYear() === year && date.getMonth() + 1 === month
    }).length
  }

  /**
   * Get absences in a specific year
   */
  getAbsencesInYear(employee, year) {
    if (!employee.absences) return 0
    
    return employee.absences.filter(absenceDate => {
      const date = parseISO(absenceDate)
      return date.getFullYear() === year
    }).length
  }

  /**
   * Calculate utilization percentage
   */
  calculateUtilizationPercentage(actualHours, expectedHours) {
    if (expectedHours <= 0) return 0
    return (actualHours / expectedHours) * 100
  }

  /**
   * Calculate weekly workload
   */
  calculateWeeklyWorkload(scheduleData, year, month) {
    const weeklyWorkload = []
    
    // Get first and last day of month
    const firstDay = new Date(year, month - 1, 1)
    const lastDay = new Date(year, month, 0)
    
    let currentWeek = startOfWeek(firstDay, { weekStartsOn: 1 }) // Monday
    
    while (currentWeek <= lastDay) {
      const weekEnd = endOfWeek(currentWeek, { weekStartsOn: 1 })
      
      // Filter schedule data for this week
      const weekEntries = scheduleData.filter(entry => {
        const entryDate = parseISO(entry.date)
        return entryDate >= currentWeek && entryDate <= weekEnd
      })
      
      // Calculate hours for this week
      const weekHours = weekEntries.reduce((total, entry) => {
        return total + this.calculateShiftHours(entry.shift)
      }, 0)
      
      weeklyWorkload.push(round(weekHours, 3))
      
      // Move to next week
      currentWeek.setDate(currentWeek.getDate() + 7)
    }
    
    return weeklyWorkload
  }

  /**
   * Calculate monthly breakdown for yearly view
   */
  calculateMonthlyBreakdown(scheduleData, year) {
    const monthlyHours = new Array(12).fill(0)
    const monthlyShifts = new Array(12).fill(0)
    
    scheduleData.forEach(entry => {
      const entryDate = parseISO(entry.date)
      if (entryDate.getFullYear() === year) {
        const month = entryDate.getMonth()
        monthlyHours[month] += this.calculateShiftHours(entry.shift)
        monthlyShifts[month]++
      }
    })
    
    return {
      hours: monthlyHours.map(hours => round(hours, 3)),
      shifts: monthlyShifts
    }
  }

  /**
   * Get empty statistics for when no data is available
   */
  getEmptyStatistics() {
    return {
      total_hours: 0,
      total_shifts: 0,
      average_hours_per_shift: 0,
      utilization_percentage: 0,
      weekly_workload: []
    }
  }

  /**
   * Get empty yearly statistics
   */
  getEmptyYearlyStatistics() {
    return {
      total_hours: 0,
      total_shifts: 0,
      average_hours_per_shift: 0,
      max_yearly_hours: 0,
      yearly_utilization_percentage: 0,
      monthly_breakdown: {
        hours: new Array(12).fill(0),
        shifts: new Array(12).fill(0)
      }
    }
  }
}

/**
 * Helper function to round numbers
 */
function round(num, decimals) {
  return Math.round(num * Math.pow(10, decimals)) / Math.pow(10, decimals)
} 