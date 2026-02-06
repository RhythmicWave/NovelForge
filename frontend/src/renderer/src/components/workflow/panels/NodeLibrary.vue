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

    <div class="library-content" v-loading="loading">
      <el-scrollbar>
        <el-collapse v-model="activeCategories">
          <el-collapse-item
            v-for="(nodes, category) in filteredNodesByCategory"
            :key="category"
            :name="category"
          >
            <template #title>
              <div class="category-title">
                <el-icon>
                  <component :is="getCategoryIcon(category)" />
                </el-icon>
                <span>{{ getCategoryLabel(category) }}</span>
                <el-tag size="small" type="info">{{ nodes.length }}</el-tag>
              </div>
            </template>
            <div class="node-list">
              <div
                v-for="node in nodes"
                :key="node.type"
                class="node-item"
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

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Search,
  Operation,
  Collection,
  DataAnalysis,
  MagicStick,
  Menu,
  Box,
  Lightning,
  Document
} from '@element-plus/icons-vue'
import request from '@/api/request'

const emit = defineEmits(['add-node'])

const searchQuery = ref('')
const activeCategories = ref(['logic', 'novel', 'card', 'example'])
const nodeTypes = ref([])
const loading = ref(false)

// 按分类组织节点
const nodesByCategory = computed(() => {
  const grouped = {}
  nodeTypes.value.forEach(node => {
    if (!grouped[node.category]) {
      grouped[node.category] = []
    }
    grouped[node.category].push(node)
  })
  return grouped
})

// 过滤后的节点
const filteredNodesByCategory = computed(() => {
  if (!searchQuery.value) return nodesByCategory.value

  const query = searchQuery.value.toLowerCase()
  const filtered = {}

  Object.entries(nodesByCategory.value).forEach(([category, nodes]) => {
    const matchedNodes = nodes.filter(n =>
      n.label.toLowerCase().includes(query) ||
      n.description.toLowerCase().includes(query) ||
      n.type.toLowerCase().includes(query)
    )
    if (matchedNodes.length > 0) {
      filtered[category] = matchedNodes
    }
  })

  return filtered
})

// 分类图标映射
const getCategoryIcon = (category) => {
  const map = {
    'trigger': Lightning,
    'logic': Operation,
    'card': Collection,
    'data': DataAnalysis,
    'ai': MagicStick,
    'novel': Document,
    'prompt': Document,
    'example': Box,
    'context': Menu
  }
  return map[category] || Menu
}

// 分类名称映射
const getCategoryLabel = (category) => {
  const map = {
    'trigger': '触发器',
    'logic': '逻辑控制',
    'card': '卡片操作',
    'data': '数据处理',
    'ai': 'AI 生成',
    'novel': '小说处理',
    'prompt': '提示词',
    'example': '示例节点',
    'context': '上下文'
  }
  return map[category] || category
}

// 节点图标映射
const getNodeIcon = (type) => {
  if (type.startsWith('Trigger.')) return Lightning
  if (type.startsWith('Card.')) return Collection
  if (type.startsWith('Logic.')) return Operation
  if (type.startsWith('Data.')) return DataAnalysis
  if (type.startsWith('AI.')) return MagicStick
  if (type.startsWith('Novel.')) return Document
  if (type.startsWith('Prompt.')) return Document
  return Box
}

// 点击节点
const handleNodeClick = (node) => {
  emit('add-node', node.type)
}

// 加载节点类型
async function loadNodeTypes() {
  loading.value = true
  try {
    const response = await request.get('/nodes/types', undefined, '/api', { showLoading: false })
    nodeTypes.value = response.node_types || []
  } catch (error) {
    console.error('加载节点类型失败:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadNodeTypes()
})
</script>

<style scoped>
.node-library {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color);
}

.library-header {
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}

.library-header h3 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.library-header h3::before {
  content: '';
  display: block;
  width: 3px;
  height: 14px;
  background: var(--el-color-primary);
  border-radius: 2px;
}

.library-content {
  flex: 1;
  overflow: hidden;
}

.library-content :deep(.el-collapse) {
  border: none;
}

.library-content :deep(.el-collapse-item__header) {
  height: 44px;
  line-height: 44px;
  padding: 0 16px;
  border-bottom: none;
  font-weight: 600;
  color: var(--el-text-color-regular);
  background: transparent;
}

.library-content :deep(.el-collapse-item__header:hover) {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.library-content :deep(.el-collapse-item__content) {
  padding: 0;
}

.category-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.category-title .el-icon {
  font-size: 16px;
}

.category-title span {
  flex: 1;
}

.category-title .el-tag {
  margin-left: auto;
  border: none;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}

.node-list {
  padding: 8px 12px;
}

.node-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  cursor: pointer;
  transition: all 0.2s;
}

.node-item:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px var(--el-box-shadow-light);
}

.node-item:hover .node-icon {
  transform: scale(1.1);
  background: var(--el-color-primary);
  color: white;
}

.node-item:active {
  transform: scale(0.98);
}

.node-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--el-fill-color);
  color: var(--el-color-primary);
  font-size: 16px;
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
  margin-bottom: 3px;
  line-height: 1.4;
}

.node-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
