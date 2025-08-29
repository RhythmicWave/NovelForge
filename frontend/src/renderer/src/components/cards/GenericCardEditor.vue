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
      @save="handleSave"
      @generate="handleGenerate"
      @open-context="openDrawer = true"
      @delete="handleDelete"
      @open-versions="showVersions = true"
    />

    <!-- 参数配置：显示当前模型ID，点击弹出就地配置面板 -->
    <div class="toolbar-row param-toolbar">
      <div class="param-inline">
        <AIPerCardParams :card-id="props.card.id" :card-type-name="props.card.card_type?.name" />
        <el-button v-if="props.card.card_type.name === '章节正文' && projectStore.currentProject?.id" size="small" @click="openStudio">专注创作</el-button>
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

    <ContextDrawer
      v-model="openDrawer"
      :context-template="localAiContextTemplate"
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
      :current-context-template="localAiContextTemplate"
      @restore="handleRestoreVersion"
    />

    <SchemaStudio v-model:visible="schemaStudioVisible" :mode="'card'" :target-id="props.card.id" :context-title="props.card.title" @saved="onSchemaSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
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
import { addVersion } from '@renderer/services/versionService'
import { Setting } from '@element-plus/icons-vue'
import { useAIStore as useAIStoreForOptions } from '@renderer/stores/useAIStore'
import SchemaStudio from '../shared/SchemaStudio.vue'
import AIPerCardParams from '../common/AIPerCardParams.vue'

const props = defineProps<{ card: CardRead }>()

const cardStore = useCardStore()
const aiStore = useAIStore()
const perCardStore = usePerCardAISettingsStore()
const projectStore = useProjectStore()
const aiStoreForOptions = useAIStoreForOptions()

const { cards } = storeToRefs(cardStore)

const openDrawer = ref(false)
const isSelectorVisible = ref(false)
const showVersions = ref(false)
const schemaStudioVisible = ref(false)

const isSaving = ref(false)
const localData = ref<any>({})
const localAiContextTemplate = ref<string>('')
const originalData = ref<any>({})
const originalAiContextTemplate = ref<string>('')
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
const titleProxy = ref(props.card.title)
watch(() => props.card.title, v => titleProxy.value = v)
watch(titleProxy, v => localData.value = { ...localData.value, title: v })

const isDirty = computed(() => {
  return !isEqual(localData.value, originalData.value) || localAiContextTemplate.value !== originalAiContextTemplate.value
})

watch(
  () => props.card,
  async (newCard) => {
    if (newCard) {
      localData.value = cloneDeep(newCard.content) || {}
      localAiContextTemplate.value = newCard.ai_context_template || ''
      originalData.value = cloneDeep(newCard.content) || {}
      originalAiContextTemplate.value = newCard.ai_context_template || ''
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
  if (atIndexForInsertion < 0) {
    // 若未通过 @ 触发，则直接在末尾追加
    localAiContextTemplate.value = `${localAiContextTemplate.value}${reference}`
    ElMessage.success('已插入引用')
    return
  }
  const text = localAiContextTemplate.value
  const isAt = text.charAt(atIndexForInsertion) === '@'
  const before = text.substring(0, atIndexForInsertion)
  const after = text.substring(atIndexForInsertion + (isAt ? 1 : 0))
  localAiContextTemplate.value = before + reference + after
  atIndexForInsertion = -1
  ElMessage.success('已插入引用')
}

function applyContextTemplate(text: string) {
  localAiContextTemplate.value = text
}

async function applyContextTemplateAndSave(text: string) {
  localAiContextTemplate.value = typeof text === 'string' ? text : String(text)
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
}

onMounted(() => { window.addEventListener('keydown', keyHandler) })
onBeforeUnmount(() => { window.removeEventListener('keydown', keyHandler) })

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
  localAiContextTemplate.value = textarea.value
  const cursorPos = textarea.selectionStart
  const lastChar = textarea.value.substring(cursorPos - 1, cursorPos)
  if (lastChar === '@') {
    atIndexForInsertion = cursorPos - 1
    isSelectorVisible.value = true
  }
}

function openSelectorFromDrawer() {
  const textarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
  if (textarea) {
    localAiContextTemplate.value = textarea.value
    // 在光标当前位置插入，不回退一位
    atIndexForInsertion = textarea.selectionStart
  }
  isSelectorVisible.value = true
}

const previewText = computed(() => localAiContextTemplate.value)

async function handleSave() {
  try {
    isSaving.value = true
    const updatePayload: CardUpdate = {
      title: titleProxy.value,
      content: cloneDeep(localData.value),
      ai_context_template: localAiContextTemplate.value,
    }
    await cardStore.modifyCard(props.card.id, updatePayload)
    try {
      await addVersion(projectStore.currentProject!.id!, {
        cardId: props.card.id,
        projectId: projectStore.currentProject!.id!,
        title: titleProxy.value,
        content: updatePayload.content as any,
        ai_context_template: localAiContextTemplate.value,
      })
    } catch {}
    originalData.value = cloneDeep(localData.value)
    originalAiContextTemplate.value = localAiContextTemplate.value
    lastSavedAt.value = new Date().toLocaleTimeString()
    ElMessage.success('保存成功！')
  } finally { isSaving.value = false }
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

async function handleGenerate() {
  const p = perCardStore.getByCardId(props.card.id) || editingParams.value
  if (!p?.llm_config_id) { ElMessage.error('请先设置有效的模型ID'); return }
  const { resolveTemplate } = await import('@renderer/services/contextResolver')
  const editingContent = wrapperName.value ? innerData.value : localData.value
  const currentCardForResolve = { ...props.card, content: editingContent }
  const resolvedContext = resolveTemplate({ template: localAiContextTemplate.value, cards: cards.value, currentCard: currentCardForResolve as any })
  try {
    // 直接读取有效 Schema 并作为 response_model_schema 发送
    const { getCardSchema } = await import('@renderer/api/setting')
    const resp = await getCardSchema(props.card.id)
    const effective = resp?.effective_schema || resp?.json_schema
    if (!effective) { ElMessage.error('未找到此卡片的结构（Schema）。'); return }
    const sampling = { temperature: p.temperature, max_tokens: p.max_tokens, timeout: p.timeout }
    const result = await aiStore.generateContentWithSchema(effective as any, resolvedContext, p.llm_config_id!, p.prompt_name ?? undefined, sampling)
    if (result) { localData.value = result; ElMessage.success('内容生成成功！') }
  } catch (e) { console.error('AI generation failed:', e) }
}

async function handleRestoreVersion(v: any) {
  // 恢复版本内容并保存
  if (wrapperName.value) innerData.value = v.content
  else localData.value = v.content
  localAiContextTemplate.value = v.ai_context_template || localAiContextTemplate.value
  showVersions.value = false
  ElMessage.success('已恢复版本，自动保存中...')
  await handleSave()
}

function openStudio() {
  const pid = projectStore.currentProject?.id
  if (!pid) return
  // @ts-ignore
  window.api?.openChapterStudio?.(pid, props.card.id)
}

async function onSchemaSaved() {
  // 保存结构后刷新 schema 并重算分区
  await loadSchemaForCard(props.card)
}
</script>

<style scoped>
.generic-card-editor { display: flex; flex-direction: column; height: 100%; }
.editor-body { display: grid; grid-template-columns: 1fr; gap: 0; flex: 1; overflow: hidden; }
.main-pane { overflow: auto; padding: 12px; }
.form-container { display: flex; flex-direction: column; gap: 12px; }
.loading-or-error-container { text-align: center; padding: 2rem; color: var(--el-text-color-secondary); }
.toolbar-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-light); }
.param-toolbar { padding: 6px 12px; border-bottom: 1px solid var(--el-border-color-light); justify-content: flex-end; }
.param-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.summary-tooltip { display: inline-flex; align-items: center; }
.param-summary { display: inline-flex; align-items: center; height: 28px; line-height: 28px; width: 360px; min-width: 360px; max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.param-summary .el-tag__content) { display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-config-form { padding: 4px 2px; }
/* 固定按钮宽度并对模型名称省略显示 */
:deep(.model-trigger) { width: 280px; min-width: 280px; max-width: 280px; box-sizing: border-box; }
:deep(.model-trigger .el-button__content) { width: 100%; display: inline-flex; align-items: center; gap: 4px; overflow: hidden; }
.model-label { flex: 0 0 auto; }
.model-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; flex-wrap: wrap; }
.ai-actions .left, .ai-actions .right { display: flex; gap: 6px; align-items: center; }
</style> 