<template>
  <el-form-item :label="label" :prop="prop">
    <el-input-number 
      v-model="internalValue" 
      @change="handleChange" 
      :disabled="readonly"
      class="full-width"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

const props = defineProps<{
  modelValue: number | undefined
  label: string
  prop: string
  readonly?: boolean
}>()

const emit = defineEmits(['update:modelValue'])

const internalValue = ref(props.modelValue)

watch(() => props.modelValue, (newValue) => {
  internalValue.value = newValue
})

function handleChange(value: number | undefined) {
  emit('update:modelValue', value)
}
</script>

<style scoped>
.full-width {
  width: 100%;
}
</style> 