<template>
  <div
    v-if="props.visible"
    ref="panelRef"
    class="generation-panel-float"
    :class="{ minimized: isMinimized }"
    :style="panelStyle"
  >
    <!-- 顶部标题栏（可拖动）-->
    <div
      class="panel-header"
      @mousedown="handleDragStart"
    >
      <div class="header-title">
        <el-icon class="title-icon"><MagicStick /></el-icon>
        <span>AI 生成助手</span>
      </div>
      <div class="header-actions">
        <el-button
          :icon="isMinimized ? ArrowUp : ArrowDown"
          circle
          size="small"
          @click.stop="toggleMinimize"
        />
        <el-button
          :icon="Close"
          circle
          size="small"
          @click.stop="handleClose"
        />
      </div>
    </div>

    <!-- 消息列表（最小化时隐藏）-->
    <div v-show="!isMinimized" ref="messagesContainer" class="messages-container">
      <div
        v-for="(msg, index) in messages"
        :key="index"
        :class="['message-item', `message-${msg.type}`]"
      >
        <!-- 思考消息 -->
        <div v-if="msg.type === 'thinking'" class="message-thinking">
          <el-icon class="message-icon"><ChatDotRound /></el-icon>
          <span class="message-text">{{ msg.content }}</span>
        </div>

        <!-- 指令执行消息 -->
        <div v-else-if="msg.type === 'action'" class="message-action">
          <el-icon class="message-icon success"><Check /></el-icon>
          <span class="message-text">{{ msg.content }}</span>
        </div>

        <!-- 用户消息 -->
        <div v-else-if="msg.type === 'user'" class="message-user">
          <el-icon class="message-icon"><User /></el-icon>
          <span class="message-text">{{ msg.content }}</span>
        </div>

        <!-- 警告消息 -->
        <div v-else-if="msg.type === 'warning'" class="message-warning">
          <el-icon class="message-icon"><Warning /></el-icon>
          <span class="message-text">{{ msg.content }}</span>
        </div>

        <!-- 错误消息 -->
        <div v-else-if="msg.type === 'error'" class="message-error">
          <el-icon class="message-icon"><CircleClose /></el-icon>
          <span class="message-text">{{ msg.content }}</span>
        </div>

        <!-- 系统消息 -->
        <div v-else-if="msg.type === 'system'" class="message-system">
          <el-icon class="message-icon"><InfoFilled /></el-icon>
          <span class="message-text">{{ msg.content }}</span>
        </div>
      </div>

      <!-- 生成中指示器 -->
      <div v-if="isGenerating && !isPaused" class="generating-indicator">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在生成...</span>
      </div>
    </div>

    <!-- 底部控制区（最小化时隐藏）-->
    <div v-show="!isMinimized" class="panel-footer">
      <!-- 进度信息 -->
      <div v-if="completedFields > 0" class="progress-info">
        <span>已生成 {{ completedFields }} 个字段</span>
      </div>

      <!-- 用户输入框 -->
      <div class="input-area">
        <el-input
          v-model="userInput"
          :placeholder="isPaused ? '输入您的回复...' : '可以随时输入指导意见...'"
          :disabled="!isGenerating && !isPaused"
          @keyup.enter="handleSendMessage"
        >
          <template #append>
            <el-button
              :icon="Promotion"
              :disabled="!userInput.trim() || (!isGenerating && !isPaused)"
              @click="handleSendMessage"
            >
              发送
            </el-button>
          </template>
        </el-input>
      </div>

      <!-- 控制按钮 -->
      <div class="control-buttons">
        <el-button
          v-if="isGenerating && !isPaused"
          :icon="VideoPause"
          size="small"
          @click="handlePause"
        >
          暂停
        </el-button>

        <el-button
          v-if="isPaused"
          :icon="VideoPlay"
          type="primary"
          size="small"
          @click="handleContinue"
        >
          继续
        </el-button>

        <el-button
          v-if="isGenerating || isPaused"
          :icon="Close"
          size="small"
          @click="handleStop"
        >
          停止
        </el-button>

        <el-button
          v-if="!isGenerating && !isPaused"
          :icon="RefreshLeft"
          size="small"
          @click="handleRestart"
        >
          重新开始
        </el-button>
      </div>
    </div>

    <!-- 调整大小手柄 -->
    <div
      v-show="!isMinimized"
      class="resize-handle"
      @mousedown="handleResizeStart"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import {
  MagicStick,
  Close,
  ChatDotRound,
  Check,
  User,
  Warning,
  CircleClose,
  InfoFilled,
  Loading,
  VideoPause,
  VideoPlay,
  RefreshLeft,
  CircleCloseFilled,
  Promotion,
  ArrowUp,
  ArrowDown
} from '@element-plus/icons-vue'
import type { GenerationMessage } from '@renderer/types/instruction'

// ==================== Props & Emits ====================

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  pause: []
  continue: [userMessage: string]
  stop: []
  restart: []
}>()

// ==================== 状态管理 ====================

const isGenerating = ref(false)
const isPaused = ref(false)
const messages = ref<GenerationMessage[]>([])
const completedFields = ref(0)
const userInput = ref('')
const messagesContainer = ref<HTMLElement>()
const panelRef = ref<HTMLElement>()

// 悬浮窗状态
const isMinimized = ref(false)
const position = ref({ x: 0, y: 0 })
const size = ref({ width: 450, height: 600 })
const isDragging = ref(false)
const isResizing = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

// 计算面板样式
const panelStyle = computed(() => ({
  left: `${position.value.x}px`,
  top: `${position.value.y}px`,
  width: `${size.value.width}px`,
  height: isMinimized.value ? '48px' : `${size.value.height}px`
}))

// ==================== 悬浮窗控制方法 ====================

/**
 * 初始化默认位置（右下角）
 */
function initPosition() {
  const windowWidth = window.innerWidth
  const windowHeight = window.innerHeight
  const padding = 20
  
  position.value = {
    x: windowWidth - size.value.width - padding,
    y: windowHeight - size.value.height - padding
  }
}

/**
 * 切换最小化状态
 */
function toggleMinimize() {
  isMinimized.value = !isMinimized.value
}

/**
 * 开始拖动
 */
function handleDragStart(e: MouseEvent) {
  isDragging.value = true
  dragOffset.value = {
    x: e.clientX - position.value.x,
    y: e.clientY - position.value.y
  }
  
  document.addEventListener('mousemove', handleDragMove)
  document.addEventListener('mouseup', handleDragEnd)
  
  // 防止文本选择
  e.preventDefault()
}

/**
 * 拖动中
 */
function handleDragMove(e: MouseEvent) {
  if (!isDragging.value) return
  
  position.value = {
    x: e.clientX - dragOffset.value.x,
    y: e.clientY - dragOffset.value.y
  }
}

/**
 * 结束拖动
 */
function handleDragEnd() {
  isDragging.value = false
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
}

/**
 * 开始调整大小
 */
function handleResizeStart(e: MouseEvent) {
  isResizing.value = true
  
  const startX = e.clientX
  const startY = e.clientY
  const startWidth = size.value.width
  const startHeight = size.value.height
  
  const handleResizeMove = (moveEvent: MouseEvent) => {
    const deltaX = moveEvent.clientX - startX
    const deltaY = moveEvent.clientY - startY
    
    size.value = {
      width: Math.max(350, startWidth + deltaX),
      height: Math.max(400, startHeight + deltaY)
    }
  }
  
  const handleResizeEnd = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', handleResizeMove)
    document.removeEventListener('mouseup', handleResizeEnd)
  }
  
  document.addEventListener('mousemove', handleResizeMove)
  document.addEventListener('mouseup', handleResizeEnd)
  
  e.preventDefault()
}

// ==================== 生命周期 ====================

onMounted(() => {
  initPosition()
})

onUnmounted(() => {
  // 清理事件监听
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
})

// ==================== 方法 ====================

/**
 * 添加消息
 */
function addMessage(type: GenerationMessage['type'], content: string) {
  // 对于thinking类型的消息，尝试合并到上一条thinking消息
  if (type === 'thinking' && messages.value.length > 0) {
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage.type === 'thinking') {
      // 合并到上一条thinking消息
      lastMessage.content += content
      lastMessage.timestamp = Date.now()
      
      // 自动滚动到底部
      nextTick(() => {
        scrollToBottom()
      })
      return
    }
  }
  
  // 其他情况，新增消息
  messages.value.push({
    type,
    content,
    timestamp: Date.now()
  })

  // 自动滚动到底部
  nextTick(() => {
    scrollToBottom()
  })
}

/**
 * 滚动到底部
 */
function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

/**
 * 处理关闭
 */
function handleClose() {
  emit('close')
}

/**
 * 处理暂停
 */
function handlePause() {
  isPaused.value = true
  isGenerating.value = false
  addMessage('system', '已暂停生成，您可以输入指导意见后继续')
  emit('pause')
}

/**
 * 处理继续
 */
function handleContinue() {
  const message = userInput.value.trim() || '请继续生成'
  
  // 只有用户实际输入了内容才显示消息
  if (userInput.value.trim()) {
    addMessage('user', message)
  }
  
  userInput.value = ''

  isPaused.value = false
  isGenerating.value = true

  emit('continue', message)
}

/**
 * 处理停止
 */
function handleStop() {
  isGenerating.value = false
  isPaused.value = false
  addMessage('system', '生成已停止')
  emit('stop')
}

/**
 * 处理重新开始
 */
function handleRestart() {
  messages.value = []
  completedFields.value = 0
  userInput.value = ''
  emit('restart')
}

/**
 * 处理发送消息
 */
function handleSendMessage() {
  if (isPaused.value) {
    handleContinue()
  } else if (isGenerating.value && userInput.value.trim()) {
    // 生成过程中也可以发送消息（作为额外指导）
    const message = userInput.value.trim()
    addMessage('user', message)
    userInput.value = ''
  }
}

/**
 * 开始生成
 */
function startGeneration() {
  isGenerating.value = true
  isPaused.value = false
  addMessage('system', '开始生成卡片内容...')
}

/**
 * 生成完成
 */
function finishGeneration(success: boolean, message?: string) {
  isGenerating.value = false
  
  if (success) {
    // 成功完成时，进入暂停状态，允许用户继续反馈
    isPaused.value = true
    addMessage('system', (message || '✓ 生成完成！') + '\n\n您可以继续提供反馈意见，或直接关闭面板。')
  } else {
    // 失败时，完全停止
    isPaused.value = false
    addMessage('error', message || '生成失败')
  }
}

/**
 * 增加已完成字段计数
 */
function incrementCompletedFields() {
  completedFields.value++
}

/**
 * 重置状态
 */
function reset() {
  messages.value = []
  isGenerating.value = false
  isPaused.value = false
  completedFields.value = 0
  userInput.value = ''
}

// ==================== 暴露方法 ====================

defineExpose({
  addMessage,
  startGeneration,
  finishGeneration,
  incrementCompletedFields,
  reset
})

// ==================== 监听 ====================

watch(() => props.visible, (visible) => {
  if (visible) {
    // 面板打开时重新初始化位置
    nextTick(() => {
      initPosition()
    })
  } else {
    // 面板关闭时重置状态
    reset()
  }
})
</script>

<style scoped>
/* 悬浮窗容器 */
.generation-panel-float {
  position: fixed;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  z-index: 2000;
  transition: height 0.3s ease;
}

.generation-panel-float.minimized {
  overflow: visible;
}

/* 顶部标题栏（可拖动）*/
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color);
  cursor: move;
  user-select: none;
  background: var(--el-bg-color);
}

.panel-header:hover {
  background: var(--el-fill-color-light);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.title-icon {
  font-size: 20px;
  color: var(--el-color-primary);
}

/* 消息列表 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-item {
  animation: slideIn 0.2s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-thinking,
.message-action,
.message-user,
.message-warning,
.message-error,
.message-system {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  line-height: 1.6;
}

.message-icon {
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 16px;
}

.message-text {
  flex: 1;
  word-break: break-word;
}

/* 思考消息 */
.message-thinking {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}

.message-thinking .message-icon {
  color: var(--el-color-primary);
}

/* 指令执行消息 */
.message-action {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.message-action .message-icon {
  color: var(--el-color-success);
}

/* 用户消息 */
.message-user {
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-primary);
  margin-left: 20px;
}

.message-user .message-icon {
  color: var(--el-color-primary);
}

/* 警告消息 */
.message-warning {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning-dark-2);
}

.message-warning .message-icon {
  color: var(--el-color-warning);
}

/* 错误消息 */
.message-error {
  background: var(--el-color-error-light-9);
  color: var(--el-color-error-dark-2);
}

.message-error .message-icon {
  color: var(--el-color-error);
}

/* 系统消息 */
.message-system {
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  justify-content: center;
}

.message-system .message-icon {
  color: var(--el-text-color-secondary);
}

/* 生成中指示器 */
.generating-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  color: var(--el-color-primary);
  font-size: 14px;
}

/* 底部控制区 */
.panel-footer {
  border-top: 1px solid var(--el-border-color);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-info {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  text-align: center;
}

.input-area {
  width: 100%;
}

/* 调整大小手柄 */
.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 20px;
  height: 20px;
  cursor: nwse-resize;
  background: linear-gradient(
    135deg,
    transparent 0%,
    transparent 50%,
    var(--el-border-color) 50%,
    var(--el-border-color) 60%,
    transparent 60%,
    transparent 70%,
    var(--el-border-color) 70%,
    var(--el-border-color) 80%,
    transparent 80%
  );
}

.resize-handle:hover {
  background: linear-gradient(
    135deg,
    transparent 0%,
    transparent 50%,
    var(--el-color-primary) 50%,
    var(--el-color-primary) 60%,
    transparent 60%,
    transparent 70%,
    var(--el-color-primary) 70%,
    var(--el-color-primary) 80%,
    transparent 80%
  );
}

.control-buttons {
  display: flex;
  gap: 8px;
  justify-content: center;
}

/* 滚动条样式 */
.messages-container::-webkit-scrollbar {
  width: 6px;
}

.messages-container::-webkit-scrollbar-thumb {
  background: var(--el-border-color-darker);
  border-radius: 3px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-dark);
}
</style>
