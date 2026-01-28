<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="node-count">
        节点: <strong>{{ nodes.length }}</strong>
      </span>
      <span class="edge-count">
        连接: <strong>{{ edgeCount }}</strong>
      </span>
    </div>

    <div v-if="runStatus" class="status-center">
      <div class="status-item" v-for="nodeStatus in nodeStatusList" :key="nodeStatus.id">
        <el-icon :class="['status-icon', `status-${nodeStatus.status}`]">
          <component :is="getStatusIcon(nodeStatus.status)" />
        </el-icon>
        <span class="status-label">{{ nodeStatus.label }}</span>
        <span v-if="nodeStatus.duration" class="status-duration">({{ nodeStatus.duration }})</span>
      </div>
    </div>

    <div class="status-right">
      <span class="status-info">
        {{ statusMessage }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { 
  VideoPlay, 
  Loading, 
  CircleCheck, 
  CircleClose, 
  Clock 
} from '@element-plus/icons-vue'

const props = defineProps<{
  nodes: any[]
  runStatus: any
}>()

// 边数量（从节点推算）
const edgeCount = computed(() => {
  // 简化版本，实际应该从edges数组获取
  return 0
})

// 节点状态列表
const nodeStatusList = computed(() => {
  if (!props.runStatus || !props.runStatus.nodeStatus) return []
  
  return Object.entries(props.runStatus.nodeStatus).map(([id, status]: [string, any]) => {
    const node = props.nodes.find(n => n.id === id)
    return {
      id,
      label: node?.data?.label || id,
      status: status.status,
      duration: status.duration ? `${status.duration}s` : null
    }
  })
})

// 状态消息
const statusMessage = computed(() => {
  if (!props.runStatus) return '就绪'
  
  const { status } = props.runStatus
  if (status === 'running') return '运行中...'
  if (status === 'completed') return '运行完成'
  if (status === 'failed') return '运行失败'
  if (status === 'cancelled') return '已取消'
  
  return '就绪'
})

// 获取状态图标
const getStatusIcon = (status: string) => {
  switch (status) {
    case 'idle':
      return Clock
    case 'running':
      return Loading
    case 'completed':
      return CircleCheck
    case 'failed':
      return CircleClose
    default:
      return VideoPlay
  }
}
</script>

<style scoped lang="scss">
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  height: 100%;
  padding: 0 20px;
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.status-left {
  display: flex;
  gap: 16px;

  .node-count,
  .edge-count {
    strong {
      color: var(--el-color-primary);
      font-weight: 600;
    }
  }
}

.status-center {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }

  .status-item {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--el-fill-color-light);
    white-space: nowrap;

    .status-icon {
      font-size: 14px;

      &.status-idle {
        color: var(--el-text-color-secondary);
      }

      &.status-running {
        color: var(--el-color-warning);
        animation: spin 1s linear infinite;
      }

      &.status-completed {
        color: var(--el-color-success);
      }

      &.status-failed {
        color: var(--el-color-danger);
      }
    }

    .status-label {
      font-size: 11px;
      color: var(--el-text-color-primary);
    }

    .status-duration {
      font-size: 10px;
      color: var(--el-text-color-secondary);
    }
  }
}

.status-right {
  .status-info {
    color: var(--el-text-color-secondary);
    font-weight: 500;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
