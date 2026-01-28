<template>
  <div class="display-node" :class="{ expanded: isExpanded }">
    <Handle type="target" :position="Position.Left" id="input" />
    
    <div class="node-header" @click="toggleExpand">
      <el-icon class="node-icon"><Monitor /></el-icon>
      <span class="node-label">{{ data.label || '显示输出' }}</span>
      <el-icon class="expand-icon">
        <component :is="isExpanded ? 'ArrowDown' : 'ArrowRight'" />
      </el-icon>
    </div>
    
    <div v-if="isExpanded" class="node-content">
      <div v-if="displayContent" class="content-display">
        <div class="content-title">{{ displayContent.title }}</div>
        <div class="content-body">
          <XMarkdown 
            :markdown="displayContent.content" 
            :default-theme-mode="'light'"
            class="content-markdown"
          />
        </div>
      </div>
      <div v-else class="empty-content">
        <el-empty description="暂无输出数据" :image-size="60" />
      </div>
    </div>
    
    <Handle type="source" :position="Position.Right" id="output" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { Monitor, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import { XMarkdown } from 'vue-element-plus-x'

const props = defineProps<{
  id: string
  data: any
}>()

// 从父组件注入运行状态
const runStatus = inject<any>('runStatus', null)

const isExpanded = ref(true)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

// 从运行状态中获取显示内容
const displayContent = computed(() => {
  if (!runStatus || !runStatus.value) {
    return null
  }
  
  const nodes = runStatus.value.nodes
  if (!nodes || !Array.isArray(nodes)) {
    return null
  }
  
  // 查找当前节点的状态
  const nodeState = nodes.find((n: any) => n.node_id === props.id)
  if (!nodeState) {
    return null
  }
  
  // 从 outputs_json 中获取 display 字段
  let outputs = nodeState.outputs_json
  if (typeof outputs === 'string') {
    try {
      outputs = JSON.parse(outputs)
    } catch (e) {
      return null
    }
  }
  
  if (outputs && outputs.display) {
    return outputs.display
  }
  
  return null
})
</script>

<style scoped lang="scss">
.display-node {
  background: white;
  border: 2px solid #909399;
  border-radius: 8px;
  min-width: 200px;
  max-width: 500px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s;
  
  &.expanded {
    min-width: 300px;
  }
  
  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
}

.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  cursor: pointer;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 6px 6px 0 0;
  color: white;
  user-select: none;
  
  &:hover {
    opacity: 0.9;
  }
  
  .node-icon {
    font-size: 18px;
  }
  
  .node-label {
    flex: 1;
    font-weight: 600;
    font-size: 14px;
  }
  
  .expand-icon {
    font-size: 14px;
    transition: transform 0.3s;
  }
}

.node-content {
  padding: 12px;
  max-height: 400px;
  overflow: auto;
}

.content-display {
  .content-title {
    font-size: 12px;
    font-weight: 600;
    color: #606266;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #e4e7ed;
  }
  
  .content-body {
    background: #f5f7fa;
    border: 1px solid #e4e7ed;
    border-radius: 4px;
    padding: 8px;
    
    &.content-json {
      .json-content {
        margin: 0;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 12px;
        line-height: 1.5;
        color: #2c3e50;
        white-space: pre-wrap;
        word-wrap: break-word;
      }
    }
    
    &.content-text {
      .text-content {
        font-size: 13px;
        line-height: 1.6;
        color: #333;
        white-space: pre-wrap;
        word-wrap: break-word;
      }
    }
  }
}

.empty-content {
  padding: 20px 0;
  text-align: center;
  
  :deep(.el-empty__description) {
    font-size: 12px;
    color: #999;
  }
}
</style>
