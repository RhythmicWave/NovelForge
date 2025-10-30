<template>
  <div class="assistant-panel">
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

    <div class="chat-area">
      <div class="messages" ref="messagesEl">
        <div v-for="(m, idx) in messages" :key="idx" :class="['msg', m.role]">
          <div class="bubble">
            <XMarkdown 
              :markdown="filterMessageContent(m.content)" 
              :default-theme-mode="isDarkMode ? 'dark' : 'light'"
              class="bubble-markdown"
            />
          </div>
          
          <!-- ⏳ 临时显示"正在调用工具"（在工具执行期间） -->
          <div v-if="m.toolsInProgress" class="tools-in-progress">
            <el-icon class="tools-icon spinning"><Loading /></el-icon>
            <pre class="tools-progress-text">{{ m.toolsInProgress }}</pre>
          </div>
          
          <!-- 工具调用展示 -->
          <div v-if="m.tools && m.tools.length" class="tools-summary">
            <div class="tools-header">
              <el-icon class="tools-icon"><Tools /></el-icon>
              <span class="tools-count">执行了 {{ m.tools.length }} 个操作</span>
            </div>
            <el-collapse class="tools-collapse">
              <el-collapse-item>
                <template #title>
                  <span class="tools-expand-label">查看详情</span>
                </template>
                <div v-for="(tool, tidx) in m.tools" :key="tidx" class="tool-item">
                  <div class="tool-header">
                    <el-tag size="small" type="success">{{ formatToolName(tool.tool_name) }}</el-tag>
                    <span class="tool-status">{{ tool.result?.success ? '✅ 成功' : '❌ 失败' }}</span>
                    <el-link 
                      v-if="tool.result?.card_id" 
                      type="primary" 
                      size="small"
                      @click="emit('jump-to-card', { 
                        projectId: projectStore.currentProject?.id || 0, 
                        cardId: tool.result.card_id 
                      })"
                    >
                      跳转到卡片 →
                    </el-link>
                  </div>
                  
                  <!-- 工具调用详细信息 -->
                  <div class="tool-details">
                    <!-- 简要消息 -->
                    <div v-if="tool.result?.message" class="tool-message">
                      {{ tool.result.message }}
                    </div>
                    
                    <!-- 关键返回数据 -->
                    <div v-if="tool.result" class="tool-result-summary">
                      <div v-if="tool.result.card_id" class="result-field">
                        <span class="field-label">卡片 ID:</span>
                        <span class="field-value">{{ tool.result.card_id }}</span>
                      </div>
                      <div v-if="tool.result.cards_created" class="result-field">
                        <span class="field-label">创建数量:</span>
                        <span class="field-value">{{ tool.result.cards_created.length }} 张</span>
                      </div>
                      <div v-if="tool.result.data" class="result-field">
                        <span class="field-label">返回数据:</span>
                        <span class="field-value">{{ typeof tool.result.data === 'object' ? JSON.stringify(tool.result.data).substring(0, 100) + '...' : tool.result.data }}</span>
                      </div>
                    </div>
                    
                    <!-- 完整 JSON（折叠显示） -->
                    <el-collapse class="tool-json-collapse">
                      <el-collapse-item title="查看完整返回数据">
                        <pre class="tool-json">{{ JSON.stringify(tool.result, null, 2) }}</pre>
                      </el-collapse-item>
                    </el-collapse>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
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
        <!-- 引用卡片显示区（分成两个容器：标签区 + 更多按钮区） -->
        <div class="chips">
          <!-- 标签显示区（可滚动溢出） -->
          <div class="chips-tags">
            <el-tag 
              v-for="(r, idx) in visibleRefs" 
              :key="r.projectId + '-' + r.cardId" 
              closable 
              @close="removeInjectedRef(idx)" 
              size="small" 
              effect="plain" 
              class="chip-tag" 
              @click="onChipClick(r)"
            >
              {{ r.projectName }} / {{ r.cardTitle }}
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
                    :key="r.projectId + '-' + r.cardId"
                    class="more-ref-item"
                  >
                    <span class="ref-info" @click="onChipClick(r)">
                      <el-icon><Document /></el-icon>
                      {{ r.projectName }} / {{ r.cardTitle }}
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
      
      <el-input v-model="draft" type="textarea" :rows="4" placeholder="输入你的想法、约束或追问" :disabled="isStreaming" @keydown="onComposerKeydown" class="composer-input" />
      
      <div class="composer-actions">
        <el-tooltip content="React模式：通过文本格式调用工具，兼容更多模型" placement="top">
          <el-switch 
            v-model="useReactMode" 
            size="small"
            active-text="React"
            style="margin-right: auto"
          />
        </el-tooltip>
        <el-button :disabled="!isStreaming" @click="handleCancel">中止</el-button>
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
import { ref, watch, computed, nextTick, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { generateContinuationStreaming, renderPromptWithKnowledge } from '@renderer/api/ai'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'
import { listLLMConfigs, type LLMConfigRead } from '@renderer/api/setting'
import { Plus, Promotion, Refresh, DocumentCopy, Tools, Loading, ChatDotRound, ArrowDown, Delete, Clock, Document, Close } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {XMarkdown} from 'vue-element-plus-x'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useAppStore } from '@renderer/stores/useAppStore'

const props = defineProps<{ resolvedContext: string; llmConfigId?: number | null; promptName?: string | null; temperature?: number | null; max_tokens?: number | null; timeout?: number | null; effectiveSchema?: any; generationPromptName?: string | null; currentCardTitle?: string | null; currentCardContent?: any }>()
const emit = defineEmits<{ 'finalize': [string]; 'refresh-context': []; 'reset-selection': []; 'jump-to-card': [{ projectId: number; cardId: number }] }>()

const messages = ref<Array<{ 
  role: 'user' | 'assistant'
  content: string
  tools?: Array<{tool_name: string, result: any}>
  toolsInProgress?: string
}>>([])
const draft = ref('')
const isStreaming = ref(false)
let streamCtl: { cancel: () => void } | null = null
const messagesEl = ref<HTMLDivElement | null>(null)

// ===== 会话管理 =====
interface ChatSession {
  id: string
  projectId: number
  title: string
  createdAt: number
  updatedAt: number
  messages: typeof messages.value
}

const currentSession = ref<ChatSession>({
  id: `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  projectId: 0,
  title: '新对话',
  createdAt: Date.now(),
  updatedAt: Date.now(),
  messages: []
})

const historySessions = ref<ChatSession[]>([])
const historyDrawerVisible = ref(false)

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

// ReAct 模式开关（按项目记忆）
const useReactMode = ref(false)
const REACT_MODE_KEY_PREFIX = 'nf:assistant:react:'
function reactModeKeyForProject(pid: number) { return `${REACT_MODE_KEY_PREFIX}${pid}` }

// 引用卡片显示控制
const MAX_VISIBLE_REFS = 5  // 最多显示5个引用（约两行，每行2-3个）

const visibleRefs = computed(() => {
  return assistantStore.injectedRefs.slice(0, MAX_VISIBLE_REFS)
})

const hiddenRefsCount = computed(() => {
  const total = assistantStore.injectedRefs.length
  return total > MAX_VISIBLE_REFS ? total - MAX_VISIBLE_REFS : 0
})

watch(overrideLlmId, (val) => {
  try { const pid = projectStore.currentProject?.id; if (pid && val) localStorage.setItem(modelKeyForProject(pid), String(val)) } catch {}
})

watch(useReactMode, (val) => {
  try { const pid = projectStore.currentProject?.id; if (pid) localStorage.setItem(reactModeKeyForProject(pid), String(val)) } catch {}
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
const appStore = useAppStore()
const { isDarkMode } = storeToRefs(appStore)
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

function buildConversationText() { 
  return messages.value.map(m => {
    const prefix = m.role === 'user' ? 'User:' : 'Assistant:'
    let text = `${prefix} ${m.content}`
    
    // 如果有工具调用历史，添加到对话中（让 LLM 知道工具执行结果）
    if (m.tools && m.tools.length > 0) {
      text += '\n\n[工具调用记录]'
      for (const tool of m.tools) {
        text += `\n- 工具: ${tool.tool_name}`
        if (tool.result) {
          text += `\n  结果: ${JSON.stringify(tool.result, null, 2)}`
        }
      }
    }
    
    return text
  }).join('\n\n')
}

//  构建灵感助手请求参数（使用新的项目结构化上下文）
function buildAssistantChatRequest() {
  const parts: string[] = []
  
  // 1. 项目结构化上下文（新增）
  if (assistantStore.projectStructure) {
    const struct = assistantStore.projectStructure
    parts.push(`# 项目: ${struct.project_name}`)
    parts.push(`项目ID: ${struct.project_id} | 卡片总数: ${struct.total_cards}`)
    parts.push('')
    
    // 统计信息
    const stats = Object.entries(struct.stats)
      .map(([type, count]) => `- ${type}: ${count} 张`)
      .join('\n')
    parts.push(`## 📊 项目统计\n${stats}`)
    parts.push('')
    
    // 卡片树
    parts.push(`## 🌲 卡片结构树\nROOT\n${struct.tree_text}`)
    parts.push('')
    
    // 可用类型
    parts.push(`## 🏷️ 可用卡片类型`)
    parts.push(struct.available_card_types.join(' | '))
    parts.push('')
  }
  
  // 2. 近期操作（新增）
  const opsText = assistantStore.formatRecentOperations()
  if (opsText) {
    parts.push(`## 📝 近期操作\n${opsText}`)
    parts.push('')
  }
  
  // 3. 当前卡片（包含 Schema）
  const context = assistantStore.getContextForAssistant()
  if (context.active_card) {
    parts.push(`## ⭐ 当前卡片`)
    parts.push(`"${context.active_card.title}" (ID: ${context.active_card.card_id}, 类型: ${context.active_card.card_type})`)
    
    // 添加当前卡片的 JSON Schema
    if (props.effectiveSchema) {
      try {
        const schemaText = JSON.stringify(props.effectiveSchema, null, 2)
        parts.push(`\n### 卡片结构 (JSON Schema)`)
        parts.push('```json')
        parts.push(schemaText)
        parts.push('```')
      } catch {}
    }
    
    parts.push('')
  }
  
  // 4. 引用卡片数据（保留，但简化）
  if (assistantStore.injectedRefs.length) {
    const blocks: string[] = []
    for (const ref of assistantStore.injectedRefs) {
      try {
        const cleaned = pruneEmpty(ref.content)
        const text = JSON.stringify(cleaned ?? {}, null, 2)
        const clipped = text.length > 4000 ? text.slice(0, 4000) + '\n/* ... */' : text
        blocks.push(`### 【引用】${ref.projectName} / ${ref.cardTitle}\n\`\`\`json\n${clipped}\n\`\`\``)
      } catch {}
    }
    parts.push(`## 📎 引用卡片\n${blocks.join('\n\n')}`)
    parts.push('')
  }
  
  // 5. @DSL 上下文（保留）
  if (props.resolvedContext) {
    parts.push(`## 🔗 上下文引用\n${props.resolvedContext}`)
    parts.push('')
  }
  
  // 6. 对话历史
  parts.push(`## 💬 对话历史`)
  parts.push(buildConversationText())
  
  // 从messages中获取最后一条用户消息，而不是从draft（draft在handleSend中已被清空）
  const lastUserMessage = messages.value.filter(m => m.role === 'user').pop()
  const userPrompt = lastUserMessage?.content?.trim() || ''
  
  return {
    user_prompt: userPrompt,
    context_info: parts.join('\n')
  }
}

function scrollToBottom() { nextTick(() => { try { const el = messagesEl.value; if (el) el.scrollTop = el.scrollHeight } catch {} }) }

function startStreaming(_prev: string, _tail: string, targetIdx: number) {
  isStreaming.value = true
  
  // 构建请求参数
  const chatRequest = buildAssistantChatRequest()
  
  // 临时工具调用状态（用于立即显示"正在调用工具"）
  let pendingToolCalls: any[] = []
  
  streamCtl = generateContinuationStreaming({
    ...chatRequest,
    llm_config_id: effectiveLlmId.value as number,
    prompt_name: (props.promptName && props.promptName.trim()) ? props.promptName : '灵感对话',
    project_id: projectStore.currentProject?.id as number,
    stream: true,
    temperature: props.temperature ?? 0.7,
    max_tokens: props.max_tokens ?? 8192,
    timeout: props.timeout ?? undefined,
    use_react_mode: useReactMode.value  // ReAct 模式开关
  } as any, (chunk) => {
    // 🔑 优先检测所有特殊标记（这些标记不应该显示在消息内容中）
    
    // ReAct 模式：检测工具调用开始
    if (chunk.includes('__TOOL_CALL_DETECTED__')) {
      if (messages.value[targetIdx]) {
        messages.value[targetIdx].toolsInProgress = '⏳ 正在调用工具...'
      }
      scrollToBottom()
      return
    }
    
    // ReAct 模式：检测工具执行完成
    if (chunk.includes('__TOOL_EXECUTED__:')) {
      const match = chunk.match(/__TOOL_EXECUTED__:(.+)/)
      if (match && messages.value[targetIdx]) {
        try {
          const toolResult = JSON.parse(match[1])
          
          // 记录工具调用
          if (!messages.value[targetIdx].tools) {
            messages.value[targetIdx].tools = []
          }
          messages.value[targetIdx].tools.push(toolResult)
          
          // 清除进度状态
          messages.value[targetIdx].toolsInProgress = undefined
          
          // 🔑 关键：调用刷新逻辑（与标准模式相同）
          handleToolsExecuted([toolResult])
          
          scrollToBottom()
        } catch (e) {
          console.warn('[ReAct] 解析工具执行结果失败', e)
        }
      }
      return
    }
    
    // 检测 __TOOL_CALL_START__（标准模式）
    if (chunk.includes('__TOOL_CALL_START__:')) {
      const match = chunk.match(/__TOOL_CALL_START__:(.+)/)
      if (match && messages.value[targetIdx]) {
        try {
          const toolCall = JSON.parse(match[1])
          pendingToolCalls.push(toolCall)
          
          if (!messages.value[targetIdx].toolsInProgress) {
            const toolsPreview = pendingToolCalls.map(t => `⏳ 正在调用工具: ${t.tool_name}...`).join('\n')
            messages.value[targetIdx].toolsInProgress = toolsPreview
          }
          scrollToBottom()
        } catch (e) {
          console.warn('解析工具调用开始失败', e)
        }
      }
      return  // 不添加到消息内容
    }
    
    // 检测 __RETRY__
    if (chunk.includes('__RETRY__:')) {
      const match = chunk.match(/__RETRY__:(.+)/)
      if (match && messages.value[targetIdx]) {
        try {
          const retryInfo = JSON.parse(match[1])
          messages.value[targetIdx].toolsInProgress = 
            `🔄 工具调用失败，${retryInfo.reason}，正在重试 (${retryInfo.retry}/${retryInfo.max})...`
          scrollToBottom()
        } catch (e) {
          console.warn('解析重试信息失败', e)
        }
      }
      return  // 不添加到消息内容
    }
    
    // 检测 __TOOL_SUMMARY__
    if (chunk.includes('__TOOL_SUMMARY__:')) {
      const match = chunk.match(/__TOOL_SUMMARY__:(.+)/)
      if (match && messages.value[targetIdx]) {
        try {
          const summary = JSON.parse(match[1])
          handleToolsExecuted(summary.tools)
          messages.value[targetIdx].toolsInProgress = undefined
          pendingToolCalls = []
        } catch (e) {
          console.warn('解析工具摘要失败', e)
        }
      }
      return  // 不添加到消息内容
    }
    
    // 检测 __ERROR__
    if (chunk.includes('__ERROR__:')) {
      const match = chunk.match(/__ERROR__:(.+)/)
      if (match && messages.value[targetIdx]) {
        try {
          const errorInfo = JSON.parse(match[1])
          messages.value[targetIdx].toolsInProgress = `❌ 工具调用失败: ${errorInfo.error || '执行失败'}`
          pendingToolCalls = []
          scrollToBottom()
        } catch (e) {
          console.warn('解析错误信息失败', e)
        }
      }
      return  // 不添加到消息内容
    }
    
    // 检测并处理 <notify>tool_name</notify> 标记
    let hasToolTag = false
    const toolMatch = chunk.match(/<notify>([\w\-]+)<\/notify>/)
    if (toolMatch && messages.value[targetIdx]) {
      hasToolTag = true
      const toolName = toolMatch[1]
      
      // 立即显示工具调用状态
      if (!messages.value[targetIdx].toolsInProgress) {
        messages.value[targetIdx].toolsInProgress = `⏳ 正在调用工具: ${toolName}...`
        scrollToBottom()
      }
      
      // 从chunk中移除 <notify> 标记
      chunk = chunk.replace(/<notify>[\w\-]+<\/notify>/g, '')
    }
    
    // 过滤后如果没有实际内容，不添加
    const trimmedChunk = chunk.trim()
    if (!trimmedChunk) {
      if (hasToolTag) scrollToBottom()
      return
    }
    
    // 安全检查：确保目标消息仍然存在
    if (!messages.value[targetIdx]) {
      console.warn(`⚠️ [AssistantPanel] 目标消息索引 ${targetIdx} 不存在，停止流式输出`)
      return
    }
    
    // 正常文本追加
    messages.value[targetIdx].content += chunk
    
    // 🔑 当收到正常文本时，清除工具调用进度提示（说明AI已经开始输出结果）
    if (trimmedChunk.length > 0 && messages.value[targetIdx]?.toolsInProgress) {
      // 只有当工具调用状态不是失败状态时才清除（失败状态需要保留显示）
      if (!messages.value[targetIdx].toolsInProgress.includes('❌')) {
        nextTick(() => {
          if (messages.value[targetIdx]) {  // 再次检查，防止在 nextTick 期间被删除
            messages.value[targetIdx].toolsInProgress = undefined
            pendingToolCalls = []
          }
        })
      }
    }
    
    scrollToBottom()
  }, () => {
    // 流结束时的清理
    isStreaming.value = false
    streamCtl = null
    
    // 如果工具调用状态不是失败状态，则清除（失败状态保留以供用户查看）
    if (messages.value[targetIdx]?.toolsInProgress && 
        !messages.value[targetIdx].toolsInProgress.includes('❌')) {
      messages.value[targetIdx].toolsInProgress = undefined
      pendingToolCalls = []
    }
    
    try { 
      const pid = projectStore.currentProject?.id
      if (pid && messages.value[targetIdx]) {
        assistantStore.appendHistory(pid, { role: 'assistant', content: messages.value[targetIdx].content })
      }
    } catch {}
  }, (err) => { 
    // ✅ 错误时也要清除"正在调用工具"状态
    if (messages.value[targetIdx]) {
      messages.value[targetIdx].toolsInProgress = undefined
    }
    pendingToolCalls = []
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
  startStreaming('', '', assistantIdx)
}

function handleCancel() { 
  try { streamCtl?.cancel() } catch {}
  isStreaming.value = false
  
  // 清除所有消息中的工具调用进度提示
  messages.value.forEach(msg => {
    if (msg.toolsInProgress) {
      msg.toolsInProgress = undefined
    }
  })
}
function handleRegenerate() { if (!canRegenerate.value || !lastRun.value) return; messages.value[lastRun.value.targetIdx].content = ''; scrollToBottom(); startStreaming('', '', lastRun.value.targetIdx) }
function regenerateFromCurrent() {
  if (isStreaming.value) return
  const lastIndex = messages.value.length - 1
  const lastIsAssistant = lastIndex >= 0 && messages.value[lastIndex].role === 'assistant'
  let targetIdx: number
  if (lastIsAssistant) {
    messages.value[lastIndex].content = ''
    targetIdx = lastIndex
  } else {
    targetIdx = messages.value.push({ role: 'assistant', content: '' }) - 1
  }
  lastRun.value = { prev: '', tail: '', targetIdx }
  startStreaming('', '', targetIdx)
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
function onChipClick(refItem: { projectId: number; cardId: number }) {
  emit('jump-to-card', { projectId: refItem.projectId, cardId: refItem.cardId })
}

function toConversationText(list: Array<{ role: 'user'|'assistant'; content: string }>) {
  return list.map(m => {
    const prefix = m.role === 'user' ? 'User:' : 'Assistant:'
    return `${prefix} ${m.content}`
  }).join('\n\n')
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
  // 覆盖该条助手消息（清空内容和工具调用记录）
  messages.value[idx].content = ''
  messages.value[idx].tools = undefined  //  清除工具调用记录
  // 同时丢弃其后的消息（因上下文已失真）
  if (messages.value.length > idx + 1) messages.value.splice(idx + 1)
  lastRun.value = { prev: '', tail: '', targetIdx: idx }
  startStreaming('', '', idx)
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
    const pid = projectStore.currentProject?.id
    
    // 恢复模型选择
    const saved = pid ? Number(localStorage.getItem(modelKeyForProject(pid)) || '') : NaN
    if (saved && Number.isFinite(saved)) {
      overrideLlmId.value = saved
    } else if (!overrideLlmId.value && llmOptions.value.length > 0) {
      overrideLlmId.value = llmOptions.value[0].id
    }
    
    // 恢复 React 模式设置
    if (pid) {
      const reactModeSaved = localStorage.getItem(reactModeKeyForProject(pid))
      if (reactModeSaved !== null) {
        useReactMode.value = reactModeSaved === 'true'
      }
    }
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

// ✅ 新增：处理工具执行结果
function handleToolsExecuted(tools: Array<{tool_name: string, result: any}>) {
  console.log('🔧 工具已执行:', tools)
  
  // 关联到最后一条助手消息
  const lastIdx = messages.value.length - 1
  if (lastIdx >= 0 && messages.value[lastIdx].role === 'assistant') {
    messages.value[lastIdx].tools = tools
  }
  
  // 刷新左侧卡片树（如果有卡片被创建或修改）
  const needsRefresh = tools.some(t => {
    const toolName = t.tool_name
    const result = t.result
    
    // 这些工具调用后需要刷新卡片列表
    const refreshTools = ['create_card', 'modify_card_field', 'batch_create_cards', 'replace_field_text']
    
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
}

// 工具名称格式化
function formatToolName(name: string): string {
  const map: Record<string, string> = {
    'search_cards': '搜索卡片',
    'create_card': '创建卡片',
    'modify_card_field': '修改字段',
    'batch_create_cards': '批量创建',
    'replace_field_text': '替换文本'
  }
  return map[name] || name
}

// ===== 会话管理函数 =====
function getSessionStorageKey(projectId: number): string {
  return `assistant-sessions-${projectId}`
}

function loadHistorySessions(projectId: number) {
  try {
    const key = getSessionStorageKey(projectId)
    const stored = localStorage.getItem(key)
    if (stored) {
      const sessions = JSON.parse(stored) as ChatSession[]
      historySessions.value = sessions.sort((a, b) => b.updatedAt - a.updatedAt)
      console.log(`📚 加载了 ${sessions.length} 个历史会话`)
    } else {
      historySessions.value = []
    }
  } catch (e) {
    console.error('加载历史会话失败:', e)
    historySessions.value = []
  }
}

function saveCurrentSession() {
  if (!projectStore.currentProject?.id) return
  if (messages.value.length === 0) return  // 空会话不保存
  
  try {
    // 深拷贝当前会话以避免引用问题
    const sessionToSave = {
      ...currentSession.value,
      messages: JSON.parse(JSON.stringify(messages.value)),
      updatedAt: Date.now(),
      projectId: projectStore.currentProject.id
    }
    
    // 自动生成标题（使用第一条用户消息的前20个字符）
    if (sessionToSave.title === '新对话') {
      const firstUserMsg = messages.value.find(m => m.role === 'user')
      if (firstUserMsg) {
        sessionToSave.title = firstUserMsg.content.substring(0, 20) + (firstUserMsg.content.length > 20 ? '...' : '')
      }
    }
    
    const key = getSessionStorageKey(projectStore.currentProject.id)
    
    // 从 localStorage 读取最新的会话列表（避免并发问题）
    let sessions: ChatSession[] = []
    try {
      const stored = localStorage.getItem(key)
      sessions = stored ? JSON.parse(stored) : []
    } catch {
      sessions = []
    }
    
    // 查找并更新现有会话，或添加新会话
    const existingIndex = sessions.findIndex(s => s.id === sessionToSave.id)
    if (existingIndex >= 0) {
      // 更新现有会话
      sessions[existingIndex] = sessionToSave
      // 将更新的会话移到最前面
      const [updated] = sessions.splice(existingIndex, 1)
      sessions.unshift(updated)
    } else {
      // 添加新会话到最前面
      sessions.unshift(sessionToSave)
    }
    
    // 最多保留50个会话
    if (sessions.length > 50) {
      sessions.splice(50)
    }
    
    localStorage.setItem(key, JSON.stringify(sessions))
    historySessions.value = sessions
    
    // 更新当前会话的标题（如果改变了）
    if (currentSession.value.title !== sessionToSave.title) {
      currentSession.value.title = sessionToSave.title
    }
  } catch (e) {
    console.error('保存会话失败:', e)
  }
}

function createNewSession() {
  // 先保存当前会话（如果有消息）
  if (messages.value.length > 0) {
    saveCurrentSession()
  }
  
  // 创建新会话（不清空输入框）
  currentSession.value = {
    id: `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    projectId: projectStore.currentProject?.id || 0,
    title: '新对话',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: []
  }
  
  messages.value = []
  
  // 关闭抽屉
  historyDrawerVisible.value = false
  
  console.log('📝 创建新对话')
}

function loadSession(sessionId: string) {
  const session = historySessions.value.find(s => s.id === sessionId)
  if (!session) return
  
  // 先保存当前会话
  if (messages.value.length > 0) {
    saveCurrentSession()
  }
  
  // 加载选中的会话
  currentSession.value = { ...session }
  messages.value = [...session.messages]
  
  // 关闭抽屉
  historyDrawerVisible.value = false
  
  console.log('📖 加载会话:', session.title)
  nextTick(() => scrollToBottom())
}

function deleteSession(sessionId: string) {
  if (!projectStore.currentProject?.id) return
  
  try {
    const key = getSessionStorageKey(projectStore.currentProject.id)
    historySessions.value = historySessions.value.filter(s => s.id !== sessionId)
    localStorage.setItem(key, JSON.stringify(historySessions.value))
    
    // 如果删除的是当前会话，创建新会话
    if (currentSession.value.id === sessionId) {
      createNewSession()
    }
    
    ElMessage.success('已删除会话')
  } catch (e) {
    console.error('删除会话失败:', e)
    ElMessage.error('删除会话失败')
  }
}

function handleDeleteSession(sessionId: string) {
  ElMessageBox.confirm('确定要删除这个对话吗？', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    deleteSession(sessionId)
  }).catch(() => {})
}

function formatSessionTime(timestamp: number): string {
  const now = Date.now()
  const diff = now - timestamp
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  
  if (diff < minute) {
    return '刚刚'
  } else if (diff < hour) {
    return `${Math.floor(diff / minute)}分钟前`
  } else if (diff < day) {
    return `${Math.floor(diff / hour)}小时前`
  } else if (diff < 7 * day) {
    return `${Math.floor(diff / day)}天前`
  } else {
    const date = new Date(timestamp)
    return `${date.getMonth() + 1}/${date.getDate()}`
  }
}

// 过滤消息内容中的特殊标记
function filterMessageContent(content: string): string {
  if (!content) return ''
  
  // 移除完整的 <notify>xxx</notify> 标记
  let filtered = content.replace(/<notify>[\w\-]*<\/notify>/g, '')
  
  // 移除末尾不完整的 <notify 标记（流式传输时可能出现）
  filtered = filtered.replace(/<notify[^>]*$/g, '')
  
  // ReAct 模式：移除 <tool_call>...</tool_call> 标记及其内容
  filtered = filtered.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
  
  // 移除不完整的 <tool_call> 标记
  filtered = filtered.replace(/<tool_call[^>]*$/g, '')
  
  // 移除所有协议标记
  filtered = filtered.replace(/__TOOL_CALL_START__:.*/g, '')
  filtered = filtered.replace(/__TOOL_CALL_DETECTED__.*/g, '')
  filtered = filtered.replace(/__TOOL_EXECUTED__:.*/g, '')
  filtered = filtered.replace(/__RETRY__:.*/g, '')
  filtered = filtered.replace(/__TOOL_SUMMARY__:.*/g, '')
  filtered = filtered.replace(/__ERROR__:.*/g, '')
  
  // ReAct 模式：移除工具执行结果文本块（**工具执行结果**：...）
  filtered = filtered.replace(/\*\*工具执行结果\*\*：[\s\S]*?```json[\s\S]*?```/g, '')
  
  return filtered.trim()
}

// 项目切换时加载该项目的历史会话
watch(() => projectStore.currentProject?.id, (newProjectId, oldProjectId) => {
  if (newProjectId) {
    loadHistorySessions(newProjectId)
    
    // 如果有历史会话，加载最近的一个（避免重复创建新会话）
    // 只有在无历史会话时才创建新会话
    if (historySessions.value.length > 0) {
      // 加载最近的会话
      const latestSession = historySessions.value[0]
      currentSession.value = { ...latestSession }
      messages.value = [...latestSession.messages]
      console.log('📖 加载最近会话:', latestSession.title)
      nextTick(() => scrollToBottom())
    } else {
      // 无历史会话：创建新会话
      createNewSession()
    }
  }
}, { immediate: true })

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
</script>

<style scoped>
.assistant-panel { 
  display: flex; 
  flex-direction: column; 
  height: 100%; 
  font-size: 13px;
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
.messages { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-fill-color-blank); }
.msg { display: flex; flex-direction: column; align-items: flex-start; }
.msg.user { align-items: flex-end; }
.msg.assistant { align-items: flex-start; }
.bubble { max-width: 80%; padding: 8px 10px; border-radius: 8px; }
.bubble-text { margin: 0; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: var(--el-text-color-primary); user-select: text; cursor: text; }

/* Markdown 渲染样式 */
.bubble-markdown { 
  font-size: 13px;
  line-height: 1.6;
  font-family: 、"Segoe UI",  "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  color: var(--el-text-color-primary);
}


/* 用户消息白色主题适配 */
.msg.user .bubble-markdown :deep(*) { 
  color: var(--el-color-white) !important; 
}
.msg.user .bubble-markdown :deep(code) { 
  background: rgba(255, 255, 255, 0.2) !important; 
}
.msg.user .bubble-markdown :deep(pre) { 
  background: rgba(255, 255, 255, 0.15) !important; 
}
.msg.user .bubble-markdown :deep(a) { 
  color: var(--el-color-white) !important;
  text-decoration: underline;
}

.msg.assistant .bubble { background: var(--el-fill-color-light); border: 1px solid var(--el-border-color); }
.msg.user .bubble { background: var(--el-color-primary); color: var(--el-color-white); }
.msg.user .bubble-text { color: var(--el-color-white); }
.msg-toolbar { display: flex; gap: 6px; padding: 4px 0 0 2px; }
.streaming-tip { color: var(--el-text-color-secondary); padding-left: 4px; font-size: 12px; }
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
  font-size: 13px;
  line-height: 1.6;
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
}

::deep(.composer .el-button) { padding: 6px 8px; font-size: 12px; }
::deep(.inject-toolbar .el-button) { padding: 4px 8px !important; font-size: 12px; height: 24px; }

/* ⏳ 正在调用工具的临时提示样式 */
.tools-in-progress {
  margin-top: 8px;
  max-width: 80%;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-color-warning-light-7);
  border-radius: 8px;
  padding: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-color-warning);
}

.tools-in-progress .tools-icon {
  font-size: 16px;
}

.tools-in-progress .spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.tools-progress-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  color: var(--el-color-warning-dark-2);
}

/* 工具调用相关样式（醒目设计） */
.tools-summary {
  margin-top: 8px;
  max-width: 80%;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 8px;
  padding: 8px;
}

.tools-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  color: var(--el-color-success);
  font-weight: 600;
  font-size: 13px;
}

.tools-icon {
  font-size: 16px;
}

.tools-count {
  color: var(--el-color-success);
}

.tools-collapse {
  margin-top: 4px;
}

.tools-expand-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tool-item {
  padding: 12px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
  border-radius: 6px;
  margin-bottom: 8px;
}

.tool-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.tool-status {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tool-details {
  margin-top: 8px;
}

.tool-message {
  color: var(--el-text-color-regular);
  font-size: 12px;
  margin-bottom: 8px;
  padding: 6px 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.tool-result-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.result-field {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.field-label {
  color: var(--el-text-color-secondary);
  font-weight: 600;
  min-width: 70px;
}

.field-value {
  color: var(--el-text-color-primary);
  font-family: 'Consolas', 'Monaco', monospace;
}

.tool-json-collapse {
  margin-top: 4px;
}

.tool-json {
  font-size: 11px;
  background: var(--el-fill-color-darker);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  max-height: 300px;
  color: var(--el-text-color-primary);
  font-family: 'Consolas', 'Monaco', monospace;
}

/* 旧样式（兼容性保留） */
.tool-msg {
  color: var(--el-text-color-regular);
  font-size: 12px;
  flex: 1;
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
</style> 