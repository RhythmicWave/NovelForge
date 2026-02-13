<template>
  <div class="agent-composer">
    <el-input
      v-model="innerValue"
      type="textarea"
      :rows="rows"
      :resize="resize"
      :placeholder="placeholder"
      :disabled="disabled"
      @keydown="handleKeydown"
      :class="['composer-input', inputClass]"
    />
    <div class="composer-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
  rows?: number
  resize?: 'none' | 'both' | 'horizontal' | 'vertical'
  inputClass?: string
}>(), {
  placeholder: '请输入内容',
  disabled: false,
  rows: 3,
  resize: 'none',
  inputClass: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'keydown', event: KeyboardEvent): void
}>()

const innerValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})

function handleKeydown(event: KeyboardEvent) {
  emit('keydown', event)
}
</script>

<style scoped>
.agent-composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.composer-input {
  width: 100%;
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
