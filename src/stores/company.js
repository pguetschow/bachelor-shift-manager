import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/api'

export const useCompanyStore = defineStore('company', () => {
  const companies = ref([])
  const currentCompany = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const getCompanyById = computed(() => {
    return (id) => companies.value.find(company => company.id === parseInt(id))
  })

  async function loadCompanies() {
    loading.value = true
    error.value = null
    
    try {
      const response = await api.get('/api/companies/')
      companies.value = response.data
    } catch (err) {
      error.value = 'Failed to load companies'
      console.error('Error loading companies:', err)
    } finally {
      loading.value = false
    }
  }

  async function loadCompany(companyId) {
    loading.value = true
    error.value = null
    
    try {
      const response = await api.get(`/api/companies/${companyId}/`)
      currentCompany.value = response.data
    } catch (err) {
      error.value = 'Failed to load company'
      console.error('Error loading company:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  function setCurrentCompany(company) {
    currentCompany.value = company
  }

  function clearCurrentCompany() {
    currentCompany.value = null
  }

  return {
    companies,
    currentCompany,
    loading,
    error,
    getCompanyById,
    loadCompanies,
    loadCompany,
    setCurrentCompany,
    clearCurrentCompany
  }
}) 