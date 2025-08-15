<template>
  <el-card shadow="never" class="object-field-card">
    <template #header>
      <div class="card-header">
        <span>{{ label }}</span>
      </div>
    </template>
    <ModelDrivenForm
      :schema="effectiveSchema"
      :modelValue="modelValue || {}"
      @update:modelValue="emit('update:modelValue', $event)"
    />
  </el-card>
</template>

<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

// 使用前向声明来处理递归组件。
// 这在模块级别打破了循环依赖。
const ModelDrivenForm = defineAsyncComponent(() => import('../ModelDrivenForm.vue'))

const props = defineProps<{
  modelValue: Record<string, any> | undefined
  label: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

// 当 schema 未声明 properties 但数据存在时，按数据键名动态补齐，保证可渲染
const effectiveSchema = computed<JSONSchema>(() => {
  const sch = props.schema || { type: 'object' }
  const hasProps = sch && typeof sch === 'object' && (sch as any).properties && Object.keys((sch as any).properties as any).length > 0
  if (hasProps) return sch
  const dataKeys = Object.keys(props.modelValue || {})
  if (dataKeys.length === 0) return sch
  const itemSchema: JSONSchema = {
    type: 'object',
    title: 'Item',
    properties: {
      id: { type: 'integer', title: 'id' },
      info: { type: 'string', title: 'info' },
      weight: { type: 'number', title: 'weight' },
    },
  }
  const propsMap: Record<string, JSONSchema> = {}
  for (const k of dataKeys) {
    propsMap[k] = { type: 'array', items: itemSchema, title: k }
  }
  return { ...sch, type: 'object', properties: propsMap }
})
</script>

<style scoped>
.object-field-card {
  margin-top: 10px;
  margin-bottom: 20px;
  background-color: var(--el-fill-color-lighter);
}
</style> 