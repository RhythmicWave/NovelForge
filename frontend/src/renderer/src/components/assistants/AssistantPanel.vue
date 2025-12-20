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

    <div class="chat-area reasoning-container">
      <div class="messages" ref="messagesEl">
        <div v-for="(m, idx) in messages" :key="idx" :class="['msg', m.role]">
          <!-- 文本内容：
               - 对于用户或无工具调用的助手消息：直接显示 content
               - 对于有工具调用的助手消息：使用 preToolText + 按波次拆分的 toolGroups 展示
          -->
          <template v-if="m.role !== 'assistant' || !m.toolGroups || !m.toolGroups.length">
            <!-- 无分波次信息时的思考过程展示（整体按顺序渲染，每段可单独折叠） -->
            <div
              v-if="m.role === 'assistant' && ((m as any).reasoningSegments && (m as any).reasoningSegments.length || m.reasoning)"
            >
              <Thinking
                v-for="(seg, sidx) in ((m as any).reasoningSegments && (m as any).reasoningSegments.length ? (m as any).reasoningSegments : (m.reasoning ? [m.reasoning] : []))"
                :key="'plain-r-' + sidx"
                v-model="reasoningBucketsOpen[`plain-${idx}-${sidx}`]"
                :status="isStreaming && idx === messages.length - 1 && m._lastAssistantEvent === 'reasoning' && m._lastReasoningBucketKey === `plain-${idx}-${sidx}` ? 'thinking' : 'end'"
                auto-collapse
                max-width="100%"
                :background-color="isDarkMode ? 'rgba(255,255,255,0.16)' : 'var(--el-fill-color-light)'"
                :color="isDarkMode ? 'var(--el-text-color-primary)' : 'var(--el-text-color-primary)'"
                :content="filterMessageContent(seg)"
              />
            </div>
            <div v-if="m.role !== 'assistant' || (!m.preToolText && !m.postToolText)" class="bubble">
              <XMarkdown 
                :markdown="filterMessageContent(m.content)" 
                :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                class="bubble-markdown"
              />
            </div>
            <div v-else>
              <div v-if="m.preToolText && m.preToolText.trim()" class="bubble">
                <XMarkdown 
                  :markdown="filterMessageContent(m.preToolText)" 
                  :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                  class="bubble-markdown"
                />
              </div>
              <div v-if="m.postToolText && m.postToolText.trim()" class="bubble">
                <XMarkdown 
                  :markdown="filterMessageContent(m.postToolText)" 
                  :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                  class="bubble-markdown"
                />
              </div>
            </div>
          </template>

          <template v-else>
            <!-- 1) 工具调用前的思考过程（可折叠） -->
            <div
              v-if="(m as any).preToolReasoningSegments && (m as any).preToolReasoningSegments.length"
            >
              <Thinking
                v-for="(seg, sidx) in (m as any).preToolReasoningSegments"
                :key="'pre-r-' + sidx"
                v-model="reasoningBucketsOpen[`pre-${idx}-${sidx}`]"
                :status="isStreaming && idx === messages.length - 1 && m._lastAssistantEvent === 'reasoning' && m._lastReasoningBucketKey === `pre-${idx}-${sidx}` ? 'thinking' : 'end'"
                auto-collapse
                max-width="100%"
                :background-color="isDarkMode ? 'rgba(255,255,255,0.16)' : 'var(--el-fill-color-light)'"
                :color="isDarkMode ? 'var(--el-text-color-primary)' : 'var(--el-text-color-primary)'"
                :content="filterMessageContent(seg)"
              />
            </div>

            <!-- 2) 工具调用前的文本 -->
            <div v-if="m.preToolText && m.preToolText.trim() && !shouldHidePreToolText(m)" class="bubble">
              <XMarkdown 
                :markdown="filterMessageContent(m.preToolText)" 
                :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                class="bubble-markdown"
              />
            </div>
            <!-- 3) 按波次拆分的工具调用 + 每波后的补充文本和思考过程（每波可单独折叠） -->
            <div v-for="(group, gidx) in m.toolGroups" :key="gidx">
              <div v-if="group.tools && group.tools.length" class="tools-summary">
                <div class="tools-header">
                  <el-icon class="tools-icon"><Tools /></el-icon>
                  <span class="tools-count">执行了 {{ group.tools.length }} 个操作</span>
                </div>
                <el-collapse class="tools-collapse">
                  <el-collapse-item>
                    <template #title>
                      <span class="tools-expand-label">查看详情</span>
                    </template>
                    <div v-for="(tool, tidx) in group.tools" :key="tidx" class="tool-item">
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
                      <div class="tool-details">
                        <div v-if="tool.result?.message" class="tool-message">
                          {{ tool.result.message }}
                        </div>
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

              <!-- 每一波工具调用后的思考过程（与该波工具同一分组，可折叠） -->
              <div
                v-if="(group as any).reasoningSegments && (group as any).reasoningSegments.length"
              >
                <Thinking
                  v-for="(seg, sidx) in (group as any).reasoningSegments"
                  :key="`g-${gidx}-r-${sidx}`"
                  v-model="reasoningBucketsOpen[`g-${idx}-${gidx}-${sidx}`]"
                  :status="isStreaming && idx === messages.length - 1 && m._lastAssistantEvent === 'reasoning' && m._lastReasoningBucketKey === `g-${idx}-${gidx}-${sidx}` ? 'thinking' : 'end'"
                  auto-collapse
                  max-width="100%"
                  :background-color="isDarkMode ? 'rgba(255,255,255,0.10)' : 'var(--el-fill-color-light)'"
                  :color="isDarkMode ? 'var(--el-text-color-primary)' : 'var(--el-text-color-primary)'"
                  :content="filterMessageContent(seg)"
                />
              </div>

              <!-- 每一波工具调用后的补充文本（忽略纯空白） -->
              <div v-if="group.postText && group.postText.trim()" class="bubble">
                <XMarkdown 
                  :markdown="filterMessageContent(group.postText)" 
                  :default-theme-mode="isDarkMode ? 'dark' : 'light'"
                  class="bubble-markdown"
                />
              </div>
            </div>
          </template>
          
          <!-- ⏳ 临时显示"正在调用工具"（在工具执行期间） -->
          <div v-if="m.toolsInProgress" class="tools-in-progress">
            <el-icon class="tools-icon spinning"><Loading /></el-icon>
            <pre class="tools-progress-text">{{ m.toolsInProgress }}</pre>
          </div>
          
          <!-- 工具调用展示（无分波次信息时的回退显示） -->
          <div v-if="m.tools && m.tools.length && (!m.toolGroups || !m.toolGroups.length)" class="tools-summary">
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
        <el-tooltip content="Thinking：启用推理/思考模式（确保模型支持开启/关闭思考）" placement="top">
          <el-switch 
            v-model="useThinkingMode" 
            size="small"
            active-text="Thinking"
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
import { XMarkdown, Thinking } from 'vue-element-plus-x'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useAppStore } from '@renderer/stores/useAppStore'
import { useAssistantPreferences } from '@renderer/composables/useAssistantPreferences'

const props = defineProps<{ resolvedContext: string; llmConfigId?: number | null; promptName?: string | null; temperature?: number | null; max_tokens?: number | null; timeout?: number | null; effectiveSchema?: any; generationPromptName?: string | null; currentCardTitle?: string | null; currentCardContent?: any }>()
const emit = defineEmits<{ 'finalize': [string]; 'refresh-context': []; 'reset-selection': []; 'jump-to-card': [{ projectId: number; cardId: number }] }>()

const messages = ref<Array<{
  role: 'user' | 'assistant'
  content: string
  tools?: Array<{tool_name: string, result: any}>
  toolsInProgress?: string
  // 以下字段仅对助手消息有意义：用于将文本分为“工具调用前/后”两部分，便于在 UI 中插入工具卡片
  preToolText?: string
  postToolText?: string
  toolCompleted?: boolean
  // 按波次拆分的工具调用分组，每一组包含本波次的所有工具、其后的补充文本以及该波次后的思考片段
  toolGroups?: Array<{ tools: Array<{tool_name: string, result: any}>, postText: string, reasoningSegments?: string[] }>
  // 内部状态：记录最近一次助手事件类型（'token' 或 'tool_end'），用于判断是否开启新的一波工具调用
  _lastAssistantEvent?: 'token' | 'tool_end' | 'reasoning'
  // 推理模型的 thinking 内容（仅在模型返回 reasoning 块时存在）
  reasoning?: string
  // 多段思考内容分片（按流式阶段拆分）
  reasoningSegments?: string[]
  // 工具调用前阶段的思考分片
  preToolReasoningSegments?: string[]
  // 本地 UI 状态：是否展开思考过程
  _showReasoning?: boolean
  // 是否曾经接收过 reasoning 内容
  _hasReasoning?: boolean
  // 用户是否主动切换过思考过程的展开/折叠
  _reasoningUserToggled?: boolean
  // 最近一段自动管理的思考片段对应的折叠桶 key（用于在思考结束时自动折叠该片段）
  _lastReasoningBucketKey?: string
}>>([])
const draft = ref('')
const isStreaming = ref(false)
let streamCtl: { cancel: () => void } | null = null
const messagesEl = ref<HTMLDivElement | null>(null)

// 思考过程折叠状态：key 为 bucket 标识（例如 plain-0-0 / pre-0-0 / g-0-1-0），值为是否展开
// 默认收起（false），用户点击后再展开
const reasoningBucketsOpen = ref<Record<string, boolean>>({})

function isReasoningBucketOpen(key: string): boolean {
  return reasoningBucketsOpen.value[key] === true
}

function toggleReasoningBucket(key: string) {
  reasoningBucketsOpen.value[key] = !isReasoningBucketOpen(key)
}

function setReasoningBucket(key: string, val: boolean) {
  reasoningBucketsOpen.value[key] = !!val
}

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

// Thinking 模式开关（按项目记忆）
const useThinkingMode = ref(false)
const THINKING_MODE_KEY_PREFIX = 'nf:assistant:thinking:'
function thinkingModeKeyForProject(pid: number) { return `${THINKING_MODE_KEY_PREFIX}${pid}` }

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

watch(useThinkingMode, (val) => {
  try { const pid = projectStore.currentProject?.id; if (pid) localStorage.setItem(thinkingModeKeyForProject(pid), String(val)) } catch {}
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
const assistantPrefs = useAssistantPreferences()
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
  
  const preferencePayload = {
    context_summarization_enabled: assistantPrefs.contextSummaryEnabled.value || undefined,
    context_summarization_threshold: assistantPrefs.contextSummaryThreshold.value || undefined,
    react_mode_enabled: assistantPrefs.reactModeEnabled.value || undefined,
  }

  return {
    user_prompt: userPrompt,
    context_info: parts.join('\n'),
    ...preferencePayload
  }
}

function scrollToBottom() { nextTick(() => { try { const el = messagesEl.value; if (el) el.scrollTop = el.scrollHeight } catch {} }) }

function startStreaming(_prev: string, _tail: string, targetIdx: number) {
  isStreaming.value = true
  
  // 构建请求参数
  const chatRequest = buildAssistantChatRequest()
  const promptName = (props.promptName && props.promptName.trim()) ? props.promptName : '灵感对话'
  
  // 临时工具调用状态（用于立即显示"正在调用工具"）
  let pendingToolCalls: any[] = []
  
  streamCtl = generateContinuationStreaming({
    ...chatRequest,
    llm_config_id: overrideLlmId.value || undefined,
    prompt_name: promptName,
    project_id: projectStore.currentProject?.id as number,
    stream: true,
    temperature: props.temperature ?? 0.7,
    max_tokens: props.max_tokens ?? 8192,
    timeout: props.timeout ?? undefined,
    thinking_enabled: useThinkingMode.value
  } as any, (chunk) => {
    // 优先尝试解析为结构化事件（JSON-line）
    let evt: any = null
    try { evt = JSON.parse(chunk) } catch { evt = null }
    if (evt && typeof evt === 'object' && evt.type) {
      const type = evt.type as string
      const data = (evt.data || {}) as any

      if (!messages.value[targetIdx]) {
        console.warn(`[AssistantPanel] 目标消息索引 ${targetIdx} 不存在，忽略事件`, evt)
        return
      }

      // 若上一段思考过程已结束（当前事件不再是 reasoning），自动折叠上一段自动管理的思考片段
      if (type !== 'reasoning') {
        const baseMsg = messages.value[targetIdx]
        if (baseMsg && baseMsg.role === 'assistant') {
          const mAny = baseMsg as any
          const lastKey = mAny._lastReasoningBucketKey as string | undefined
          if (lastKey && isReasoningBucketOpen(lastKey)) {
            reasoningBucketsOpen.value[lastKey] = false
          }
          mAny._lastReasoningBucketKey = undefined
        }
      }

      if (type === 'token') {
        let text = String(data.text || '')
        if (!text) return

        // 后端已统一处理所有协议标记，前端直接使用原始文本

        const msg = messages.value[targetIdx]

        // 1) 始终累加到 content，便于历史、导出和复制
        msg.content += text
        // 2) 对助手消息进行分段显示：
        if (msg.role === 'assistant') {
          // 如果前面已经有 reasoning，在第一段正式回复文本到来时自动折叠思考过程
          if (msg._hasReasoning && msg._showReasoning && !msg._reasoningUserToggled) {
            msg._showReasoning = false
          }
          // 在首个工具完成(tool_end)之前的文本视为 preToolText
          if (!msg.toolCompleted) {
            msg.preToolText = (msg.preToolText || '') + text
          } else {
            // 已经至少有一轮工具调用：将文本归入当前波次的 postText
            if (!msg.toolGroups || msg.toolGroups.length === 0) {
              msg.toolGroups = [{ tools: [], postText: '' }]
            }
            const lastGroup = msg.toolGroups[msg.toolGroups.length - 1]
            lastGroup.postText = (lastGroup.postText || '') + text
          }
          msg._lastAssistantEvent = 'token'
        }
        if (messages.value[targetIdx]?.toolsInProgress && !messages.value[targetIdx].toolsInProgress.includes('❌')) {
          nextTick(() => {
            if (messages.value[targetIdx]) {
              messages.value[targetIdx].toolsInProgress = undefined
              pendingToolCalls = []
            }
          })
        }
        scrollToBottom()
        return
      }

      if (type === 'tool_start') {
        const toolName = data.tool_name || ''
        if (!messages.value[targetIdx].toolsInProgress) {
          messages.value[targetIdx].toolsInProgress = `⏳ 正在调用工具: ${toolName || '工具'}...`
        }
        scrollToBottom()
        return
      }

      if (type === 'tool_end') {
        const toolResult = {
          tool_name: data.tool_name,
          args: data.args,
          result: data.result
        }
        const msg = messages.value[targetIdx]
        if (!msg.tools) {
          msg.tools = []
        }
        msg.tools.push(toolResult)

        // 按波次分组工具调用：
        if (!msg.toolGroups) {
          msg.toolGroups = []
        }
        const lastEvent = msg._lastAssistantEvent
        if (!msg.toolGroups.length || lastEvent !== 'tool_end') {
          // 新的一波工具调用
          msg.toolGroups.push({ tools: [toolResult], postText: '' })
        } else {
          // 与上一条 tool_end 连续，归入同一波
          msg.toolGroups[msg.toolGroups.length - 1].tools.push(toolResult)
        }

        msg.toolsInProgress = undefined
        // 标记该助手消息已至少完成一次工具调用
        msg.toolCompleted = true
        msg._lastAssistantEvent = 'tool_end'

        handleToolsExecuted(targetIdx, [toolResult])
        scrollToBottom()
        return
      }

      if (type === 'tool_summary') {
        const tools = Array.isArray(data.tools) ? data.tools : []
        if (tools.length) {
          handleToolsExecuted(targetIdx, tools)
        }
        messages.value[targetIdx].toolsInProgress = undefined
        pendingToolCalls = []
        scrollToBottom()
        return
      }

      if (type === 'reasoning') {
        // console.log('DEBUG: Reasoning event received', data)
        const text = (data.text ?? '').toString()
        if (!text) return
        const msg = messages.value[targetIdx]
        if (msg && msg.role === 'assistant') {
          const isDelta = data.delta === true
          const mAny = msg as any
          // 全局思考片段列表（用于无工具场景和历史存储）
          if (!Array.isArray(mAny.reasoningSegments)) {
            mAny.reasoningSegments = msg.reasoning ? [msg.reasoning] : []
          }
          const allSegs: string[] = mAny.reasoningSegments

          const hasGroups = Array.isArray(msg.toolGroups) && msg.toolGroups.length > 0
          let currentBucketKey: string | null = null
          let newBucketKey: string | null = null

          // 根据是否已经有工具分组，将思考片段归入：
          // - 工具调用前：msg.preToolReasoningSegments
          // - 某一波工具之后：对应 group.reasoningSegments
          if (!hasGroups) {
            // 仍在第一波工具调用之前
            if (!Array.isArray(mAny.preToolReasoningSegments)) {
              mAny.preToolReasoningSegments = []
            }
            const bucketSegs: string[] = mAny.preToolReasoningSegments
            let segIndex: number
            if (isDelta && msg._lastAssistantEvent === 'reasoning' && bucketSegs.length > 0 && allSegs.length > 0) {
              // 同一段思考的增量 token：追加到当前片段
              segIndex = bucketSegs.length - 1
              bucketSegs[segIndex] = (bucketSegs[segIndex] || '') + text
              allSegs[allSegs.length - 1] = (allSegs[allSegs.length - 1] || '') + text
            } else {
              // 新的一段思考过程
              bucketSegs.push(text)
              allSegs.push(text)
              segIndex = bucketSegs.length - 1
              // 无工具/无分波信息时，与模板中的 plain-${idx}-${sidx} 对齐
              newBucketKey = `plain-${targetIdx}-${segIndex}`
            }
            currentBucketKey = `plain-${targetIdx}-${segIndex}`
          } else {
            // 已经至少有一波工具调用：将思考片段归入最后一波工具之后
            const groups = msg.toolGroups as any[]
            const gidx = groups.length - 1
            const lastGroup: any = groups[gidx]
            if (!Array.isArray(lastGroup.reasoningSegments)) {
              lastGroup.reasoningSegments = []
            }
            const bucketSegs: string[] = lastGroup.reasoningSegments
            let segIndex: number
            if (isDelta && msg._lastAssistantEvent === 'reasoning' && bucketSegs.length > 0 && allSegs.length > 0) {
              segIndex = bucketSegs.length - 1
              bucketSegs[segIndex] = (bucketSegs[segIndex] || '') + text
              allSegs[allSegs.length - 1] = (allSegs[allSegs.length - 1] || '') + text
            } else {
              bucketSegs.push(text)
              allSegs.push(text)
              segIndex = bucketSegs.length - 1
              // 每一波工具后的思考片段，与模板中的 g-${idx}-${gidx}-${sidx} 对齐
              newBucketKey = `g-${targetIdx}-${gidx}-${segIndex}`
            }
            currentBucketKey = `g-${targetIdx}-${gidx}-${segIndex}`
          }

          // 合并可能重复的思考片段（部分模型会重复返回完整 reasoning 内容）
          if (allSegs.length > 1) {
            const merged: string[] = []
            for (const seg of allSegs) {
              if (!merged.length || merged[merged.length - 1] !== seg) {
                merged.push(seg)
              }
            }
            if (merged.length !== allSegs.length) {
              allSegs.splice(0, allSegs.length, ...merged)
            }
          }

          // 对于新的一段思考过程，在 UI 中自动展开对应的折叠块
          if (!isDelta && currentBucketKey) {
            reasoningBucketsOpen.value[currentBucketKey] = true
          }

          // 记录当前正在更新的思考块 key，供 Thinking 组件区分哪一段处于 thinking 状态
          ;(msg as any)._lastReasoningBucketKey = currentBucketKey

          // 兼容旧字段：将所有片段拼接成一个整体字符串（主要用于历史存储等场景）
          msg.reasoning = allSegs.join('\n\n')
          msg._hasReasoning = true
          msg._lastAssistantEvent = 'reasoning' as any
          // 第一段 reasoning 到来时自动展开
          if (msg._showReasoning === undefined) {
            msg._showReasoning = true
          }
        }
        scrollToBottom()
        return
      }

      if (type === 'retry') {
        const reason = data.reason || '工具调用失败'
        const current = data.current ?? data.retry
        const max = data.max
        messages.value[targetIdx].toolsInProgress = `🔄 工具调用失败，${reason}，正在重试 (${current}/${max})...`
        scrollToBottom()
        return
      }

      if (type === 'error') {
        const msg = data.error || '执行失败'
        messages.value[targetIdx].toolsInProgress = `❌ 工具调用失败: ${msg}`
        pendingToolCalls = []
        scrollToBottom()
        return
      }

      // 未识别类型，直接忽略或后续扩展
      return
    }

    // 非结构化事件：退化为简单的文本增量处理
    const plain = (chunk ?? '').toString()
    if (!plain) return

    // 安全检查：确保目标消息仍然存在
    if (!messages.value[targetIdx]) {
      console.warn(`⚠️ [AssistantPanel] 目标消息索引 ${targetIdx} 不存在，停止流式输出`)
      return
    }

    // 将纯文本追加到 content，并按工具完成前/后更新 preToolText/postToolText
    messages.value[targetIdx].content += plain
    const msg = messages.value[targetIdx]
    if (msg.role === 'assistant') {
      if (!msg.toolCompleted) {
        msg.preToolText = (msg.preToolText || '') + plain
      } else {
        msg.postToolText = (msg.postToolText || '') + plain
      }
      msg._lastAssistantEvent = 'token'
    }

    scrollToBottom()
  }, () => {
    // 流结束时的清理
    isStreaming.value = false
    streamCtl = null
    
    // 如果工具调用状态不是失败状态，则清除（失败状态保留以供用户查看）
    if (messages.value[targetIdx]?.toolsInProgress && 
        !messages.value[targetIdx].toolsInProgress.includes('❌')) {
      nextTick(() => {
        if (messages.value[targetIdx]) {
          messages.value[targetIdx].toolsInProgress = undefined
          pendingToolCalls = []
        }
      })
    }

    // 流结束后立即保存会话，确保最近一轮工具调用和思考过程也被持久化
    if (messages.value.length > 0) {
      saveCurrentSession()
    }
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
    // 清空内容与工具相关字段，准备重新生成
    messages.value[lastIndex].content = ''
    messages.value[lastIndex].preToolText = undefined
    messages.value[lastIndex].postToolText = undefined
    messages.value[lastIndex].toolCompleted = undefined
    messages.value[lastIndex].tools = undefined
    messages.value[lastIndex].toolGroups = undefined
    messages.value[lastIndex].toolsInProgress = undefined
    messages.value[lastIndex]._lastAssistantEvent = undefined
    // 清空推理模型的思考过程状态
    messages.value[lastIndex].reasoning = undefined
    messages.value[lastIndex].reasoningSegments = undefined
    messages.value[lastIndex].preToolReasoningSegments = undefined
    messages.value[lastIndex]._showReasoning = undefined
    messages.value[lastIndex]._hasReasoning = false
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
  // 覆盖该条助手消息（清空内容、思考过程和工具调用记录）
  const msg = messages.value[idx]
  msg.content = ''
  msg.preToolText = undefined
  msg.postToolText = undefined
  msg.toolCompleted = undefined
  msg.tools = undefined               // 清除工具调用记录
  msg.toolGroups = undefined          // 清除按波次的工具分组
  msg.toolsInProgress = undefined
  msg._lastAssistantEvent = undefined
  // 清空推理模型的思考过程状态
  msg.reasoning = undefined
  msg.reasoningSegments = undefined
  msg.preToolReasoningSegments = undefined
  msg._showReasoning = undefined
  msg._hasReasoning = false
  // 同时丢弃其后的消息（因上下文已失真）
  if (messages.value.length > idx + 1) messages.value.splice(idx + 1)
  lastRun.value = { prev: '', tail: '', targetIdx: idx }
  startStreaming('', '', idx)
}

function onToggleReasoning(idx: number) {
  const msg = messages.value[idx]
  if (!msg || msg.role !== 'assistant') return
  msg._showReasoning = !msg._showReasoning
  msg._reasoningUserToggled = true
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
    
    // 恢复 Thinking 模式设置
    if (pid) {
      const thinkingSaved = localStorage.getItem(thinkingModeKeyForProject(pid))
      if (thinkingSaved !== null) {
        useThinkingMode.value = thinkingSaved === 'true'
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

// ✅ 处理工具执行结果：将工具结果追加到指定的助手消息上
function handleToolsExecuted(targetIdx: number, tools: Array<{tool_name: string, result: any}>) {
  console.log('🔧 工具已执行:', targetIdx, tools)

  const msg = messages.value[targetIdx]
  if (!msg || msg.role !== 'assistant') return
  
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

// 过滤消息内容中的特殊标记（后端已完全统一处理所有协议标记，前端直接使用原始内容）
function filterMessageContent(content: string): string {
  if (!content) return ''
  
  // 后端已统一处理所有协议差异，前端只需返回原始内容
  return content
}

// 检测并隐藏重复的 preToolText（解决模型在 Action 前后重复输出导致的 UI 冗余及 Markdown 渲染异常）
function shouldHidePreToolText(msg: any): boolean {
  if (!msg.toolGroups || msg.toolGroups.length === 0) return false
  const pre = (msg.preToolText || '').trim()
  if (!pre) return true 

  // 获取第一波工具后的文本
  const firstGroup = msg.toolGroups[0]
  const post = (firstGroup.postText || '').trim()
  
  if (!post) return false

  // 启发式规则：
  // 1. 如果 pre 很短（< 10字符），可能是简单的确认语（"好的"），保留
  if (pre.length < 10) return false

  // 2. 如果 post 包含 pre 的前 20 个非空白字符，视为重复
  const sampleLen = 20
  const cleanPre = pre.replace(/\s/g, '').substring(0, sampleLen)
  const cleanPost = post.replace(/\s/g, '')
  
  if (cleanPost.includes(cleanPre)) {
    return true
  }
  
  return false
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
  font-family: "Segoe UI",  "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  color: var(--el-text-color-primary);
  user-select: text;  /* 允许选中文本 */
  cursor: text;  /* 显示文本光标 */
}

/* XMarkdown 内部元素也允许选中 */
.bubble-markdown :deep(*) {
  user-select: text !important;
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

/* 思考过程：整体偏淡色，用次级文字色；标题行在明暗主题下都可见 */
.reasoning-section {
  margin: 4px 0;
}
.reasoning-header {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.reasoning-label {
  color: var(--el-text-color-secondary);
}
.reasoning-arrow {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.reasoning-container .reasoning-bubble .bubble-markdown {
  color: var(--el-text-color-secondary);
}
.reasoning-container .reasoning-bubble .bubble-markdown :deep(*) {
  color: var(--el-text-color-secondary) !important;
}
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
  max-height: 300px;
  color: var(--el-text-color-primary);
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: hidden;
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


:deep(.el-thinking .trigger) {
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
}

</style> 