<template>
  <el-form-item :label="label" :prop="prop">
    <el-switch
      v-model="internalValue"
      :disabled="readonly"
      @change="handleChange"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  modelValue: boolean | undefined
  label: string
  prop: string
  readonly?: boolean
}>()

const emit = defineEmits(['update:modelValue'])

const internalValue = ref<boolean>(props.modelValue ?? false)

watch(
  () => props.modelValue,
  (val) => {
    internalValue.value = val ?? false
  }
)

function handleChange(val: boolean) {
  emit('update:modelValue', val)
}
</script>

<style scoped>
.el-switch {
  --el-switch-on-color: var(--el-color-primary);
}
</style>
