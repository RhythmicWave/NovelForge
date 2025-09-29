<script setup lang="ts">
import { ref, computed } from 'vue'
// 使用基本图标避免导入问题

const props = defineProps<{
  field: any
  level: number
}>()

const emit = defineEmits<{
  'select-field': [string]
  'toggle-expand': [string]
}>()

const expanded = computed({
  get: () => props.field.expanded || false,
  set: (value: boolean) => {
    emit('toggle-expand', props.field.path)
  }
})

const hasChildren = computed(() => {
  return props.field.children && props.field.children.length > 0
})

const typeIcon = computed(() => {
  switch (props.field.type) {
    case 'object': return hasChildren.value ? '📁' : '📄'
    case 'array': return '📊'
    default: return '📄'
  }
})

const typeColor = computed(() => {
  switch (props.field.type) {
    case 'object': return '#409eff'
    case 'array': return '#67c23a'
    case 'string': return '#909399'
    case 'number': return '#e6a23c'
    case 'boolean': return '#f56c6c'
    default: return '#909399'
  }
})

function toggleExpanded() {
  if (hasChildren.value) {
    expanded.value = !expanded.value
  }
}

function handleClick() {
  emit('select-field', props.field.path)
}

function handleChildSelect(fieldPath: string) {
  emit('select-field', fieldPath)
}

function handleChildToggle(fieldPath: string) {
  emit('toggle-expand', fieldPath)
}
</script>

<template>
  <div class="field-node" :style="{ paddingLeft: `${level * 16}px` }">
    <div class="field-row" @click="handleClick">
      <!-- 展开/收起图标 -->
      <div class="expand-icon" @click.stop="toggleExpanded" v-if="hasChildren">
        <span class="expand-arrow">{{ expanded ? '▼' : '▶' }}</span>
      </div>
      <div class="expand-placeholder" v-else></div>
      
      <!-- 类型图标 -->
      <span class="type-icon" :style="{ color: typeColor }">{{ typeIcon }}</span>
      
      <!-- 字段信息 -->
      <div class="field-info">
        <span class="field-name">{{ field.title || field.name }}</span>
        <span class="field-type">{{ field.type }}</span>
        <span v-if="field.required" class="required-marker">*</span>
        <span class="field-path">{{ field.path }}</span>
      </div>
    </div>
    
    <!-- 子字段 -->
    <div v-if="expanded && hasChildren" class="children">
      <FieldTreeNode 
        v-for="child in field.children" 
        :key="child.path"
        :field="child"
        :level="level + 1"
        @select-field="handleChildSelect"
        @toggle-expand="handleChildToggle"
      />
    </div>
  </div>
</template>

<style scoped>
.field-node {
  user-select: none;
  font-size: 12px;
}

.field-row {
  display: flex;
  align-items: center;
  padding: 2px 4px;
  margin: 1px 0;
  border-radius: 3px;
  cursor: pointer;
  transition: background-color 0.15s;
  min-height: 22px;
  overflow: hidden;
}

.field-row:hover {
  background-color: var(--el-color-primary-light-9, #f0f9ff);
}

.expand-icon {
  width: 12px;
  height: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  margin-right: 2px;
}

.expand-arrow {
  font-size: 8px;
  color: var(--el-text-color-secondary, #909399);
  transition: transform 0.15s;
  user-select: none;
}

.expand-placeholder {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  margin-right: 2px;
}

.type-icon {
  margin-right: 3px;
  font-size: 11px;
  flex-shrink: 0;
  line-height: 1;
}

.field-info {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.field-name {
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
  font-size: 11px;
  flex-shrink: 0;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-type {
  font-size: 9px;
  color: var(--el-text-color-secondary, #909399);
  background: var(--el-color-info-light-8, #f4f4f5);
  padding: 1px 3px;
  border-radius: 2px;
  flex-shrink: 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  line-height: 1.2;
}

.required-marker {
  color: var(--el-color-danger, #f56c6c);
  font-weight: bold;
  font-size: 9px;
  flex-shrink: 0;
}

.field-path {
  font-size: 9px;
  color: var(--el-text-color-placeholder, #a8abb2);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
  line-height: 1.2;
}

.children {
  border-left: 1px solid var(--el-border-color-lighter, #ebeef5);
  margin-left: 6px;
  padding-left: 2px;
}

/* 为更深层级的嵌套提供更紧凑的样式 */
.field-node .field-node .field-row {
  min-height: 20px;
  padding: 1px 3px;
}

.field-node .field-node .field-name {
  font-size: 10px;
  max-width: 80px;
}

.field-node .field-node .field-type {
  font-size: 8px;
}

.field-node .field-node .field-path {
  font-size: 8px;
}

/* 响应式调整 */
@media (max-width: 600px) {
  .field-path {
    display: none;
  }
  
  .field-name {
    max-width: 80px;
  }
}
</style>
