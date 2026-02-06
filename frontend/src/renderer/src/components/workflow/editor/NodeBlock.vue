<template>
  <div 
    class="node-block"
    :class="{ 'selected': isSelected, 'collapsed': node.collapsed }"
    @click="$emit('select')"
  >
    <!-- 节点头部 -->
    <div class="node-header">
      <div class="node-info">
        <el-tag :type="getCategoryType(node.category)" size="small">
          {{ node.category }}
        </el-tag>
        
        <!-- 变量名编辑 -->
        <NodeVariableEditor
          v-if="editingVariable"
          :value="node.variable"
          @save="handleVariableSave"
          @cancel="$emit('cancel-variable-edit')"
        />
        <span
          v-else
          class="node-variable editable"
          @click.stop="$emit('start-variable-edit')"
          title="点击编辑变量名"
        >
          {{ node.variable }}
        </span>
        <span class="node-type">{{ node.nodeType }}</span>
      </div>
      
      <div class="node-actions">
        <el-tooltip content="删除节点" placement="top">
          <el-button
            size="small"
            text
            type="danger"
            @click.stop="$emit('delete')"
            :icon="Delete"
          />
        </el-tooltip>
      </div>
    </div>

    <!-- 节点参数 -->
    <NodeParameters
      v-if="!node.collapsed"
      :fields="node.fields"
      :editing-param="editingParam"
      @start-edit="handleStartParamEdit"
      @save-edit="handleSaveParamEdit"
      @cancel-edit="$emit('cancel-param-edit')"
    />

    <!-- 输出字段 -->
    <NodeOutputs
      v-if="!node.collapsed && node.outputs?.length > 0"
      :outputs="node.outputs"
      :variable="node.variable"
    />
  </div>
</template>

<script setup>
import { Delete } from '@element-plus/icons-vue'
import NodeVariableEditor from './NodeVariableEditor.vue'
import NodeParameters from './NodeParameters.vue'
import NodeOutputs from './NodeOutputs.vue'

const props = defineProps({
  node: {
    type: Object,
    required: true
  },
  isSelected: {
    type: Boolean,
    default: false
  },
  editingVariable: {
    type: Boolean,
    default: false
  },
  editingParam: {
    type: Object,
    default: null
  }
})

const emit = defineEmits([
  'select',
  'delete',
  'start-variable-edit',
  'save-variable',
  'cancel-variable-edit',
  'start-param-edit',
  'save-param',
  'cancel-param-edit'
])

function getCategoryType(category) {
  const typeMap = {
    'Logic': 'primary',
    'Data': 'success',
    'Novel': 'warning',
    'Card': 'info',
    'AI': 'danger',
    'Trigger': 'warning',
    'Context': 'info'
  }
  return typeMap[category] || ''
}

function handleVariableSave(newName) {
  emit('save-variable', newName)
}

function handleStartParamEdit(fieldIndex) {
  emit('start-param-edit', fieldIndex)
}

function handleSaveParamEdit(value) {
  emit('save-param', value)
}
</script>

<style scoped>
.node-block {
  background: white;
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.node-block:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}

.node-block.selected {
  border-color: #409eff;
  background: #f0f9ff;
}

.node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.node-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.node-variable {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.node-variable.editable:hover {
  color: #409eff;
  text-decoration: underline;
}

.node-type {
  color: #909399;
  font-size: 13px;
}

.node-actions {
  display: flex;
  gap: 4px;
}
</style>
