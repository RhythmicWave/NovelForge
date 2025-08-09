<template>
  <el-form-item :label="label" :prop="prop">
    <el-input
      v-if="!isLongText"
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      clearable
    />
    <el-input
      v-else
      type="textarea"
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      :autosize="{ minRows: 3, maxRows: 10 }"
      clearable
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

const props = defineProps<{
  modelValue: string | undefined
  label: string
  prop: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

// 一个简单的启发式方法：如果描述或标题表明它是一个长文本字段，则使用文本区域。
// 一个更健壮的解决方案可能是在 schema 中包含一个自定义属性，比如 `x-ui-control: 'textarea'`。
const isLongText = computed(() => {
  const description = props.schema.description?.toLowerCase() || ''
  const title = props.schema.title?.toLowerCase() || ''
  // 如果字段名为overview，强制用textarea
  if (props.prop === 'overview') return true
  return description.includes('思考') || description.includes('过程') || description.includes('描述') || description.includes('概述') || title.includes('thinking')
})

const placeholder = computed(() => {
  return props.schema.description || `请输入 ${props.label}`
})
</script> 