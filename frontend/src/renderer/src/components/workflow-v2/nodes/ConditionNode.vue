<template>
  <div class="workflow-node condition-node" :class="{ selected }">
    <!-- 左侧输入端口 -->
    <Handle 
      type="target" 
      :position="Position.Left" 
      class="node-handle node-handle-target"
    />

    <!-- 节点内容 -->
    <div class="node-content">
      <!-- 节点头部 -->
      <div class="node-header">
        <div class="node-icon">
          <el-icon :size="16">
            <CircleCheck />
          </el-icon>
        </div>
        <div class="node-title">{{ label }}</div>
      </div>

      <!-- 节点描述 -->
      <div v-if="description" class="node-description">
        {{ description }}
      </div>
    </div>

    <!-- 右侧输出端口 - True (上方) -->
    <div 
      class="source-handle-wrapper handle-wrapper-true"
      :style="{ top: '30%' }"
      @dblclick.stop="(e) => handleSourceDoubleClick(e, 'true')"
    >
      <Handle 
        id="true"
        type="source" 
        :position="Position.Right" 
        class="node-handle node-handle-source handle-true"
      />
      <el-icon class="plus-icon">
        <Plus />
      </el-icon>
      <span class="handle-label">True</span>
    </div>

    <!-- 右侧输出端口 - False (下方) -->
    <div 
      class="source-handle-wrapper handle-wrapper-false"
      :style="{ top: '70%' }"
      @dblclick.stop="(e) => handleSourceDoubleClick(e, 'false')"
    >
      <Handle 
        id="false"
        type="source" 
        :position="Position.Right" 
        class="node-handle node-handle-source handle-false"
      />
      <el-icon class="plus-icon">
        <Plus />
      </el-icon>
      <span class="handle-label">False</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { CircleCheck, Plus } from '@element-plus/icons-vue'
import { computed } from 'vue'

const props = defineProps<{
  id: string
  type: string
  data: {
    label: string
    description?: string
    onAddNode?: (nodeId: string, handleId: string, event: MouseEvent) => void
  }
  selected?: boolean
}>()

const label = computed(() => props.data?.label || '条件分支')
const description = computed(() => props.data?.description)

// 双击输出端口
const handleSourceDoubleClick = (event: MouseEvent, handleId: string) => {
  if (props.data?.onAddNode) {
    props.data.onAddNode(props.id, handleId, event)
  }
}
</script>

<style scoped lang="scss">
.condition-node {
  background: #fff;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px 16px;
  min-width: 180px;
  max-width: 220px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.2s ease;
  cursor: pointer;
  position: relative;

  &:hover {
    border-color: #409eff;
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
    transform: translateY(-1px);
  }

  &.selected {
    border-color: #409eff;
    box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.2);
  }
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.node-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: #fff;
  flex-shrink: 0;
}

.node-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
}

.node-description {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 2px;
}

// 端口样式
.node-handle {
  width: 12px !important;
  height: 12px !important;
  border: 2px solid #fff !important;
  transition: all 0.2s;
  position: absolute;

  &:hover {
    width: 14px !important;
    height: 14px !important;
  }
}

.node-handle-target {
  left: -6px !important;
  background: #409eff !important;
}

.node-handle-source {
  right: -6px !important;
}

// True端口 - 绿色
.handle-true {
  background: #67c23a !important;
  
  &:hover {
    background: #85ce61 !important;
  }
}

// False端口 - 红色
.handle-false {
  background: #f56c6c !important;
  
  &:hover {
    background: #f78989 !important;
  }
}

// 端口标签
.handle-label {
  position: absolute;
  right: -40px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  font-weight: 600;
  color: #606266;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s;
}

.condition-node:hover .handle-label {
  opacity: 1;
}

// 输出端口包装器（带+号）
.source-handle-wrapper {
  position: absolute;
  right: -6px;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  
  &:hover {
    .plus-icon {
      opacity: 1;
    }
  }
}

.plus-icon {
  position: absolute;
  font-size: 10px;
  color: #fff;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
  z-index: 11;
}

.condition-node:hover .plus-icon {
  opacity: 1;
}
</style>
