<template>
  <teleport to="body">
    <div 
      v-if="visible" 
      class="node-quick-menu"
      :style="{ left: position.x + 'px', top: position.y + 'px' }"
      @click.stop
    >
      <div class="menu-header">选择节点</div>
      <div class="menu-list">
        <div 
          v-for="node in nodeTypes" 
          :key="node.type"
          class="menu-item"
          @click="handleSelect(node.type)"
        >
          <el-icon class="menu-icon" :style="{ color: node.color }">
            <component :is="node.icon" />
          </el-icon>
          <span class="menu-label">{{ node.label }}</span>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { 
  VideoPlay, 
  CloseBold, 
  CircleCheck, 
  Clock, 
  Edit, 
  View,
  Document,
  Plus,
  Delete,
  Search,
  Menu,
  Collection,
  Filter,
  Histogram,
  PieChart,
  MagicStick
} from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  position: { x: number; y: number }
}>()

const emit = defineEmits<{
  'select': [nodeType: string]
  'close': []
}>()

// 节点类型列表
const nodeTypes = [
  { type: 'Logic.Condition', label: '条件分支', icon: CircleCheck, color: '#f093fb' },
  { type: 'Logic.Loop', label: '循环', icon: 'Refresh', color: '#667eea' },
  { type: 'Logic.SetVariable', label: '设置变量', icon: Edit, color: '#667eea' },
  { type: 'Logic.GetVariable', label: '获取变量', icon: View, color: '#667eea' },
  { type: 'Logic.Delay', label: '延迟', icon: Clock, color: '#667eea' },
  { type: 'Card.Read', label: '读取卡片', icon: Document, color: '#f5af19' },
  { type: 'Card.Create', label: '创建卡片', icon: Plus, color: '#f5af19' },
  { type: 'Card.Update', label: '更新卡片', icon: Edit, color: '#f5af19' },
  { type: 'Data.Transform', label: '数据转换', icon: Menu, color: '#43e97b' },
  { type: 'Data.Filter', label: '数据过滤', icon: Filter, color: '#43e97b' },
  { type: 'Data.Log', label: '日志输出', icon: Document, color: '#43e97b' },
  { type: 'AI.Generate', label: 'AI生成', icon: MagicStick, color: '#fa709a' },
  { type: 'Logic.End', label: '结束', icon: CloseBold, color: '#667eea' },
]

const handleSelect = (nodeType: string) => {
  emit('select', nodeType)
  emit('close')
}

// 点击外部关闭
watch(() => props.visible, (newVal) => {
  if (newVal) {
    setTimeout(() => {
      document.addEventListener('click', handleClickOutside)
    }, 100)
  } else {
    document.removeEventListener('click', handleClickOutside)
  }
})

const handleClickOutside = () => {
  emit('close')
}
</script>

<style scoped lang="scss">
.node-quick-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  min-width: 200px;
  max-width: 250px;
  padding: 8px 0;
  animation: menuFadeIn 0.15s ease-out;
}

@keyframes menuFadeIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(-5px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.menu-header {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 4px;
}

.menu-list {
  max-height: 400px;
  overflow-y: auto;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #f5f7fa;
  }

  &:active {
    background: #e8edf3;
  }
}

.menu-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.menu-label {
  font-size: 14px;
  color: #303133;
  flex: 1;
}
</style>
