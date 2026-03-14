<template>
  <div class="generic-card-editor">
    <EditorHeader
      :project-name="projectName"
      :card-type="props.card.card_type.name"
      v-model:title="titleProxy"
      :dirty="isDirty"
      :saving="isSaving"
      :can-save="isDirty && !isSaving"
      :last-saved-at="lastSavedAt"
      :is-chapter-content="!!activeContentEditor"
      :needs-confirmation="props.card.needs_confirmation"
      :active-context-template-kind="activeContextTemplateKind"
      @save="handleSave"
      @generate="handleGenerateClick"
      @open-context="openDrawer = true"
      @update:active-context-template-kind="handleActiveContextTemplateKindChange"
      @delete="handleDelete"
      @open-versions="showVersions = true"
    />

    <!-- 自定义内容编辑器（如 CodeMirrorEditor）-->
    <template v-if="activeContentEditor">
      <component
        :is="activeContentEditor"
        ref="contentEditorRef"
        :card="props.card"
        :prefetched="props.prefetched"
        :context-templates="localAiContextTemplates"
        :generation-context-kind="generationContextKind"
        :review-context-kind="reviewContextKind"
        @update:generation-context-kind="handleGenerationContextKindChange"
        @update:review-context-kind="handleReviewContextKindChange"
        @switch-tab="handleSwitchTab"
        @update:dirty="handleContentEditorDirtyChange"
      />
    </template>

    <!-- 默认表单编辑器 -->
    <template v-else>
      <!-- 参数配置：显示当前模型ID，点击弹出就地配置面板 -->
      <div class="toolbar-row param-toolbar">
        <div class="param-inline">
          <el-button
            v-if="isStageOutlineCard"
            size="small"
            plain
            :loading="stageReviewLoading"
            @click="executeStageReview"
          >
            <el-icon><List /></el-icon> 阶段审核
          </el-button>
          <AIPerCardParams :card-id="props.card.id" :card-type-name="props.card.card_type?.name" />
          <el-button size="small" type="primary" plain @click="schemaStudioVisible = true">结构</el-button>
        </div>
      </div>

      <div class="editor-body">
        <div class="main-pane">
          <div v-if="schema" class="form-container">
            <template v-if="sections && sections.length">
              <SectionedForm v-if="wrapperName" :schema="innerSchema" v-model="innerData" :sections="sections" />
              <SectionedForm v-else :schema="schema" v-model="localData" :sections="sections" />
            </template>
            <template v-else>
              <ModelDrivenForm v-if="wrapperName" :schema="innerSchema" v-model="innerData" />
              <ModelDrivenForm v-else :schema="schema" v-model="localData" />
            </template>
          </div>
          <div v-else class="loading-or-error-container">
            <p v-if="schemaIsLoading">正在加载模型...</p>
            <p v-else>无法加载此卡片内容的编辑模型。</p>
          </div>
        </div>
      </div>
    </template>

    <ContextDrawer
      v-model="openDrawer"
      :context-templates="localAiContextTemplates"
      v-model:active-context-template-kind="activeContextTemplateKind"
      :preview-text="previewText"
      @apply-context="applyContextTemplateAndSave"
      @open-selector="openSelectorFromDrawer"
    >
      <template #params>
        <div class="param-placeholder">参数设置入口（已改为每卡片本地参数）</div>
      </template>
    </ContextDrawer>

    <CardReferenceSelectorDialog v-model="isSelectorVisible" :cards="cards" :currentCardId="props.card.id" @confirm="handleReferenceConfirm" />
    <CardVersionsDialog
      v-if="projectStore.currentProject?.id"
      v-model="showVersions"
      :project-id="projectStore.currentProject!.id"
      :card-id="props.card.id"
      :current-content="wrapperName ? innerData : localData"
      :current-context-templates="localAiContextTemplates"
      @restore="handleRestoreVersion"
    />

    <SchemaStudio v-model:visible="schemaStudioVisible" :mode="'card'" :target-id="props.card.id" :context-title="props.card.title" @saved="onSchemaSaved" />

    <!-- 初始提示对话框 -->
    <InitialPromptDialog
      v-model:visible="showInitialPromptDialog"
      :card-type-name="props.card.card_type?.name"
      @confirm="handleStartGeneration"
      @cancel="showInitialPromptDialog = false"
    />

    <!-- 生成面板（悬浮窗）-->
    <GenerationPanel
      ref="generationPanelRef"
      :visible="showGenerationPanel"
      @close="handleCloseGenerationPanel"
      @pause="handlePauseGeneration"
      @continue="handleContinueGeneration"
      @stop="handleStopGeneration"
      @restart="handleRestartGeneration"
    />

    <el-dialog v-model="stageReviewDialogVisible" title="阶段审核结果" width="72%">
      <div v-if="stageReviewText" class="stage-review-dialog-body">
        <div class="stage-review-overview">
          <div class="stage-review-overview-main">
            <el-tag
              v-if="stageReviewRecord"
              :type="getReviewVerdictTagType(stageReviewRecord.quality_gate)"
              effect="dark"
            >
              {{ formatReviewVerdict(stageReviewRecord.quality_gate) }}
            </el-tag>
            <span v-if="stageReviewRecord" class="stage-review-score">
              记录于 {{ formatReviewCreatedAt(stageReviewRecord.created_at) }}
            </span>
          </div>
          <p class="stage-review-summary">本次阶段审核已按标准审稿单格式存档，可直接用于回看和历史查询。</p>
        </div>

        <div class="stage-review-text-block">
          <SimpleMarkdown
            :markdown="stageReviewText || '（暂无内容）'"
            class="review-markdown"
          />
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { storeToRefs } from 'pinia'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useAIStore } from '@renderer/stores/useAIStore'
import { usePerCardAISettingsStore, type PerCardAIParams } from '@renderer/stores/usePerCardAISettingsStore'
import { getCardAIParams, updateCardAIParams, applyCardAIParamsToType } from '@renderer/api/setting'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { schemaService } from '@renderer/api/schema'
import type { JSONSchema } from '@renderer/api/schema'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import ModelDrivenForm from '../dynamic-form/ModelDrivenForm.vue'
import SectionedForm from '../dynamic-form/SectionedForm.vue'
import { mergeSections, autoGroup, type SectionConfig } from '@renderer/services/uiLayoutService'
import CardReferenceSelectorDialog from './CardReferenceSelectorDialog.vue'
import EditorHeader from '../common/EditorHeader.vue'
import ContextDrawer from '../common/ContextDrawer.vue'
import CardVersionsDialog from '../common/CardVersionsDialog.vue'
import { cloneDeep, isEqual } from 'lodash-es'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { ElMessage, ElMessageBox } from 'element-plus'
import SimpleMarkdown from '../common/SimpleMarkdown.vue'
import { addVersion } from '@renderer/services/versionService'
import { List } from '@element-plus/icons-vue'
import { useAppStore } from '@renderer/stores/useAppStore'
import { useAIStore as useAIStoreForOptions } from '@renderer/stores/useAIStore'
import SchemaStudio from '../shared/SchemaStudio.vue'
import AIPerCardParams from '../common/AIPerCardParams.vue'
// 移除 AssistantSidebar 相关导入与逻辑
import { resolveTemplate } from '@renderer/services/contextResolver'
import {
  buildContextTemplateUpdatePayload,
  cloneContextTemplates,
  getCardContextTemplates,
  getContextTemplateByKind,
  normalizeContextTemplateKind,
  type ContextTemplateKind,
  type ContextTemplates,
} from '@renderer/services/contextSlots'
import {
  runStageReview,
  type PreviousStageInput,
  type ReviewRecord,
  type StageChapterOutlineInput,
  type StageReviewRunRequest,
} from '@renderer/api/chapterReviews'
// 指令流生成相关导入
import GenerationPanel from '../generation/GenerationPanel.vue'
import InitialPromptDialog from '../generation/InitialPromptDialog.vue'
import { InstructionExecutor } from '@renderer/services/instructionExecutor'
import { generateWithInstructionStream } from '@renderer/api/generation'
import type { Instruction, ConversationMessage } from '@renderer/types/instruction'

const props = defineProps<{
  card: CardRead
  prefetched?: any
}>()

const cardStore = useCardStore()
const aiStore = useAIStore()
const perCardStore = usePerCardAISettingsStore()
const projectStore = useProjectStore()
const aiStoreForOptions = useAIStoreForOptions()
const appStore = useAppStore()

const { cards } = storeToRefs(cardStore)
const isDarkMode = computed(() => appStore.isDarkMode)

const openDrawer = ref(false)
const isSelectorVisible = ref(false)
const showVersions = ref(false)
const schemaStudioVisible = ref(false)
const assistantVisible = ref(false)
const stageReviewLoading = ref(false)
const stageReviewDialogVisible = ref(false)
const stageReviewText = ref('')
const stageReviewRecord = ref<ReviewRecord | null>(null)
const stageReviewAbortController = ref<AbortController | null>(null)
const assistantResolvedContext = ref<string>('')
const assistantEffectiveSchema = ref<any>(null)
const prefetchedContext = ref<any>(null)

// 指令流生成相关状态
const showInitialPromptDialog = ref(false)
const showGenerationPanel = ref(false)
const generationPanelRef = ref<InstanceType<typeof GenerationPanel>>()
const instructionExecutor = ref<InstructionExecutor | null>(null)
const currentAbortController = ref<AbortController | null>(null)
const conversationHistory = ref<ConversationMessage[]>([])

// --- 内容编辑器动态映射 ---
// 类似 CardEditorHost 的 editorMap，但这里是内容编辑器（共享外壳）
const contentEditorMap: Record<string, any> = {
  CodeMirrorEditor: defineAsyncComponent(() => import('../editors/CodeMirrorEditor.vue')),
  MarkdownTextEditor: defineAsyncComponent(() => import('../editors/MarkdownTextEditor.vue')),
  // 未来可以添加更多内容编辑器，例如：
  // RichTextEditor: defineAsyncComponent(() => import('../editors/RichTextEditor.vue')),
  // MarkdownEditor: defineAsyncComponent(() => import('../editors/MarkdownEditor.vue')),
}

// 根据 card_type.editor_component 选择内容编辑器
const activeContentEditor = computed(() => {
  const editorName = props.card?.card_type?.editor_component
  if (editorName && contentEditorMap[editorName]) {
    return contentEditorMap[editorName]
  }
  return null // null 表示使用默认的表单编辑器
})

const isStageOutlineCard = computed(() => props.card.card_type?.name === '阶段大纲')

// 通用的内容编辑器引用（可以是 CodeMirrorEditor 或其他）
const contentEditorRef = ref<any>(null)
const contentEditorDirty = ref(false)

function handleSwitchTab(tab: string) {
  const evt = new CustomEvent('nf:switch-right-tab', { detail: { tab } })
  window.dispatchEvent(evt)
}

function handleContentEditorDirtyChange(dirty: boolean) {
  contentEditorDirty.value = dirty
}

function getResolvedContextByKind(kind: ContextTemplateKind | string | null | undefined, currentContent?: any) {
  const editingContent = currentContent ?? (wrapperName.value ? innerData.value : localData.value)
  const currentCardForResolve = { ...props.card, content: editingContent }
  const template = getContextTemplateByKind(props.card, localAiContextTemplates.value, kind, 'generation')
  return resolveTemplate({ template, cards: cards.value, currentCard: currentCardForResolve as any })
}

function handleGenerationContextKindChange(kind: ContextTemplateKind | string) {
  generationContextKind.value = normalizeContextTemplateKind(kind, 'generation')
}

function handleReviewContextKindChange(kind: ContextTemplateKind | string) {
  reviewContextKind.value = normalizeContextTemplateKind(kind, 'review')
}

function handleActiveContextTemplateKindChange(kind: ContextTemplateKind | string) {
  activeContextTemplateKind.value = normalizeContextTemplateKind(kind, 'generation')
}

function openAssistant() {
  assistantResolvedContext.value = getResolvedContextByKind(generationContextKind.value)
  // 读取有效 Schema 作为对话指导
  import('@renderer/api/setting').then(async ({ getCardSchema }) => {
    try {
      const resp = await getCardSchema(props.card.id)
      assistantEffectiveSchema.value = resp?.effective_schema || resp?.json_schema || null
    } catch { assistantEffectiveSchema.value = null }
  })
  assistantVisible.value = true
}

const isSaving = ref(false)
const localData = ref<any>({})
const localAiContextTemplates = ref<ContextTemplates>(cloneContextTemplates())
const originalData = ref<any>({})
const originalAiContextTemplates = ref<ContextTemplates>(cloneContextTemplates())
const activeContextTemplateKind = ref<ContextTemplateKind>('generation')
const generationContextKind = ref<ContextTemplateKind>('generation')
const reviewContextKind = ref<ContextTemplateKind>('review')
const schema = ref<JSONSchema | undefined>(undefined)
const schemaIsLoading = ref(false)
let atIndexForInsertion = -1
const sections = ref<SectionConfig[] | undefined>(undefined)
const wrapperName = ref<string | undefined>(undefined)
const innerSchema = ref<JSONSchema | undefined>(undefined)
const innerData = computed({
  get: () => {
    if (!wrapperName.value) return localData.value
    return (localData.value && localData.value[wrapperName.value]) || {}
  },
  set: (v: any) => {
    if (!wrapperName.value) { localData.value = v; return }
    localData.value = { ...(localData.value || {}), [wrapperName.value]: v }
  }
})

// AI 可选项（模型/提示词/输出模型）
const aiOptions = ref<AIConfigOptions | null>(null)
async function loadAIOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }

const projectName = '当前项目'
const lastSavedAt = ref<string | undefined>(undefined)

// 顶部标题与表单 Title 字段保持同步
// 1) 初始化为 card.title，切换卡片时重置
const titleProxy = ref(props.card.title)
watch(
  () => props.card.title,
  (v) => {
    titleProxy.value = v
  }
)

// 2) 顶部标题变更 -> 写回表单数据中的 title（若存在）
watch(
  titleProxy,
  (v) => {
    if (!localData.value) {
      localData.value = { title: v }
      return
    }
    if ((localData.value as any).title === v) return
    localData.value = { ...(localData.value || {}), title: v }
  }
)

// 3) 表单中的 title 字段变更 -> 回写到标题栏
watch(
  () => (localData.value && (localData.value as any).title),
  (v) => {
    if (typeof v === 'string' && v !== titleProxy.value) {
      titleProxy.value = v
    }
  }
)

const isDirty = computed(() => {
  const ctxDirty = !isEqual(localAiContextTemplates.value, originalAiContextTemplates.value)
  const titleDirty = titleProxy.value !== props.card.title

  // 使用自定义内容编辑器（如章节正文）：
  // 只要正文内容、上下文模板或标题有任一改动，都视为未保存
  if (activeContentEditor.value) {
    return contentEditorDirty.value || ctxDirty || titleDirty
  }

  // 默认表单编辑器：比较内容 + 上下文模板 + 标题
  return !isEqual(localData.value, originalData.value) || ctxDirty || titleDirty
})

watch(
  () => props.card,
  async (newCard) => {
    if (newCard) {
      localData.value = cloneDeep(newCard.content) || {}
      localAiContextTemplates.value = getCardContextTemplates(newCard)
      originalData.value = cloneDeep(newCard.content) || {}
      originalAiContextTemplates.value = getCardContextTemplates(newCard)
      activeContextTemplateKind.value = 'generation'
      generationContextKind.value = 'generation'
      reviewContextKind.value = 'review'
      titleProxy.value = newCard.title
      await loadSchemaForCard(newCard)
      // 载入每卡片参数
      await loadAIOptions()
      // 优先从后端读取有效参数
      try {
        const resp = await getCardAIParams(newCard.id)
        const eff = resp?.effective_params
        if (eff) editingParams.value = { ...eff }
      } catch {}
      if (!editingParams.value || Object.keys(editingParams.value).length === 0) {
        const preset = getPresetForType(newCard.card_type?.name) || {}
        editingParams.value = { ...preset }
      }
      if (!editingParams.value.llm_config_id) {
        const first = aiOptions.value?.llm_configs?.[0]
        if (first) editingParams.value.llm_config_id = first.id
      }
      // 本地兼容保存
      perCardStore.setForCard(newCard.id, editingParams.value)
    }
  },
  { immediate: true, deep: true }
)

const perCardParams = computed(() => perCardStore.getByCardId(props.card.id))
const editingParams = ref<PerCardAIParams>({})

const selectedModelName = computed(() => {
  try {
    const id = (perCardParams.value || editingParams.value)?.llm_config_id
    const list = aiOptions.value?.llm_configs || []
    const found = list.find(m => m.id === id)
    return found?.display_name || (id != null ? String(id) : '')
  } catch { return '' }
})

const paramSummary = computed(() => {
  const p = perCardParams.value || editingParams.value
  const model = selectedModelName.value ? `模型:${selectedModelName.value}` : '模型:未设'
  const prompt = p?.prompt_name ? `提示词:${p.prompt_name}` : '提示词:未设'
  const t = p?.temperature != null ? `温度:${p.temperature}` : ''
  const m = p?.max_tokens != null ? `max_tokens:${p.max_tokens}` : ''
  return [model, prompt, t, m].filter(Boolean).join(' · ')
})

function formatReviewVerdict(verdict?: ReviewRecord['quality_gate'] | null): string {
  switch (verdict) {
    case 'pass':
      return '基本通过'
    case 'block':
      return '高风险拦截'
    default:
      return '建议修改'
  }
}

function getReviewVerdictTagType(verdict?: ReviewRecord['quality_gate'] | null): 'success' | 'warning' | 'danger' {
  switch (verdict) {
    case 'pass':
      return 'success'
    case 'block':
      return 'danger'
    default:
      return 'warning'
  }
}

function formatReviewCreatedAt(value?: string | null): string {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return value
  }
}

function isCanceledRequest(error: unknown): boolean {
  const candidate = error as { code?: string; name?: string; message?: string }
  return candidate?.code === 'ERR_CANCELED'
    || candidate?.name === 'CanceledError'
    || candidate?.message === 'canceled'
    || candidate?.message === 'CanceledError'
}

function getCurrentEditingContent() {
  return cloneDeep(wrapperName.value ? innerData.value : localData.value) || {}
}

function getStageVolumeNumber(content: any): number | null {
  const value = Number(content?.volume_number)
  return Number.isFinite(value) ? value : null
}

function getStageNumber(content: any): number | null {
  const value = Number(content?.stage_number)
  return Number.isFinite(value) ? value : null
}

function getStageReferenceChapter(content: any): number[] {
  if (!Array.isArray(content?.reference_chapter)) return []
  return content.reference_chapter
    .map((item: any) => Number(item))
    .filter((item: number) => Number.isFinite(item))
    .slice(0, 2)
}

function getOrderedStageCards(currentContent?: any): CardRead[] {
  return [...(cards.value || [])]
    .filter((item: any) => item?.card_type?.name === '阶段大纲')
    .map((item: any) => {
      const content = item.id === props.card.id && currentContent ? currentContent : (item?.content || {})
      return {
        card: item,
        volumeNumber: getStageVolumeNumber(content) ?? 0,
        stageNumber: getStageNumber(content) ?? 0,
      }
    })
    .filter(item => item.volumeNumber > 0 && item.stageNumber > 0)
    .sort((a, b) => {
      if (a.volumeNumber !== b.volumeNumber) return a.volumeNumber - b.volumeNumber
      return a.stageNumber - b.stageNumber
    })
    .map(item => item.card)
}

function getPreviousStagesForReview(currentContent: any): PreviousStageInput[] {
  const currentVolumeNumber = getStageVolumeNumber(currentContent)
  const currentStageNumber = getStageNumber(currentContent)
  if (currentVolumeNumber == null || currentStageNumber == null) return []

  const ordered = getOrderedStageCards(currentContent)
  const currentIndex = ordered.findIndex(item => item.id === props.card.id)
  if (currentIndex <= 0) return []

  return ordered
    .slice(Math.max(0, currentIndex - 1), currentIndex)
    .map((item: any) => {
      const content = item?.content || {}
      return {
        title: item?.title || content?.stage_name || '未命名阶段',
        stage_name: content?.stage_name || null,
        volume_number: getStageVolumeNumber(content),
        stage_number: getStageNumber(content),
        reference_chapter: getStageReferenceChapter(content),
        overview: String(content?.overview || ''),
        analysis: content?.analysis || '',
        entity_snapshot: Array.isArray(content?.entity_snapshot) ? content.entity_snapshot.map((entry: any) => String(entry)) : [],
      }
    })
}

function getStageChapterOutlinesForReview(currentContent: any): StageChapterOutlineInput[] {
  const stageVolumeNumber = getStageVolumeNumber(currentContent)
  const stageNumber = getStageNumber(currentContent)
  const chapterContentMap = new Map<number, { hasContent: boolean; wordCount: number | null }>()

  for (const item of cards.value || []) {
    if ((item as any)?.card_type?.name !== '章节正文') continue
    const content = (item as any)?.content || {}
    const volumeNumber = Number(content?.volume_number)
    const chapterStageNumber = Number(content?.stage_number)
    const chapterNumber = Number(content?.chapter_number)
    if (!Number.isFinite(volumeNumber) || !Number.isFinite(chapterStageNumber) || !Number.isFinite(chapterNumber)) continue
    if (stageVolumeNumber != null && volumeNumber !== stageVolumeNumber) continue
    if (stageNumber != null && chapterStageNumber !== stageNumber) continue
    const text = String(content?.content || '')
    chapterContentMap.set(chapterNumber, {
      hasContent: text.trim().length > 0,
      wordCount: text.trim().length > 0 ? text.replace(/\s+/g, '').length : 0,
    })
  }

  const childOutlineCards = (cards.value || [])
    .filter((item: any) => item?.parent_id === props.card.id && item?.card_type?.name === '章节大纲')
    .map((item: any) => {
      const content = item?.content || {}
      const chapterNumber = Number(content?.chapter_number)
      return {
        title: String(content?.title || item?.title || '未命名章节'),
        chapter_number: Number.isFinite(chapterNumber) ? chapterNumber : null,
        overview: String(content?.overview || ''),
        entity_list: Array.isArray(content?.entity_list) ? content.entity_list.map((entry: any) => String(entry)) : [],
      }
    })
    .sort((a, b) => {
      const aNum = a.chapter_number ?? Number.MAX_SAFE_INTEGER
      const bNum = b.chapter_number ?? Number.MAX_SAFE_INTEGER
      return aNum - bNum
    })

  const fallbackOutlineList = Array.isArray(currentContent?.chapter_outline_list) ? currentContent.chapter_outline_list : []
  const sourceList = childOutlineCards.length ? childOutlineCards : fallbackOutlineList

  return sourceList.map((item: any) => {
    const chapterNumber = Number(item?.chapter_number)
    const chapterMeta = Number.isFinite(chapterNumber) ? chapterContentMap.get(chapterNumber) : undefined
    return {
      title: String(item?.title || '未命名章节'),
      chapter_number: Number.isFinite(chapterNumber) ? chapterNumber : null,
      overview: String(item?.overview || ''),
      entity_list: Array.isArray(item?.entity_list) ? item.entity_list.map((entry: any) => String(entry)) : [],
      has_content: chapterMeta?.hasContent ?? false,
      word_count: chapterMeta?.wordCount ?? null,
    }
  })
}

function formatStageSnapshot(currentContent: any, chapterOutlines: StageChapterOutlineInput[]): string {
  const lines: string[] = [
    '[阶段信息]',
    `- 标题：${titleProxy.value || props.card.title || '未命名阶段'}`,
  ]

  if (currentContent?.stage_name) lines.push(`- 阶段名：${String(currentContent.stage_name)}`)
  if (getStageVolumeNumber(currentContent) != null) lines.push(`- 卷号：${getStageVolumeNumber(currentContent)}`)
  if (getStageNumber(currentContent) != null) lines.push(`- 阶段号：${getStageNumber(currentContent)}`)

  const referenceChapter = getStageReferenceChapter(currentContent)
  if (referenceChapter.length >= 2) {
    lines.push(`- 参考章节范围：${referenceChapter[0]} - ${referenceChapter[1]}`)
  }

  if (currentContent?.analysis) {
    lines.push('', '[阶段分析]', String(currentContent.analysis))
  }
  if (currentContent?.overview) {
    lines.push('', '[阶段概述]', String(currentContent.overview))
  }
  if (Array.isArray(currentContent?.entity_snapshot) && currentContent.entity_snapshot.length) {
    lines.push('', '[阶段末实体快照]')
    for (const item of currentContent.entity_snapshot) {
      lines.push(`- ${String(item)}`)
    }
  }
  if (chapterOutlines.length) {
    lines.push('', '[章节列表]')
    chapterOutlines.forEach((item, index) => {
      const chapterLabel = item.chapter_number != null ? `第${item.chapter_number}章` : `章节${index + 1}`
      lines.push(`${index + 1}. ${chapterLabel} ${item.title}`.trim())
      if (item.overview) lines.push(`概述：${item.overview}`)
      if (item.entity_list?.length) lines.push(`出场实体：${item.entity_list.join('、')}`)
      lines.push(`是否已有正文：${item.has_content ? '是' : '否'}`)
      if (item.word_count != null) lines.push(`正文字数：${item.word_count}`)
    })
  }

  return lines.join('\n').trim()
}

function formatFactsFromContext(ctx: any | null | undefined): string {
  try {
    if (!ctx) return ''
    const factsStruct: any = (ctx as any)?.facts_structured || {}
    const lines: string[] = []
    if (Array.isArray(factsStruct.fact_summaries) && factsStruct.fact_summaries.length) {
      lines.push('关键事实:')
      for (const s of factsStruct.fact_summaries) lines.push(`- ${s}`)
    }
    if (Array.isArray(factsStruct.relation_summaries) && factsStruct.relation_summaries.length) {
      lines.push('关系摘要:')
      for (const r of factsStruct.relation_summaries) {
        lines.push(`- ${r.a} ↔ ${r.b}（${r.kind}）`)
        if (r.description) lines.push(`  · ${r.description}`)
        if (r.a_to_b_addressing || r.b_to_a_addressing) {
          const addressingParts: string[] = []
          if (r.a_to_b_addressing) addressingParts.push(`A称B：${r.a_to_b_addressing}`)
          if (r.b_to_a_addressing) addressingParts.push(`B称A：${r.b_to_a_addressing}`)
          lines.push(`  · ${addressingParts.join(' / ')}`)
        }
        if (Array.isArray(r.recent_dialogues) && r.recent_dialogues.length) {
          lines.push('  · 对话样例：')
          for (const d of r.recent_dialogues) lines.push(`    - ${d}`)
        }
        if (Array.isArray(r.recent_event_summaries) && r.recent_event_summaries.length) {
          lines.push('  · 近期事件：')
          for (const ev of r.recent_event_summaries) {
            const tags: string[] = []
            if (ev.volume_number != null) tags.push(`卷${ev.volume_number}`)
            if (ev.chapter_number != null) tags.push(`章${ev.chapter_number}`)
            lines.push(`    - ${ev.summary}${tags.length ? `（${tags.join(' ')}）` : ''}`)
          }
        }
      }
    }
    return lines.join('\n').trim()
  } catch {
    return ''
  }
}

async function applyAndSavePerCardParams() {
  try {
    await updateCardAIParams(props.card.id, { ...editingParams.value })
    perCardStore.setForCard(props.card.id, { ...editingParams.value })
    ElMessage.success('已保存')
  } catch { ElMessage.error('保存失败') }
}

async function restoreParamsFollowType() {
  try {
    await updateCardAIParams(props.card.id, null)
    ElMessage.success('已恢复跟随类型')
    const resp = await getCardAIParams(props.card.id)
    const eff = resp?.effective_params
    if (eff) editingParams.value = { ...eff }
  } catch { ElMessage.error('操作失败') }
}

async function applyParamsToType() {
  try {
    // 1) 先把当前编辑值保存到该卡片（作为来源）
    await updateCardAIParams(props.card.id, { ...editingParams.value })
    // 2) 应用到类型
    await applyCardAIParamsToType(props.card.id)
    // 通知设置页刷新
    window.dispatchEvent(new Event('card-types-updated'))
    // 3) 应用到类型后，默认让当前卡片恢复跟随类型，以便参数与顶部显示立即一致
    await updateCardAIParams(props.card.id, null)
    const resp = await getCardAIParams(props.card.id)
    const eff = resp?.effective_params
    if (eff) {
      editingParams.value = { ...eff }
      perCardStore.setForCard(props.card.id, { ...eff })
    }
    ElMessage.success('已应用到类型，并恢复本卡片跟随类型')
  } catch { ElMessage.error('应用失败') }
}

function resetToPreset() {
  const preset = getPresetForType(props.card.card_type?.name) || {}
  if (!preset.llm_config_id) {
    const first = aiOptions.value?.llm_configs?.[0]
    if (first) preset.llm_config_id = first.id
  }
  editingParams.value = { ...preset }
  perCardStore.setForCard(props.card.id, editingParams.value)
}

function getPresetForType(typeName?: string) : PerCardAIParams | undefined {
  // 兼容旧预设：按照类型名提供简易默认值
  const map: Record<string, PerCardAIParams> = {
    '金手指': { prompt_name: '金手指生成', response_model_name: 'SpecialAbilityResponse', temperature: 0.6, max_tokens: 1024, timeout: 60 },
    '一句话梗概': { prompt_name: '一句话梗概', response_model_name: 'OneSentence', temperature: 0.6, max_tokens: 1024, timeout: 60 },
    '故事大纲': { prompt_name: '一段话大纲', response_model_name: 'ParagraphOverview', temperature: 0.6, max_tokens: 2048, timeout: 60 },
    '世界观设定': { prompt_name: '世界观设定', response_model_name: 'WorldBuilding', temperature: 0.6, max_tokens: 8192, timeout: 120 },
    '核心蓝图': { prompt_name: '核心蓝图', response_model_name: 'Blueprint', temperature: 0.6, max_tokens: 8192, timeout: 120 },
    '分卷大纲': { prompt_name: '分卷大纲', response_model_name: 'VolumeOutline', temperature: 0.6, max_tokens: 8192, timeout: 120 },
    '阶段大纲': { prompt_name: '阶段大纲', response_model_name: 'StageLine', temperature: 0.6, max_tokens: 8192, timeout: 120 },
    '章节大纲': { prompt_name: '章节大纲', response_model_name: 'ChapterOutline', temperature: 0.6, max_tokens: 4096, timeout: 60 },
    '写作指南': { prompt_name: '写作指南', response_model_name: 'WritingGuide', temperature: 0.7, max_tokens: 8192, timeout: 60 },
    '章节正文': { prompt_name: '内容生成', temperature: 0.7, max_tokens: 8192, timeout: 60 },
  }
  return map[typeName || '']
}

async function loadSchemaForCard(card: CardRead) {
  schemaIsLoading.value = true
  try {
    // 优先从后端按类型/实例读取 schema
    try {
      const { getCardSchema } = await import('@renderer/api/setting')
      const resp = await getCardSchema(card.id)
      const effective = (resp?.effective_schema || resp?.json_schema)
      if (effective) {
        schema.value = effective
      }
    } catch {}
    if (!schema.value) {
      // 回退：仍走原有 schemaService 以避免首轮迁移空值导致空白
      const typeName = (card.card_type as any)?.name as string | undefined
      await schemaService.loadSchemas()
      if (!typeName) {
        schema.value = undefined
        sections.value = undefined
        wrapperName.value = undefined
        innerSchema.value = undefined
        return
      }
      schema.value = schemaService.getSchema(typeName)
      if (!schema.value) {
        await schemaService.refreshSchemas()
        schema.value = schemaService.getSchema(typeName)
      }
    }
    const props: any = (schema.value as any)?.properties || {}
    const keys = Object.keys(props)
    const onlyKey = keys.length === 1 ? keys[0] : undefined
    const isObject = onlyKey && (props[onlyKey]?.type === 'object' || props[onlyKey]?.$ref || props[onlyKey]?.anyOf)
    if (onlyKey && isObject) {
      wrapperName.value = onlyKey
      const maybeRef = props[onlyKey]
      if (maybeRef && typeof maybeRef === 'object' && '$ref' in maybeRef && typeof maybeRef.$ref === 'string') {
        const refName = maybeRef.$ref.split('/').pop() || ''
        const localDefs = (schema.value as any)?.$defs || {}
        innerSchema.value = localDefs[refName] || schemaService.getSchema(refName) || maybeRef
      } else {
        innerSchema.value = maybeRef
      }
    } else {
      wrapperName.value = undefined
      innerSchema.value = undefined
    }
    const schemaForLayout = (wrapperName.value ? innerSchema.value : schema.value) as any
    const schemaMeta = schemaForLayout?.['x-ui'] || undefined
    const backendLayout = (schemaForLayout?.['ui_layout'] || undefined)
    sections.value = mergeSections({ schemaMeta, backendLayout, frontendDefault: autoGroup(schemaForLayout) })
  } finally { schemaIsLoading.value = false }
}

function handleReferenceConfirm(reference: string) {
  const kind = activeContextTemplateKind.value
  const currentText = localAiContextTemplates.value[kind]
  if (atIndexForInsertion < 0) {
    // 若未通过 @ 触发，则直接在末尾追加
    localAiContextTemplates.value = {
      ...localAiContextTemplates.value,
      [kind]: `${currentText}${reference}`,
    }
    ElMessage.success('已插入引用')
    return
  }
  const isAt = currentText.charAt(atIndexForInsertion) === '@'
  const before = currentText.substring(0, atIndexForInsertion)
  const after = currentText.substring(atIndexForInsertion + (isAt ? 1 : 0))
  localAiContextTemplates.value = {
    ...localAiContextTemplates.value,
    [kind]: before + reference + after,
  }
  atIndexForInsertion = -1
  ElMessage.success('已插入引用')
}

function applyContextTemplate(payload: { kind: ContextTemplateKind; text: string }) {
  const kind = normalizeContextTemplateKind(payload?.kind, activeContextTemplateKind.value)
  localAiContextTemplates.value = {
    ...localAiContextTemplates.value,
    [kind]: typeof payload?.text === 'string' ? payload.text : String(payload?.text || ''),
  }
}

async function applyContextTemplateAndSave(payload: { kind: ContextTemplateKind; text: string }) {
  applyContextTemplate(payload)
  ElMessage.success('上下文模板已应用')
  openDrawer.value = false
  await handleSave()
}

// Alt+K 打开抽屉
function keyHandler(e: KeyboardEvent) {
  if ((e.altKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    openDrawer.value = true
  }
  if ((e.altKey || e.metaKey) && (e.key === 'j' || e.key === 'J')) {
    e.preventDefault()
    openAssistant()
  }
}

onMounted(() => { window.addEventListener('keydown', keyHandler) })
onBeforeUnmount(() => {
  try { stageReviewAbortController.value?.abort() } catch {}
  window.removeEventListener('keydown', keyHandler)
})

// 在抽屉中输入 @ 时弹出选择器
let drawerTextarea: HTMLTextAreaElement | null = null
watch(() => openDrawer.value, (v) => {
  if (v) {
    nextTick(() => {
      drawerTextarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
      drawerTextarea?.addEventListener('input', handleDrawerInput)
    })
  } else {
    drawerTextarea?.removeEventListener('input', handleDrawerInput)
    drawerTextarea = null
    atIndexForInsertion = -1
  }
})

function handleDrawerInput(ev: Event) {
  const textarea = ev.target as HTMLTextAreaElement
  // 同步抽屉内文本到本地模板，避免选择器插入时丢失前缀
  localAiContextTemplates.value = {
    ...localAiContextTemplates.value,
    [activeContextTemplateKind.value]: textarea.value,
  }
  const cursorPos = textarea.selectionStart
  const lastChar = textarea.value.substring(cursorPos - 1, cursorPos)
  if (lastChar === '@') {
    atIndexForInsertion = cursorPos - 1
    isSelectorVisible.value = true
  }
}

function openSelectorFromDrawer(payload?: { kind?: ContextTemplateKind; text?: string }) {
  if (payload?.kind) activeContextTemplateKind.value = normalizeContextTemplateKind(payload.kind, activeContextTemplateKind.value)
  const textarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
  if (textarea) {
    localAiContextTemplates.value = {
      ...localAiContextTemplates.value,
      [activeContextTemplateKind.value]: textarea.value,
    }
    // 在光标当前位置插入，不回退一位
    atIndexForInsertion = textarea.selectionStart
  }
  isSelectorVisible.value = true
}

const previewText = computed(() => localAiContextTemplates.value[activeContextTemplateKind.value] || '')

async function handleSave() {
  const templatesBeforeSave = cloneContextTemplates(localAiContextTemplates.value)
  const previousTemplatesOnCard = getCardContextTemplates(props.card)
  // 自定义内容编辑器的保存逻辑（如 CodeMirrorEditor）
  if (activeContentEditor.value && contentEditorRef.value) {
    try {
      isSaving.value = true
      // 将当前标题传递给内容编辑器，由内容编辑器统一负责保存 title 与正文内容
      const savedContent = await contentEditorRef.value.handleSave(titleProxy.value)

      if (!isEqual(templatesBeforeSave, previousTemplatesOnCard)) {
        try {
          await cardStore.modifyCard(props.card.id, {
            ...buildContextTemplateUpdatePayload(templatesBeforeSave),
          } as any)
        } catch {}
      }

      // 保存历史版本
      try {
        if (projectStore.currentProject?.id && savedContent) {
          await addVersion(projectStore.currentProject.id, {
            cardId: props.card.id,
            projectId: projectStore.currentProject.id,
            title: titleProxy.value,
            content: savedContent,
            ...buildContextTemplateUpdatePayload(templatesBeforeSave),
          })
        }
      } catch (e) {
        console.error('Failed to add version:', e)
      }

      contentEditorDirty.value = false
      originalAiContextTemplates.value = cloneContextTemplates(templatesBeforeSave)
      lastSavedAt.value = new Date().toLocaleTimeString()
      ElMessage.success('保存成功')
    } catch (e) {
      ElMessage.error('保存失败')
    } finally {
      isSaving.value = false
    }
    return
  }

  // 默认表单编辑器的保存逻辑
  try {
    isSaving.value = true
    const updatePayload: CardUpdate = {
      title: titleProxy.value,
      content: cloneDeep(localData.value),
      ...buildContextTemplateUpdatePayload(templatesBeforeSave),
      needs_confirmation: false,  // 清除 AI 修改标记，触发工作流
    }
    await cardStore.modifyCard(props.card.id, updatePayload)
    try {
      await addVersion(projectStore.currentProject!.id!, {
        cardId: props.card.id,
        projectId: projectStore.currentProject!.id!,
        title: titleProxy.value,
        content: updatePayload.content as any,
        ...buildContextTemplateUpdatePayload(templatesBeforeSave),
      })
    } catch {}
    originalData.value = cloneDeep(localData.value)
    originalAiContextTemplates.value = cloneContextTemplates(templatesBeforeSave)
    lastSavedAt.value = new Date().toLocaleTimeString()
    ElMessage.success('保存成功！')
  } finally { isSaving.value = false }
}

async function executeStageReview() {
  if (!isStageOutlineCard.value) return

  const currentContent = getCurrentEditingContent()
  const chapterOutlines = getStageChapterOutlinesForReview(currentContent)
  const hasStageCoreContent = Boolean(
    String(currentContent?.overview || '').trim() ||
    String(currentContent?.analysis || '').trim() ||
    chapterOutlines.length
  )
  if (!hasStageCoreContent) {
    ElMessage.warning('请先完善当前阶段内容后再审核')
    return
  }

  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) {
    ElMessage.error('请先设置有效的模型ID')
    return
  }

  stageReviewLoading.value = true
  stageReviewText.value = ''
  stageReviewRecord.value = null
  const abortController = new AbortController()
  stageReviewAbortController.value = abortController

  try {
    const resolvedContext = getResolvedContextByKind(reviewContextKind.value, currentContent)

    const payload: StageReviewRunRequest = {
      card_id: props.card.id,
      project_id: projectStore.currentProject?.id || props.card.project_id,
      title: titleProxy.value || props.card.title || '未命名阶段',
      stage_name: currentContent?.stage_name || titleProxy.value || props.card.title || null,
      volume_number: getStageVolumeNumber(currentContent),
      stage_number: getStageNumber(currentContent),
      reference_chapter: getStageReferenceChapter(currentContent),
      analysis: String(currentContent?.analysis || ''),
      overview: String(currentContent?.overview || ''),
      entity_snapshot: Array.isArray(currentContent?.entity_snapshot) ? currentContent.entity_snapshot.map((item: any) => String(item)) : [],
      chapter_outlines: chapterOutlines,
      previous_stages: getPreviousStagesForReview(currentContent),
      context_info: resolvedContext.trim() || undefined,
      facts_info: formatFactsFromContext(props.prefetched).trim() || undefined,
      content_snapshot: formatStageSnapshot(currentContent, chapterOutlines),
      llm_config_id: p.llm_config_id,
      prompt_name: '阶段审核',
    }

    if (typeof p.temperature === 'number') payload.temperature = p.temperature
    if (typeof p.max_tokens === 'number') payload.max_tokens = Math.min(p.max_tokens, 6144)
    if (typeof p.timeout === 'number') payload.timeout = p.timeout

    const result = await runStageReview(payload, { signal: abortController.signal }).catch((e) => {
      if (isCanceledRequest(e)) return null
      throw e
    })
    if (!result) return
    stageReviewText.value = result.review_text
    stageReviewRecord.value = result.record
    stageReviewDialogVisible.value = true
    window.dispatchEvent(new CustomEvent('nf:review-history-refresh'))
    ElMessage.success('阶段审核完成')
  } catch (e) {
    console.error('阶段审核失败:', e)
    ElMessage.error('阶段审核失败')
  } finally {
    if (stageReviewAbortController.value === abortController) {
      stageReviewAbortController.value = null
    }
    stageReviewLoading.value = false
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(`确认删除卡片「${props.card.title}」？此操作不可恢复`, '删除确认', { type: 'warning' })
    await cardStore.removeCard(props.card.id)
    ElMessage.success('卡片已删除')
    const evt = new CustomEvent('nf:navigate', { detail: { to: 'market' } })
    window.dispatchEvent(evt)
  } catch (e) {
  }
}

// ==================== 指令流生成相关方法 ====================

/**
 * 点击生成按钮时触发
 */
function handleGenerateClick() {
  // 显示初始提示对话框
  showInitialPromptDialog.value = true
}

/**
 * 开始生成（用户确认初始提示后）
 */
async function handleStartGeneration(userPrompt: string, useExistingContent: boolean) {
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) {
    ElMessage.error('请先设置有效的模型ID')
    return
  }

  try {
    // 1. 获取有效 Schema
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) {
      ElMessage.error('未找到此卡片的结构（Schema）。')
      return
    }

    // 2. 解析上下文
    const editingContent = wrapperName.value ? innerData.value : localData.value
    const resolvedContext = getResolvedContextByKind(generationContextKind.value)

    // 3. 初始化指令执行器（根据选项决定是否使用现有内容）
    const initialData = useExistingContent ? (editingContent || {}) : {}
    instructionExecutor.value = new InstructionExecutor(initialData)

    // 4. 重置对话历史
    conversationHistory.value = []

    // 5. 显示生成面板并重置状态
    showGenerationPanel.value = true
    await nextTick()

    // 重置面板状态（清空消息）
    if (generationPanelRef.value) {
      generationPanelRef.value.reset()
    }

    // 6. 显示用户要求（如果有）
    // 必须要要在 reset 之后添加，否则会被 reset 清空
    if (userPrompt && generationPanelRef.value) {
      console.log('Adding user prompt to panel:', userPrompt)
      // 使用 setTimeout 确保在 reset 的 DOM 更新后执行
      setTimeout(() => {
        generationPanelRef.value?.addMessage('user', userPrompt)
      }, 0)
    }

    // 7. 开始生成
    if (generationPanelRef.value) {
      generationPanelRef.value.startGeneration()
    }

    // 8. 调用生成 API
    await performGeneration(userPrompt, effective, resolvedContext, p, useExistingContent)
  } catch (e) {
    console.error('启动生成失败:', e)
    ElMessage.error('启动生成失败')
  }
}

/**
 * 执行生成
 */
async function performGeneration(
  userPrompt: string,
  schema: any,
  contextInfo: string,
  params: PerCardAIParams,
  useExistingContent: boolean
) {
  // 创建 AbortController
  currentAbortController.value = new AbortController()

  try {
    await generateWithInstructionStream(
      {
        llm_config_id: params.llm_config_id!,
        user_prompt: userPrompt,
        response_model_schema: schema,
        // 根据选项决定是否传递现有内容
        current_data: useExistingContent ? (instructionExecutor.value?.getData() || {}) : {},
        conversation_context: conversationHistory.value,
        context_info: contextInfo,
        prompt_template: params.prompt_name,
        temperature: params.temperature,
        max_tokens: params.max_tokens,
        timeout: params.timeout
      },
      {
        onThinking: (text) => {
          generationPanelRef.value?.addMessage('thinking', text)
        },
        onInstruction: (instruction: Instruction) => {
          // 执行指令
          instructionExecutor.value?.execute(instruction)

          // 更新 UI
          const data = instructionExecutor.value?.getData()
          if (data) {
            import('lodash-es').then(({ cloneDeep }) => {
              const clonedData = cloneDeep(data)
              if (wrapperName.value) {
                innerData.value = clonedData
              } else {
                localData.value = clonedData
              }
            })
          }

          // 显示指令执行消息
          const actionText = formatInstructionAction(instruction)
          generationPanelRef.value?.addMessage('action', actionText)
          generationPanelRef.value?.incrementCompletedFields()
        },
        onWarning: (text) => {
          generationPanelRef.value?.addMessage('warning', text)
        },
        onError: (text) => {
          generationPanelRef.value?.addMessage('error', text)
          generationPanelRef.value?.finishGeneration(false, text)
        },
        onDone: async (success, message, finalData) => {
          if (success) {
            // 如果后端回传了最终完整数据（包含默认值注入），则合并更新
            if (finalData) {
              console.log('Received final data from backend:', finalData)
              const { mergeWith, isArray } = await import('lodash-es')
              const arrayOverwrite = (objValue: any, srcValue: any) => {
                if (isArray(objValue) || isArray(srcValue)) {
                  return srcValue
                }
                return undefined
              }
              if (wrapperName.value) {
                const mergedInner = mergeWith({}, innerData.value || {}, finalData, arrayOverwrite)
                innerData.value = mergedInner
              } else {
                const merged = mergeWith({}, localData.value || {}, finalData, arrayOverwrite)
                localData.value = merged
              }
            }
            generationPanelRef.value?.finishGeneration(true, message)
            ElMessage.success(message || '生成完成！')
          } else {
            generationPanelRef.value?.finishGeneration(false, message)
          }
        }
      },
      currentAbortController.value.signal
    )
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      console.error('生成失败:', error)
      generationPanelRef.value?.addMessage('error', error.message || '生成失败')
      generationPanelRef.value?.finishGeneration(false)
    }
  }
}

/**
 * 格式化指令为可读文本
 */
function formatInstructionAction(instruction: Instruction): string {
  if (instruction.op === 'set') {
    const path = instruction.path.replace(/^\//, '').replace(/\//g, ' > ')
    return `设置字段: ${path}`
  } else if (instruction.op === 'append') {
    const path = instruction.path.replace(/^\//, '').replace(/\//g, ' > ')
    return `添加元素到: ${path}`
  } else if (instruction.op === 'done') {
    return '生成完成'
  }
  return '执行指令'
}

/**
 * 关闭生成面板
 */
function handleCloseGenerationPanel() {
  // 中断当前生成
  if (currentAbortController.value) {
    currentAbortController.value.abort()
    currentAbortController.value = null
  }

  showGenerationPanel.value = false
  instructionExecutor.value = null
  conversationHistory.value = []
}

/**
 * 暂停生成
 */
function handlePauseGeneration() {
  if (currentAbortController.value) {
    currentAbortController.value.abort()
    currentAbortController.value = null
  }
}

/**
 * 继续生成
 */
async function handleContinueGeneration(userMessage: string) {
  // 将用户消息添加到对话历史
  conversationHistory.value.push({
    role: 'user',
    content: userMessage
  })

  // 获取参数
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) {
    ElMessage.error('请先设置有效的模型ID')
    return
  }

  try {
    // 获取 Schema 和上下文
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) {
      ElMessage.error('未找到此卡片的结构（Schema）。')
      return
    }

    const resolvedContext = getResolvedContextByKind(generationContextKind.value)

    // 继续生成（总是基于现有内容）
    await performGeneration(userMessage, effective, resolvedContext, p, true)
  } catch (e) {
    console.error('继续生成失败:', e)
    ElMessage.error('继续生成失败')
  }
}

/**
 * 停止生成
 */
function handleStopGeneration() {
  handleCloseGenerationPanel()
}

/**
 * 重新开始生成
 */
function handleRestartGeneration() {
  // 重置执行器
  const editingContent = wrapperName.value ? innerData.value : localData.value
  instructionExecutor.value = new InstructionExecutor(editingContent || {})

  // 重置对话历史
  conversationHistory.value = []

  // 显示初始提示对话框
  showGenerationPanel.value = false
  showInitialPromptDialog.value = true
}

// ==================== 原有的生成方法（保留作为备用）====================

async function handleGenerate() {
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) { ElMessage.error('请先设置有效的模型ID'); return }
  const resolvedContext = getResolvedContextByKind(generationContextKind.value)
  try {
    // 直接读取有效 Schema 并作为 response_model_schema 发送
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) { ElMessage.error('未找到此卡片的结构（Schema）。'); return }
    const sampling = { temperature: p.temperature, max_tokens: p.max_tokens, timeout: p.timeout }
    const result = await aiStore.generateContentWithSchema(effective as any, resolvedContext, p.llm_config_id!, p.prompt_name ?? undefined, sampling)
    if (result) {
      const { mergeWith, isArray } = await import('lodash-es')
      const arrayOverwrite = (objValue: any, srcValue: any) => {
        if (isArray(objValue) || isArray(srcValue)) {
          return srcValue
        }
        return undefined
      }
      if (wrapperName.value) {
        const mergedInner = mergeWith({}, innerData.value || {}, result, arrayOverwrite)
        innerData.value = mergedInner
      } else {
        const merged = mergeWith({}, localData.value || {}, result, arrayOverwrite)
        localData.value = merged
      }
      ElMessage.success('内容生成成功！')
    }
  } catch (e) { console.error('AI generation failed:', e) }
}

async function handleRestoreVersion(v: any) {
  showVersions.value = false

  // 自定义内容编辑器的恢复逻辑（如 CodeMirrorEditor）
  if (activeContentEditor.value && contentEditorRef.value) {
    try {
      ElMessage.success('已恢复版本，自动保存中...')

      // 通知内容编辑器恢复内容（需要编辑器实现 restoreContent 方法）
      if (typeof contentEditorRef.value.restoreContent === 'function') {
        await contentEditorRef.value.restoreContent(v.content)
      }

      // 恢复上下文模板
      localAiContextTemplates.value = cloneContextTemplates({
        generation: v.ai_context_template ?? localAiContextTemplates.value.generation,
        review: v.ai_context_template_review ?? localAiContextTemplates.value.review,
        custom: v.ai_context_template_custom ?? localAiContextTemplates.value.custom,
      })

      // 保存恢复的内容
      await handleSave()

      // 刷新卡片数据
      await cardStore.fetchCards(projectStore.currentProject!.id!)

      ElMessage.success('版本已恢复并保存')
    } catch (e) {
      console.error('Failed to restore content editor version:', e)
      ElMessage.error('恢复版本失败')
    }
    return
  }

  // 默认表单编辑器的恢复逻辑
  if (wrapperName.value) innerData.value = v.content
  else localData.value = v.content
  localAiContextTemplates.value = cloneContextTemplates({
    generation: v.ai_context_template ?? localAiContextTemplates.value.generation,
    review: v.ai_context_template_review ?? localAiContextTemplates.value.review,
    custom: v.ai_context_template_custom ?? localAiContextTemplates.value.custom,
  })
  ElMessage.success('已恢复版本，自动保存中...')
  await handleSave()
}

async function onSchemaSaved() {
  // 保存结构后刷新 schema 并重算分区
  await loadSchemaForCard(props.card)
}

async function handleAssistantFinalize(summary: string) {
  try {
    const p = perCardStore.getByCardId(props.card.id) || editingParams.value
    if (!p?.llm_config_id) { ElMessage.error('请先设置有效的模型ID'); return }
    // 将对话要点与上下文合并，作为输入文本（不再附加卡片提示词模板）
    const resolvedContextText = getResolvedContextByKind(generationContextKind.value)
    const inputText = `${resolvedContextText}\n\n[对话要点]\n${summary}`
    // 读取有效 Schema
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) { ElMessage.error('未找到此卡片的结构（Schema）。'); return }
    const sampling = { temperature: p.temperature, max_tokens: p.max_tokens, timeout: p.timeout }
    const result = await aiStore.generateContentWithSchema(effective as any, inputText, p.llm_config_id!, p.prompt_name ?? undefined, sampling)
    if (result) {
      const { mergeWith, isArray } = await import('lodash-es')
      const arrayOverwrite = (objValue: any, srcValue: any) => {
        if (isArray(objValue) || isArray(srcValue)) {
          return srcValue
        }
        return undefined
      }
      if (wrapperName.value) {
        const mergedInner = mergeWith({}, innerData.value || {}, result, arrayOverwrite)
        innerData.value = mergedInner
      } else {
        const merged = mergeWith({}, localData.value || {}, result, arrayOverwrite)
        localData.value = merged
      }
      assistantVisible.value = false
      ElMessage.success('定稿生成完成！')
    }
  } catch (e) { console.error('Finalize generate failed:', e) }
}
</script>

<style scoped>
.generic-card-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden; /* 防止整体滚动 */
}

/* 确保自定义内容编辑器（如 CodeMirrorEditor）占据剩余空间 */
.generic-card-editor > :deep(.chapter-studio),
.generic-card-editor > :deep([class*="-editor"]) {
  flex: 1;
  min-height: 0;
}

.editor-body { display: grid; grid-template-columns: 1fr; gap: 0; flex: 1; overflow: hidden; }
.main-pane { overflow: auto; padding: 12px; }
.form-container { display: flex; flex-direction: column; gap: 12px; }
.loading-or-error-container { text-align: center; padding: 2rem; color: var(--el-text-color-secondary); }
.toolbar-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-light); }
.param-toolbar { padding: 6px 12px; border-bottom: 1px solid var(--el-border-color-light); justify-content: flex-end; }
.param-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ai-config-form { padding: 4px 2px; }
/* 固定按钮宽度并对模型名称省略显示 */
:deep(.model-trigger) { width: 230px; min-width: 220px; max-width: 260px; box-sizing: border-box; }
:deep(.model-trigger .el-button__content) { width: 100%; display: inline-flex; align-items: center; gap: 4px; overflow: hidden; }
.model-label { flex: 0 0 auto; }
.model-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; flex-wrap: wrap; }
.ai-actions .left, .ai-actions .right { display: flex; gap: 6px; align-items: center; }

.stage-review-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-height: 72vh;
  overflow: auto;
}

.stage-review-overview {
  padding: 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}

.stage-review-overview-main {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.stage-review-score {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  font-weight: 600;
}

.stage-review-summary {
  margin: 0;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}

.stage-review-text-block {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

:deep(.review-markdown) {
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.8;
  word-break: break-word;
}

:deep(.review-markdown h1),
:deep(.review-markdown h2),
:deep(.review-markdown h3),
:deep(.review-markdown h4),
:deep(.review-markdown h5),
:deep(.review-markdown h6) {
  margin-top: 0;
  color: var(--el-text-color-primary);
}

:deep(.review-markdown p),
:deep(.review-markdown li),
:deep(.review-markdown blockquote) {
  color: var(--el-text-color-primary);
}

:deep(.review-markdown pre) {
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
}

:deep(.review-markdown code) {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}
</style>
