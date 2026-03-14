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
        <div class="context-action-combo">
          <el-tooltip content="打开上下文抽屉（Alt+K）">
            <el-button type="primary" plain class="context-main-button" @click="$emit('open-context')">上下文注入</el-button>
          </el-tooltip>
          <el-popover v-model:visible="slotPickerVisible" trigger="click" width="220" popper-class="context-slot-popper">
            <template #reference>
              <el-button type="primary" plain class="context-trigger-button">
                <el-icon><ArrowDown /></el-icon>
              </el-button>
            </template>
            <div class="slot-picker-panel">
              <button
                v-for="kind in contextTemplateKinds"
                :key="kind"
                type="button"
                class="slot-picker-item"
                :class="{ 'is-active': activeContextTemplateKind === kind }"
                @click="selectContextTemplateKind(kind)"
              >
                <span>{{ contextTemplateLabels[kind] }}</span>
                <el-icon v-if="activeContextTemplateKind === kind" class="check-icon"><Select /></el-icon>
              </button>
            </div>
          </el-popover>
        </div>
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
import { ArrowDown, Select } from '@element-plus/icons-vue'
import { CONTEXT_TEMPLATE_LABELS, type ContextTemplateKind } from '@renderer/services/contextSlots'

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
  activeContextTemplateKind?: ContextTemplateKind
}>()

// 计算是否可以保存：如果需要确认，即使没有修改也可以保存
const canSaveComputed = computed(() => {
  if (props.needsConfirmation) return !props.saving
  return props.canSave
})

const emit = defineEmits(['update:title','save','generate','open-versions','delete','open-context','update:active-context-template-kind'])
const slotPickerVisible = ref(false)
const contextTemplateKinds: ContextTemplateKind[] = ['generation', 'review', 'custom']
const contextTemplateLabels = CONTEXT_TEMPLATE_LABELS
const activeContextTemplateKind = computed<ContextTemplateKind>(() => props.activeContextTemplateKind || 'generation')

const titleProxy = ref(props.title)
watch(() => props.title, v => titleProxy.value = v)
watch(titleProxy, v => emit('update:title', v))

const statusTag = computed(() => {
  if (props.needsConfirmation) return { type: 'warning', label: 'AI 已修改' }
  if (props.saving) return { type: 'warning', label: '保存中' }
  if (props.dirty) return { type: 'info', label: '未保存' }
  return { type: 'success', label: '已保存' }
})

function selectContextTemplateKind(kind: ContextTemplateKind) {
  emit('update:active-context-template-kind', kind)
  slotPickerVisible.value = false
}
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
.context-action-combo { display: inline-flex; align-items: stretch; }
.context-main-button { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.context-trigger-button { margin-left: -1px; border-top-left-radius: 0; border-bottom-left-radius: 0; padding-inline: 9px; }
.slot-picker-panel { display: flex; flex-direction: column; gap: 6px; }
.slot-picker-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-fill-color-blank); padding: 8px 10px; cursor: pointer; color: var(--el-text-color-primary); }
.slot-picker-item.is-active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.check-icon { color: var(--el-color-primary); }
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
