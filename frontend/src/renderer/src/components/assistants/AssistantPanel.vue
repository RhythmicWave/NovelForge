<template>
  <div class="assistant-panel">
    <div class="panel-header">
      <div class="header-title-row">
        <span class="title">灵感助手</span>
      </div>
      <div class="header-controls-row">
        <el-tag v-if="currentCardTitle" size="small" type="info" class="card-tag" effect="plain">{{ currentCardTitle }}</el-tag>
        <div class="spacer"></div>
        <el-button size="small" text type="danger" @click="$emit('reset-selection')">重置</el-button>
        <el-button size="small" @click="$emit('refresh-context')">刷新</el-button>
        <el-popover placement="bottom" width="480" trigger="hover">
          <template #reference>
            <el-tag type="info" class="ctx-tag" size="small">预览上下文</el-tag>
          </template>
          <pre class="ctx-preview">{{ (resolvedContext || '') }}</pre>
        </el-popover>
      </div>
    </div>

    <div class="chat-area">
      <div class="messages" ref="messagesEl">
        <div v-for="(m, idx) in messages" :key="idx" :class="['msg', m.role]">
          <div class="bubble">
            <pre class="bubble-text">{{ m.content }}</pre>
          </div>
          <div v-if="m.role==='assistant'" class="msg-toolbar">
            <el-button :icon="Refresh" circle size="small" :disabled="isStreaming" @click="handleRegenerateAt(idx)" title="重新生成" />
            <el-button :icon="DocumentCopy" circle size="small" :disabled="isStreaming || !m.content" @click="handleCopy(idx)" title="复制内容" />
          </div>
        </div>
      </div>
      <div v-if="isStreaming" class="streaming-tip">正在生成中…</div>
    </div>

    <div class="composer">
      <div class="inject-toolbar">
        <div class="chips">
          <el-tag v-for="(r, idx) in assistantStore.injectedRefs" :key="r.projectId + '-' + r.cardId" closable @close="removeInjectedRef(idx)" size="small" effect="plain" class="chip-tag" @click="onChipClick(r)">
            {{ r.projectName }} / {{ r.cardTitle }}
          </el-tag>
        </div>
        <el-button size="small" :icon="Plus" @click="openInjectSelector">添加引用</el-button>
      </div>
      <div class="composer-subbar">
        <el-select v-model="overrideLlmId" placeholder="选择模型" size="small" style="width: 200px">
          <el-option v-for="m in llmOptions" :key="m.id" :label="(m.display_name || m.model_name)" :value="m.id" />
        </el-select>
      </div>
      <el-input v-model="draft" type="textarea" :rows="3" placeholder="输入你的想法、约束或追问" :disabled="isStreaming" @keydown="onComposerKeydown" />
      <div class="composer-actions">
        <el-button @click="handleReset" :disabled="isStreaming">重置对话</el-button>
        <el-button :disabled="!isStreaming" @click="handleCancel">中止</el-button>
        <el-button type="success" :disabled="isStreaming || !messages.length" @click="handleFinalize">定稿生成</el-button>
        <el-button type="primary" :icon="Promotion" circle :disabled="isStreaming || !canSend" @click="handleSend" title="发送" />
      </div>
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
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted } from 'vue'
import { generateContinuationStreaming, renderPromptWithKnowledge } from '@renderer/api/ai'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'
import { listLLMConfigs, type LLMConfigRead } from '@renderer/api/setting'
import { Plus, Promotion, Refresh, DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'

const props = defineProps<{ resolvedContext: string; llmConfigId?: number | null; promptName?: string | null; temperature?: number | null; max_tokens?: number | null; timeout?: number | null; effectiveSchema?: any; generationPromptName?: string | null; currentCardTitle?: string | null; currentCardContent?: any }>()
const emit = defineEmits<{ 'finalize': [string]; 'refresh-context': []; 'reset-selection': []; 'jump-to-card': [{ projectId: number; cardId: number }] }>()

const messages = ref<Array<{ role: 'user' | 'assistant'; content: string }>>([])
const draft = ref('')
const isStreaming = ref(false)
let streamCtl: { cancel: () => void } | null = null
const messagesEl = ref<HTMLDivElement | null>(null)

const lastRun = ref<{ prev: string; tail: string; targetIdx: number } | null>(null)
const canRegenerate = computed(() => !isStreaming.value && !!lastRun.value && messages.value[lastRun.value.targetIdx]?.role === 'assistant')
const canRegenerateNow = computed(() => {
  if (isStreaming.value) return false
  const last = messages.value[messages.value.length - 1]
  return !!last && last.role === 'assistant'
})

// 模型选择（覆盖卡片配置，按项目记忆）
const llmOptions = ref<LLMConfigRead[]>([])
const overrideLlmId = ref<number | null>(null)
const effectiveLlmId = computed(() => overrideLlmId.value || (props.llmConfigId as any) || null)
const MODEL_KEY_PREFIX = 'nf:assistant:model:'
function modelKeyForProject(pid: number) { return `${MODEL_KEY_PREFIX}${pid}` }

watch(overrideLlmId, (val) => {
  try { const pid = projectStore.currentProject?.id; if (pid && val) localStorage.setItem(modelKeyForProject(pid), String(val)) } catch {}
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

// ---- 多卡片数据引用（跨项目，使用 Pinia） ----
const assistantStore = useAssistantStore()
const projectStore = useProjectStore()
const selectorVisible = ref(false)
const selectorSourcePid = ref<number | null>(null)
const selectorCards = ref<CardRead[]>([])
const selectorSearch = ref('')
const selectorSelectedIds = ref<number[]>([])
const filteredSelectorCards = computed(() => {
  const q = (selectorSearch.value || '').trim().toLowerCase()
  if (!q) return selectorCards.value
  return (selectorCards.value || []).filter(c => (c.title || '').toLowerCase().includes(q))
})
const selectorTreeData = computed(() => {
  const byType: Record<string, any[]> = {}
  for (const c of filteredSelectorCards.value || []) {
    const tn = c.card_type?.name || '未分类'
    if (!byType[tn]) byType[tn] = []
    byType[tn].push({ id: c.id, title: c.title, label: c.title, key: `card:${c.id}`, isLeaf: true })
  }
  return Object.keys(byType).sort().map((t, idx) => ({ key: `type:${idx}`, label: t, children: byType[t] }))
})
const selectorCheckedKeys = ref<string[]>([])

async function openInjectSelector() {
  try {
    await assistantStore.loadProjects()
    const currentPid = projectStore.currentProject?.id || null
    selectorSourcePid.value = currentPid ?? (assistantStore.projects[0]?.id ?? null)
    if (selectorSourcePid.value) selectorCards.value = await assistantStore.loadCardsForProject(selectorSourcePid.value)
    selectorSelectedIds.value = []
    selectorSearch.value = ''
    selectorVisible.value = true
  } catch {}
}

async function onSelectorProjectChange(pid: number | null) {
  selectorCards.value = []
  if (!pid) return
  selectorCards.value = await assistantStore.loadCardsForProject(pid)
}

function onTreeCheck(_: any, meta: any) {
  // meta.checkedKeys: string[]
  const keys: string[] = (meta?.checkedKeys || []) as string[]
  selectorCheckedKeys.value = keys
  const ids = keys.filter(k => k.startsWith('card:')).map(k => Number(k.split(':')[1])).filter(n => Number.isFinite(n))
  selectorSelectedIds.value = ids
}

function removeInjectedRef(idx: number) { assistantStore.removeInjectedRefAt(idx) }

async function confirmAddInjectedRefs() {
  try {
    const pid = selectorSourcePid.value as number
    const pname = assistantStore.projects.find(p => p.id === pid)?.name || ''
    assistantStore.addInjectedRefs(pid, pname, selectorSelectedIds.value)
  } finally { selectorVisible.value = false }
}

function pruneEmpty(val: any): any {
  if (val == null) return val
  if (typeof val === 'string') return val.trim() === '' ? undefined : val
  if (typeof val !== 'object') return val
  if (Array.isArray(val)) {
    const arr = val.map(pruneEmpty).filter(v => v !== undefined)
    return arr
  }
  const out: Record<string, any> = {}
  for (const [k, v] of Object.entries(val)) {
    const pv = pruneEmpty(v)
    if (pv === undefined) continue
    if (typeof pv === 'object' && !Array.isArray(pv) && Object.keys(pv).length === 0) continue
    if (Array.isArray(pv) && pv.length === 0) continue
    out[k] = pv
  }
  return out
}

function buildConversationText() { return messages.value.map(m => (m.role === 'user' ? `用户: ${m.content}` : `助手: ${m.content}`)).join('\n') }

function buildDraftTail() {
  const parts: string[] = []
  if (injectedCardPrompt.value) parts.push(`【卡片提示词】\n${injectedCardPrompt.value}`)
  if (props.effectiveSchema) { try { parts.push(`【JSON Schema】\n\n\`\`\`json\n${JSON.stringify(props.effectiveSchema, null, 2)}\n\`\`\``) } catch {} }
  // 注入“引用卡片数据”（跨项目，多条）
  if (assistantStore.injectedRefs.length) {
    const blocks: string[] = []
    for (const ref of assistantStore.injectedRefs) {
      try {
        const cleaned = pruneEmpty(ref.content)
        const text = JSON.stringify(cleaned ?? {}, null, 2)
        const clipped = text.length > 6000 ? text.slice(0, 6000) + '\n/* 其余已截断 */' : text
        blocks.push(`【引用】项目：${ref.projectName} / 卡片：${ref.cardTitle}\n\n\`\`\`json\n${clipped}\n\`\`\``)
      } catch {}
    }
    if (blocks.length) parts.push(blocks.join('\n\n'))
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
    llm_config_id: effectiveLlmId.value as number,
    prompt_name: (props.promptName && props.promptName.trim()) ? props.promptName : '灵感对话',
    stream: true,
    temperature: props.temperature ?? 0.7,
    max_tokens: props.max_tokens ?? 8192,
    timeout: props.timeout ?? undefined,
    current_draft_tail: tail,
    append_continuous_novel_directive: false,
  }, (chunk) => {
    messages.value[targetIdx].content += chunk
    scrollToBottom()
  }, () => {
    isStreaming.value = false; streamCtl = null
    try { const pid = projectStore.currentProject?.id; if (pid) assistantStore.appendHistory(pid, { role: 'assistant', content: messages.value[targetIdx].content }) } catch {}
  }, (err) => { ElMessage.error(err?.message || '生成失败'); isStreaming.value = false; streamCtl = null }) as any
}

function handleSend() {
  if (!canSend.value || isStreaming.value) return
  lastRun.value = null
  const userText = draft.value.trim(); if (!userText) return
  messages.value.push({ role: 'user', content: userText })
  try { const pid = projectStore.currentProject?.id; if (pid) assistantStore.appendHistory(pid, { role: 'user', content: userText }) } catch {}
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
function regenerateFromCurrent() {
  if (isStreaming.value) return
  // 构造“去掉最后一条助手消息”的对话作为 previous_content
  const lastIndex = messages.value.length - 1
  const lastIsAssistant = lastIndex >= 0 && messages.value[lastIndex].role === 'assistant'
  const msgsForPrev = lastIsAssistant ? messages.value.slice(0, lastIndex) : messages.value.slice()
  const prev = msgsForPrev.map(m => (m.role === 'user' ? `用户: ${m.content}` : `助手: ${m.content}`)).join('\n')
  const tail = buildDraftTail()
  let targetIdx: number
  if (lastIsAssistant) {
    messages.value[lastIndex].content = ''
    targetIdx = lastIndex
  } else {
    targetIdx = messages.value.push({ role: 'assistant', content: '' }) - 1
  }
  lastRun.value = { prev, tail, targetIdx }
  startStreaming(prev, tail, targetIdx)
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
function handleReset() { try { streamCtl?.cancel() } catch {}; isStreaming.value = false; messages.value = []; draft.value = ''; lastRun.value = null; try { const pid = projectStore.currentProject?.id; if (pid) assistantStore.clearHistory(pid) } catch {}; scrollToBottom() }

function onChipClick(refItem: { projectId: number; cardId: number }) {
  emit('jump-to-card', { projectId: refItem.projectId, cardId: refItem.cardId })
}

function toConversationText(list: Array<{ role: 'user'|'assistant'; content: string }>) {
  return list.map(m => (m.role === 'user' ? `用户: ${m.content}` : `助手: ${m.content}`)).join('\n')
}

function handleRegenerateAt(idx: number) {
  if (isStreaming.value) return
  if (idx < 0 || idx >= messages.value.length) return
  if (messages.value[idx].role !== 'assistant') return
  // 历史剪裁到该条之前
  try {
    const pid = projectStore.currentProject?.id
    if (pid) {
      const prevMsgs = messages.value.slice(0, idx)
      assistantStore.setHistory(pid, prevMsgs.map(m => ({ role: m.role as any, content: m.content })))
    }
  } catch {}
  // 构造 prev 并覆盖该条助手消息
  const prev = toConversationText(messages.value.slice(0, idx))
  const tail = buildDraftTail()
  messages.value[idx].content = ''
  // 同时丢弃其后的消息（因上下文已失真）
  if (messages.value.length > idx + 1) messages.value.splice(idx + 1)
  lastRun.value = { prev, tail, targetIdx: idx }
  startStreaming(prev, tail, idx)
}

function onComposerKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    if (!e.shiftKey) {
      e.preventDefault()
      if (canSend.value && !isStreaming.value) handleSend()
    }
  }
}

onMounted(async () => {
  try {
    llmOptions.value = await listLLMConfigs()
    // 先尝试读取项目记忆；否则默认第一个模型
    const pid = projectStore.currentProject?.id
    const saved = pid ? Number(localStorage.getItem(modelKeyForProject(pid)) || '') : NaN
    if (saved && Number.isFinite(saved)) {
      overrideLlmId.value = saved
    } else if (!overrideLlmId.value && llmOptions.value.length > 0) {
      overrideLlmId.value = llmOptions.value[0].id
    }
  } catch {}
  try {
    const pid = projectStore.currentProject?.id
    if (!pid) { messages.value = []; return }
    const hist = assistantStore.getHistory(pid) || []
    messages.value = hist.map(h => ({ role: h.role, content: h.content }))
    nextTick(() => scrollToBottom())
  } catch {}
})

async function handleCopy(idx: number) {
  try {
    await navigator.clipboard.writeText(messages.value[idx]?.content || '')
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.assistant-panel { display: flex; flex-direction: column; height: 100%; font-size: 13px; }
.panel-header { display: flex; flex-direction: column; gap: 8px; padding: 8px; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-bg-color); }
.header-title-row { display: flex; align-items: center; }
.header-controls-row { display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; overflow-x: auto; }
.panel-header .title { font-weight: 600; color: var(--el-text-color-primary); font-size: 15px; }
.panel-header .card-tag { flex-shrink: 0; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.panel-header .spacer { flex: 1; min-width: 4px; }
.ctx-tag { cursor: pointer; flex-shrink: 0; font-size: 12px; }
.header-controls-row .el-button { flex-shrink: 0; padding: 3px 6px; font-size: 12px; }
.ctx-preview { max-height: 40vh; overflow: auto; white-space: pre-wrap; background: var(--el-bg-color); color: var(--el-text-color-primary); padding: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.chat-area { flex: 1; display: flex; flex-direction: column; gap: 6px; overflow: hidden; padding: 6px 8px; }
.messages { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-fill-color-blank); }
.msg { display: flex; flex-direction: column; align-items: flex-start; }
.msg.user { align-items: flex-end; }
.msg.assistant { align-items: flex-start; }
.bubble { max-width: 80%; padding: 8px 10px; border-radius: 8px; }
.bubble-text { margin: 0; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: var(--el-text-color-primary); }
.msg.assistant .bubble { background: var(--el-fill-color-light); border: 1px solid var(--el-border-color); }
.msg.user .bubble { background: var(--el-color-primary); color: var(--el-color-white); }
.msg.user .bubble-text { color: var(--el-color-white); }
.msg-toolbar { display: flex; gap: 6px; padding: 4px 0 0 2px; }
.streaming-tip { color: var(--el-text-color-secondary); padding-left: 4px; font-size: 12px; }
.composer { display: flex; flex-direction: column; gap: 6px; padding: 6px 8px; border-top: 1px solid var(--el-border-color-light); }
.inject-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-bottom: 6px; }
.inject-toolbar .chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.chip-tag { cursor: pointer; }
.composer-subbar { display: flex; align-items: center; gap: 8px; }
.composer-actions { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: nowrap; }
::deep(.composer .el-button) { padding: 6px 8px; font-size: 12px; }
</style> 