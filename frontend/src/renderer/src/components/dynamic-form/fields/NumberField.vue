<template>
  <el-form-item :label="label" :prop="prop">
    <el-input-number 
      v-model="internalValue" 
      @change="handleChange" 
      :disabled="readonly"
      class="full-width"
      :step="step"
      :precision="precision"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

const props = defineProps<{
  modelValue: number | undefined
  label: string
  prop: string
  readonly?: boolean
  schema?: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

const internalValue = ref(props.modelValue)

const isInteger = computed(() => props.schema?.type === 'integer')
const step = computed(() => (isInteger.value ? 1 : undefined))
const precision = computed(() => (isInteger.value ? 0 : undefined))

watch(() => props.modelValue, (newValue) => {
  internalValue.value = newValue
})

function handleChange(value: number | undefined) {
  if (value != null && props.schema?.type === 'integer') {
    // 强制转为整数，避免出现小数
    const intVal = Math.floor(value)
    emit('update:modelValue', intVal)
  } else {
    emit('update:modelValue', value)
  }
}
</script>

<style scoped>
.full-width {
  width: 100%;
}
</style> 