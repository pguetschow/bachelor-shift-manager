<template>
  <div class="upload-benchmark">
    <div class="container mx-auto px-4 py-8">
      <div class="max-w-2xl mx-auto">
        <h1 class="text-3xl font-bold text-gray-900 mb-8">Upload Benchmark Results</h1>
        
        <!-- Instructions -->
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8">
          <h2 class="text-lg font-semibold text-blue-900 mb-4">Instructions</h2>
          <ol class="list-decimal list-inside space-y-2 text-blue-800">
            <li>Export results as SQL dump using: <code class="bg-blue-100 px-2 py-1 rounded">python manage.py export_sql_dump --include-schedules</code></li>
            <li>Upload the generated ZIP file below</li>
            <li>Results will be imported into the deployed database</li>
          </ol>
          <div class="mt-4 p-3 bg-green-50 border border-green-200 rounded">
            <p class="text-sm text-green-800">
              <strong>💡 Tip:</strong> SQL dumps are faster and more reliable than the old JSON method. 
              The system automatically detects and uses SQL dumps when available.
            </p>
          </div>
        </div>

        <!-- Upload Area -->
        <div 
          class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center transition-colors"
          :class="{
            'border-blue-400 bg-blue-50': isDragOver,
            'border-gray-300 bg-gray-50': !isDragOver
          }"
          @drop="handleDrop"
          @dragover.prevent="isDragOver = true"
          @dragleave.prevent="isDragOver = false"
          @dragenter.prevent
        >
          <div v-if="!uploading && !uploadComplete">
            <p class="text-lg font-medium text-gray-900 mb-2">
              Upload Benchmark Results
            </p>
            <p class="text-gray-500 mb-4">
              Drag and drop a ZIP file here, or click to select
            </p>
            <input
              ref="fileInput"
              type="file"
              accept=".zip"
              class="hidden"
              @change="handleFileSelect"
            />
            <button
              @click="$refs.fileInput.click()"
              class="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Select ZIP File
            </button>
          </div>

          <!-- Upload Progress -->
          <div v-if="uploading" class="space-y-4">
            <div class="flex items-center justify-center">
              <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
            <p class="text-gray-600">Uploading benchmark results...</p>
            <div v-if="uploadProgress > 0" class="w-full bg-gray-200 rounded-full h-2">
              <div class="bg-blue-600 h-2 rounded-full transition-all duration-300" :style="{ width: uploadProgress + '%' }"></div>
            </div>
          </div>

          <!-- Upload Complete -->
          <div v-if="uploadComplete" class="space-y-4">
            <p class="text-lg font-medium text-green-900">Upload Complete!</p>
            <div class="text-left bg-green-50 border border-green-200 rounded-lg p-4">
              <h3 class="font-semibold text-green-900 mb-2">Import Summary:</h3>
              <ul class="space-y-1 text-sm text-green-800">
                <li>Companies: {{ importSummary.companies_imported }}</li>
                <li>Employees: {{ importSummary.employees_imported }}</li>
                <li>Shifts: {{ importSummary.shifts_imported }}</li>
                <li>Schedule Entries: {{ importSummary.schedule_entries_imported }}</li>
              </ul>
              <div v-if="importSummary.errors.length > 0" class="mt-3">
                <h4 class="font-semibold text-red-900 mb-1">Errors:</h4>
                <ul class="space-y-1 text-sm text-red-800">
                  <li v-for="error in importSummary.errors" :key="error">{{ error }}</li>
                </ul>
              </div>
            </div>
            <button
              @click="resetUpload"
              class="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Upload Another File
            </button>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mt-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <div class="flex">
            <div class="ml-3">
              <h3 class="text-sm font-medium text-red-800">Upload Failed</h3>
              <p class="mt-1 text-sm text-red-700">{{ error }}</p>
            </div>
          </div>
        </div>

        <!-- Back to Dashboard -->
        <div class="mt-8 text-center">
          <router-link
            to="/"
            class="text-blue-600 hover:text-blue-800 font-medium transition-colors"
          >
            ← Back to Dashboard
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive } from 'vue'
import { apiService } from '@/services/api'

export default {
  name: 'UploadBenchmark',
  setup() {
    const fileInput = ref(null)
    const isDragOver = ref(false)
    const uploading = ref(false)
    const uploadComplete = ref(false)
    const uploadProgress = ref(0)
    const error = ref('')
    const importSummary = reactive({
      companies_imported: 0,
      employees_imported: 0,
      shifts_imported: 0,
      schedule_entries_imported: 0,
      errors: []
    })

    const handleFileSelect = (event) => {
      const file = event.target.files[0]
      if (file) {
        uploadFile(file)
      }
    }

    const handleDrop = (event) => {
      isDragOver.value = false
      const files = event.dataTransfer.files
      if (files.length > 0) {
        const file = files[0]
        if (file.name.endsWith('.zip')) {
          uploadFile(file)
        } else {
          error.value = 'Please select a ZIP file'
        }
      }
    }

    const uploadFile = async (file) => {
      if (!file.name.endsWith('.zip')) {
        error.value = 'Please select a ZIP file'
        return
      }

      uploading.value = true
      uploadComplete.value = false
      error.value = ''
      uploadProgress.value = 0

      try {
        const formData = new FormData()
        formData.append('file', file)

        // Simulate progress
        const progressInterval = setInterval(() => {
          if (uploadProgress.value < 90) {
            uploadProgress.value += 10
          }
        }, 200)

        const response = await apiService.uploadBenchmarkResults(formData)
        
        clearInterval(progressInterval)
        uploadProgress.value = 100

        // Update import summary
        Object.assign(importSummary, response.import_summary)
        
        uploading.value = false
        uploadComplete.value = true

        // Reset file input
        if (fileInput.value) {
          fileInput.value.value = ''
        }

      } catch (err) {
        clearInterval(progressInterval)
        uploading.value = false
        error.value = err.message || 'Upload failed'
      }
    }

    const resetUpload = () => {
      uploadComplete.value = false
      uploadProgress.value = 0
      error.value = ''
      Object.assign(importSummary, {
        companies_imported: 0,
        employees_imported: 0,
        shifts_imported: 0,
        schedule_entries_imported: 0,
        errors: []
      })
    }

    return {
      fileInput,
      isDragOver,
      uploading,
      uploadComplete,
      uploadProgress,
      error,
      importSummary,
      handleFileSelect,
      handleDrop,
      resetUpload
    }
  }
}
</script>

<style scoped>
.upload-benchmark {
  min-height: 100vh;
  background-color: #f9fafb;
}
</style> 