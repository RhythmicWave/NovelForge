<template>
  <div class="template-input">
    <div class="input-header" v-if="variables.length > 0">
      <span class="label">插入变量:</span>
      <div class="variable-tags">
        <el-tag
          v-for="v in variables"
          :key="v.value"
          size="small"
          effect="plain"
          class="var-tag"
          @click="insertVariable(v.value)"
        >
          {{ v.label }}
        </el-tag>
      </div>
    </div>
    <el-input
      ref="inputRef"
      :model-value="modelValue"
      @input="handleInput"
      type="textarea"
      :rows="rows"
      :placeholder="placeholder"
      resize="vertical"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue: string
  variables: Array<{ label: string; value: string }>
  rows?: number
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}>()

const inputRef = ref()

const handleInput = (val: string) => {
  emit('update:modelValue', val)
  emit('change', val)
}

const insertVariable = (variable: string) => {
  const inputEl = inputRef.value.textarea || inputRef.value.$el.querySelector('textarea')
  if (!inputEl) {
    // Fallback if ref not ready
    const newVal = (props.modelValue || '') + variable
    emit('update:modelValue', newVal)
    emit('change', newVal)
    return
  }

  const start = inputEl.selectionStart
  const end = inputEl.selectionEnd
  const text = props.modelValue || ''
  
  const before = text.substring(0, start)
  const after = text.substring(end)
  
  const newVal = before + variable + after
  
  emit('update:modelValue', newVal)
  emit('change', newVal)
  
  // Restore focus and cursor
  setTimeout(() => {
    inputEl.focus()
    const newPos = start + variable.length
    inputEl.setSelectionRange(newPos, newPos)
  }, 0)
}
</script>

<style scoped>
.template-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.label {
  font-size: 12px;
  color: var(--text-secondary);
}

.variable-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.var-tag {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.var-tag:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
</style>
