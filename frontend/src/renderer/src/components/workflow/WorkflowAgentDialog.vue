<template>
  <div class="workflow-agent-widget" :style="widgetStyle" ref="widgetRef">
    <div v-if="!visible" class="agent-trigger" @mousedown="handleMouseDown" @click="handleTriggerClick">
      <el-icon class="trigger-icon"><MagicStick /></el-icon>
      <span class="trigger-label">工作流智能体</span>
      <el-badge v-if="pendingPatchOps.length" :value="pendingPatchOps.length" class="trigger-badge" />
    </div>

    <div v-if="visible" class="agent-window" :class="{ 'is-collapsed': collapsed }" :style="windowStyle" @mousedown.stop>
      <div class="window-header" @mousedown.stop>
        <div class="window-title" @mousedown="handleWindowMouseDown">
          <span>{{ collapsed ? '工作流Agent' : '工作流智能体' }}</span>
          <el-tag v-if="!collapsed" size="small" type="info">工作流 #{{ props.workflowId || '-' }}</el-tag>
        </div>
        <div class="window-actions">
          <el-button size="small" text @click="toggleCollapsed">
            {{ collapsed ? '展开' : '折叠' }}
          </el-button>
          <el-button size="small" text @click="handleCloseWindow">关闭</el-button>
        </div>
      </div>

      <div v-show="!collapsed" class="window-toolbar">
        <el-select
          v-model="selectedLlmId"
          filterable
          placeholder="选择模型"
          size="small"
          style="width: 220px"
          popper-class="workflow-agent-popper"
          :teleported="true"
          :loading="llmLoading"
          :disabled="llmLoading || !llmOptions.length"
        >
          <el-option
            v-for="item in llmOptions"
            :key="item.id"
            :label="item.display_name || item.model_name"
            :value="item.id"
          />
          <el-option v-if="!llmLoading && !llmOptions.length" label="暂无可用模型" :value="-1" disabled />
        </el-select>

        <el-select
          v-model="mode"
          size="small"
          style="width: 150px"
          popper-class="workflow-agent-popper"
          :teleported="true"
        >
          <el-option label="建议模式" value="suggest" />
        </el-select>

        <el-switch
          v-model="thinkingEnabled"
          size="small"
          inline-prompt
          active-text="思考"
          inactive-text="思考"
        />

        <el-tag v-if="pendingPatchOps.length" size="small" type="success">{{ pendingPatchOps.length }} 个操作</el-tag>
      </div>

      <div v-show="!collapsed" class="window-body">
        <agent-message-list
          ref="messageListRef"
          :messages="messages"
          :streaming="streaming"
          empty-description="请描述你希望的工作流改动目标，我会先给出补丁预览。"
        />

        <div class="patch-panel" v-if="pendingPatchOps.length || pendingDiff">
          <div class="patch-title-row">
            <div class="patch-title-meta">
              <span class="patch-title">补丁预览</span>
              <el-tag size="small" type="success">{{ pendingPatchOps.length }} 个操作</el-tag>
            </div>
            <el-button size="small" text @click="patchPreviewExpanded = !patchPreviewExpanded">
              {{ patchPreviewExpanded ? '收起预览' : '展开预览' }}
            </el-button>
          </div>

          <div class="patch-ops" v-show="patchPreviewExpanded">
            <el-tag v-for="(op, idx) in pendingPatchOps" :key="`op-${idx}`" size="small" effect="plain">
              {{ op.op }}
            </el-tag>
          </div>

          <el-input
            v-show="patchPreviewExpanded"
            v-model="pendingDiff"
            type="textarea"
            :rows="8"
            readonly
            placeholder="暂无 diff 预览"
          />

          <div class="patch-actions" v-show="patchPreviewExpanded">
            <el-button
              size="small"
              type="primary"
              :disabled="!canApplyPatch"
              :loading="applyingPatch"
              @click="confirmApplyPatch"
            >应用补丁</el-button>
            <el-button size="small" @click="clearPendingPatch">清空补丁</el-button>
          </div>

          <div v-if="lastPatchError" class="patch-error">{{ lastPatchError }}</div>
        </div>

        <div class="agent-footer">
          <AgentComposer
            v-model="draft"
            :rows="3"
            resize="none"
            placeholder="例如：在大纲节点后新增结构化节点，并输出到项目A"
            :disabled="streaming"
            @keydown="handleEnterSend"
          >
            <template #actions>
              <div class="footer-actions">
                <el-button size="small" @click="suggestFixForValidation" :disabled="!lastValidationFailed">
                  让智能体修复校验问题
                </el-button>
                <el-button v-if="!streaming" type="primary" size="small" :disabled="!canSend" @click="sendMessage">
                  发送
                </el-button>
                <el-button v-else type="danger" size="small" :icon="VideoPause" @click="handleStopStreaming">
                  中止
                </el-button>
              </div>
            </template>
          </AgentComposer>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, VideoPause } from '@element-plus/icons-vue'

import AgentMessageList from '@/components/shared/AgentMessageList.vue'
import AgentComposer from '@/components/shared/AgentComposer.vue'
import { applyAgentStreamEvent, ensureAssistantMessage } from '@/composables/agentChatEvents'
import { useEnterToSend } from '@/composables/useEnterToSend'
import { useMessageListScroll } from '@/composables/useMessageListScroll'
import type { AgentChatMessage } from '@/types/agentChat'
import { useAgentPreferences } from '@/composables/useAgentPreferences'
import { listLLMConfigs, type LLMConfigRead } from '@/api/setting'
import {
  applyWorkflowPatch,
  workflowAgentChatStreaming,
  type WorkflowAgentMode,
  type WorkflowPatchOp,
} from '@/api/workflowAgent'

const props = defineProps<{
  workflowId: number | null
  revision: string
}>()

const emit = defineEmits<{
  (e: 'applied', payload: { newCode: string; newRevision?: string }): void
}>()

const visible = ref(false)
const collapsed = ref(false)
const draft = ref('')
const streaming = ref(false)
const mode = ref<WorkflowAgentMode>('suggest')
const thinkingEnabled = ref(false)
const messages = ref<AgentChatMessage[]>([])

const llmOptions = ref<LLMConfigRead[]>([])
const selectedLlmId = ref<number | null>(null)
const llmLoading = ref(false)

const pendingPatchOps = ref<WorkflowPatchOp[]>([])
const pendingDiff = ref('')
const lastPatchError = ref('')
const patchPreviewExpanded = ref(false)
const applyingPatch = ref(false)
const lastValidationFailed = ref(false)
const previewSeq = ref(0)
const lastPatchFingerprint = ref('')
const streamCancelRef = ref<null | (() => void)>(null)

const revisionRef = ref(props.revision || '')

const canSend = computed(() => Boolean(props.workflowId && selectedLlmId.value && draft.value.trim().length > 0 && !streaming.value))
const canApplyPatch = computed(() => Boolean(props.workflowId && pendingPatchOps.value.length && revisionRef.value))

const { messageListRef, scrollToBottom } = useMessageListScroll()
const widgetRef = ref<HTMLElement | null>(null)
const agentPrefs = useAgentPreferences()

const position = ref<{ left: number; top: number } | null>(null)
const dragState = ref({ startX: 0, startY: 0, startLeft: 0, startTop: 0, dragging: false })

const windowPosition = ref<{ left: number; top: number } | null>(null)
const windowDragState = ref({ startX: 0, startY: 0, startLeft: 0, startTop: 0, dragging: false })

const widgetStyle = computed(() => {
  const base: Record<string, any> = {}
  if (position.value) {
    base.left = `${position.value.left}px`
    base.top = `${position.value.top}px`
    base.right = 'auto'
    base.bottom = 'auto'
  }
  return base
})

const windowStyle = computed(() => {
  const base: Record<string, any> = {}
  if (windowPosition.value) {
    base.left = `${windowPosition.value.left}px`
    base.top = `${windowPosition.value.top}px`
    base.right = 'auto'
    base.bottom = 'auto'
  }
  return base
})

watch(() => props.revision, value => {
  revisionRef.value = value || ''
})

watch(() => props.workflowId, () => {
  clearConversationState()
})

watch(visible, open => {
  if (!open) return
  clearConversationState()
  if (!llmOptions.value.length && !llmLoading.value) {
    void loadLlmOptions()
  }
})

function clearConversationState() {
  previewSeq.value += 1
  streamCancelRef.value?.()
  streamCancelRef.value = null
  messages.value = []
  pendingPatchOps.value = []
  pendingDiff.value = ''
  lastPatchError.value = ''
  applyingPatch.value = false
  streaming.value = false
  lastValidationFailed.value = false
  lastPatchFingerprint.value = ''
}

function handleStopStreaming() {
  streamCancelRef.value?.()
  streamCancelRef.value = null
  streaming.value = false
}

function clearPendingPatch() {
  previewSeq.value += 1
  pendingPatchOps.value = []
  pendingDiff.value = ''
  lastPatchError.value = ''
  patchPreviewExpanded.value = false
  lastValidationFailed.value = false
  lastPatchFingerprint.value = ''
}

function normalizePatchOps(payload: any): WorkflowPatchOp[] {
  if (payload && typeof payload === 'object' && typeof payload.new_code === 'string' && !payload.patch_ops) {
    return [{
      op: 'replace_code',
      new_code: payload.new_code,
      reason: 'fallback_replace_code',
    }]
  }

  const ops = Array.isArray(payload?.patch_ops)
    ? payload.patch_ops
    : Array.isArray(payload)
      ? payload
      : []

  if (!ops.length) return []

  return ops
    .map((item: any) => {
      const raw = item || {}
      const rawOp = typeof raw.op === 'string' ? raw.op.trim() : ''
      const op = (rawOp === 'replace' || rawOp === 'replace_all' || rawOp === 'full_replace' || rawOp === 'replace_workflow')
        ? 'replace_code'
        : rawOp

      if (op === 'replace_code') {
        const fullCode = raw.new_code || raw.code || raw.full_code || raw.new_block
        return {
          ...raw,
          op,
          new_code: typeof fullCode === 'string' ? fullCode : raw.new_code,
        }
      }

      return {
        ...raw,
        op,
      }
    })
    .filter((item: any) => {
      if (typeof item.op !== 'string' || item.op.length === 0) {
        return false
      }
      if (item.op === 'replace_code') {
        return typeof item.new_code === 'string' && item.new_code.trim().length > 0
      }
      return true
    })
}

function buildPatchFingerprint(ops: WorkflowPatchOp[]): string {
  return `${revisionRef.value}::${JSON.stringify(ops)}`
}

async function setPendingPatchOps(ops: WorkflowPatchOp[], options?: { preview?: boolean }) {
  if (!ops.length) {
    pendingPatchOps.value = []
    pendingDiff.value = ''
    return
  }

  previewSeq.value += 1

  const fingerprint = buildPatchFingerprint(ops)
  if (fingerprint === lastPatchFingerprint.value) {
    return
  }

  lastPatchFingerprint.value = fingerprint
  pendingPatchOps.value = ops
  patchPreviewExpanded.value = false
  lastPatchError.value = ''

  if (options?.preview !== false) {
    await previewPatchDryRun()
  }
}

async function previewPatchDryRun() {
  const workflowId = props.workflowId
  if (!workflowId || !pendingPatchOps.value.length || !revisionRef.value) {
    return
  }

  const seq = ++previewSeq.value
  try {
    const result = await applyWorkflowPatch(workflowId, {
      base_revision: revisionRef.value,
      patch_ops: pendingPatchOps.value,
      dry_run: true,
    })

    if (seq !== previewSeq.value) {
      return
    }

    pendingDiff.value = result.diff || ''
    lastValidationFailed.value = !Boolean(result.validation?.is_valid)
    if (!result.success) {
      if (result.error === 'revision_mismatch' && typeof (result as any).current_revision === 'string' && (result as any).current_revision.trim()) {
        revisionRef.value = (result as any).current_revision
        await previewPatchDryRunOnce()
        return
      }
      if (result.error === 'revision_mismatch') {
        lastPatchError.value = '代码已在后台更新，已为你同步到最新版本，请重试。'
      } else {
        lastPatchError.value = result.error || (result.validation?.is_valid ? '' : '校验未通过')
      }
    } else {
      lastPatchError.value = ''
    }
  } catch (error: any) {
    if (seq !== previewSeq.value) {
      return
    }
    const detail = error?.response?.data?.detail
    if (detail?.code === 'revision_mismatch') {
      if (typeof detail?.current_revision === 'string' && detail.current_revision.trim()) {
        revisionRef.value = detail.current_revision
        await previewPatchDryRunOnce()
        return
      }
      lastPatchError.value = '代码已在后台更新，已为你同步到最新版本，请重试。'
    } else {
      lastPatchError.value = detail?.message || detail || error?.message || '补丁预览失败'
    }
  }
}

async function previewPatchDryRunOnce() {
  const workflowId = props.workflowId
  if (!workflowId || !pendingPatchOps.value.length || !revisionRef.value) {
    return
  }
  const seq = ++previewSeq.value
  try {
    const result = await applyWorkflowPatch(workflowId, {
      base_revision: revisionRef.value,
      patch_ops: pendingPatchOps.value,
      dry_run: true,
    })
    if (seq !== previewSeq.value) return
    pendingDiff.value = result.diff || ''
    lastValidationFailed.value = !Boolean(result.validation?.is_valid)
    if (!result.success) {
      lastPatchError.value = result.error === 'revision_mismatch'
        ? '代码刚刚又被修改，请再试一次。'
        : (result.error || (result.validation?.is_valid ? '' : '校验未通过'))
    } else {
      lastPatchError.value = ''
    }
  } catch (error: any) {
    if (seq !== previewSeq.value) return
    const detail = error?.response?.data?.detail
    if (detail?.code === 'revision_mismatch') {
      lastPatchError.value = '代码刚刚又被修改，请再试一次。'
    } else {
      lastPatchError.value = detail?.message || detail || error?.message || '补丁预览失败'
    }
  }
}

async function confirmApplyPatch() {
  const workflowId = props.workflowId
  if (!workflowId || !pendingPatchOps.value.length || !revisionRef.value) return

  try {
    await ElMessageBox.confirm('确认将当前补丁应用到工作流代码吗？', '应用补丁', {
      type: 'warning',
      confirmButtonText: '确认应用',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  applyingPatch.value = true
  try {
    const result = await applyWorkflowPatch(workflowId, {
      base_revision: revisionRef.value,
      patch_ops: pendingPatchOps.value,
      dry_run: false,
    })

    if (!result.success) {
      lastValidationFailed.value = !Boolean(result.validation?.is_valid)
      lastPatchError.value = result.error || '补丁应用失败'
      ElMessage.error(lastPatchError.value)
      return
    }

    revisionRef.value = result.new_revision || revisionRef.value
    emit('applied', { newCode: result.new_code, newRevision: result.new_revision ?? undefined })
    ElMessage.success('补丁应用成功，且校验通过')
    clearPendingPatch()
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    if (detail?.code === 'revision_mismatch') {
      if (typeof detail?.current_revision === 'string' && detail.current_revision.trim()) {
        revisionRef.value = detail.current_revision
      }
      lastPatchError.value = '代码已更新，补丁基线已自动同步，请再次点击“应用补丁”。'
      void previewPatchDryRunOnce()
    } else {
      lastPatchError.value = detail?.message || detail || error?.message || '应用补丁失败'
    }
    ElMessage.error(lastPatchError.value)
  } finally {
    applyingPatch.value = false
  }
}

const handleEnterSend = useEnterToSend({
  canSend,
  onSend: sendMessage,
  streaming,
})

function sendMessage() {
  const workflowId = props.workflowId
  if (!canSend.value || !workflowId || !selectedLlmId.value) return

  const prompt = draft.value.trim()
  const pendingCode = (() => {
    const replaceOp = [...pendingPatchOps.value]
      .reverse()
      .find(item => item?.op === 'replace_code' && typeof (item as any).new_code === 'string' && (item as any).new_code.trim().length > 0)
    if (replaceOp && typeof (replaceOp as any).new_code === 'string') {
      return (replaceOp as any).new_code
    }
    return ''
  })()
  const historyMessages = messages.value
    .slice(-20)
    .filter(message => message && typeof message.content === 'string' && message.content.trim().length > 0)
    .map(message => ({
      role: message.role,
      content: message.content,
    }))
  draft.value = ''
  messages.value.push({ role: 'user', content: prompt })
  messages.value.push({ role: 'assistant', content: '', tools: [] })
  streaming.value = true
  scrollToBottom()

  const streamHandle = workflowAgentChatStreaming(
    {
      workflow_id: workflowId,
      llm_config_id: selectedLlmId.value,
      user_prompt: prompt,
      mode: mode.value,
      temperature: agentPrefs.agentTemperature.value || undefined,
      max_tokens: agentPrefs.agentMaxTokens.value || undefined,
      timeout: agentPrefs.agentTimeout.value || undefined,
      thinking_enabled: thinkingEnabled.value,
      react_mode_enabled: agentPrefs.reactModeEnabled.value || undefined,
      history_messages: historyMessages,
      pending_code: pendingCode || undefined,
    },
    evt => {
      const target = ensureAssistantMessage(messages.value)

      applyAgentStreamEvent(target, evt, {
        trackTimeline: true,
        onToolEnd: (toolName, result) => {
          if (toolName === 'wf_apply_patch' && result && typeof result === 'object') {
            const patchResult = result as any
            if (typeof patchResult.base_revision === 'string' && patchResult.base_revision.trim()) {
              revisionRef.value = patchResult.base_revision
            }
            if (patchResult.error === 'revision_mismatch' && typeof patchResult.current_revision === 'string' && patchResult.current_revision.trim()) {
              revisionRef.value = patchResult.current_revision
            }
            const ops = normalizePatchOps(patchResult)
            const hasValidReplaceCode = ops.some((item: any) => item?.op !== 'replace_code' || (typeof item?.new_code === 'string' && item.new_code.trim().length > 0))
            if (ops.length && hasValidReplaceCode) {
              void setPendingPatchOps(ops, { preview: patchResult.error === 'revision_mismatch' })
            } else if ((patchResult?.patch_ops?.length || Array.isArray(patchResult) || patchResult?.op === 'replace_code')) {
              lastPatchError.value = patchResult?.message || '模型返回了无效补丁（replace_code 缺少 new_code），请重试。'
            }
            if (typeof patchResult.diff === 'string') {
              pendingDiff.value = patchResult.diff
            }
            if (patchResult.validation) {
              lastValidationFailed.value = !Boolean(patchResult.validation?.is_valid)
            }
            if (patchResult.error) {
              lastPatchError.value = patchResult.error === 'revision_mismatch'
                ? '代码版本已变化，已自动同步最新版本并重新预览。'
                : String(patchResult.error)
            } else if (patchResult.success) {
              lastPatchError.value = ''
            }
          }

          if (toolName === 'wf_replace_code' && result && typeof result === 'object') {
            const replaceResult = result as any
            if (typeof replaceResult.base_revision === 'string' && replaceResult.base_revision.trim()) {
              revisionRef.value = replaceResult.base_revision
            }
            if (replaceResult.error === 'revision_mismatch' && typeof replaceResult.current_revision === 'string' && replaceResult.current_revision.trim()) {
              revisionRef.value = replaceResult.current_revision
            }
            const generatedCode = typeof replaceResult.new_code === 'string' ? replaceResult.new_code : ''
            if (generatedCode.trim()) {
              void setPendingPatchOps([
                {
                  op: 'replace_code',
                  new_code: generatedCode,
                  reason: 'wf_replace_code_result',
                } as WorkflowPatchOp,
              ], { preview: false })
            } else {
              lastPatchError.value = replaceResult?.message || 'replace_code 缺少 new_code，请重试。'
            }

            if (typeof replaceResult.diff === 'string') {
              pendingDiff.value = replaceResult.diff
            }
            if (replaceResult.validation) {
              lastValidationFailed.value = !Boolean(replaceResult.validation?.is_valid)
            }
            if (replaceResult.error) {
              lastPatchError.value = replaceResult.error === 'revision_mismatch'
                ? '代码版本已变化，已自动同步最新版本并重新预览。'
                : String(replaceResult.error)
            } else if (replaceResult.success) {
              lastPatchError.value = ''
            }
          }
        },
      })

      scrollToBottom()
    },
    () => {
      streaming.value = false
      streamCancelRef.value = null
      scrollToBottom()
    },
    err => {
      streaming.value = false
      streamCancelRef.value = null
      ElMessage.error(err?.message || '工作流智能体请求失败')
    },
  )

  streamCancelRef.value = () => streamHandle.cancel()
}

function suggestFixForValidation() {
  if (!lastValidationFailed.value) return
  draft.value = '上一次补丁未通过校验，请基于 patch-first 重新生成可通过校验的 patch_ops。'
}

function clampToViewport(left: number, top: number, width: number, height: number) {
  const padding = 8
  const maxLeft = Math.max(padding, window.innerWidth - width - padding)
  const maxTop = Math.max(padding, window.innerHeight - height - padding)
  return {
    left: Math.min(Math.max(left, padding), maxLeft),
    top: Math.min(Math.max(top, padding), maxTop),
  }
}

function handleTriggerClick() {
  if (dragState.value.dragging) return
  visible.value = !visible.value
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
}

function handleCloseWindow() {
  visible.value = false
}

function onMouseMove(event: MouseEvent) {
  const dx = event.clientX - dragState.value.startX
  const dy = event.clientY - dragState.value.startY
  if (!dragState.value.dragging && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
    dragState.value.dragging = true
  }
  if (!dragState.value.dragging) return

  const el = widgetRef.value
  const width = el?.offsetWidth || 220
  const height = el?.offsetHeight || 48
  position.value = clampToViewport(
    dragState.value.startLeft + dx,
    dragState.value.startTop + dy,
    width,
    height,
  )
}

function onMouseUp() {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
  setTimeout(() => {
    dragState.value.dragging = false
  }, 0)
}

function handleMouseDown(event: MouseEvent) {
  const el = widgetRef.value
  if (!el) return

  dragState.value.dragging = false
  const rect = el.getBoundingClientRect()
  dragState.value.startLeft = rect.left
  dragState.value.startTop = rect.top
  dragState.value.startX = event.clientX
  dragState.value.startY = event.clientY

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function onWindowMouseMove(event: MouseEvent) {
  if (!windowDragState.value.dragging) {
    const dx = event.clientX - windowDragState.value.startX
    const dy = event.clientY - windowDragState.value.startY
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      windowDragState.value.dragging = true
    } else {
      return
    }
  }

  const dx = event.clientX - windowDragState.value.startX
  const dy = event.clientY - windowDragState.value.startY
  const winEl = widgetRef.value?.querySelector('.agent-window') as HTMLElement | null
  const width = winEl?.offsetWidth || 520
  const height = winEl?.offsetHeight || 640

  windowPosition.value = clampToViewport(
    windowDragState.value.startLeft + dx,
    windowDragState.value.startTop + dy,
    width,
    height,
  )
}

function onWindowMouseUp() {
  document.removeEventListener('mousemove', onWindowMouseMove)
  document.removeEventListener('mouseup', onWindowMouseUp)
  setTimeout(() => {
    windowDragState.value.dragging = false
  }, 0)
}

function handleWindowMouseDown(event: MouseEvent) {
  const el = widgetRef.value?.querySelector('.agent-window') as HTMLElement | null
  if (!el) return

  const rect = el.getBoundingClientRect()
  windowDragState.value = {
    startX: event.clientX,
    startY: event.clientY,
    startLeft: rect.left,
    startTop: rect.top,
    dragging: false,
  }

  document.addEventListener('mousemove', onWindowMouseMove)
  document.addEventListener('mouseup', onWindowMouseUp)
}

async function loadLlmOptions() {
  llmLoading.value = true
  try {
    llmOptions.value = await listLLMConfigs()
    if (!llmOptions.value.length) {
      ElMessage.warning('当前没有可用模型，请先在设置中配置 LLM。')
    }
    if (!selectedLlmId.value && llmOptions.value.length) {
      selectedLlmId.value = llmOptions.value[0].id
    }
  } catch (error: any) {
    llmOptions.value = []
    ElMessage.error(error?.message || '加载模型列表失败')
  } finally {
    llmLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', handleViewportResize)
  handleViewportResize()
  loadLlmOptions()
})

onBeforeUnmount(() => {
  streamCancelRef.value?.()
  streamCancelRef.value = null
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
  document.removeEventListener('mousemove', onWindowMouseMove)
  document.removeEventListener('mouseup', onWindowMouseUp)
  window.removeEventListener('resize', handleViewportResize)
})

function handleViewportResize() {
  if (position.value) {
    const triggerEl = widgetRef.value
    const width = triggerEl?.offsetWidth || 220
    const height = triggerEl?.offsetHeight || 48
    position.value = clampToViewport(position.value.left, position.value.top, width, height)
  }

  if (windowPosition.value) {
    const winEl = widgetRef.value?.querySelector('.agent-window') as HTMLElement | null
    const width = winEl?.offsetWidth || 520
    const height = winEl?.offsetHeight || 640
    windowPosition.value = clampToViewport(windowPosition.value.left, windowPosition.value.top, width, height)
  }
}
</script>

<style scoped>
.workflow-agent-widget {
  position: fixed;
  right: 24px;
  bottom: 24px;
  top: auto;
  z-index: 2100;
}

.agent-window {
  position: fixed;
  right: 24px;
  bottom: 88px;
  top: auto;
  width: 680px;
  min-width: 420px;
  max-width: calc(100vw - 16px);
  height: 780px;
  min-height: 420px;
  max-height: calc(100vh - 16px);
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(18px);
  box-shadow: 0 20px 56px rgba(15, 23, 42, 0.18);
  overflow: hidden;
  resize: both;
}

.agent-window.is-collapsed {
  height: auto;
  min-height: 0;
  width: 320px;
  min-width: 280px;
  max-width: min(360px, calc(100vw - 16px));
  resize: none;
}

.agent-window.is-collapsed .window-header {
  padding: 8px 10px;
}

.agent-window.is-collapsed .window-title {
  gap: 6px;
  font-size: 14px;
}

html.dark .agent-window {
  background: rgba(17, 24, 39, 0.72);
  border-color: rgba(148, 163, 184, 0.22);
}

.window-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
}

.window-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  cursor: move;
  user-select: none;
}

.window-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.window-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.window-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 10px 12px;
  gap: 10px;
}

.agent-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 20px;
  cursor: pointer;
  user-select: none;
  color: #fff;
  background: linear-gradient(120deg, #7c3aed, #2563eb);
  box-shadow: 0 10px 28px rgba(59, 130, 246, 0.35);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.agent-trigger:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 32px rgba(99, 102, 241, 0.45);
}

.trigger-icon {
  font-size: 16px;
}

.trigger-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.trigger-badge {
  margin-left: 4px;
}

.patch-panel {
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  padding: 10px;
  background: var(--el-fill-color-extra-light);
}

.patch-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.patch-title-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.patch-title {
  font-size: 13px;
  font-weight: 600;
}

.patch-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.patch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.patch-error {
  margin-top: 8px;
  color: var(--el-color-danger);
  font-size: 12px;
}

.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

:global(.workflow-agent-popper) {
  z-index: 4005 !important;
}
</style>
