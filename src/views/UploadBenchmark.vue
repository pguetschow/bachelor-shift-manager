<template>
  <div class="upload-benchmark">
    <div class="container mx-auto px-4 py-8">
      <div class="max-w-2xl mx-auto">
        <h1 class="text-3xl font-bold text-gray-900 mb-8">Benchmark-Ergebnisse hochladen</h1>
        
        <!-- Instructions -->
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8">
          <h2 class="text-lg font-semibold text-blue-900 mb-4">Anweisungen</h2>
          <ol class="list-decimal list-inside space-y-2 text-blue-800">
            <li>Ergebnisse als SQL-Dump exportieren mit: <code class="bg-blue-100 px-2 py-1 rounded">python manage.py export_sql_dump --include-schedules</code></li>
            <li>Generierte ZIP-Datei unten hochladen</li>
            <li>Ergebnisse werden in die bereitgestellte Datenbank importiert</li>
          </ol>
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
              Benchmark-Ergebnisse hochladen
            </p>
            <p class="text-gray-500 mb-4">
              ZIP-Datei hierher ziehen oder klicken zur Auswahl
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
              class="btn btn-lg btn-primary mt-3"
            >
              ZIP-Datei hochladen
            </button>
          </div>

          <!-- Upload Progress -->
          <div v-if="uploading" class="space-y-4">
            <div class="flex items-center justify-center">
              <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
            <p class="text-gray-600">Benchmark-Ergebnisse werden hochgeladen...</p>
            <div v-if="uploadProgress > 0" class="w-full bg-gray-200 rounded-full h-2">
              <div class="bg-blue-600 h-2 rounded-full transition-all duration-300" :style="{ width: uploadProgress + '%' }"></div>
            </div>
          </div>

          <!-- Upload Complete -->
          <div v-if="uploadComplete" class="space-y-4">
            <p class="text-lg font-medium text-green-900">Upload abgeschlossen!</p>
            <button
              @click="resetUpload"
              class="btn btn-lg btn-primary mt-3"
            >
              Weitere Datei hochladen
            </button>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mt-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <div class="flex">
            <div class="ml-3">
              <h3 class="text-sm font-medium text-red-800">Upload fehlgeschlagen</h3>
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
            ← Zurück zum Dashboard
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
    }

    return {
      fileInput,
      isDragOver,
      uploading,
      uploadComplete,
      uploadProgress,
      error,
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