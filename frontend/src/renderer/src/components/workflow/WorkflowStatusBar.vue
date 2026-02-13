<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkflowStore } from '@/stores/useWorkflowStore'
import { Loading, Check, Close, Timer, Connection } from '@element-plus/icons-vue'

const store = useWorkflowStore()
const { activeRunCount, completedRuns, activeRuns, totalRunCount } = storeToRefs(store)

const visible = ref(false)

// 清空已完成的记录
const clearCompleted = () => {
  store.clearCompleted()
}

// --- 拖拽逻辑 ---
const statusBarRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const position = ref<{ left: number; top: number } | null>(null)
let dragStartPos = { x: 0, y: 0 }
let dragStartElPos = { left: 0, top: 0 }

const handleMouseDown = (e: MouseEvent) => {
  if (!statusBarRef.value) return
  
  isDragging.value = false
  
  const rect = statusBarRef.value.getBoundingClientRect()
  dragStartElPos = { left: rect.left, top: rect.top }
  dragStartPos = { x: e.clientX, y: e.clientY }
  
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

const handleMouseMove = (e: MouseEvent) => {
  const dx = e.clientX - dragStartPos.x
  const dy = e.clientY - dragStartPos.y
  
  if (!isDragging.value && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
    isDragging.value = true
  }
  
  if (isDragging.value) {
    position.value = {
      left: dragStartElPos.left + dx,
      top: dragStartElPos.top + dy
    }
  }
}

const handleMouseUp = () => {
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
  
  if (isDragging.value) {
     setTimeout(() => { isDragging.value = false }, 0)
  }
}

const style = computed(() => {
  if (position.value) {
    return {
      left: `${position.value.left}px`,
      top: `${position.value.top}px`,
      bottom: 'auto',
      right: 'auto'
    }
  }
  return {}
})

const formatTime = (iso: string) => {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString()
}

const getStatusType = (status: string) => {
    switch(status) {
        case 'succeeded': return 'success'
        case 'failed': return 'danger'
        case 'running': return 'primary'
        case 'paused': return 'warning'
        case 'pending': return 'info'
        case 'timeout': return 'warning'
        case 'cancelled': return 'info'
        default: return 'info'
    }
}

const getStatusIcon = (status: string) => {
    switch(status) {
        case 'succeeded': return Check
        case 'failed': return Close
        case 'running': return Loading
        default: return Timer
    }
}

// 计算总节点数和已完成节点数
const getNodeStats = (run: any) => {
  // 根据进度百分比估算节点数
  if (run.progress !== undefined && run.progress > 0) {
    const total = 10 // 假设平均10个节点
    const completed = Math.floor((run.progress / 100) * total)
    return {
      completed,
      total
    }
  }
  return null
}

// 闪烁提醒逻辑
const isFlashing = ref(false)
let flashTimer: any = null
let lastCompletedCount = 0

watch(() => completedRuns.value.length, (newVal, oldVal) => {
  const previous = oldVal ?? 0
  console.log('[WorkflowStatusBar] completedRuns 变化:', oldVal, '->', newVal)
  if (newVal > previous && newVal > lastCompletedCount) {
    console.log('[WorkflowStatusBar] 触发闪烁动画')
    isFlashing.value = true
    lastCompletedCount = newVal
    if (flashTimer) clearTimeout(flashTimer)
    flashTimer = setTimeout(() => {
      isFlashing.value = false
      console.log('[WorkflowStatusBar] 闪烁动画结束')
    }, 2000)
  }
}, { immediate: true })

// 调试日志
watch(() => activeRuns.value, (runs) => {
  console.log('[WorkflowStatusBar] activeRuns 更新:', runs)
}, { deep: true })

watch(() => activeRunCount.value, (count) => {
  console.log('[WorkflowStatusBar] activeRunCount 更新:', count)
})
</script>

<template>
  <div 
    class="workflow-status-bar" 
    ref="statusBarRef" 
    :style="style"
    @mousedown="handleMouseDown"
  >
    <div @click.capture="(e) => isDragging && e.stopPropagation()">
      <el-popover
        v-model:visible="visible"
        placement="top-end"
        title="工作流执行状态"
        :width="360"
        trigger="click"
      >
        <template #reference>
          <div class="status-trigger" :class="{ 'is-active': activeRunCount > 0, 'is-dragging': isDragging, 'is-flashing': isFlashing }">
           <div class="trigger-icon">
              <el-icon v-if="activeRunCount > 0" class="is-loading"><Loading /></el-icon>
              <el-icon v-else><Connection /></el-icon>
              <span v-if="activeRunCount > 0" class="collapsed-badge">{{ activeRunCount }}</span>
           </div>
           
           <div class="status-content">
             <span class="status-text">
               <template v-if="activeRunCount > 0">
                  {{ activeRunCount }} 运行中 / {{ completedRuns.length }} 已完成
               </template>
               <template v-else>
                  工作流就绪
               </template>
             </span>
           </div>
        </div>
      </template>
      
      <div class="run-list">
        <template v-if="activeRuns.length > 0">
            <div class="list-header">运行中</div>
            <div v-for="run in activeRuns" :key="run.id" class="run-item running">
                <el-icon class="is-loading"><Loading /></el-icon>
                <div class="run-info">
                    <div class="run-name">{{ run.workflow_name }}</div>
                    <div class="run-meta">
                      <span>ID: {{ run.id }}</span>
                      <span v-if="run.created_at"> · {{ formatTime(run.created_at) }}</span>
                    </div>
                    
                    <!-- 当前节点 -->
                    <div v-if="run.current_node" class="run-node">
                        <el-icon><Connection /></el-icon>
                        <span>当前节点: {{ run.current_node }}</span>
                    </div>
                    
                    <!-- 进度条 -->
                    <div v-if="run.progress !== undefined" class="progress-wrapper">
                      <el-progress
                        :percentage="Math.round(run.progress)"
                        :show-text="true"
                        :stroke-width="6"
                        :format="(percent) => `${percent}%`"
                      />
                    </div>
                </div>
            </div>
        </template>
        
        <template v-if="completedRuns.length > 0">
            <div class="list-header">
                <span>已完成</span>
                <el-button
                  text
                  size="small"
                  @click="clearCompleted"
                >
                  清空
                </el-button>
            </div>
            <div v-for="run in completedRuns" :key="run.id" class="run-item">
                <el-tag size="small" :type="getStatusType(run.status)" effect="plain">
                    <el-icon><component :is="getStatusIcon(run.status)" /></el-icon>
                </el-tag>
                <div class="run-info">
                    <div class="run-name">{{ run.workflow_name }}</div>
                    <div class="run-meta">
                      <span>{{ formatTime(run.created_at || '') }}</span>
                      <span> · {{ run.status }}</span>
                    </div>
                    <div v-if="run.error" class="run-error" :title="run.error">{{ run.error }}</div>
                </div>
            </div>
        </template>
        
        <div v-if="activeRuns.length === 0 && completedRuns.length === 0" class="empty-tip">
            暂无运行记录
        </div>
      </div>
    </el-popover>
    </div>
  </div>
</template>

<style scoped>
.workflow-status-bar {
  position: fixed;
  bottom: 24px;
  left: 24px;
  z-index: 2000;
}

.status-trigger {
  display: flex;
  align-items: center;
  height: 40px; 
  padding: 0;
  
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  
  border-radius: 20px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  cursor: pointer;
  
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
  
  font-size: 13px;
  color: var(--el-text-color-primary);
  user-select: none;
  overflow: hidden;
  
  width: 40px; 
}

html.dark .status-trigger {
  background: rgba(30, 30, 30, 0.5);
  border-color: rgba(255, 255, 255, 0.1);
  color: var(--el-text-color-regular);
}

.status-trigger:hover {
  width: auto;
  min-width: 200px;
  padding-right: 16px;
  
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  border-color: var(--el-color-primary-light-5);
  opacity: 1;
  transform: translateY(-2px);
}

html.dark .status-trigger:hover {
  background: rgba(40, 40, 40, 0.9);
  border-color: var(--el-color-primary-dark-2);
}

.trigger-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
}

.status-trigger .el-icon {
  font-size: 18px; 
  margin: 0;
}

.collapsed-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background-color: var(--el-color-primary);
  color: white;
  border-radius: 10px;
  padding: 0 4px;
  font-size: 10px;
  line-height: 14px;
  min-width: 14px;
  text-align: center;
  border: 1px solid white;
}

html.dark .collapsed-badge {
    border-color: #333;
}

.status-content {
  white-space: nowrap;
  opacity: 0;
  max-width: 0;
  transition: all 0.3s ease;
  overflow: hidden;
}

.status-trigger:hover .status-content {
  opacity: 1;
  max-width: 300px;
  margin-left: 4px;
}

.status-trigger.is-active {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: rgba(var(--el-color-primary-rgb), 0.1);
}

.status-trigger.is-active:hover {
    background: var(--el-color-primary-light-9);
}

.status-trigger.is-flashing {
  animation: status-flash 2s ease-in-out infinite;
}

@keyframes status-flash {
  0% { box-shadow: 0 0 0 0 rgba(var(--el-color-success-rgb), 0.7); border-color: var(--el-color-success); }
  50% { box-shadow: 0 0 0 10px rgba(var(--el-color-success-rgb), 0); border-color: var(--el-color-success-light-3); }
  100% { box-shadow: 0 0 0 0 rgba(var(--el-color-success-rgb), 0); border-color: var(--el-color-success); }
}

.run-list {
  max-height: 400px;
  overflow-y: auto;
  scrollbar-width: thin;
  padding-right: 4px;
}

.run-list::-webkit-scrollbar {
  width: 6px;
}
.run-list::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 3px;
}
html.dark .run-list::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.2);
}

.list-header {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0 4px;
  padding-left: 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.run-node {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-color-primary);
  margin-top: 6px;
  font-weight: 500;
}

.progress-wrapper {
  margin-top: 8px;
}

.run-item {
  display: flex;
  align-items: flex-start;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 6px;
}

.run-item:hover {
  background-color: var(--el-fill-color-light);
}

.run-item.running {
    background-color: var(--el-color-primary-light-9);
}

.run-info {
  margin-left: 10px;
  flex-grow: 1;
  overflow: hidden;
}

.run-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.run-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.run-error {
  font-size: 12px;
  color: var(--el-color-danger);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.empty-tip {
    text-align: center;
    color: var(--el-text-color-secondary);
    padding: 20px;
}
</style>
