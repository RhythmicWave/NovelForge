<template>
  <div class="sectioned-form">
    <el-collapse v-model="activeNames">
      <el-collapse-item v-for="(sec, idx) in sections" :key="idx" :name="String(idx)">
        <template #title>
          <span class="sec-title">{{ sec.title }}</span>
          <span class="sec-desc" v-if="sec.description">{{ sec.description }}</span>
        </template>
        <ModelDrivenForm
          :schema="schema"
          v-model="proxy"
          :include-fields="sec.include"
          :exclude-fields="sec.exclude"
        />
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'
import ModelDrivenForm from './ModelDrivenForm.vue'
import type { SectionConfig } from '@renderer/services/uiLayoutService'

const props = defineProps<{ schema: JSONSchema | undefined; modelValue: any; sections: SectionConfig[] }>()
const emit = defineEmits(['update:modelValue'])

const proxy = ref<any>(props.modelValue)
watch(() => props.modelValue, v => proxy.value = v, { deep: true })
watch(proxy, v => emit('update:modelValue', v), { deep: true })

const activeNames = ref<string[]>([])

// 在首次接收 sections 时，初始化展开状态；后续更新时尽量保留当前展开项
let initialized = false
watch(() => props.sections, (secs) => {
  const namesAll = secs.map((_, i) => String(i))
  if (!initialized) {
    // 展开未标记 collapsed 的分区
    activeNames.value = secs.map((s, i) => (!s.collapsed ? String(i) : '')).filter(Boolean) as string[]
    initialized = true
    return
  }
  // 保留仍然存在的已展开项，并自动展开新出现且未 collapsed 的分区
  const preserved = activeNames.value.filter(n => namesAll.includes(n))
  const newlyOpen = secs
    .map((s, i) => ({ i, s }))
    .filter(({ i, s }) => !s.collapsed && !preserved.includes(String(i)))
    .map(({ i }) => String(i))
  activeNames.value = [...preserved, ...newlyOpen]
}, { immediate: true })
</script>

<style scoped>
.sectioned-form { display: flex; flex-direction: column; gap: 8px; }
.sec-title { font-weight: 600; margin-right: 8px; }
.sec-desc { color: var(--el-text-color-secondary); font-size: 12px; }
</style> 