<template>
  <div class="assistant-panel">
    <div class="panel-header">
      <span class="title">灵感助手</span>
      <el-tag v-if="currentCardTitle" size="small" type="info" class="card-tag" effect="plain">{{ currentCardTitle }}</el-tag>
      <div class="spacer"></div>
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
      <div class="inject-toolbar">
        <div class="chips">
          <el-tag v-for="(r, idx) in assistantStore.injectedRefs" :key="r.projectId + '-' + r.cardId" closable @close="removeInjectedRef(idx)" size="small" effect="plain">
            {{ r.projectName }} / {{ r.cardTitle }}
          </el-tag>
        </div>
        <el-button size="small" :icon="Plus" @click="openInjectSelector">添加引用</el-button>
      </div>
      <el-input v-model="draft" type="textarea" :rows="3" placeholder="输入你的想法、约束或追问" :disabled="isStreaming" />
      <div class="composer-actions">
        <el-button @click="handleReset" :disabled="isStreaming">重置对话</el-button>
        <el-button :disabled="!isStreaming" @click="handleCancel">中止</el-button>
        <el-button :disabled="!canRegenerate" @click="handleRegenerate">重新生成</el-button>
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
import { ref, watch, computed, nextTick } from 'vue'
import { generateContinuationStreaming, renderPromptWithKnowledge } from '@renderer/api/ai'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'
import { Plus, Promotion } from '@element-plus/icons-vue'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'

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

const canSend = computed(() => {
  const hasDraft = !!draft.value.trim()
  const hasRefs = assistantStore.injectedRefs.length > 0
  return !!props.llmConfigId && (hasDraft || hasRefs)
})

// ---- 多卡片数据引用（跨项目，使用 Pinia） ----
const assistantStore = useAssistantStore()
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
    selectorSourcePid.value = assistantStore.projects[0]?.id ?? null
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
.inject-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-bottom: 6px; }
.inject-toolbar .chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.composer-actions { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: nowrap; }
:deep(.composer .el-button) { padding: 6px 8px; font-size: 12px; }
</style> 