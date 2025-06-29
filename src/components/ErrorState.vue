<template>
  <div v-if="error" class="alert alert-danger" role="alert">
    <i class="bi bi-exclamation-triangle-fill me-2"></i>
    {{ error }}
  </div>
</template>

<script setup>
defineProps({
  error: {
    type: String,
    default: ''
  }
})
</script> 