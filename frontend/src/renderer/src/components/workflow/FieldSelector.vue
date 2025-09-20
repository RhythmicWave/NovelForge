<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ schema: any | null; basePrefix?: string; modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

function collect(schema: any, base = '', acc: Array<{ label: string; value: string }> = [], prefix = '$.content') {
  try {
    const props = (schema?.properties || {}) as Record<string, any>
    Object.keys(props).forEach((k) => {
      const node = props[k]
      const path = base ? `${base}.${k}` : k
      if (node?.type === 'object' && node?.properties) collect(node, path, acc, prefix)
      else acc.push({ label: path, value: `${prefix}.${path}` })
    })
  } catch {}
  return acc
}

const options = computed(() => collect(props.schema || {}, '', [], props.basePrefix || '$.content'))
</script>

<template>
  <el-select :model-value="modelValue" filterable clearable placeholder="字段" style="width: 180px" @update:model-value="(v:any)=>emit('update:modelValue', v)">
    <el-option v-for="o in options" :key="o.value" :label="o.label" :value="o.value" />
  </el-select>
</template>


