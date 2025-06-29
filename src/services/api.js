import axios from 'axios'

// Create axios instance with default configuration
export const api = axios.create({
  baseURL: process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  }
})

// Request interceptor to add CSRF token
api.interceptors.request.use(
  (config) => {
    // Get CSRF token from cookie if available
    const csrfToken = document.cookie
      .split('; ')
      .find(row => row.startsWith('csrftoken='))
      ?.split('=')[1]
    
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken
    }
    
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized access
      window.location.href = '/'
    } else if (error.response?.status === 404) {
      // Handle not found
      console.error('Resource not found:', error.config.url)
    } else if (error.response?.status >= 500) {
      // Handle server errors
      console.error('Server error:', error.response.data)
    }
    
    return Promise.reject(error)
  }
)

// API methods for different endpoints
export const companyAPI = {
  getAll: () => api.get('/api/companies/'),
  getById: (id) => api.get(`/api/companies/${id}/`),
  getSchedule: (id, params) => api.get(`/api/companies/${id}/schedule/`, { params }),
  getAlgorithms: (id) => api.get(`/api/companies/${id}/algorithms/`),
  getEmployees: (id) => api.get(`/api/companies/${id}/employees/`),
  getShifts: (id) => api.get(`/api/companies/${id}/shifts/`)
}

export const scheduleAPI = {
  getByDate: (companyId, date) => api.get(`/api/companies/${companyId}/schedule/${date}/`),
  getByMonth: (companyId, year, month, algorithm) => {
    const params = { year, month }
    if (algorithm) params.algorithm = algorithm
    return api.get(`/api/companies/${companyId}/schedule/`, { params })
  },
  getEmployeeSchedule: (companyId, employeeId, year, month) => 
    api.get(`/api/companies/${companyId}/employees/${employeeId}/schedule/`, { 
      params: { year, month } 
    })
}

export const analyticsAPI = {
  getCoverageStats: (companyId, year, month, algorithm) => {
    const params = { year, month }
    if (algorithm) params.algorithm = algorithm
    return api.get(`/api/companies/${companyId}/analytics/coverage/`, { params })
  },
  getEmployeeStats: (companyId, year, month, algorithm) => {
    const params = { year, month }
    if (algorithm) params.algorithm = algorithm
    return api.get(`/api/companies/${companyId}/analytics/employees/`, { params })
  },
  getShiftStats: (companyId, year, month, algorithm) => {
    const params = { year, month }
    if (algorithm) params.algorithm = algorithm
    return api.get(`/api/companies/${companyId}/analytics/shifts/`, { params })
  }
} 