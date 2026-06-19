<template>
  <div class="assistant-panel" :style="assistantPanelStyle">
    <div class="panel-header">
      <div class="header-title-row">
        <div class="title-area">
          <span class="main-title">灵感助手</span>
          <span class="session-subtitle">{{ currentSession.title }}</span>
        </div>
        <div class="spacer"></div>
        <el-tooltip content="新增对话" placement="bottom">
          <el-button :icon="Plus" size="small" circle @click="createNewSession" />
        </el-tooltip>
        <el-tooltip content="历史对话" placement="bottom">
          <el-button :icon="Clock" size="small" circle @click="historyDrawerVisible = true" />
        </el-tooltip>
      </div>
      <div class="header-controls-row">
        <el-tag v-if="currentCardTitle" size="small" type="info" class="card-tag" effect="plain">{{ currentCardTitle }}</el-tag>
        <div class="spacer"></div>
        <el-button size="small" @click="$emit('refresh-context')">刷新上下文</el-button>
        <el-popover placement="bottom" width="480" trigger="hover">
          <template #reference>
            <el-tag type="info" class="ctx-tag" size="small">预览</el-tag>
          </template>
          <pre class="ctx-preview">{{ (resolvedContext || '') }}</pre>
        </el-popover>
      </div>
    </div>

    <div class="chat-area reasoning-container">
      <AgentMessageList
        ref="messageListRef"
        :messages="messages"
        :streaming="isStreaming"
        empty-description="请输入你的需求，我会先给出建议。"
        :jump-project-id="projectStore.currentProject?.id || null"
        :show-assistant-actions="true"
        :assistant-actions-latest-only="false"
        :show-user-actions="true"
        @jump-to-card="payload => emit('jump-to-card', payload)"
        @copy-assistant="payload => handleCopyAssistantAt(payload.index)"
        @regenerate-assistant="payload => handleRegenerateAt(payload.index)"
        @delete-assistant="payload => handleDeleteAssistantAt(payload.index)"
        @copy-user="payload => handleCopyUserAt(payload.index)"
        @delete-user="payload => handleDeleteUserAt(payload.index)"
      />
      <div v-if="isStreaming" class="streaming-tip">正在生成中…</div>
    </div>

    <div class="composer">
      <div class="inject-toolbar">
        <!-- 引用卡片显示区（分成两个容器：标签区 + 更多按钮区） -->
        <div class="chips">
          <!-- 标签显示区（可滚动溢出） -->
          <div class="chips-tags">
            <el-tag 
              v-for="(r, idx) in visibleRefs" 
              :key="getRefKey(r)" 
              closable 
              @close="removeInjectedRef(idx)" 
              size="small" 
              effect="plain" 
              class="chip-tag" 
              @click="onChipClick(r)"
            >
              {{ getRefLabel(r) }}
            </el-tag>
          </div>

          <!-- 更多按钮区（固定显示，不受宽度影响） -->
          <div v-if="assistantStore.injectedRefs.length > 0" class="chips-more">
            <el-popover
              placement="bottom-start"
              :width="380"
              trigger="click"
            >
              <template #reference>
                <el-button 
                  size="small" 
                  text
                  class="more-refs-btn"
                  :title="`共 ${assistantStore.injectedRefs.length} 个引用卡片`"
                >
                  <span class="more-refs-dots">...</span>
                  <span class="more-refs-count">({{ assistantStore.injectedRefs.length }})</span>
                </el-button>
              </template>

              <!-- Popover 内容 -->
              <div class="more-refs-popover">
                <div class="popover-header">
                  <span>引用卡片</span>
                  <span class="popover-count">{{ assistantStore.injectedRefs.length }} 个</span>
                </div>
                <div class="more-refs-list">
                  <div 
                    v-for="(r, idx) in assistantStore.injectedRefs" 
                    :key="getRefKey(r)"
                    class="more-ref-item"
                  >
                    <span class="ref-info" @click="onChipClick(r)">
                      <el-icon><Document /></el-icon>
                      {{ getRefLabel(r) }}
                    </span>
                    <el-button 
                      :icon="Close" 
                      size="small" 
                      text 
                      @click="removeInjectedRef(idx)"
                      title="删除引用"
                    />
                  </div>
                </div>
              </div>
            </el-popover>
          </div>
        </div>

        <el-button size="small" :icon="Plus" @click="openInjectSelector" class="add-ref-btn">添加引用</el-button>
      </div>

      <div class="composer-subbar">
        <el-select v-model="overrideLlmId" placeholder="选择模型" size="small" style="width: 200px">
          <el-option v-for="m in llmOptions" :key="m.id" :label="(m.display_name || m.model_name)" :value="m.id" />
        </el-select>
      </div>

      <AgentComposer
        v-model="draft"
        :rows="4"
        placeholder="输入你的想法、约束或追问"
        :disabled="isStreaming"
        input-class="composer-input"
        @keydown="handleComposerEnter"
      >
        <template #actions>
          <div class="composer-actions">
            <el-tooltip content="Thinking：启用推理/思考模式（确保模型支持开启/关闭思考）" placement="top">
              <el-switch 
                v-model="useThinkingMode" 
                size="small"
                active-text="Thinking"
                style="margin-right: auto"
              />
            </el-tooltip>
            <el-button
              :type="sendButtonType"
              :icon="sendButtonIcon"
              circle
              :disabled="!isStreaming && !canSend"
              @click="handlePrimaryAction"
              :title="sendButtonTitle"
            />
          </div>
        </template>
      </AgentComposer>
    </div>

    <!-- 选择器对话框 -->
    <el-dialog v-model="selectorVisible" title="添加引用卡片" width="760px">
      <div style="display:flex; gap:12px; align-items:center; margin-bottom:10px;">
        <el-select v-model="selectorSourcePid" placeholder="来源项目" style="width: 260px" @change="onSelectorProjectChange($event as any)">
          <el-option v-for="p in assistantStore.projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-input v-model="selectorSearch" placeholder="搜索标题..." clearable style="flex:1" />
      </div>
      <el-tree :data="selectorTreeData" :props="{ label: 'label', children: 'children' }" node-key="key" show-checkbox highlight-current :default-expand-all="false" :check-strictly="false" @check="onTreeCheck" style="max-height:360px; overflow:auto; border:1px solid var(--el-border-color-light); padding:8px; border-radius:6px;" />
      <template #footer>
        <el-button @click="selectorVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!selectorSelectedIds.length || !selectorSourcePid" @click="confirmAddInjectedRefs">添加</el-button>
      </template>
    </el-dialog>


    <!-- 历史对话抽屉 -->
    <el-drawer
      v-model="historyDrawerVisible"
      title="历史对话"
      direction="rtl"
      size="320px"
    >
      <div class="history-drawer-content">
        <div class="history-actions">
          <el-button type="primary" :icon="Plus" @click="createNewSession" style="width: 100%;">
            新增对话
          </el-button>
        </div>

        <el-divider />

        <div v-if="!historySessions.length" class="empty-history">
          <el-empty description="暂无历史对话" :image-size="80" />
        </div>

        <div v-else class="history-list">
          <div 
            v-for="session in historySessions" 
            :key="session.id"
            :class="['history-item', { 'is-current': session.id === currentSession.id }]"
            @click="loadSession(session.id)"
          >
            <div class="history-item-header">
              <el-icon class="history-icon"><ChatDotRound /></el-icon>
              <span class="history-title">{{ session.title }}</span>
            </div>
            <div class="history-item-footer">
              <span class="history-time">{{ formatSessionTime(session.updatedAt) }}</span>
              <el-button 
                :icon="Delete" 
                size="small" 
                text 
                type="danger"
                @click.stop="handleDeleteSession(session.id)"
              />
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { generateContinuationStreaming, renderPromptWithKnowledge } from '@renderer/api/ai'
import { listLLMConfigs, type LLMConfigRead } from '@renderer/api/setting'
import { Plus, Promotion, ChatDotRound, Delete, Clock, Document, Close, VideoPause } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentMessageList from '@/components/shared/AgentMessageList.vue'
import AgentComposer from '@/components/shared/AgentComposer.vue'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { useAssistantPreferences } from '@renderer/composables/useAssistantPreferences'
import { useAssistantSessionHistory } from '@renderer/composables/useAssistantSessionHistory'
import { useAssistantInjectionSelector } from '@renderer/composables/useAssistantInjectionSelector'
import { useAssistantRequestBuilder } from '@renderer/composables/useAssistantRequestBuilder'
import { applyAssistantStreamChunk, resetAssistantMessageForRegenerate } from '@renderer/composables/useAssistantStreamMessageOps'
import { useEnterToSend } from '@renderer/composables/useEnterToSend'
import { useMessageListScroll } from '@renderer/composables/useMessageListScroll'
import { notifyTaskDone } from '@renderer/utils/taskDoneNotifier'
import type { AssistantChatSession, AssistantPanelMessage } from '@renderer/types/assistantPanel'
import type { AssistantRef } from '@renderer/api/ai'

const props = defineProps<{ resolvedContext: string; llmConfigId?: number | null; promptName?: string | null; temperature?: number | null; max_tokens?: number | null; timeout?: number | null; effectiveSchema?: any; generationPromptName?: string | null; currentCardTitle?: string | null; currentCardContent?: any }>()
const emit = defineEmits<{ 'finalize': [string]; 'refresh-context': []; 'reset-selection': []; 'jump-to-card': [{ projectId: number; cardId: number }] }>()
const messages = ref<AssistantPanelMessage[]>([])
const draft = ref('')
const isStreaming = ref(false)
let streamCtl: { cancel: () => void } | null = null
let streamCanceled = false
const { messageListRef, scrollToBottom } = useMessageListScroll()

// ---- 多卡片数据引用（跨项目，使用 Pinia） ----
const assistantStore = useAssistantStore()
const projectStore = useProjectStore()
const editorStore = useEditorStore()

// 思考过程折叠状态：key 为 bucket 标识（例如 plain-0-0 / pre-0-0 / g-0-1-0），值为是否展开
// 默认收起（false），用户点击后再展开
const reasoningBucketsOpen = ref<Record<string, boolean>>({})

function isReasoningBucketOpen(key: string): boolean {
  return Boolean(reasoningBucketsOpen.value[key])
}

// ===== 会话管理 =====
const currentSession = ref<AssistantChatSession>({
  id: `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  projectId: 0,
  title: '新对话',
  createdAt: Date.now(),
  updatedAt: Date.now(),
  messages: []
})

const historySessions = ref<AssistantChatSession[]>([])
const historyDrawerVisible = ref(false)
const projectIdRef = computed(() => projectStore.currentProject?.id || null)

const sessionHistory = useAssistantSessionHistory({
  projectId: projectIdRef,
  messages,
  currentSession,
  historySessions,
  historyDrawerVisible,
  onScrollToBottom: () => scrollToBottom(),
})

const {
  saveCurrentSession,
  createNewSession,
  loadSession,
  handleDeleteSession,
  formatSessionTime,
} = sessionHistory

const lastRun = ref<{ prev: string; tail: string; targetIdx: number } | null>(null)
const canRegenerate = computed(() => !isStreaming.value && !!lastRun.value && messages.value[lastRun.value.targetIdx]?.role === 'assistant')

// 模型选择（覆盖卡片配置，按项目记忆）
const llmOptions = ref<LLMConfigRead[]>([])
const overrideLlmId = ref<number | null>(null)
const effectiveLlmId = computed(() => overrideLlmId.value || props.llmConfigId || null)
const MODEL_KEY_PREFIX = 'nf:assistant:model:'
function modelKeyForProject(pid: number): string { return `${MODEL_KEY_PREFIX}${pid}` }

function restoreProjectAssistantState(pid: number | null): void {
  if (!pid) {
    overrideLlmId.value = null
    return
  }

  const saved = Number(localStorage.getItem(modelKeyForProject(pid)) || '')
  if (saved && Number.isFinite(saved)) {
    overrideLlmId.value = saved
  } else if (llmOptions.value.length > 0) {
    overrideLlmId.value = llmOptions.value[0].id
  } else {
    overrideLlmId.value = null
  }

  const thinkingSaved = localStorage.getItem(thinkingModeKeyForProject(pid))
  if (thinkingSaved !== null) {
    useThinkingMode.value = thinkingSaved === 'true'
  }
}

// Thinking 模式开关（按项目记忆）
const useThinkingMode = ref(false)
const THINKING_MODE_KEY_PREFIX = 'nf:assistant:thinking:'
function thinkingModeKeyForProject(pid: number): string { return `${THINKING_MODE_KEY_PREFIX}${pid}` }

// 引用卡片显示控制
const MAX_VISIBLE_REFS = 5  // 最多显示5个引用（约两行，每行2-3个）

const visibleRefs = computed(() => {
  return assistantStore.injectedRefs.slice(0, MAX_VISIBLE_REFS)
})

watch(overrideLlmId, (val) => {
  try { const pid = projectStore.currentProject?.id; if (pid && val) localStorage.setItem(modelKeyForProject(pid), String(val)) } catch {
    // ignore localStorage write errors
  }
})

watch(useThinkingMode, (val) => {
  try { const pid = projectStore.currentProject?.id; if (pid) localStorage.setItem(thinkingModeKeyForProject(pid), String(val)) } catch {
    // ignore localStorage write errors
  }
})

const injectedCardPrompt = ref<string>('')
async function loadInjectedCardPrompt() {
  try {
    const name = props.generationPromptName || ''
    if (!name) { injectedCardPrompt.value = ''; return }
    const resp = await renderPromptWithKnowledge(name)
    injectedCardPrompt.value = resp?.text || ''
  } catch { injectedCardPrompt.value = '' }
}

watch(() => props.generationPromptName, async () => { await loadInjectedCardPrompt() }, { immediate: true })

const canSend = computed(() => {
  const hasDraft = !!draft.value.trim()
  const hasRefs = assistantStore.injectedRefs.length > 0
  return !!effectiveLlmId.value && (hasDraft || hasRefs)
})
const sendButtonType = computed(() => (isStreaming.value ? 'danger' : 'primary'))
const sendButtonTitle = computed(() => (isStreaming.value ? '中止生成' : '发送'))
const sendButtonIcon = computed(() => (isStreaming.value ? VideoPause : Promotion))

const assistantPrefs = useAssistantPreferences()
const assistantPanelStyle = computed(() => ({
  '--nf-assistant-font-size': `${assistantPrefs.assistantFontSize.value}px`,
  '--nf-assistant-line-height': '1.65',
}))

function notifyAssistantDone(): void {
  notifyTaskDone({
    title: '灵感助手完成',
    body: '助手回复已生成。',
    soundEnabled: assistantPrefs.taskDoneSoundEnabled.value,
    desktopNotificationEnabled: assistantPrefs.taskDoneDesktopNotificationEnabled.value,
  })
}
const injectionSelector = useAssistantInjectionSelector({
  assistantStore,
  currentProjectId: computed(() => projectStore.currentProject?.id || null),
})

const {
  selectorVisible,
  selectorSourcePid,
  selectorSearch,
  selectorSelectedIds,
  selectorTreeData,
  openInjectSelector,
  onSelectorProjectChange,
  onTreeCheck,
  confirmAddInjectedRefs,
} = injectionSelector

function removeInjectedRef(idx: number) { assistantStore.removeInjectedRefAt(idx) }

function getRefKey(ref: AssistantRef): string {
  if (ref.refType === 'card') return `card:${ref.projectId}:${ref.cardId}`
  if (ref.refType === 'chapter_excerpt') {
    return `chapter_excerpt:${ref.projectId}:${ref.cardId}:${ref.startLine}:${ref.endLine}:${ref.snapshotHash}`
  }
  return `review_result:${ref.projectId}:${ref.reviewCardId}`
}

function getRefLabel(ref: AssistantRef): string {
  if (ref.refType === 'card') return `${ref.projectName} / ${ref.cardTitle}`
  if (ref.refType === 'chapter_excerpt') {
    return `${ref.projectName} / ${ref.cardTitle} [${ref.startLine}-${ref.endLine}行]`
  }
  return `审核结果 / ${ref.targetTitle}`
}

const { buildConversationText, buildAssistantChatRequest } = useAssistantRequestBuilder({
  messages,
  assistantStore,
  resolvedContext: computed(() => props.resolvedContext || ''),
  effectiveSchema: computed(() => props.effectiveSchema),
  preferences: {
    contextSummaryEnabled: assistantPrefs.contextSummaryEnabled,
    contextSummaryThreshold: assistantPrefs.contextSummaryThreshold,
    reactModeEnabled: assistantPrefs.reactModeEnabled,
    assistantTemperature: assistantPrefs.assistantTemperature,
    assistantMaxTokens: assistantPrefs.assistantMaxTokens,
    assistantTimeout: assistantPrefs.assistantTimeout,
  },
})

async function startStreaming(targetIdx: number) {
  isStreaming.value = true
  streamCanceled = false

  const hasChapterExcerptRefs = assistantStore.injectedRefs.some(ref => ref.refType === 'chapter_excerpt')
  if (hasChapterExcerptRefs) {
    try {
      const persisted = await editorStore.persistActiveChapterDraft()
      if (!persisted) {
        isStreaming.value = false
        return
      }
    } catch (error) {
      console.error('Failed to persist active chapter draft before assistant run:', error)
      ElMessage.error('正文保存失败，请先保存章节后重试')
      isStreaming.value = false
      return
    }
  }

  const chatRequest = buildAssistantChatRequest()
  const promptName = props.promptName?.trim() || '灵感对话'
  const requestTemperature = assistantPrefs.assistantTemperature.value

  streamCtl = generateContinuationStreaming({
    ...chatRequest,
    llm_config_id: overrideLlmId.value || undefined,
    prompt_name: promptName,
    temperature: requestTemperature || undefined,
    project_id: projectStore.currentProject?.id as number,
    stream: true,
    thinking_enabled: useThinkingMode.value
  } as any, (chunk) => {
    applyAssistantStreamChunk({
      messages,
      targetIdx,
      chunk,
      reasoningBucketsOpen,
      isReasoningBucketOpen,
      scrollToBottom,
      schedule: callback => nextTick(callback),
      onToolsExecuted: tools => handleToolsExecuted(targetIdx, tools),
    })
  }, () => {
    const wasCanceled = streamCanceled
    streamCanceled = false
    isStreaming.value = false
    streamCtl = null

    if (messages.value[targetIdx]?.toolsInProgress && 
        !messages.value[targetIdx].toolsInProgress.includes('❌')) {
      nextTick(() => {
        if (messages.value[targetIdx]) {
          messages.value[targetIdx].toolsInProgress = undefined
        }
      })
    }

    if (messages.value.length > 0) {
      saveCurrentSession()
    }
    if (!wasCanceled) {
      nfFlushAssistantTextPatchBatches(targetIdx)
      nfMaybeDispatchTextPatchBatchFromMessage(targetIdx)
      notifyAssistantDone()
    }
  }, (err) => { 
    streamCanceled = false
    if (messages.value[targetIdx]) {
      messages.value[targetIdx].toolsInProgress = undefined
    }
    ElMessage.error(err?.message || '生成失败')
    isStreaming.value = false
    streamCtl = null 
  }) as any
}

function handleSend() {
  if (!canSend.value || isStreaming.value) return
  lastRun.value = null
  const userText = draft.value.trim(); if (!userText) return
  messages.value.push({ role: 'user', content: userText })
  try { const pid = projectStore.currentProject?.id; if (pid) assistantStore.appendHistory(pid, { role: 'user', content: userText }) } catch {}
  draft.value = ''
  scrollToBottom()

  // 灵感助手不需要 prev/tail，直接在 startStreaming 内部构建请求
  const assistantIdx = messages.value.push({ role: 'assistant', content: '' }) - 1
  scrollToBottom()
  lastRun.value = { prev: '', tail: '', targetIdx: assistantIdx }
  startStreaming(assistantIdx)
}

function handleCancel() { 
  if (streamCtl) streamCanceled = true
  try { streamCtl?.cancel() } catch {}
  isStreaming.value = false

  // 清除所有消息中的工具调用进度提示
  messages.value.forEach(msg => {
    if (msg.toolsInProgress) {
      msg.toolsInProgress = undefined
    }
  })
}

function handlePrimaryAction() {
  if (isStreaming.value) {
    handleCancel()
    return
  }
  handleSend()
}

function handleCopyAssistantAt(index: number) {
  const target = messages.value[index]
  if (!target || target.role !== 'assistant') return
  const text = (target.content || '').trim()
  if (!text) return

  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function handleCopyUserAt(index: number) {
  const target = messages.value[index]
  if (!target || target.role !== 'user') return
  const text = (target.content || '').trim()
  if (!text) return

  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function handleRegenerateAt(index: number) {
  if (isStreaming.value) return
  if (index < 0 || index >= messages.value.length) return
  if (messages.value[index]?.role !== 'assistant') return

  messages.value = messages.value.slice(0, index + 1)
  const target = messages.value[index]
  resetAssistantMessageForRegenerate(target)

  lastRun.value = { prev: '', tail: '', targetIdx: index }
  scrollToBottom()
  startStreaming(index)
}

function handleDeleteAssistantAt(index: number) {
  if (isStreaming.value) return
  if (index < 0 || index >= messages.value.length) return
  if (messages.value[index]?.role !== 'assistant') return

  deleteMessageAt(index)
  ElMessage.success('已删除该回复')
}

function handleDeleteUserAt(index: number) {
  if (isStreaming.value) return
  if (index < 0 || index >= messages.value.length) return
  if (messages.value[index]?.role !== 'user') return

  deleteMessageAt(index)
  ElMessage.success('已删除该消息')
}

function deleteMessageAt(index: number) {
  if (index < 0 || index >= messages.value.length) return

  messages.value.splice(index, 1)

  if (lastRun.value) {
    if (lastRun.value.targetIdx === index) {
      lastRun.value = null
    } else if (lastRun.value.targetIdx > index) {
      lastRun.value = {
        ...lastRun.value,
        targetIdx: lastRun.value.targetIdx - 1,
      }
    }
  }

  saveCurrentSession()
}

function handleRegenerate() { if (!canRegenerate.value || !lastRun.value) return; messages.value[lastRun.value.targetIdx].content = ''; scrollToBottom(); startStreaming(lastRun.value.targetIdx) }
function regenerateFromCurrent() {
  if (isStreaming.value) return
  const lastIndex = messages.value.length - 1
  const lastIsAssistant = lastIndex >= 0 && messages.value[lastIndex].role === 'assistant'
  let targetIdx: number
  if (lastIsAssistant) {
    resetAssistantMessageForRegenerate(messages.value[lastIndex])
    targetIdx = lastIndex
  } else {
    targetIdx = messages.value.push({ role: 'assistant', content: '' }) - 1
  }
  lastRun.value = { prev: '', tail: '', targetIdx }
  startStreaming(targetIdx)
}
function handleRegenerateWithHistory() {
  // 优先移除历史中的最后一条助手消息
  try {
    const pid = projectStore.currentProject?.id
    if (pid) {
      const hist = assistantStore.getHistory(pid)
      for (let i = hist.length - 1; i >= 0; i--) { if (hist[i].role === 'assistant') { hist.splice(i, 1); break } }
      assistantStore.setHistory(pid, hist)
    }
  } catch {}
  if (lastRun.value && canRegenerate.value) {
    handleRegenerate()
  } else {
    regenerateFromCurrent()
  }
}
function handleFinalize() { const summary = (() => { const last = [...messages.value].reverse().find(m => m.role === 'assistant'); return (last?.content || '').trim() || buildConversationText() })(); emit('finalize', summary) }
function onChipClick(refItem: AssistantRef) {
  if (refItem.refType === 'review_result') {
    emit('jump-to-card', { projectId: refItem.projectId, cardId: refItem.targetId })
    return
  }
  emit('jump-to-card', { projectId: refItem.projectId, cardId: refItem.cardId })
}

const handleComposerEnter = useEnterToSend({
  canSend,
  onSend: handleSend,
  streaming: isStreaming,
})

onMounted(async () => {
  try {
    llmOptions.value = await listLLMConfigs()
  } catch {}
  restoreProjectAssistantState(projectStore.currentProject?.id || null)
})

watch(projectIdRef, (pid) => {
  restoreProjectAssistantState(pid)
})

// ✅ 处理工具执行结果：将工具结果追加到指定的助手消息上
/* NF_ASSISTANT_BATCH_PATCH_BEGIN */
function nfIsAssistantTextPatchBatch(result: any): boolean {
  return !!result && (
    result.kind === 'assistant_text_patch_batch' ||
    result.status === 'text_patch_batch_proposed'
  ) && Array.isArray(result.patches)
}

function nfNormalizeAssistantPatchBatch(result: any) {
  const patches = Array.isArray(result?.patches) ? result.patches : []
  return {
    ...result,
    kind: 'assistant_text_patch_batch',
    status: result?.status || 'text_patch_batch_proposed',
    patches: patches.map((patch: any, index: number) => ({
      ...patch,
      id: patch?.id ?? index + 1,
      index: patch?.index ?? index + 1,
      old_text: patch?.old_text ?? patch?.original_text ?? '',
      original_text: patch?.original_text ?? patch?.old_text ?? '',
      new_text: patch?.new_text ?? patch?.revised_text ?? patch?.replacement_text ?? '',
      instruction: patch?.instruction ?? patch?.reason ?? patch?.explanation ?? '',
      status: patch?.status || 'pending',
    })),
  }
}

function nfDispatchAssistantTextPatchBatch(result: any): number {
  const batch = nfNormalizeAssistantPatchBatch(result)
  if (!batch.patches.length) return 0
  window.dispatchEvent(new CustomEvent('nf-assistant-text-patch-batch', { detail: batch }))
  return batch.patches.length
}

function nfStoreAssistantTextPatchBatches(
  msg: AssistantPanelMessage,
  results: any[],
): void {
  const messageAny = msg as any
  if (!Array.isArray(messageAny._nfPendingPatchBatches)) {
    messageAny._nfPendingPatchBatches = []
  }
  messageAny._nfPendingPatchBatches.push(...results.map(nfNormalizeAssistantPatchBatch))
}

function nfFlushAssistantTextPatchBatches(targetIdx: number): boolean {
  const msg = messages.value[targetIdx]
  if (!msg || msg.role !== 'assistant') return false

  const messageAny = msg as any
  const batches = Array.isArray(messageAny._nfPendingPatchBatches)
    ? messageAny._nfPendingPatchBatches
    : []
  if (!batches.length) return false

  const grouped = new Map<string, any>()
  for (const batch of batches) {
    const key = `${batch.card_id ?? ''}::${batch.field_path ?? 'content'}`
    const current = grouped.get(key)
    if (current) {
      current.patches.push(...batch.patches)
      current.failed_patches = [
        ...(current.failed_patches || []),
        ...(batch.failed_patches || []),
      ]
    } else {
      grouped.set(key, {
        ...batch,
        patches: [...batch.patches],
        failed_patches: [...(batch.failed_patches || [])],
      })
    }
  }

  let total = 0
  grouped.forEach(batch => {
    batch.patches = batch.patches.map((patch: any, index: number) => ({
      ...patch,
      id: patch.id ?? index + 1,
      index: index + 1,
    }))
    batch.count = batch.patches.length
    batch.failed_count = Array.isArray(batch.failed_patches) ? batch.failed_patches.length : 0
    total += nfDispatchAssistantTextPatchBatch(batch)
  })

  messageAny._nfPendingPatchBatches = []
  messageAny._nfPatchBatchDispatched = total > 0
  if (total > 0) {
    ElMessage.success(`已发送 ${total} 条修改建议到当前正文编辑器`)
  }
  return total > 0
}

function nfCleanPatchText(raw: unknown): string {
  return String(raw ?? '')
    .trim()
    .replace(/^```[a-zA-Z0-9_-]*\s*/, '')
    .replace(/```$/, '')
    .replace(/^["“”'‘’]+|["“”'‘’]+$/g, '')
    .trim()
}

function nfEscapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function nfExtractLabeledValue(block: string, labels: string[], allLabels: string[]): string {
  const labelPattern = labels.map(nfEscapeRegExp).join('|')
  const stopPattern = allLabels.map(nfEscapeRegExp).join('|')
  const re = new RegExp(
    `(?:^|\\n)\\s*(?:${labelPattern})\\s*[：:]?\\s*([\\s\\S]*?)(?=\\n\\s*(?:${stopPattern})\\s*[：:]|$)`,
    'i',
  )
  const match = block.match(re)
  return nfCleanPatchText(match?.[1] || '')
}

function nfSplitSuggestionBlocks(text: string): string[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let current: string[] = []
  const startRe = /^\s*(?:建议\s*#?\s*\d+|第\s*\d+\s*条|#\s*\d+|\d+[.、)）])/

  for (const line of lines) {
    if (startRe.test(line) && current.join('\n').trim()) {
      blocks.push(current.join('\n'))
      current = [line]
    } else {
      current.push(line)
    }
  }
  if (current.join('\n').trim()) {
    blocks.push(current.join('\n'))
  }
  return blocks.length ? blocks : [text]
}

function nfCurrentTextPatchTarget(): { card_id?: number, field_path: string } {
  const refs = assistantStore.injectedRefs as any[]
  const excerpt = refs.find(ref => ref?.refType === 'chapter_excerpt')
  if (excerpt) {
    return { card_id: Number(excerpt.cardId) || undefined, field_path: excerpt.fieldPath || 'content' }
  }
  const card = refs.find(ref => ref?.refType === 'card')
  if (card) {
    return { card_id: Number(card.cardId) || undefined, field_path: 'content' }
  }
  return { field_path: 'content' }
}

function nfParseAssistantTextPatchBatch(text: string): any | null {
  const normalized = text.replace(/\r\n/g, '\n').trim()
  if (!normalized) return null

  const allLabels = [
    '原文', '原句', '原片段', '旧文', 'old_text', 'original_text',
    '新文', '修改后', '替换为', '建议替换', 'new_text', 'revised_text', 'replacement_text',
    '理由', '说明', '原因', 'reason', 'instruction', 'explanation',
  ]
  const blocks = nfSplitSuggestionBlocks(normalized)
  const target = nfCurrentTextPatchTarget()
  const patches = blocks.map((block, index) => {
    const oldText = nfExtractLabeledValue(
      block,
      ['原文', '原句', '原片段', '旧文', 'old_text', 'original_text'],
      allLabels,
    )
    const newText = nfExtractLabeledValue(
      block,
      ['新文', '修改后', '替换为', '建议替换', 'new_text', 'revised_text', 'replacement_text'],
      allLabels,
    )
    const instruction = nfExtractLabeledValue(
      block,
      ['理由', '说明', '原因', 'reason', 'instruction', 'explanation'],
      allLabels,
    )
    if (!oldText || !newText) return null
    return {
      id: index + 1,
      index: index + 1,
      card_id: target.card_id,
      field_path: target.field_path,
      old_text: oldText,
      original_text: oldText,
      new_text: newText,
      instruction,
      status: 'pending',
    }
  }).filter(Boolean)

  if (!patches.length) return null
  return {
    success: true,
    kind: 'assistant_text_patch_batch',
    status: 'text_patch_batch_proposed',
    card_id: target.card_id,
    field_path: target.field_path,
    count: patches.length,
    patches,
    preview_only: true,
    needs_user_accept: true,
    source: 'assistant_text_parse',
  }
}

function nfLooksLikeTextPatchSuggestions(text: string): boolean {
  return /(?:原文|原句|原片段|旧文|old_text|original_text)/i.test(text) &&
    /(?:新文|修改后|替换为|建议替换|new_text|revised_text|replacement_text)/i.test(text)
}

function nfMaybeDispatchTextPatchBatchFromMessage(targetIdx: number): boolean {
  const msg = messages.value[targetIdx]
  if (!msg || msg.role !== 'assistant') return false

  const messageAny = msg as any
  if (messageAny._nfPatchBatchDispatched) return true

  const parsed = nfParseAssistantTextPatchBatch(msg.content || '')
  if (parsed) {
    const count = nfDispatchAssistantTextPatchBatch(parsed)
    messageAny._nfPatchBatchDispatched = count > 0
    if (count > 0) {
      ElMessage.success(`已解析 ${count} 条文本修改建议到当前正文编辑器`)
      return true
    }
  } else if (nfLooksLikeTextPatchSuggestions(msg.content || '')) {
    ElMessage.warning('检测到修改建议文本，但未能解析为“原文/新文/理由”结构；请让助手按该格式重新输出，或启用支持工具调用的模型配置。')
  }
  return false
}
/* NF_ASSISTANT_BATCH_PATCH_END */


function handleToolsExecuted(targetIdx: number, tools: Array<{tool_name: string, result: any}>) {
  console.log('🔧 工具已执行:', targetIdx, tools)

  const msg = messages.value[targetIdx]
  if (!msg || msg.role !== 'assistant') return


  const nfPatchBatchTools = tools
    .map(t => t?.result)
    .filter(result => nfIsAssistantTextPatchBatch(result))
  if (nfPatchBatchTools.length) {
    nfStoreAssistantTextPatchBatches(msg, nfPatchBatchTools)
  }
// 刷新左侧卡片树（如果有卡片被创建或修改）
  const needsRefresh = tools.some(t => {
    const toolName = t.tool_name
    const result = t.result

    // 这些工具调用后需要刷新卡片列表
    const refreshTools = ['create_card', 'modify_card_field', 'batch_create_cards', 'replace_field_text', 'replace_card_text_by_lines']

    if (refreshTools.includes(toolName)) {
      console.log(`🔄 检测到 ${toolName} 调用，准备刷新卡片列表`)
      return true
    }

    // 或者有 card_id 字段的结果
    if (result?.card_id) {
      console.log(`🔄 检测到 card_id: ${result.card_id}，准备刷新卡片列表`)
      return true
    }

    return false
  })

  if (needsRefresh && projectStore.currentProject?.id) {
    const cardStore = useCardStore()
    console.log('🔄 开始刷新卡片列表...')
    // 刷新整个卡片列表
    cardStore.fetchCards(projectStore.currentProject.id).then(() => {
      console.log('✅ 卡片列表刷新完成')
    }).catch((err) => {
      console.error('❌ 卡片列表刷新失败:', err)
    })
  }

  // 显示通知
  const successTools = tools.filter(t => t.result?.success)
  if (successTools.length > 0) {
    ElMessage.success(`✅ 已执行 ${successTools.length} 个操作`)
  }

  const failedTools = tools.filter(t => t.result?.success === false || t.result?.error)
  if (failedTools.length > 0) {
    const first = failedTools[0]
    const message = first.result?.message || first.result?.error || `${first.tool_name || '工具'} 调用失败`
    ElMessage.error(String(message))
  }
}

// 消息变化时自动保存（防抖，避免频繁保存）
// 优化：仅监听数组长度和最后一条消息，避免深度监听导致性能问题
let saveDebounceTimer: any = null
watch([
  () => messages.value.length,
  () => messages.value[messages.value.length - 1]?.content
], () => {
  if (messages.value.length > 0) {
    // 清除之前的定时器
    if (saveDebounceTimer) clearTimeout(saveDebounceTimer)
    // 300ms 后保存
    saveDebounceTimer = setTimeout(() => {
      saveCurrentSession()
    }, 300)
  }
})

onBeforeUnmount(() => {
  if (saveDebounceTimer) {
    clearTimeout(saveDebounceTimer)
    saveDebounceTimer = null
  }
})
</script>

<style scoped>
.assistant-panel {
  display: flex; 
  flex-direction: column; 
  height: 100%; 
  font-size: 13px;
  --nf-assistant-font-size: 16px;
  --nf-assistant-line-height: 1.65;
  font-family:"Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
.panel-header { display: flex; flex-direction: column; gap: 8px; padding: 8px; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-bg-color); }
.header-title-row { 
  display: flex; 
  align-items: center; 
  gap: 12px; 
}
.title-area {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 8px;
  overflow: hidden;
}
.main-title { 
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-size: 15px;
  flex-shrink: 0;
}
.session-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.header-controls-row { display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; overflow-x: auto; }
.panel-header .card-tag { flex-shrink: 0; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.panel-header .spacer { flex: 1; min-width: 4px; }
.ctx-tag { cursor: pointer; flex-shrink: 0; font-size: 12px; }
.header-controls-row .el-button { flex-shrink: 0; padding: 3px 6px; font-size: 12px; }
.ctx-preview { max-height: 40vh; overflow: auto; white-space: pre-wrap; background: var(--el-bg-color); color: var(--el-text-color-primary); padding: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.chat-area { flex: 1; display: flex; flex-direction: column; gap: 6px; overflow: hidden; padding: 6px 8px; }
.streaming-tip { color: var(--el-text-color-secondary); padding-left: 4px; font-size: var(--nf-assistant-font-size); line-height: var(--nf-assistant-line-height); }
.composer { 
  display: flex; 
  flex-direction: column; 
  gap: 6px; 
  padding: 10px; 
  border-top: 1px solid var(--el-border-color-light); 
}

/* 引用卡片工具栏 - 固定高度，更紧凑 */
.inject-toolbar { 
  display: flex; 
  align-items: flex-start; 
  justify-content: space-between; 
  gap: 8px; 
  padding-bottom: 6px; 
  min-height: 28px;
  max-height: 64px; /* 稍微增加高度容纳两行 + 间距 */
}

.inject-toolbar .chips { 
  display: flex; 
  align-items: flex-start; /* 改为顶部对齐 */
  gap: 6px; 
  flex: 1;
  overflow: hidden;
  max-height: 58px; /* 限制最多两行（24px×2 + 6px间距 + 4px余量） */
}

/* 标签显示区（可换行，整齐排列） */
.chips-tags {
  display: flex;
  align-items: flex-start; /* 顶部对齐 */
  gap: 6px; /* 统一间距 */
  row-gap: 6px; /* 行间距 */
  flex-wrap: wrap;
  flex: 1;
  overflow: hidden;
  line-height: 1.2;
  align-content: flex-start; /* 多行时从顶部开始排列 */
  min-height: 24px; /* 至少一行的高度 */
}

/* 更多按钮区（固定显示） */
.chips-more {
  flex-shrink: 0; /* 不允许收缩 */
  display: flex;
  align-items: flex-start; /* 与标签顶部对齐 */
  padding-top: 2px; /* 微调对齐 */
}

.chip-tag { 
  cursor: pointer;
  font-size: 12px !important;
  height: 24px !important;
  line-height: 22px !important;
  padding: 0 8px !important;
  margin: 0; /* 移除上下边距，使用 gap 统一间距 */
  flex-shrink: 0; /* 防止标签被压缩 */
  white-space: nowrap; /* 防止标签内文字换行 */
}

/* 输入框样式 */
.composer-input {
  flex: 1;
  min-height: 90px;
}

::deep(.composer-input .el-textarea__inner) {
  min-height: 90px !important;
  font-size: var(--nf-assistant-font-size);
  line-height: var(--nf-assistant-line-height);
}

::deep(.composer-input .el-textarea__inner::placeholder) {
  font-size: var(--nf-assistant-font-size);
}

.more-refs-btn {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
  padding: 0 10px !important;
  height: 24px !important;
  line-height: 22px !important;
  border: 1px dashed var(--el-color-primary);
  border-radius: 4px;
  flex-shrink: 0;
  margin: 0; /* 与标签对齐 */
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.more-refs-btn:hover {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.more-refs-dots {
  font-weight: 700;
  letter-spacing: 1px;
}

.more-refs-count {
  font-size: 11px;
  font-weight: 500;
  opacity: 0.85;
}

/* 添加引用按钮 */
.add-ref-btn {
  flex-shrink: 0;
  align-self: flex-start; /* 顶部对齐 */
  margin-top: 2px; /* 微调对齐 */
}

/* 更多引用 Popover */
.more-refs-popover {
  padding: 0;
}

.popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.popover-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: normal;
}

.more-refs-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
  padding: 8px;
}

.more-ref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  transition: all 0.2s;
}

.more-ref-item:hover {
  background: var(--el-fill-color);
}

.more-ref-item .ref-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.more-ref-item .ref-info:hover {
  color: var(--el-color-primary);
}

.composer-subbar { 
  display: flex; 
  align-items: center; 
  gap: 8px; 
  padding: 2px 0;
}

.composer-actions { 
  display: flex; 
  gap: 6px; 
  justify-content: flex-end; 
  flex-wrap: nowrap; 
  align-items: center; 
  padding: 4px 0 0 0;
  width: 100%;
}

::deep(.composer .el-button) { padding: 6px 8px; font-size: 12px; }
::deep(.inject-toolbar .el-button) { padding: 4px 8px !important; font-size: 12px; height: 24px; }

.chat-area :deep(.msg-bubble),
.chat-area :deep(.bubble-markdown),
.chat-area :deep(.bubble-markdown p),
.chat-area :deep(.bubble-markdown li),
.chat-area :deep(.bubble-markdown blockquote),
.chat-area :deep(.bubble-markdown span),
.chat-area :deep(.bubble-markdown strong),
.chat-area :deep(.bubble-markdown em),
.chat-area :deep(.thinking-content),
.chat-area :deep(.thinking-content .bubble-markdown),
.chat-area :deep(.tool-result),
.chat-area :deep(.tools-progress-text) {
  font-size: var(--nf-assistant-font-size);
  line-height: var(--nf-assistant-line-height);
}

.chat-area :deep(.thinking-title) {
  font-size: max(14px, calc(var(--nf-assistant-font-size) - 1px));
}

/* 历史对话抽屉样式 */
.history-drawer-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}

.history-actions {
  padding: 0 0 8px 0;
}

.empty-history {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
}

.history-item {
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-light);
  cursor: pointer;
  transition: all 0.2s;
}

.history-item:hover {
  background: var(--el-fill-color-light);
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.history-item.is-current {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-7);
}

.history-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.history-icon {
  color: var(--el-color-primary);
  font-size: 16px;
  flex-shrink: 0;
}

.history-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.history-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}


:deep(.el-thinking .trigger) {
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
}

</style> 
