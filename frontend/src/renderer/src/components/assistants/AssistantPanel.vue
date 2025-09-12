<template>
  <div class="assistant-panel">
    <div class="panel-header">
      <span class="title">灵感助手</span>
      <el-tag v-if="currentCardTitle" size="small" type="info" class="card-tag" effect="plain">{{ currentCardTitle }}</el-tag>
      <div class="spacer"></div>
      <el-switch v-model="injectContentJson" active-text="卡片数据" inline-prompt size="small" />
      <el-button size="small" text type="danger" @click="$emit('reset-selection')">重置选中</el-button>
      <el-button size="small" @click="$emit('refresh-context')">刷新上下文</el-button>
      <el-popover placement="bottom" width="480" trigger="hover">
        <template #reference>
          <el-tag type="info" class="ctx-tag">上下文预览</el-tag>
        </template>
        <pre class="ctx-preview">{{ (resolvedContext || '').slice(0, 3000) }}</pre>
      </el-popover>
    </div>

    <div class="chat-area">
      <div class="messages" ref="messagesEl">
        <div v-for="(m, idx) in messages" :key="idx" :class="['msg', m.role]">
          <div class="bubble">
            <pre class="bubble-text">{{ m.content }}</pre>
          </div>
        </div>
      </div>
      <div v-if="isStreaming" class="streaming-tip">正在生成中…</div>
    </div>

    <div class="composer">
      <el-input v-model="draft" type="textarea" :rows="3" placeholder="输入你的想法、约束或追问" :disabled="isStreaming" />
      <div class="composer-actions">
        <el-button @click="handleReset" :disabled="isStreaming">重置对话</el-button>
        <el-button :disabled="!isStreaming" @click="handleCancel">中止</el-button>
        <el-button :disabled="!canRegenerate" @click="handleRegenerate">重新生成</el-button>
        <el-button type="success" :disabled="isStreaming || !messages.length" @click="handleFinalize">定稿生成</el-button>
        <el-button type="primary" :disabled="isStreaming || !canSend" @click="handleSend">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue'
import { generateContinuationStreaming, renderPromptWithKnowledge } from '@renderer/api/ai'

const props = defineProps<{ resolvedContext: string; llmConfigId?: number | null; promptName?: string | null; temperature?: number | null; max_tokens?: number | null; timeout?: number | null; effectiveSchema?: any; generationPromptName?: string | null; currentCardTitle?: string | null; currentCardContent?: any }>()
const emit = defineEmits<{ 'finalize': [string]; 'refresh-context': []; 'reset-selection': [] }>()

const messages = ref<Array<{ role: 'user' | 'assistant'; content: string }>>([])
const draft = ref('')
const isStreaming = ref(false)
let streamCtl: { cancel: () => void } | null = null
const messagesEl = ref<HTMLDivElement | null>(null)

const lastRun = ref<{ prev: string; tail: string; targetIdx: number } | null>(null)
const canRegenerate = computed(() => !isStreaming.value && !!lastRun.value && messages.value[lastRun.value.targetIdx]?.role === 'assistant')

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

const canSend = computed(() => !!draft.value.trim() && !!props.llmConfigId)

// === 注入内容JSON 开关（默认开启，记忆到本地存储） ===
const LS_KEY_INJECT = 'nf.assistant.injectContentJson'
const initialInject = (() => { try { const raw = localStorage.getItem(LS_KEY_INJECT); return raw === null ? true : raw === '1' } catch { return true } })()
const injectContentJson = ref<boolean>(initialInject)
watch(injectContentJson, (v) => { try { localStorage.setItem(LS_KEY_INJECT, v ? '1' : '0') } catch {} })

// 已移除复杂剪裁工具，仅保留屏蔽 x-ai-exclude 的最小逻辑

function buildConversationText() { return messages.value.map(m => (m.role === 'user' ? `用户: ${m.content}` : `助手: ${m.content}`)).join('\n') }

function maskBySchema(value: any, schema: any): any {
  if (value === null || value === undefined) return value
  const t = typeof value
  if (t !== 'object') return value
  if (Array.isArray(value)) {
    const schItems = (schema && (schema.items || schema.prefixItems)) || {}
    return (value as any[]).map((it) => maskBySchema(it, schItems))
  }
  const schProps = (schema && schema.properties) || {}
  const out: Record<string, any> = {}
  for (const [k, v] of Object.entries(value as Record<string, any>)) {
    const propSchema = schProps[k] || {}
    if (propSchema && propSchema['x-ai-exclude'] === true) continue
    out[k] = maskBySchema(v, propSchema)
  }
  return out
}

function buildDraftTail() {
  const parts: string[] = []
  if (injectedCardPrompt.value) parts.push(`【卡片提示词】\n${injectedCardPrompt.value}`)
  if (props.effectiveSchema) { try { parts.push(`【JSON Schema】\n\n\`\`\`json\n${JSON.stringify(props.effectiveSchema, null, 2)}\n\`\`\``) } catch {} }
  // 注入“卡片数据（JSON，仅供参考）”：直接拼接，尊重 x-ai-exclude，整体限长
  if (injectContentJson.value && props.currentCardContent) {
    try {
      const masked = props.effectiveSchema ? maskBySchema(props.currentCardContent, props.effectiveSchema) : props.currentCardContent
      const jsonText = JSON.stringify(masked ?? {}, null, 2)
      // 限长保护（整体最长注入约 8000 字符）
      const clipped = jsonText.length > 8000 ? jsonText.slice(0, 8000) + '\n/* 其余已截断 */' : jsonText
      parts.push(`【该卡片已有数据（仅供参考）】\n\n\`\`\`json\n${clipped}\n\`\`\``)
    } catch {}
  }
  const activeCtx = props.resolvedContext || ''
  if (activeCtx) parts.push(`【上下文】\n${activeCtx}`)
  const convo = buildConversationText()
  if (convo) parts.push(`【对话历史（请结合最新反馈调整你的回答）】\n${convo}`)
  return parts.join('\n\n')
}

function scrollToBottom() { nextTick(() => { try { const el = messagesEl.value; if (el) el.scrollTop = el.scrollHeight } catch {} }) }

function startStreaming(prev: string, tail: string, targetIdx: number) {
  isStreaming.value = true
  streamCtl = generateContinuationStreaming({
    previous_content: prev,
    llm_config_id: props.llmConfigId as number,
    prompt_name: (props.promptName && props.promptName.trim()) ? props.promptName : '灵感对话',
    stream: true,
    temperature: props.temperature ?? undefined,
    max_tokens: props.max_tokens ?? undefined,
    timeout: props.timeout ?? undefined,
    current_draft_tail: tail,
    append_continuous_novel_directive: false,
  }, (chunk) => {
    messages.value[targetIdx].content += chunk
    scrollToBottom()
  }, () => { isStreaming.value = false; streamCtl = null }, () => { isStreaming.value = false; streamCtl = null }) as any
}

function handleSend() {
  if (!canSend.value || isStreaming.value) return
  lastRun.value = null
  const userText = draft.value.trim(); if (!userText) return
  messages.value.push({ role: 'user', content: userText })
  draft.value = ''
  scrollToBottom()

  const previous_content = buildConversationText()
  const current_draft_tail = buildDraftTail()
  const assistantIdx = messages.value.push({ role: 'assistant', content: '' }) - 1
  scrollToBottom()
  lastRun.value = { prev: previous_content, tail: current_draft_tail, targetIdx: assistantIdx }
  startStreaming(previous_content, current_draft_tail, assistantIdx)
}

function handleCancel() { try { streamCtl?.cancel() } catch {}; isStreaming.value = false }
function handleRegenerate() { if (!canRegenerate.value || !lastRun.value) return; messages.value[lastRun.value.targetIdx].content = ''; scrollToBottom(); startStreaming(lastRun.value.prev, lastRun.value.tail, lastRun.value.targetIdx) }
function handleFinalize() { const summary = (() => { const last = [...messages.value].reverse().find(m => m.role === 'assistant'); return (last?.content || '').trim() || buildConversationText() })(); emit('finalize', summary) }
function handleReset() { try { streamCtl?.cancel() } catch {}; isStreaming.value = false; messages.value = []; draft.value = ''; lastRun.value = null; scrollToBottom() }
</script>

<style scoped>
.assistant-panel { display: flex; flex-direction: column; height: 100%; font-size: 13px; }
.panel-header { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-bg-color); }
.panel-header .title { font-weight: 600; color: var(--el-text-color-primary); font-size: 14px; }
.panel-header .card-tag { margin-left: 8px; }
.panel-header .spacer { flex: 1; }
.ctx-tag { cursor: pointer; }
.ctx-preview { max-height: 40vh; overflow: auto; white-space: pre-wrap; background: var(--el-bg-color); color: var(--el-text-color-primary); padding: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.chat-area { flex: 1; display: flex; flex-direction: column; gap: 6px; overflow: hidden; padding: 6px 8px; }
.messages { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); }
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.bubble { max-width: 80%; padding: 8px 10px; border-radius: 8px; }
.bubble-text { margin: 0; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: var(--el-text-color-primary); }
.msg.assistant .bubble { background: var(--el-bg-color); border: 1px solid var(--el-border-color); }
.msg.user .bubble { background: var(--el-color-primary); color: var(--el-color-white); }
.msg.user .bubble-text { color: var(--el-color-white); }
.streaming-tip { color: var(--el-text-color-secondary); padding-left: 4px; font-size: 12px; }
.composer { display: flex; flex-direction: column; gap: 6px; padding: 6px 8px; border-top: 1px solid var(--el-border-color-light); }
.composer-actions { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: nowrap; }
:deep(.composer .el-button) { padding: 6px 8px; font-size: 12px; }
</style> 