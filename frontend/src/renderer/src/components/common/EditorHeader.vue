<template>
  <div class="editor-header">
    <div class="header-main">
      <div class="left">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item>{{ projectName }}</el-breadcrumb-item>
          <el-breadcrumb-item>{{ cardType }}</el-breadcrumb-item>
          <el-breadcrumb-item>
            <el-input v-model="titleProxy" size="small" class="title-input" />
          </el-breadcrumb-item>
        </el-breadcrumb>
        <el-tag :type="statusTag.type" size="small">{{ statusTag.label }}</el-tag>
        <span v-if="lastSavedAt" class="last-saved">上次保存：{{ lastSavedAt }}</span>
      </div>
      <div class="right">
        <el-tooltip content="打开上下文抽屉（Alt+K）">
          <el-button type="primary" plain @click="$emit('open-context')">上下文注入</el-button>
        </el-tooltip>
        <el-button v-if="!isChapterContent" type="success" plain @click="$emit('generate')">AI 生成</el-button>
        <el-button 
          :type="canSaveComputed ? 'primary' : 'info'" 
          :disabled="!canSaveComputed" 
          :loading="saving" 
          :class="{ 'needs-confirmation-btn': needsConfirmation }"
          @click="$emit('save')"
        >
          {{ needsConfirmation ? '确认并保存' : '保存' }}
        </el-button>
        <el-dropdown>
          <el-button text>更多</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="$emit('open-versions')">历史版本</el-dropdown-item>
              <el-dropdown-item divided type="danger" @click="$emit('delete')">删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue'

const props = defineProps<{
  projectName?: string
  cardType: string
  title: string
  dirty: boolean
  saving: boolean
  lastSavedAt?: string
  canSave?: boolean
  isChapterContent?: boolean
  needsConfirmation?: boolean  // AI 修改需要确认
}>()

// 计算是否可以保存：如果需要确认，即使没有修改也可以保存
const canSaveComputed = computed(() => {
  if (props.needsConfirmation) return !props.saving
  return props.canSave
})

const emit = defineEmits(['update:title','save','generate','open-versions','delete','open-context'])

const titleProxy = ref(props.title)
watch(() => props.title, v => titleProxy.value = v)
watch(titleProxy, v => emit('update:title', v))

const statusTag = computed(() => {
  if (props.needsConfirmation) return { type: 'warning', label: 'AI 已修改' }
  if (props.saving) return { type: 'warning', label: '保存中' }
  if (props.dirty) return { type: 'info', label: '未保存' }
  return { type: 'success', label: '已保存' }
})
</script>

<style scoped>
.editor-header { 
  flex-shrink: 0; /* 固定：防止被压缩 */
}

.header-main {
  display: flex; 
  align-items: center; 
  justify-content: space-between; 
  padding: 8px 12px; 
  border-bottom: 1px solid var(--el-border-color-light); 
  background: var(--el-bg-color);
}

.left { display: flex; align-items: center; gap: 10px; }
.right { display: flex; align-items: center; gap: 8px; }
.title-input { width: 280px; }
.last-saved { color: var(--el-text-color-secondary); font-size: 12px; }

.needs-confirmation-btn {
  animation: pulse 2s infinite;
  box-shadow: 0 0 0 3px rgba(255, 193, 7, 0.3) !important;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
</style> 