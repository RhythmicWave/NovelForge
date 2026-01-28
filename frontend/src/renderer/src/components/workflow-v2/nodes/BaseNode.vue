<template>
  <div class="workflow-node" :class="{ selected }">
    <!-- 节点头部 -->
    <div class="node-header">
      <div class="node-icon">
        <el-icon :size="16">
          <component :is="icon" />
        </el-icon>
      </div>
      <div class="node-text">
        <div class="node-type">{{ type }}</div>
        <div v-if="label" class="node-title">{{ label }}</div>
      </div>
    </div>

    <!-- 节点主体：端口区域 -->
    <div class="node-body">
      <!-- 输入端口列表 -->
      <div class="port-section inputs">
        <div 
          v-for="input in inputPorts" 
          :key="input.name"
          class="port-row"
        >
          <!-- Handle 放在左侧，使用 relative 定位微调位置 -->
          <Handle 
            :id="input.name"
            type="target" 
            :position="Position.Left"
            class="port-handle port-handle-input"
            :connectable="true"
          />
          <div class="port-label">
            <span class="port-name">{{ input.name }}</span>
            <span v-if="input.required" class="port-required">*</span>
          </div>
        </div>
      </div>

      <!-- 输出端口列表 -->
      <div class="port-section outputs">
        <div 
          v-for="output in outputPorts" 
          :key="output.name"
          class="port-row"
        >
          <div class="port-label">
            <span class="port-name">{{ output.name }}</span>
          </div>
          <Handle 
            :id="output.name"
            type="source" 
            :position="Position.Right"
            class="port-handle port-handle-output"
            :connectable="true"
          />
        </div>
      </div>
    </div>

    <!-- 快捷添加按钮 (悬停时显示) -->
    <div 
      v-if="outputPorts.length > 0"
      class="quick-add-button"
      @click.stop="handleSourceClick"
    >
      <el-icon><Plus /></el-icon>
    </div>

    <!-- 控制流端口 (虚线依赖) -->
    <Handle 
      type="target" 
      :position="Position.Top" 
      id="dep-input"
      class="dep-handle dep-handle-input"
      title="依赖输入（控制流）"
    />
    <Handle 
      type="source" 
      :position="Position.Bottom" 
      id="dep-output"
      class="dep-handle dep-handle-output"
      title="依赖输出（控制流）"
    />
  </div>
</template>

<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed, markRaw, inject } from 'vue'
import { Plus, Lightning } from '@element-plus/icons-vue'
import * as ElementPlusIcons from '@element-plus/icons-vue'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'

const props = defineProps<{
  id: string
  type: string
  data: {
    label: string
    description?: string
  }
  selected?: boolean
}>()

const workflowStore = useWorkflowStore()
const onAddNode = inject<(payload: { nodeId: string; handleId?: string; event: MouseEvent }) => void>('onAddNode')

// 获取节点类型定义
const nodeDefinition = computed(() => workflowStore.getNodeType(props.type))

// 获取输入端口列表
const inputPorts = computed(() => {
  return nodeDefinition.value?.inputs || []
})

// 获取输出端口列表
const outputPorts = computed(() => {
  return nodeDefinition.value?.outputs || []
})

// 获取图标组件
const icon = computed(() => {
  let iconName = 'Document'
  if (props.type.startsWith('Card.')) iconName = 'Collection'
  if (props.type.startsWith('Logic.')) iconName = 'Operation'
  if (props.type.startsWith('Data.')) iconName = 'DataAnalysis'
  if (props.type.startsWith('AI.')) iconName = 'MagicStick'
  if (props.type.startsWith('Trigger.')) return Lightning
  
  return markRaw((ElementPlusIcons as any)[iconName] || ElementPlusIcons.Document)
})

const emit = defineEmits<{
  'add-node': [event: MouseEvent]
}>()

const label = computed(() => props.data?.label || props.type)
const description = computed(() => props.data?.description)

// 点击输出端口
const handleSourceClick = (event: MouseEvent) => {
  if (onAddNode) {
    onAddNode({ nodeId: props.id, event })
  } else {
    emit('add-node', event)
  }
}
</script>

<style scoped lang="scss">
.workflow-node {
  background: rgba(255, 255, 255, 0.98);  /* 改为不透明背景，移除模糊效果 */
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: var(--border-radius-md);
  padding: 0;
  min-width: 200px;
  max-width: 240px;
  box-shadow: var(--shadow-md);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  cursor: pointer;
  will-change: transform;  /* 提示浏览器优化transform动画 */

  &:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-lg);
    border-color: var(--primary-color);
  }

  &.selected {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px var(--primary-color), var(--shadow-lg);
  }
}

.node-content {
  display: flex;
  flex-direction: column;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(to right, rgba(248, 250, 252, 0.5), rgba(255, 255, 255, 0));
  border-bottom: 1px solid var(--border-color);
  /* Manually round top corners */
  border-top-left-radius: var(--border-radius-md);
  border-top-right-radius: var(--border-radius-md);
}

.node-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--primary-gradient);
  color: #fff;
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}

.node-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.node-type {
  font-size: 10px;
  font-weight: 500;
  color: var(--text-muted);
  line-height: 1.2;
  letter-spacing: 0.5px;
}

.node-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.node-description {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding: 12px 16px;
  background: #fff;
  /* Manually round bottom corners */
  border-bottom-left-radius: var(--border-radius-md);
  border-bottom-right-radius: var(--border-radius-md);
}


// 节点主体：ComfyUI 风格布局
.node-body {
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.port-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.port-row {
  position: relative;
  height: 26px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  transition: background 0.2s;
  
  &:hover {
    background: rgba(0, 0, 0, 0.02);
  }
}

// 端口标签
.port-label {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-family: 'Fira Code', monospace; /* 程序员友好字体 */
}

.inputs .port-row {
  justify-content: flex-start;
  .port-label { margin-left: 8px; }
}

.outputs .port-row {
  justify-content: flex-end;
  .port-label { margin-right: 8px; }
}

.port-required {
  color: #f56c6c;
  margin-left: 2px;
}

// 端口 Handle 样式
.port-handle {
  width: 10px !important;
  height: 10px !important;
  border: 2px solid #fff !important;
  background: var(--text-muted) !important;
  transition: all 0.2s;
  z-index: 10;
  
  &:hover {
    background: var(--primary-color) !important;
    transform: scale(1.3) translateY(-50%) !important; /* 保持垂直居中 */
  }
}

.port-handle-input {
  left: -5px !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
}

.port-handle-output {
  right: -5px !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
}

// 依赖控制流 Handle (Top/Bottom)
.dep-handle {
  width: 24px !important; /* 更宽，易于点击 */
  height: 8px !important;
  border-radius: 4px !important;
  background: #E4E7ED !important;
  border: 1px solid #fff !important;
  transition: all 0.2s;
  
  &:hover {
    background: var(--primary-color) !important;
    height: 10px !important;
  }
}

.dep-handle-input {
  top: -4px !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
}

.dep-handle-output {
  bottom: -4px !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
}

// 快捷添加按钮
.quick-add-button {
  position: absolute;
  right: -24px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  background: var(--primary-color);
  border-radius: 50%;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  opacity: 0;
  transition: all 0.2s;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  z-index: 99;
}

.workflow-node:hover .quick-add-button {
  opacity: 1;
}
</style>
