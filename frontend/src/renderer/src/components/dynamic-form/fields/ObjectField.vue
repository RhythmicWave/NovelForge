<template>
  <el-card shadow="never" class="object-field-card">
    <template #header>
      <div class="card-header">
        <span>{{ label }}</span>
      </div>
    </template>
    <ModelDrivenForm
      :schema="schema"
      :modelValue="modelValue || {}"
      @update:modelValue="emit('update:modelValue', $event)"
    />
  </el-card>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

// 使用前向声明来处理递归组件。
// 这在模块级别打破了循环依赖。
const ModelDrivenForm = defineAsyncComponent(() => import('../ModelDrivenForm.vue'))

defineProps<{
  modelValue: Record<string, any> | undefined
  label: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.object-field-card {
  margin-top: 10px;
  margin-bottom: 20px;
  background-color: var(--el-fill-color-lighter);
}
</style> 