<template>
  <div class="node-library">
    <div class="library-header">
      <h3>节点库</h3>
      <el-input
        v-model="searchQuery"
        placeholder="搜索节点..."
        clearable
        :prefix-icon="Search"
        size="small"
      />
    </div>

    <div class="library-content" v-loading="workflowStore.isLoading">
      <el-scrollbar>
        <el-collapse v-model="activeCategories" accordion>
          <el-collapse-item 
            v-for="category in workflowStore.categories" 
            :key="category" 
            :name="category"
          >
            <template #title>
              <div class="category-title">
                <el-icon>
                  <component :is="getCategoryIcon(category)" />
                </el-icon>
                <span>{{ getCategoryLabel(category) }}</span>
                <el-tag size="small" type="info">{{ getFilteredNodes(category).length }}</el-tag>
              </div>
            </template>
            <div class="node-list">
              <div
                v-for="node in getFilteredNodes(category)"
                :key="node.type"
                class="node-item"
                draggable="true"
                @dragstart="handleDragStart($event, node)"
                @click="handleNodeClick(node)"
              >
                <el-icon class="node-icon">
                  <component :is="getNodeIcon(node.type)" />
                </el-icon>
                <div class="node-info">
                  <div class="node-name">{{ node.label }}</div>
                  <div class="node-desc">{{ node.description || '无描述' }}</div>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-scrollbar>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { 
  Search, 
  Operation, 
  Collection, 
  DataAnalysis, 
  MagicStick,
  Menu,
  Box,
  Lightning
} from '@element-plus/icons-vue'
import { useWorkflowStore } from '@/stores/useWorkflowStore'
import type { WorkflowNodeType } from '@/api/workflows'

const workflowStore = useWorkflowStore()
const searchQuery = ref('')
const activeCategories = ref(['trigger', 'logic'])

const emit = defineEmits<{
  addNode: [nodeType: string, position?: { x: number; y: number }]
}>()

// 初始化加载
onMounted(() => {
  workflowStore.fetchNodeTypes()
})

// 过滤节点
const getFilteredNodes = (category: string) => {
  const nodes = workflowStore.getNodesByCategory(category)
  if (!searchQuery.value) return nodes
  
  const query = searchQuery.value.toLowerCase()
  return nodes.filter(n => 
    n.label.toLowerCase().includes(query) ||
    n.description.toLowerCase().includes(query) ||
    n.type.toLowerCase().includes(query)
  )
}

// 分类图标映射
const getCategoryIcon = (category: string) => {
  const map: Record<string, any> = {
    trigger: Lightning,
    logic: Operation,
    card: Collection,
    data: DataAnalysis,
    ai: MagicStick
  }
  return map[category] || Menu
}

// 分类名称映射
const getCategoryLabel = (category: string) => {
  const map: Record<string, string> = {
    trigger: '触发器',
    logic: '逻辑控制',
    card: '卡片操作',
    data: '数据处理',
    ai: 'AI 生成'
  }
  return map[category] || category.charAt(0).toUpperCase() + category.slice(1)
}

// 节点图标映射（简化处理，后续可从后端获取 icon 字段）
const getNodeIcon = (type: string) => {
  // 根据类型前缀判断
  if (type.startsWith('Trigger.')) return Lightning
  if (type.startsWith('Card.')) return Collection
  if (type.startsWith('Logic.')) return Operation
  if (type.startsWith('Data.')) return DataAnalysis
  if (type.startsWith('AI.')) return MagicStick
  return Box
}



// 拖拽开始
const handleDragStart = (event: DragEvent, node: WorkflowNodeType) => {
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('application/vueflow', JSON.stringify(node))
  }
}

// 点击节点
const handleNodeClick = (node: WorkflowNodeType) => {
  // 点击添加到画布中心
  emit('addNode', node.type)
}
</script>

<style scoped lang="scss">
.node-library {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  border-right: 1px solid var(--el-border-color-light);
}

html.dark .node-library {
  background: rgba(45, 45, 45, 0.9);
}

.library-header {
  padding: 20px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);

  h3 {
    margin: 0 0 16px 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    display: flex;
    align-items: center;
    gap: 8px;
    
    &::before {
      content: '';
      display: block;
      width: 4px;
      height: 16px;
      background: var(--el-color-primary);
      border-radius: 2px;
    }
  }
}

.library-content {
  flex: 1;
  overflow: hidden;

  :deep(.el-collapse) {
    border: none;
    --el-collapse-header-bg-color: transparent;
    --el-collapse-content-bg-color: transparent;
    --el-collapse-border-color: transparent;
  }

  :deep(.el-collapse-item__header) {
    height: 48px;
    line-height: 48px;
    padding: 0 16px;
    border-bottom: 1px solid transparent;
    font-weight: 600;
    color: var(--text-secondary);
    transition: all 0.2s;

    &:hover {
      color: var(--el-color-primary);
      background: rgba(0, 0, 0, 0.02);
    }
    
    &.is-active {
      color: var(--el-color-primary);
      background: rgba(99, 102, 241, 0.05);
    }
  }

  :deep(.el-collapse-item__content) {
    padding: 0;
  }
}

.category-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  
  .el-icon {
    font-size: 16px;
  }

  span {
    flex: 1;
  }

  .el-tag {
    margin-left: auto;
    border: none;
    background: var(--el-fill-color-light);
    color: var(--el-text-color-secondary);
  }
}

.node-list {
  padding: 12px;
}

.node-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  margin-bottom: 8px;
  border-radius: var(--border-radius-sm);
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  cursor: grab;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--el-color-primary);
    opacity: 0;
    transition: opacity 0.2s;
  }

  &:hover {
    border-color: var(--el-color-primary);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
    
    &::before {
      opacity: 1;
    }
    
    .node-icon {
      transform: scale(1.1);
      background: var(--el-color-primary);
      color: #fff;
    }
  }

  &:active {
    cursor: grabbing;
    transform: scale(0.98);
  }

  .node-icon {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: var(--el-fill-color-light);
    color: var(--el-color-primary);
    font-size: 18px;
    flex-shrink: 0;
    transition: all 0.2s;
  }

  .node-info {
    flex: 1;
    min-width: 0;
  }

  .node-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-bottom: 4px;
    line-height: 1.4;
  }

  .node-desc {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}
</style>
