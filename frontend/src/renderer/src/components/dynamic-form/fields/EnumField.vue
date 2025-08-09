<template>
  <el-form-item :label="label" :prop="prop">
    <el-select
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      clearable
      style="width: 100%"
    >
      <el-option
        v-for="item in schema.enum"
        :key="String(item)"
        :label="String(item)"
        :value="item"
      />
    </el-select>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

const props = defineProps<{
  modelValue: string | number | undefined
  label: string
  prop: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

const placeholder = computed(() => {
  return props.schema.description || `请选择 ${props.label}`
})
</script> 