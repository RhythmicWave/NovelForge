<script setup lang="ts">
import { ref, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkflowStatusStore } from '@/stores/useWorkflowStatusStore'
import { Loading, Check, Close, Timer, Connection } from '@element-plus/icons-vue'

const store = useWorkflowStatusStore()
const { activeCount, completedRuns, activeRuns, totalCount } = storeToRefs(store)

const visible = ref(false)

// --- 拖拽逻辑 ---
const statusBarRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const position = ref<{ left: number; top: number } | null>(null)
let dragStartPos = { x: 0, y: 0 }
let dragStartElPos = { left: 0, top: 0 }

const handleMouseDown = (e: MouseEvent) => {
  // 防止在可能需要交互的子元素上触发拖拽（虽然 popover trigger 包裹了所有）
  // 为了更好的体验，允许在胶囊体的任何位置拖拽
  
  if (!statusBarRef.value) return
  
  isDragging.value = false // 移动时才会设为 true
  
  const rect = statusBarRef.value.getBoundingClientRect()
  dragStartElPos = { left: rect.left, top: rect.top }
  dragStartPos = { x: e.clientX, y: e.clientY }
  
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

const handleMouseMove = (e: MouseEvent) => {
  const dx = e.clientX - dragStartPos.x
  const dy = e.clientY - dragStartPos.y
  
  // 阈值检测：区分点击和拖拽
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
  
  // 如果刚才在拖拽，防止点击事件立即触发 popover
  // popover 的 trigger="click" 通常通过点击事件处理
  // 我们可以在捕获阶段拦截，或者因为我们标记了 isDragging，
  // 从而阻止冒泡。
  if (isDragging.value) {
     setTimeout(() => { isDragging.value = false }, 0)
  }
}

// 计算固定定位的样式
const style = computed(() => {
  if (position.value) {
    return {
      left: `${position.value.left}px`,
      top: `${position.value.top}px`,
      bottom: 'auto',
      right: 'auto'
    }
  }
  return {} // 使用 CSS 默认值
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

// --- 闪烁提醒逻辑 ---
import { watch } from 'vue'
const isFlashing = ref(false)
let flashTimer: any = null

watch(() => completedRuns.value.length, (newVal, oldVal) => {
  if (newVal > oldVal) {
    // 只有当完成数量增加时闪烁
    isFlashing.value = true
    if (flashTimer) clearTimeout(flashTimer)
    flashTimer = setTimeout(() => {
      isFlashing.value = false
    }, 2000) // 闪烁持续 2 秒
  }
})
</script>

<template>
  <div 
    class="workflow-status-bar" 
    ref="statusBarRef" 
    :style="style"
    @mousedown="handleMouseDown"
  >
    <!-- 捕获点击事件，如果是拖拽操作则阻止 Popover 切换 -->
    <div @click.capture="(e) => isDragging && e.stopPropagation()">
      <el-popover
        v-model:visible="visible"
        placement="top-end"
        title="工作流运行记录 (本次会话)"
        :width="320"
        trigger="click"
      >
        <template #reference>
          <div class="status-trigger" :class="{ 'is-active': activeCount > 0, 'is-dragging': isDragging, 'is-flashing': isFlashing }">
           <div class="trigger-icon">
              <el-icon v-if="activeCount > 0" class="is-loading"><Loading /></el-icon>
              <el-icon v-else><Connection /></el-icon>
              <!-- 折叠时显示运行中的数量角标 -->
              <span v-if="activeCount > 0" class="collapsed-badge">{{ activeCount }}</span>
           </div>
           
           <div class="status-content">
             <span class="status-text">
               <template v-if="totalCount > 0">
                  工作流: {{ activeCount }} 运行中 / {{ completedRuns.length }} 已完成
               </template>
               <template v-else>
                  工作流系统就绪
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
                    <div class="run-meta">ID: {{ run.id }} · {{ formatTime(run.created_at || '') }}</div>
                </div>
            </div>
        </template>
        
        <template v-if="completedRuns.length > 0">
            <div class="list-header">已完成</div>
            <div v-for="run in completedRuns" :key="run.id" class="run-item">
                <el-tag size="small" :type="getStatusType(run.status)" effect="plain" circle>
                    <el-icon><component :is="getStatusIcon(run.status)" /></el-icon>
                </el-tag>
                <div class="run-info">
                    <div class="run-name">{{ run.workflow_name }}</div>
                    <div class="run-meta">{{ formatTime(run.created_at || '') }} · {{ run.status }}</div>
                    <div v-if="run.error" class="run-error" :title="run.error">{{ run.error }}</div>
                </div>
            </div>
        </template>
        
        <div v-if="activeRuns.length === 0 && completedRuns.length === 0" class="empty-tip">
            暂无记录
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
  left: 24px; /* 默认左侧 */
  z-index: 2000;
}

.status-trigger {
  display: flex;
  align-items: center;
  /* 固定高度 + 可变宽度 */
  height: 40px; 
  padding: 0; /* Padding 由子元素或 Flex 对齐处理 */
  
  /* 毛玻璃基础效果 */
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  
  border-radius: 20px; /* 初始完全圆形 (如果宽度很小) */
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  cursor: pointer;
  
  /* 宽度/圆角/样式的过渡动画 */
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
  
  font-size: 13px;
  color: var(--el-text-color-primary);
  user-select: none;
  overflow: hidden; /* 折叠时隐藏文本 */
  
  /* 允许收缩到仅图标大小 */
  width: 40px; 
}

/* 深色模式支持 */
html.dark .status-trigger {
  background: rgba(30, 30, 30, 0.5);
  border-color: rgba(255, 255, 255, 0.1);
  color: var(--el-text-color-regular);
}

/* 悬停状态: 展开 */
.status-trigger:hover {
  width: auto; /* 允许自动宽度展开 */
  min-width: 200px; /* 最小展开宽度 */
  padding-right: 16px; /* 为文本添加右侧内边距 */
  
  /* 样式增强 */
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  border-color: var(--el-color-primary-light-5);
  opacity: 1;
  transform: translateY(-2px);
}

/* 激活状态 (运行中) - 保持紧凑但显示指示器 */
/* For now, keep compact but show indicator */

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
  max-height: 280px; /* Reduced from 400px to avoid looking "infinite" */
  overflow-y: auto;
  scrollbar-width: thin; /* Firefox */
  padding-right: 4px; /* Space for scrollbar */
}

/* Webkit 滚动条样式 */
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
}

.run-item {
  display: flex;
  align-items: flex-start;
  padding: 8px;
  border-radius: 6px;
  margin-bottom: 4px;
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
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.run-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.run-error {
  font-size: 12px;
  color: var(--el-color-danger);
  margin-top: 2px;
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
