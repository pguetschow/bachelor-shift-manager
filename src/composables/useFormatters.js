import { format } from 'date-fns'
import { de } from 'date-fns/locale'

export function useFormatters() {
  const formatNumber = (num) => {
    if (num === null || num === undefined) return '0'
    return parseFloat(num).toFixed(3).replace(/\.?0+$/, '')
  }

  const formatTime = (timeString) => {
    if (!timeString) return ''
    // Remove seconds if present and format as HH:mm
    return timeString.substring(0, 5)
  }

  const formatDate = (date) => {
    if (!date) return ''
    return format(new Date(date), 'dd.MM.yyyy', { locale: de })
  }

  const formatDateTime = (date) => {
    if (!date) return ''
    return format(new Date(date), 'dd.MM.yyyy HH:mm', { locale: de })
  }

  const formatMonth = (year, month) => {
    const date = new Date(year, month - 1)
    return format(date, 'MMMM yyyy', { locale: de })
  }

  const getDayOfWeek = (date) => {
    if (!date) return ''
    return format(new Date(date), 'EEEE', { locale: de })
  }

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
    const classMap = {
      'EarlyShift': 'shift-early',
      'MorningShift': 'shift-morning',
      'LateShift': 'shift-late',
      'NightShift': 'shift-night'
    }
    return classMap[shiftName] || 'shift-default'
  }

  const getStatusText = (status) => {
    const statusMap = {
      'ok': 'OK',
      'understaffed': 'Unterbesetzt',
      'overstaffed': 'Überbesetzt',
      'full': 'Voll'
    }
    return statusMap[status] || status
  }

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'ok': return 'bg-success'
      case 'understaffed': return 'bg-danger'
      case 'overstaffed': return 'bg-warning'
      default: return 'bg-primary'
    }
  }

  const getProgressBarClass = (coveragePercentage) => {
    if (coveragePercentage < 80) return 'bg-danger'
    if (coveragePercentage < 95) return 'bg-warning'
    return 'bg-success'
  }

  return {
    formatNumber,
    formatTime,
    formatDate,
    formatDateTime,
    formatMonth,
    getDayOfWeek,
    getShiftDisplayName,
    getShiftColorClass,
    getStatusText,
    getStatusBadgeClass,
    getProgressBarClass
  }
} 