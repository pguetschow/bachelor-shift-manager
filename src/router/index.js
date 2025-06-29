import { createRouter, createWebHistory } from 'vue-router'
import routes from './routes'

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard to handle company loading
router.beforeEach(async (to, from, next) => {
  if (to.params.companyId) {
    const { useCompanyStore } = await import('@/stores/company')
    const companyStore = useCompanyStore()
    
    try {
      await companyStore.loadCompany(to.params.companyId)
    } catch (error) {
      console.error('Failed to load company:', error)
      next('/')
      return
    }
  }
  next()
})

export default router 