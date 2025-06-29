<template>
  <div class="algorithm-selector">
    <select 
      :value="selected" 
      @change="$emit('change', $event.target.value)"
      class="form-select form-select-sm d-inline-block w-auto ms-3"
    >
      <option value="">Alle Algorithmen</option>
      <option 
        v-for="algorithm in algorithms" 
        :key="algorithm" 
        :value="algorithm"
      >
        {{ algorithm }}
      </option>
    </select>
  </div>
</template>

<script setup>
defineProps({
  algorithms: {
    type: Array,
    default: () => []
  },
  selected: {
    type: String,
    default: ''
  }
})

defineEmits(['change'])
</script>

<style scoped>
.algorithm-selector {
  display: inline-block;
}
</style> 