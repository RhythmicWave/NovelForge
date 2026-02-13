<template>
  <div class="agent-message-list" ref="listEl">
    <div v-for="(msg, idx) in props.messages" :key="idx" :class="['msg-row', msg.role]">
      <div class="msg-bubble">
        <template v-if="msg.role === 'assistant'">
          <div class="timeline-block">
            <div
              v-for="(timelineItem, timelineIndex) in getRenderSequence(msg)"
              :key="`${idx}-timeline-${timelineIndex}`"
              class="timeline-item"
            >
              <template v-if="timelineItem.kind === 'reasoning'">
                <div class="timeline-thinking-wrap">
                  <div class="thinking-card">
                    <button class="thinking-trigger" type="button" @click="toggleThinkingItem(idx, timelineIndex)">
                      <span class="thinking-status-dot" :class="{ spinning: isThinkingInProgress(idx, timelineIndex) }">
                        <el-icon v-if="isThinkingInProgress(idx, timelineIndex)"><Loading /></el-icon>
                        <template v-else>✓</template>
                      </span>
                      <span class="thinking-title">
                        {{ isThinkingInProgress(idx, timelineIndex) ? '思考中…' : (isThinkingItemOpen(idx, timelineIndex) ? '思考过程' : '思考完成') }}
                      </span>
                      <el-icon class="thinking-arrow">
                        <ArrowUp v-if="isThinkingItemOpen(idx, timelineIndex)" />
                        <ArrowDown v-else />
                      </el-icon>
                    </button>
                    <div v-if="isThinkingItemOpen(idx, timelineIndex)" class="thinking-content">
                      <XMarkdown
                        :markdown="timelineItem.text || ''"
                        :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                        class="bubble-markdown"
                      />
                    </div>
                  </div>
                </div>
              </template>

              <template v-else-if="timelineItem.kind === 'tool' && timelineItem.tool">
                <div class="tool-summary-card timeline-tool-card">
                  <div class="tool-item-head">
                    <el-tag size="small" effect="plain">{{ timelineItem.tool.tool_name }}</el-tag>
                    <span class="tool-status">{{ formatToolStatus(timelineItem.tool) }}</span>
                  </div>

                  <div v-if="showJumpLink(timelineItem.tool)" class="tool-jump-row">
                    <el-link type="primary" size="small" @click="emitJumpToCard(timelineItem.tool)">
                      跳转到卡片 →
                    </el-link>
                  </div>

                  <div v-if="timelineItem.tool.result !== undefined" class="tool-result-toggle-row">
                    <el-button text size="small" @click="toggleToolResult(idx, timelineIndex)">
                      {{ isToolResultOpen(idx, timelineIndex) ? '收起结果' : '展开结果' }}
                    </el-button>
                  </div>
                  <pre
                    v-if="timelineItem.tool.result !== undefined && isToolResultOpen(idx, timelineIndex)"
                    class="tool-result"
                  >{{ formatToolValue(timelineItem.tool.result) }}</pre>
                </div>
              </template>

              <template v-else>
                <div class="markdown-wrap">
                  <XMarkdown
                    :markdown="timelineItem.text || ''"
                    :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                    class="bubble-markdown"
                  />
                </div>
              </template>
            </div>
          </div>

          <div v-if="msg.toolsInProgress" class="tools-in-progress">
            <el-icon class="tools-icon spinning"><Loading /></el-icon>
            <pre class="tools-progress-text">{{ msg.toolsInProgress }}</pre>
          </div>

          <div
            v-if="shouldShowAssistantActions(msg, idx)"
            class="assistant-actions"
          >
            <el-tooltip content="复制回复" placement="top">
              <el-button
                circle
                size="small"
                :icon="CopyDocument"
                @click="emitCopyAssistant(idx)"
              />
            </el-tooltip>
            <el-tooltip content="重新生成" placement="top">
              <el-button
                circle
                size="small"
                :icon="RefreshRight"
                @click="emitRegenerateAssistant(idx)"
              />
            </el-tooltip>
          </div>
        </template>

        <template v-else>
          <div class="markdown-wrap">
            <XMarkdown
              :markdown="msg.content"
              :default-theme-mode="isDarkMode ? 'dark' : 'light'"
              class="bubble-markdown"
            />
          </div>
        </template>
      </div>
    </div>

    <el-empty v-if="!props.messages.length" :description="props.emptyDescription" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { XMarkdown } from 'vue-element-plus-x'
import { Loading, CopyDocument, RefreshRight, ArrowUp, ArrowDown } from '@element-plus/icons-vue'

import { useAppStore } from '@renderer/stores/useAppStore'
import type { AgentChatMessage } from '@/types/agentChat'

const props = withDefaults(
  defineProps<{
    messages: AgentChatMessage[]
    emptyDescription?: string
    streaming?: boolean
    jumpProjectId?: number | null
    showAssistantActions?: boolean
    assistantActionsLatestOnly?: boolean
  }>(),
  {
    emptyDescription: '请输入需求，我会先给出可审阅的结果。',
    streaming: false,
    jumpProjectId: null,
    showAssistantActions: false,
    assistantActionsLatestOnly: true,
  },
)

const emit = defineEmits<{
  (e: 'jump-to-card', payload: { projectId: number; cardId: number }): void
  (e: 'copy-assistant', payload: { index: number }): void
  (e: 'regenerate-assistant', payload: { index: number }): void
}>()

const listEl = ref<HTMLElement | null>(null)
const thinkingOpenMap = ref<Record<string, boolean>>({})
const toolResultOpenMap = ref<Record<string, boolean>>({})

const appStore = useAppStore()
const isDarkMode = computed(() => appStore.isDarkMode)

function thinkingKey(messageIndex: number, timelineIndex: number): string {
  return `thinking-${messageIndex}-${timelineIndex}`
}

function isThinkingItemOpen(messageIndex: number, timelineIndex: number): boolean {
  const key = thinkingKey(messageIndex, timelineIndex)
  if (key in thinkingOpenMap.value) {
    return Boolean(thinkingOpenMap.value[key])
  }
  return isThinkingInProgress(messageIndex, timelineIndex)
}

function toggleThinkingItem(messageIndex: number, timelineIndex: number): void {
  const key = thinkingKey(messageIndex, timelineIndex)
  thinkingOpenMap.value[key] = !thinkingOpenMap.value[key]
}

function isThinkingInProgress(messageIndex: number, timelineIndex: number): boolean {
  if (!props.streaming) return false
  if (messageIndex !== props.messages.length - 1) return false

  const message = props.messages[messageIndex]
  if (!message || message.role !== 'assistant') return false

  if ((message as any)._agentLastEventType !== 'reasoning') {
    return false
  }

  const sequence = getRenderSequence(message)
  const item = sequence[timelineIndex]
  if (!item || item.kind !== 'reasoning') return false

  let latestReasoningIndex = -1
  for (let i = sequence.length - 1; i >= 0; i--) {
    if (sequence[i]?.kind === 'reasoning') {
      latestReasoningIndex = i
      break
    }
  }

  if (latestReasoningIndex < 0) return false
  return timelineIndex === latestReasoningIndex
}

function toolResultKey(messageIndex: number, timelineIndex: number): string {
  return `tool-result-${messageIndex}-${timelineIndex}`
}

function isToolResultOpen(messageIndex: number, timelineIndex: number): boolean {
  return Boolean(toolResultOpenMap.value[toolResultKey(messageIndex, timelineIndex)])
}

function toggleToolResult(messageIndex: number, timelineIndex: number): void {
  const key = toolResultKey(messageIndex, timelineIndex)
  toolResultOpenMap.value[key] = !toolResultOpenMap.value[key]
}

function getRenderSequence(message: AgentChatMessage) {
  const timeline = Array.isArray(message.timeline)
    ? message.timeline.filter(item => {
      if (item.kind === 'tool') return !!item.tool
      return !!(item.text || '').trim()
    })
    : []

  if (timeline.length) {
    return timeline
  }

  const fallback: Array<{ kind: 'reasoning' | 'text' | 'tool'; text?: string; tool?: any }> = []
  if ((message.reasoning || '').trim()) {
    fallback.push({ kind: 'reasoning', text: message.reasoning || '' })
  }
  if ((message.content || '').trim()) {
    fallback.push({ kind: 'text', text: message.content || '' })
  }
  if (Array.isArray(message.tools) && message.tools.length) {
    for (const tool of message.tools) {
      fallback.push({ kind: 'tool', tool })
    }
  }
  return fallback
}

function formatToolValue(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatToolStatus(toolItem: any): string {
  const success = toolItem?.result?.success
  if (success === true) return '✅ 成功'
  if (success === false) return '❌ 失败'
  return '已执行'
}

function showJumpLink(toolItem: any): boolean {
  const cardId = Number(toolItem?.result?.card_id)
  const projectId = Number(props.jumpProjectId)
  if (!Number.isFinite(cardId) || cardId <= 0) return false
  if (!Number.isFinite(projectId) || projectId <= 0) return false
  return true
}

function emitJumpToCard(toolItem: any): void {
  const cardId = Number(toolItem?.result?.card_id)
  const projectId = Number(props.jumpProjectId)
  if (!Number.isFinite(cardId) || cardId <= 0) return
  if (!Number.isFinite(projectId) || projectId <= 0) return
  emit('jump-to-card', { projectId, cardId })
}

function scrollToBottom(): void {
  const element = listEl.value
  if (!element) return
  element.scrollTop = element.scrollHeight
}

function isLatestAssistantIndex(index: number): boolean {
  for (let i = props.messages.length - 1; i >= 0; i--) {
    if (props.messages[i]?.role === 'assistant') {
      return i === index
    }
  }
  return false
}

function shouldShowAssistantActions(message: AgentChatMessage, index: number): boolean {
  if (!props.showAssistantActions) return false
  if (message.role !== 'assistant') return false
  if (!(message.content || '').trim()) return false
  if (props.streaming && index === props.messages.length - 1) return false
  return !props.assistantActionsLatestOnly || isLatestAssistantIndex(index)
}

function emitCopyAssistant(index: number): void {
  emit('copy-assistant', { index })
}

function emitRegenerateAssistant(index: number): void {
  emit('regenerate-assistant', { index })
}

defineExpose({
  scrollToBottom,
})
</script>

<style scoped>
.agent-message-list {
  flex: 1;
  overflow: auto;
  padding: 6px 2px;
}

.msg-row {
  display: flex;
  margin-bottom: 10px;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-row.assistant {
  justify-content: flex-start;
}

.msg-bubble {
  max-width: 88%;
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-overlay);
  color: var(--el-text-color-primary);
}

.msg-row.user .msg-bubble {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-text-color-primary);
}

.markdown-wrap {
  min-width: 0;
}

:deep(.bubble-markdown) {
  line-height: 1.6;
  word-break: break-word;
}

:deep(.bubble-markdown),
:deep(.bubble-markdown p),
:deep(.bubble-markdown li),
:deep(.bubble-markdown h1),
:deep(.bubble-markdown h2),
:deep(.bubble-markdown h3),
:deep(.bubble-markdown h4),
:deep(.bubble-markdown h5),
:deep(.bubble-markdown h6),
:deep(.bubble-markdown blockquote),
:deep(.bubble-markdown span),
:deep(.bubble-markdown strong),
:deep(.bubble-markdown em) {
  color: inherit;
}

:deep(.bubble-markdown a) {
  color: var(--el-color-primary);
}

:deep(.bubble-markdown pre) {
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-primary);
}

:deep(.bubble-markdown code) {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

:deep(.bubble-markdown p) {
  margin: 0.35em 0;
}

.reasoning-block {
  margin-top: 10px;
  margin-bottom: 10px;
}

.timeline-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.timeline-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.timeline-thinking-wrap {
  display: flex;
  justify-content: flex-start;
}

.thinking-card {
  width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-fill-color-lighter);
  overflow: hidden;
}

.thinking-trigger {
  width: 100%;
  border: 0;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  text-align: left;
}

.thinking-status-dot {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--el-color-success);
  color: #fff;
  font-size: 12px;
  flex-shrink: 0;
}

.thinking-status-dot.spinning {
  background: var(--el-color-primary);
}

.thinking-title {
  font-size: 14px;
  font-weight: 600;
  flex: 1;
}

.thinking-arrow {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.thinking-content {
  border-top: 1px solid var(--el-border-color-light);
  padding: 10px 12px;
  background: var(--el-bg-color-overlay);
}

.thinking-content :deep(.bubble-markdown),
.thinking-content :deep(.bubble-markdown p),
.thinking-content :deep(.bubble-markdown li),
.thinking-content :deep(.bubble-markdown span),
.thinking-content :deep(.bubble-markdown strong),
.thinking-content :deep(.bubble-markdown em) {
  color: var(--el-text-color-secondary);
}

.timeline-tool-card {
  margin-top: 0;
}

.tool-summary-card {
  margin-top: 10px;
  border: 1px solid rgba(103, 194, 58, 0.35);
  background: rgba(103, 194, 58, 0.06);
  border-radius: 8px;
  padding: 8px;
  color: var(--el-text-color-primary);
}

.tool-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tool-summary-title {
  color: var(--el-color-success);
  font-size: 13px;
  font-weight: 600;
}

.tool-detail-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-detail-item {
  border-top: 1px dashed var(--el-border-color-lighter);
  padding-top: 8px;
}

.tool-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tool-status {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tools-in-progress {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 6px 8px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.tools-icon {
  margin-top: 2px;
  color: var(--el-color-primary);
}

.spinning {
  animation: spin 1s linear infinite;
}

.tools-progress-text {
  margin: 0;
  white-space: pre-wrap;
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.tool-jump-row {
  margin-top: 6px;
}

.tool-result-toggle-row {
  margin-top: 6px;
}

.tool-result {
  margin: 6px 0 0;
  max-height: 180px;
  overflow: auto;
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 11px;
  line-height: 1.5;
  font-family: 'Cascadia Mono', 'Consolas', monospace;
}

.assistant-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
