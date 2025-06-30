export default [
  {
    path: '/',
    name: 'company-selection',
    component: () => import('@/views/CompanySelection.vue')
  },
  {
    path: '/company/:companyId',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { requiresCompany: true }
  },
  {
    path: '/company/:companyId/month',
    name: 'month-view',
    component: () => import('@/views/MonthView.vue'),
    meta: { requiresCompany: true }
  },
  {
    path: '/company/:companyId/employees',
    name: 'employees',
    component: () => import('@/views/Employees.vue'),
    meta: { requiresCompany: true }
  },
  {
    path: '/company/:companyId/day/:date',
    name: 'day-view',
    component: () => import('@/views/DayView.vue'),
    meta: { requiresCompany: true }
  },
  {
    path: '/company/:companyId/employee/:employeeId',
    name: 'employee-view',
    component: () => import('@/views/EmployeeView.vue'),
    meta: { requiresCompany: true }
  },
  {
    path: '/company/:companyId/analytics',
    name: 'analytics',
    component: () => import('@/views/Analytics.vue'),
    meta: { requiresCompany: true }
  },
  {
    path: '/upload-benchmark',
    name: 'upload-benchmark',
    component: () => import('@/views/UploadBenchmark.vue')
  }
] 