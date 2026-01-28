<template>
  <div
    v-show="props.visible"
    ref="panelRef"
    class="generation-panel-float"
    :class="{ minimized: isMinimized }"
    :style="panelStyle"
  >
    <!-- 顶部标题栏-->
    <div class="panel-header" @mousedown="handleDragStart">
      <div class="header-title">
        <el-icon class="title-icon"><MagicStick /></el-icon>
        <span>AI 生成</span>
      </div>
      <div class="header-actions">
        <el-button
          :icon="isMinimized ? ArrowUp : ArrowDown"
          circle
          size="small"
          text
          @click.stop="toggleMinimize"
        />
        <el-button
          :icon="Close"
          circle
          size="small"
          text
          @click.stop="handleClose"
        />
      </div>
    </div>

    <!-- 消息列表（最小化时隐藏）-->
    <div v-show="!isMinimized" ref="messagesContainer" class="messages-container">
      <div
        v-for="(msg, index) in messages"
        :key="index"
        class="message-item"
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
        <el-icon><Check /></el-icon>
        <span>已生成 {{ completedFields }} 个字段</span>
      </div>

      <!-- 用户输入框 -->
      <div class="input-area">
        <div class="custom-input-wrapper">
          <el-input
            v-model="userInput"
            :placeholder="isFinished ? '输入反馈以继续生成...' : (isPaused ? '输入反馈并继续...' : '输入指导意见...')"
            size="default"
            @keyup.enter="handleSendMessage"
          >
           <template #suffix>
              <el-button
                v-if="userInput.trim()"
                :icon="Promotion"
                link
                type="primary"
                @click="handleSendMessage"
              />
           </template>
          </el-input>
        </div>
      </div>

      <!-- 控制按钮 -->
      <div class="control-buttons">
        <!-- 生成中/暂停中 -->
        <template v-if="!isFinished">
           <el-button
            v-if="isGenerating && !isPaused"
            :icon="VideoPause"
            round
            @click="handlePause"
          >
            暂停
          </el-button>

          <el-button
            v-if="isPaused"
            :icon="VideoPlay"
            type="primary"
            round
            @click="handleContinue"
          >
            继续生成
          </el-button>

          <el-button
            :icon="CircleClose"
            text
            bg
            round
            type="danger"
            @click="handleStop"
          >
            终止
          </el-button>
        </template>

        <!-- 完成后 -->
        <template v-else>
           <el-button
            :icon="Check"
            type="primary"
            round
            @click="handleClose"
          >
            完成
          </el-button>

           <el-button
            :icon="RefreshLeft"
            text
            bg
            round
            @click="handleRestart"
          >
            重新开始
          </el-button>
        </template>
      </div>
    </div>
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
  finish: [] // 新增 finish 事件
}>()

// ==================== 状态管理 ====================

const isGenerating = ref(false)
const isPaused = ref(false)
const isFinishedState = ref(false) // 明确的完成状态
const messages = ref<GenerationMessage[]>([])
const completedFields = ref(0)
const userInput = ref('')
const messagesContainer = ref<HTMLElement>()
const panelRef = ref<HTMLElement>()

// 悬浮窗状态
const isMinimized = ref(false)
const position = ref({ x: 0, y: 0 })
const isDragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

// 计算属性：是否处于完成态
const isFinished = computed(() => isFinishedState.value)

// 计算面板样式
const panelStyle = computed(() => {
  if (isMinimized.value) {
    return {
      left: `${position.value.x}px`,
      top: `${position.value.y}px`,
      height: 'auto'
    }
  }
  return {
    left: `${position.value.x}px`,
    top: `${position.value.y}px`
    // height 由 CSS max-height 控制
  }
})

// ==================== 悬浮窗控制方法 ====================

/**
 * 初始化默认位置（右下角，留出一定边距）
 */
function initPosition() {
  const width = 360 // 估计宽度
  const height = 500 // 估计高度
  const padding = 30
  
  position.value = {
    x: window.innerWidth - width - padding,
    y: window.innerHeight - height - padding
  }
}

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
  e.preventDefault()
}

/**
 * 拖动中
 */
function handleDragMove(e: MouseEvent) {
  if (!isDragging.value) return
  
  // 计算新位置
  let newX = e.clientX - dragOffset.value.x
  let newY = e.clientY - dragOffset.value.y
  
  // 简单的边界检查（防止拖出屏幕太远）
  const maxX = window.innerWidth - 50
  const maxY = window.innerHeight - 50
  
  if (newX < -300) newX = -300
  if (newX > maxX) newX = maxX
  if (newY < 0) newY = 0
  if (newY > maxY) newY = maxY

  position.value = { x: newX, y: newY }
}

/**
 * 结束拖动
 */
function handleDragEnd() {
  isDragging.value = false
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
}

// ==================== 生命周期 ====================

onMounted(() => {
  // 初始位置
  initPosition()
  window.addEventListener('resize', handleWindowResize)
})

onUnmounted(() => {
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
  window.removeEventListener('resize', handleWindowResize)
})

function handleWindowResize() {
  // 简单的自适应：如果超出屏幕则重置
  if (position.value.x > window.innerWidth - 100 || position.value.y > window.innerHeight - 100) {
    initPosition()
  }
}

// ==================== 业务逻辑方法 ====================

/**
 * 添加消息
 */
function addMessage(type: GenerationMessage['type'], content: string) {
  if (type === 'thinking' && messages.value.length > 0) {
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage.type === 'thinking') {
      lastMessage.content += content
      lastMessage.timestamp = Date.now()
      nextTick(scrollToBottom)
      return
    }
  }
  
  messages.value.push({
    type,
    content,
    timestamp: Date.now()
  })
  nextTick(scrollToBottom)
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function handleClose() {
  emit('close')
}

function handlePause() {
  isPaused.value = true
  isGenerating.value = false // 暂停时不视为生成中
  addMessage('system', '已暂停')
  emit('pause')
}

function handleContinue() {
  const message = userInput.value.trim() 
  if (message) {
    addMessage('user', message)
  }
  userInput.value = ''
  
  isPaused.value = false
  isFinishedState.value = false
  isGenerating.value = true
  
  emit('continue', message || '请继续')
}

function handleStop() {
  isGenerating.value = false
  isPaused.value = false
  isFinishedState.value = true // 终止也算一种结束状态
  addMessage('system', '生成已终止')
  emit('stop')
}

function handleRestart() {
  reset()
  emit('restart')
}

function handleSendMessage() {
  if (!userInput.value.trim()) return

  if (isPaused.value || isFinishedState.value) {
    // 暂停或（新增）已完成状态下，发送消息都视为继续生成
    handleContinue()
  } else if (isGenerating.value) {
    // 生成中插入反馈
    const msg = userInput.value.trim()
    addMessage('user', msg)
    userInput.value = ''
  }
}

function startGeneration() {
  reset()
  isGenerating.value = true
  addMessage('system', '开始生成...')
}

function finishGeneration(success: boolean, message?: string) {
  isGenerating.value = false
  isPaused.value = false
  isFinishedState.value = true // 标记为完成
  
  if (success) {
    addMessage('system', (message || '✓ 生成完成'))
  } else {
    addMessage('error', message || '生成失败')
  }
}

function incrementCompletedFields() {
  completedFields.value++
}

function reset() {
  messages.value = []
  isGenerating.value = false
  isPaused.value = false
  isFinishedState.value = false
  completedFields.value = 0
  userInput.value = ''
}

defineExpose({
  addMessage,
  startGeneration,
  finishGeneration,
  incrementCompletedFields,
  reset
})

watch(() => props.visible, (val) => {
  if (val) {
    // 每次打开检查位置
    if (position.value.x === 0 && position.value.y === 0) {
      initPosition()
    }
  }
})
</script>

<style scoped>
/* 悬浮窗容器 - 毛玻璃风格 */
.generation-panel-float {
  position: fixed; /* 全局悬浮 */
  width: 380px;
  max-height: 500px; /* 固定最大高度 */
  display: flex;
  flex-direction: column;
  
  /* 毛玻璃效果 */
  background: rgba(255, 255, 255, 0.9); /* 更不透明，增加对比 */
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 20px;
  box-shadow: 
    0 16px 48px rgba(0, 0, 0, 0.12),
    0 8px 24px rgba(0, 0, 0, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
  
  overflow: hidden;
  z-index: 9999; /* 确保在顶层 */
  transition: opacity 0.2s;
}

/* 暗色模式适配 */
html.dark .generation-panel-float {
  /* 提升背景亮度以区别于深色编辑器背景 (通常是 #1e1e1e) */
  background: rgba(45, 45, 45, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.15); /* 更明显的边框 */
  box-shadow: 
    0 20px 60px rgba(0, 0, 0, 0.6),
    0 8px 20px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.generation-panel-float.minimized {
  height: auto !important;
  max-height: 52px;
  overflow: hidden;
}

/* 顶部标题栏 */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  cursor: move; /* 允许拖动 */
  user-select: none;
  background: rgba(255, 255, 255, 0.5);
  flex-shrink: 0;
}

html.dark .panel-header {
  background: rgba(255, 255, 255, 0.05);
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px; /* 加大字号 */
  font-weight: 800; /* 更粗 */
  /* 渐变文字效果 */
  background: linear-gradient(120deg, var(--el-text-color-primary) 0%, var(--el-color-primary) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: var(--el-text-color-primary); /* 回退 */

  letter-spacing: 0.5px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.title-icon {
  font-size: 20px;
  /* 图标也加一点动感 */
  filter: drop-shadow(0 2px 4px rgba(64, 158, 255, 0.3));
  color: var(--el-color-primary);
}

/* 消息列表 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 120px; /* 最小内容高度 */
}

.message-item {
  animation: fadeSlideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 消息气泡通用样式 */
.message-thinking,
.message-action,
.message-user,
.message-warning,
.message-error,
.message-system {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  position: relative;
}

.message-icon {
  margin-top: 3px;
  font-size: 16px;
  flex-shrink: 0;
}

.message-text {
  word-break: break-word;
  white-space: pre-wrap;
}

/* 思考 */
.message-thinking {
  background: rgba(240, 242, 245, 0.6);
  color: var(--el-text-color-regular);
  font-size: 13px;
}
html.dark .message-thinking { background: rgba(255,255,255,0.05); }
.message-thinking .message-icon { color: #909399; }

/* 成功/执行 */
.message-action {
  background: rgba(225, 243, 216, 0.4);
  color: #67C23A;
}
html.dark .message-action { background: rgba(103, 194, 58, 0.15); }

/* 错误 */
.message-error {
  background: rgba(254, 240, 240, 0.8);
  color: #F56C6C;
  border: 1px solid rgba(245, 108, 108, 0.2);
}
html.dark .message-error { 
  background: rgba(245, 108, 108, 0.15); 
  border-color: rgba(245, 108, 108, 0.3);
}

/* 警告 */
.message-warning {
  background: rgba(253, 246, 236, 0.8);
  color: #E6A23C;
  border: 1px solid rgba(230, 162, 60, 0.2);
}
html.dark .message-warning { 
  background: rgba(230, 162, 60, 0.15); 
  border-color: rgba(230, 162, 60, 0.3);
}

/* 用户 */
.message-user {
  align-self: flex-start; /* 统一靠左 */
  background: rgba(236, 245, 255, 0.6);
  color: var(--el-text-color-primary);
  /* 使用伪元素实现左侧强调条，配合 overflow: hidden 完美贴合圆角 */
  position: relative;
  overflow: hidden;
  padding-left: 18px; /* 增加左侧内边距，给强调条留出空间 */
}

.message-user::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background-color: #409EFF;
}

html.dark .message-user { background: rgba(64, 158, 255, 0.15); }

/* 系统 */
.message-system {
  background: transparent;
  justify-content: center;
  padding: 4px 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

/* 生成中指示器 */
.generating-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  color: var(--el-color-primary);
  font-size: 13px;
}

/* 底部控制区 */
.panel-footer {
  flex-shrink: 0; /* 防止底部被压缩 */
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

html.dark .panel-footer {
  background: rgba(255, 255, 255, 0.03);
  border-top-color: rgba(255, 255, 255, 0.08);
}

.progress-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-color-success);
  font-weight: 500;
}

/* 输入框美化 */
.custom-input-wrapper {
  transition: transform 0.2s;
}
.custom-input-wrapper:focus-within {
  transform: translateY(-2px);
}

:deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
  border: 1px solid rgba(0,0,0,0.05);
  padding-right: 8px;
  background-color: var(--el-fill-color-blank); /* 显式设置背景色 */
}

/* 暗色模式下输入框增强 */
html.dark :deep(.el-input__wrapper) {
  background-color: rgba(0, 0, 0, 0.3); /* 深色半透明背景 */
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: none !important;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.2) !important;
  border-color: var(--el-color-primary-light-5);
}

html.dark :deep(.el-input__wrapper.is-focus) {
  background-color: rgba(0, 0, 0, 0.5);
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary) !important;
}

.control-buttons {
  display: flex;
  justify-content: center;
  gap: 12px;
}

.control-buttons .el-button {
  padding: 8px 20px;
  font-weight: 500;
  transition: all 0.2s;
}

.control-buttons .el-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

/* 滚动条美化 */
.messages-container::-webkit-scrollbar { width: 4px; }
.messages-container::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.1);
  border-radius: 2px;
}
html.dark .messages-container::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); }
</style>
