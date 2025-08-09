<template>
  <el-form-item :label="label">
    <div class="fallback-field">
      <p class="unsupported-text">
        <strong>Unsupported Field Type:</strong> <code>{{ schema.type }}</code>
      </p>
      <pre class="schema-preview">{{ JSON.stringify(schema, null, 2) }}</pre>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import type { JSONSchema } from '@renderer/api/schema'

defineProps<{
  label: string
  schema: JSONSchema
}>()
</script>

<style scoped>
.fallback-field {
  padding: 10px;
  background-color: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 4px;
  width: 100%;
  box-sizing: border-box;
}

.unsupported-text {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: var(--el-color-warning);
}

.unsupported-text code {
  background-color: var(--el-color-warning-light-7);
  padding: 2px 4px;
  border-radius: 3px;
}

.schema-preview {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  background-color: var(--el-bg-color);
  padding: 8px;
  border-radius: 4px;
}
</style> 